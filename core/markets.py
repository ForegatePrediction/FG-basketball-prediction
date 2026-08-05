#!/usr/bin/env python3
"""由双方期望得分 + 正态近似,产出尽可能多的篮球玩法(不含球员盘/需要临场数据的玩法)。
净胜分 ~ Normal(margin_mean, sd_margin);总分 ~ Normal(total_mean, sd_total)。
分段(半场/单节)按得分占比拆均值、按时间份额缩放标准差(独立增量假设:σ ∝ √时间)。
球队得分 ~ Normal(该队期望分, sd_team),sd_team 由 sd_margin/sd_total 解析推导。

产出:
  full_game / first_half / second_half / q1..q4:各含 expected_points + moneyline + spreads + totals + team_totals
  winning_margin           净胜分区间(主/客 1-5 / 6-10 / 11-15 / 16+)
  highest_scoring_half     最高得分半场(first / second)
  highest_scoring_quarter  最高得分单节(q1..q4)
  double_result            半场领先×全场胜(home_home / home_away / away_home / away_away)
"""
import math

SD_MARGIN = 14.7
SD_TOTAL = 20.0
FH_SHARE = 0.505
# 各节得分占比(NBA 实测,主客平均);上半场 = q1+q2
Q_SHARES = [0.2531, 0.2519, 0.2535, 0.2416]


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _spread(mm, sd, lines):
    out = {}
    for L in lines:
        p = 1 - _phi((-L - mm) / sd)   # P(净胜 > -line)
        out[str(L)] = {"line": L, "home": p, "away": 1 - p}
    return out


def _totals(tm, sd, lines):
    out = {}
    for T in lines:
        over = 1 - _phi((T - tm) / sd)
        out[str(T)] = {"line": T, "over": over, "under": 1 - over}
    return out


def _team_totals(mean_pts, sd_team, lines):
    out = {}
    for T in lines:
        over = 1 - _phi((T - mean_pts) / sd_team)
        out[str(T)] = {"line": T, "over": over, "under": 1 - over}
    return out


def _lines_around(center, step, n):
    base = round(center / step) * step
    return sorted({round(base + step * k, 1) for k in range(-n, n + 1)})


def _block(ph, pa, sd_m, sd_t, n_spread=6, n_total=5, n_team=3):
    mm, tm = ph - pa, ph + pa
    sd_team = math.sqrt(sd_m * sd_m + sd_t * sd_t) / 2.0
    return {
        "expected_points": {"home": round(ph, 1), "away": round(pa, 1), "total": round(tm, 1)},
        "moneyline": {"home": _phi(mm / sd_m), "away": 1 - _phi(mm / sd_m)},
        "spreads": _spread(mm, sd_m, _lines_around(mm, 1.0, n_spread)),
        "totals": _totals(tm, sd_t, _lines_around(tm, 2.0, n_total)),
        "team_totals": {"home": _team_totals(ph, sd_team, _lines_around(ph, 2.0, n_team)),
                        "away": _team_totals(pa, sd_team, _lines_around(pa, 2.0, n_team))},
    }


def _winning_margin(mm, sd):
    def band(lo, hi):   # P(lo < margin <= hi)
        return _phi((hi - mm) / sd) - _phi((lo - mm) / sd)
    return {
        "home_1_5": band(0.5, 5.5), "home_6_10": band(5.5, 10.5),
        "home_11_15": band(10.5, 15.5), "home_16plus": 1 - _phi((15.5 - mm) / sd),
        "away_1_5": band(-5.5, -0.5), "away_6_10": band(-10.5, -5.5),
        "away_11_15": band(-15.5, -10.5), "away_16plus": _phi((-15.5 - mm) / sd),
    }


def _highest_scoring_half(tm, sd_t, fh_share):
    """1H 总分 vs 2H 总分。两半独立增量,各 σ = sd_t/√2 → 差的 σ = sd_t。"""
    mean_diff = tm * fh_share - tm * (1 - fh_share)
    p_first = _phi(mean_diff / sd_t)
    return {"first": p_first, "second": 1 - p_first}


