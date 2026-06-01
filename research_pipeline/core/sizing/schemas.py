from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RiskBasedSizingMetrics:
    target_risk_pct: float | None
    actual_risk_pct_avg: float | None
    actual_risk_pct_p50: float | None
    actual_risk_pct_p75: float | None
    actual_risk_pct_p90: float | None
    risk_utilization_avg: float | None
    risk_utilization_p50: float | None
    risk_utilization_p75: float | None
    risk_utilization_p90: float | None


@dataclass(frozen=True)
class NotionalCapMetrics:
    notional_cap_hit_count: int | None
    notional_cap_hit_ratio: float | None
    required_notional_to_cap_ratio_avg: float | None
    required_notional_to_cap_ratio_p50: float | None
    required_notional_to_cap_ratio_p75: float | None
    required_notional_to_cap_ratio_p90: float | None
    required_notional_far_above_cap_count: int | None
    required_notional_far_above_cap_ratio: float | None


@dataclass(frozen=True)
class MarginDiagnostics:
    margin_required_too_high_count: int | None
    stop_distance_too_near_count: int | None
    stop_near_margin_overlap_count: int | None
    margin_required_pct_p50: float | None
    margin_required_pct_p75: float | None
    margin_required_pct_p90: float | None
    notional_to_equity_pct_p50: float | None
    notional_to_equity_pct_p75: float | None
    notional_to_equity_pct_p90: float | None


@dataclass(frozen=True)
class CappedSizingProposalMetrics:
    capped_proposal_approved: int | None
    capped_only_rows: int | None
    actual_risk_pct_after_cap_p50: float | None
    actual_risk_pct_after_cap_p75: float | None
    risk_utilization_after_cap_p50: float | None
    risk_utilization_after_cap_p75: float | None
    low_risk_count: int | None
    medium_risk_count: int | None
    near_target_risk_count: int | None
    proposal_only: bool = True


@dataclass(frozen=True)
class SizingModelDiagnostics:
    sizing_model: str
    fresh_candidates: int | None
    formal_approved: int | None
    proposal_approved: int | None
    closed_trades: int | None
    risk_based: RiskBasedSizingMetrics
    notional_cap: NotionalCapMetrics
    margin: MarginDiagnostics
    capped_proposal: CappedSizingProposalMetrics
    missing_fields: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SizingDiagnostics:
    strategy: str
    stage: str
    window: str
    fresh_candidates: int | None
    formal_approved: int | None
    proposal_approved: int | None
    closed_trades: int | None
    models: dict[str, SizingModelDiagnostics]
    source_files: list[str]
    missing_fields: list[str] = field(default_factory=list)
    proposal_only: bool = True
    readonly: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["models"] = {
            key: value.as_dict() for key, value in self.models.items()
        }
        return payload

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
