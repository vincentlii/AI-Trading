# Legacy Wrapper Mapping

## Conclusion

This file documents the PR 3 compatibility layer. The wrappers only register and echo legacy LR research commands. They do not migrate scanner, filter, sizing, execution, RiskEngine, fee, funding, margin, stop formula, candidate generation, or report logic.

## Registered Liquidity Reversal Scripts

| Alias | Legacy script | Stage | Status | Calls old logic | Migrated to core |
|---|---|---|---|---|---|
| `fresh-lr-scan` | `run_fresh_lr_scanner.py` | `fresh_lr_scanner` | active | true | false |
| `minimal-lr-filter` | `run_minimal_lr_v0_filter.py` | `minimal_lr_v0_filter` | active | true | false |
| `stage6-quality` | `run_stage6_quality_recovery.py` | `stage6_quality_recovery` | active | true | false |
| `stage6c-sizing` | `run_stage6c_sizing_proposal.py` | `stage6c_sizing_proposal` | active | true | false |
| `stage6d-edge` | `run_stage6d_edge_validation.py` | `stage6d_edge_validation` | active | true | false |
| `stage6e-aggregate` | `run_stage6e_aggregator.py` | `stage6e_aggregator` | active | false | false |
| `stage7-smoke-plan` | `run_stage7_smoke_plan.py` | `stage7_smoke_plan` | active | false | false |

## Current Boundary

- `legacy-list` lists wrapper registry entries.
- `legacy-run` is dry-run only and prints the command that would call the old script.
- `stage6e-aggregate` and `stage7-smoke-plan` are read-only wrappers to `research_pipeline`; their `migrated_to_core` value remains false because no strategy logic has migrated.
- Old scripts remain the source of truth and are not deleted.
- Real strategy logic migration starts after the read-only wrapper and manifest phases.

## Pending

- Candidate scanner migration.
- Filter replay migration.
- Sizing diagnostics migration.
- Edge validation migration.
- Execution replay migration.
