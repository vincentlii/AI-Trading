# Final Test Results

## Validation Commands

| Check | Command | Result |
|---|---|---|
| Full audit | `python -m research_pipeline.cli.research full-audit --strategy liquidity_reversal --artifact-dir storage\backtest_cache\pr11g_clean_rebuild\lr_combined_fix --output-dir storage\research_runs\liquidity_reversal\final\full_audit` | passed |
| Strategy regression check | `python -m research_pipeline.cli.research strategy-regression-check --strategy liquidity_reversal --baseline-dir tests\fixtures\regression_baselines\liquidity_reversal\stage6e_10000w --summary-dir tests\fixtures\regression_baselines\liquidity_reversal\stage6e_10000w --output-dir storage\research_runs\liquidity_reversal\final\strategy_regression` | passed |
| Final config regression | `python -B -m unittest tests.test_liquidity_reversal_final_config -v` | passed |
| Research pipeline tests | `python -B -m unittest discover -s research_pipeline\tests -v` | passed |
| Compile | `python -B -m compileall research_pipeline` | passed |
| Diff check | `git diff --check` | passed with CRLF warnings only |
| Artifact validation | `python -m research_pipeline.cli.research validate-artifacts --artifact-index storage\research_runs\liquidity_reversal\final\artifact_index.json` | passed after final index build |

## Required Assertions

- no blocking issue: passed.
- performance only from `closed_trade`: passed.
- proposal / diagnostic / summary rows excluded from performance: passed.
- trade_id / execution_id lineage intact in clean robustness input: passed.
- no-lookahead verifiable in clean rebuild audit: passed with accepted warnings.
- duplicate_event_count = 0: passed.
- final config matches Restricted Variant B: passed.

## Notes

The project uses `unittest`; no separate `pytest` suite was required for this PR.
