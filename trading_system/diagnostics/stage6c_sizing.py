from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stage6CSizingResult:
    sizing_rows: tuple[dict[str, object], ...]
    sizing_summary_rows: tuple[dict[str, object], ...]
    subgroup_rows: tuple[dict[str, object], ...]
    report: str


def default_setup_sizing_policies() -> dict[str, dict[str, object]]:
    return {
        "liquidity_reversal": {
            "risk_policy_name": "liquidity_reversal_notional_cap_proposal_v1",
            "sizing_model": "notional_capped_risk_based",
            "target_risk_pct": 0.005,
            "max_single_notional_pct": 0.15,
            "allow_notional_cap": True,
            "min_actual_risk_pct_after_cap": 0.001,
            "reject_if_risk_utilization_too_low": True,
            "stop_model": "structure_extreme_buffer",
            "exit_model": "fast_reversal_time_cut_or_structure_target",
        },
        "trend_continuation": {
            "risk_policy_name": "trend_continuation_placeholder_v1",
            "sizing_model": "risk_based_or_volatility_based",
            "target_risk_pct": 0.005,
            "max_single_notional_pct": 0.15,
            "allow_notional_cap": False,
            "stop_model": "pullback_structure_or_atr_trailing",
            "exit_model": "partial_tp_plus_trailing",
        },
    }


def read_jsonl(path: str | Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return tuple(rows)


def build_stage6c_sizing_report(
    *,
    filter_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
    equity: float,
    max_single_notional_pct: float,
    min_actual_risk_pct_after_cap: float = 0.001,
    window_label: str = "",
) -> Stage6CSizingResult:
    execution_by_id = {str(row.get("candidate_id", "")): row for row in execution_rows}
    policies = default_setup_sizing_policies()
    sizing_rows: list[dict[str, object]] = []
    for row in filter_rows:
        sizing_rows.append(
            _sizing_row(
                row,
                sizing_model="current_risk_based_sizing",
                equity=equity,
                max_single_notional_pct=max_single_notional_pct,
                min_actual_risk_pct_after_cap=min_actual_risk_pct_after_cap,
                policy=policies["liquidity_reversal"],
                window_label=window_label,
            )
        )
        sizing_rows.append(
            _sizing_row(
                row,
                sizing_model="notional_capped_risk_based",
                equity=equity,
                max_single_notional_pct=max_single_notional_pct,
                min_actual_risk_pct_after_cap=min_actual_risk_pct_after_cap,
                policy=policies["liquidity_reversal"],
                window_label=window_label,
            )
        )
    sizing_rows_tuple = tuple(sizing_rows)
    summary_rows = tuple(_summary_row(model, sizing_rows_tuple, execution_by_id) for model in ("current_risk_based_sizing", "notional_capped_risk_based"))
    subgroup_rows = _subgroup_rows(sizing_rows_tuple, execution_by_id)
    report = _report(summary_rows=summary_rows, subgroup_rows=subgroup_rows, policies=policies, window_label=window_label)
    return Stage6CSizingResult(
        sizing_rows=sizing_rows_tuple,
        sizing_summary_rows=summary_rows,
        subgroup_rows=subgroup_rows,
        report=report,
    )


def write_stage6c_artifacts(output_dir: str | Path, result: Stage6CSizingResult) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "sizing_csv": output / "stage6c_sizing_candidates.csv",
        "summary_csv": output / "stage6c_sizing_summary.csv",
        "subgroups_csv": output / "stage6c_sizing_subgroups.csv",
        "report_md": output / "stage6c_sizing_report.md",
    }
    _write_csv(paths["sizing_csv"], result.sizing_rows)
    _write_csv(paths["summary_csv"], result.sizing_summary_rows)
    _write_csv(paths["subgroups_csv"], result.subgroup_rows)
    paths["report_md"].write_text(result.report, encoding="utf-8")
    return paths


