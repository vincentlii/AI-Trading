from __future__ import annotations

from typing import Any

from research_pipeline.core.sizing.notional_cap import notional_cap_hit_ratio
from research_pipeline.core.sizing.schemas import (
    CappedSizingProposalMetrics,
    MarginDiagnostics,
    NotionalCapMetrics,
    RiskBasedSizingMetrics,
    SizingModelDiagnostics,
)


REQUIRED_MODEL_FIELDS = [
    "actual_risk_pct_after_cap_avg",
    "actual_risk_pct_after_cap_p50",
    "actual_risk_pct_after_cap_p75",
    "actual_risk_pct_after_cap_p90",
    "risk_utilization_ratio_avg",
    "risk_utilization_ratio_p50",
    "risk_utilization_ratio_p75",
    "risk_utilization_ratio_p90",
    "notional_cap_hit_count",
    "required_notional_to_cap_ratio_avg",
    "required_notional_to_cap_ratio_p50",
    "required_notional_to_cap_ratio_p75",
    "required_notional_to_cap_ratio_p90",
    "required_notional_far_above_cap_count",
    "margin_required_too_high",
    "stop_distance_too_near",
    "stop_near_margin_overlap",
    "margin_required_pct_p50",
    "margin_required_pct_p75",
    "margin_required_pct_p90",
    "notional_to_equity_pct_p50",
    "notional_to_equity_pct_p75",
    "notional_to_equity_pct_p90",
    "low_risk_count",
    "medium_risk_count",
    "near_target_risk_count",
]


def build_model_diagnostics(
    sizing_model: str,
    row: dict[str, Any],
    *,
    fresh_candidates: int | None,
) -> SizingModelDiagnostics:
    missing = [field for field in REQUIRED_MODEL_FIELDS if row.get(field) in (None, "")]
    proposal_approved = _int(row.get("proposal_approved"))
    formal_approved = _int(row.get("formal_approved"))
    cap_hit_count = _int(row.get("notional_cap_hit_count"))
    required_far_count = _int(row.get("required_notional_far_above_cap_count"))
    return SizingModelDiagnostics(
        sizing_model=sizing_model,
        fresh_candidates=_int(row.get("fresh_candidates")) or fresh_candidates,
        formal_approved=formal_approved,
        proposal_approved=proposal_approved,
        closed_trades=_int(row.get("closed_trades")),
        risk_based=RiskBasedSizingMetrics(
            target_risk_pct=_num(row.get("target_risk_pct")),
            actual_risk_pct_avg=_num(row.get("actual_risk_pct_after_cap_avg")),
            actual_risk_pct_p50=_num(row.get("actual_risk_pct_after_cap_p50")),
            actual_risk_pct_p75=_num(row.get("actual_risk_pct_after_cap_p75")),
            actual_risk_pct_p90=_num(row.get("actual_risk_pct_after_cap_p90")),
            risk_utilization_avg=_num(row.get("risk_utilization_ratio_avg")),
            risk_utilization_p50=_num(row.get("risk_utilization_ratio_p50")),
            risk_utilization_p75=_num(row.get("risk_utilization_ratio_p75")),
            risk_utilization_p90=_num(row.get("risk_utilization_ratio_p90")),
        ),
        notional_cap=NotionalCapMetrics(
            notional_cap_hit_count=cap_hit_count,
            notional_cap_hit_ratio=notional_cap_hit_ratio(cap_hit_count, fresh_candidates),
            required_notional_to_cap_ratio_avg=_num(
                row.get("required_notional_to_cap_ratio_avg")
            ),
            required_notional_to_cap_ratio_p50=_num(
                row.get("required_notional_to_cap_ratio_p50")
            ),
            required_notional_to_cap_ratio_p75=_num(
                row.get("required_notional_to_cap_ratio_p75")
            ),
            required_notional_to_cap_ratio_p90=_num(
                row.get("required_notional_to_cap_ratio_p90")
            ),
            required_notional_far_above_cap_count=required_far_count,
            required_notional_far_above_cap_ratio=notional_cap_hit_ratio(
                required_far_count, fresh_candidates
            ),
        ),
        margin=MarginDiagnostics(
            margin_required_too_high_count=_int(row.get("margin_required_too_high")),
            stop_distance_too_near_count=_int(row.get("stop_distance_too_near")),
            stop_near_margin_overlap_count=_int(row.get("stop_near_margin_overlap")),
            margin_required_pct_p50=_num(row.get("margin_required_pct_p50")),
            margin_required_pct_p75=_num(row.get("margin_required_pct_p75")),
            margin_required_pct_p90=_num(row.get("margin_required_pct_p90")),
            notional_to_equity_pct_p50=_num(row.get("notional_to_equity_pct_p50")),
            notional_to_equity_pct_p75=_num(row.get("notional_to_equity_pct_p75")),
            notional_to_equity_pct_p90=_num(row.get("notional_to_equity_pct_p90")),
        ),
        capped_proposal=CappedSizingProposalMetrics(
            capped_proposal_approved=proposal_approved,
            capped_only_rows=(
                proposal_approved - formal_approved
                if proposal_approved is not None and formal_approved is not None
                else None
            ),
            actual_risk_pct_after_cap_p50=_num(row.get("actual_risk_pct_after_cap_p50")),
            actual_risk_pct_after_cap_p75=_num(row.get("actual_risk_pct_after_cap_p75")),
            risk_utilization_after_cap_p50=_num(row.get("risk_utilization_ratio_p50")),
            risk_utilization_after_cap_p75=_num(row.get("risk_utilization_ratio_p75")),
            low_risk_count=_int(row.get("low_risk_count")),
            medium_risk_count=_int(row.get("medium_risk_count")),
            near_target_risk_count=_int(row.get("near_target_risk_count")),
        ),
        missing_fields=missing,
    )


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))
