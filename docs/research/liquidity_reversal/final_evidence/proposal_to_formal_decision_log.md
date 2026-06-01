# Proposal To Formal Decision Log

## 结论

Restricted Variant B 正式化为 LR 的当前研究候选配置。正式化不等于实盘启用；`live_trading_enabled=false` 仍保持。

## 为什么正式化 Restricted Variant B

Restricted Variant B 在 clean rebuild、full-audit、PR11H robustness 与 PR11H-fix exposure restriction 后仍保持正收益与 PF>1：

- closed = 183
- total_R = 85.070
- PF = 7.80
- portfolio_heat_max = 0.05
- liquidation_event_count = 0
- duplicate_event_count = 0

相比 unrestricted Variant B，它牺牲部分 total_R，但将 max concurrent 从 22 降到 10，same-direction overlap 从 558 降到 303，portfolio heat 从 0.11 降到 0.05。

## 为什么保留 Variant A 作为 baseline

Variant A Tier 1 only 质量高，PF=17.62，total_R=73.222，但 max_concurrent_positions=21、portfolio_heat=0.105，组合覆盖低于 Restricted Variant B。它适合作为 regression baseline 和回退参考，不替代主配置。

## 为什么 B profile 暂不正式启用

B profile fresh candidates=2828，C profile fresh candidates=2824，说明 B 不是没有机会。阻断点在 formal approval：B=13，C=404。当前没有发现 writer / join / execution mapping 丢失，因此 B profile 应保留 diagnostic-only，后续单独研究 approval bottleneck。

## 为什么 portfolio_heat_cap_5pct 是必要条件

未限制 Variant B 的 portfolio_heat_max=0.11，max_concurrent_positions=22，same_direction_overlap_count=558。加入 `portfolio_heat_cap=0.05` 后，收益仍稳定为正，且 exposure 明显下降。因此该限制是正式候选的一部分。

## 进入正式配置的 expansion

- Session_HL source，仅限 Restricted Variant B。
- attempt_4 displacement 主 setup。
- attempt_3 CHOCH/MSS positive Tier 2。
- dynamic_time_cut，仅限 Restricted Variant B。
- quality_aware_capped_sizing，仅限 Restricted Variant B。
- portfolio_heat_cap=0.05。

## 保留 diagnostic / backlog

- B profile main config。
- unrestricted Variant B。
- Full original family。
- Tier 3。
- rolling_range。
- PDH/PDL。
- EQH/EQL。
- runner / partial TP / structure target。

## 当前限制

正式候选仍需要 PR12 后续 merge/tag 前检查；不得绕过 full-audit、regression 或 artifact validation。
