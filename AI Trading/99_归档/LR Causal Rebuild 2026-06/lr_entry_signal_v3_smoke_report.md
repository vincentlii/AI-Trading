# LR Entry Signal v3 Smoke Report

## 结论

**Decision A：明显改善：可以进入一个很小的真实 execution feasibility smoke。**

本报告是 diagnostic-only 机制验证，不是交易绩效；未生成 entry、execution 或 closed-trade evidence。

## 样本漏斗

| Metric | Count |
|---|---:|
| Eligible 1H same-bar events | 2,427 |
| Structural confirmations | 1,358 |
| Unique confirmed physical events | 982 |
| Failed before confirmation | 510 |
| No confirmation within 4 bars | 559 |

## 主结果

| Metric | Supplied baseline | Matched eligible baseline | v3 confirmed | Pass threshold |
|---|---:|---:|---:|---:|
| Invalidation-first | 50.02% | 48.37% | 26.65% | <=45% |
| +1R first | 48.00% | 48.95% | 68.92% | >=52% |
| 240m median structural R | 0.142 | 0.175 | 0.471 | diagnostic |
| +0.5R first | - | - | 86.60% | diagnostic |
| No decision | - | - | 6.04% | diagnostic |

Median time-to-confirmation: 30m; median time-to-0.5R: 60m; median time-to-invalidation: 345m。
Path outcomes 从确认后的下一根 15m bar 开始；confirmation bar 不同时计为确认后的目标命中。Invalidation-first 分母为 +1R/invalidation 已决样本，其余 first/no-decision 指标分母为全部 confirmed events。
Unique-physical sensitivity：invalidation-first 27.16%，+1R-first 68.84%，+0.5R-first 86.56%，no-decision 5.50%；最终 gate 使用 event-level 与 unique-physical 两者中更保守的数值。

## Yearly Breakdown

| Group | Baseline events | Confirmed unique | Baseline inv-first | v3 inv-first | Baseline +1R | v3 +1R | Improved |
|---|---:|---:|---:|---:|---:|---:|---|
| 2020 | 1 | 0 | 0.00% | n/a | 100.00% | n/a | no |
| 2021 | 535 | 219 | 46.35% | 22.14% | 50.84% | 72.26% | yes |
| 2022 | 629 | 258 | 50.67% | 29.74% | 47.06% | 67.51% | yes |
| 2023 | 673 | 275 | 47.13% | 27.60% | 49.33% | 66.58% | yes |
| 2024 | 589 | 230 | 49.20% | 26.01% | 48.73% | 70.42% | yes |

改善年份：4/4；各年 unique confirmed physical events：2021=219, 2022=258, 2023=275, 2024=230。

## BTC/ETH Breakdown

| Group | Baseline events | Confirmed unique | Baseline inv-first | v3 inv-first | Baseline +1R | v3 +1R | Improved |
|---|---:|---:|---:|---:|---:|---:|---|
| BTC-USDT-SWAP | 1,214 | 483 | 48.50% | 26.62% | 48.19% | 67.97% | yes |
| ETH-USDT-SWAP | 1,213 | 499 | 48.24% | 26.67% | 49.71% | 69.84% | yes |

## Long/Short Breakdown

| Group | Baseline events | Confirmed unique | Baseline inv-first | v3 inv-first | Baseline +1R | v3 +1R | Improved |
|---|---:|---:|---:|---:|---:|---:|---|
| long | 1,183 | 470 | 51.13% | 27.64% | 45.82% | 67.02% | yes |
| short | 1,244 | 512 | 45.81% | 25.72% | 51.93% | 70.75% | yes |

Material subgroup failures: none。定义为 unique confirmed <50、invalidation-first 比 matched baseline 恶化 >2pp，或 +1R-first 恶化 >2pp。

## Level Breakdown

| Group | Baseline events | Confirmed unique | Baseline inv-first | v3 inv-first | Baseline +1R | v3 +1R | Improved |
|---|---:|---:|---:|---:|---:|---:|---|
| confirmed_swing | 1,124 | 610 | 48.49% | 24.78% | 48.58% | 70.16% | yes |
| previous_day_high_low | 1,303 | 748 | 48.27% | 28.15% | 49.27% | 67.91% | yes |

PDH/PDL 与 confirmed swing 分开报告；Session H/L 未独立放行。

## VPA Attribution

Fixed bins 只作 attribution，不过滤、不打分、不调阈值。

