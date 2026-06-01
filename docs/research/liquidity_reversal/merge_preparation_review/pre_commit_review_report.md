# PR12 Pre-Commit Review Report

## 1. Executive Summary

当前不建议直接 commit。

Go / No-Go Decision = B：高风险 diff 需要人工进一步确认，不能 commit。

阻断原因：

- 当前 untracked files = 242，不能使用全量 staging 命令。
- `storage/` 被 `.gitignore` 忽略，final artifacts 不会自动进入 master。
- `AI Trading/.obsidian/plugins/realclaudian/main.js` 等插件文件体积较大，存在误提交风险。
- `trading_system/backtest/execution.py`、`trading_system/config/loader.py`、`trading_system/config/proposals.py`、`trading_system/strategies/trend_price_volume_v1/features.py` 等 diff 涉及 execution、cost tier、time cut、stop/target 相关代码，必须人工确认它们只属于已验证的 lineage / audit / diagnostics / proposal 支持，而不是未审查的策略边界放宽。

下一步人工确认：

- 确认高风险 diff 是否全部属于 PR12 已验证范围。
- 确认 final evidence 采用 `docs/research/liquidity_reversal/final_evidence/` 复制提交，还是精确 `git add -f` 小型 final artifacts。
- 确认 staging 严格按白名单执行，不使用全量 staging 命令。

## 2. Staging Whitelist

### Formal Config

建议进入 commit：

- `configs/strategies/liquidity_reversal.yaml`
- `configs/research_backlog/liquidity_reversal_backlog.yaml`

需要人工确认后才进入 commit：

- `configs/assets/btc_eth_swap.toml`
- `configs/costs/crypto_swap_research.toml`
- `configs/presets/btc_eth_swap_proposal.toml`
- `configs/strategies/trend_price_volume_swap_proposal.toml`

### Research Pipeline / Audit / Robustness Code

建议进入 commit：

- `research_pipeline/`

注意：不要提交 `__pycache__/`。如已被 git 忽略则无需处理；如未忽略，必须排除。

### Audit / Robustness Runners

建议进入 commit：

- `scripts/export_lr_regression_baseline.py`
- `scripts/run_fresh_lr_scanner.py`
- `scripts/run_minimal_lr_v0_filter.py`
- `scripts/run_stage6_quality_recovery.py`
- `scripts/run_stage6c_sizing_proposal.py`
- `scripts/run_stage6d_edge_validation.py`
- `scripts/run_stage6e_aggregator.py`
- `scripts/run_stage7_smoke_plan.py`

需要人工确认后才进入 commit：

- `scripts/check_data_quality.py`
- `scripts/download_okx_history.py`
- `scripts/run_btc_eth_p4_4_backtest.py`
- `scripts/run_btc_eth_swap_proposal.py`
- `scripts/run_candidate_anatomy_audit.py`

### Tests

建议进入 commit：

- `research_pipeline/tests/`
- `tests/fixtures/`
- `tests/test_liquidity_reversal_final_config.py`
- `tests/test_lr_regression_baseline.py`
- `tests/test_fresh_lr_scanner.py`
- `tests/test_minimal_lr_filter.py`
- `tests/test_stage6_quality_recovery.py`
- `tests/test_contract_risk_diagnostics.py`
- `tests/test_layered_proposal_pipeline.py`
- `tests/test_proposal_contract_report.py`
- `tests/test_candidate_anatomy_audit.py`
- `tests/test_backtest_run_records.py`

需要人工确认后才进入 commit：

- `tests/test_backtest_batch.py`
- `tests/test_backtest_execution.py`
- `tests/test_config_loader.py`
- `tests/test_signal_rejection_detail.py`
- `tests/test_trend_price_volume_features.py`

### Docs / Final Research Memo

建议进入 commit：

- `docs/research/liquidity_reversal/final_research_memo.md`
- `docs/research/liquidity_reversal/merge_preparation_review/`
- `AI Trading/05_回测风控与模拟盘/Proposal验证流程.md`
- `AI Trading/01_长期记忆/测试与验证命令.md`
- `AI Trading/01_长期记忆/项目事实库.md`
- `AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md`
- `AI Trading/03_策略研究中心/策略研究总览.md`

需要人工确认后才进入 commit：

- `README.md`
- `AI Trading/01_长期记忆/架构地图.md`
- `AI Trading/05_回测风控与模拟盘/P5中文交易诊断驾驶舱.md`
- 根目录中文薄入口文档：`代理协作流程.md`、`开发记录.md`、`策略规格.md`、`项目总规划.md`

