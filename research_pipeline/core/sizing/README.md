# Read-only Sizing Diagnostics

## Conclusion

PR 9 sizing diagnostics is read-only. It standardizes existing sizing artifacts and reports but does not run scanner, filter replay, sizing engine, execution replay, or full backtest.

## Scope

- Read `key_metrics.json` or an artifact index that points to it.
- Normalize current risk-based sizing and notional-capped proposal metrics.
- Preserve missing fields as `null` and list them in `missing_fields`.
- Produce JSON and Markdown diagnostics.

## Current vs Proposal

`current_risk_based_sizing` is the formal baseline represented in frozen artifacts.

`notional_capped_risk_based` remains proposal-only. Proposal approval is not formal approval, and capped sizing is not formalized by this module.

## Risk Utilization

Risk utilization means:

```text
actual_risk_pct_after_cap / target_risk_pct
```

Low actual risk or low risk utilization is not an automatic reject.

Interpretation:

- low risk plus MFE / cost-adjusted return can remain under observation;
- low risk plus no MFE, no cost-adjusted return, and high time cut is low-quality noise.

## Notional Cap

Notional cap hit ratio measures how often risk-based position sizing would exceed the configured notional cap.

Required-notional tiers:

- `near_cap`: `<= 1.5`
- `moderate_above_cap`: `1.5 - 3`
- `far_above_cap`: `3 - 5`
- `extreme_above_cap`: `> 5`

## Margin And Stop-near

`margin_required_too_high` and `stop_distance_too_near` are preserved as diagnostics. If `stop_near_margin_overlap` is missing from a historical artifact, it stays `null` and appears in `missing_fields`.

This module does not modify `RiskEngine`, margin, fee, funding, stop formula, candidate generation, or LR proposal parameters.

## Roadmap Boundary

Capped sizing formal validation remains PR 11. Cleanup, master merge, and stable tag remain PR 12.
