from __future__ import annotations

from pathlib import Path
from typing import Any

from research_pipeline.core.analytics.aggregation import AggregationResult
from research_pipeline.core.analytics.smoke_readiness import evaluate_smoke_readiness
from research_pipeline.core.artifacts.reader import read_artifact


AGGREGATED_COMPARISON = "stage6e_aggregated_comparison_snapshot.csv"
LEGACY_AGGREGATED_COMPARISON = "stage6e_aggregated_comparison.csv"


def build_aggregation_result(strategy: str, summary_dir: Path) -> AggregationResult:
    if strategy != "liquidity_reversal":
        raise ValueError(f"Unsupported strategy for read-only aggregation: {strategy}")
    summary_dir = Path(summary_dir)
    rows = [_typed_row(row) for row in read_artifact(_comparison_path(summary_dir)).data]
    windows = sorted({str(row["window"]) for row in rows})
    baseline_by_window = {
        str(row["window"]): row for row in rows if row.get("label") == "baseline"
    }

    combo_metrics: dict[str, dict[str, dict[str, Any]]] = {}
    consistency_flags: dict[str, dict[str, Any]] = {}
    sample_size_warnings: dict[str, list[str]] = {}
    smoke_ready_combos: list[str] = []

    labels = sorted({str(row["label"]) for row in rows if row.get("label") != "baseline"})
    for label in labels:
        normalized = _normalize_combo_name(label)
        label_rows = [row for row in rows if row.get("label") == label]
        combo_metrics[normalized] = {str(row["window"]): row for row in label_rows}
        computed_flags = {
            str(row["window"]): evaluate_smoke_readiness(row, baseline_by_window[str(row["window"])])
            for row in label_rows
        }
        legacy_ready = all(bool(row.get("stage7_smoke_ready")) for row in label_rows)
        multi_window_consistent = all(flags["smoke_ready"] for flags in computed_flags.values())
        consistency_flags[normalized] = {
            "legacy_stage6e_smoke_ready": legacy_ready,
            "computed_multi_window_ready": multi_window_consistent,
            "multi_window_consistent": legacy_ready,
            "window_flags": computed_flags,
        }
        warnings = sorted(
            {
                str(row["sample_size_warning"])
                for row in label_rows
                if row.get("sample_size_warning") not in (None, "")
            }
        )
        sample_size_warnings[normalized] = warnings
        if legacy_ready:
            smoke_ready_combos.append(normalized)

    return AggregationResult(
        strategy=strategy,
        windows=windows,
        grouped_metrics=rows,
        combo_metrics=combo_metrics,
        baseline_metrics=baseline_by_window,
        smoke_ready_combos=sorted(smoke_ready_combos),
        consistency_flags=consistency_flags,
        sample_size_warnings=sample_size_warnings,
        source_files=[str(_comparison_path(summary_dir))],
    )


def _comparison_path(summary_dir: Path) -> Path:
    snapshot = summary_dir / AGGREGATED_COMPARISON
    if snapshot.exists():
        return snapshot
    legacy = summary_dir / LEGACY_AGGREGATED_COMPARISON
    if legacy.exists():
        return legacy
    raise FileNotFoundError(f"Missing {AGGREGATED_COMPARISON} or {LEGACY_AGGREGATED_COMPARISON} in {summary_dir}")


def _typed_row(row: dict[str, str]) -> dict[str, Any]:
    return {key: _typed_value(value) for key, value in row.items()}


def _typed_value(value: str) -> Any:
    if value == "":
        return None
    if value in {"True", "False"}:
        return value == "True"
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _normalize_combo_name(label: str) -> str:
    if label == "CHOCH true only":
        return "CHOCH true"
    if label == "high_sweep_rvol only":
        return "high_sweep_rvol"
    return label
