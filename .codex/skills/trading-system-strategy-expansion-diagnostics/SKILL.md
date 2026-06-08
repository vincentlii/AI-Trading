---
name: trading-system-strategy-expansion-diagnostics
description: Use when a strategy has raw candidates equal to zero, too few closed trades, concentrated rejections, near-miss questions, or needs bounded proposal-only expansion diagnostics.
---

# Trading System Strategy Expansion Diagnostics

## Purpose

Turn “no candidates” or “too few trades” into a staged, explainable research result. Expansion diagnostics is a Research Pipeline stage, not a one-off strategy script.

## Boundaries

- Proposal-only and diagnostic-only by default.
- Do not change formal config or RiskEngine.
- Do not widen fees, funding, margin, notional cap, heat, stop, target, or exits.
- Variants must be bounded and declared by the adapter.
- Metrics remain closed_trade-only.

## Inputs

- Baseline research run.
- Adapter diagnostic stages.
- Rejection rows and near-miss rows.
- Optional reusable baseline artifacts with matching fingerprints.
- A maximum number of variants from the user or research plan.

## Workflow

1. Run or read strict baseline first.
2. Build staged funnel from context to candidate to approval to closed_trade.
3. Rank primary rejection layers and secondary reasons.
4. Separate low-quality rejects, reasonable near-misses, and definition conflicts.
5. Design only minimal proposal-only variants targeting the diagnosed bottleneck.
6. Reuse baseline artifacts when fingerprint-safe.
7. Run audit isolation so diagnostic rows cannot enter metrics.
8. Stop after the bounded variant budget.

## Outputs

- Signal funnel.
- Rejection distribution.
- Near-miss taxonomy.
- Variant table with raw, approved, closed, audit status, and sample warning.
- Recommendation: continue diagnostic, refactor definition, backlog, or formal validation candidate discussion.

## Stop Rules

- If the main bottleneck is unexplained, report pipeline / feature gap first.
- If variants still produce no candidates or no audited closed trades, stop.
- If a setup definition is too broad, recommend strategy-family split instead of local tuning.
