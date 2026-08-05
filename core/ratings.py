#!/usr/bin/env python3
"""篮球得分评级(在线,进攻/防守效率 + 主场优势)。
每队:offense(得分强度)/ defense(限分强度)。期望得分:
  pts_home = mu + hfa + off_home - def_away
  pts_away = mu       + off_away - def_home
在线 SGD 更新(近期权重更高),快照供预测端零训练使用。"""
from collections import defaultdict


class PointsRatings:
    def __init__(self, mu=113.0, hfa=2.3, lr=0.06, season_reset=1.0):
        self.off = defaultdict(float)
        self.dfn = defaultdict(float)
        self.mu = mu
        self.hfa = hfa
        self.lr = lr
        self.season_reset = season_reset
        self._season = None
        self.gp = defaultdict(int); self.w = defaultdict(int); self.l = defaultdict(int)

    def rates(self, h, a):
        return (self.mu + self.hfa + self.off[h] - self.dfn[a],
                self.mu + self.off[a] - self.dfn[h])

    def _newseason(self, s):
        if s is not None and self._season is not None and s != self._season and self.season_reset < 1.0:
            for t in list(self.off): self.off[t] *= self.season_reset
            for t in list(self.dfn): self.dfn[t] *= self.season_reset
        self._season = s

    def update(self, h, a, hp, ap, season=None):
        if season is not None:
            self._newseason(season)
        ph, pa = self.rates(h, a)
        eh, ea, lr = ph - hp, pa - ap, self.lr
        self.off[h] -= lr * eh; self.dfn[a] += lr * eh
        self.off[a] -= lr * ea; self.dfn[h] += lr * ea
        self.mu -= 0.002 * (eh + ea)
        self.hfa -= 0.003 * eh
        self.gp[h] += 1; self.gp[a] += 1
        if hp > ap: self.w[h] += 1; self.l[a] += 1
        else: self.w[a] += 1; self.l[h] += 1

    def fit(self, matches):
        for m in matches:
            self.update(m["home"], m["away"], m["hp"], m["ap"], m.get("season"))
        return self

    def snapshot(self):
        teams = {t: {"off": round(self.off[t], 4), "dfn": round(self.dfn[t], 4),
                     "w": self.w[t], "l": self.l[t], "gp": self.gp[t]} for t in self.gp}
        return {"mu": round(self.mu, 4), "hfa": round(self.hfa, 4), "teams": teams}

    @classmethod
    def from_snapshot(cls, snap, lr=0.06):
        r = cls(mu=snap.get("mu", 113.0), hfa=snap.get("hfa", 2.3), lr=lr)
        for t, v in snap.get("teams", {}).items():
            r.off[t] = v.get("off", 0.0); r.dfn[t] = v.get("dfn", 0.0)
            r.w[t] = v.get("w", 0); r.l[t] = v.get("l", 0); r.gp[t] = v.get("gp", 0)
        return r

    @staticmethod
    def rates_from_snapshot(snap, h, a):
        mu, hfa, T = snap["mu"], snap["hfa"], snap["teams"]
        oh = T.get(h, {}).get("off", 0.0); dh = T.get(h, {}).get("dfn", 0.0)
        oa = T.get(a, {}).get("off", 0.0); da = T.get(a, {}).get("dfn", 0.0)
        return mu + hfa + oh - da, mu + oa - dh
