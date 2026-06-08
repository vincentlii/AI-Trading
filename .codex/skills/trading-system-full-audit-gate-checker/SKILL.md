---
name: trading-system-full-audit-gate-checker
description: Use when checking trading research artifacts for Full Audit Gate compliance, closed_trade-only metrics, proposal row isolation, lineage, no-lookahead, metric recompute, or regression baseline.
---

# Trading System Full Audit Gate Checker

## Purpose

Full Audit Gate verifies whether research artifacts are traceable, recomputable, no-lookahead, and safe to discuss as formal research evidence. It does not optimize strategies or modify configs.

## Hard Rules

- Performance metrics must come only from `row_type=closed_trade`.
- `proposal`, `diagnostic`, `summary`, and sizing diagnostic rows must be excluded from returns.
- Closed trades must trace execution, candidate, event, and timeseries lineage.
- No-lookahead must validate event and trade time order, not only field presence.
- Metric recompute must match reported metrics from row-level artifacts.
- Robustness, exposure restriction, and regression baseline must use audited closed_trade rows.

## Inputs

- Run root or variant path.
- Manifest and artifact index.
- Closed trade rows.
- Candidate, event, execution, and timeseries lineage.
- Reported metric summary.
- Regression baseline reference.

## Workflow

1. Identify row types and confirm the performance source table.
2. Recompute metrics from closed_trade rows only.
3. Verify proposal / diagnostic / summary row isolation.
4. Verify lineage keys and timestamps.
5. Run no-lookahead checks.
6. Check artifact integrity and fingerprints.
7. Compare regression baseline.
8. Summarize pass, fail, or unverifiable.

## Outputs

- Gate status: `pass`, `fail`, or `not_run_no_closed_trade_unverifiable`.
- Blocking findings with artifact paths.
- Metric recompute summary.
- No-lookahead summary.
- Regression baseline diff.
- Explicit formalization boundary.

## Forbidden

- Do not treat missing closed trades as a pass.
- Do not use old PR artifacts as formal evidence.
- Do not patch strategy logic to make audit pass.
- Do not allow audit rows to overwrite LR final evidence.
