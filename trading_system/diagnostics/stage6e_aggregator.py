from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stage6EAggregationResult:
    comparison_rows: tuple[dict[str, object], ...]
    decision: str
    report: str


TRACKED_LABELS = (
    "baseline",
    "high_sweep_rvol only",
    "CHOCH true only",
    "high_wick",
    "high_sweep_rvol + CHOCH true + high_wick",
    "displacement_after_reclaim",
    "displacement_after_reclaim + high_wick",
    "ETH C short",
)


def build_stage6e_aggregation(*, window_results: Mapping[str, Mapping[str, Sequence[Mapping[str, object]]]]) -> Stage6EAggregationResult:
    rows: list[dict[str, object]] = []
    for window, artifacts in sorted(window_results.items()):
        combo_rows = _as_rows(artifacts.get("combo_rows", ()))
        gate_rows = _as_rows(artifacts.get("gate_rows", ()))
        rows.extend(_baseline_rows(window, gate_rows))
        rows.extend(_tracked_combo_rows(window, combo_rows))
    _apply_smoke_readiness(rows)
    decision = _stage7_decision(rows)
    report = _report(rows, decision)
    return Stage6EAggregationResult(comparison_rows=tuple(rows), decision=decision, report=report)


def read_stage6e_windows(paths: Mapping[str, str | Path]) -> dict[str, dict[str, tuple[dict[str, object], ...]]]:
    windows: dict[str, dict[str, tuple[dict[str, object], ...]]] = {}
    for window, root in paths.items():
        directory = Path(root)
        windows[window] = {
            "combo_rows": _read_csv(directory / "stage6d_quality_combos.csv"),
            "gate_rows": _read_csv(directory / "stage6d_capped_gates.csv"),
        }
    return windows


def _as_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, Mapping):
        return (value,)
    return tuple(row for row in value if isinstance(row, Mapping)) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def write_stage6e_aggregation(output_dir: str | Path, result: Stage6EAggregationResult) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "stage6e_aggregated_comparison.csv"
    report_path = output / "stage6e_aggregator_final_report.md"
    _write_csv(csv_path, result.comparison_rows)
    report_path.write_text(result.report, encoding="utf-8")
    return {"comparison_csv": csv_path, "report_md": report_path}


