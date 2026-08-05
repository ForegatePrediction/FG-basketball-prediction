#!/usr/bin/env python3
"""每日增量刷新:只拉「上次快照日期之后」的已结束比赛,增量更新评级快照。
- api-basketball 联赛:按日期拉 /games?date=YYYY-MM-DD(一天一次调用,覆盖全部联赛),
  只保留我们关心的 league_id 与已结束比分。
- WNBA:ESPN scoreboard 免费接口按日期拉。
零训练秒级:from_snapshot 载入现有评级,只 update 新增比赛,写回 ratings.json + last_date。
用量极低:即便不付费,每天仅需拉当天新增,约 1 次 api-basketball + 若干次 ESPN。
注:NBA / WNBA / NCAA 走 ESPN 免费源(不限赛季,当前赛季可用);其余联赛走 api-basketball,
    免费层仅放行 2022–2024 赛季,当前赛季需付费计划方能日更。
环境变量:APIBASKETBALL_KEY(api-basketball key)。
"""
import json, os, sys, time, datetime as dt, urllib.request, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(ROOT, "games")
sys.path.insert(0, ROOT)
from core.ratings import PointsRatings

KEY = os.environ.get("APIBASKETBALL_KEY", "")
FIN = {"FT", "AOT", "OT", "AET"}
MAX_LOOKBACK = 14   # 最多回看天数,防止长时间未刷新时漏单


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception:
            time.sleep(1)
    # 回退:部分环境对 Python 客户端做了拦截,改用 curl
    try:
        hdr = []
        for k, v in (headers or {}).items():
            hdr += ["-H", f"{k}: {v}"]
        out = subprocess.run(["curl", "-s", "--max-time", "25", *hdr, url],
                             capture_output=True, text=True, timeout=30).stdout
        return json.loads(out) if out.strip() else {}
    except Exception:
        return {}


def _dates_since(last_date):
    today = dt.date.today()
    if last_date:
        start = dt.date.fromisoformat(last_date) + dt.timedelta(days=1)
    else:
        start = today - dt.timedelta(days=MAX_LOOKBACK)
    start = max(start, today - dt.timedelta(days=MAX_LOOKBACK))
    out = []
    d = start
    while d <= today:
        out.append(d.isoformat()); d += dt.timedelta(days=1)
    return out


def _configs():
    for code in sorted(os.listdir(GAMES)):
        cf = os.path.join(GAMES, code, "config.json")
        if os.path.isfile(cf):
            yield code, json.load(open(cf, encoding="utf-8"))


def _apibasketball_by_date(dates):
    """一天一次调用,返回 {af_league_id: [match,...]}。"""
    by_league = {}
    for day in dates:
        d = _get(f"https://v1.basketball.api-sports.io/games?date={day}",
                 {"x-apisports-key": KEY})
        for g in d.get("response", []):
            if g.get("status", {}).get("short") not in FIN:
                continue
            hp = g["scores"]["home"]["total"]; ap = g["scores"]["away"]["total"]
            if hp is None or ap is None:
                continue
            lid = g["league"]["id"]
            by_league.setdefault(lid, []).append(
                {"date": g["date"][:10], "home": g["teams"]["home"]["name"],
                 "away": g["teams"]["away"]["name"], "hp": hp, "ap": ap,
                 "season": str(g["league"]["season"])})
        time.sleep(6)  # 免费层 10 次/分
    return by_league


def _espn(path, dates, query=""):
    out = []
    for day in dates:
        d = _get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{path}/scoreboard?dates={day.replace('-','')}{query}")
        for e in d.get("events", []):
            if "FINAL" not in e["status"]["type"]["name"]:
                continue
            comp = e["competitions"][0]["competitors"]
            h = next(x for x in comp if x["homeAway"] == "home")
            a = next(x for x in comp if x["homeAway"] == "away")
            try:
                hp = int(h["score"]); ap = int(a["score"])
            except Exception:
                continue
            out.append({"date": e["date"][:10], "home": h["team"]["displayName"],
                        "away": a["team"]["displayName"], "hp": hp, "ap": ap,
                        "season": e["date"][:4]})
    return out


def _apply(code, cfg, new_ms):
    if not new_ms:
        print(f"[{code}] {cfg['name']}: 无新增"); return
    snap_p = os.path.join(GAMES, code, "ratings.json")
    snap = json.load(open(snap_p, encoding="utf-8"))
    last = snap.get("last_date")
    fresh = [m for m in new_ms if not last or m["date"] > last]
    fresh.sort(key=lambda m: (m["date"], m["home"]))
    if not fresh:
        print(f"[{code}] {cfg['name']}: 无晚于 {last} 的新增"); return
    R = PointsRatings.from_snapshot(snap, lr=cfg.get("lr", 0.06))
    for m in fresh:
        R.update(m["home"], m["away"], m["hp"], m["ap"], m.get("season"))
    out = R.snapshot()
    out["updated_from"] = snap.get("updated_from", 0) + len(fresh)
    out["last_date"] = max(m["date"] for m in fresh)
    # 追加到 matches.json 以便未来全量重建
    mp = os.path.join(GAMES, code, "data", "matches.json")
    allm = json.load(open(mp, encoding="utf-8")) if os.path.isfile(mp) else []
    allm += fresh
    json.dump(allm, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(out, open(snap_p, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{code}] {cfg['name']}: +{len(fresh)} 场 -> last_date {out['last_date']}")


def main():
    cfgs = list(_configs())
    # 计算全局回看窗口(取所有联赛 last_date 的最早值)
    earliest = None
    for code, cfg in cfgs:
        sp = os.path.join(GAMES, code, "ratings.json")
        if os.path.isfile(sp):
            ld = json.load(open(sp, encoding="utf-8")).get("last_date")
            if ld and (earliest is None or ld < earliest):
                earliest = ld
    dates = _dates_since(earliest)
    if not dates:
        print("全部快照已是最新,无需回看"); return
    print(f"回看日期: {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")

    ab = _apibasketball_by_date(dates) if KEY else {}
    if not KEY:
        print("警告: 未设置 APIBASKETBALL_KEY,跳过 api-basketball 联赛")

    for code, cfg in cfgs:
        if cfg.get("source") == "espn":
            ms = _espn(cfg["espn_path"], dates, cfg.get("espn_query", ""))
        else:
            ms = ab.get(cfg.get("af_id"), [])
        _apply(code, cfg, ms)


if __name__ == "__main__":
    main()
