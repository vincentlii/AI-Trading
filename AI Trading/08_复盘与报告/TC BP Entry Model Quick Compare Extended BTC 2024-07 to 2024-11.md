# TC BP Entry Model Quick Compare Extended

## 实验边界

- Development window: `2024-07-01` 至 `2024-11-30`；BTC-USDT-SWAP。
- 共享 true breakout events: 34；两个 entry model 共用同一事件池。
- True breakout 使用 fresh cross：前一根 4H close 必须仍在 level 内侧；第一次 accepted breakout 后该 level 即被消耗。
- Level 最长有效 180 天；trend_state 只由 causal confirmed swings 计算；固定 187 天 warmup 保证窗口重叠结果一致。
- Upstream acceptance-reference 4H / 12H / 24H median signed return: +0.1352% / +0.0355% / +0.6513%。
- Raw OHLCV only；holdout 未读取；未修改正式配置、RiskEngine、cost、exit、sizing。
- 本报告仅含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`；future return、MFE/MAE、path-order 不进入 feature。
- 原始核心表保留原实验 48H path-order 口径；扩展 path-order 与 MFE/MAE 观察窗为入场后最多 96H。
- 同根 15m 同时触发目标和 invalidation 的样本排除出主路径统计。

## 双模型核心表

| model | events | triggered | trigger_rate | +1R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| left_level_edge_limit | 34 | 14 | 41.18% | 40.00% | 60.00% | 0.0500 | +0.0785% | +0.0760% | limit_expired_32_bars |
| right_level_retest_confirm | 34 | 7 | 20.59% | 57.14% | 42.86% | 0.5101 | +0.1410% | +0.2361% | retest_invalidated_setup |

## 风险距离

| model | triggered | median_stop_distance_ATR | median_stop_distance_pct | p25_stop_distance_pct | p75_stop_distance_pct | median_entry_to_level_ATR |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 14 | 0.2963 | +0.4054% | +0.3563% | +0.4714% | 0.0500 |
| right_level_retest_confirm | 7 | 0.6952 | +1.1587% | +0.8941% | +1.3821% | 0.5101 |

## R 倍数路径

| model | +1R_first | +2R_first | invalidation_first | no_decision_rate | median_time_to_1R | median_time_to_invalidation |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 40.00% | 30.00% | 60.00% | 0.00% | 45 min | 90 min |
| right_level_retest_confirm | 57.14% | 42.86% | 42.86% | 0.00% | 285 min | 795 min |

## 固定时间方向收益

正值表示沿交易方向移动。96H 为回答长期对照问题而补充。

| model | 2H | 4H | 8H | 12H | 16H | 20H | 24H | 36H | 48H | 60H | 72H | 96H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | -0.0330% | +0.0785% | -0.1587% | +0.0760% | +0.4738% | +0.2299% | +0.3737% | +0.4589% | +0.9568% | +0.5122% | +1.9036% | +4.0439% |
| right_level_retest_confirm | -0.3896% | +0.1410% | -0.0829% | +0.2361% | +0.2568% | +0.4385% | +0.1358% | +0.1785% | +0.7900% | +2.2322% | +1.6114% | +2.9298% |

## MFE / MAE

| model | horizon | median_MFE_pct | median_MAE_pct | median_MFE_R | median_MAE_R |
|---|---:|---:|---:|---:|---:|
| left_level_edge_limit | 2H | +0.3569% | +0.4819% | 1.0029 | 1.2359 |
| left_level_edge_limit | 4H | +0.7145% | +0.5973% | 1.5532 | 1.2984 |
| left_level_edge_limit | 8H | +0.7145% | +0.8255% | 1.6349 | 1.9850 |
| left_level_edge_limit | 12H | +0.9435% | +0.8255% | 1.8703 | 1.9850 |
| left_level_edge_limit | 16H | +1.1156% | +1.1528% | 3.0837 | 2.5232 |
| left_level_edge_limit | 20H | +2.3284% | +1.4031% | 5.5989 | 3.8784 |
| left_level_edge_limit | 24H | +2.3284% | +1.5263% | 5.5989 | 3.9089 |
| left_level_edge_limit | 36H | +2.3284% | +2.0226% | 5.5989 | 4.1840 |
| left_level_edge_limit | 48H | +3.1439% | +2.1837% | 9.2036 | 5.6298 |
| left_level_edge_limit | 60H | +3.4328% | +2.1837% | 9.6857 | 5.6298 |
| left_level_edge_limit | 72H | +4.0500% | +2.1837% | 10.2946 | 5.6298 |
| left_level_edge_limit | 96H | +5.0060% | +2.1837% | 11.3391 | 5.6298 |
| right_level_retest_confirm | 2H | +0.1404% | +0.6727% | 0.1761 | 0.4797 |
| right_level_retest_confirm | 4H | +0.2615% | +0.7737% | 0.2257 | 0.6257 |
| right_level_retest_confirm | 8H | +0.5181% | +0.8016% | 0.4517 | 0.6257 |
| right_level_retest_confirm | 12H | +0.5181% | +0.8016% | 0.6036 | 0.6257 |
| right_level_retest_confirm | 16H | +1.6829% | +0.8352% | 1.2028 | 0.6257 |
| right_level_retest_confirm | 20H | +1.6829% | +0.8755% | 1.2028 | 0.6918 |
| right_level_retest_confirm | 24H | +1.6829% | +0.8755% | 1.2028 | 0.6918 |
| right_level_retest_confirm | 36H | +1.6829% | +1.0659% | 1.4524 | 1.8540 |
| right_level_retest_confirm | 48H | +1.6829% | +1.7742% | 1.4524 | 1.8540 |
| right_level_retest_confirm | 60H | +3.7881% | +1.7742% | 2.6087 | 1.8540 |
| right_level_retest_confirm | 72H | +3.7881% | +1.7742% | 2.6087 | 1.8540 |
| right_level_retest_confirm | 96H | +4.5105% | +1.7742% | 2.9525 | 1.8540 |

## Paired Subset 拓展

| left_model | paired | stop_pct L/R | 24H L/R | 48H L/R | 72H L/R | 96H L/R | +2R_first L/R | MFE_pct L/R | MAE_pct L/R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 4 | +0.4259% / +0.9000% | +0.9214% / +0.3603% | +0.8560% / +0.8795% | +2.0971% / +1.8237% | +3.1414% / +2.4935% | 75.00% / 50.00% | +4.2080% / +3.6794% | +0.8821% / +1.3580% |

## Asset / Direction 简单分组

| model | group | n | +1R_first | +2R_first | invalidation_first | 48H | 72H | 96H | MFE_pct | MAE_pct |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | asset:BTC | 11 | 40.00% | 30.00% | 60.00% | +0.9568% | +1.9036% | +4.0439% | +5.0060% | +2.1837% |
| left_level_edge_limit | direction:long | 8 | 42.86% | 42.86% | 57.14% | +0.8478% | +2.0971% | +4.0449% | +4.8317% | +2.1211% |
| left_level_edge_limit | direction:short | 3 | 33.33% | 0.00% | 66.67% | +2.7787% | +0.7365% | +1.8861% | +5.2162% | +2.5898% |
| right_level_retest_confirm | asset:BTC | 7 | 57.14% | 42.86% | 42.86% | +0.7900% | +1.6114% | +2.9298% | +4.5105% | +1.7742% |
| right_level_retest_confirm | direction:long | 6 | 50.00% | 50.00% | 50.00% | +0.8795% | +1.8237% | +2.1545% | +3.6794% | +1.3580% |
| right_level_retest_confirm | direction:short | 1 | 100.00% | 0.00% | 0.00% | +0.3163% | +0.3073% | +3.4367% | +4.5105% | +2.8324% |

## 简短结论

1. `left_level_edge_limit` 的 +1R 优势仍有明显的小 R 几何嫌疑：其 +2R-first 为 30.00%，invalidation-first 为 60.00%，48H/72H/96H 中位方向收益分别为 +0.9568% / +1.9036% / +4.0439%。
2. 各长期窗口中位数最高模型：48H=left_level_edge_limit、72H=left_level_edge_limit、96H=left_level_edge_limit。这只是 development diagnostic，不是可交易绩效。
3. `right_level_retest_confirm` 在 48H/72H/96H 均未反超 left_level_edge_limit。
4. 建议保留右侧确认作为后续对照，左侧 level-edge 仍为主要研究对象。

本次 decision：`inconclusive_need_more_development_scan`。本扩展不改变策略、参数或研究阶段。
