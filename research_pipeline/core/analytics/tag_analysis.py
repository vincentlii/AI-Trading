from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from research_pipeline.core.analytics.edge import EdgeMetrics
from research_pipeline.core.analytics.push_classification import (
    PushClassification,
    classify_from_mfe_threshold_ratios,
)


@dataclass(frozen=True)
class TagComboMetrics:
    combo_name: str
    tags: list[str]
    candidates: int | None
    formal_approved: int | None
    proposal_approved: int | None
    closed_trades: int
    edge_metrics: EdgeMetrics
    push_classification: PushClassification
    sample_size_warning: str | None
    smoke_ready_hint: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["edge_metrics"] = self.edge_metrics.as_dict()
        payload["push_classification"] = self.push_classification.as_dict()
        return payload


def tag_combo_metrics_from_row(combo_name: str, row: dict[str, Any]) -> TagComboMetrics:
    edge = EdgeMetrics.from_mapping(row)
    push = classify_from_mfe_threshold_ratios(
        closed_trades=edge.closed_trades,
        mfe_ge_0_5_ratio=edge.MFE_ge_0_5_ratio or 0.0,
        mfe_ge_1_0_ratio=edge.MFE_ge_1_0_ratio or 0.0,
    )
    return TagComboMetrics(
        combo_name=combo_name,
        tags=_tags_from_combo(combo_name),
        candidates=_optional_int(row.get("candidates")),
        formal_approved=_optional_int(row.get("current_formal_approved")),
        proposal_approved=_optional_int(row.get("capped_proposal_approved") or row.get("proposal_approved")),
        closed_trades=edge.closed_trades,
        edge_metrics=edge,
        push_classification=push,
        sample_size_warning=edge.sample_size_warning,
        smoke_ready_hint=bool(row.get("stage7_smoke_ready")),
    )


def _tags_from_combo(combo_name: str) -> list[str]:
    if combo_name == "baseline":
        return []
    return [tag.strip() for tag in combo_name.split("+")]


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))
