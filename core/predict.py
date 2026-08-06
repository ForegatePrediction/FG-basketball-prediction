#!/usr/bin/env python3
"""读 config + ratings 快照,零训练秒出篮球玩法(胜负/让分/大小分,全场+半场)。
三语理由;队名模糊匹配;可选盘口混合口径(moneyline)。"""
import json, os, unicodedata as _ud, re as _re
from .ratings import PointsRatings
from .markets import markets
from .odds import devig_two, divergence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(ROOT, "games")

_ABBR = {"la": "losangeles", "ny": "newyork", "gs": "goldenstate", "sa": "sanantonio",
         "okc": "oklahomacity", "phi": "philadelphia", "st": "saint"}


def _load(code):
    d = os.path.join(GAMES, str(code))
    cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
    ref = cfg.get("pool_ref")
    snap = json.load(open(os.path.join(GAMES, str(ref) if ref else str(code), "ratings.json"), encoding="utf-8"))
    return cfg, snap


def _toks(s):
    s = _ud.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = _re.sub(r"[^a-z0-9 ]", " ", s)
    return [_ABBR.get(t, t) for t in s.split() if t]


def _find(teams, name):
    if name in teams:
        return name
    nl = name.lower().strip()
    c = [t for t in teams if nl in t.lower() or t.lower() in nl]
    if c:
        return max(c, key=lambda t: teams[t].get("gp", 0))
    q = set(_toks(name))
    if not q:
        return None
    best, bs = None, 0.0
    for t in teams:
        tt = set(_toks(t))
        if not tt:
            continue
        sub = sum(1 for x in q for y in tt if len(x) > 3 and (x in y or y in x))
        sc = (len(q & tt) + 0.5 * sub) / max(len(q), len(tt))
        if sc > bs:
            best, bs = t, sc
    return best if bs >= 0.5 else None


def _pc(x):
    return f"{round((x or 0) * 100)}%"


def _half_line(A, B, h, lang):
    """上/下半场一句:预计比分 + 领先方概率 + 半场总分。"""
    ml = h["moneyline"]; ep = h["expected_points"]; pc = _pc
    fav, favp = (A, ml["home"]) if ml["home"] >= ml["away"] else (B, ml["away"])
    if lang == "en":
        return f"Projected {ep['home']} : {ep['away']}, {fav} lead {pc(favp)}; total {ep['total']}"
    if lang == "vi":
        return f"Dự báo {ep['home']} : {ep['away']}, {fav} dẫn {pc(favp)}; tổng {ep['total']}"
    return f"預計 {ep['home']} : {ep['away']},{fav} 領先機率 {pc(favp)};總分 {ep['total']}"