### Merge Preparation Docs

建议进入 commit：

- `docs/research/liquidity_reversal/merge_preparation_review/pre_merge_review_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/commit_candidate_files.md`
- `docs/research/liquidity_reversal/merge_preparation_review/merge_content_summary.md`
- `docs/research/liquidity_reversal/merge_preparation_review/delete_or_archive_plan.md`
- `docs/research/liquidity_reversal/merge_preparation_review/git_hygiene_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/final_safety_boundary_check.md`
- `docs/research/liquidity_reversal/merge_preparation_review/pre_commit_review_report.md`

### Backlog / Rollback / Cleanup Docs

优先方案是先复制小型 final evidence 到：

- `docs/research/liquidity_reversal/final_evidence/`

建议纳入的 evidence 文件：

- `final_regression_baseline.json`
- `proposal_to_formal_decision_log.md`
- `final_full_audit_report.md`
- `final_robustness_summary.md`
- `final_test_results.md`
- `merge_readiness_report.md`
- `cleanup_manifest.md`
- `legacy_migration_manifest.md`
- `rollback_instructions.md`
- `artifact_index.json`
- `research_run_registry.json`

### Legacy Wrappers

建议进入 commit：

- `scripts/run_stage6e_aggregator.py`
- `scripts/run_stage7_smoke_plan.py`
- `research_pipeline/legacy/`

需要人工确认后才进入 commit：

- 其他 legacy wrapper 和旧 runner，确认它们只调用兼容层或保留旧命令入口，不引入新策略行为。

## 3. Exact Git Add Commands

禁止使用全量 staging 命令。

建议分批执行，且每批后运行 `git status --short` 检查。

### Batch 1: Formal LR Config

```powershell
git add -- "configs/strategies/liquidity_reversal.yaml"
git add -- "configs/research_backlog/liquidity_reversal_backlog.yaml"
```

### Batch 2: Research Pipeline

```powershell
git add -- "research_pipeline"
```

提交前必须确认没有 staged `__pycache__/`。

### Batch 3: LR Regression / Wrapper Scripts

```powershell
git add -- "scripts/export_lr_regression_baseline.py"
git add -- "scripts/run_fresh_lr_scanner.py"
git add -- "scripts/run_minimal_lr_v0_filter.py"
git add -- "scripts/run_stage6_quality_recovery.py"
git add -- "scripts/run_stage6c_sizing_proposal.py"
git add -- "scripts/run_stage6d_edge_validation.py"
git add -- "scripts/run_stage6e_aggregator.py"
git add -- "scripts/run_stage7_smoke_plan.py"
```

### Batch 4: Tests

```powershell
git add -- "research_pipeline/tests"
git add -- "tests/fixtures"
git add -- "tests/test_liquidity_reversal_final_config.py"
git add -- "tests/test_lr_regression_baseline.py"
git add -- "tests/test_fresh_lr_scanner.py"
git add -- "tests/test_minimal_lr_filter.py"
git add -- "tests/test_stage6_quality_recovery.py"
git add -- "tests/test_contract_risk_diagnostics.py"
git add -- "tests/test_layered_proposal_pipeline.py"
git add -- "tests/test_proposal_contract_report.py"
git add -- "tests/test_candidate_anatomy_audit.py"
git add -- "tests/test_backtest_run_records.py"
```

### Batch 5: Final Docs

```powershell
git add -- "docs/research/liquidity_reversal/final_research_memo.md"
git add -- "docs/research/liquidity_reversal/merge_preparation_review"
git add -- "AI Trading/05_回测风控与模拟盘/Proposal验证流程.md"
git add -- "AI Trading/01_长期记忆/测试与验证命令.md"
git add -- "AI Trading/01_长期记忆/项目事实库.md"
git add -- "AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md"
git add -- "AI Trading/03_策略研究中心/策略研究总览.md"
```

### Batch 6: Final Evidence, Preferred Path

仅在把小型 final evidence 复制到 `docs/research/liquidity_reversal/final_evidence/` 后执行：