| Feature | Bucket | Confirmed | Inv-first | +1R first | No decision |
|---|---|---:|---:|---:|---:|
| `close_location_value` | `q1` | 79 | 2.53% | 97.47% | 0.00% |
| `close_location_value` | `q2` | 418 | 23.43% | 75.84% | 0.96% |
| `close_location_value` | `q3` | 429 | 25.57% | 68.53% | 7.93% |
| `close_location_value` | `q4` | 432 | 36.08% | 57.41% | 10.19% |
| `combined_volume_ratio` | `elevated_1.2_1.5` | 102 | 24.51% | 75.49% | 0.00% |
| `combined_volume_ratio` | `high_ge_1.5` | 1,164 | 26.89% | 67.96% | 7.04% |
| `combined_volume_ratio` | `low_lt_0.8` | 9 | 22.22% | 77.78% | 0.00% |
| `combined_volume_ratio` | `normal_0.8_1.2` | 83 | 26.51% | 73.49% | 0.00% |
| `reclaim_range_expansion` | `elevated_1.2_1.5` | 218 | 30.73% | 69.27% | 0.00% |
| `reclaim_range_expansion` | `high_ge_1.5` | 1,008 | 26.24% | 67.76% | 8.13% |
| `reclaim_range_expansion` | `low_lt_0.8` | 9 | 11.11% | 88.89% | 0.00% |
| `reclaim_range_expansion` | `normal_0.8_1.2` | 123 | 23.58% | 76.42% | 0.00% |
| `reclaim_relative_volume` | `elevated_1.2_1.5` | 102 | 24.51% | 75.49% | 0.00% |
| `reclaim_relative_volume` | `high_ge_1.5` | 1,164 | 26.89% | 67.96% | 7.04% |
| `reclaim_relative_volume` | `low_lt_0.8` | 9 | 22.22% | 77.78% | 0.00% |
| `reclaim_relative_volume` | `normal_0.8_1.2` | 83 | 26.51% | 73.49% | 0.00% |
| `sweep_range_expansion` | `elevated_1.2_1.5` | 218 | 30.73% | 69.27% | 0.00% |
| `sweep_range_expansion` | `high_ge_1.5` | 1,008 | 26.24% | 67.76% | 8.13% |
| `sweep_range_expansion` | `low_lt_0.8` | 9 | 11.11% | 88.89% | 0.00% |
| `sweep_range_expansion` | `normal_0.8_1.2` | 123 | 23.58% | 76.42% | 0.00% |
| `sweep_relative_volume` | `elevated_1.2_1.5` | 102 | 24.51% | 75.49% | 0.00% |
| `sweep_relative_volume` | `high_ge_1.5` | 1,164 | 26.89% | 67.96% | 7.04% |
| `sweep_relative_volume` | `low_lt_0.8` | 9 | 22.22% | 77.78% | 0.00% |
| `sweep_relative_volume` | `normal_0.8_1.2` | 83 | 26.51% | 73.49% | 0.00% |
| `wick_ratio` | `q1` | 98 | 11.34% | 87.76% | 1.02% |
| `wick_ratio` | `q2` | 533 | 24.27% | 72.61% | 4.13% |
| `wick_ratio` | `q3` | 562 | 28.65% | 66.01% | 7.47% |
| `wick_ratio` | `q4` | 165 | 37.84% | 55.76% | 10.30% |

## Data Gaps

- 既有 artifacts 没有 first-touch 与 active-session 字段；Session H/L 只能作为未使用的背景缺口记录。
- v3 不生成 Session H/L confluence 结论，避免用缺失字段做事后代理。
- `missing_confirmed_post_signal_bars`: 1 events。
- `missing_previous_confirmed_bar`: 1 events。

## Audit

- status: pass
- violations: 0
- holdout accessed: false
- source scanner rerun: false
- Entry Tournament run: false
- performance rows generated: 0
- RiskEngine/cost/stop/notional/formal config modified: false
- Restricted Variant B: suspended
- source SHA-256 `event_rows.jsonl`: `306c812a43a5a1852e92d16d04a1c3021a3c8ce74be4772a3cf950dc1590126e`
- source SHA-256 `vpa_feature_rows.jsonl`: `9f633b70c270df11c0eea5bf3d34255b52edde3fd0c698561833bb132c6db5fa`
- source SHA-256 `anatomy_rows.jsonl`: `7a18cedc05c3dadfe8ebb0a0a60f60c8f17aad131ebdb8831965fd17cdae4c94`
- source SHA-256 `run_manifest.json`: `aca13dbf0d8e2e987ad7207b3a827772e25c79d71f4b8ea216c3d4a17cfd68c0`

## Gate Decision

- Event-level and unique-physical invalidation-first <=45%: pass
- Event-level and unique-physical +1R-first >=52%: pass
- At least 3/4 years improved: pass
- BTC/ETH and long/short no material unilateral failure: pass
- Unique confirmed events >=300 and every year >=50: pass
- Final decision: **A**
