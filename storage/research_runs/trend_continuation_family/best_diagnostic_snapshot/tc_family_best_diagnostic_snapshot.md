# TC Family Best Diagnostic Snapshot

## Executive Summary

TC family 当前阶段已封存。最佳诊断版本为 `bp_shallow_cost_aware_admission_v3`，仅作为 `diagnostic_best_snapshot_preserved` 保存，用于后续复盘、对照、复现或未来重新研究。

该版本不是 formal candidate，不进入 P6，不进入正式 proposal 队列，不修改正式配置，`live_trading_enabled=false` 保持不变。

## Why We Stop TC Family Refinement

- final regime-aware refinement 没有超过 v3 baseline。
- v3 的 harsh avg R 仍为 -0.0010，接近打平但未稳定转正。
- adaptive exit 提高部分 median_R，但削弱均值、harsh 或 walk-forward 稳定性。
- regime cost gate 对 MEAN_REVERTING_TRANSITION 的收紧存在 overfilter 风险。
- CE native / CE shallow 已不再作为优化主线。
- 继续围绕 TC family 小修小补的过拟合风险高于研究收益。
- 下一阶段更适合等待人工定义 simple support/resistance fixed RR baseline 做对照。

## Best Variant

- strategy_family: `trend_continuation_family`
- best_variant: `bp_shallow_cost_aware_admission_v3`
- status: `diagnostic_best_snapshot_preserved`
- formal_candidate: `false`
- proposal_candidate: `false`
- p6_allowed: `false`
- live_trading_enabled: `false`
- refinement_status: `stopped`
- next_research: `simple_support_resistance_fixed_rr_baseline_pending_user_spec`

## Key Metrics

| Metric | Value |
| --- | ---: |
| closed | 416 |
| base R | 0.0612 |
| stress R | 0.0381 |
| harsh R | -0.0010 |
| median_R | 0.0195 |
| PF | 1.4068 |
| WF | 4/1 |
| Ex top1 | 0.0577 |
| Ex top2 | 0.0544 |

## Reproducibility

- run_id: `20260605T173718Z_61df2053b9f1`
- source run root: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1`
- variant path: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_admission_v3`
- manifest: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_admission_v3\run_manifest.json`
- artifact index: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_admission_v3\artifact_index.json`
- closed trades: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_admission_v3\closed_trade_rows.jsonl`
- Full Audit: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_admission_v3\full_audit`
- metric recompute: `passed`
- no-lookahead: `passed`
- regression baseline: `present`
- cost tier policy: base / stress / harsh preserved.
- row_type policy: performance metrics only from `row_type=closed_trade`; diagnostic / proposal / summary rows are excluded.
- capped risk sizing: proposal-only; min actual risk after cap = 0.10% equity.

## Known Limitations

- TC family remains diagnostic-only.
- Best harsh remains slightly negative.
- Regime split is informative, but not actionable enough for validation-prep.
- CE native and CE shallow are paused.
- simple support/resistance fixed RR baseline is not implemented yet.

## How To Restore

Use the `variant_path` above as the frozen diagnostic source. Do not write this variant into formal config or proposal queue.

Any future TC family restart must explicitly cite this snapshot, keep proposal-only boundaries, and start from a new research brief.