```powershell
git add -- "docs/research/liquidity_reversal/final_evidence/final_regression_baseline.json"
git add -- "docs/research/liquidity_reversal/final_evidence/proposal_to_formal_decision_log.md"
git add -- "docs/research/liquidity_reversal/final_evidence/final_full_audit_report.md"
git add -- "docs/research/liquidity_reversal/final_evidence/final_robustness_summary.md"
git add -- "docs/research/liquidity_reversal/final_evidence/final_test_results.md"
git add -- "docs/research/liquidity_reversal/final_evidence/merge_readiness_report.md"
git add -- "docs/research/liquidity_reversal/final_evidence/cleanup_manifest.md"
git add -- "docs/research/liquidity_reversal/final_evidence/legacy_migration_manifest.md"
git add -- "docs/research/liquidity_reversal/final_evidence/rollback_instructions.md"
git add -- "docs/research/liquidity_reversal/final_evidence/artifact_index.json"
git add -- "docs/research/liquidity_reversal/final_evidence/research_run_registry.json"
```

### Batch 7: Optional Force Add, Not Preferred

如果不复制到 docs，而选择从 ignored `storage/` 精确纳入小型 final artifacts，只能使用以下形式，不得 force-add 整个 storage：

```powershell
git add -f -- "storage/research_runs/liquidity_reversal/final/final_regression_baseline.json"
git add -f -- "storage/research_runs/liquidity_reversal/final/proposal_to_formal_decision_log.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/final_full_audit_report.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/final_robustness_summary.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/final_test_results.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/merge_readiness_report.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/cleanup_manifest.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/legacy_migration_manifest.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/rollback_instructions.md"
git add -f -- "storage/research_runs/liquidity_reversal/final/artifact_index.json"
git add -f -- "storage/research_runs/liquidity_reversal/final/research_run_registry.json"
```

禁止 force-add：

- `storage/backtest_cache/**`
- row-level jsonl 大文件
- Monte Carlo row-level output
- `full_audit/*.jsonl`
- 临时过程 artifacts

### Batch 8: High-Risk Diffs, Only After Human Confirmation

```powershell
git add -- "trading_system/backtest/execution.py"
git add -- "trading_system/backtest/scanner.py"
git add -- "trading_system/config/loader.py"
git add -- "trading_system/config/proposals.py"
git add -- "trading_system/strategies/trend_price_volume_v1/features.py"
git add -- "trading_system/strategies/trend_price_volume_v1/strategy.py"
git add -- "tests/test_backtest_execution.py"
git add -- "tests/test_config_loader.py"
git add -- "tests/test_trend_price_volume_features.py"
```

## 4. Final Artifact Inclusion Plan

### Preferred Plan

把小型 final evidence 从 `storage/research_runs/liquidity_reversal/final/` 复制到：

- `docs/research/liquidity_reversal/final_evidence/`

然后只提交 docs 下的小型 evidence 文件。

优点：

- 避免破坏 `storage/` 忽略规则。
- 避免把 backtest cache、row-level jsonl、Monte Carlo 明细误提交。
- final memo、audit、robustness、regression baseline 更容易被 code review 看到。

当前状态：

- `storage/research_runs/liquidity_reversal/final/` 存在小型 final artifacts。
- `docs/research/liquidity_reversal/final_evidence/` 当前未发现已生成文件。
- 因本阶段只输出报告，未复制文件。

### Alternative Plan

使用精确 `git add -f` 纳入小型 final artifacts。

限制：

- 只能 force-add 单个小文件。
- 不能 force-add `storage/` 目录。
- 不能 force-add `storage/backtest_cache/**`。

## 5. Exclusion List

明确排除，不进入本次 commit：

- `.obsidian/workspace.json`
- `AI Trading/.obsidian/plugins/**`
- `AI Trading/.obsidian/community-plugins.json`
- `AI Trading/.claudian/**`
- `AI Trading/99_归档/**`
- `storage/backtest_cache/**`
- 旧 PR11A-PR11H row-level artifacts
- broken lineage artifacts
- old proposal/debug rows
- obsolete reports
- 临时 `jsonl` / `csv` / `md`
- `__pycache__/`
- `.pyc`
- old backtest cache outputs

特别风险：

- `AI Trading/.obsidian/plugins/realclaudian/main.js` 约 3.8 MB，不应进入 commit。

## 6. Risky Diff Review

### `trading_system/backtest/execution.py`

观察到的改动类型：

- 新增 `trade_id` / `execution_id` / `candidate_id` / `event_id` 到 `BacktestFillResult`。
- 新增 execution identity 与 lineage 生成。
- 新增 same-bar、forced pessimistic exit、MFE/MAE、time-cut、exit diagnostics 字段。
- 新增 `spread_slippage_rate` 成本项。
- 新增 `reversal_time_cut_bars` / `reversal_time_cut_min_mfe_r` 相关逻辑。

审查结论：需要人工确认后才能 staged。

回答：

