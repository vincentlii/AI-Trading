---
type: research-report
status: diagnostic-complete
updated: 2026-06-20
tags:
  - strategy/liquidity-reversal
  - research/causal
  - research/vpa
---

# LR Multi-Timeframe + VPA Causal Event Research

## 结论

完整 development 运行与因果审计通过，但本阶段不是交易绩效，也不选择正式 winner。

15m control 的事件后方向性最强且 2021-2024 跨年为正；1H sweep/reclaim 次之，语义更干净，也具备跨年稳定性；4H wick-reclaim 整体在 240m 接近零，不支持直接进入 execution research。

下一步优先进行 development-only、预注册的 event stratification validation：并行保留 15m control 与 1H event，重点验证 level family、1H reclaim span 和非线性 VPA 分层。4H 仅保留诊断分支。暂不进入 entry tournament、structural MSS、exit、sizing 或 holdout。

## lr_multitimeframe_event_scanner_report

运行目录：`storage/research_runs/liquidity_reversal/multitimeframe_vpa_v1/multitimeframe_events_development_2020-12-31_2024-11-30`

- event-level：26,494。
- unique physical events：20,147。
- 跨 level family 重复 event-level：6,347；同一 physical event 的 anatomy 与 VPA 特征冲突数均为 0。
- 15m unique：8,530；1H unique：6,733；4H unique：4,884。
- BTC/ETH、long/short 均有充足样本，未发现单资产或单方向垄断结论。

| Event timeframe | Unique events | 240m median R | 240m median ATR | 1200m median R | 2021-2024 的 240m 正年份 |
|---|---:|---:|---:|---:|---:|
| 15m control | 8,530 | 0.180 | 0.273 | 0.142 | 4/4 |
| 1H sweep/reclaim | 6,733 | 0.097 | 0.099 | 0.072 | 4/4 |
| 4H wick-reclaim | 4,884 | -0.005 | -0.003 | 0.014 | 1/4 |

ATR-normalized return 与 diagnostic R 排名一致，周期比较不是主要由 R 分母差异造成。

1H reclaim span 不是等价事件：同根、第二根、第三根 reclaim 的 240m median R 分别为 0.119、0.050、0.028；后续研究必须把 span 当作预注册 attribution，不得继续无差别合并。

## lr_vpa_attribution_report

VPA 具有区分能力，但关系明显非单调，不支持“volume 越高越好”的串行 gate。

- 15m reclaim range normal 的 240m median R/ATR 为 0.296/0.370，high 为 0.146/0.247。
- 1H sweep range normal 为 0.220R/0.172ATR，low 为 -0.016R/-0.010ATR，high 为 0.073R/0.095ATR。
- 1H reclaim relative volume normal 为 0.168R/0.152ATR，high 为 0.062R/0.075ATR。
- 4H close-location q1 为 0.274R/0.075ATR，q4 为 -0.058R/-0.062ATR；方向在 ATR 单位下仍一致，但 q1 的 R 较小，不能只看 R 倍数。

上述主要分层在多个年份重复，但部分指标的 forward R、follow-through 和 invalidation-first 指向不一致。VPA 当前适合做 attribution 或预注册分桶比较，不适合直接转成单阈值 quality gate，也不适合从本轮数据拟合权重分数。

post-signal volume 继续只属于 diagnostic label，不得进入 feature 或 gate。

## lr_event_timeframe_anatomy_report

- 15m：MFE/MAE median 为 2.704R/2.832R，事件后存在方向性，但路径噪声和双向波动都很大。
- 1H：MFE/MAE median 为 1.938R/2.053R，方向性较弱，但跨年、资产和方向较稳定。
- 4H：MFE/MAE median 为 1.253R/1.337R，240m 几乎无方向性。
- 4H follow-through rate 较高不能直接解释为更优，因为其 median `R_size/ATR=0.662`，明显小于 15m 的 1.372，更容易触及 0.5R。

Level family 证据：

