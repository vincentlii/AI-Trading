# Reusable Research Pipeline Full Audit Gate Report

- strategy = breakout_pullback
- proposal_only = true
- formal_conclusion_enabled = false
- audit_passed = true

## Gate Summary
- schema_contract_rows = 403
- lineage_rows = 1
- join_integrity_rows = 1
- proposal_boundary_rows = 5
- no_lookahead_rows = 13
- metric_recompute_rows = 30
- report_consistency_rows = 16
- artifact_integrity_rows = 16
- code_logic_review_rows = 204

## Primary Decision
B. Audit passed with non-blocking warnings; carry warnings into the next review.

## Blocking Issues
- None

## Non-blocking Warnings
- Artifact metadata incomplete: candidate_rows.jsonl
- Artifact metadata incomplete: closed_trade_rows.jsonl
- Artifact metadata incomplete: diagnostic_rows.jsonl
- Artifact metadata incomplete: execution_path_diagnostics.jsonl
- Artifact metadata incomplete: execution_path_summary.json
- Artifact metadata incomplete: filter_results_research.jsonl
- Artifact metadata incomplete: regression_baseline.json
- Artifact metadata incomplete: review_log_rows.jsonl
- Artifact metadata incomplete: robustness_rows.jsonl
- Artifact metadata incomplete: run_manifest.json
- Artifact metadata incomplete: run_manifest.md
- Artifact metadata incomplete: summary_rows.jsonl
- Artifact metadata incomplete: trend_state_lineage_diagnostics.json
- Artifact metadata incomplete: variant_diagnostics.json
- Report scope unavailable: baseline regression report
- Report scope unavailable: artifact summary report
- Report scope unavailable: aggregation report
- Report scope unavailable: smoke plan report
- Report scope unavailable: edge analysis report
- Report scope unavailable: sizing diagnostics report
- Report scope unavailable: strategy summary report
- Report scope unavailable: strategy regression check report
- Report scope unavailable: stage7 smoke report
- Report scope unavailable: expansion diagnostic report
- Report scope unavailable: attempt proposal report
- Report scope unavailable: structure source proposal report
- Report scope unavailable: exit profile proposal report
- Report scope unavailable: sizing proposal report
- Report scope unavailable: combined candidate report
- Report scope unavailable: robustness report
- Code review risk medium: summary_rows_as_closed_rows in D:\交易系统\research_pipeline\adapters\liquidity_reversal.py
- Code review risk medium: summary_rows_as_closed_rows in D:\交易系统\research_pipeline\core\analytics\combo_ranking.py
- Code review risk medium: missing_field_default_zero in D:\交易系统\research_pipeline\core\analytics\combo_ranking.py
- Code review risk medium: summary_rows_as_closed_rows in D:\交易系统\research_pipeline\core\analytics\edge.py
- Code review risk medium: missing_field_default_zero in D:\交易系统\research_pipeline\core\analytics\edge.py
- Code review risk medium: summary_rows_as_closed_rows in D:\交易系统\research_pipeline\core\analytics\execution_path.py
- Code review risk medium: missing_field_default_zero in D:\交易系统\research_pipeline\core\analytics\execution_path.py
- Code review risk medium: summary_rows_as_closed_rows in D:\交易系统\research_pipeline\core\analytics\push_classification.py
- Code review risk medium: missing_field_default_zero in D:\交易系统\research_pipeline\core\analytics\push_classification.py
- Code review risk medium: summary_rows_as_closed_rows in D:\交易系统\research_pipeline\core\analytics\smoke_readiness.py
- ... 137 more warnings in JSON result

## Next PR Recommendation
- strategy research validation review
