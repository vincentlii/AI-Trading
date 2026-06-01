from __future__ import annotations

import csv
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stage6DEdgeResult:
    tier_rows: tuple[dict[str, object], ...]
    mfe_push_rows: tuple[dict[str, object], ...]
    combo_rows: tuple[dict[str, object], ...]
    gate_rows: tuple[dict[str, object], ...]
    report: str


def read_jsonl(path: str | Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return tuple(rows)


def read_csv_rows(path: str | Path) -> tuple[dict[str, object], ...]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def build_stage6d_edge_report(
    *,
    sizing_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
) -> Stage6DEdgeResult:
    capped_rows = [row for row in sizing_rows if row.get("sizing_model") == "notional_capped_risk_based"]
    execution_by_id = {str(row.get("candidate_id", "")): row for row in execution_rows}
    tier_rows = _tier_rows(capped_rows, execution_by_id)
    mfe_push_rows = _mfe_push_rows(capped_rows, execution_by_id)
    combo_rows = _combo_rows(sizing_rows, execution_by_id)
    gate_rows = _gate_rows(capped_rows, execution_by_id)
    report = _report(tier_rows=tier_rows, mfe_push_rows=mfe_push_rows, combo_rows=combo_rows, gate_rows=gate_rows)
    return Stage6DEdgeResult(
        tier_rows=tier_rows,
        mfe_push_rows=mfe_push_rows,
        combo_rows=combo_rows,
        gate_rows=gate_rows,
        report=report,
    )


def write_stage6d_artifacts(output_dir: str | Path, result: Stage6DEdgeResult) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "tiers_csv": output / "stage6d_risk_tiers.csv",
        "mfe_push_csv": output / "stage6d_mfe_push.csv",
        "combos_csv": output / "stage6d_quality_combos.csv",
        "gates_csv": output / "stage6d_capped_gates.csv",
        "report_md": output / "stage6d_edge_report.md",
    }
    _write_csv(paths["tiers_csv"], result.tier_rows)
    _write_csv(paths["mfe_push_csv"], result.mfe_push_rows)
    _write_csv(paths["combos_csv"], result.combo_rows)
    _write_csv(paths["gates_csv"], result.gate_rows)
    paths["report_md"].write_text(result.report, encoding="utf-8")
    return paths