| Timeframe | Level family | Events | 240m median R | 2021-2024 正年份 | 判断 |
|---|---|---:|---:|---:|---|
| 15m | PDH/PDL | 2,255 | 0.232 | 4/4 | 优先保留 |
| 15m | Session H/L | 6,574 | 0.204 | 4/4 | 保留作宽基线 |
| 15m | Confirmed swing | 2,044 | 0.121 | 4/4 | 保留 |
| 1H | PDH/PDL | 1,755 | 0.170 | 4/4 | 优先保留 |
| 1H | Confirmed swing | 1,553 | 0.107 | 4/4 | 优先保留 |
| 1H | Session H/L | 5,526 | 0.097 | 4/4 | 保留作对照 |
| 4H | PDH/PDL | 1,378 | 0.041 | 3/4 | 仅诊断 |
| 4H | Confirmed swing | 1,179 | 0.030 | 2/4 | 仅诊断 |
| 4H | Session H/L | 4,230 | -0.013 | 1/4 | 暂停推进 |

PDH/PDL 是三周期中最稳定的 level family；confirmed swing 在 15m/1H 可继续研究；4H Session H/L 缺少稳定方向性。

## lr_event_causality_audit_report

- causality audit：pass，0 violation。
- event/feature/anatomy 数量：26,494/26,494/26,494。
- diagnostic labels：52,988。
- `holdout_accessed=false`。
- artifact index：16 个 records，0 missing、0 hash mismatch，required artifacts 全部被索引。
- deterministic reserialization：pass。
- `closed_trade_rows` 与 `execution_rows` 为空。
- Full Audit 状态正确为 `not_run_no_closed_trade_unverifiable`；本报告不得解释为可交易收益或 formal evidence。
- RiskEngine、成本和正式配置未修改；Restricted Variant B 继续 suspended。

## lr_research_direction_recommendation

### 研究问题 1：15m / 1H / 4H 哪个更像真实 LR？

15m 的事件后方向性证据最强，1H 的定义更干净且跨年稳定，二者都值得继续；4H 整体证据不足。这里没有硬 winner，因为尚未验证真实 entry、stop、fill、成本与 RiskEngine。

### 研究问题 2：15m 失败更像周期过低、信号太宽，还是缺少量价确认？

当前证据不支持“15m 周期过低导致上游信号完全失效”。15m event anatomy 明显为正，之前 Entry Tournament 的失败更可能来自宽事件池叠加 entry/stop/cost 不匹配。VPA 缺失是次要因素，因为 VPA 能分层但不是单调解释变量。

### 研究问题 3：VPA 能否区分高低质量事件？

能部分区分，尤其是 1H normal range expansion 与 4H close-location；但关系非单调、不同标签间有冲突。目前只能做分层验证，不能直接做加权分数或硬门控。

### 研究问题 4：哪些 level family 值得继续？

第一优先级是 PDH/PDL；第二优先级是 1H/15m confirmed swing；Session H/L 保留为宽基线，其中 4H Session H/L 暂停。

### 研究问题 5：下一步优先研究什么？

优先做 1H event + 15m execution 的前置 event validation，同时保留 15m control 作比较。先验证 1H same-bar reclaim、PDH/PDL/confirmed swing 与固定 VPA 分层；暂不优先 4H wick execution，也不立即恢复 structural MSS。

### 研究问题 6：推荐方向与依据

推荐下一阶段为 `LR Pre-Registered Event Stratification Validation`：

1. development 内按年份做滚动验证，不读取 holdout。
2. 保留 15m control；1H 分离 span=1 与 span=2/3，禁止事后合并美化。
3. level family 预注册为 PDH/PDL、confirmed swing、Session H/L control。
4. VPA 只使用本轮固定 bins，重点验证 normal/moderate 与 extreme 的非线性，不优化 threshold 或权重。
5. 只有在跨年、BTC/ETH、long/short 同向稳定后，才进入真实 15m execution tournament。
6. 若分层优势不能跨年重复，暂停 LR causal rebuild；不得继续局部调参。

本阶段决策标签：`diagnostic evidence supports bounded continuation`。
