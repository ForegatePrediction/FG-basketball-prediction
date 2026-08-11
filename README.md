# ForeGate Basketball Prediction · 篮球预测服务

零依赖(Python 标准库)的篮球赛前概率服务,覆盖平台全部 **24 个篮球联赛**。基于球队进攻/防守效率评级 + 主场优势,平台玩法(胜负 / 让分 / 大小分 / 加时)全部联赛都有;NBA 等有分节数据的联赛额外产出 **半场 / 下半场 / 各单节 · 球队得分 · 净胜分区间 · 最高得分半场/单节 · 半场-全场**。评级在线滚动更新、落快照,预测端零训练、秒级响应。

A zero-dependency (Python stdlib) pre-game basketball probability service covering all **24 platform basketball leagues**. Core platform markets (moneyline / spreads / totals / overtime) exist for every league; leagues with quarter data (NBA etc.) also get halves / quarters / team totals / margin bands / highest-scoring half & quarter. Ratings update online and are snapshotted (training-free, millisecond responses).

---

## 覆盖 · Coverage(平台 24 个篮球联赛)

前端用 `platform_id`(平台内部联赛 id)直接解析调用。`免费日更` ✅ = 免费源(ESPN / EuroLeague 官方),付费到期后仍持续每日更新;`—` = api-basketball 付费源,付费期(至 2026-09)每日更新,到期后冻结在已存历史(仍可预测,不再增量)。

Frontend resolves by `platform_id`. `免费日更` ✅ = free source (ESPN / EuroLeague official), keeps updating after the paid window; `—` = api-basketball paid source, updates daily during the paid window (until 2026-09), then freezes on stored history (still predictable, no new increments).

