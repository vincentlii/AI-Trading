# TC BP Entry Model Quick Compare

## 实验范围

- Development window: `2024-07-01` 至 `2024-11-30`。
- BTC-USDT-SWAP / ETH-USDT-SWAP；4H structure + 15m entry diagnostic。
- Raw OHLCV only；holdout 未读取；RiskEngine、正式 execution/config、exit/sizing/cost 均未修改。
- 同一 physical breakout/direction 只保留 breakout close 距 level edge 最近的 causal confirmed level；四个 entry model 共用同一事件池。

## 公共 True Breakout

- true_breakout_event_count: 173
- acceptance-reference 4H / 12H / 24H median signed return: +0.0323% / +0.1765% / +0.3009%

| group | events | median_4H | median_12H | median_24H |
|---|---:|---:|---:|---:|
| asset:BTC-USDT-SWAP | 94 | -0.1228% | +0.0003% | -0.1239% |
| asset:ETH-USDT-SWAP | 79 | +0.1591% | +0.2592% | +0.6634% |
| direction:long | 99 | -0.0901% | +0.1907% | +0.4913% |
| direction:short | 74 | +0.1304% | +0.0895% | -0.0453% |

## 左侧 vs 右侧

| model | events | triggered | trigger_rate | +1R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| left_level_edge_limit | 173 | 85 | 49.13% | 60.00% | 40.00% | 0.0500 | +0.1915% | +0.2297% | limit_expired_32_bars |
| left_breakout_mid_limit | 173 | 113 | 65.32% | 48.60% | 46.73% | 0.2845 | +0.0694% | -0.1444% | limit_expired_32_bars |
| left_impulse_382_limit | 173 | 145 | 83.82% | 44.14% | 50.34% | 0.6361 | -0.3401% | -0.2788% | pre_fill_extension_too_far |
| right_level_retest_confirm | 173 | 56 | 32.37% | 51.79% | 42.86% | 0.5080 | -0.1344% | +0.2531% | no_valid_level_retest |

## Paired Subset

| left_model | paired_count | left_better_price_rate | left_avg_entry_improvement_ATR | left/right +1R_first | left/right invalidation_first |
|---|---:|---:|---:|---:|---:|
| left_level_edge_limit | 33 | 100.00% | 0.4594 | 72.73% / 45.45% | 27.27% / 48.48% |
| left_breakout_mid_limit | 41 | 68.29% | 0.2111 | 48.78% / 48.78% | 41.46% / 46.34% |
| left_impulse_382_limit | 50 | 44.00% | -0.0094 | 48.00% / 50.00% | 42.00% / 44.00% |

## Decision

`inconclusive_need_more_development_scan`

本报告仅为 entry diagnostic；future return/path-order 未进入任何 feature 或触发条件。
