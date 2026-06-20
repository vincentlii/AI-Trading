# LR VPA Effort-Result Review

## 结论

VPA 有弱到中等的真伪识别价值，但不是单调 quality gate。当前最稳定的观察是：**normal/elevated effort 往往好于 extreme effort，extreme volume/range 不等于更强 reversal**。VPA 可以进入下一个最小验证作为预注册 attribution，尚不能形成分数、权重或正式门槛。

## 固定分桶

本次沿用已实现的 causal bins，没有按全样本结果调阈值：

- Relative volume / range expansion：`low < 0.8`，`normal 0.8-1.2`，`elevated 1.2-1.5`，`high >= 1.5`。
- Volume percentile：既有 causal `q1-q4`，只用 signal_time 前的分布。
- Post-signal volume 仍是 `diagnostic_label`，禁止进入 feature 或 gate。

## Reclaim Volume

| Relative volume | Events | 240m median R | 1200m median R | Follow 240m | Invalidation-first | 1R first |
|---|---:|---:|---:|---:|---:|---:|
| Low | 2,451 | 0.088 | -0.002 | 68.19% | 48.52% | 49.61% |
| Normal | 4,014 | 0.110 | 0.171 | 68.96% | 48.66% | 49.15% |
| Elevated | 2,739 | 0.114 | 0.073 | 70.43% | 47.76% | 49.87% |
| High | 17,286 | 0.090 | 0.130 | 65.32% | 50.26% | 46.29% |

High volume 占样本约 65%，但 follow-through 更低、invalidation-first 更高。这符合 effort-result 解释：极端成交量可能是吸收，也可能是趋势延续、恐慌或已完成的价格迁移，单看 effort 无法确认 reversal result。

Percentile buckets 也不单调：reclaim `q3` 的 1200m median R 为 0.184，`q4` 为 0.111；`q4` 的 1R-first 仅 45.91%。因此不存在“只放行最高量分位”的依据。

## Reclaim Range

| Range expansion | Events | 240m median R | 1200m median R | Follow 240m | Invalidation-first | No decision |
|---|---:|---:|---:|---:|---:|---:|
| Low | 2,378 | 0.037 | -0.007 | 67.11% | 50.45% | 2.40% |
| Normal | 5,388 | 0.136 | 0.094 | 68.28% | 48.97% | 2.75% |
| Elevated | 4,033 | 0.108 | 0.203 | 68.37% | 47.72% | 3.92% |
| High | 14,691 | 0.087 | 0.120 | 65.46% | 50.22% | 8.31% |

Low range 更像无足够 result 的弱 reclaim；normal/elevated 有更合理的 effort-result 平衡；high range 可能已经走完一部分反转，也可能只是高波动趋势 bar，其 no-decision 明显更高。

## 分周期解释

- **15m**：normal reclaim volume 的 1200m median R 为 0.399，elevated 的 invalidation-first 降到 45.05%；但 high volume 占 8,791/10,873，且路径更差。这说明 15m 事件池被极端短周期波动主导。
- **1H**：normal/elevated reclaim volume 的 follow-through 约 70%，high 仅 66.08%；normal/low 的 1R-first 约 53%，high 为 46.27%。这是 VPA 最值得继续验证的周期，但仍非单调。
- **4H**：high reclaim volume 的 240m median R 为 -0.018，no-decision 22.41%；normal 仅轻微好转。量价不能弥补 4H close 确认过晚。

## 候选角色

| Feature | 下一步角色 | 原因 |
|---|---|---|
| Reclaim relative volume | 固定 bins 的 attribution | normal/elevated 相对可重复，但不单调 |
| Reclaim range expansion | 固定 bins 的 attribution | low 缺 result，high 可能过度/追价 |
| Sweep relative volume/range | diagnostic covariate | 差异小，无独立 gate 证据 |
| Wick ratio / CLV | 继续机制诊断 | 需按 direction/timeframe 解释，不能全局统一阈值 |
| Follow-through volume / post-reclaim expansion | diagnostic label only | 含 signal_time 之后信息，不可交易 |

本次不拟合权重、不生成 score、不从全样本反推阈值。
