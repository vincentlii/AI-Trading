# TC BP Entry Model Quick Compare Extended

## 实验边界

- Development window: `2022-01-01` 至 `2024-11-30`；BTC-USDT-SWAP。
- 共享 true breakout events: 501；两个 entry model 共用同一事件池。
- Raw OHLCV only；holdout 未读取；未修改正式配置、RiskEngine、cost、exit、sizing。
- 本报告仅含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`；future return、MFE/MAE、path-order 不进入 feature。
- 原始核心表保留原实验 48H path-order 口径；扩展 path-order 与 MFE/MAE 观察窗为入场后最多 96H。
- 同根 15m 同时触发目标和 invalidation 的样本排除出主路径统计。

## 双模型核心表

| model | events | triggered | trigger_rate | +1R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| left_level_edge_limit | 501 | 250 | 49.90% | 60.27% | 39.73% | 0.0500 | +0.1505% | +0.0316% | limit_expired_32_bars |
| right_level_retest_confirm | 501 | 180 | 35.93% | 42.22% | 53.33% | 0.4101 | -0.0932% | -0.1059% | no_valid_level_retest |

## 风险距离

| model | triggered | median_stop_distance_ATR | median_stop_distance_pct | p25_stop_distance_pct | p75_stop_distance_pct | median_entry_to_level_ATR |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 250 | 0.3220 | +0.5055% | +0.4046% | +0.6115% | 0.0500 |
| right_level_retest_confirm | 180 | 0.6951 | +1.0899% | +0.8280% | +1.5282% | 0.4101 |

## R 倍数路径

| model | +1R_first | +2R_first | invalidation_first | no_decision_rate | median_time_to_1R | median_time_to_invalidation |
|---|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 60.27% | 39.73% | 39.73% | 0.00% | 60 min | 285 min |
| right_level_retest_confirm | 45.00% | 31.67% | 54.44% | 0.56% | 330 min | 465 min |

## 固定时间方向收益

正值表示沿交易方向移动。96H 为回答长期对照问题而补充。

| model | 2H | 4H | 8H | 12H | 16H | 20H | 24H | 36H | 48H | 60H | 72H | 96H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | +0.1344% | +0.1505% | +0.0774% | +0.0316% | -0.0836% | -0.0600% | -0.0300% | +0.0760% | -0.1290% | -0.0977% | +0.1128% | +0.0992% |
| right_level_retest_confirm | -0.0159% | -0.0932% | -0.0480% | -0.1059% | -0.0190% | -0.0189% | -0.2031% | -0.0135% | -0.2822% | -0.3248% | -0.3081% | -0.3573% |

## MFE / MAE

| model | horizon | median_MFE_pct | median_MAE_pct | median_MFE_R | median_MAE_R |
|---|---:|---:|---:|---:|---:|
| left_level_edge_limit | 2H | +0.4793% | +0.2964% | 0.9715 | 0.5767 |
| left_level_edge_limit | 4H | +0.6321% | +0.3980% | 1.2633 | 0.8692 |
| left_level_edge_limit | 8H | +0.8514% | +0.6885% | 1.6191 | 1.3651 |
| left_level_edge_limit | 12H | +0.9806% | +0.8959% | 1.8602 | 1.8870 |
| left_level_edge_limit | 16H | +1.1089% | +1.1064% | 2.0729 | 2.3937 |
| left_level_edge_limit | 20H | +1.2499% | +1.4415% | 2.4843 | 2.8130 |
| left_level_edge_limit | 24H | +1.3660% | +1.4883% | 2.8578 | 2.9348 |
| left_level_edge_limit | 36H | +1.8959% | +1.7700% | 3.5584 | 3.6830 |
| left_level_edge_limit | 48H | +2.1930% | +2.1460% | 4.2865 | 4.2181 |
| left_level_edge_limit | 60H | +2.3633% | +2.3334% | 4.5877 | 4.5840 |
| left_level_edge_limit | 72H | +2.6159% | +2.4470% | 4.9933 | 4.8744 |
| left_level_edge_limit | 96H | +2.9631% | +2.9535% | 5.5409 | 5.9505 |
| right_level_retest_confirm | 2H | +0.3039% | +0.3732% | 0.2831 | 0.3291 |
| right_level_retest_confirm | 4H | +0.4106% | +0.5572% | 0.3794 | 0.4822 |
| right_level_retest_confirm | 8H | +0.5935% | +0.8684% | 0.5517 | 0.7699 |
| right_level_retest_confirm | 12H | +0.7844% | +0.9420% | 0.7530 | 0.8137 |
| right_level_retest_confirm | 16H | +1.0276% | +1.0693% | 0.9346 | 0.9526 |
| right_level_retest_confirm | 20H | +1.2926% | +1.2479% | 1.1712 | 1.1124 |
| right_level_retest_confirm | 24H | +1.3542% | +1.4183% | 1.1824 | 1.2790 |
| right_level_retest_confirm | 36H | +1.6858% | +1.7152% | 1.4734 | 1.6592 |
| right_level_retest_confirm | 48H | +1.8376% | +2.1276% | 1.7455 | 1.9046 |
| right_level_retest_confirm | 60H | +2.1768% | +2.3553% | 2.0246 | 2.1632 |
| right_level_retest_confirm | 72H | +2.4729% | +2.6046% | 2.3409 | 2.3257 |
| right_level_retest_confirm | 96H | +2.8555% | +2.9618% | 2.8359 | 2.7747 |

## Paired Subset 拓展

| left_model | paired | stop_pct L/R | 24H L/R | 48H L/R | 72H L/R | 96H L/R | +2R_first L/R | MFE_pct L/R | MAE_pct L/R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | 109 | +0.5053% / +1.0951% | +0.3677% / -0.3640% | -0.0945% / -0.4936% | +0.2459% / -0.3737% | +0.3405% / -0.3275% | 54.13% / 33.03% | +3.3474% / +2.8174% | +2.5874% / +3.3877% |

## Asset / Direction 简单分组

| model | group | n | +1R_first | +2R_first | invalidation_first | 48H | 72H | 96H | MFE_pct | MAE_pct |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| left_level_edge_limit | asset:BTC | 219 | 60.27% | 39.73% | 39.73% | -0.1290% | +0.1128% | +0.0992% | +2.9631% | +2.9535% |
| left_level_edge_limit | direction:long | 122 | 63.11% | 45.08% | 36.89% | -0.0976% | +0.3940% | +0.4719% | +3.3288% | +2.8246% |
| left_level_edge_limit | direction:short | 97 | 56.70% | 32.99% | 43.30% | -0.1290% | -0.1332% | -0.2991% | +2.5784% | +3.2990% |
| right_level_retest_confirm | asset:BTC | 180 | 45.00% | 31.67% | 54.44% | -0.2822% | -0.3081% | -0.3573% | +2.8555% | +2.9618% |
| right_level_retest_confirm | direction:long | 96 | 52.08% | 39.58% | 46.88% | -0.1445% | +0.6089% | +0.3351% | +3.2276% | +2.7565% |
| right_level_retest_confirm | direction:short | 84 | 36.90% | 22.62% | 63.10% | -0.3098% | -0.6619% | -0.8261% | +2.5468% | +3.6258% |

## 简短结论

1. `left_level_edge_limit` 的 +1R 优势仍有明显的小 R 几何嫌疑：其 +2R-first 为 39.73%，invalidation-first 为 39.73%，48H/72H/96H 中位方向收益分别为 -0.1290% / +0.1128% / +0.0992%。
2. 各长期窗口中位数最高模型：48H=left_level_edge_limit、72H=left_level_edge_limit、96H=left_level_edge_limit。这只是 development diagnostic，不是可交易绩效。
3. `right_level_retest_confirm` 在 48H/72H/96H 均未反超 left_level_edge_limit。
4. 当前证据只支持继续观察 left_level_edge_limit；右侧确认可停止扩展。

本次 decision：`prefer_left_limit_entry_for_next_review`。本扩展不改变策略、参数或研究阶段。
