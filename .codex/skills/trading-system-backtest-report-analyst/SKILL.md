---
name: trading-system-backtest-report-analyst
description: Use when interpreting trading backtest reports, closed_trade metrics, MFE/MAE paths, cost sensitivity, reject reasons, concentration risk, or proposal-only optimization evidence.
---

# Trading System Backtest Report Analyst

## Purpose

Read research reports and artifacts to explain what drove results. Distinguish signal quality, entry timing, exit efficiency, cost sensitivity, sizing effects, and sample concentration.

## Boundaries

- Do not infer live-trading readiness.
- Do not recommend formalization without Full Audit evidence.
- Do not use diagnostic / proposal / summary rows as performance.
- Do not hand-pick asset, profile, direction, or regime to beautify results.
- Do not propose loosening risk, cost, margin, or formal exits.

## Inputs

- Concentrated research report.
- Closed trade rows or metric recompute summary.
- Base / stress / harsh cost tiers.
- MAE / MFE / exit diagnostics when available.
- Rejection and RiskEngine diagnostics.
- Asset / profile / direction / trend_state splits.

## Analysis Checklist

1. Confirm metrics are closed_trade-only.
2. Compare base, stress, and harsh results.
3. Check median R, PF, win rate, average win/loss, drawdown, and top winner concentration.
4. Check `avg_R_excluding_top1/top2`.
5. Review walk-forward and regime split.
6. Diagnose MFE vs final R, MAE timing, profit giveback, and cost flips.
7. Identify whether the issue is signal, entry, exit, cost, sizing, or sample concentration.
8. Produce proposal-only next steps with explicit stop rules.

## Outputs

- Short conclusion.
- Evidence table.
- Failure / improvement attribution.
- Risk and concentration notes.
- Decision label and next action.

## Forbidden

- Do not state “strategy invalid” when only implementation semantics failed.
- Do not make a thin positive result sound robust.
- Do not suggest P6 or live trading from diagnostic evidence.