def _reasons(A, B, mk, p, lang):
    """逐玩法量化依据,key 对齐 platform_markets + 半场。三语:zh(繁體)/en/vi。
    覆盖:moneyline/spreads/totals/soccer_extra_time/first_half/second_half/winning_margin。"""
    f = mk["full_game"]; ml = f["moneyline"]; eg = f["expected_points"]; pc = _pc
    fav, favp = (A, ml["home"]) if ml["home"] >= ml["away"] else (B, ml["away"])
    mm = round(eg["home"] - eg["away"], 1)          # 主队净胜(正=主胜)
    line = -abs(mm)                                  # 让分线(受让方视角)
    fav_side = A if mm >= 0 else B
    p_ot = ((p or {}).get("soccer_extra_time") or {}).get("yes", 0.0)
    wm = mk["winning_margin"]
    band = max(wm, key=wm.get)                       # 最可能净胜区间
    _bz = {"home_1_5": (A, "1-5"), "home_6_10": (A, "6-10"), "home_11_15": (A, "11-15"),
           "home_16plus": (A, "16+"), "away_1_5": (B, "1-5"), "away_6_10": (B, "6-10"),
           "away_11_15": (B, "11-15"), "away_16plus": (B, "16+")}
    bteam, brange = _bz[band]
    h1, h2 = mk.get("first_half"), mk.get("second_half")
    if lang == "en":
        r = {"moneyline": [f"Projected score {A} {eg['home']} : {eg['away']} {B}",
                           f"Model lean: {fav} {pc(favp)} to win"],
             "spreads": [f"Fair line: {fav_side} {line}"],
             "totals": [f"Projected total {eg['total']}"],
             "soccer_extra_time": [f"Overtime likelihood: {pc(p_ot)}"],
             "winning_margin": [f"Most likely: {bteam} by {brange} ({pc(wm[band])})"]}
    elif lang == "vi":
        r = {"moneyline": [f"Dự báo tỉ số {A} {eg['home']} : {eg['away']} {B}",
                           f"Mô hình nghiêng: {fav} thắng {pc(favp)}"],
             "spreads": [f"Kèo chấp hợp lý: {fav_side} {line}"],
             "totals": [f"Tổng điểm dự báo {eg['total']}"],
             "soccer_extra_time": [f"Khả năng vào hiệp phụ: {pc(p_ot)}"],
             "winning_margin": [f"Khả năng cao: {bteam} thắng {brange} ({pc(wm[band])})"]}
    else:  # zh — 繁體中文
        r = {"moneyline": [f"預計比分 {A} {eg['home']} : {eg['away']} {B}",
                           f"模型傾向:{fav} 勝 {pc(favp)}"],
             "spreads": [f"合理讓分:{fav_side} {line}"],
             "totals": [f"預計總分 {eg['total']}"],
             "soccer_extra_time": [f"進入加時機率:{pc(p_ot)}"],
             "winning_margin": [f"最可能:{bteam} 淨勝 {brange} 分({pc(wm[band])})"]}
    if h1: r["first_half"] = [_half_line(A, B, h1, lang)]
    if h2: r["second_half"] = [_half_line(A, B, h2, lang)]
    return r


def _platform_markets(mk, cfg):
    """平台篮球玩法 key:moneyline / spreads / totals / soccer_extra_time(加时)。"""
    import math
    f = mk["full_game"]
    mm = f["expected_points"]["home"] - f["expected_points"]["away"]
    sd = cfg.get("sd_margin", 14.7)
    base_ot = cfg.get("ot_base", 0.06)   # 势均力敌时进加时的基础概率
    p_ot = base_ot * math.exp(-(mm * mm) / (2 * sd * sd))
    return {
        "moneyline": f["moneyline"],
        "spreads": f["spreads"],
        "totals": f["totals"],
        "soccer_extra_time": {"yes": p_ot, "no": 1 - p_ot},
    }


def predict(code, A, B, lang="zh", odds_ml=None):
    cfg, snap = _load(code)
    teams = snap["teams"]
    a, b = _find(teams, A), _find(teams, B)
    if not a or not b:
        return {"error": f"未找到:{A if not a else B}", "missing": A if not a else B}
    ph, pa = PointsRatings.rates_from_snapshot(snap, a, b)
    mk = markets(ph, pa, sd_margin=cfg.get("sd_margin", 14.7),
                 sd_total=cfg.get("sd_total", 20.0), fh_share=cfg.get("fh_share", 0.505),
                 q_shares=cfg.get("q_shares"))
    pm = _platform_markets(mk, cfg)
    out = {"code": str(code), "competition": cfg.get("name"), "category_id": cfg.get("category_id"),
           "platform_id": cfg.get("platform_id"), "A": a, "B": b, "lang": lang,
           "matched_exact": (A == a and B == b),
           "markets": mk, "platform_markets": pm,
           "reasons": _reasons(a, b, mk, pm, lang)}
    if odds_ml:
        m = mk["full_game"]["moneyline"]; model = [m["home"], m["away"]]
        market = devig_two(*odds_ml)
        out["market"] = {"moneyline": {"home": market[0], "away": market[1]}} if market else None
        out["divergence"] = divergence(model, market, ["home", "away"]) if market else None
    return out


def list_teams(code, kw):
    _, snap = _load(code)
    kw = kw.lower()
    return sorted([(t, v) for t, v in snap["teams"].items() if kw in t.lower()], key=lambda x: -x[1]["gp"])
