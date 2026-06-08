# TC Family Cleanup and Preservation Report

## 1. Executive Summary

本轮完成 TC family 阶段封存、报告修复、项目清理验证和分层 commit 准备。

当前最佳诊断版本为 `bp_shallow_cost_aware_admission_v3`。该版本已保存为 `diagnostic_best_snapshot_preserved`，仅用于后续复盘、对照、复现或未来重新研究。

本轮没有 formalize，没有进入 P6，没有进入正式 proposal 队列，没有修改正式策略配置，`live_trading_enabled=false` 保持不变。LR final evidence 未被覆盖、重解释或污染。

## 2. Preserved Best Diagnostic Snapshot

- strategy_family: `trend_continuation_family`
- best variant: `bp_shallow_cost_aware_admission_v3`
- status: `diagnostic_best_snapshot_preserved`
- formal_candidate: `false`
- proposal_candidate: `false`
- p6_allowed: `false`
- live_trading_enabled: `false`
- refinement_status: `stopped`
- run_id: `20260605T173718Z_61df2053b9f1`
- variant path: `storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_admission_v3`

Key metrics:

| Metric | Value |
| --- | ---: |
| closed | 416 |
| base avg R | 0.0612 |
| stress avg R | 0.0381 |
| harsh avg R | -0.0010 |
| median_R | 0.0195 |
| PF | 1.4068 |
| WF | 4/1 |
| Ex top1 | 0.0577 |
| Ex top2 | 0.0544 |

Audit and reproducibility evidence:

- run manifest: readable
- artifact index: readable
- closed_trade rows: readable
- Full Audit: `passed`
- no-lookahead / lineage evidence: `passed`
- metric recompute: `passed`
- regression baseline: `present`
- capped risk sizing: proposal-only, min actual risk after cap = 0.10% equity
- cost tier policy: base / stress / harsh preserved
- row_type policy: performance metrics only from `row_type=closed_trade`; diagnostic / proposal / summary rows are excluded

## 3. Why We Stop TC Refinement

- final regime-aware refinement did not outperform `bp_shallow_cost_aware_admission_v3`.
- v3 harsh avg R remains -0.0010, close to flat but not stable positive.
- Global partial capture improved median_R in prior rounds but weakened mean / harsh / right-tail quality.
- regime adaptive exit did not produce a better overall result.
- regime cost gate showed overfilter risk; removed MEAN_REVERTING_TRANSITION trades were not clearly worse.
- CE native and CE shallow no longer justify further optimization in this phase.
- Continuing TC family local refinement would increase overfitting risk.
- The next more useful comparison is a simple support/resistance fixed RR baseline, pending user specification.

## 4. Cleanup Plan and Actions

Retained categories:

- best diagnostic snapshot md/json
- cleanup dry-run plan and cleanup report
- best v3 run manifest and artifact index
- best v3 closed_trade rows required for metric recompute
- Full Audit evidence
- no-lookahead / lineage evidence
- regression baseline evidence
- final reports referenced by Obsidian
- Research Pipeline shared lifecycle core and generic runners
- Obsidian formal knowledge pages

Deleted categories:

- failed_variant_intermediate
- duplicate_replay
- superseded_by_report
- obsolete diagnostic replay directories that are not required for best snapshot reproduction

Actual deleted paths:

| Path | Reason | Estimated size |
| --- | --- | ---: |
| `cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_partial_capture_v1` | failed_variant_intermediate | 28.29 MB |
| `cost_aware_refinement_with_trend_state\runs\20260605T173718Z_61df2053b9f1\variants\bp_shallow_cost_aware_momentum_failure_exit_v1` | failed_variant_intermediate | 28.28 MB |
| `final_regime_aware_refinement\runs\20260607T172428Z_bb3914fa269c\variants\bp_shallow_regime_diagnostic_no_filter_v1` | duplicate_replay | 27.32 MB |
| `final_regime_aware_refinement\runs\20260607T172428Z_bb3914fa269c\variants\bp_shallow_regime_adaptive_exit_v1` | failed_variant_intermediate | 27.29 MB |
| `final_regime_aware_refinement\runs\20260607T172428Z_bb3914fa269c\variants\bp_shallow_regime_cost_gate_v1` | failed_variant_intermediate | 26.28 MB |

