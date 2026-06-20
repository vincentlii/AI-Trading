# LR Anatomy-to-Execution Loss Review

## 结论

Anatomy 正、execution 负不是单一原因。主链路是：**上游信号路径不够干净 → 部分 entry 需追价或等回踩 → stop geometry 与 min-risk admission 大量拒绝 → 入选交易仅剩 +0.081R gross edge → 0.228R 成本将其稳定翻为 -0.147R net**。

成本是已入场交易从正 gross 翻为负 net 的直接因素，但不是根因；真正问题是 gross edge 太薄，无法承受既定成本。

## 桥接方法

Tournament v2 来源是较早的 `causal_anatomy.v4`，没有 MT `physical_event_key`。本次按以下字段匹配 MT `15m_micro` control：

`instrument + level_id + direction + sweep_time + reclaim_time`

- Tournament unique source candidates：10,085。
- MT 15m 唯一逐笔匹配：8,368，覆盖 82.97%。
- 未匹配：1,717，由 scanner 版本/语义差异造成，仅作 summary-level bridge。

## Fill 层

| Entry model | Decisions | Filled | Fill rate | Missed rate | Chase proxy med ATR | Entry delay med | Stop distance med ATR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market next open | 10,085 | 10,085 | 100.00% | 0.00% | +0.100 | 15m | 1.506 |
| Level retest limit | 10,085 | 5,446 | 54.00% | 46.00% | -0.351 | 15m | 1.256 |
| Reclaim midpoint limit | 10,085 | 6,353 | 62.99% | 37.01% | -0.207 | 15m | 1.326 |
| MSS market | 10,085 | 5,436 | 53.90% | 46.10% | +0.813 | 45m | 1.721 |
| MSS midpoint limit | 10,085 | 3,719 | 36.88% | 63.12% | +0.538 | 60m | 1.714 |

Artifact 中未成交状态名为 `missed`；表中 Missed rate 即本报告的 no-fill rate。
全部 filled decisions 的 stop distance / ATR15m 为 p10 `0.569`、median `1.477`、p90 `3.012`，说明同一上游 event pool 产生了跨度很大的 stop geometry。

Chase proxy 为沿信号方向的 `(entry - reclaim_close) / ATR15m`，long/short 已统一符号；正值为追价，负值为回踩入场。

- Market next open 基本不追价，但无质量确认。
- Retest/midpoint 节省价格，但大量 missed，且成交样本本身更容易是回到风险区的弱事件。
- MSS 提高了事后 anatomy 质量，但中位追价 0.54-0.81 ATR，同时 fill 下降。

## Stop Geometry 与 Admission

50,425 个 entry decisions 中 31,039 个先达到 fill，最终只有 11,325 个 base executions 通过 RiskEngine 与 min actual risk。拒绝 reason code 可多选：

| Reject reason | Count |
|---|---:|
| `actual_risk_after_cap_below_minimum` | 16,119 |
| `stop_distance_too_near` | 6,478 |
| `stop_distance_too_far` | 3,635 |
| `mss_not_confirmed_within_ttl` | 9,248 |
| `limit_not_filled_within_ttl` | 8,371 |
| `post_mss_limit_not_filled_within_ttl` | 1,742 |
| invalid stop geometry | 25 |

已入选 base trades 的 actual risk pct 为 p10 `0.11%`、median `0.16%`、p90 `0.29%`，98.36% 被 notional cap 限制。这说明 admission 问题很大，但它的作用是拒绝无法按风险目标部署的交易，不是造成已入选交易为负的原因。RiskEngine 与边界不应放宽。

## Gross / Cost / Net

| Entry | Base trades | Gross avg R | Cost avg R | Net avg R | Net total R | PF |
|---|---:|---:|---:|---:|---:|---:|
| Market next open | 3,882 | +0.070 | 0.232 | -0.162 | -630.09 | 0.784 |
| Level retest limit | 1,145 | +0.019 | 0.239 | -0.220 | -252.33 | 0.722 |
| Reclaim midpoint limit | 1,796 | +0.073 | 0.240 | -0.167 | -300.28 | 0.781 |
| MSS market | 2,578 | +0.109 | 0.214 | -0.105 | -270.54 | 0.851 |
| MSS midpoint limit | 1,924 | +0.112 | 0.221 | -0.109 | -209.67 | 0.847 |
| **Total** | **11,325** | **+0.081** | **0.228** | **-0.147** | **-1,662.90** | **0.802** |

PDH/PDL 的 gross avg R 最高（+0.124），但成本 0.226R 后仍为 -0.101R。Confirmed swing 和 Session H/L 的 gross 分别仅 +0.065R/+0.069R。这支持“上游事件边界过宽”，不支持“只需降成本就可盈利”。

## 逐笔桥接子集

| Entry | Joined trades | Join coverage | Anatomy 240m med R | Anatomy inv-first | Execution gross avg R | Execution net avg R |
|---|---:|---:|---:|---:|---:|---:|
| Market next open | 3,087 | 79.52% | 0.350 | 36.57% | +0.062 | -0.174 |
| Level retest limit | 655 | 57.21% | -0.072 | 60.61% | +0.002 | -0.248 |
| Reclaim midpoint limit | 1,214 | 67.59% | -0.011 | 56.74% | +0.072 | -0.178 |
| MSS market | 2,194 | 85.10% | 0.705 | 22.19% | +0.103 | -0.115 |
| MSS midpoint limit | 1,632 | 84.82% | 0.572 | 23.00% | +0.104 | -0.121 |

MSS 子集的 signal-close anatomy 明显更好，但等待确认后追价、stop 重定义和真实成本将优势压缩到约 +0.10R gross。Retest 子集则显示回踩成交本身带来 adverse selection。

## 问题定性

| 问题 | 判断 |
|---|---|
| 信号本身不够干净 | **是，根因**。全体 invalidation-first 近 50%，gross edge 太薄 |
| Entry 太追价 | **部分是**。MSS 明显；market next open 不严重 |
| Stop geometry 不匹配 | **是**。near/far stop 大量被拒，入选 stop 仍使 R 成本较高 |
| 成本吃掉 | **是，直接翻负层**。0.228R 成本 > 0.081R gross edge |
| Notional cap / min risk admission | **是，部署问题**。大量拒绝，但不是已入选 net R 为负的原因 |

结论是多者共同作用，但研究顺序必须从上游信号定义开始，不应绕过它去调 stop、cost、exit 或 sizing。
