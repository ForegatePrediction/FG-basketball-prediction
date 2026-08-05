# ForeGate Basketball Prediction · 篮球预测服务

零依赖(Python 标准库)的篮球赛前概率服务。基于球队进攻/防守效率评级 + 主场优势,产出每场比赛 **全场 + 上半场** 的 **胜负 / 让分 / 大小分** 玩法概率。评级以在线方式滚动更新并落成快照,预测端零训练、秒级响应。

A zero-dependency (Python standard library only) pre-game basketball probability service. From per-team offense/defense efficiency ratings plus home-court advantage, it produces **full-game and first-half** probabilities for **moneyline / spreads / totals**. Ratings update online and are snapshotted, so the prediction endpoint needs no training and responds in milliseconds.

---

## 覆盖联赛 · Leagues Covered (17)

按历史样本量排序。`code` = 内部联赛目录名;`categoryId` = 平台分类 id;`胜负命中率` = 走查式样本外回测(burn-in 50%)。

Sorted by historical sample size. `code` = internal league directory; `categoryId` = platform category id; `Moneyline Acc` = walk-forward out-of-sample backtest (50% burn-in).

`lr` = 该联赛按回测选出的最优在线学习率(近期权重强度,阵容更替越频繁取值越高)。

`lr` = the per-league online learning rate chosen by backtest (recency strength; higher for leagues with faster roster turnover).

