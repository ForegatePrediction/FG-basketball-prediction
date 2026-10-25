#!/usr/bin/env python3
"""Refresh basketball snapshots from free ESPN/EuroLeague sources.
Historical gaps resume from a committed per-league cursor, at most 31 days per run.
Use --max-days 0 for full backfill. Only free sources are permitted.
"""
import json, os, sys, time, datetime as dt, urllib.request, subprocess, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(ROOT, "games")
sys.path.insert(0, ROOT)
from core.ratings import PointsRatings



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


CBA_TEAMS = {
    "29136": "Beijing Royal Fighters", "29115": "Beijing", "29134": "Fujian",
    "29124": "Guangdong", "29139": "Guangzhou", "29118": "Jiangsu Dragons",
    "29129": "Liaoning", "29133": "Nanjing Tongxi", "100074683": "Ningbo Rockets",
    "29135": "Qingdao", "29130": "Shandong", "29125": "Shanghai",
    "29132": "Shanxi Zhongyu", "29131": "Shenzhen", "29127": "Sichuan",
    "29138": "Tianjin", "29117": "Xinjiang", "29137": "Jilin",
    "29140": "Zhejiang Chouzhou", "29128": "Zhejiang Guangsha",
}


def _cba_list(path):
    url = "https://data-server.cbaleague.com/api" + path
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "isEncrypt": "no"})
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.load(response)
            if not isinstance(result, list):
                raise ValueError("CBA official response is not a list")
            return result
        except Exception:
            if attempt == 2:
                raise RuntimeError("CBA official request failed; refuse empty-success") from None
            time.sleep(1)


def _cba(dates):
    """Official CBA calendar and final scores. Regular season/playoffs only."""
    wanted = set(dates)
    active = set()
    for month in sorted({date[:7] for date in dates}):
        year, number = month.split("-")
        calendar = _cba_list(f"/schedules/month?year={year}&month={number}")
        if not calendar:
            raise RuntimeError("CBA month calendar is empty")
        for row in calendar:
            day = row["scheduleTime"][:10]
            if day in wanted and int(row["scheduleNum"]) > 0:
                active.add(day)
    matches = []
    for day in sorted(active):
        rows = _cba_list(f"/schedules/day?day={day}&auto=0")
        if not rows:
            raise RuntimeError(f"CBA calendar has games but daily list is empty: {day}")
        for row in rows:
            if int(row["status"]) != 4 or int(row["matchTypeId"]) not in (1, 2):
                continue
            home_id, away_id = str(row["homeTeamId"]), str(row["visitingTeamId"])
            if home_id not in CBA_TEAMS or away_id not in CBA_TEAMS:
                raise RuntimeError("Unmapped CBA team ID; avoid splitting historical ratings")
            date = row["scheduleTime"][:10]
            if date not in wanted:
                raise RuntimeError("CBA daily endpoint returned another day")
            matches.append({"date": date, "home": CBA_TEAMS[home_id], "away": CBA_TEAMS[away_id],
                            "hp": int(row["homeTeamScore"]), "ap": int(row["visitingTeamScore"]),
                            "season": str(row["season"]), "source_id": str(row["scheduleId"])})
    return matches


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
        if src not in ("espn", "euroleague", "cba"):
            print(f"[skip] {code}: no free source connected; historical snapshot only")
            continue
        try:
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
            elif src == "cba":
                ms = _cba(dates)
            _apply(code, cfg, ms)
            latest = json.load(open(os.path.join(GAMES, code, "ratings.json"), encoding="utf-8")).get("last_date")
            state[code] = {"checked_through": dates[-1], "source": src, "latest_match": latest,
                           "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "source_matches_in_batch": len(ms)}
            _write_json(state_path, state)
        except Exception as exc:
            failures.append(code)
            print(f"[fail] {code}: {type(exc).__name__}: {exc}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\nFree sources only. Unsupported leagues remain historical.\n\n| League | Checked through |\n|---|---|\n")
            for code, value in state.items():
                f.write(f"| {code} | {value['checked_through']} |\n")
            f.write(f"\nFailed leagues: {failures}\n")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
