# LR v3 Confirmation Geometry Diagnostic

## 结论

**B. 有改善但主要来自 confirmation chase，需重新定义 confirmation。**

本报告是 diagnostic-only，不是交易绩效；未生成 entry、execution 或 closed-trade evidence。

## 样本

- Eligible 1H same-bar PDH/PDL + confirmed swing events: 2,427
- v3 confirmed events: 1,358
- Geometry-complete events: 1,358
- Unique physical events: 982
- Data gaps: 0

## Confirmation Geometry

所有距离均按 reversal 方向带符号；`confirmation_to_1R` 小于等于 0 表示 confirmation close 已到达或越过原 reclaim-reference +1R。ATR15m 只使用 confirmation close 时已经确认的 14 根数据。

| Geometry | p10 | p25 | median | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| `confirmation_to_level_ATR15m` | 0.699 | 1.065 | 1.520 | 2.104 | 2.777 |
| `confirmation_to_level_ATR1H` | 0.375 | 0.596 | 0.844 | 1.211 | 1.927 |
| `confirmation_to_invalidation_ATR15m` | 1.561 | 1.970 | 2.494 | 3.105 | 3.826 |
| `confirmation_to_invalidation_diagnostic_R` | 1.057 | 1.162 | 1.311 | 1.516 | 1.888 |
| `confirmation_to_1R_ATR15m` | 0.133 | 0.691 | 1.294 | 2.005 | 2.690 |
| `confirmation_to_1R_diagnostic_R` | 0.112 | 0.484 | 0.689 | 0.838 | 0.943 |
| `confirmation_chase_proxy` | 0.128 | 0.341 | 0.576 | 0.839 | 1.252 |
| `confirmation_delay_bars` | 1.000 | 1.000 | 2.000 | 3.000 | 4.000 |
| `confirmation_delay_minutes` | 15.000 | 15.000 | 30.000 | 45.000 | 60.000 |

- Confirmation already at/beyond original +1R: 7.36%
- Median chase proxy: 0.576 ATR15m
- Median remaining distance to original +1R: 0.689 diagnostic R

## Dual-Reference Path Order

A 与 B 使用相同的 confirmation 后路径、相同 structural invalidation 和相同 240m future timestamp。A 使用 1H reclaim close/R；B 使用 15m confirmation close/R。Confirmation bar 本身不计入确认后 target 命中。

| Metric | Original eligible baseline | A: reclaim reference | B: confirmation reference |
|---|---:|---:|---:|
| Invalidation-first | 48.37% | 26.65% | 46.31% |
| +0.5R first | 65.39% | 86.60% | 66.35% |
| +1R first | 48.95% | 68.92% | 47.64% |
| No decision | 5.19% | 6.04% | 11.27% |
| 240m median R | 0.175 | 0.470 | 0.114 |

Unique-physical sensitivity:

- A invalidation-first 27.16%, +1R-first 68.84%, 240m median R 0.467。
- B invalidation-first 47.05%, +1R-first 47.45%, 240m median R 0.114。

## Yearly Breakdown

| Group | Reference | Events | Inv-first | +0.5R first | +1R first | No decision | 240m median R |
|---|---|---:|---:|---:|---:|---:|---:|
| 2020 | baseline | 1 | 0.00% | 100.00% | 100.00% | 0.00% | 0.227 |
| 2020 | A reclaim | 0 | n/a | n/a | n/a | n/a | n/a |
| 2020 | B confirmation | 0 | n/a | n/a | n/a | n/a | n/a |
| 2021 | baseline | 535 | 46.35% | 65.42% | 50.84% | 5.23% | 0.247 |
| 2021 | A reclaim | 292 | 22.14% | 86.30% | 72.26% | 7.19% | 0.432 |
| 2021 | B confirmation | 292 | 38.70% | 69.18% | 54.79% | 10.62% | 0.104 |
| 2022 | baseline | 629 | 50.67% | 65.34% | 47.06% | 4.61% | 0.104 |
| 2022 | A reclaim | 357 | 29.74% | 86.27% | 67.51% | 3.92% | 0.356 |
| 2022 | B confirmation | 357 | 51.70% | 64.15% | 43.70% | 9.52% | 0.020 |
| 2023 | baseline | 673 | 47.13% | 65.82% | 49.33% | 6.69% | 0.272 |
| 2023 | A reclaim | 398 | 27.60% | 86.68% | 66.58% | 8.04% | 0.515 |
| 2023 | B confirmation | 398 | 44.57% | 66.58% | 47.49% | 14.32% | 0.156 |
| 2024 | baseline | 589 | 49.20% | 64.86% | 48.73% | 4.07% | 0.059 |
| 2024 | A reclaim | 311 | 26.01% | 87.14% | 70.42% | 4.82% | 0.541 |
| 2024 | B confirmation | 311 | 49.29% | 65.92% | 45.66% | 9.97% | 0.128 |

