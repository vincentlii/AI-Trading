from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stage6QualityResult:
    run_rows: tuple[dict[str, object], ...]
    tag_rows: tuple[dict[str, object], ...]
    margin_rows: tuple[dict[str, object], ...]
    margin_summary: dict[str, object]
    time_cut_summary: dict[str, object]
    report: str


def read_jsonl(path: str | Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return tuple(rows)


def build_stage6_quality_report(
    *,
    filter_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
    equity: float,
    max_single_notional_pct: float,
) -> Stage6QualityResult:
    execution_by_id = {str(row.get("candidate_id", "")): row for row in execution_rows}
    run_rows = tuple(_run_row(spec, filter_rows, execution_by_id) for spec in _run_specs())
    tag_rows = _tag_performance_rows(filter_rows, execution_by_id)
    margin_rows, margin_summary = _margin_diagnostics(filter_rows, equity=equity, max_single_notional_pct=max_single_notional_pct)
    time_cut_summary = _time_cut_summary(execution_rows)
    report = _report(run_rows=run_rows, tag_rows=tag_rows, margin_summary=margin_summary, time_cut_summary=time_cut_summary)
    return Stage6QualityResult(
        run_rows=run_rows,
        tag_rows=tag_rows,
        margin_rows=margin_rows,
        margin_summary=margin_summary,
        time_cut_summary=time_cut_summary,
        report=report,
    )


def write_stage6_artifacts(output_dir: str | Path, result: Stage6QualityResult) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "runs_csv": output / "stage6_quality_runs.csv",
        "tags_csv": output / "stage6_tag_performance.csv",
        "margin_csv": output / "stage6_margin_stop_near.csv",
        "summary_json": output / "stage6_summary.json",
        "report_md": output / "stage6_quality_report.md",
    }
    _write_csv(paths["runs_csv"], result.run_rows)
    _write_csv(paths["tags_csv"], result.tag_rows)
    _write_csv(paths["margin_csv"], result.margin_rows)
    paths["summary_json"].write_text(
        json.dumps({"margin_summary": result.margin_summary, "time_cut_summary": result.time_cut_summary}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["report_md"].write_text(result.report, encoding="utf-8")
    return paths


def _run_specs() -> tuple[tuple[str, Callable[[Mapping[str, object]], bool], str], ...]:
    return (
        ("Run 0 Baseline", lambda row: True, ""),
        ("Run 1 CHoCH filter", lambda row: row.get("choch_tag") == "choch_true", "quality_choch_required"),
        ("Run 2 Trend alignment filter", lambda row: row.get("trend_alignment_tag") == "trend_aligned", "quality_trend_required"),
        ("Run 3 Wick filter", lambda row: row.get("wick_ratio_tier") in {"medium_wick", "high_wick"}, "quality_low_wick"),
        ("Run 4 Sweep RVOL filter", lambda row: row.get("sweep_rvol_tier") in {"normal_sweep_rvol", "high_sweep_rvol"}, "quality_low_or_unknown_sweep_rvol"),
        ("Run 5 Reclaim RVOL filter", lambda row: row.get("reclaim_rvol_tier") in {"ideal_reclaim", "acceptable_reclaim"}, "quality_high_or_unknown_reclaim_rvol"),
        (
            "Run 6 Combined Conservative",
            lambda row: row.get("choch_tag") == "choch_true"
            and row.get("trend_alignment_tag") == "trend_aligned"
            and row.get("wick_ratio_tier") in {"medium_wick", "high_wick"}
            and row.get("sweep_rvol_tier") in {"normal_sweep_rvol", "high_sweep_rvol"}
            and row.get("reclaim_rvol_tier") in {"ideal_reclaim", "acceptable_reclaim"},
            "quality_conservative_failed",
        ),
        (
            "Run 7 Combined Balanced",
            lambda row: (row.get("choch_tag") == "choch_true" or row.get("trend_alignment_tag") == "trend_aligned")
            and row.get("wick_ratio_tier") in {"medium_wick", "high_wick"}
            and row.get("sweep_rvol_tier") in {"normal_sweep_rvol", "high_sweep_rvol"}
            and row.get("reclaim_rvol_tier") in {"ideal_reclaim", "acceptable_reclaim"},
            "quality_balanced_failed",
        ),
    )


def _run_row(
    spec: tuple[str, Callable[[Mapping[str, object]], bool], str],
    filter_rows: Sequence[Mapping[str, object]],
    execution_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    name, predicate, quality_reason = spec
    pass_quality = [row for row in filter_rows if predicate(row)]
    approved = [row for row in pass_quality if row.get("formal_approved")]
    approved_ids = {str(row.get("candidate_id", "")) for row in approved}
    executions = [row for key, row in execution_by_id.items() if key in approved_ids]
    reject_reasons = Counter()
    for row in filter_rows:
        if not predicate(row):
            reject_reasons[quality_reason or "quality_filter_failed"] += 1
        elif not row.get("formal_approved"):
            reject_reasons[str(row.get("reject_reason") or "rejected")] += 1
    return {
        "run": name,
        "fresh_candidates": len(filter_rows),
        "quality_pass": len(pass_quality),
        "formal_approved": len(approved),
        "closed_trades": len(executions),
        "reject_reason_top": dict(reject_reasons.most_common(5)),
        "approval_rate": _rate(len(approved), len(filter_rows)),
        "MAE_R_avg": _avg(_values(executions, "mae_R")),
        "MAE_R_p50": _percentile(_values(executions, "mae_R"), 0.50),
        "MAE_R_p75": _percentile(_values(executions, "mae_R"), 0.75),
        "MFE_R_avg": _avg(_values(executions, "mfe_R")),
        "MFE_R_p50": _percentile(_values(executions, "mfe_R"), 0.50),
        "MFE_R_p75": _percentile(_values(executions, "mfe_R"), 0.75),
        "net_R_avg": _avg(_values(executions, "net_R")),
        "net_R_p50": _percentile(_values(executions, "net_R"), 0.50),
        "net_R_p75": _percentile(_values(executions, "net_R"), 0.75),
        "time_cut_exit_count": sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"),
        "time_cut_exit_rate": _rate(sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"), len(executions)),
        "same_bar_ambiguous_count": sum(1 for row in executions if row.get("same_bar_ambiguous")),
        "liquidation_event_count": sum(1 for row in executions if row.get("liquidation_event")),
        "funding_sum": sum(_float(row.get("funding_paid_or_received")) or 0.0 for row in executions),
        "stop_atr_p50": _percentile(_values(pass_quality, "stop_atr"), 0.50),
        "stop_atr_p90": _percentile(_values(pass_quality, "stop_atr"), 0.90),
        "margin_required_too_high_count": sum(1 for row in pass_quality if row.get("reject_reason") == "margin_required_too_high"),
        "stop_distance_too_near_count": sum(1 for row in pass_quality if row.get("reject_reason") == "stop_distance_too_near"),
        "cost_after_r_too_low_count": sum(1 for row in pass_quality if row.get("reject_reason") == "cost_after_r_too_low"),
    }


def _tag_performance_rows(
    filter_rows: Sequence[Mapping[str, object]],
    execution_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    specs = (
        ("CHoCH", "choch_tag"),
        ("trend_alignment", "trend_alignment_tag"),
        ("wick_ratio", "wick_ratio_tier"),
        ("sweep_rvol", "sweep_rvol_tier"),
        ("reclaim_rvol", "reclaim_rvol_tier"),
        ("liquidity_score", "liquidity_score_tier"),
        ("structure_source", "structure_level_source"),
        ("asset_profile_direction", "asset_profile_direction"),
    )
    augmented = []
    for row in filter_rows:
        copy = dict(row)
        copy["asset_profile_direction"] = f"{row.get('asset', '')} {row.get('profile', '')} {row.get('direction', '')}".strip()
        augmented.append(copy)

    output: list[dict[str, object]] = []
    for tag_type, field in specs:
        grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in augmented:
            grouped[str(row.get(field, "unknown"))].append(row)
        for value, group in sorted(grouped.items()):
            approved_ids = {str(row.get("candidate_id", "")) for row in group if row.get("formal_approved")}
            executions = [row for key, row in execution_by_id.items() if key in approved_ids]
            reasons = Counter(str(row.get("reject_reason", "")) for row in group if row.get("reject_reason"))
            output.append(
                {
                    "tag_type": tag_type,
                    "tag_value": value,
                    "fresh_candidates": len(group),
                    "formal_approved": len(approved_ids),
                    "closed_trades": len(executions),
                    "approval_rate": _rate(len(approved_ids), len(group)),
                    "MAE_R_avg": _avg(_values(executions, "mae_R")),
                    "MAE_R_p50": _percentile(_values(executions, "mae_R"), 0.50),
                    "MAE_R_p75": _percentile(_values(executions, "mae_R"), 0.75),
                    "MFE_R_avg": _avg(_values(executions, "mfe_R")),
                    "MFE_R_p50": _percentile(_values(executions, "mfe_R"), 0.50),
                    "MFE_R_p75": _percentile(_values(executions, "mfe_R"), 0.75),
                    "net_R_avg": _avg(_values(executions, "net_R")),
                    "net_R_p50": _percentile(_values(executions, "net_R"), 0.50),
                    "time_cut_exit_count": sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"),
                    "time_cut_exit_rate": _rate(sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"), len(executions)),
                    "stop_atr_p50": _percentile(_values(group, "stop_atr"), 0.50),
                    "stop_atr_p90": _percentile(_values(group, "stop_atr"), 0.90),
                    "margin_required_too_high_count": reasons["margin_required_too_high"],
                    "stop_distance_too_near_count": reasons["stop_distance_too_near"],
                    "main_reject_reason": reasons.most_common(1)[0][0] if reasons else "",
                }
            )
    return tuple(output)


def _margin_diagnostics(
    filter_rows: Sequence[Mapping[str, object]],
    *,
    equity: float,
    max_single_notional_pct: float,
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    rejected = [row for row in filter_rows if row.get("reject_reason") in {"margin_required_too_high", "stop_distance_too_near"}]
    grouped: dict[tuple[str, str, str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rejected:
        key = (
            str(row.get("asset", "")),
            str(row.get("profile", "")),
            str(row.get("direction", "")),
            _stop_atr_tier(_float(row.get("stop_atr"))),
            _notional_tier(_float(row.get("notional")), equity),
            _leverage_tier(_float(row.get("leverage"))),
        )
        grouped[key].append(row)
    rows = tuple(
        {
            "asset": key[0],
            "profile": key[1],
            "direction": key[2],
            "stop_atr_tier": key[3],
            "notional_tier": key[4],
            "leverage_tier": key[5],
            "count": len(group),
            "stop_atr_p50": _percentile(_values(group, "stop_atr"), 0.50),
            "notional_p50": _percentile(_values(group, "notional"), 0.50),
            "margin_required_p50": _percentile(_values(group, "margin_required"), 0.50),
            "notional_equity_ratio_p50": _percentile([(_float(row.get("notional")) or 0.0) / equity for row in group], 0.50),
            "stop_distance_pct_p50": _percentile([_stop_distance_pct(row) for row in group], 0.50),
        }
        for key, group in sorted(grouped.items())
    )
    current_cap = equity * max_single_notional_pct
    summary = {
        "margin_required_too_high": sum(1 for row in filter_rows if row.get("reject_reason") == "margin_required_too_high"),
        "stop_distance_too_near": sum(1 for row in filter_rows if row.get("reject_reason") == "stop_distance_too_near"),
        "stop_near_margin_overlap": sum(1 for row in filter_rows if row.get("reject_reason") == "stop_distance_too_near" and (_float(row.get("notional")) or 0.0) > current_cap),
        "shadow_max_single_notional_current_pass": _notional_shadow_pass(filter_rows, current_cap),
        "shadow_max_single_notional_1_5x_pass": _notional_shadow_pass(filter_rows, current_cap * 1.5),
        "shadow_max_single_notional_2x_pass": _notional_shadow_pass(filter_rows, current_cap * 2.0),
        "shadow_min_stop_0_5_pass": _min_stop_shadow_pass(filter_rows, 0.5),
        "shadow_min_stop_0_8_pass": _min_stop_shadow_pass(filter_rows, 0.8),
        "shadow_min_stop_1_0_pass": _min_stop_shadow_pass(filter_rows, 1.0),
        "risk_pct_used": 0.005,
        "formal_notional_cap_pct": max_single_notional_pct,
    }
    return rows, summary


def _time_cut_summary(execution_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    time_cut_rows = [row for row in execution_rows if row.get("exit_reason") == "time_cut_exit"]
    return {
        "time_cut_bars_current": 8,
        "time_cut_min_mfe_r_current": 0.5,
        "closed_trades": len(execution_rows),
        "time_cut_exit_count": len(time_cut_rows),
        "time_cut_exit_rate": _rate(len(time_cut_rows), len(execution_rows)),
        "bars_to_MFE_p50": _percentile(_values(execution_rows, "bars_to_MFE"), 0.50),
        "MFE_R_avg": _avg(_values(execution_rows, "mfe_R")),
        "MFE_R_p75": _percentile(_values(execution_rows, "mfe_R"), 0.75),
        "MFE_R_p90": _percentile(_values(execution_rows, "mfe_R"), 0.90),
        "net_R_avg": _avg(_values(execution_rows, "net_R")),
        "shadow_time_cut_2x": "requires replay with reversal_time_cut_bars=16",
        "shadow_lower_min_mfe": "requires replay with reversal_time_cut_min_mfe_r below 0.5",
        "shadow_no_time_cut": "requires replay with time cut disabled",
    }


def _report(
    *,
    run_rows: Sequence[Mapping[str, object]],
    tag_rows: Sequence[Mapping[str, object]],
    margin_summary: Mapping[str, object],
    time_cut_summary: Mapping[str, object],
) -> str:
    best_runs = sorted(run_rows, key=lambda row: (_float(row.get("MFE_R_avg")) or -999.0, _float(row.get("net_R_avg")) or -999.0), reverse=True)
    top_tags = sorted(tag_rows, key=lambda row: (_float(row.get("MFE_R_avg")) or -999.0, _float(row.get("net_R_avg")) or -999.0), reverse=True)[:10]
    return "\n".join(
        (
            "# Stage 6 Quality Filter Recovery Report",
            "",
            "## Run Summary",
            *(
                f"- {row['run']}: quality_pass={row['quality_pass']} formal={row['formal_approved']} closed={row['closed_trades']} "
                f"MFE_avg={row['MFE_R_avg']} net_avg={row['net_R_avg']} time_cut={row['time_cut_exit_count']}"
                for row in run_rows
            ),
            "",
            "## Best Tags",
            *(
                f"- {row['tag_type']}={row['tag_value']}: fresh={row['fresh_candidates']} formal={row['formal_approved']} "
                f"MFE_avg={row['MFE_R_avg']} net_avg={row['net_R_avg']} main_reject={row['main_reject_reason']}"
                for row in top_tags
            ),
            "",
            "## Margin / Stop Near",
            f"- margin_required_too_high={margin_summary.get('margin_required_too_high')}",
            f"- stop_distance_too_near={margin_summary.get('stop_distance_too_near')}",
            f"- stop_near_margin_overlap={margin_summary.get('stop_near_margin_overlap')}",
            f"- shadow_notional_current/1.5x/2x={margin_summary.get('shadow_max_single_notional_current_pass')}/"
            f"{margin_summary.get('shadow_max_single_notional_1_5x_pass')}/{margin_summary.get('shadow_max_single_notional_2x_pass')}",
            "",
            "## Time Cut",
            f"- closed_trades={time_cut_summary.get('closed_trades')}",
            f"- time_cut_exit_count={time_cut_summary.get('time_cut_exit_count')}",
            f"- MFE_R_avg={time_cut_summary.get('MFE_R_avg')}",
            f"- net_R_avg={time_cut_summary.get('net_R_avg')}",
            "",
            f"best_run_by_MFE={best_runs[0]['run'] if best_runs else ''}",
        )
    ) + "\n"


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
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stop_atr_tier(value: float | None) -> str:
    if value is None:
        return "unknown_stop_atr"
    if value < 0.8:
        return "too_near"
    if value <= 3.0:
        return "formal_range"
    return "too_far"


def _notional_tier(value: float | None, equity: float) -> str:
    if value is None or equity <= 0:
        return "unknown_notional"
    ratio = value / equity
    if ratio <= 0.15:
        return "within_15pct"
    if ratio <= 0.30:
        return "15_to_30pct"
    if ratio <= 1.0:
        return "30_to_100pct"
    return "above_100pct"


def _leverage_tier(value: float | None) -> str:
    if value is None:
        return "unknown_leverage"
    if value <= 0.15:
        return "within_single_cap"
    if value <= 1.0:
        return "under_1x"
    return "above_1x"


def _stop_distance_pct(row: Mapping[str, object]) -> float:
    entry = _float(row.get("entry_price")) or 0.0
    distance = _float(row.get("stop_distance_abs")) or 0.0
    return 0.0 if entry <= 0 else distance / entry


def _notional_shadow_pass(rows: Sequence[Mapping[str, object]], cap: float) -> int:
    return sum(1 for row in rows if (_float(row.get("notional")) or 0.0) <= cap)


def _min_stop_shadow_pass(rows: Sequence[Mapping[str, object]], min_stop: float) -> int:
    return sum(1 for row in rows if (value := _float(row.get("stop_atr"))) is not None and min_stop <= value <= 3.0)


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
    "Stage6QualityResult",
    "build_stage6_quality_report",
    "read_jsonl",
    "write_stage6_artifacts",
)
