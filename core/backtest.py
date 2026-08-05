#!/usr/bin/env python3
"""走查式回测:胜负命中 + 净胜分/总分残差 σ。"""
import statistics
from .ratings import PointsRatings


def walk_forward(matches, burn_frac=0.5, mu=113.0, hfa=2.3, lr=0.06, season_reset=1.0):
    matches = sorted(matches, key=lambda m: (m["date"], m["home"]))
    R = PointsRatings(mu=mu, hfa=hfa, lr=lr, season_reset=season_reset)
    burn = int(len(matches) * burn_frac)
    n = hit = 0; mres = []; tres = []
    for i, m in enumerate(matches):
        h, a, hp, ap, s = m["home"], m["away"], m["hp"], m["ap"], m.get("season")
        ph, pa = R.rates(h, a)
        if i >= burn:
            pm, am = ph - pa, hp - ap
            hit += ((pm > 0) == (am > 0)); n += 1
            mres.append(am - pm); tres.append((hp + ap) - (ph + pa))
        R.update(h, a, hp, ap, s)
    if not n:
        return {"N": 0}
    return {"N": n, "acc_ml": hit / n,
            "sd_margin": statistics.pstdev(mres), "sd_total": statistics.pstdev(tres)}
