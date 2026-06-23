# TC BP Entry Model Quick Compare Extended

## 实验边界

- Development window: `2022-01-01` 至 `2024-11-30`；BTC-USDT-SWAP。
- 共享 true breakout events: 185；两个 entry model 共用同一事件池。
- True breakout 使用 fresh cross：前一根 4H close 必须仍在 level 内侧；第一次 accepted breakout 后该 level 即被消耗。
- Level 最长有效 180 天；trend_state 只由 causal confirmed swings 计算；固定 187 天 warmup 保证窗口重叠结果一致。
- Upstream acceptance-reference 4H / 12H / 24H median signed return: -0.0432% / -0.0160% / -0.1881%。
- Raw OHLCV only；holdout 未读取；未修改正式配置、RiskEngine、cost、exit、sizing。
- 本报告仅含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`；future return、MFE/MAE、path-order 不进入 feature。
- 原始核心表保留原实验 48H path-order 口径；扩展 path-order 与 MFE/MAE 观察窗为入场后最多 96H。
- 同根 15m 同时触发目标和 invalidation 的样本排除出主路径统计。

## 双模型核心表

| model | events | triggered | trigger_rate | +1R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| left_level_edge_limit | 185 | 80 | 43.24% | 55.71% | 44.29% | 0.0500 | +0.1174% | +0.1328% | limit_expired_32_bars |
| right_level_retest_confirm | 185 | 46 | 24.86% | 54.35% | 39.13% | 0.4529 | -0.1057% | -0.0268% | retest_invalidated_setup |

## 风险距离

| model | triggered | median_stop_distance_ATR | median_stop_distance_pct | p25_stop_distance_pct | p75_stop_distance_pct | median_entry_to_level_ATR |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 80 | 0.2924 | +0.4539% | +0.3526% | +0.5804% | 0.0500 |
| right_level_retest_confirm | 46 | 0.6577 | +1.1854% | +0.7887% | +1.5021% | 0.4529 |

## R 倍数路径

| model | +1R_first | +2R_first | invalidation_first | no_decision_rate | median_time_to_1R | median_time_to_invalidation |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 55.71% | 37.14% | 44.29% | 0.00% | 45 min | 150 min |
| right_level_retest_confirm | 60.87% | 43.48% | 39.13% | 0.00% | 488 min | 465 min |

## 固定时间方向收益

正值表示沿交易方向移动。96H 为回答长期对照问题而补充。

| model | 2H | 4H | 8H | 12H | 16H | 20H | 24H | 36H | 48H | 60H | 72H | 96H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | +0.1283% | +0.1174% | +0.1116% | +0.1328% | +0.1076% | -0.0232% | +0.1790% | +0.2438% | +0.0121% | +0.4231% | +0.2713% | -0.0291% |
| right_level_retest_confirm | -0.1176% | -0.1057% | -0.0523% | -0.0268% | -0.1432% | -0.0324% | +0.0068% | -0.3300% | -0.3706% | -0.4940% | -0.1505% | -0.5151% |

## MFE / MAE

| model | horizon | median_MFE_pct | median_MAE_pct | median_MFE_R | median_MAE_R |
|---|---:|---:|---:|---:|---:|
| left_level_edge_limit | 2H | +0.4913% | +0.3263% | 1.1249 | 0.6555 |
| left_level_edge_limit | 4H | +0.6010% | +0.4389% | 1.3724 | 0.9752 |
| left_level_edge_limit | 8H | +0.9072% | +0.6675% | 1.7449 | 1.7139 |
| left_level_edge_limit | 12H | +1.0123% | +0.8044% | 1.9675 | 1.8820 |
| left_level_edge_limit | 16H | +1.1199% | +0.9080% | 2.1172 | 2.2927 |
| left_level_edge_limit | 20H | +1.2220% | +1.2546% | 2.5094 | 3.0653 |
| left_level_edge_limit | 24H | +1.3530% | +1.2961% | 3.1671 | 3.1734 |
| left_level_edge_limit | 36H | +1.9489% | +1.6358% | 3.8375 | 3.3845 |
| left_level_edge_limit | 48H | +2.2244% | +2.0704% | 4.5796 | 4.6048 |
| left_level_edge_limit | 60H | +2.7270% | +2.2500% | 5.7815 | 4.7721 |
| left_level_edge_limit | 72H | +3.1332% | +2.4961% | 8.1230 | 5.2394 |
| left_level_edge_limit | 96H | +3.2770% | +2.8169% | 8.1581 | 5.5589 |
| right_level_retest_confirm | 2H | +0.3077% | +0.3675% | 0.2635 | 0.3342 |
| right_level_retest_confirm | 4H | +0.3856% | +0.5146% | 0.3184 | 0.4433 |
| right_level_retest_confirm | 8H | +0.5854% | +0.7876% | 0.5469 | 0.6426 |
| right_level_retest_confirm | 12H | +0.7938% | +0.8179% | 0.8951 | 0.6757 |
| right_level_retest_confirm | 16H | +0.9072% | +0.9813% | 1.1918 | 0.8649 |
| right_level_retest_confirm | 20H | +1.1762% | +1.0417% | 1.2016 | 0.8649 |
| right_level_retest_confirm | 24H | +1.4142% | +1.1270% | 1.2738 | 1.2368 |
| right_level_retest_confirm | 36H | +2.0001% | +1.5901% | 1.7975 | 1.3202 |
| right_level_retest_confirm | 48H | +2.0001% | +2.4051% | 1.8749 | 1.9700 |
| right_level_retest_confirm | 60H | +3.1965% | +2.6198% | 2.2567 | 2.2514 |
| right_level_retest_confirm | 72H | +3.4116% | +2.7702% | 2.4993 | 2.3249 |
| right_level_retest_confirm | 96H | +3.6998% | +3.1326% | 2.6545 | 2.7174 |

## Paired Subset 拓展

| left_model | paired | stop_pct L/R | 24H L/R | 48H L/R | 72H L/R | 96H L/R | +2R_first L/R | MFE_pct L/R | MAE_pct L/R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 27 | +0.4731% / +1.0585% | +0.4078% / -0.1130% | -0.3791% / -0.9635% | -0.1875% / -0.8656% | -0.3641% / -0.7797% | 66.67% / 33.33% | +2.9376% / +2.6212% | +2.7797% / +3.2592% |

## Asset / Direction 简单分组

| model | group | n | +1R_first | +2R_first | invalidation_first | 48H | 72H | 96H | MFE_pct | MAE_pct |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | asset:BTC | 72 | 55.71% | 37.14% | 44.29% | +0.0121% | +0.2713% | -0.0291% | +3.2770% | +2.8169% |
| left_level_edge_limit | direction:long | 38 | 61.11% | 41.67% | 38.89% | -0.0074% | +0.0045% | +0.0912% | +3.2566% | +2.8259% |
| left_level_edge_limit | direction:short | 34 | 50.00% | 32.35% | 50.00% | +0.0121% | +0.7063% | -0.1446% | +3.4119% | +2.7220% |
| right_level_retest_confirm | asset:BTC | 46 | 60.87% | 43.48% | 39.13% | -0.3706% | -0.1505% | -0.5151% | +3.6998% | +3.1326% |
| right_level_retest_confirm | direction:long | 25 | 64.00% | 56.00% | 36.00% | -0.7813% | +0.6510% | +0.3644% | +3.6895% | +3.2592% |
| right_level_retest_confirm | direction:short | 21 | 57.14% | 28.57% | 42.86% | -0.1740% | -0.4229% | -0.6770% | +3.7957% | +3.0059% |

## 简短结论

1. `left_level_edge_limit` 的 +1R 优势仍有明显的小 R 几何嫌疑：其 +2R-first 为 37.14%，invalidation-first 为 44.29%，48H/72H/96H 中位方向收益分别为 +0.0121% / +0.2713% / -0.0291%。
2. 各长期窗口中位数最高模型：48H=left_level_edge_limit、72H=left_level_edge_limit、96H=left_level_edge_limit。这只是 development diagnostic，不是可交易绩效。
3. `right_level_retest_confirm` 在 48H/72H/96H 均未反超 left_level_edge_limit。
4. 当前证据只支持继续观察 left_level_edge_limit；右侧确认可停止扩展。

本次 decision：`stop_bp_upstream_breakout_edge_failed`。本扩展不改变策略、参数或研究阶段。
