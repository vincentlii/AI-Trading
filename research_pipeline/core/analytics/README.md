# Read-only Aggregation

## Conclusion

PR 5 aggregation is read-only. It consumes frozen artifact summaries and structured Stage 6E comparison data, then produces normalized aggregation and proposal-only smoke-plan outputs.

## Scope

- No scanner execution.
- No filter replay execution.
- No sizing diagnostics execution.
- No edge validation execution.
- No execution replay or full backtest.
- No changes to `RiskEngine`, fee, funding, margin, stop formula, candidate generation, or old report output.

## Inputs

- `ResearchRunSummary`
- `stage6e_aggregated_comparison_snapshot.csv`
- `stage7_smoke_grouped_rows_snapshot.jsonl`
- `key_metrics.json`
- `baseline_manifest.json`

## Outputs

- `AggregationResult`
- aggregation markdown report
- proposal-only `SmokePlan`
- smoke-plan markdown report

## Current Reproduction Target

The read-only aggregation preserves the frozen Stage 6E decision:

- smoke-ready combos: `CHOCH true`, `displacement_after_reclaim`
- `displacement_after_reclaim` remains the strongest combo
- `high_wick`, `high_sweep_rvol + CHOCH true + high_wick`, and `ETH C short` are not smoke-ready

Old `stage6e_aggregator` and `stage7_smoke_plan` scripts remain registered as legacy wrappers and are not deleted.

## PR 8 Edge Analytics

PR 8 adds read-only edge analytics for Stage 6D / Stage 6E outputs.

It still does not run strategy logic. It only reads existing artifacts, aggregation results, or summaries.

## Edge Inputs

- `AggregationResult`
- `ResearchRunSummary`
- structured Stage 6E comparison CSV rows

Structured files are preferred. Markdown remains auxiliary.

## Edge Outputs

- `EdgeMetrics`
- `PushClassification`
- `TagComboMetrics`
- `QualityComboRanking`
- `edge_analysis_result.json`
- `edge_analysis_report.md`

## Push Classification

- `no_push`: `MFE_R < 0.3`
- `weak_push`: `0.3 <= MFE_R < 0.5`
- `medium_push`: `0.5 <= MFE_R < 1.0`
- `strong_push`: `MFE_R >= 1.0`

When only threshold ratios are available, the reader preserves medium/strong push counts from `MFE_R >= 0.5` and `MFE_R >= 1.0`. It does not invent unavailable no/weak counts.

## Combo Ranking

Ranking is explicit and non-black-box. It keeps raw metrics beside every decision flag.

Priority:

1. smoke-ready hint from Stage 6E aggregation;
2. `closed_trades >= 40`;
3. `MFE_R_avg` above baseline;
4. `MFE_R >= 0.5` ratio above baseline;
5. `MFE_R >= 1.0` ratio not below baseline;
6. `net_R` or `net_return_on_notional` not worse than baseline;
7. lower `time_cut_exit_rate`;
8. no sample-size warning.

The current frozen LR target remains:

- smoke-ready combos: `CHOCH true`, `displacement_after_reclaim`
- strongest combo: `displacement_after_reclaim`

## Boundaries

Edge analytics does not:

- generate candidates;
- run scanner / filter / sizing / execution;
- change proposal parameters;
- turn diagnostic tags into formal filters;
- formalize notional-capped sizing;
- enter Stage 7 full backtest.

LR formal proposal validation remains PR 11. Cleanup and merge remain PR 12.
