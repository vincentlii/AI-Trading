from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from research_pipeline.core.analytics.edge import EdgeMetrics
from research_pipeline.core.analytics.tag_analysis import TagComboMetrics


@dataclass(frozen=True)
class QualityComboRanking:
    strategy: str
    stage: str
    window: str
    ranked_combos: list[dict[str, Any]]
    baseline_combo: dict[str, Any]
    ranking_method: str
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def rank_quality_combos(
    *,
    strategy: str,
    stage: str,
    window: str,
    combo_metrics: list[TagComboMetrics],
    baseline_metrics: EdgeMetrics,
    source_files: list[str],
) -> QualityComboRanking:
    ranked = []
    for combo in combo_metrics:
        flags = _ranking_flags(combo.edge_metrics, baseline_metrics)
        score = sum(1 for passed in flags.values() if passed)
        payload = combo.as_dict()
        payload["ranking_flags"] = flags
        payload["ranking_score"] = score
        ranked.append(payload)

    ranked.sort(key=_ranking_key, reverse=True)
    return QualityComboRanking(
        strategy=strategy,
        stage=stage,
        window=window,
        ranked_combos=ranked,
        baseline_combo={
            "combo_name": "baseline",
            "edge_metrics": baseline_metrics.as_dict(),
        },
        ranking_method=(
            "smoke_ready_hint, then closed>=40, MFE improvement, threshold ratios, "
            "net non-deterioration, lower time cut, and sample-size quality"
        ),
        source_files=source_files,
    )


def _ranking_flags(edge: EdgeMetrics, baseline: EdgeMetrics) -> dict[str, bool]:
    return {
        "sample_ok": edge.closed_trades >= 40,
        "MFE_R_avg_above_baseline": _num(edge.MFE_R_avg) > _num(baseline.MFE_R_avg),
        "MFE_ge_0_5_above_baseline": _num(edge.MFE_ge_0_5_ratio)
        > _num(baseline.MFE_ge_0_5_ratio),
        "MFE_ge_1_0_not_below_baseline": _num(edge.MFE_ge_1_0_ratio)
        >= _num(baseline.MFE_ge_1_0_ratio),
        "net_not_worse": _num(edge.net_R_avg) >= _num(baseline.net_R_avg)
        or _num(edge.net_return_on_notional_avg)
        >= _num(baseline.net_return_on_notional_avg),
        "time_cut_lower": _num(edge.time_cut_exit_rate) < _num(baseline.time_cut_exit_rate),
        "no_sample_size_warning": edge.sample_size_warning in (None, ""),
    }


def _ranking_key(row: dict[str, Any]) -> tuple[object, ...]:
    edge = row["edge_metrics"]
    return (
        bool(row.get("smoke_ready_hint")),
        int(row.get("ranking_score") or 0),
        _num(edge.get("MFE_R_avg")),
        _num(edge.get("MFE_ge_0_5_ratio")),
        _num(edge.get("MFE_ge_1_0_ratio")),
        _num(edge.get("net_R_avg")),
        _num(edge.get("net_return_on_notional_avg")),
        int(edge.get("closed_trades") or 0),
    )


def _num(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)