| 联赛 League | code | categoryId | 样本 Games | 胜负命中率 ML Acc | lr | σ 净胜分 | σ 总分 | 源 Source |
|---|---|---|---|---|---|---|---|---|
| NCAA (NCAA Men's) | 116 | 100396 | 23,573 | 73.5% | 0.10 | 13.7 | 17.3 | ESPN |
| NBA | 12 | 745 | 5,557 | 66.6% | 0.06 | 14.7 | 20.0 | ESPN |
| B.League (Japan) | 56 | 104349 | 2,210 | 69.0% | 0.03 | 12.9 | 16.7 | api-basketball |
| CBA (China) | 31 | 103097 | 1,525 | 76.5% | 0.03 | 13.2 | 19.4 | api-basketball |
| WNBA | wnba | 100254 | 1,349 | 65.8% | 0.045 | 13.8 | 19.1 | ESPN |
| EuroLeague | 120 | 102669 | 989 | 65.1% | 0.06 | 12.0 | 17.1 | api-basketball |
| BBL (Germany) | 40 | 104345 | 969 | 66.8% | 0.06 | 12.7 | 18.3 | api-basketball |
| LNB Pro A (France) | 2 | 103099 | 920 | 70.7% | 0.08 | 13.0 | 18.3 | api-basketball |
| KBL (Korea) | 91 | 103100 | 875 | 64.4% | 0.08 | 13.5 | 16.1 | api-basketball |
| VTB United League | 82 | 104344 | 837 | 74.9% | 0.06 | 13.0 | 16.9 | api-basketball |
| Lega A (Italy) | 52 | 103095 | 802 | 67.3% | 0.06 | 12.3 | 17.2 | api-basketball |
| ABA League (Adriatic) | 198 | 104346 | 664 | 79.2% | 0.10 | 12.1 | 17.1 | api-basketball |
| LKL (Lithuania) | 60 | 105267 | 637 | 72.7% | 0.06 | 12.9 | 16.8 | api-basketball |
| Basketball Champions League | 202 | 103093 | 597 | 55.5% | 0.10 | 12.4 | 20.4 | api-basketball |
| Basket League (Greece) | 45 | 104348 | 539 | 73.3% | 0.08 | 12.4 | 18.2 | api-basketball |
| NBL (Australia) | 1 | 103096 | 467 | 62.4% | 0.10 | 15.1 | 18.0 | api-basketball |
| Liga Endesa (Spain ACB) | 117 | 103094 | 325 | 69.3% | 0.08 | 11.4 | 16.6 | api-basketball |

> 历史深度与时效:NBA / WNBA / NCAA 由 ESPN 免费源覆盖到**最新完整赛季 2025/26**(不限赛季);其余联赛覆盖 2022/23–2024/25(免费数据源上限)。评级为在线滚动,近期比赛权重远高于早期——重磅交易/换血会在球队打几场后自动反映;每个联赛的近期权重(`lr`)已按回测单独校准。每日增量任务持续把新结果并入评级。
>
> History & recency: NBA / WNBA / NCAA are covered by the free ESPN source through the **latest full 2025/26 season** (no season cap); other leagues cover 2022/23–2024/25 (free-source limit). Ratings are online and weight recent games far more than old ones — blockbuster trades show up within a few games — and each league's recency weight (`lr`) is individually calibrated by backtest. A daily incremental job keeps merging new results.

---

## 支持玩法与字段 · Markets & Fields

每次预测同时返回 `full_game`(全场)与 `first_half`(上半场)两块,结构一致:

Every prediction returns both `full_game` and `first_half` with identical structure:

| 玩法 Market | 字段 Field | 说明 Description |
|---|---|---|
| 期望得分 Expected points | `expected_points.home` / `.away` / `.total` | 双方期望得分与期望总分 · projected points and total |
| 胜负 Moneyline | `moneyline.home` / `.away` | 主/客获胜概率 · win probability for home/away |
| 让分 Spreads | `spreads["<line>"].line` / `.home` / `.away` | 每条让分线(主队让分)双方赢盘概率 · cover probability per spread line |
| 大小分 Totals | `totals["<line>"].line` / `.over` / `.under` | 每条总分线大/小概率 · over/under probability per total line |

模型逻辑 · How each is derived:

净胜分服从正态 `Normal(home−away, σ_margin)`,总分服从正态 `Normal(home+away, σ_total)`,`σ` 按联赛回测校准。胜负 = `Φ(margin_mean/σ_margin)`;让分 = `P(净胜 > −line)`;大小分 = `1 − Φ((line − total_mean)/σ_total)`。上半场按上半场得分占比 `fh_share≈0.504` 拆分期望得分,标准差按 `σ/√2` 缩放。让分线围绕模型净胜分自动生成整/半分梯度,大小分线围绕期望总分生成。

Margin follows `Normal(home−away, σ_margin)` and total follows `Normal(home+away, σ_total)`, with `σ` calibrated per league from backtests. Moneyline = `Φ(margin_mean/σ_margin)`; spread cover = `P(margin > −line)`; total over = `1 − Φ((line − total_mean)/σ_total)`. The first half splits expected points by the first-half scoring share `fh_share≈0.504` and scales the deviation by `σ/√2`. Spread lines are auto-generated around the model margin, total lines around the expected total.

可选盘口混合 · Optional odds blend: 传入两向胜负赔率(`oh`/`oa`),接口额外返回去水后的市场隐含概率 `market.moneyline` 与模型-市场分歧 `divergence`,**模型与市场分开展示,不做加权融合**。
If you pass two-way moneyline odds (`oh`/`oa`), the API also returns de-vigged market-implied probabilities `market.moneyline` and the model-vs-market gap `divergence`. **Model and market are shown side by side, never blended into one number.**

---

## HTTP API

本地启动 · Run locally:

```bash
python3 server.py          # 默认端口 PORT=8000
```

| 路由 Route | 说明 Description |
|---|---|
| `GET /health` | 服务状态 + 就绪联赛数 · status + ready leagues |
| `GET /competitions` | 全部联赛 + categoryId + 回测命中率 · all leagues |
| `GET /teams?categoryId=745&q=Lakers` | 查队伍(快照内)· team lookup |
| `GET /predict?categoryId=745&a=Lakers&b=Celtics` | 预测一场 · predict a game |

联赛解析三选一 · Resolve a league by any one of:`categoryId`(平台分类 id) / `code`(内部目录) / `name`(联赛名,支持包含匹配)。
预测参数 · Predict params:`a`、`b`(主/客队名,支持模糊匹配)、`lang`(`zh`/`en`/`vi`)、可选 `oh`/`oa`(两向胜负赔率)。

示例 · Example:

```bash
curl "http://localhost:8000/predict?categoryId=745&a=Lakers&b=Celtics&lang=en&oh=2.10&oa=1.75"
```

队名支持模糊匹配(词级 + 常见缩写,如 `LA`/`GS`/`OKC`),无需精确全称。
Team names use fuzzy matching (word-level + common abbreviations like `LA`/`GS`/`OKC`); exact full names are not required.

---

## 每日刷新 · Daily Refresh

`refresh.py` 只拉「上次快照日期之后」的已结束比赛,增量并入评级,再提交更新后的 `ratings.json`。用量极低:主数据源按**日期**整体拉取,一天约一次调用即可覆盖全部联赛;WNBA 赛季内另用免费公开接口按日拉取。即使数据源不付费,每日新增拉取也在免费额度内。

`refresh.py` fetches only finished games **after the last snapshot date**, merges them incrementally, and commits the updated `ratings.json`. Usage is minimal: the primary source is queried **by date** (roughly one call per day covers all leagues); WNBA uses a free public endpoint by date during its season. Daily incremental pulls stay within free tiers even without a paid plan.

GitHub Actions(`.github/workflows/daily-refresh.yml`)每日运行,需在仓库 Secrets 配置 `APIBASKETBALL_KEY`。密钥只存在于环境变量 / Secrets,绝不写入代码或提交。
The GitHub Action runs daily and needs `APIBASKETBALL_KEY` in repository Secrets. Keys live only in env vars / Secrets — never committed to code.

---

## 目录结构 · Layout

```
core/            评级、玩法、赔率去水、预测 · ratings, markets, odds de-vig, predict
games/<code>/    config.json(联赛配置)· ratings.json(评级快照)
server.py        HTTP API(标准库)
refresh.py       每日增量刷新 · daily incremental refresh
cli.py           snapshot / predict / backtest / list
master_mapping.json  categoryId ↔ 内部 code 映射
```

## 模型方法 · Methodology

在线评级:每队学习进攻强度 `off` 与防守强度 `dfn`,主场优势 `hfa` 与联赛均值 `mu` 同步在线更新;近期比赛权重更高。期望得分:`home = mu + hfa + off_home − dfn_away`,`away = mu + off_away − dfn_home`。由期望得分经正态近似得到全部让分/大小分/胜负概率(见上)。评级拟合与预测完全分离——快照落地后预测端零训练、可离线秒出。

Online ratings: each team learns an offense strength `off` and defense strength `dfn`; the home-court advantage `hfa` and league mean `mu` update online too, with recent games weighted more heavily. Expected points: `home = mu + hfa + off_home − dfn_away`, `away = mu + off_away − dfn_home`. A normal approximation over the point distribution yields all spread/total/moneyline probabilities (above). Fitting and prediction are fully decoupled — once snapshotted, prediction is training-free and instant offline.
