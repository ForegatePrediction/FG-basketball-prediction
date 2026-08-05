# ForeGate NBA Prediction · NBA 预测服务

零依赖(Python 标准库)的 NBA 赛前概率服务。基于球队进攻/防守效率评级 + 主场优势,产出每场比赛 **全场 / 上半场 / 下半场 / 各单节** 的 **胜负 · 让分 · 大小分 · 球队得分**,外加 **净胜分区间 · 最高得分半场 · 最高得分单节 · 半场-全场双结果**。评级在线滚动更新并落成快照,预测端零训练、秒级响应。数据来自免费公开源、**无需任何 API key**。

A zero-dependency (Python standard library only) pre-game NBA probability service. From per-team offense/defense efficiency ratings plus home-court advantage, it produces **moneyline · spreads · totals · team totals** for the **full game / first half / second half / each quarter**, plus **winning-margin bands · highest-scoring half · highest-scoring quarter · half-time/full-time double result**. Ratings update online and are snapshotted (training-free, millisecond responses). Data comes from a free public source, **no API key required**.

---

## 覆盖 · Coverage

| 联赛 League | categoryId | code | 样本 Games | 胜负命中率 ML Acc | 数据源 Source |
|---|---|---|---|---|---|
| NBA | 745 | 12 | 5,557 | 66.6% | ESPN(免费,含最新赛季 · free, current season) |

> 历史覆盖近 4 个赛季(2022/23–2025/26,含最新完整赛季)。评级为在线滚动更新,近期比赛权重远高于早期——重磅交易/换血会在球队打几场后自动反映。每日增量任务持续把新赛果并入评级。
>
> ~4 seasons of history (2022/23–2025/26, including the latest full season). Ratings update online, weighting recent games far more than old ones — blockbuster trades show up within a few games. A daily incremental job keeps merging new results.

---

## 支持玩法与字段 · Markets & Fields

预测返回的 `markets` 含以下键。`full_game / first_half / second_half / q1 / q2 / q3 / q4` 七个分段结构一致,各含四类玩法:

The `markets` object has the keys below. The seven segments `full_game / first_half / second_half / q1 / q2 / q3 / q4` share one structure, each with four market types:

| 分段内玩法 Segment market | 字段 Field | 说明 Description |
|---|---|---|
| 期望得分 Expected points | `expected_points.home/.away/.total` | 该分段双方期望得分与总分 · projected points/total for the segment |
| 胜负 Moneyline | `moneyline.home/.away` | 该分段主/客获胜概率 · win prob for the segment |
| 让分 Spreads | `spreads["<line>"].{line,home,away}` | 每条让分线双方赢盘概率(多线)· cover prob per line |
| 大小分 Totals | `totals["<line>"].{line,over,under}` | 每条总分线大/小概率(多线)· over/under per line |
| 球队得分 Team totals | `team_totals.home/.away["<line>"].{line,over,under}` | 各队个人得分大小(多线)· each team's points over/under |

另有 4 个跨分段衍生玩法 · Plus four cross-segment derived markets:

| 玩法 Market | 字段 Field | 说明 Description |
|---|---|---|
| 净胜分区间 Winning margin | `winning_margin.{home,away}_{1_5,6_10,11_15,16plus}` | 主/客净胜分落在各区间的概率 · prob the winner wins by each band |
| 最高得分半场 Highest half | `highest_scoring_half.{first,second}` | 上/下半场哪个总分更高 · which half scores more |
| 最高得分单节 Highest quarter | `highest_scoring_quarter.{q1,q2,q3,q4}` | 哪一节总分最高 · which quarter scores most |
| 半场-全场双结果 Double result | `double_result.{home_home,home_away,away_home,away_away}` | 半场领先方 × 全场胜方 · half-time leader × full-time winner |

模型逻辑 · How each is derived:

净胜分 ~ `Normal(home−away, σ_margin)`,总分 ~ `Normal(home+away, σ_total)`,`σ` 由回测校准。胜负 = `Φ(margin/σ_margin)`;让分 = `P(净胜 > −line)`;大小 = `1 − Φ((line − total)/σ_total)`。半场/单节按实测得分占比拆均值(单节≈0.253/0.252/0.253/0.242,上半场≈0.505),标准差按时间份额缩放(半场 `σ/√2`、单节 `σ/2`)。球队得分 `σ_team = √(σ_margin²+σ_total²)/2`(解析推导)。净胜分区间由正态 CDF 分段;最高半场/单节由分段分布的数值积分;双结果由(半场净胜, 全场净胜)的二元正态求象限概率。

Margin ~ `Normal(home−away, σ_margin)`, total ~ `Normal(home+away, σ_total)`, `σ` backtest-calibrated. Moneyline = `Φ(margin/σ_margin)`; spread cover = `P(margin > −line)`; total over = `1 − Φ((line − total)/σ_total)`. Halves/quarters split the mean by empirical scoring shares (quarters ≈0.253/0.252/0.253/0.242, first half ≈0.505) and scale σ by the time share (`σ/√2` per half, `σ/2` per quarter). Team-total σ = `√(σ_margin²+σ_total²)/2` (analytic). Margin bands from the normal CDF; highest half/quarter by numerical integration of the segment distributions; double result from the bivariate normal of (half margin, full margin).

可选盘口混合 · Optional odds blend: 传入两向胜负赔率(`oh`/`oa`),额外返回去水市场隐含概率 `market.moneyline` 与模型-市场分歧 `divergence`,**模型与市场分开展示,不融合**。
Pass two-way moneyline odds (`oh`/`oa`) and the API adds de-vigged market probabilities `market.moneyline` and the gap `divergence`. **Model and market shown side by side, never blended.**

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

`refresh.py` 从 ESPN 免费接口只拉「上次快照日期之后」的已结束比赛,增量并入评级,再提交更新后的 `ratings.json`。**无需任何 API key、零成本**。

`refresh.py` pulls only finished games **after the last snapshot date** from the free ESPN endpoint, merges them incrementally, and commits the updated `ratings.json`. **No API key, zero cost.**

GitHub Actions(`.github/workflows/daily-refresh.yml`)每日运行——**无需配置任何 Secret**。
The GitHub Action runs daily — **no secrets to configure**.

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
