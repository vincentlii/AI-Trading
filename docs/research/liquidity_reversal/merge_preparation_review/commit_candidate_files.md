# Commit Candidate Files

## 结论

不要使用 `git add -A`。当前工作区包含大量未跟踪 Obsidian plugin、归档资料和历史研究文件，必须按白名单提交。

## 正式策略配置

- `configs/strategies/liquidity_reversal.yaml`
- `configs/research_backlog/liquidity_reversal_backlog.yaml`

## Research Pipeline / Audit / Robustness 代码

建议提交整个 `research_pipeline/`，这是 PR1-PR12 research framework 主体：

- `research_pipeline/adapters/`
- `research_pipeline/cli/research.py`
- `research_pipeline/core/`
- `research_pipeline/legacy/`
- `research_pipeline/registry/`
- `research_pipeline/runners/`
- `research_pipeline/tests/`

重点新增或最终相关：

- `research_pipeline/runners/lr_robustness_fix.py`
- `research_pipeline/runners/lr_robustness_validation.py`
- `research_pipeline/runners/full_pipeline_audit.py`
- `research_pipeline/core/audit/`

## 测试文件

- `tests/test_liquidity_reversal_final_config.py`
- `research_pipeline/tests/test_lr_robustness_fix.py`
- `research_pipeline/tests/test_lr_robustness_validation.py`
- `research_pipeline/tests/test_full_pipeline_audit_cli.py`
- `research_pipeline/tests/test_*`
- `tests/fixtures/regression_baselines/liquidity_reversal/stage6e_10000w/`

## 最终研究纪要与决策日志

- `docs/research/liquidity_reversal/final_research_memo.md`
- `docs/research/liquidity_reversal/merge_preparation_review/pre_merge_review_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/commit_candidate_files.md`
- `docs/research/liquidity_reversal/merge_preparation_review/merge_content_summary.md`
- `docs/research/liquidity_reversal/merge_preparation_review/delete_or_archive_plan.md`
- `docs/research/liquidity_reversal/merge_preparation_review/git_hygiene_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/final_safety_boundary_check.md`
- `AI Trading/05_回测风控与模拟盘/Proposal验证流程.md`

## Final Audit / Robustness / Regression Baseline

这些文件目前位于 `storage/research_runs/liquidity_reversal/final/`，但 `storage/` 被 `.gitignore` 忽略。若要进入 master，必须人工确认后使用 `git add -f` 精确添加，不能添加整个 `storage/`。

建议最多 force-add：

- `storage/research_runs/liquidity_reversal/final/final_regression_baseline.json`
- `storage/research_runs/liquidity_reversal/final/final_full_audit_report.md`
- `storage/research_runs/liquidity_reversal/final/final_robustness_summary.md`
- `storage/research_runs/liquidity_reversal/final/final_test_results.md`
- `storage/research_runs/liquidity_reversal/final/proposal_to_formal_decision_log.md`
- `storage/research_runs/liquidity_reversal/final/merge_readiness_report.md`
- `storage/research_runs/liquidity_reversal/final/cleanup_manifest.md`
- `storage/research_runs/liquidity_reversal/final/legacy_migration_manifest.md`
- `storage/research_runs/liquidity_reversal/final/rollback_instructions.md`

不建议 force-add：

- `storage/backtest_cache/**`
- `storage/research_runs/liquidity_reversal/final/full_audit/*.jsonl`
- Monte Carlo row-level output
- 大型过程 rows

## Legacy Wrapper / Compatibility

- `scripts/run_fresh_lr_scanner.py`
- `scripts/run_minimal_lr_v0_filter.py`
- `scripts/run_stage6_quality_recovery.py`
- `scripts/run_stage6c_sizing_proposal.py`
- `scripts/run_stage6d_edge_validation.py`
- `scripts/run_stage6e_aggregator.py`
- `scripts/run_stage7_smoke_plan.py`
- `scripts/export_lr_regression_baseline.py`

## 必须排除

- `.obsidian/workspace.json`
- `AI Trading/.obsidian/plugins/**`
- `AI Trading/.claudian/**`
- `AI Trading/99_归档/**`，除非用户明确要求纳入
- `storage/backtest_cache/**`
- `storage/research_runs/**` 的大体积 row-level 临时输出