## BTC/ETH Breakdown

| Group | Reference | Events | Inv-first | +0.5R first | +1R first | No decision | 240m median R |
|---|---|---:|---:|---:|---:|---:|---:|
| BTC-USDT-SWAP | baseline | 1,214 | 48.50% | 64.42% | 48.19% | 6.43% | 0.199 |
| BTC-USDT-SWAP | A reclaim | 665 | 26.62% | 86.47% | 67.97% | 7.37% | 0.450 |
| BTC-USDT-SWAP | B confirmation | 665 | 45.83% | 67.37% | 46.92% | 13.38% | 0.117 |
| ETH-USDT-SWAP | baseline | 1,213 | 48.24% | 66.36% | 49.71% | 3.96% | 0.151 |
| ETH-USDT-SWAP | A reclaim | 693 | 26.67% | 86.72% | 69.84% | 4.76% | 0.489 |
| ETH-USDT-SWAP | B confirmation | 693 | 46.74% | 65.37% | 48.34% | 9.24% | 0.110 |

## Long/Short Breakdown

| Group | Reference | Events | Inv-first | +0.5R first | +1R first | No decision | 240m median R |
|---|---|---:|---:|---:|---:|---:|---:|
| long | baseline | 1,183 | 51.13% | 63.57% | 45.82% | 6.26% | 0.151 |
| long | A reclaim | 664 | 27.64% | 86.45% | 67.02% | 7.38% | 0.439 |
| long | B confirmation | 664 | 45.21% | 67.17% | 48.19% | 12.05% | 0.102 |
| short | baseline | 1,244 | 45.81% | 67.12% | 51.93% | 4.18% | 0.207 |
| short | A reclaim | 694 | 25.72% | 86.74% | 70.75% | 4.76% | 0.523 |
| short | B confirmation | 694 | 47.34% | 65.56% | 47.12% | 10.52% | 0.142 |

## Level Breakdown

| Group | Reference | Events | Inv-first | +0.5R first | +1R first | No decision | 240m median R |
|---|---|---:|---:|---:|---:|---:|---:|
| confirmed_swing | baseline | 1,124 | 48.49% | 64.41% | 48.58% | 5.69% | 0.133 |
| confirmed_swing | A reclaim | 610 | 24.78% | 87.21% | 70.16% | 6.72% | 0.472 |
| confirmed_swing | B confirmation | 610 | 46.60% | 66.23% | 46.39% | 13.11% | 0.110 |
| previous_day_high_low | baseline | 1,303 | 48.27% | 66.23% | 49.27% | 4.76% | 0.207 |
| previous_day_high_low | A reclaim | 748 | 28.15% | 86.10% | 67.91% | 5.48% | 0.469 |
| previous_day_high_low | B confirmation | 748 | 46.07% | 66.44% | 48.66% | 9.76% | 0.117 |

PDH/PDL 与 confirmed swing 分开报告；Session H/L 未独立放行。

## 判断

A 显著改善而 B 基本回到原 eligible baseline，说明 v3 的表面 path-order 优势主要来自等待 confirmation 后，价格已经沿 reversal 方向推进、原 +1R 剩余距离缩短；当从 confirmation close 重新承担完整 structural risk 后，后续推进不足。它不是纯粹由少数已越过 +1R 的事件造成（占比仅见上方 geometry），但目前不能视为可直接交易的持续信号质量提升。

- Reclaim-reference 通过原 v3 path-order 标准: pass
- Confirmation-reference 通过相同标准: fail
- 至少 3/4 年且 BTC/ETH、long/short、level 均无明显失效: fail
- Median chase < 1 ATR15m: pass
- Median confirmation 尚未越过原 +1R: pass
- Final decision: **B**

## Data Gaps

- 既有 artifacts 仍无 first-touch 与 active-session 字段；本诊断不使用 Session H/L。
- Geometry 所需 ATR15m 与 confirmation bar 完整。

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
- source SHA-256 `anatomy_rows.jsonl`: `7a18cedc05c3dadfe8ebb0a0a60f60c8f17aad131ebdb8831965fd17cdae4c94`
- source SHA-256 `run_manifest.json`: `aca13dbf0d8e2e987ad7207b3a827772e25c79d71f4b8ea216c3d4a17cfd68c0`
