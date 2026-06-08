# Full Audit Gate 指南

## 结论

Full Audit Gate 是所有 formal research candidate 的通用准入标准。它不优化策略、不生成交易、不修改配置，只验证研究产物是否可追溯、可重算、无前瞻、可解释。

## 硬规则

| 规则 | 要求 |
|---|---|
| 收益统计 | 只能来自 `row_type=closed_trade` |
| 禁止进入收益统计 | `proposal_candidate`、`sizing_diagnostic`、`diagnostic_only`、`summary_row` |
| lineage | closed trade 必须追溯 `trade_id`、`execution_id`、`candidate_id`、`event_id` 和 timeseries |
| no-lookahead | 不只检查字段存在，还必须验证时间顺序 |
| metric recompute | 报告指标必须可从 row-level artifact 重算 |
| robustness | 只能使用通过 lineage/no-lookahead 的 closed trade rows |
| regression baseline | formal candidate 必须保留可回放基线 |

## 当前实现状态

- metric recompute 支持 `mfe_R/mae_R` 与 `MFE_R/MAE_R` 兼容。
- no-lookahead 已验证时间顺序，不再只检查字段存在。
- LR audit 仍保留历史命名兼容，但原则已抽象到 generic audit profile。
- 旧 PR artifacts 只作历史参考，不作为正式 robustness input。

## 阻断条件

- closed trade 缺少 execution identity。
- proposal/diagnostic/summary rows 污染收益统计。
- 时间链缺字段或顺序失败。
- metric recompute 与报告不一致。
- final evidence、robustness 或 regression baseline 无法追溯。

## Codex Skill 入口

Full Audit Gate 已作为项目通用流程沉淀为 `trading-system-full-audit-gate-checker`。

使用边界：

- 只验证，不优化策略。
- 只读取 `row_type=closed_trade` 作为绩效来源。
- proposal / diagnostic / summary rows 必须隔离。
- 无 closed_trade 时只能报告不可验证，不能绕过 gate。
- LR final evidence 只读保护，不得用后续研究覆盖或重解释。
