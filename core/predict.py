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


def _reasons(A, B, mk, lang):
    f = mk["full_game"]; ml = f["moneyline"]; eg = f["expected_points"]
    pc = lambda x: f"{round(x*100)}%"
    fav, favp = (A, ml["home"]) if ml["home"] >= ml["away"] else (B, ml["away"])
    if lang == "en":
        return {"moneyline": [f"Projected score {A} {eg['home']} : {eg['away']} {B}",
                              f"Model lean: {fav} {pc(favp)} to win"],
                "totals": [f"Projected total {eg['total']}"]}
    if lang == "vi":
        return {"moneyline": [f"Dự báo tỉ số {A} {eg['home']} : {eg['away']} {B}",
                              f"Mô hình nghiêng: {fav} thắng {pc(favp)}"],
                "totals": [f"Tổng điểm dự báo {eg['total']}"]}
    return {"moneyline": [f"预计比分 {A} {eg['home']} : {eg['away']} {B}",
                          f"模型倾向:{fav} 胜 {pc(favp)}"],
            "totals": [f"预计总分 {eg['total']}"]}


def predict(code, A, B, lang="zh", odds_ml=None):
    cfg, snap = _load(code)
    teams = snap["teams"]
    a, b = _find(teams, A), _find(teams, B)
    if not a or not b:
        return {"error": f"未找到:{A if not a else B}", "missing": A if not a else B}
    ph, pa = PointsRatings.rates_from_snapshot(snap, a, b)
    mk = markets(ph, pa, sd_margin=cfg.get("sd_margin", 14.9),
                 sd_total=cfg.get("sd_total", 18.9), fh_share=cfg.get("fh_share", 0.504))
    out = {"code": str(code), "competition": cfg.get("name"), "category_id": cfg.get("category_id"),
           "A": a, "B": b, "lang": lang, "matched_exact": (A == a and B == b),
           "markets": mk, "reasons": _reasons(a, b, mk, lang)}
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
