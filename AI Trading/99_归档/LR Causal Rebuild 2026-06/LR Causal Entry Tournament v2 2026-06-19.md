# LR Causal Entry Tournament v2

## 结论

完整 development Entry Tournament v2 未产生可接受 winner。五种预注册入场在整体 base、stress、harsh 成本下均为负期望；不得进入退出优化、动态缩仓、组合层或 holdout。

Restricted Variant B 的历史 183 笔结果继续仅作追溯材料，不再作为可信绩效基线或正式研究候选。

## 研究边界

- development：`2020-12-31` 至 `2024-11-30`。
- holdout：自 `2024-12-01` 起继续封存，本轮未访问。
- 来源：`causal_anatomy.v4`，ATR 使用 sweep bar close 时点。
- 五种入场：`market_next_open`、`level_retest_limit`、`reclaim_midpoint_limit`、`mss_market`、`mss_midpoint_limit`。
- 固定边界：`4` bar entry TTL、`80` bar holding、`2R` target、RiskEngine、notional cap、base/stress/harsh 成本。
- 全部交易属于 proposal-only variant evidence；正式 `closed_trade_rows.jsonl` 保持为空。

## 漏斗

- 来源候选：`10,088`。
- development 尾部保护后候选：`10,085`；`3` 个因 `insufficient_development_tail` 拒绝。
- 入场决策：`50,425`。
- 入场模型成交：`31,039`。
- RiskEngine 与最小实际风险约束后独立 execution：`11,325`。
- 三档成本 closed-trade rows：`33,975`。

主要拒绝原因：

- 仅 `actual_risk_after_cap_below_minimum`：`9,601`。
- `stop_distance_too_near + actual_risk_after_cap_below_minimum`：`6,159`。
- 仅 `stop_distance_too_far`：`3,276`。
- 仅 `stop_distance_too_near`：`319`。
- `stop_distance_too_far + actual_risk_after_cap_below_minimum`：`359`。

因此本轮绩效只回答“在正式 stop 边界、notional cap 与最小实际风险约束下，哪种入场更好”，不能单独证明所有 causal sweep/reclaim 信号都没有 edge。下一阶段需要把信号质量与 sizing/admission 影响分开归因。

## 整体结果

| 入场 | Base trades | Base avg R | Base PF | Stress avg R | Harsh avg R |
|---|---:|---:|---:|---:|---:|
| `market_next_open` | 3,882 | -0.1623 | 0.7835 | -0.2203 | -0.3169 |
| `level_retest_limit` | 1,145 | -0.2204 | 0.7222 | -0.2802 | -0.3799 |
| `reclaim_midpoint_limit` | 1,796 | -0.1672 | 0.7809 | -0.2271 | -0.3270 |
| `mss_market` | 2,578 | -0.1049 | 0.8511 | -0.1583 | -0.2473 |
| `mss_midpoint_limit` | 1,924 | -0.1090 | 0.8474 | -0.1642 | -0.2564 |

最接近持平的局部分组是 `previous_day_high_low + mss_midpoint_limit`：base `414` 笔、avg `+0.00284R`、PF `1.0043`；stress 降为 `-0.05089R`、PF `0.9268`，harsh 降为 `-0.14045R`、PF `0.8113`。该分组还存在明显年度不稳定：2021、2022 为负，2023、2024 为正，因此不能选为 winner。

## 审计

- Artifact SHA-256 mismatch：`0`。
- 时间链、lineage、holdout 越界、bar confirmation、no-lookahead 违规：`0`。
- `11,325` 个 execution 均有且仅有三档成本行。
- 45 个 variant/family/cost 汇总组均可由逐笔 closed-trade rows 复算。
- 相关测试：`30/30` 通过。
- Audit 状态：`not_run_no_selected_variant`；没有 winner 时不得把 variant rows 提升为正式 evidence。

## 决策与下一步

Entry Tournament 到此停止，不继续围绕五种入场做局部调参，也不进入退出和仓位优化。下一阶段回到 signal quality attribution：使用预注册、粗粒度、可解释特征分析哪些 sweep/reclaim 条件具有跨年度和 stress 成本稳定性；先做 diagnostic-only 分层与 walk-forward，不直接生成新质量门或正式配置。

若 signal quality attribution 仍不能找到跨年度、stress 成本为正且样本充分的稳定区域，则停止 LR Causal Rebuild，不访问 holdout。
