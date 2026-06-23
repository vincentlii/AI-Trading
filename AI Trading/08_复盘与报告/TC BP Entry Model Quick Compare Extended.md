# TC BP Entry Model Quick Compare Extended

## 实验边界

- Development window: `2022-01-01` 至 `2024-11-30`；BTC-USDT-SWAP / ETH-USDT-SWAP。
- 共享 true breakout events: 962；两个 entry model 共用同一事件池。
- Raw OHLCV only；holdout 未读取；未修改正式配置、RiskEngine、cost、exit、sizing。
- 本报告仅含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`；future return、MFE/MAE、path-order 不进入 feature。
- 原始核心表保留原实验 48H path-order 口径；扩展 path-order 与 MFE/MAE 观察窗为入场后最多 96H。
- 同根 15m 同时触发目标和 invalidation 的样本排除出主路径统计。

## 原始四模型核心表

| model | events | triggered | trigger_rate | +1R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| left_level_edge_limit | 962 | 493 | 51.25% | 56.94% | 43.06% | 0.0500 | +0.1540% | +0.0956% | limit_expired_32_bars |
| right_level_retest_confirm | 962 | 336 | 34.93% | 46.13% | 50.30% | 0.4287 | -0.1129% | -0.1556% | no_valid_level_retest |

## 风险距离

| model | triggered | median_stop_distance_ATR | median_stop_distance_pct | p25_stop_distance_pct | p75_stop_distance_pct | median_entry_to_level_ATR |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 493 | 0.3126 | +0.5450% | +0.4321% | +0.6790% | 0.0500 |
| right_level_retest_confirm | 336 | 0.7104 | +1.2115% | +0.8625% | +1.7864% | 0.4287 |

## R 倍数路径

| model | +1R_first | +2R_first | invalidation_first | no_decision_rate | median_time_to_1R | median_time_to_invalidation |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 56.94% | 39.35% | 43.06% | 0.00% | 60 min | 195 min |
| right_level_retest_confirm | 48.51% | 32.44% | 50.89% | 0.60% | 330 min | 570 min |

## 固定时间方向收益

正值表示沿交易方向移动。96H 为回答长期对照问题而补充。

| model | 2H | 4H | 8H | 12H | 16H | 20H | 24H | 36H | 48H | 60H | 72H | 96H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | +0.1402% | +0.1540% | +0.1026% | +0.0956% | -0.0710% | -0.0506% | +0.0557% | +0.2329% | -0.0913% | -0.1263% | -0.0321% | +0.0462% |
| right_level_retest_confirm | -0.0159% | -0.1129% | -0.0625% | -0.1556% | -0.0733% | -0.0477% | -0.2031% | -0.0792% | -0.3672% | -0.4237% | -0.1499% | -0.2016% |

## MFE / MAE

| model | horizon | median_MFE_pct | median_MAE_pct | median_MFE_R | median_MAE_R |
|---|---:|---:|---:|---:|---:|
| left_level_edge_limit | 2H | +0.5299% | +0.3517% | 0.9559 | 0.6265 |
| left_level_edge_limit | 4H | +0.7359% | +0.5132% | 1.3419 | 0.9589 |
| left_level_edge_limit | 8H | +0.9540% | +0.8348% | 1.8179 | 1.4704 |
| left_level_edge_limit | 12H | +1.1519% | +1.0494% | 2.0954 | 1.9236 |
| left_level_edge_limit | 16H | +1.3237% | +1.2645% | 2.5177 | 2.2860 |
| left_level_edge_limit | 20H | +1.4886% | +1.5112% | 2.8314 | 2.8245 |
| left_level_edge_limit | 24H | +1.7064% | +1.5734% | 3.0489 | 2.9539 |
| left_level_edge_limit | 36H | +2.2485% | +1.9160% | 3.9370 | 3.7069 |
| left_level_edge_limit | 48H | +2.5312% | +2.2952% | 4.4199 | 4.3975 |
| left_level_edge_limit | 60H | +2.8604% | +2.5185% | 4.9934 | 4.7415 |
| left_level_edge_limit | 72H | +3.0523% | +2.7481% | 5.4284 | 5.3387 |
| left_level_edge_limit | 96H | +3.4483% | +3.2063% | 5.8497 | 6.1181 |
| right_level_retest_confirm | 2H | +0.3768% | +0.3865% | 0.3172 | 0.3086 |
| right_level_retest_confirm | 4H | +0.5258% | +0.5909% | 0.4095 | 0.4604 |
| right_level_retest_confirm | 8H | +0.7791% | +0.9149% | 0.6144 | 0.7004 |
| right_level_retest_confirm | 12H | +0.9886% | +1.0948% | 0.7530 | 0.8128 |
| right_level_retest_confirm | 16H | +1.2168% | +1.2466% | 0.9494 | 0.9840 |
| right_level_retest_confirm | 20H | +1.4706% | +1.4829% | 1.1691 | 1.1180 |
| right_level_retest_confirm | 24H | +1.5144% | +1.6299% | 1.2179 | 1.2584 |
| right_level_retest_confirm | 36H | +1.9124% | +1.8151% | 1.5890 | 1.5970 |
| right_level_retest_confirm | 48H | +2.1787% | +2.3416% | 1.7140 | 1.8401 |
| right_level_retest_confirm | 60H | +2.4774% | +2.6240% | 1.9449 | 2.0833 |
| right_level_retest_confirm | 72H | +2.7539% | +2.8038% | 2.2975 | 2.2633 |
| right_level_retest_confirm | 96H | +3.2939% | +3.4116% | 2.5639 | 2.6239 |

## Paired Subset 拓展

| left_model | paired | stop_pct L/R | 24H L/R | 48H L/R | 72H L/R | 96H L/R | +2R_first L/R | MFE_pct L/R | MAE_pct L/R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 203 | +0.5452% / +1.1887% | +0.5521% / -0.2257% | +0.3458% / -0.4588% | +0.2451% / -0.2054% | +0.4397% / -0.3287% | 54.68% / 33.00% | +3.9827% / +3.2230% | +2.5643% / +3.4443% |

## Asset / Direction 简单分组

| model | group | n | +1R_first | +2R_first | invalidation_first | 48H | 72H | 96H | MFE_pct | MAE_pct |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | asset:BTC | 219 | 60.27% | 39.73% | 39.73% | -0.1290% | +0.1128% | +0.0992% | +2.9631% | +2.9535% |
| left_level_edge_limit | asset:ETH | 213 | 53.52% | 38.97% | 46.48% | -0.0665% | -0.2914% | +0.0109% | +4.1051% | +3.7549% |
| left_level_edge_limit | direction:long | 235 | 57.45% | 40.43% | 42.55% | -0.0884% | +0.2787% | +0.4773% | +3.7257% | +3.0666% |
| left_level_edge_limit | direction:short | 197 | 56.35% | 38.07% | 43.65% | -0.0934% | -0.3233% | -0.6284% | +3.1914% | +3.6342% |
| right_level_retest_confirm | asset:BTC | 180 | 45.00% | 31.67% | 54.44% | -0.2822% | -0.3081% | -0.3573% | +2.8555% | +2.9618% |
| right_level_retest_confirm | asset:ETH | 156 | 52.56% | 33.33% | 46.79% | -0.5602% | -0.1126% | -0.0464% | +3.7286% | +3.9150% |
| right_level_retest_confirm | direction:long | 178 | 52.25% | 37.08% | 47.19% | -0.1479% | +0.6065% | +0.6744% | +3.6488% | +2.9981% |
| right_level_retest_confirm | direction:short | 158 | 44.30% | 27.22% | 55.06% | -0.5747% | -0.6282% | -1.0797% | +2.8689% | +3.9585% |

## 简短结论

1. `left_level_edge_limit` 的 +1R 优势仍有明显的小 R 几何嫌疑：其 +2R-first 为 39.35%，invalidation-first 为 43.06%，48H/72H/96H 中位方向收益分别为 -0.0913% / -0.0321% / +0.0462%。
2. 各长期窗口中位数最高模型：48H=left_level_edge_limit、72H=left_level_edge_limit、96H=left_level_edge_limit。这只是 development diagnostic，不是可交易绩效。
3. `right_level_retest_confirm` 在 48H/72H/96H 均未反超 left_level_edge_limit。
4. 当前证据只支持继续观察 left_level_edge_limit；右侧确认可停止扩展。

原实验 decision 保持：`stop_bp_upstream_breakout_edge_failed`。本扩展不改变策略、参数或研究阶段。
