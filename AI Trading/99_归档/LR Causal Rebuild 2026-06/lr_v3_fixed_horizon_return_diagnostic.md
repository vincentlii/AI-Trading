# LR v3 Fixed-Horizon Return Diagnostic

## 结论

**12h/24h 有弱正漂移，但 36h/48h 去重与分组不稳定；edge 更像短线冲击，不支持长持。**

本报告是 diagnostic-only forward return，不是交易绩效；不包含 stop、target、RiskEngine、成本或真实交易。

## 样本

- Eligible 1H same-bar events: 2,427
- v3 confirmed events: 1,358
- Diagnostic rows: 1,358
- Unique physical events: 982

## Overall Fixed-Horizon Return

| Horizon | Samples | Missing future bars | Mean return | Median return | Win rate |
|---|---:|---:|---:|---:|---:|
| 12h | 1,358 | 0 | +0.1299% | +0.2075% | 58.32% |
| 24h | 1,358 | 0 | +0.1496% | +0.2351% | 54.49% |
| 36h | 1,357 | 1 | +0.0667% | +0.2165% | 54.61% |
| 48h | 1,357 | 1 | +0.1387% | +0.1447% | 52.47% |

Unique-physical sensitivity:

| Horizon | Samples | Missing | Mean return | Median return | Win rate |
|---|---:|---:|---:|---:|---:|
| 12h | 982 | 0 | +0.0941% | +0.1872% | 57.33% |
| 24h | 982 | 0 | +0.0694% | +0.1756% | 53.36% |
| 36h | 981 | 1 | -0.0257% | +0.1605% | 53.52% |
| 48h | 981 | 1 | +0.0132% | +0.0884% | 51.48% |

## BTC/ETH Breakdown

| Group | Horizon | Samples | Missing | Mean return | Median return | Win rate |
|---|---|---:|---:|---:|---:|---:|
| BTC-USDT-SWAP | 12h | 665 | 0 | +0.0091% | +0.1739% | 57.29% |
| BTC-USDT-SWAP | 24h | 665 | 0 | +0.0348% | +0.1831% | 53.53% |
| BTC-USDT-SWAP | 36h | 665 | 0 | +0.0042% | +0.1222% | 53.08% |
| BTC-USDT-SWAP | 48h | 665 | 0 | +0.0012% | +0.1135% | 52.78% |
| ETH-USDT-SWAP | 12h | 693 | 0 | +0.2458% | +0.2540% | 59.31% |
| ETH-USDT-SWAP | 24h | 693 | 0 | +0.2597% | +0.3474% | 55.41% |
| ETH-USDT-SWAP | 36h | 692 | 1 | +0.1267% | +0.2632% | 56.07% |
| ETH-USDT-SWAP | 48h | 692 | 1 | +0.2708% | +0.1799% | 52.17% |

## Long/Short Breakdown

| Group | Horizon | Samples | Missing | Mean return | Median return | Win rate |
|---|---|---:|---:|---:|---:|---:|
| long | 12h | 664 | 0 | +0.1278% | +0.2374% | 59.34% |
| long | 24h | 664 | 0 | +0.2628% | +0.2965% | 55.72% |
| long | 36h | 664 | 0 | +0.3518% | +0.2288% | 55.42% |
| long | 48h | 664 | 0 | +0.4509% | +0.3120% | 54.97% |
| short | 12h | 694 | 0 | +0.1319% | +0.1869% | 57.35% |
| short | 24h | 694 | 0 | +0.0412% | +0.1696% | 53.31% |
| short | 36h | 693 | 1 | -0.2065% | +0.1965% | 53.82% |
| short | 48h | 693 | 1 | -0.1604% | +0.0140% | 50.07% |

## Yearly Breakdown