| platform_id | 联赛 | code | 数据源 | 免费日更 | 胜负命中 | 样本 |
|---|---|---|---|:--:|--:|--:|
| 30163 | NBA | 12 | ESPN 免费 | ✅ | 66.6% | 5,557 |
| 30164 | NCAAB | 116 | ESPN 免费 | ✅ | 72.6% | 23,573 |
| 30165 | KBL (Korea) | 91 | api-basketball 付费 | — | 63.5% | 1,741 |
| 30166 | CBA (China) | 31 | api-basketball 付费 | — | 74.1% | 2,905 |
| 30167 | Liga A (Argentina) | 18 | api-basketball 付费 | — | 64.8% | 2,519 |
| 30168 | CWBB (Women's College) | cwbb | ESPN 免费 | ✅ | 74.7% | 11,385 |
| 30169 | EuroLeague | 120 | 官方免费 | ✅ | 64.8% | 2,270 |
| 30170 | B.League (Japan) | 56 | api-basketball 付费 | — | 68.8% | 3,625 |
| 30171 | VTB United League | 82 | api-basketball 付费 | — | 76.2% | 1,413 |
| 30172 | Basketball Champions League | 202 | api-basketball 付费 | — | 56.4% | 989 |
| 30173 | Pro A (France) | 2 | api-basketball 付费 | — | 67.9% | 1,827 |
| 30174 | Liga Endesa (Spain) | 117 | api-basketball 付费 | — | 68.8% | 1,990 |
| 30175 | Lega A (Italy) | 52 | api-basketball 付费 | — | 66.4% | 1,566 |
| 30176 | BBL (Germany) | 40 | api-basketball 付费 | — | 65.9% | 1,970 |
| 30177 | ABA League | 198 | api-basketball 付费 | — | 74.2% | 1,308 |
| 30178 | BSL (Turkey) | 104 | api-basketball 付费 | — | 69.1% | 1,542 |
| 30179 | Basket League (Greece) | 45 | api-basketball 付费 | — | 76.1% | 1,054 |
| 30180 | NBL (Australia) | 1 | ESPN 免费 | ✅ | 66.6% | 676 |
| 30207 | WNBA | wnba | ESPN 免费 | ✅ | 65.5% | 1,349 |
| 30211 | FIBA WCQ Asia (Asia Cup pool) | 301 | api-basketball 付费 | — | 71.8% | 411 |
| 30212 | WNBA | wnba | ESPN 免费 | ✅ | 65.5% | 1,349 |
| 30213 | FIBA WCQ Americas (AmeriCup pool) | 282 | api-basketball 付费 | — | 69.9% | 306 |
| 30214 | FIBA WCQ Europe (EuroBasket pool) | 197 | api-basketball 付费 | — | 60.2% | 518 |
| 30215 | FIBA WCQ Africa (AfroBasket pool) | 324 | api-basketball 付费 | — | 65.2% | 132 |
| 30220 | NBA Summer League | 17 | api-basketball 付费 | — | 52.9% | 454 |

> 各联赛历史约 4–6 个赛季(含最新赛季)。评级在线滚动更新,近期比赛权重更高。
> ~4–6 seasons per league (incl. current). Online ratings weight recent games more.

---

## 支持玩法与字段 · Markets & Fields

预测返回的 `markets` 含以下键。`full_game / first_half / second_half / q1 / q2 / q3 / q4` 七个分段结构一致,各含四类玩法:

The `markets` object has the keys below. The seven segments `full_game / first_half / second_half / q1 / q2 / q3 / q4` share one structure, each with four market types:

| 分段内玩法 Segment market | 字段 Field | 说明 Description |
|---|---|---|
| 期望得分 Expected points | `expected_points.home/.away/.total` | 该分段双方期望得分与总分 · projected points/total for the segment |
| 胜负 Moneyline | `moneyline.home/.away` | 该分段主/客获胜概率 · win prob for the segment |
| 让分 Spreads | `spreads["<line>"].{line,home,away}` | 每条让分线双方赢盘概率(0.5 步长,对标真实 NBA 盘口,如 -3.5/-4.5)· cover prob per line |
| 大小分 Totals | `totals["<line>"].{line,over,under}` | 每条总分线大/小概率(0.5 步长,如 215.5/216.5)· over/under per line |
| 球队得分 Team totals | `team_totals.home/.away["<line>"].{line,over,under}` | 各队个人得分大小(0.5 步长,如 109.5/110.5)· each team's points over/under |

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

## 平台玩法字段对齐 / Platform market keys(`platform_markets`)

预测返回额外含 `platform_markets`,用平台玩法 key 直接暴露,前端按 key 直取(全部联赛都有):

| 平台 key | 值 | 说明 |
|---|---|---|
| `moneyline` | home, away | 全场胜负 |
| `spreads` | 多条 {line, home, away} | 全场让分(0.5 步长,如 -3.5/-4.5) |
| `totals` | 多条 {line, over, under} | 全场大小分(0.5 步长,如 215.5/216.5) |
| `soccer_extra_time` | yes, no | 是否打加时(势均力敌越可能,由净胜分分布推导) |

> 内部 `markets` 另含半场/单节/球队得分等扩展玩法(有分节数据的联赛),平台只需上面 4 个 key。

---

## 每日刷新 · Daily Refresh

`refresh.py` 只拉「上次快照日期之后」的已结束比赛,增量并入评级。免费源(NBA/NCAA/WNBA/CWBB/NBL 走 ESPN、EuroLeague 走官方)零成本;其余联赛走 api-basketball 付费源。**付费到期后自动降级**:免费源联赛继续每日更新,付费源联赛拿不到新赛季数据即自动跳过、冻结在已存历史(仍可预测)。

`refresh.py` merges finished games after the last snapshot date. Free sources (ESPN + EuroLeague official) cost nothing; the rest use api-basketball (paid). **Graceful downgrade when the paid plan ends**: free-source leagues keep updating daily; paid-source leagues simply skip (frozen on stored history, still predictable).

GitHub Actions(`.github/workflows/daily-refresh.yml`)每日运行,付费源需在 Secrets 配置 `APIBASKETBALL_KEY`;免费源联赛即使无该 Secret 也照常更新。
The GitHub Action runs daily; paid sources need `APIBASKETBALL_KEY` in Secrets, while free-source leagues update even without it.

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
