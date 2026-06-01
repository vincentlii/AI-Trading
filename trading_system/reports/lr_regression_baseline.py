from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE_DIR = (
    WORKSPACE_ROOT
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


@dataclass(frozen=True)
class LiquidityReversalBaselineSources:
    fresh_candidates: Path
    filter_results: Path
    execution_results: Path
    sizing_summary: Path
    edge_combos: Path
    aggregator_csv: Path
    aggregator_report: Path
    smoke_plan: Path
    smoke_grouped_rows: Path

    @classmethod
    def stage6e_10000w(cls, root: Path = WORKSPACE_ROOT) -> "LiquidityReversalBaselineSources":
        return cls(
            fresh_candidates=root
            / "storage"
            / "backtest_cache"
            / "fresh_lr_scanner_stage6e"
            / "10000w"
            / "fresh_lr_candidates.jsonl",
            filter_results=root
            / "storage"
            / "backtest_cache"
            / "minimal_lr_v0_filter_stage6e"
            / "10000w"
            / "minimal_lr_v0_filter_results.jsonl",
            execution_results=root
            / "storage"
            / "backtest_cache"
            / "minimal_lr_v0_filter_stage6e"
            / "10000w"
            / "minimal_lr_v0_execution_results.jsonl",
            sizing_summary=root
            / "storage"
            / "backtest_cache"
            / "stage6e_sizing"
            / "10000w"
            / "stage6c_sizing_summary.csv",
            edge_combos=root
            / "storage"
            / "backtest_cache"
            / "stage6e_edge"
            / "10000w"
            / "stage6d_quality_combos.csv",
            aggregator_csv=root
            / "storage"
            / "backtest_cache"
            / "stage6e_aggregator"
            / "stage6e_aggregated_comparison.csv",
            aggregator_report=root
            / "storage"
            / "backtest_cache"
            / "stage6e_aggregator"
            / "stage6e_aggregator_final_report.md",
            smoke_plan=root
            / "storage"
            / "backtest_cache"
            / "stage7_smoke_plan"
            / "final"
            / "stage7_smoke_plan.md",
            smoke_grouped_rows=root
            / "storage"
            / "backtest_cache"
            / "stage7_smoke_plan"
            / "final"
            / "stage7_smoke_grouped_rows.jsonl",
        )

    def as_dict(self) -> dict[str, Path]:
        return {
            "fresh_candidates": self.fresh_candidates,
            "filter_results": self.filter_results,
            "execution_results": self.execution_results,
            "sizing_summary": self.sizing_summary,
            "edge_combos": self.edge_combos,
            "aggregator_csv": self.aggregator_csv,
            "aggregator_report": self.aggregator_report,
            "smoke_plan": self.smoke_plan,
            "smoke_grouped_rows": self.smoke_grouped_rows,
        }


def load_baseline(baseline_dir: Path = DEFAULT_BASELINE_DIR) -> dict[str, Any]:
    baseline_dir = Path(baseline_dir)
    with (baseline_dir / "baseline_manifest.json").open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    with (baseline_dir / "key_metrics.json").open("r", encoding="utf-8") as handle:
        key_metrics = json.load(handle)
    return {"manifest": manifest, "key_metrics": key_metrics}


def export_lr_regression_baseline(
    output_dir: Path = DEFAULT_BASELINE_DIR,
    sources: LiquidityReversalBaselineSources | None = None,
) -> dict[str, Any]:
    sources = sources or LiquidityReversalBaselineSources.stage6e_10000w()
    _validate_sources(sources)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    key_metrics = _build_key_metrics(sources)
    snapshots = _write_snapshots(output_dir, sources)
    manifest = _build_manifest(output_dir, sources, snapshots)

    _write_json(output_dir / "key_metrics.json", key_metrics)
    _write_json(output_dir / "baseline_manifest.json", manifest)
    return {"manifest": manifest, "key_metrics": key_metrics}


def _build_key_metrics(sources: LiquidityReversalBaselineSources) -> dict[str, Any]:
    sizing_rows = _read_csv_rows(sources.sizing_summary)
    current_sizing = _row_by_value(sizing_rows, "sizing_model", "current_risk_based_sizing")
    capped_sizing = _row_by_value(sizing_rows, "sizing_model", "notional_capped_risk_based")
    execution_rows = list(_read_jsonl(sources.execution_results))

    tracked_combos = _tracked_combo_metrics(sources.edge_combos, sources.aggregator_csv)
    final_decision = _parse_final_decision(sources.aggregator_report)
    selected_combos = _parse_stage7_selected_combos(sources.smoke_plan)
    smoke_ready_labels = _smoke_ready_labels(sources.aggregator_csv)

    return {
        "strategy": "liquidity_reversal",
        "window": "10000w",
        "counts": {
            "fresh_candidates": _count_lines(sources.fresh_candidates),
            "formal_approved": _to_int(current_sizing["formal_approved"]),
            "proposal_approved": _to_int(capped_sizing["proposal_approved"]),
            "closed_trades": _to_int(current_sizing["closed_trades"]),
        },
        "execution": {
            "MFE_R": _distribution(execution_rows, "mfe_R", percentiles=(50, 75, 90)),
            "MAE_R": _distribution(execution_rows, "mae_R", percentiles=(50, 75)),
            "net_R": _distribution(execution_rows, "net_R", percentiles=(50,)),
            "time_cut_exit_rate": _typed_value(current_sizing["time_cut_exit_rate"]),
        },
        "sizing": {
            "current_risk_based_sizing": _typed_row(current_sizing),
            "notional_capped_risk_based": _typed_row(capped_sizing),
        },
        "tracked_combos": tracked_combos,
        "stage6e_aggregator_final_decision": final_decision,
        "stage6e_smoke_ready_labels": smoke_ready_labels,
        "stage7_smoke_plan_selected_combos": selected_combos,
    }


def _tracked_combo_metrics(edge_combos: Path, aggregator_csv: Path) -> dict[str, dict[str, Any]]:
    edge_rows = _read_csv_rows(edge_combos)
    aggregator_rows = _read_csv_rows(aggregator_csv)
    tracked = [
        ("baseline", "baseline"),
        ("high_sweep_rvol", "high_sweep_rvol only"),
        ("CHOCH true", "CHOCH true only"),
        ("high_wick", "high_wick"),
        (
            "high_sweep_rvol + CHOCH true + high_wick",
            "high_sweep_rvol + CHOCH true + high_wick",
        ),
        ("displacement_after_reclaim", "displacement_after_reclaim"),
        ("ETH C short", "ETH C short"),
    ]
    out: dict[str, dict[str, Any]] = {}
    for key, label in tracked:
        agg = _row_matching(aggregator_rows, window="10000w", label=label)
        edge = _row_matching(
            edge_rows,
            combo=label,
            sizing_model="notional_capped_risk_based",
        ) or _row_matching(edge_rows, combo=label, sizing_model="current_risk_based_sizing")
        merged = _typed_row(edge) if edge else {}
        if agg:
            merged.update(_typed_row(agg))
        out[key] = merged
    return out


def _write_snapshots(output_dir: Path, sources: LiquidityReversalBaselineSources) -> dict[str, str]:
    snapshot_sources = {
        "stage6e_aggregator_final_snapshot.md": sources.aggregator_report,
        "stage6e_aggregated_comparison_snapshot.csv": sources.aggregator_csv,
        "stage7_smoke_plan_snapshot.md": sources.smoke_plan,
        "stage7_smoke_grouped_rows_snapshot.jsonl": sources.smoke_grouped_rows,
    }
    snapshots: dict[str, str] = {}
    for filename, source in snapshot_sources.items():
        destination = output_dir / filename
        shutil.copyfile(source, destination)
        snapshots[source.name] = filename
    return snapshots


def _build_manifest(
    output_dir: Path,
    sources: LiquidityReversalBaselineSources,
    snapshots: dict[str, str],
) -> dict[str, Any]:
    selected = _parse_stage7_selected_combos(sources.smoke_plan)
    source_artifacts = {}
    for name, path in sources.as_dict().items():
        source_artifacts[name] = {
            "path": _workspace_relative(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
    return {
        "baseline_name": "liquidity_reversal_stage6e_10000w",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": "liquidity_reversal",
        "window": "10000w",
        "baseline_dir": _workspace_relative(output_dir),
        "key_metrics": "key_metrics.json",
        "snapshots": snapshots,
        "source_artifacts": source_artifacts,
        "selected_stage7_smoke_combos": selected,
        "metric_tolerance": {
            "counts": "exact",
            "float_abs": 1e-9,
            "float_rel": 1e-6,
        },
        "pr_scope": "PR1 Regression Freeze only; no scanner/filter/sizing/execution logic changes.",
    }


def _validate_sources(sources: LiquidityReversalBaselineSources) -> None:
    missing = [str(path) for path in sources.as_dict().values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing LR regression baseline source artifacts: " + ", ".join(missing))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _count_lines(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def _row_by_value(rows: list[dict[str, str]], field: str, value: str) -> dict[str, str]:
    row = _row_matching(rows, **{field: value})
    if row is None:
        raise ValueError(f"Missing row where {field}={value}")
    return row


def _row_matching(rows: list[dict[str, str]], **criteria: str) -> dict[str, str] | None:
    for row in rows:
        if all(row.get(key) == value for key, value in criteria.items()):
            return row
    return None


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
    if number.is_integer() and value.lower() not in {"nan", "inf", "-inf"}:
        return int(number)
    return number


def _to_int(value: str) -> int:
    return int(float(value))


def _distribution(rows: list[dict[str, Any]], field: str, percentiles: tuple[int, ...]) -> dict[str, float | int]:
    values = sorted(float(row[field]) for row in rows if row.get(field) is not None)
    if not values:
        return {"count": 0}
    out: dict[str, float | int] = {"count": len(values), "avg": mean(values)}
    for percentile in percentiles:
        out[f"p{percentile}"] = _percentile(values, percentile)
    return out


def _percentile(sorted_values: list[float], percentile: int) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _parse_final_decision(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- decision="):
            return stripped.split("=", 1)[1]
    return "unknown"


def _parse_stage7_selected_combos(path: Path) -> list[str]:
    combos: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- combo="):
            combos.append(stripped.split("=", 1)[1])
    return combos


def _smoke_ready_labels(path: Path) -> list[str]:
    rows = _read_csv_rows(path)
    return [
        row["label"]
        for row in rows
        if row.get("window") == "10000w" and row.get("stage7_smoke_ready") == "True"
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT))
    except ValueError:
        return str(path.resolve())