| Group | Horizon | Samples | Missing | Mean return | Median return | Win rate |
|---|---|---:|---:|---:|---:|---:|
| 2021 | 12h | 292 | 0 | +0.1370% | +0.2880% | 57.53% |
| 2021 | 24h | 292 | 0 | +0.0373% | +0.0991% | 52.40% |
| 2021 | 36h | 292 | 0 | -0.0606% | +0.1197% | 51.37% |
| 2021 | 48h | 292 | 0 | +0.7071% | +0.5537% | 54.11% |
| 2022 | 12h | 357 | 0 | +0.1804% | +0.2996% | 57.42% |
| 2022 | 24h | 357 | 0 | +0.1791% | +0.1224% | 52.10% |
| 2022 | 36h | 357 | 0 | +0.2738% | +0.3403% | 54.90% |
| 2022 | 48h | 357 | 0 | -0.0050% | +0.1083% | 50.98% |
| 2023 | 12h | 398 | 0 | +0.0871% | +0.1790% | 59.80% |
| 2023 | 24h | 398 | 0 | +0.2908% | +0.2998% | 59.80% |
| 2023 | 36h | 398 | 0 | +0.1779% | +0.2640% | 58.79% |
| 2023 | 48h | 398 | 0 | +0.1083% | +0.2047% | 55.03% |
| 2024 | 12h | 311 | 0 | +0.1201% | +0.1703% | 58.20% |
| 2024 | 24h | 311 | 0 | +0.0402% | +0.1881% | 52.41% |
| 2024 | 36h | 310 | 1 | -0.1948% | +0.0695% | 51.94% |
| 2024 | 48h | 310 | 1 | -0.1924% | -0.0183% | 49.35% |

## Level Breakdown

| Group | Horizon | Samples | Missing | Mean return | Median return | Win rate |
|---|---|---:|---:|---:|---:|---:|
| confirmed_swing | 12h | 610 | 0 | +0.1149% | +0.1713% | 58.52% |
| confirmed_swing | 24h | 610 | 0 | +0.0608% | +0.1261% | 52.95% |
| confirmed_swing | 36h | 609 | 1 | -0.0331% | +0.2210% | 54.68% |
| confirmed_swing | 48h | 609 | 1 | +0.0811% | +0.1758% | 52.55% |
| previous_day_high_low | 12h | 748 | 0 | +0.1422% | +0.2451% | 58.16% |
| previous_day_high_low | 24h | 748 | 0 | +0.2219% | +0.2998% | 55.75% |
| previous_day_high_low | 36h | 748 | 0 | +0.1479% | +0.2126% | 54.55% |
| previous_day_high_low | 48h | 748 | 0 | +0.1856% | +0.1327% | 52.41% |

PDH/PDL 与 confirmed swing 分开报告；Session H/L 未独立放行。

## 研究问题回答

1. 12h/24h/36h/48h 全体平均分别为 +0.1299%、+0.1496%、+0.0667%、+0.1387%。
2. BTC 平均分别为 +0.0091%/+0.0348%/+0.0042%/+0.0012%。
3. ETH 平均分别为 +0.2458%/+0.2597%/+0.1267%/+0.2708%。
4. 固定时间持有判断：不是只有 +1R first 好看，12h/24h 的 mean、median 与 win rate 仍为正；但去重后 36h 转负、48h 接近零，长期漂移不稳。12h/24h 有弱正漂移，但 36h/48h 去重与分组不稳定；edge 更像短线冲击，不支持长持。
5. 若短窗口为正、长窗口转负，只解释为短线冲击，不推导长持策略。
6. 若全部窗口接近零或为负，停止当前 LR 研究线；本报告不以 +1R first 作为判断依据。

## Missing Future Bars

- 12h: 0
- 24h: 0
- 36h: 1
- 48h: 1

## Audit

- status: pass
- violations: 0
- holdout accessed: false
- source scanner rerun: false
- real trades generated: 0
- stop/target/RiskEngine/cost computed: false
- formal config modified: false
- Restricted Variant B: suspended
- source SHA-256 `event_rows.jsonl`: `306c812a43a5a1852e92d16d04a1c3021a3c8ce74be4772a3cf950dc1590126e`
- source SHA-256 `run_manifest.json`: `aca13dbf0d8e2e987ad7207b3a827772e25c79d71f4b8ea216c3d4a17cfd68c0`