def _tier_rows(rows: Sequence[Mapping[str, object]], execution_by_id: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    specs: tuple[tuple[str, Callable[[Mapping[str, object]], str]], ...] = (
        ("actual_risk_pct", lambda row: _actual_risk_tier(_float(row.get("actual_risk_pct_after_cap")))),
        ("risk_utilization", lambda row: _risk_util_tier(_float(row.get("risk_utilization_ratio")))),
        ("required_notional_to_cap", lambda row: _required_to_cap_tier(_float(row.get("required_notional_to_cap_ratio")))),
    )
    output: list[dict[str, object]] = []
    for tier_type, classifier in specs:
        tiers: dict[str, list[Mapping[str, object]]] = {}
        for row in rows:
            tiers.setdefault(classifier(row), []).append(row)
        for tier, group in sorted(tiers.items()):
            output.append(_metric_row(group, execution_by_id, {"tier_type": tier_type, "tier": tier}))
    return tuple(output)


def _mfe_push_rows(rows: Sequence[Mapping[str, object]], execution_by_id: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    groups: dict[str, list[Mapping[str, object]]] = {"no_push": [], "weak_push": [], "strong_push": [], "no_execution": []}
    for row in rows:
        execution = execution_by_id.get(str(row.get("candidate_id", "")))
        mfe = _float(execution.get("mfe_R")) if execution else None
        if mfe is None:
            groups["no_execution"].append(row)
        elif mfe < 0.3:
            groups["no_push"].append(row)
        elif mfe < 1.0:
            groups["weak_push"].append(row)
        else:
            groups["strong_push"].append(row)
    return tuple(_metric_row(group, execution_by_id, {"mfe_push_class": name}) for name, group in groups.items() if group)


def _combo_rows(sizing_rows: Sequence[Mapping[str, object]], execution_by_id: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    specs = _quality_specs()
    output: list[dict[str, object]] = []
    for sizing_model in ("current_risk_based_sizing", "notional_capped_risk_based"):
        model_rows = [row for row in sizing_rows if row.get("sizing_model") == sizing_model]
        for name, predicate in specs:
            group = [row for row in model_rows if predicate(row)]
            row = _metric_row(group, execution_by_id, {"combo": name, "sizing_model": sizing_model})
            row["current_formal_approved"] = sum(1 for item in group if _truthy(item.get("formal_approved")))
            row["capped_proposal_approved"] = sum(1 for item in group if _truthy(item.get("proposal_approved")))
            row["sample_size_warning"] = "trades_lt_30" if int(row["closed_trades"]) < 30 else ""
            output.append(row)
    return tuple(output)


def _gate_rows(rows: Sequence[Mapping[str, object]], execution_by_id: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    approved = [row for row in rows if _truthy(row.get("proposal_approved"))]
    specs: tuple[tuple[str, Callable[[Mapping[str, object]], bool]], ...] = (
        ("Gate A risk-aware", lambda row: (_float(row.get("actual_risk_pct_after_cap")) or 0.0) >= 0.001 and (_float(row.get("risk_utilization_ratio")) or 0.0) >= 0.20),
        ("Gate B balanced risk-aware", lambda row: (_float(row.get("actual_risk_pct_after_cap")) or 0.0) >= 0.0015 and (_float(row.get("risk_utilization_ratio")) or 0.0) >= 0.30),
        ("Gate C quality-first", lambda row: (_is_high_sweep(row) or _is_choch(row)) and (_float(row.get("actual_risk_pct_after_cap")) or 0.0) >= 0.001),
        ("Gate D MFE-informed diagnostic", lambda row: (_is_high_sweep(row) or _is_choch(row) or _is_high_wick(row)) and (_float(row.get("actual_risk_pct_after_cap")) or 0.0) >= 0.001 and (_float(row.get("required_notional_to_cap_ratio")) or 999.0) <= 5.0),
        ("Gate E conservative executable", lambda row: (_float(row.get("actual_risk_pct_after_cap")) or 0.0) >= 0.002 and (_float(row.get("risk_utilization_ratio")) or 0.0) >= 0.40 and (_float(row.get("required_notional_to_cap_ratio")) or 999.0) <= 3.0 and (_is_high_sweep(row) or _is_choch(row))),
    )
    output: list[dict[str, object]] = []
    for name, predicate in specs:
        group = [row for row in approved if predicate(row)]
        row = _metric_row(group, execution_by_id, {"gate": name})
        row["candidates_before_gate"] = len(approved)
        row["approved_after_gate"] = len(group)
        row["rejected_by_gate"] = len(approved) - len(group)
        row["high_sweep_rvol_count"] = sum(1 for item in group if _is_high_sweep(item))
        row["CHOCH_true_count"] = sum(1 for item in group if _is_choch(item))
        row["high_wick_count"] = sum(1 for item in group if _is_high_wick(item))
        row["ETH_C_short_count"] = sum(1 for item in group if item.get("asset") == "ETH" and item.get("profile") == "C" and item.get("direction") == "short")
        output.append(row)
    return tuple(output)


def _metric_row(
    group: Sequence[Mapping[str, object]],
    execution_by_id: Mapping[str, Mapping[str, object]],
    prefix: Mapping[str, object],
) -> dict[str, object]:
    approved = [row for row in group if _truthy(row.get("proposal_approved"))]
    executions = [execution_by_id[str(row.get("candidate_id", ""))] for row in approved if str(row.get("candidate_id", "")) in execution_by_id]
    net_returns = [_net_return_on_notional(execution, _find_row(approved, str(execution.get("candidate_id", "")))) for execution in executions]
    row = dict(prefix)
    row.update(
        {
            "candidates": len(group),
            "proposal_approved": len(approved),
            "closed_trades": len(executions),
            "actual_risk_pct_after_cap_p50": _percentile(_values(group, "actual_risk_pct_after_cap"), 0.50),
            "actual_risk_pct_after_cap_p75": _percentile(_values(group, "actual_risk_pct_after_cap"), 0.75),
            "risk_utilization_ratio_p50": _percentile(_values(group, "risk_utilization_ratio"), 0.50),
            "risk_utilization_ratio_p75": _percentile(_values(group, "risk_utilization_ratio"), 0.75),
            "MFE_R_avg": _avg(_values(executions, "mfe_R")),
            "MFE_R_p50": _percentile(_values(executions, "mfe_R"), 0.50),
            "MFE_R_p75": _percentile(_values(executions, "mfe_R"), 0.75),
            "MFE_R_p90": _percentile(_values(executions, "mfe_R"), 0.90),
            "MFE_R_ge_0_5_ratio": _rate(sum(1 for execution in executions if (_float(execution.get("mfe_R")) or 0.0) >= 0.5), len(executions)),
            "MFE_R_ge_1_0_ratio": _rate(sum(1 for execution in executions if (_float(execution.get("mfe_R")) or 0.0) >= 1.0), len(executions)),
            "MAE_R_avg": _avg(_values(executions, "mae_R")),
            "MAE_R_p50": _percentile(_values(executions, "mae_R"), 0.50),
            "MAE_R_p75": _percentile(_values(executions, "mae_R"), 0.75),
            "net_R_avg": _avg(_values(executions, "net_R")),
            "net_R_p50": _percentile(_values(executions, "net_R"), 0.50),
            "net_return_on_notional_avg": _avg([value for value in net_returns if value is not None]),
            "net_return_on_notional_p50": _percentile([value for value in net_returns if value is not None], 0.50),
            "cost_adjusted_return_on_notional": _avg([value for value in net_returns if value is not None]),
            "time_cut_exit_rate": _rate(sum(1 for execution in executions if execution.get("exit_reason") == "time_cut_exit"), len(executions)),
            "high_sweep_rvol_ratio": _rate(sum(1 for item in group if _is_high_sweep(item)), len(group)),
            "CHOCH_true_ratio": _rate(sum(1 for item in group if _is_choch(item)), len(group)),
            "high_wick_ratio": _rate(sum(1 for item in group if _is_high_wick(item)), len(group)),
            "displacement_after_reclaim_ratio": _rate(sum(1 for item in group if _truthy(item.get("displacement_after_reclaim"))), len(group)),
            "reclaim_within_3_ratio": _rate(sum(1 for item in group if _truthy(item.get("reclaim_within_3"))), len(group)),
            "recent_swing_ratio": _rate(sum(1 for item in group if item.get("structure_level_source") == "recent_swing"), len(group)),
            "rolling_range_ratio": _rate(sum(1 for item in group if item.get("structure_level_source") == "rolling_range"), len(group)),
            "PDH_PDL_ratio": _rate(sum(1 for item in group if _truthy(item.get("pdh_pdl_tag"))), len(group)),
            "EQH_EQL_ratio": _rate(sum(1 for item in group if _truthy(item.get("eqh_eql_tag"))), len(group)),
            "london_open_window_ratio": _rate(sum(1 for item in group if _truthy(item.get("london_open_window"))), len(group)),
            "ny_open_window_ratio": _rate(sum(1 for item in group if _truthy(item.get("ny_open_window"))), len(group)),
            "london_ny_overlap_ratio": _rate(sum(1 for item in group if _truthy(item.get("london_ny_overlap"))), len(group)),
            "high_sweep_rvol_count": sum(1 for item in group if _is_high_sweep(item)),
            "CHOCH_true_count": sum(1 for item in group if _is_choch(item)),
            "high_wick_count": sum(1 for item in group if _is_high_wick(item)),
        }
    )
    return row


def _quality_specs() -> tuple[tuple[str, Callable[[Mapping[str, object]], bool]], ...]:
    return (
        ("high_sweep_rvol only", _is_high_sweep),
        ("CHOCH true only", _is_choch),
        ("high_wick only", _is_high_wick),
        ("displacement_after_reclaim", lambda row: _truthy(row.get("displacement_after_reclaim"))),
        ("high_sweep_rvol + CHOCH true", lambda row: _is_high_sweep(row) and _is_choch(row)),
        ("high_sweep_rvol + high_wick", lambda row: _is_high_sweep(row) and _is_high_wick(row)),
        ("high_sweep_rvol + CHOCH true + high_wick", lambda row: _is_high_sweep(row) and _is_choch(row) and _is_high_wick(row)),
        ("displacement_after_reclaim + high_wick", lambda row: _truthy(row.get("displacement_after_reclaim")) and _is_high_wick(row)),
        ("ETH C short", lambda row: row.get("asset") == "ETH" and row.get("profile") == "C" and row.get("direction") == "short"),
        ("ETH C short + high_sweep_rvol", lambda row: row.get("asset") == "ETH" and row.get("profile") == "C" and row.get("direction") == "short" and _is_high_sweep(row)),
        ("recent_swing + high_sweep_rvol", lambda row: row.get("structure_level_source") == "recent_swing" and _is_high_sweep(row)),
        ("rolling_range + high_sweep_rvol", lambda row: row.get("structure_level_source") == "rolling_range" and _is_high_sweep(row)),
    )


def _report(
    *,
    tier_rows: Sequence[Mapping[str, object]],
    mfe_push_rows: Sequence[Mapping[str, object]],
    combo_rows: Sequence[Mapping[str, object]],
    gate_rows: Sequence[Mapping[str, object]],
) -> str:
    best_combos = sorted(combo_rows, key=lambda row: (_float(row.get("MFE_R_avg")) or -999.0, _float(row.get("net_return_on_notional_avg")) or -999.0), reverse=True)[:8]
    best_gates = sorted(gate_rows, key=lambda row: (_float(row.get("MFE_R_avg")) or -999.0, int(row.get("approved_after_gate") or 0)), reverse=True)
    push_summary = ", ".join(f"{row['mfe_push_class']}={row['closed_trades']}" for row in mfe_push_rows)
    return "\n".join(
        (
            "# Stage 6D Capped Sizing Edge & MFE Quality Report",
            "",
            f"- mfe_push_summary={push_summary}",
            "",
            "## Best Quality Combos",
            *(
                f"- {row['combo']} / {row['sizing_model']}: candidates={row['candidates']} approved={row['proposal_approved']} closed={row['closed_trades']} MFE={row['MFE_R_avg']} net_notional={row['net_return_on_notional_avg']} warning={row.get('sample_size_warning', '')}"
                for row in best_combos
            ),
            "",
            "## Capped Gates",
            *(
                f"- {row['gate']}: approved={row['approved_after_gate']} closed={row['closed_trades']} MFE={row['MFE_R_avg']} MFE>=0.5={row['MFE_R_ge_0_5_ratio']} net_notional={row['net_return_on_notional_avg']}"
                for row in best_gates
            ),
            "",
            "## Risk Tier Note",
            "- Low actual risk is diagnostic, not an automatic rejection. Proposal-only rows without execution are not treated as proven edge.",
        )
    ) + "\n"


def _find_row(rows: Sequence[Mapping[str, object]], candidate_id: str) -> Mapping[str, object] | None:
    for row in rows:
        if str(row.get("candidate_id", "")) == candidate_id:
            return row
    return None


def _net_return_on_notional(execution: Mapping[str, object], row: Mapping[str, object] | None) -> float | None:
    if row is None:
        return None
    net_r = _float(execution.get("net_R"))
    risk_amount = _float(row.get("actual_risk_amount_after_cap"))
    notional = _float(row.get("capped_position_notional"))
    if net_r is None or risk_amount is None or notional is None or notional <= 0:
        return None
    return net_r * risk_amount / notional


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _actual_risk_tier(value: float | None) -> str:
    if value is None:
        return "unknown_risk"
    if value < 0.001:
        return "tiny_risk"
    if value < 0.002:
        return "low_risk"
    if value < 0.0035:
        return "medium_risk"
    return "near_target_risk"


def _risk_util_tier(value: float | None) -> str:
    if value is None:
        return "unknown_utilization"
    if value < 0.20:
        return "very_low_utilization"
    if value < 0.40:
        return "low_utilization"
    if value < 0.70:
        return "medium_utilization"
    return "high_utilization"


def _required_to_cap_tier(value: float | None) -> str:
    if value is None:
        return "unknown_required_notional"
    if value <= 1.5:
        return "near_cap"
    if value <= 3.0:
        return "moderate_above_cap"
    if value <= 5.0:
        return "far_above_cap"
    return "extreme_above_cap"


def _is_high_sweep(row: Mapping[str, object]) -> bool:
    return row.get("sweep_rvol_tier") == "high_sweep_rvol"


def _is_choch(row: Mapping[str, object]) -> bool:
    return row.get("choch_tag") == "choch_true"


def _is_high_wick(row: Mapping[str, object]) -> bool:
    return row.get("wick_ratio_tier") == "high_wick"


def _values(rows: Sequence[Mapping[str, object]], field: str) -> list[float]:
    return [value for row in rows if (value := _float(row.get(field))) is not None]


def _avg(values: Sequence[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _percentile(values: Sequence[float], q: float) -> float | None:
    numbers = sorted(float(value) for value in values)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * q
    low = int(position)
    high = min(low + 1, len(numbers) - 1)
    fraction = position - low
    return numbers[low] * (1.0 - fraction) + numbers[high] * fraction


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


__all__ = (
    "Stage6DEdgeResult",
    "build_stage6d_edge_report",
    "read_csv_rows",
    "read_jsonl",
    "write_stage6d_artifacts",
)
