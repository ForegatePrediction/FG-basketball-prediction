#!/usr/bin/env python3
"""赔率去水 + 分歧(混合展示:模型 vs 盘口)。篮球 moneyline 两向。"""


def devig_two(o_home, o_away):
    if not o_home or not o_away or o_home <= 1 or o_away <= 1:
        return None
    ih, ia = 1.0 / o_home, 1.0 / o_away
    s = ih + ia
    return [ih / s, ia / s]


def divergence(model, market, labels):
    if not market:
        return None
    diffs = [(labels[i], model[i] - market[i]) for i in range(len(model))]
    lab, d = max(diffs, key=lambda x: abs(x[1]))
    return {"outcome": lab, "delta_pt": round(d * 100, 1)}
