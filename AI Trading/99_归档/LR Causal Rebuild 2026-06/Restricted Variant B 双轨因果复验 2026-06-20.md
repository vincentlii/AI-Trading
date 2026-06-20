---
type: research-report
status: completed-negative
updated: 2026-06-20
tags:
  - strategy/liquidity-reversal
  - research/causal
  - audit/full-audit
---

# Restricted Variant B 双轨因果复验

## 结论

两条轨道的 Full Audit 均通过，但在 development 数据上均为负期望，不能恢复 Restricted Variant B，也不能进入 holdout。

- `historical_causal_repair` 证明旧 183 笔高收益结论不可迁移到正确回测语义。修复后有 5,078 笔 base closed trade，`total_net_R=-356.64`、`PF=0.722`，所有 setup、资产、方向和年份均未达到正净期望。
- `rebuilt_1h_15m` 的事件质量优于旧定义，但仍不足以覆盖真实成本。223 笔 base closed trade，`total_net_R=-23.26`、`PF=0.724`；gross 为 `+16.23R`，base 成本拖累 `39.49R`。
- 不选择 hard winner。`session_hl_attempt4_fixed_current` 在 rebuilt 轨道为 `+2.30R`，但只有 13 笔，去掉前两笔后平均值转负，不具备研究结论强度。
- Restricted Variant B 继续 `suspended`；holdout 保持封存。

## 运行与审计

- development：`2020-12-31` 至 `2024-11-30`
- 标的：BTC/ETH SWAP，C profile
- 成本：base / stress / harsh
- 性能来源：仅 `row_type=closed_trade`
- 两轨 Full Audit：`pass`，`primary_decision=B`，blocking issue 为 0
- no-lookahead 的 9 项时间与确认检查全部通过
- metric recompute 全部匹配，artifact hash 无 blocking mismatch
- audit warnings 为项目级静态 code review 与 metadata 完整性提醒，不改变本次指标；不是盈利门槛通过证明

## 总体证据

| Track | Candidates | Base closed | Win rate | Median R | Avg R | Total R | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| historical causal repair | 5,209 | 5,078 | 45.51% | -0.048 | -0.070 | -356.64 | 0.722 | 393.66R |
| rebuilt 1H+15m | 1,363 | 223 | 54.71% | +0.024 | -0.104 | -23.26 | 0.724 | 31.79R |

| Track | Base total R | Stress total R | Harsh total R |
|---|---:|---:|---:|
| historical causal repair | -356.64 | -469.10 | -656.54 |
| rebuilt 1H+15m | -23.26 | -33.13 | -49.58 |

## Gross Edge 与成本

| Track / setup | Gross R | Gross avg R | Gross PF | Base net R | Cost drag |
|---|---:|---:|---:|---:|---:|
| historical ALL | +93.22 | +0.018 | 1.088 | -356.64 | 449.86R |
| historical session attempt 3 | +88.93 | +0.026 | 1.131 | -249.47 | 338.39R |
| rebuilt ALL | +16.23 | +0.073 | 1.233 | -23.26 | 39.49R |
| rebuilt session attempt 3 MSS | +16.90 | +0.095 | 1.318 | -16.31 | 33.21R |
| rebuilt recent swing attempt 4 | -3.70 | -0.116 | 0.678 | -9.25 | 5.55R |

旧定义只有很薄的 gross edge，远低于 base 成本。重建后的 Session H/L + MSS 有较明显 gross 改善，但平均成本约 `0.187R/笔`，仍高于 `0.095 gross R/笔`。不能通过放宽成本模型解决，必须提升事件和入场的可交易 edge。

## Setup 分解

| Track / setup | Closed | Avg R | Total R | PF | 结论 |
|---|---:|---:|---:|---:|---|
| historical session attempt 4 fixed | 752 | -0.038 | -28.56 | 0.877 | 最接近盈亏平衡，但仍负 |
| historical recent swing attempt 4 | 845 | -0.093 | -78.62 | 0.612 | gross 与 net 均负 |
| historical session attempt 3 | 3,481 | -0.072 | -249.47 | 0.706 | 交易过宽，成本拖累大 |
| rebuilt session attempt 4 fixed | 13 | +0.177 | +2.30 | 1.438 | 样本过小，不可选 winner |
| rebuilt recent swing attempt 4 | 32 | -0.289 | -9.25 | 0.351 | 明确失败 |
| rebuilt session attempt 3 MSS | 178 | -0.092 | -16.31 | 0.748 | 有 gross edge，但净值失败 |

## 年度稳定性

| Year | Historical total R | Rebuilt total R |
|---|---:|---:|
| 2021 | -9.10 | -5.13 |
| 2022 | -123.57 | -5.95 |
| 2023 | -166.07 | -4.73 |
| 2024 | -57.90 | -7.44 |

两轨每个完整年份都为负，因此不是单一年份或少数极端交易造成。去掉最大一笔或前两笔后，平均 R 进一步下降，也不存在“少数赢家掩盖整体失败”的相反误判。

## 入场、退出与风控归因

Historical 轨道的主要损失来自 2,337 笔 `lr_momentum_deadline`，合计 `-520.82R`；整体 time-cut rate 为 61.19%。动态保护的 1,208 笔 `lr_protective_stop` 合计 `+172.52R`，说明动态缩仓/保护有减损价值，但无法修复上游信号质量。

Rebuilt 轨道有 105 笔 protective stop，仅贡献 `+6.53R`；67 笔完整 stop loss 损失 `-79.01R`，28 笔 target 收益 `+51.11R`。胜率虽然为 54.71%，但平均盈利仅 `+0.500R`，平均亏损为 `-0.834R`，收益分布仍为负偏斜。

Rebuilt 候选到成交的转换率：

- Session attempt 4 fixed：782 -> 13，1.66%
- Recent swing attempt 4：108 -> 32，29.63%
- Session attempt 3 MSS：473 -> 178，37.63%

主要拒绝包含 `stop_distance_too_far` 782 次、`notional_cap_exceeded` 678 次。这里反映 1H parent sweep stop 与 15m entry 的几何距离经常不适合当前 RiskEngine，不应通过放宽 stop/notional/risk 边界解决。

## 决策

1. Track A 停止继续优化。它已完成“旧 Variant B 在正确语义下是否仍成立”的回答，结论是否定的。
2. Track B 不进入 holdout，不进行 sizing 放宽，不从 13 笔正收益 setup 中选择 winner。
3. 可继续研究的唯一上游方向是 `1H Session H/L event + 15m structural MSS`，但身份仍是 diagnostic hypothesis。
4. 下一步先研究 causal cost-to-risk geometry、VPA attribution 和更严格的 event/entry alignment，目标是提高 gross edge 并降低每笔 cost R；在 development 内不能达到跨年 base/stress 正期望则停止 LR causal rebuild。

## Artifact

`storage/research_runs/liquidity_reversal/restricted_variant_b_causal_retest_v1/development_2020-12-31_2024-11-30`
