from __future__ import annotations

from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.reader import read_artifact
from research_pipeline.core.artifacts.schemas import ResearchRunSummary
from research_pipeline.core.reports.readers import read_markdown_report


def normalize_research_run_summary(strategy: str, artifact_dir: Path) -> ResearchRunSummary:
    if strategy != "liquidity_reversal":
        raise ValueError(f"Unsupported strategy for read-only artifact summary: {strategy}")
    artifact_dir = Path(artifact_dir)

    key_metrics = read_artifact(artifact_dir / "key_metrics.json").data
    manifest = read_artifact(artifact_dir / "baseline_manifest.json").data
    smoke_plan = read_markdown_report(artifact_dir / "stage7_smoke_plan_snapshot.md")

    metrics = _metrics_from_key_metrics(key_metrics)
    combos = _combos_from_key_metrics(key_metrics)
    sizing = _sizing_from_key_metrics(key_metrics)
    smoke = {
        "selected_combos": list(manifest.get("selected_stage7_smoke_combos", [])),
        "proposal_only": _contains_bool_flag(smoke_plan.raw_text, "proposal_only", True),
        "formal_conclusion_enabled": _contains_bool_flag(
            smoke_plan.raw_text, "formal_conclusion_enabled", True
        ),
    }

    return ResearchRunSummary(
        strategy=strategy,
        run_id=manifest.get("baseline_name", "unknown"),
        stage="stage6e_expanded_sample",
        window=manifest.get("window", key_metrics.get("window", "unknown")),
        source_files=sorted(manifest.get("snapshots", {}).values()),
        created_at=manifest.get("created_at_utc"),
        metrics=metrics,
        combos=combos,
        sizing=sizing,
        smoke=smoke,
    )


def _metrics_from_key_metrics(key_metrics: dict[str, Any]) -> dict[str, Any]:
    counts = key_metrics["counts"]
    execution = key_metrics["execution"]
    return {
        "fresh_candidates": counts["fresh_candidates"],
        "formal_approved": counts["formal_approved"],
        "proposal_approved": counts["proposal_approved"],
        "closed_trades": counts["closed_trades"],
        "MFE_R_avg": execution["MFE_R"]["avg"],
        "MFE_R_p50": execution["MFE_R"]["p50"],
        "MFE_R_p75": execution["MFE_R"]["p75"],
        "MFE_R_p90": execution["MFE_R"]["p90"],
        "MAE_R_avg": execution["MAE_R"]["avg"],
        "net_R_avg": execution["net_R"]["avg"],
        "net_R_p50": execution["net_R"]["p50"],
        "time_cut_exit_rate": execution["time_cut_exit_rate"],
    }


def _combos_from_key_metrics(key_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    combos: list[dict[str, Any]] = []
    for combo_name, row in key_metrics.get("tracked_combos", {}).items():
        combos.append(
            {
                "combo_name": combo_name,
                "closed_trades": row.get("closed_trades"),
                "MFE_R_avg": row.get("MFE_R_avg"),
                "MFE_ge_0_5": row.get("MFE_R_ge_0_5_ratio"),
                "MFE_ge_1_0": row.get("MFE_R_ge_1_0_ratio"),
                "net_R_avg": row.get("net_R_avg"),
                "net_return_on_notional": row.get("net_return_on_notional_avg"),
                "time_cut_exit_rate": row.get("time_cut_exit_rate"),
                "sample_size_warning": row.get("sample_size_warning"),
            }
        )
    return combos


def _sizing_from_key_metrics(key_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    sizing: list[dict[str, Any]] = []
    for sizing_model, row in key_metrics.get("sizing", {}).items():
        sizing.append(
            {
                "sizing_model": sizing_model,
                "proposal_approved": row.get("proposal_approved"),
                "notional_cap_hit": row.get("notional_cap_hit_count"),
                "actual_risk_pct_p50": row.get("actual_risk_pct_after_cap_p50"),
                "risk_utilization_p50": row.get("risk_utilization_ratio_p50"),
            }
        )
    return sizing


def _contains_bool_flag(text: str, key: str, default: bool) -> bool:
    lowered = text.lower()
    if f"{key.lower()}=true" in lowered:
        return True
    if f"{key.lower()}=false" in lowered:
        return False
    return default
