# LR Path-Order Review

## 结论

当前 LR 的 median forward R 确实被路径噪声美化。全体 240m/1200m median R 为 0.096/0.120，但 1200m invalidation-first 仍为 49.59%，MFE/MAE 中位数为 1.929R/1.934R。这是双向高波动事件池，不是已经确认的干净 reversal edge。

## 口径

- `follow_through_240m`：240m 内先到 +0.5R，分母为 +0.5R/invalidation 已决定样本。
- `invalidation_first_1200m`：1200m 内 invalidation 先于 +1R，分母为 +1R/invalidation 已决定样本。
- `+0.5R first` / `+1R first`：分母为全部 events，同 bar 采用保守的 invalidation-first 顺序。
- `no decision`：1200m 内 +1R 与 invalidation 均未先决出。

## Timeframe

| Timeframe | Events | 240m med R | Follow | Inv-first | +0.5R first | +1R first | No decision | med t +0.5R | med t invalidation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15m | 10,873 | 0.195 | 64.93% | 49.66% | 64.29% | 49.37% | 1.93% | 30m | 105m |
| 1H | 8,834 | 0.115 | 67.39% | 48.94% | 65.44% | 48.34% | 5.33% | 45m | 165m |
| 4H | 6,787 | 0.008 | 69.25% | 50.41% | 63.14% | 42.99% | 13.30% | 105m | 255m |

4H follow-through 高不代表更好；其 diagnostic R 尺度更小，更容易到 0.5R，但 +1R-first 反而最低。

## Level Family

| Level | 240m med R | Follow | Inv-first | +0.5R first | +1R first | No decision |
|---|---:|---:|---:|---:|---:|---:|
| PDH/PDL | 0.134 | 68.24% | 48.27% | 65.61% | 48.52% | 6.22% |
| Confirmed swing | 0.083 | 66.09% | 49.20% | 63.71% | 47.03% | 7.43% |
| Session H/L | 0.085 | 66.29% | 50.14% | 64.16% | 47.13% | 5.47% |

PDH/PDL 是相对最一致的 level，但 invalidation-first 仍接近 48%，仍不适合直接进入正式交易研究。

## 1H Reclaim Span

| Span | 240m med R | Follow | Inv-first | +0.5R first | +1R first | No decision | med t +0.5R | med t invalidation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.142 | 65.76% | 50.02% | 64.68% | 48.00% | 3.95% | 45m | 135m |
| 2 | 0.051 | 72.55% | 46.08% | 67.53% | 49.43% | 8.32% | 90m | 255m |
| 3 | 0.077 | 75.00% | 43.99% | 68.19% | 49.13% | 12.28% | 105m | 323m |

Same-bar 的形态语义更强，但当前 path order 未胜过 delayed reclaim。这不是 delayed reclaim 的 winner 证据；二者机制不同，且 span=3 仅 635 events。

## Year / Asset / Direction

| Group | Events | 240m med R | Inv-first | +1R first | No decision |
|---|---:|---:|---:|---:|---:|
| 2021 | 6,599 | 0.099 | 48.60% | 48.84% | 4.99% |
| 2022 | 6,715 | 0.074 | 51.32% | 45.99% | 5.54% |
| 2023 | 6,746 | 0.145 | 47.68% | 48.01% | 8.23% |
| 2024 | 6,424 | 0.043 | 50.74% | 46.76% | 5.07% |
| BTC | 13,336 | 0.099 | 50.16% | 46.44% | 6.82% |
| ETH | 13,158 | 0.093 | 49.03% | 48.36% | 5.13% |
| Long | 12,882 | 0.107 | 50.99% | 45.89% | 6.35% |
| Short | 13,612 | 0.089 | 48.28% | 48.81% | 5.63% |

2022/2024、BTC、long 的 +1R-first 更弱，说明轻微正 median R 并非跨状态的强 edge。2020 仅 10 rows，不参与判断。

## VPA Bucket

| Reclaim volume percentile | Events | 240m med R | Follow | Inv-first | +1R first | No decision |
|---|---:|---:|---:|---:|---:|---:|
| q1 | 1,501 | 0.123 | 68.75% | 48.74% | 50.17% | 2.13% |
| q2 | 3,122 | 0.063 | 68.75% | 48.56% | 49.30% | 4.16% |
| q3 | 5,840 | 0.119 | 67.71% | 48.39% | 49.73% | 3.65% |
| q4 | 16,030 | 0.089 | 65.65% | 50.34% | 45.91% | 7.54% |

q4 的数量最大但 path-order 更差，极端成交量不能作为 reversal 的直接确认。

## 判断

凡是 median forward R 为正但 invalidation-first 接近或超过 50% 的组，都不适合直接进入交易研究。当前这包括整体 15m、1H same-bar、Session H/L、4H 全体以及 reclaim-volume q4。下一版信号必须将“先有利推动、再失效”作为机制验证主指标，而不是只看固定 horizon 的终点回报。
