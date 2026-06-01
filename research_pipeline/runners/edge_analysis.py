from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.analytics.aggregation import AggregationResult
from research_pipeline.core.analytics.combo_ranking import (
    QualityComboRanking,
    rank_quality_combos,
)
from research_pipeline.core.analytics.edge import EdgeMetrics
from research_pipeline.core.analytics.tag_analysis import (
    TagComboMetrics,
    tag_combo_metrics_from_row,
)
from research_pipeline.runners.aggregate_summaries import build_aggregation_result


@dataclass(frozen=True)
class EdgeAnalysisResult:
    strategy: str
    stage: str
    window: str
    combo_metrics: list[dict[str, Any]]
    ranked_combos: list[dict[str, Any]]
    baseline_combo: dict[str, Any]
    ranking_method: str
    source_files: list[str]
    readonly: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def build_edge_analysis(
    strategy: str,
    *,
    summary_dir: Path | None = None,
    aggregation_result_path: Path | None = None,
    preferred_window: str = "10000w",
) -> EdgeAnalysisResult:
    aggregation = _load_aggregation(
        strategy=strategy,
        summary_dir=summary_dir,
        aggregation_result_path=aggregation_result_path,
    )
    window = _select_window(aggregation, preferred_window)
    baseline = EdgeMetrics.from_mapping(aggregation.baseline_metrics[window])
    combos = _combo_metrics_for_window(aggregation, window)
    ranking = rank_quality_combos(
        strategy=strategy,
        stage="read_only_edge_analysis",
        window=window,
        combo_metrics=combos,
        baseline_metrics=baseline,
        source_files=aggregation.source_files,
    )
    return _result_from_ranking(ranking)


def _load_aggregation(
    *,
    strategy: str,
    summary_dir: Path | None,
    aggregation_result_path: Path | None,
) -> AggregationResult:
    if aggregation_result_path is not None:
        data = json.loads(Path(aggregation_result_path).read_text(encoding="utf-8"))
        return AggregationResult(**data)
    if summary_dir is None:
        raise ValueError("summary_dir or aggregation_result_path is required")
    return build_aggregation_result(strategy, Path(summary_dir))


def _select_window(aggregation: AggregationResult, preferred_window: str) -> str:
    if preferred_window in aggregation.baseline_metrics:
        return preferred_window
    if not aggregation.baseline_metrics:
        raise ValueError("Aggregation result has no baseline metrics")
    return sorted(aggregation.baseline_metrics)[-1]


def _combo_metrics_for_window(
    aggregation: AggregationResult,
    window: str,
) -> list[TagComboMetrics]:
    combos: list[TagComboMetrics] = []
    for combo_name, rows_by_window in aggregation.combo_metrics.items():
        row = rows_by_window.get(window)
        if row is None:
            continue
        combo = tag_combo_metrics_from_row(combo_name, row)
        combo = _with_smoke_ready_hint(
            combo,
            bool(
                aggregation.consistency_flags.get(combo_name, {}).get(
                    "legacy_stage6e_smoke_ready",
                    combo.smoke_ready_hint,
                )
            ),
        )
        combos.append(combo)
    return combos


def _with_smoke_ready_hint(combo: TagComboMetrics, smoke_ready_hint: bool) -> TagComboMetrics:
    return TagComboMetrics(
        combo_name=combo.combo_name,
        tags=combo.tags,
        candidates=combo.candidates,
        formal_approved=combo.formal_approved,
        proposal_approved=combo.proposal_approved,
        closed_trades=combo.closed_trades,
        edge_metrics=combo.edge_metrics,
        push_classification=combo.push_classification,
        sample_size_warning=combo.sample_size_warning,
        smoke_ready_hint=smoke_ready_hint,
    )


def _result_from_ranking(ranking: QualityComboRanking) -> EdgeAnalysisResult:
    return EdgeAnalysisResult(
        strategy=ranking.strategy,
        stage=ranking.stage,
        window=ranking.window,
        combo_metrics=ranking.ranked_combos,
        ranked_combos=ranking.ranked_combos,
        baseline_combo=ranking.baseline_combo,
        ranking_method=ranking.ranking_method,
        source_files=ranking.source_files,
    )
