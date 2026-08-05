#!/usr/bin/env python3
"""snapshot / predict / backtest / list。code = api-basketball league_id(games 目录名)。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.ratings import PointsRatings
from core import backtest as bt
from core.predict import predict, list_teams

ROOT = os.path.dirname(os.path.abspath(__file__))


def _matches(code):
    f = os.path.join(ROOT, "games", str(code), "data", "matches.json")
    return sorted(json.load(open(f, encoding="utf-8")), key=lambda m: (m["date"], m["home"]))


def _cfg(code):
    return json.load(open(os.path.join(ROOT, "games", str(code), "config.json"), encoding="utf-8"))


def cmd_snapshot(code):
    cfg = _cfg(code); ms = _matches(code)
    R = PointsRatings(mu=cfg.get("mu", 113.0), hfa=cfg.get("hfa", 2.3), lr=cfg.get("lr", 0.06)).fit(ms)
    snap = R.snapshot(); snap["updated_from"] = len(ms)
    if ms: snap["last_date"] = max(m["date"] for m in ms)
    json.dump(snap, open(os.path.join(ROOT, "games", str(code), "ratings.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{code}] {cfg.get('name')}: 拟合 {len(ms)} 场,{len(snap['teams'])} 队")


def cmd_backtest(code):
    cfg = _cfg(code); ms = _matches(code)
    r = bt.walk_forward(ms, mu=cfg.get("mu", 113.0), hfa=cfg.get("hfa", 2.3))
    if r.get("N"):
        print(f"[{code}] {cfg.get('name')} 样本外: 胜负={r['acc_ml']*100:.1f}%  "
              f"σ净胜={r['sd_margin']:.1f}  σ总分={r['sd_total']:.1f}  N={r['N']}")
    else:
        print(f"[{code}] 数据不足")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit()
    c = a[0]
    if c == "snapshot": cmd_snapshot(a[1])
    elif c == "backtest": cmd_backtest(a[1])
    elif c == "predict": print(json.dumps(predict(a[1], a[2], a[3], a[4] if len(a) > 4 else "zh"), ensure_ascii=False, indent=2))
    elif c == "list": [print(f"  {t} (W{v['w']} L{v['l']}, {v['gp']}场)") for t, v in list_teams(a[1], a[2] if len(a) > 2 else "")[:20]]
    else: print("未知命令", c)