def _sizing_row(
    row: Mapping[str, object],
    *,
    sizing_model: str,
    equity: float,
    max_single_notional_pct: float,
    min_actual_risk_pct_after_cap: float,
    policy: Mapping[str, object],
    window_label: str,
) -> dict[str, object]:
    entry = _float(row.get("entry_price")) or 0.0
    stop_distance = _float(row.get("stop_distance_abs"))
    if stop_distance is None:
        stop = _float(row.get("stop_price")) or 0.0
        stop_distance = abs(entry - stop)
    target_risk_pct = _float(row.get("risk_pct")) or float(policy.get("target_risk_pct") or 0.005)
    target_risk_amount = _float(row.get("risk_amount")) or equity * target_risk_pct
    raw_notional = _float(row.get("raw_position_notional_by_risk"))
    if raw_notional is None:
        qty = _float(row.get("raw_position_qty_by_risk")) or 0.0
        raw_notional = abs(qty * entry)
    max_single_notional = _float(row.get("max_single_notional")) or equity * max_single_notional_pct
    capped_by_notional = raw_notional > max_single_notional
    if sizing_model == "notional_capped_risk_based":
        position_notional = min(raw_notional, max_single_notional)
    else:
        position_notional = raw_notional
    capped_qty = 0.0 if entry <= 0 else position_notional / entry
    actual_risk_amount = 0.0 if entry <= 0 else target_risk_amount * (position_notional / raw_notional if raw_notional > 0 else 0.0)
    actual_risk_pct = 0.0 if equity <= 0 else actual_risk_amount / equity
    risk_utilization = 0.0 if target_risk_pct <= 0 else actual_risk_pct / target_risk_pct
    required_notional_pct = 0.0 if equity <= 0 else raw_notional / equity
    required_to_cap = 0.0 if max_single_notional <= 0 else raw_notional / max_single_notional
    margin_required = position_notional
    margin_required_pct = 0.0 if equity <= 0 else margin_required / equity
    stop_near_flag = _stop_near_quality_flag(
        required_notional_to_cap_ratio=required_to_cap,
        actual_risk_pct_after_cap=actual_risk_pct,
        min_actual_risk_pct_after_cap=min_actual_risk_pct_after_cap,
    )
    formal_approved = bool(row.get("formal_approved"))
    proposal_approved = _proposal_approved(
        row,
        sizing_model=sizing_model,
        formal_approved=formal_approved,
        actual_risk_pct=actual_risk_pct,
        min_actual_risk_pct=min_actual_risk_pct_after_cap,
        margin_required_pct=margin_required_pct,
        max_single_notional_pct=max_single_notional_pct,
    )
    output = dict(row)
    output.update(
        {
            "window": window_label,
            "setup": str(row.get("setup") or "liquidity_reversal"),
            "risk_policy_name": str(policy.get("risk_policy_name") or ""),
            "sizing_model": sizing_model,
            "stop_model": str(policy.get("stop_model") or ""),
            "exit_model": str(policy.get("exit_model") or ""),
            "target_risk_pct": target_risk_pct,
            "target_risk_amount": target_risk_amount,
            "raw_position_notional_by_risk": raw_notional,
            "max_single_notional": max_single_notional,
            "max_single_notional_pct": max_single_notional_pct,
            "capped_by_notional": capped_by_notional and sizing_model == "notional_capped_risk_based",
            "capped_position_qty": capped_qty,
            "capped_position_notional": position_notional,
            "actual_risk_amount_after_cap": actual_risk_amount,
            "actual_risk_pct_after_cap": actual_risk_pct,
            "risk_utilization_ratio": risk_utilization,
            "margin_required": margin_required,
            "margin_required_pct": margin_required_pct,
            "notional_to_equity_pct": margin_required_pct,
            "required_notional_pct": required_notional_pct,
            "required_notional_to_cap_ratio": required_to_cap,
            "stop_near_quality_flag": stop_near_flag,
            "proposal_approved": proposal_approved,
            "formal_approved": formal_approved,
            "proposal_only": sizing_model == "notional_capped_risk_based",
            "net_return_on_notional": None,
        }
    )
    return output


def _proposal_approved(
    row: Mapping[str, object],
    *,
    sizing_model: str,
    formal_approved: bool,
    actual_risk_pct: float,
    min_actual_risk_pct: float,
    margin_required_pct: float,
    max_single_notional_pct: float,
) -> bool:
    if sizing_model == "current_risk_based_sizing":
        return formal_approved
    if formal_approved:
        return True
    reject_reason = str(row.get("reject_reason") or "")
    stop_atr = _float(row.get("stop_atr"))
    target_r = _float(row.get("target_r"))
    cost_after_r = _float(row.get("cost_after_r"))
    liquidation_distance = _float(row.get("liquidation_distance_pct"))
    return (
        reject_reason == "margin_required_too_high"
        and stop_atr is not None
        and 0.8 <= stop_atr <= 3.0
        and target_r is not None
        and target_r >= 1.5
        and (cost_after_r is None or cost_after_r > 0)
        and actual_risk_pct >= min_actual_risk_pct
        and margin_required_pct <= max_single_notional_pct + 1e-12
        and (liquidation_distance is None or liquidation_distance > 0.02)
    )