Estimated released space: 137.46 MB.

Protected paths check: passed. The deletion list did not include best v3 artifact, LR final evidence, Research Pipeline code, shared lifecycle engine, Obsidian formal pages, or final reports.

Actual deletion status: completed. Only the listed failed / duplicate variant directories were removed.

Additional large artifact note:

- Older `breakout_pullback/core_rebuild_round` artifacts still contain several 50 MB+ JSONL files.
- They are not removed in this round because Obsidian pages still reference the historical core rebuild result and they are outside the TC best snapshot cleanup scope.
- They should be handled only by a separate historical artifact archival pass.

## 5. Post-Cleanup Validation

| Check | Result |
| --- | --- |
| best diagnostic snapshot markdown exists | passed |
| best diagnostic snapshot json exists | passed |
| cleanup report exists and is readable | passed |
| best variant artifact path readable | passed |
| closed_trade rows / metric recompute evidence readable | passed |
| Full Audit readable | passed |
| no-lookahead / lineage evidence readable | passed |
| regression baseline readable | passed |
| run manifest readable | passed |
| Obsidian pages updated | passed |
| LR final evidence untouched by this cleanup | passed |
| live trading true flag absent from configs | passed |
| TC family formal/proposal/P6 flags remain false in snapshot | passed |
| simple baseline not implemented | passed |

## 6. Commit Readiness

Recommended commit groups:

1. `harden research pipeline lineage and preservation utilities`
   - Research Pipeline / shared lifecycle / audit / no-lookahead / metric recompute / capped risk / TC family runners / tests.

2. `preserve TC family best diagnostic snapshot`
   - AGENTS.md if accepted as project agent entry.
   - TC family Obsidian status pages.
   - Forced-add minimal ignored snapshot and best v3 evidence from `storage/`.

3. `cleanup superseded TC family research artifacts`
   - Cleanup report and deletion evidence.
   - Any tracked deletion state, if present.

4. `fix TC family preservation report encoding`
   - Only needed if the encoding/report fixes are kept separate from the snapshot commit.

Files that should not be committed by default:

- `.obsidian/workspace.json`
- `AI Trading/.obsidian/plugins/realclaudian/*`
- `AI Trading/.obsidian/community-plugins.json`
- `AI Trading/.claudian/*`
- large ignored storage artifacts outside the minimal snapshot evidence chain
- any simple baseline half-finished implementation, if it appears later

Large file risk:

- `storage/` is ignored by `.gitignore`.
- The snapshot and minimal evidence files must be added with `git add -f` if they are meant to enter the repository.
- Do not force-add the whole best v3 directory; only force-add the minimal reproducibility evidence.

Manual confirmation items:

- Whether to commit `AGENTS.md` as a tracked project entry.
- Whether Obsidian plugin / `.claudian` files are intentional project configuration or local-only state.
- Whether older BP core rebuild 50 MB+ artifacts should be archived in a separate cleanup round.

## 7. Remaining Known Limitations

- TC family remains diagnostic-only.
- Best harsh remains close to flat but slightly negative.
- Regime-aware refinement did not create a validation-prep-ready variant.
- simple support/resistance fixed RR baseline is not implemented.
- `target_space` and `cost_edge_score` can be audited later if TC family is explicitly restarted.
- Current phase stops TC family tuning.

## 8. Next Step Placeholder

Wait for user-provided simple support/resistance fixed RR baseline specification.

Do not implement the baseline early. Do not use TC family diagnostic snapshot as formal candidate evidence.