def _baseline_rows(window: str, gate_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    baseline = next((row for row in gate_rows if row.get("gate") == "Gate A risk-aware"), None)
    return [] if baseline is None else [_comparison_row(window, "baseline", baseline)]


def _tracked_combo_rows(window: str, combo_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for label in TRACKED_LABELS:
        if label == "baseline":
            continue
        row = _best_combo_row(label, combo_rows)
        if row is not None:
            output.append(_comparison_row(window, label, row))
    return output


def _best_combo_row(label: str, rows: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    aliases = {
        "high_wick": ("high_wick only",),
        "displacement_after_reclaim": ("displacement_after_reclaim",),
        "displacement_after_reclaim + high_wick": ("displacement_after_reclaim + high_wick",),
    }
    names = aliases.get(label, (label,))
    candidates = [row for row in rows if str(row.get("combo", "")) in names or str(row.get("combo", "")).startswith(names)]
    if not candidates:
        return None
    return max(candidates, key=lambda row: (_float(row.get("MFE_R_avg")) or -999.0, _int(row.get("closed_trades"))))


def _comparison_row(window: str, label: str, row: Mapping[str, object]) -> dict[str, object]:
    closed = _int(row.get("closed_trades"))
    mfe_avg = _float(row.get("MFE_R_avg"))
    mfe_05 = _float(row.get("MFE_R_ge_0_5_ratio"))
    mfe_10 = _float(row.get("MFE_R_ge_1_0_ratio"))
    net_r = _float(row.get("net_R_avg"))
    net_notional = _float(row.get("net_return_on_notional_avg"))
    time_cut = _float(row.get("time_cut_exit_rate"))
    return {
        "window": window,
        "label": label,
        "closed_trades": closed,
        "MFE_R_avg": mfe_avg,
        "MFE_R_p50": _float(row.get("MFE_R_p50")),
        "MFE_R_p75": _float(row.get("MFE_R_p75")),
        "MFE_R_p90": _float(row.get("MFE_R_p90")),
        "MFE_R_ge_0_5_ratio": mfe_05,
        "MFE_R_ge_1_0_ratio": mfe_10,
        "net_R_avg": net_r,
        "net_return_on_notional_avg": net_notional,
        "time_cut_exit_rate": time_cut,
        "sample_size_warning": "trades_lt_30" if closed < 30 else "trades_lt_40" if closed < 40 else "",
        "stage7_smoke_ready": False,
        "window_smoke_ready": False,
    }


def _apply_smoke_readiness(rows: list[dict[str, object]]) -> None:
    baselines = {str(row["window"]): row for row in rows if row.get("label") == "baseline"}
    windows = set(baselines)
    ready_by_label: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        label = str(row.get("label", ""))
        if label == "baseline":
            continue
        baseline = baselines.get(str(row.get("window", "")))
        row["window_smoke_ready"] = _beats_baseline(row, baseline)
        ready_by_label.setdefault(label, []).append(row)
    for label, group in ready_by_label.items():
        covered = {str(row.get("window", "")) for row in group}
        consistent = covered == windows and all(bool(row.get("window_smoke_ready")) for row in group)
        for row in group:
            row["stage7_smoke_ready"] = consistent


def _beats_baseline(row: Mapping[str, object], baseline: Mapping[str, object] | None) -> bool:
    if baseline is None:
        return False
    return (
        _int(row.get("closed_trades")) >= 40
        and (_float(row.get("MFE_R_avg")) or -999.0) > (_float(baseline.get("MFE_R_avg")) or 999.0)
        and (_float(row.get("MFE_R_ge_0_5_ratio")) or -999.0) > (_float(baseline.get("MFE_R_ge_0_5_ratio")) or 999.0)
        and (_float(row.get("MFE_R_ge_1_0_ratio")) or -999.0) >= (_float(baseline.get("MFE_R_ge_1_0_ratio")) or 999.0)
        and (
            (_float(row.get("net_R_avg")) or -999.0) >= (_float(baseline.get("net_R_avg")) or 999.0)
            or (_float(row.get("net_return_on_notional_avg")) or -999.0) >= (_float(baseline.get("net_return_on_notional_avg")) or 999.0)
        )
        and (_float(row.get("time_cut_exit_rate")) or 999.0) < (_float(baseline.get("time_cut_exit_rate")) or -999.0)
    )


def _stage7_decision(rows: Sequence[Mapping[str, object]]) -> str:
    ready = [row for row in rows if row.get("label") != "baseline" and row.get("stage7_smoke_ready")]
    if ready:
        return "stage7_smoke_candidate_ready"
    partial = [row for row in rows if row.get("label") != "baseline" and _int(row.get("closed_trades")) >= 30 and (_float(row.get("MFE_R_ge_0_5_ratio")) or 0.0) >= 0.50]
    if partial:
        return "wait_for_10000w_or_full_confirmation"
    return "stage6f_entry_confirmation_upgrade"


def _report(rows: Sequence[Mapping[str, object]], decision: str) -> str:
    lines = ["# Stage 6E Aggregator Final Report", "", f"- decision={decision}", "", "## Window Comparison"]
    for row in rows:
        lines.append(
            f"- {row['window']} {row['label']}: closed={row['closed_trades']} "
            f"MFE={row['MFE_R_avg']} P50={row['MFE_R_p50']} P75={row['MFE_R_p75']} P90={row['MFE_R_p90']} MFE>=0.5={row['MFE_R_ge_0_5_ratio']} "
            f"MFE>=1.0={row['MFE_R_ge_1_0_ratio']} net_R={row['net_R_avg']} "
            f"net_notional={row['net_return_on_notional_avg']} time_cut={row['time_cut_exit_rate']} "
            f"warning={row['sample_size_warning']} window_ready={row['window_smoke_ready']} smoke_ready={row['stage7_smoke_ready']}"
        )
    lines.extend(
        (
            "",
            "## Rule",
            "- Stage 7 smoke is allowed only when a non-baseline combo has >=40 closed trades, stronger MFE, higher MFE>=0.5, MFE>=1.0 not below baseline, non-worse returns, lower time-cut pressure, and consistent readiness across all aggregated windows.",
            "- This aggregator does not formalize capped sizing and does not modify strategy logic.",
        )
    )
    return "\n".join(lines) + "\n"


def _read_csv(path: Path) -> tuple[dict[str, object], ...]:
    if not path.exists():
        return ()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


__all__ = (
    "Stage6EAggregationResult",
    "build_stage6e_aggregation",
    "read_stage6e_windows",
    "write_stage6e_aggregation",
)
