# TC/BP 35个月综合轻量诊断实验

## 实验边界

- Development window: `2022-01-01` 至 `2024-11-30`；标的：BTC-USDT-SWAP。
- Holdout start: `2024-12-01`，本实验不读取 holdout。
- 本报告只包含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`。
- 未修改 RiskEngine、正式配置、cost、exit、sizing。
- 事件、trend、VPA、entry diagnostic 均从 raw OHLCV 重新生成，不复用旧缓存。

## Event funnel

| item | count | note |
|---|---:|---|
| raw true breakout candidates | 974 | no trend hard gate；later level attempts allowed |
| current hard confirmed-swing trend match | 274 | trend_state == breakout direction |
| no trend gate retained | 974 | diagnostic candidate pool |
| attempt 1 first accepted | 362 | current first-consume baseline |
| attempt 2 later accepted | 243 | level consume soft diagnostic |
| attempt >=3 later accepted | 369 | repeated attempts diagnostic |

Upstream acceptance-reference 4H / 12H / 24H median signed return: -0.0369% / -0.0143% / -0.1779%。

## Entry model core

备注：`+1R_first`、`+1.5R_first`、`+2R_first`、`invalidation_first` 均统计入场后 48H path-order 观察窗口；2H/4H/8H/12H/24H/48H 列为对应固定持仓时长的方向收益。

| model | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| left_level_edge_limit | 974 | 487 | 50.00% | 58.74% | 49.42% | 44.52% | 41.26% | 0.0500 | +0.1531% | +0.1150% | limit_expired_32_bars |
| right_level_retest_confirm | 974 | 252 | 25.87% | 50.79% | 38.49% | 30.16% | 44.84% | 0.4313 | -0.0766% | -0.0406% | retest_invalidated_setup |
| right_level_retest_confirm_soft_vpa | 974 | 702 | 72.07% | 53.81% | 41.44% | 32.52% | 43.74% | 0.3602 | -0.0178% | +0.0014% | no_valid_level_retest |

## Trend diagnostic

| model | group | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | 2H | 4H | 8H | 12H | 24H | 48H |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | trend_opposite | 223 | 106 | 47.53% | 56.19% | 52.38% | 48.57% | 43.81% | +0.1610% | +0.1536% | +0.2257% | +0.2638% | +0.1151% | +0.2198% |
| left_level_edge_limit | trend_score_match | 416 | 185 | 44.47% | 57.61% | 45.11% | 39.13% | 42.39% | +0.1471% | +0.1149% | +0.1696% | +0.0689% | -0.0333% | +0.0375% |
| left_level_edge_limit | trend_unknown_or_transition | 335 | 141 | 42.09% | 62.14% | 52.86% | 48.57% | 37.86% | +0.1321% | +0.2060% | +0.1367% | +0.1362% | +0.1759% | -0.0152% |
| right_level_retest_confirm_soft_vpa | trend_opposite | 223 | 166 | 74.44% | 56.02% | 39.16% | 29.52% | 42.17% | -0.0084% | -0.0296% | +0.0045% | -0.0094% | +0.1598% | -0.0329% |
| right_level_retest_confirm_soft_vpa | trend_score_match | 416 | 293 | 70.43% | 55.17% | 44.48% | 35.17% | 41.72% | -0.0058% | -0.0102% | +0.0035% | -0.0058% | -0.1364% | -0.0852% |
| right_level_retest_confirm_soft_vpa | trend_unknown_or_transition | 335 | 243 | 72.54% | 50.63% | 39.33% | 31.38% | 47.28% | +0.0073% | -0.0174% | +0.0179% | +0.0291% | +0.0855% | +0.0510% |

## Level consume / attempt diagnostic

| model | group | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | 2H | 4H | 8H | 12H | 24H | 48H |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | attempt_1_first_accepted | 362 | 152 | 41.99% | 59.87% | 48.68% | 42.11% | 40.13% | +0.1444% | +0.1978% | +0.1513% | +0.1366% | +0.1394% | +0.2342% |
| left_level_edge_limit | attempt_2_later_accepted | 243 | 108 | 44.44% | 58.49% | 49.06% | 44.34% | 41.51% | +0.1589% | +0.1355% | +0.1878% | +0.0160% | +0.1906% | +0.0575% |
| left_level_edge_limit | attempt_3_plus_later_accepted | 369 | 172 | 46.61% | 57.89% | 50.29% | 46.78% | 42.11% | +0.1395% | +0.1302% | +0.1952% | +0.1197% | -0.0379% | -0.1281% |
| right_level_retest_confirm_soft_vpa | attempt_1_first_accepted | 362 | 253 | 69.89% | 52.19% | 41.04% | 31.08% | 45.42% | -0.0534% | -0.0266% | -0.0136% | -0.0188% | +0.0044% | +0.0252% |
| right_level_retest_confirm_soft_vpa | attempt_2_later_accepted | 243 | 182 | 74.90% | 55.80% | 40.33% | 31.49% | 40.88% | +0.0221% | -0.0014% | -0.0204% | +0.0299% | +0.0752% | +0.0321% |
| right_level_retest_confirm_soft_vpa | attempt_3_plus_later_accepted | 369 | 267 | 72.36% | 53.99% | 42.59% | 34.60% | 44.11% | +0.0347% | -0.0168% | +0.0671% | +0.0499% | +0.0156% | -0.1451% |

## Right retest lifecycle

| model | group | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | 2H | 4H | 8H | 12H | 24H | 48H |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| right_level_retest_confirm_soft_vpa | close_breach_reclaimed | 91 | 81 | 89.01% | 44.30% | 37.97% | 31.65% | 54.43% | -0.0588% | -0.1901% | -0.0768% | +0.0126% | -0.1534% | -0.4078% |
| right_level_retest_confirm_soft_vpa | confirmed_failure | 70 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | n/a | n/a | n/a | n/a | n/a | n/a |
| right_level_retest_confirm_soft_vpa | deep_but_reclaimed | 2 | 2 | 100.00% | 0.00% | 0.00% | 0.00% | 100.00% | -1.4485% | -1.4503% | -2.1851% | -1.8736% | -2.5655% | -1.8034% |
| right_level_retest_confirm_soft_vpa | no_reclaim_after_retest | 2 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | n/a | n/a | n/a | n/a | n/a | n/a |
| right_level_retest_confirm_soft_vpa | no_retest | 152 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | n/a | n/a | n/a | n/a | n/a | n/a |
| right_level_retest_confirm_soft_vpa | shallow_retest | 520 | 494 | 95.00% | 56.21% | 42.77% | 33.20% | 41.14% | +0.0052% | -0.0014% | +0.0231% | +0.0461% | +0.0579% | +0.0156% |
| right_level_retest_confirm_soft_vpa | wick_breach_reclaimed | 137 | 125 | 91.24% | 51.22% | 39.02% | 30.89% | 46.34% | +0.0157% | -0.0267% | -0.0054% | -0.1230% | +0.2075% | +0.1583% |

## Confirmation type

| model | group | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | 2H | 4H | 8H | 12H | 24H | 48H |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| right_level_retest_confirm_soft_vpa | level_reclaim_confirm | 500 | 490 | 98.00% | 54.53% | 41.77% | 32.51% | 43.42% | +0.0026% | -0.0267% | +0.0190% | +0.0052% | +0.0611% | +0.0069% |
| right_level_retest_confirm_soft_vpa | micro_bos_confirm | 146 | 138 | 94.52% | 53.68% | 40.44% | 32.35% | 42.65% | -0.0546% | -0.0441% | -0.0305% | -0.0848% | -0.1328% | -0.1870% |
| right_level_retest_confirm_soft_vpa | not_confirmed | 245 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | n/a | n/a | n/a | n/a | n/a | n/a |
| right_level_retest_confirm_soft_vpa | vpa_relaunch_confirm | 83 | 74 | 89.16% | 49.32% | 41.10% | 32.88% | 47.95% | +0.0605% | +0.1004% | +0.0744% | +0.1111% | +0.3567% | +0.0312% |

## VPA attribution

| model | group | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | 2H | 4H | 8H | 12H | 24H | 48H |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| right_level_retest_confirm_soft_vpa | missing_vpa | 272 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | n/a | n/a | n/a | n/a | n/a | n/a |
| right_level_retest_confirm_soft_vpa | normal_vpa | 297 | 297 | 100.00% | 54.27% | 41.98% | 32.08% | 41.98% | +0.0073% | -0.0291% | +0.0110% | +0.0591% | +0.1283% | +0.2086% |
| right_level_retest_confirm_soft_vpa | strong_vpa | 294 | 294 | 100.00% | 54.98% | 44.67% | 36.43% | 43.99% | +0.0215% | +0.0425% | +0.0551% | +0.0072% | +0.0219% | -0.0802% |
| right_level_retest_confirm_soft_vpa | weak_vpa | 111 | 111 | 100.00% | 49.55% | 31.53% | 23.42% | 47.75% | -0.0319% | -0.1000% | -0.0937% | -0.1226% | -0.1622% | -0.4100% |

## Decision

`trend_gate_overfiltered_continue_soft_score`

解释：本实验仍停留在 signal/entry diagnostic。fixed return、MFE/MAE、path-order 均为 diagnostic label，不允许进入 feature、score、gate 或正式策略。