- 是否修改 RiskEngine：未看到直接修改 RiskEngine 类，但 execution fill result 和 diagnostics 变化会影响 backtest 输出。
- 是否修改 fee / funding / margin / notional cap：没有看到 margin / notional cap 直接放宽；但新增 `spread_slippage_rate` 影响 cost estimate，需确认是更保守成本层而非降低成本。
- 是否修改 stop / target / exit：涉及 time-cut exit 与 exit diagnostics，必须确认属于已验证 proposal / audit 路径，不改变未验证正式 exit 语义。
- 是否放宽 same-bar / slippage / funding / liquidation 假设：same-bar 仍有 `conservative_same_bar` 和 forced pessimistic 标记；未看到放宽证据，但需人工确认。
- 是否只是 execution identity / lineage / audit / diagnostics 支持：主要是这类支持，但包含 cost/time-cut 行为扩展，不能自动认定无风险。
- 是否影响 live trading path：看起来属于 backtest execution，不应进入 live trading；仍需确认没有被 live path 调用。
- 是否需要拆出去：如果不能确认它完全属于 clean rebuild / full-audit 必需变更，应拆成单独 commit 或延后。

### `trading_system/backtest/scanner.py`

观察到的改动类型：

- 增加 direction / inst_type 统计字段。
- 增加 fee-to-gross-profit ratio、long/short 分布等 summary diagnostics。

审查结论：相对低风险，但仍建议与 audit/reporting commit 一起审查。

回答：

- 是否修改 RiskEngine：未看到。
- 是否修改 fee / funding / margin / notional cap：未看到放宽，仅新增统计。
- 是否修改 stop / target / exit：未看到。
- 是否放宽执行假设：未看到。
- 是否只是 diagnostics 支持：是。
- 是否影响 live trading path：不应影响。
- 是否需要拆出去：通常不需要，除非 scanner 输出口径尚未验证。

### `trading_system/config/loader.py`

观察到的改动类型：

- 新增 `contract_mode`、`allow_short`、cost tiers、`spread_slippage_rate`、`funding_mode`。
- 新增 execution 参数、profile status、strategy parameters / grid / volume。
- 将配置映射到 backtest execution config。

审查结论：高风险，需要人工确认。

回答：

- 是否修改 RiskEngine：未看到直接修改。
- 是否修改 fee / funding / margin / notional cap：新增 cost tier / funding mode / spread slippage 配置，必须确认没有降低成本或放宽约束。
- 是否修改 stop / target / exit：新增 execution 参数可影响 exit/time-cut proposal，必须确认正式配置只启用 validated candidate。
- 是否放宽执行假设：不能仅凭 diff 排除，需人工确认配置默认值安全。
- 是否只是 execution identity / lineage / audit / diagnostics 支持：不完全是；它扩展了配置面。
- 是否影响 live trading path：配置 loader 是共用层，需确认 live path 不启用 proposal-only 参数。
- 是否需要拆出去：建议至少人工确认后再进 commit；如范围过大，可拆为 config schema commit。

### `trading_system/config/proposals.py`

观察到的改动类型：

- 扩展允许变更路径，包括 cost、execution、strategy profile/status、parameter grid 等。
- 增加 cost tier validation。

审查结论：高风险，需要人工确认。

回答：

- 是否修改 RiskEngine：未看到。
- 是否修改 fee / funding / margin / notional cap：允许 proposal 修改更多 cost/execution 字段，需确认仅用于 research/proposal，不自动进正式配置。
- 是否修改 stop / target / exit：允许 execution 参数 proposal，需确认 formalization gate 仍有效。
- 是否放宽执行假设：可能扩大 proposal 配置面，需人工确认边界。
- 是否只是 audit / diagnostics 支持：不完全是；属于 proposal 配置治理。
- 是否影响 live trading path：取决于 proposal 应用路径，需确认不会自动应用到 live。
- 是否需要拆出去：如无法确认 proposal boundary，建议拆出或延后。

### `trading_system/strategies/trend_price_volume_v1/features.py`

观察到的改动类型：

- 强化 confirmed candle 使用。
- 增加 TOD/DOW volume baseline 分支。
- liquidity reversal 相关 invalidation / target 计算有 diff。

审查结论：高风险，需要人工确认。

回答：