def _highest_scoring_quarter(tm, sd_t, shares):
    """各节总分 ~ N(tm*share_k, sd_t/2);数值积分求“该节最高”概率。"""
    means = [tm * s for s in shares]
    sd_q = sd_t / 2.0
    lo, hi = min(means) - 6 * sd_q, max(means) + 6 * sd_q
    N = 400; step = (hi - lo) / N
    probs = [0.0] * 4
    for i in range(N):
        x = lo + (i + 0.5) * step
        pdf = [math.exp(-((x - m) ** 2) / (2 * sd_q * sd_q)) / (sd_q * math.sqrt(2 * math.pi)) for m in means]
        cdf = [_phi((x - m) / sd_q) for m in means]
        for k in range(4):
            others = 1.0
            for j in range(4):
                if j != k:
                    others *= cdf[j]
            probs[k] += pdf[k] * others * step
    s = sum(probs) or 1.0
    return {f"q{k+1}": probs[k] / s for k in range(4)}


def _bvn_upper(h, k, rho):
    """P(Z1>h, Z2>k),标准二元正态,相关系数 rho(Drezner–Wesolowsky 高斯积分近似)。"""
    if rho == 0:
        return (1 - _phi(h)) * (1 - _phi(k))
    X = [0.04691008, 0.23076534, 0.5, 0.76923466, 0.95308992]
    W = [0.018854042, 0.038088059, 0.0452707394, 0.038088059, 0.018854042]
    hk = h * k
    if abs(rho) < 0.925:
        hs = (h * h + k * k) / 2.0
        asr = math.asin(rho)
        bvn = 0.0
        for i in range(5):
            sn1 = math.sin(asr * (X[i] + 1) / 2.0)
            sn2 = math.sin(asr * (-X[i] + 1) / 2.0)
            bvn += W[i] * math.exp((sn1 * hk - hs) / (1 - sn1 * sn1))
            bvn += W[i] * math.exp((sn2 * hk - hs) / (1 - sn2 * sn2))
        bvn = bvn * asr / (4 * math.pi) + (1 - _phi(h)) * (1 - _phi(k))
    else:
        bvn = (1 - _phi(max(h, k))) if rho > 0 else max(0.0, (1 - _phi(h)) - _phi(k))
    return min(max(bvn, 0.0), 1.0)


def _double_result(mm, sd_m, fh_share):
    """半场领先方 × 全场胜方。半场净胜 M1~N(mm*fh_share, σ1),全场净胜 M~N(mm, sd_m)。
    Cov(M1,M)=Var(M1) → 相关 rho = σ1/sd_m。"""
    s1 = sd_m / math.sqrt(2)
    mu1 = mm * fh_share
    rho = s1 / sd_m
    h, k = -mu1 / s1, -mm / sd_m
    hh = _bvn_upper(h, k, rho)             # 半场主领先 & 全场主胜
    ha = max((1 - _phi(h)) - hh, 0.0)      # 半场主领先 & 全场客胜
    ah = max((1 - _phi(k)) - hh, 0.0)      # 半场客领先 & 全场主胜
    aa = max(1 - hh - ha - ah, 0.0)        # 半场客领先 & 全场客胜
    z = (hh + ha + ah + aa) or 1.0
    return {"home_home": hh / z, "home_away": ha / z, "away_home": ah / z, "away_away": aa / z}


def markets(ph, pa, sd_margin=SD_MARGIN, sd_total=SD_TOTAL, fh_share=FH_SHARE, q_shares=None):
    q_shares = q_shares or Q_SHARES
    mm, tm = ph - pa, ph + pa
    sd_h_m, sd_h_t = sd_margin / math.sqrt(2), sd_total / math.sqrt(2)   # 半场
    sd_q_m, sd_q_t = sd_margin / 2.0, sd_total / 2.0                      # 单节

    out = {"full_game": _block(ph, pa, sd_margin, sd_total)}
    out["first_half"] = _block(ph * fh_share, pa * fh_share, sd_h_m, sd_h_t, n_spread=5, n_total=4)
    sh = 1 - fh_share
    out["second_half"] = _block(ph * sh, pa * sh, sd_h_m, sd_h_t, n_spread=5, n_total=4)
    for k in range(4):
        s = q_shares[k]
        out[f"q{k+1}"] = _block(ph * s, pa * s, sd_q_m, sd_q_t, n_spread=4, n_total=3, n_team=2)
    out["winning_margin"] = _winning_margin(mm, sd_margin)
    out["highest_scoring_half"] = _highest_scoring_half(tm, sd_total, fh_share)
    out["highest_scoring_quarter"] = _highest_scoring_quarter(tm, sd_total, q_shares)
    out["double_result"] = _double_result(mm, sd_margin, fh_share)
    return out
