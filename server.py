#!/usr/bin/env python3
"""ForeGate 篮球预测 · HTTP API(零依赖,Python 标准库)。
只读各联赛已提交的评级快照,秒级响应。本地:python3 server.py(PORT 默认 8000)。

路由:
  GET /health
  GET /competitions                          所有联赛 + categoryId
  GET /teams?categoryId=745&q=Lakers          查队伍(快照内)
  GET /predict?categoryId=745&a=Lakers&b=Celtics[&lang=zh&oh=&oa=]
      联赛解析三选一:categoryId(内部分类 id) / code(联赛内部编号) / name
      玩法:全场 + 半场的 胜负 / 让分 / 大小分
      传 oh/oa(胜负两向欧赔)则附盘口去水隐含概率 + 分歧(混合展示)
"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import predict as P
from core import storage

ROOT = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(ROOT, "games")
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*", "Access-Control-Max-Age": "86400"}


def competitions():
    out = {}
    snapshots = storage.games(GAMES)
    for code in sorted(os.listdir(GAMES)):
        cf = os.path.join(GAMES, code, "config.json")
        if os.path.isfile(cf):
            c = json.load(open(cf, encoding="utf-8"))
            ref = c.get("pool_ref")
            snap_dir = snapshots / str(ref or code)
            has = os.path.isfile(os.path.join(snap_dir, "ratings.json"))
            out[code] = {"name": c.get("name"), "category_id": c.get("category_id"),
                         "category_ids": c.get("category_ids", []),
                         "ml_acc": c.get("backtest_ml_acc"), "ready": has}
    return out


def resolve(q):
    """categoryId / code / name 三选一 -> 联赛目录 code。"""
    comps = competitions()
    cid = q.get("categoryId") or q.get("category_id")
    if cid:
        for code, c in comps.items():
            if str(cid) in [str(x) for x in c.get("category_ids", [])] or str(cid) == str(c.get("category_id")):
                return code, None
        return None, {"error": f"未知 categoryId: {cid}", "categoryId": cid}
    code = q.get("code") or q.get("league")
    if code:
        return (code, None) if code in comps else (None, {"error": f"未知 code: {code}", "code": code})
    nm = q.get("name")
    if nm:
        for code, c in comps.items():
            if nm.strip().lower() in (c.get("name") or "").lower():
                return code, None
        return None, {"error": f"未识别联赛 name: {nm}", "name": nm}
    return None, {"error": "需要 categoryId / code / name 参数"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body):
        p = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for k, v in CORS.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(p)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS.items(): self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path.rstrip("/") or "/"
        try:
            if path in ("/", "/health"):
                cs = competitions()
                return self._send(200, {"status": "ok", "service": "foregate-basketball-prediction",
                                        "competitions": len(cs), "ready": sum(1 for c in cs.values() if c["ready"]),
                                        "data": storage.provenance()})
            if path == "/competitions":
                return self._send(200, competitions())
            if path in ("/teams", "/predict"):
                code, err = resolve(q)
                if err:
                    return self._send(404 if ("categoryId" in err or "name" in err or "code" in err) else 400, err)
                if path == "/teams":
                    hits = P.list_teams(code, q.get("q", ""))
                    return self._send(200, {"code": code, "count": len(hits),
                                            "teams": [{"name": t, **v} for t, v in hits[:60]]})
                a, b = q.get("a"), q.get("b")
                if not (a and b):
                    return self._send(400, {"error": "需要 a / b 参数"})
                lang = q.get("lang") if q.get("lang") in ("en", "vi") else "zh"
                odds = None
                if q.get("oh") and q.get("oa"):
                    try: odds = [float(q["oh"]), float(q["oa"])]
                    except ValueError: odds = None
                r = P.predict(code, a, b, lang=lang, odds_ml=odds)
                return self._send(200 if "error" not in r else 404, r)
            return self._send(404, {"error": "not found",
                                    "endpoints": ["/health", "/competitions", "/teams", "/predict"]})
        except Exception as e:
            return self._send(500, {"error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"ForeGate basketball API on :{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
