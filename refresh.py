#!/usr/bin/env python3
"""Refresh basketball snapshots from free ESPN/EuroLeague sources.
Historical gaps resume from a committed per-league cursor, at most 31 days per run.
Use --max-days 0 for full backfill. Paid API-Sports is disabled unless explicitly
requested with --enable-paid-api after renewing the subscription.
"""
import json, os, sys, time, datetime as dt, urllib.request, subprocess, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(ROOT, "games")
sys.path.insert(0, ROOT)
from core.ratings import PointsRatings

KEY = os.environ.get("APIBASKETBALL_KEY", "")
FIN = {"FT", "AOT", "OT", "AET"}
MAX_LOOKBACK = 14   # 最多回看天数,防止长时间未刷新时漏单


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.load(r)
            if not isinstance(data, dict) or data.get("errors"):
                raise ValueError("上游响应错误或订阅权限不足")
            return data
        except Exception:
            if attempt == 2:
                raise RuntimeError("数据请求失败，拒绝将失败当作无比赛") from None
            time.sleep(1)


def _get_text(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/xml"}), timeout=25) as r:
        return r.read().decode("utf-8")


def _dates_since(last_date, checked_through=None, max_days=31, end_date=None):
    # Completed UTC days only. Persist an independent cursor so offseasons advance too.
    end = end_date or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))
    cursor = checked_through or last_date
    start = dt.date.fromisoformat(cursor) + dt.timedelta(days=1) if cursor else end - dt.timedelta(days=13)
    stop = min(end, start + dt.timedelta(days=max_days - 1)) if max_days else end
    return [(start + dt.timedelta(days=n)).isoformat() for n in range(max(0, (stop-start).days+1))]


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


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
    if not dates:
        return []
    out = []; seen = set(); wanted = set(dates)
    # ESPN indexes local league days; UTC matches may be on the preceding scoreboard.
    query_days = [(dt.date.fromisoformat(dates[0])-dt.timedelta(days=1)).isoformat()] + dates
    for day in query_days:
        d = _get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{path}/scoreboard?dates={day.replace('-','')}{query}")
        if "events" not in d:
            raise RuntimeError("ESPN 响应缺少 events")
        for e in d["events"]:
            if e["id"] in seen or e["date"][:10] not in wanted:
                continue
            seen.add(e["id"])
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


def _euroleague(dates):
    """EuroLeague 官方 XML(免费,不限赛季)。拉当前与上一赛季,回看窗口内的已完成比赛。"""
    import xml.etree.ElementTree as ET, datetime as _dt
    seasons = {int(day[:4]) - offset for day in dates for offset in (0, 1)}
    dset = set(dates); out = []
    for s in seasons:
        raw = _get_text(f"https://api-live.euroleague.net/v1/results?seasonCode=E{s}")
        root = ET.fromstring(raw)
        for g in root.findall("game"):
            if (g.findtext("played") or "").lower() != "true":
                continue
            try:
                hp = int(g.findtext("homescore")); ap = int(g.findtext("awayscore"))
                iso = _dt.datetime.strptime(g.findtext("date"), "%b %d, %Y").date().isoformat()
            except Exception:
                continue
            if iso in dset:
                out.append({"date": iso, "home": g.findtext("hometeam"),
                            "away": g.findtext("awayteam"), "hp": hp, "ap": ap, "season": str(s)})
    return out


def _match_key(match):
    return "|".join((match["date"], match["home"], match["away"]))


def _apply(code, cfg, new_ms):
    if not new_ms:
        print(f"[{code}] {cfg['name']}: 无新增"); return
    snap_p = os.path.join(GAMES, code, "ratings.json")
    snap = json.load(open(snap_p, encoding="utf-8"))
    last = snap.get("last_date")
    seen = snap.get("applied_on_last_date")
    fresh = [m for m in new_ms if not last or m["date"] > last or (m["date"] == last and seen is not None and _match_key(m) not in seen)]
    fresh.sort(key=lambda m: (m["date"], m["home"]))
    if not fresh:
        print(f"[{code}] {cfg['name']}: 无晚于 {last} 的新增"); return
    R = PointsRatings.from_snapshot(snap, lr=cfg.get("lr", 0.06))
    for m in fresh:
        R.update(m["home"], m["away"], m["hp"], m["ap"], m.get("season"))
    out = R.snapshot()
    out["updated_from"] = snap.get("updated_from", 0) + len(fresh)
    out["last_date"] = max(m["date"] for m in fresh)
    out["applied_on_last_date"] = sorted(set(([k for k in (seen or [])] if out["last_date"] == last else []) + [_match_key(m) for m in fresh if m["date"] == out["last_date"]]))
    # 追加到 matches.json 以便未来全量重建
    mp = os.path.join(GAMES, code, "data", "matches.json")
    allm = json.load(open(mp, encoding="utf-8")) if os.path.isfile(mp) else []
    allm += fresh
    _write_json(mp, allm)
    _write_json(snap_p, out)
    print(f"[{code}] {cfg['name']}: +{len(fresh)} 场 -> last_date {out['last_date']}")


def main():
    parser = argparse.ArgumentParser(description="Refresh free basketball sources; resume historical gaps in order")
    parser.add_argument("--max-days", type=int, default=31, help="Per-league batch size; 0 means complete backfill")
    parser.add_argument("--enable-paid-api", action="store_true", help="Explicit opt-in after renewing API-Sports")
    parser.add_argument("--league", action="append", help="League code; repeat to select multiple")
    args = parser.parse_args()
    if args.max_days < 0:
        parser.error("max-days must be >= 0")
    cfgs = list(_configs())
    known = {code for code, _ in cfgs}
    if set(args.league or []) - known:
        parser.error("Unknown league")
    state_path = os.path.join(ROOT, "refresh-state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.isfile(state_path) else {}
    failures = []
    for code, cfg in cfgs:
        if args.league and code not in args.league:
            continue
        src = cfg.get("source")
        if src not in ("espn", "euroleague") and not args.enable_paid_api:
            print(f"[skip] {code}: paid API disabled (subscription expired)")
            continue
        try:
            if src not in ("espn", "euroleague") and not KEY:
                raise RuntimeError("Missing APIBASKETBALL_KEY")
            snap = json.load(open(os.path.join(GAMES, code, "ratings.json"), encoding="utf-8"))
            dates = _dates_since(snap.get("last_date"), state.get(code, {}).get("checked_through"), args.max_days)
            if not dates:
                print(f"[ok] {code}: checked through yesterday")
                continue
            print(f"[{code}] {dates[0]} ~ {dates[-1]} ({len(dates)} days)")
            if src == "espn":
                ms = _espn(cfg["espn_path"], dates, cfg.get("espn_query", ""))
            elif src == "euroleague":
                ms = _euroleague(dates)
            else:
                ms = _apibasketball_by_date(dates).get(cfg.get("af_id"), [])
            _apply(code, cfg, ms)
            state[code] = {"checked_through": dates[-1], "source": src}
            _write_json(state_path, state)
        except Exception as exc:
            failures.append(code)
            print(f"[fail] {code}: {type(exc).__name__}: {exc}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\nPaid API: disabled unless explicitly requested.\n\n| League | Checked through |\n|---|---|\n")
            for code, value in state.items():
                f.write(f"| {code} | {value['checked_through']} |\n")
            f.write(f"\nFailed leagues: {failures}\n")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
