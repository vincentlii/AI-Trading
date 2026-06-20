---
name: trading-system-research-pipeline-runner
description: Use when running or planning quant strategy research in the trading system with Research Pipeline, manifests, artifacts, diagnostics, proposal-only variants, or validation reports.
---

# Trading System Research Pipeline Runner

## Purpose

Use the project Research Pipeline as the default path for strategy research. Do not copy legacy PR stage scripts or create one-off runners when an adapter, manifest, artifact contract, and audit profile can express the work.

## Required Boundaries

- Default mode is research / diagnostic / proposal-only.
- Do not formalize a strategy, enter P6, change formal config, or change `live_trading_enabled=false`.
- Do not bypass `RiskEngine`, fees, funding, margin, notional cap, portfolio heat, stop, target, or exit boundaries.
- Do not let diagnostic, proposal, or summary rows enter performance metrics.
- Protect invalidated or stopped-strategy evidence as read-only historical reference; never restore it as a candidate without a new audited research decision.

## Inputs

- Strategy or setup id.
- Dataset window and preset.
- Adapter / registry entry.
- Audit profile and artifact contract.
- Optional baseline artifact or cross-run fingerprint.
- Required variants, if the task is proposal-only expansion or validation.

## Workflow

1. Read `AGENTS.md` and relevant `AI Trading/` pages before writing.
2. Check `git branch --show-current` and `git status --short`.
3. Confirm the strategy has an adapter, manifest, artifact contract, and audit profile.
4. Prefer cross-run artifact reuse when fingerprints match.
5. Read existing reports, artifact indexes, and row-level evidence before deciding to rerun expensive scanners.
6. Run baseline before variants.
7. Run only bounded proposal-only variants requested by the research plan.
8. Before execution optimization, test confirmation geometry and fixed-horizon drift when event-reference diagnostics may be improved by chase.
9. Generate one concentrated report per stage unless audit requires machine-readable artifacts.
10. Run Full Audit Gate, no-lookahead, metric recompute, robustness, exposure restriction, and regression baseline when closed trades exist.
11. Record status in Obsidian after the round.

## Required Outputs

- Run manifest and artifact index.
- Candidate / execution / closed_trade lineage.
- Diagnostic funnel and rejection summary.
- Variant summary with base / stress / harsh cost tiers.
- Full Audit result or explicit `not_run_no_closed_trade_unverifiable`.
- Concentrated report with decision and next action.

## Stop Rules

- If baseline cannot produce candidates, run diagnostics before variants.
- If artifact fingerprints do not match, reject reuse.
- If Full Audit fails, stop formalization discussion.
- If variants are exhausted, preserve findings and do not continue local tuning.
- If upstream event semantics or path-order remain unreliable, do not expand entry, exit, sizing, or threshold grids.
- When a bounded research line is stopped, preserve the final evidence map, keep holdout sealed, archive intermediate reports, and mark the strategy `stopped`.