def _stop_near_quality_flag(
    *,
    required_notional_to_cap_ratio: float,
    actual_risk_pct_after_cap: float,
    min_actual_risk_pct_after_cap: float,
) -> str:
    if required_notional_to_cap_ratio > 2.0:
        return "required_notional_far_above_cap"
    if actual_risk_pct_after_cap < min_actual_risk_pct_after_cap:
        return "actual_risk_too_low_after_cap"
    return ""


def _summary_row(
    sizing_model: str,
    sizing_rows: Sequence[Mapping[str, object]],
    execution_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    rows = [row for row in sizing_rows if row.get("sizing_model") == sizing_model]
    proposal_ids = {str(row.get("candidate_id", "")) for row in rows if row.get("proposal_approved")}
    executions = [execution_by_id[candidate_id] for candidate_id in proposal_ids if candidate_id in execution_by_id]
    rows_by_id = {str(row.get("candidate_id", "")): row for row in rows}
    net_returns = [_net_return_on_notional(execution, rows_by_id.get(str(execution.get("candidate_id", "")))) for execution in executions]
    return {
        "sizing_model": sizing_model,
        "fresh_candidates": len(rows),
        "formal_approved": sum(1 for row in rows if row.get("formal_approved")),
        "proposal_approved": sum(1 for row in rows if row.get("proposal_approved")),
        "closed_trades": len(executions),
        "margin_required_too_high": sum(1 for row in rows if row.get("reject_reason") == "margin_required_too_high"),
        "stop_distance_too_near": sum(1 for row in rows if row.get("reject_reason") == "stop_distance_too_near"),
        "notional_cap_hit_count": sum(1 for row in rows if row.get("capped_by_notional")),
        "cost_after_r_too_low": sum(1 for row in rows if row.get("reject_reason") == "cost_after_r_too_low"),
        "liquidation_distance_too_close": sum(1 for row in rows if row.get("reject_reason") == "liquidation_distance_too_close"),
        "portfolio_heat_exceeded": sum(1 for row in rows if row.get("reject_reason") == "portfolio_heat_exceeded"),
        "actual_risk_pct_after_cap_p50": _percentile(_values(rows, "actual_risk_pct_after_cap"), 0.50),
        "actual_risk_pct_after_cap_p75": _percentile(_values(rows, "actual_risk_pct_after_cap"), 0.75),
        "actual_risk_pct_after_cap_p90": _percentile(_values(rows, "actual_risk_pct_after_cap"), 0.90),
        "risk_utilization_ratio_p50": _percentile(_values(rows, "risk_utilization_ratio"), 0.50),
        "risk_utilization_ratio_p75": _percentile(_values(rows, "risk_utilization_ratio"), 0.75),
        "risk_utilization_ratio_p90": _percentile(_values(rows, "risk_utilization_ratio"), 0.90),
        "notional_to_equity_pct_p50": _percentile(_values(rows, "notional_to_equity_pct"), 0.50),
        "notional_to_equity_pct_p75": _percentile(_values(rows, "notional_to_equity_pct"), 0.75),
        "notional_to_equity_pct_p90": _percentile(_values(rows, "notional_to_equity_pct"), 0.90),
        "margin_required_pct_p50": _percentile(_values(rows, "margin_required_pct"), 0.50),
        "margin_required_pct_p75": _percentile(_values(rows, "margin_required_pct"), 0.75),
        "margin_required_pct_p90": _percentile(_values(rows, "margin_required_pct"), 0.90),
        "stop_atr_p50": _percentile(_values(rows, "stop_atr"), 0.50),
        "stop_atr_p75": _percentile(_values(rows, "stop_atr"), 0.75),
        "stop_atr_p90": _percentile(_values(rows, "stop_atr"), 0.90),
        "stop_distance_pct_p50": _percentile(_values(rows, "stop_distance_pct"), 0.50),
        "stop_distance_pct_p75": _percentile(_values(rows, "stop_distance_pct"), 0.75),
        "stop_distance_pct_p90": _percentile(_values(rows, "stop_distance_pct"), 0.90),
        "MAE_R_avg": _avg(_values(executions, "mae_R")),
        "MAE_R_p50": _percentile(_values(executions, "mae_R"), 0.50),
        "MAE_R_p75": _percentile(_values(executions, "mae_R"), 0.75),
        "MFE_R_avg": _avg(_values(executions, "mfe_R")),
        "MFE_R_p50": _percentile(_values(executions, "mfe_R"), 0.50),
        "MFE_R_p75": _percentile(_values(executions, "mfe_R"), 0.75),
        "net_R_avg": _avg(_values(executions, "net_R")),
        "net_R_p50": _percentile(_values(executions, "net_R"), 0.50),
        "net_return_on_notional_avg": _avg([value for value in net_returns if value is not None]),
        "net_return_on_notional_p50": _percentile([value for value in net_returns if value is not None], 0.50),
        "time_cut_exit_rate": _rate(sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"), len(executions)),
        "liquidation_event_count": sum(1 for row in executions if row.get("liquidation_event")),
        "funding_sum": sum(_float(row.get("funding_paid_or_received")) or 0.0 for row in executions),
    }


def _subgroup_rows(
    sizing_rows: Sequence[Mapping[str, object]],
    execution_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    specs = (
        ("high_sweep_rvol", lambda row: row.get("sweep_rvol_tier") == "high_sweep_rvol"),
        ("CHoCH true", lambda row: row.get("choch_tag") == "choch_true"),
        ("high_sweep_rvol + CHoCH true", lambda row: row.get("sweep_rvol_tier") == "high_sweep_rvol" and row.get("choch_tag") == "choch_true"),
        ("high_sweep_rvol + high_wick", lambda row: row.get("sweep_rvol_tier") == "high_sweep_rvol" and row.get("wick_ratio_tier") == "high_wick"),
        ("ETH C short", lambda row: row.get("asset") == "ETH" and row.get("profile") == "C" and row.get("direction") == "short"),
        ("ETH C short + high_sweep_rvol", lambda row: row.get("asset") == "ETH" and row.get("profile") == "C" and row.get("direction") == "short" and row.get("sweep_rvol_tier") == "high_sweep_rvol"),
        ("recent_swing + high_sweep_rvol", lambda row: row.get("structure_level_source") == "recent_swing" and row.get("sweep_rvol_tier") == "high_sweep_rvol"),
    )
    output: list[dict[str, object]] = []
    models = sorted({str(row.get("sizing_model")) for row in sizing_rows})
    for model in models:
        model_rows = [row for row in sizing_rows if row.get("sizing_model") == model]
        for name, predicate in specs:
            group = [row for row in model_rows if predicate(row)]
            proposal_ids = {str(row.get("candidate_id", "")) for row in group if row.get("proposal_approved")}
            executions = [execution_by_id[candidate_id] for candidate_id in proposal_ids if candidate_id in execution_by_id]
            group_by_id = {str(row.get("candidate_id", "")): row for row in group}
            net_returns = [_net_return_on_notional(execution, group_by_id.get(str(execution.get("candidate_id", "")))) for execution in executions]
            output.append(
                {
                    "subgroup": name,
                    "sizing_model": model,
                    "fresh_candidates": len(group),
                    "approved_under_current_risk_based_sizing": sum(1 for row in group if row.get("formal_approved")),
                    "approved_under_notional_capped_risk_based_sizing": sum(1 for row in group if row.get("proposal_approved")),
                    "closed_trades": len(executions),
                    "MFE_R_avg": _avg(_values(executions, "mfe_R")),
                    "MFE_R_p50": _percentile(_values(executions, "mfe_R"), 0.50),
                    "MFE_R_p75": _percentile(_values(executions, "mfe_R"), 0.75),
                    "MAE_R_avg": _avg(_values(executions, "mae_R")),
                    "MAE_R_p50": _percentile(_values(executions, "mae_R"), 0.50),
                    "MAE_R_p75": _percentile(_values(executions, "mae_R"), 0.75),
                    "net_R_avg": _avg(_values(executions, "net_R")),
                    "net_R_p50": _percentile(_values(executions, "net_R"), 0.50),
                    "net_return_on_notional_avg": _avg([value for value in net_returns if value is not None]),
                    "net_return_on_notional_p50": _percentile([value for value in net_returns if value is not None], 0.50),
                    "time_cut_exit_rate": _rate(sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"), len(executions)),
                    "margin_required_too_high": sum(1 for row in group if row.get("reject_reason") == "margin_required_too_high"),
                    "stop_distance_too_near": sum(1 for row in group if row.get("reject_reason") == "stop_distance_too_near"),
                    "actual_risk_pct_after_cap_p50": _percentile(_values(group, "actual_risk_pct_after_cap"), 0.50),
                    "actual_risk_pct_after_cap_p75": _percentile(_values(group, "actual_risk_pct_after_cap"), 0.75),
                    "risk_utilization_ratio_p50": _percentile(_values(group, "risk_utilization_ratio"), 0.50),
                    "risk_utilization_ratio_p75": _percentile(_values(group, "risk_utilization_ratio"), 0.75),
                }
            )
    return tuple(output)


def _net_return_on_notional(execution: Mapping[str, object], sizing_row: Mapping[str, object] | None) -> float | None:
    if sizing_row is None:
        return None
    net_r = _float(execution.get("net_R"))
    risk_amount = _float(sizing_row.get("actual_risk_amount_after_cap"))
    notional = _float(sizing_row.get("capped_position_notional"))
    if net_r is None or risk_amount is None or notional is None or notional <= 0:
        return None
    return net_r * risk_amount / notional


def _report(
    *,
    summary_rows: Sequence[Mapping[str, object]],
    subgroup_rows: Sequence[Mapping[str, object]],
    policies: Mapping[str, Mapping[str, object]],
    window_label: str,
) -> str:
    capped = next((row for row in summary_rows if row.get("sizing_model") == "notional_capped_risk_based"), {})
    current = next((row for row in summary_rows if row.get("sizing_model") == "current_risk_based_sizing"), {})
    best_groups = sorted(subgroup_rows, key=lambda row: (_float(row.get("net_R_avg")) or -999.0, _float(row.get("MFE_R_avg")) or -999.0), reverse=True)[:8]
    lr_policy = policies["liquidity_reversal"]
    trend_policy = policies["trend_continuation"]
    return "\n".join(
        (
            "# Stage 6C Setup-Specific Sizing Proposal Report",
            "",
            f"- window={window_label}",
            f"- liquidity_reversal_policy={lr_policy['sizing_model']} stop={lr_policy['stop_model']} exit={lr_policy['exit_model']}",
            f"- trend_continuation_policy_placeholder={trend_policy['sizing_model']} stop={trend_policy['stop_model']} exit={trend_policy['exit_model']}",
            "",
            "## Sizing Comparison",
            f"- current: formal={current.get('formal_approved')} proposal={current.get('proposal_approved')} closed={current.get('closed_trades')} margin_high={current.get('margin_required_too_high')} stop_near={current.get('stop_distance_too_near')}",
            f"- capped proposal: formal={capped.get('formal_approved')} proposal={capped.get('proposal_approved')} closed_with_existing_execution={capped.get('closed_trades')} cap_hits={capped.get('notional_cap_hit_count')} actual_risk_p50={capped.get('actual_risk_pct_after_cap_p50')} risk_util_p50={capped.get('risk_utilization_ratio_p50')}",
            "",
            "## Focus Subgroups",
            *(
                f"- {row['subgroup']} / {row['sizing_model']}: fresh={row['fresh_candidates']} current={row['approved_under_current_risk_based_sizing']} capped={row['approved_under_notional_capped_risk_based_sizing']} closed={row['closed_trades']} MFE={row['MFE_R_avg']} net={row['net_R_avg']}"
                for row in best_groups
            ),
            "",
            "## Conclusion",
            "- notional_capped_risk_based is proposal-only; it does not change formal RiskEngine approval.",
            "- If capped proposal increases approvals but actual risk utilization is too low, Stage 6C should continue before Stage 7.",
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
    "Stage6CSizingResult",
    "build_stage6c_sizing_report",
    "default_setup_sizing_policies",
    "read_jsonl",
    "write_stage6c_artifacts",
)
