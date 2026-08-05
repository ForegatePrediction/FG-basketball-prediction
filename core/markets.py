#!/usr/bin/env python3
"""由双方期望得分 + 正态近似,产出篮球玩法:胜负 / 让分 / 大小分(全场 + 半场)。
净胜分 ~ Normal(margin_mean, sd_margin);总分 ~ Normal(total_mean, sd_total)。
半场:期望得分按上半场占比拆分,标准差按 /√2 缩放。"""
import math

SD_MARGIN = 14.9   # NBA 实测;其它联赛可在 config 覆盖
SD_TOTAL = 18.9
FH_SHARE = 0.504   # 上半场得分占比


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _spread(margin_mean, sd, lines):
    # 主队让 line 分(line<0=主队让分):P(净胜 + line > 0)= P(margin > -line)
    out = {}
    for L in lines:
        p = 1 - _phi((-L - margin_mean) / sd)  # P(margin > -L)
        out[str(L)] = {"line": L, "home": p, "away": 1 - p}
    return out


def _totals(total_mean, sd, lines):
    out = {}
    for T in lines:
        over = 1 - _phi((T - total_mean) / sd)
        out[str(T)] = {"line": T, "over": over, "under": 1 - over}
    return out


def _block(ph, pa, sd_m, sd_t, spread_lines, total_lines):
    mm = ph - pa; tm = ph + pa
    return {
        "expected_points": {"home": round(ph, 1), "away": round(pa, 1), "total": round(tm, 1)},
        "moneyline": {"home": _phi(mm / sd_m), "away": 1 - _phi(mm / sd_m)},
        "spreads": _spread(mm, sd_m, spread_lines),
        "totals": _totals(tm, sd_t, total_lines),
    }


def _lines_around(center, step, n):
    base = round(center / step) * step
    return [round(base + step * k, 1) for k in range(-n, n + 1)]


def markets(ph, pa, sd_margin=SD_MARGIN, sd_total=SD_TOTAL, fh_share=FH_SHARE):
    tm = ph + pa; mm = ph - pa
    sl = _lines_around(mm, 1.0, 6) + [-x for x in _lines_around(mm, 1.0, 6)]  # 覆盖主客让分整数线
    sl = sorted(set([round(x * 2) / 2 for x in _lines_around(mm, 1.5, 6)]))    # 主队让分线(半分)
    tl = sorted(set(_lines_around(tm, 2.0, 5)))                                 # 大小分线
    full = _block(ph, pa, sd_margin, sd_total, sl, tl)
    # 半场:期望得分按占比拆,σ 按 /√2
    h_ph, h_pa = ph * fh_share, pa * fh_share
    h_mm, h_tm = h_ph - h_pa, h_ph + h_pa
    hsl = sorted(set(_lines_around(h_mm, 1.0, 5)))
    htl = sorted(set(_lines_around(h_tm, 2.0, 4)))
    half = _block(h_ph, h_pa, sd_margin / math.sqrt(2), sd_total / math.sqrt(2), hsl, htl)
    return {"full_game": full, "first_half": half}
