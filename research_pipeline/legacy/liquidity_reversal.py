from __future__ import annotations

from research_pipeline.legacy.registry import LegacyScriptMapping


def _lr_mapping(
    script: str,
    alias: str,
    stage: str,
    notes: str,
    calls_old_logic: bool = True,
    readonly_wrapper_to_core: bool = False,
) -> LegacyScriptMapping:
    return LegacyScriptMapping(
        legacy_script_name=script,
        pipeline_command_alias=alias,
        strategy="liquidity_reversal",
        stage=stage,
        status="active",
        calls_old_logic=calls_old_logic,
        migrated_to_core=False,
        readonly_wrapper_to_core=readonly_wrapper_to_core,
        notes=notes,
    )


LIQUIDITY_REVERSAL_LEGACY_MAPPINGS = (
    _lr_mapping(
        "run_fresh_lr_scanner.py",
        "fresh-lr-scan",
        "fresh_lr_scanner",
        "Fresh LR event scanner wrapper; logic remains in the legacy script.",
    ),
    _lr_mapping(
        "run_minimal_lr_v0_filter.py",
        "minimal-lr-filter",
        "minimal_lr_v0_filter",
        "Minimal LR filter replay wrapper; logic remains in the legacy script.",
    ),
    _lr_mapping(
        "run_stage6_quality_recovery.py",
        "stage6-quality",
        "stage6_quality_recovery",
        "Stage 6 quality filter report wrapper; logic remains in the legacy script.",
    ),
    _lr_mapping(
        "run_stage6c_sizing_proposal.py",
        "stage6c-sizing",
        "stage6c_sizing_proposal",
        "Stage 6C sizing proposal wrapper; logic remains in the legacy script.",
    ),
    _lr_mapping(
        "run_stage6d_edge_validation.py",
        "stage6d-edge",
        "stage6d_edge_validation",
        "Stage 6D edge validation wrapper; logic remains in the legacy script.",
    ),
    _lr_mapping(
        "run_stage6e_aggregator.py",
        "stage6e-aggregate",
        "stage6e_aggregator",
        "Read-only aggregation/reporting now calls research_pipeline; no strategy logic migrated.",
        calls_old_logic=False,
        readonly_wrapper_to_core=True,
    ),
    _lr_mapping(
        "run_stage7_smoke_plan.py",
        "stage7-smoke-plan",
        "stage7_smoke_plan",
        "Read-only smoke-plan reporting now calls research_pipeline; no strategy logic migrated.",
        calls_old_logic=False,
        readonly_wrapper_to_core=True,
    ),
)