- 是否修改 RiskEngine：未看到。
- 是否修改 fee / funding / margin / notional cap：未看到。
- 是否修改 stop / target / exit：看到 invalidation / target 相关 diff，必须确认它是此前已验证的 stop formula / no-lookahead 修复，而不是 PR12 新策略变更。
- 是否放宽执行假设：未看到 execution assumption 直接放宽。
- 是否只是 lineage / audit / diagnostics 支持：不完全是；这里可能影响 signal feature / stop-target 语义。
- 是否影响 live trading path：这是 strategy feature 文件，潜在影响 strategy signal path；必须人工确认 live disabled 且正式配置一致。
- 是否需要拆出去：若无法确认属于已验证 LR rebuild 基础修复，应拆出或延后。

### `trading_system/strategies/trend_price_volume_v1/strategy.py`

观察到的改动类型：

- 与 confirmed candle / feature context / setup detection 调用相关。

审查结论：需要人工确认。

回答：

- 是否修改 RiskEngine：未看到。
- 是否修改 fee / funding / margin / notional cap：未看到。
- 是否修改 stop / target / exit：未直接看到，但可能通过 features 影响 setup。
- 是否放宽执行假设：未看到。
- 是否只是 audit / diagnostics 支持：可能是 no-lookahead / confirmed bar 支持，但需确认。
- 是否影响 live trading path：strategy 文件可能影响 live path；由于 `live_trading_enabled=false`，不应启用，但仍需人工确认。
- 是否需要拆出去：若它只是 no-lookahead 修复并已有测试，可纳入；否则拆出。

## 7. Safety Boundary Check

当前 safety boundary 检查结论：通过，但依赖高风险 diff 人工确认。

已确认：

- final config = Restricted Variant B。
- `portfolio_heat_cap=0.05`。
- C profile formal scope。
- B profile = diagnostic-only。
- `live_trading_enabled=false`。
- unrestricted Variant B 未正式化。
- Full original family 未正式化。
- Tier 3 未正式化。
- rolling_range、PDH/PDL、EQH/EQL 未正式化。
- runner、partial TP、structure target 未正式化。
- unexecuted proposal rows excluded from performance。
- proposal / diagnostic / summary rows 不应进入 performance。

需要人工确认：

- high-risk config / execution / strategy diffs 没有绕过 RiskEngine。
- 没有降低 fee / funding / margin / notional cap。
- 没有放宽 same-bar / slippage / funding / liquidation 假设。
- `dynamic_time_cut`、`quality_aware_capped_sizing`、`Session_HL` 只在 Restricted Variant B 受限正式候选内生效。

## 8. Commit Package Summary

本次 commit 应包含：

- Restricted Variant B final config。
- `portfolio_heat_cap=0.05` final risk restriction。
- C profile formal scope 与 B profile diagnostic-only。
- Research Pipeline audit / artifact / registry / robustness / regression 框架。
- Full Audit Gate 与 final regression baseline。
- Final research memo、decision log、rollback、cleanup、legacy migration docs。
- Tests covering final config, audit gate, regression, artifact validation, and pipeline runners。

本次 commit 不应包含：

- `.obsidian/` workspace 或 plugins。
- `.claudian/`。
- `AI Trading/99_归档/`。
- `storage/backtest_cache/`。
- PR11A-PR11H row-level process artifacts。
- broken lineage artifacts。
- old proposal/debug rows。
- obsolete reports。
- 临时 jsonl/csv/md。
- unrestricted Variant B。
- Full original family。
- B profile formal main config。
- unexecuted proposal rows as performance evidence。

## 9. Suggested Commit Message

```text
formalize liquidity reversal research pipeline candidate

- add Restricted Variant B liquidity reversal formal research config
- add reusable research pipeline audit, artifact, registry, and robustness tooling
- freeze final LR regression, audit, robustness, and decision evidence
- document proposal-to-formal decision, rollback path, and cleanup rules
- keep live trading disabled and B profile diagnostic-only
```

## 10. Go / No-Go Decision

Primary Decision = B：高风险 diff 需要人工进一步确认，不能 commit。

原因：

- staging 白名单已经可执行，但高风险 diff 仍需人工确认。
- final evidence 纳入方式尚未最终选择，优先建议复制到 docs 后提交。
- 当前 untracked files 多，误提交风险高。
- 不允许使用全量 staging 命令。

Next Step：

- 人工确认 high-risk diff 是否属于已验证 lineage / audit / diagnostics / proposal 支持。
- 人工决定 final evidence 使用 docs 复制方案或精确 `git add -f` 方案。
- 确认后按白名单分批 staging。
- staging 后重新运行 `git status --short`、`git diff --cached --stat`、`git diff --cached --check`、相关 tests。

禁止在当前状态下 commit、merge、tag。
