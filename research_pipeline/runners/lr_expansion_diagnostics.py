from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run


STRUCTURE_SOURCES = (
    "recent_swing",
    "rolling_range",
    "PDH/PDL",
    "Session High/Low",
    "EQH/EQL",
)

ATTEMPTS = (
    ("attempt_1_reclaim_entry", lambda row: True),
    ("attempt_2_retest_entry", lambda row: _truthy(row.get("pullback_retest_after_reclaim"))),
    (
        "attempt_3_choch_mss_entry",
        lambda row: _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true",
    ),
    ("attempt_4_displacement_entry", lambda row: _truthy(row.get("displacement_after_reclaim"))),
    ("attempt_5_fvg_ce_retest", lambda row: _truthy(row.get("fvg_exists")) or _truthy(row.get("fvg_retest_hit"))),
)

EXIT_PROFILES = (
    "baseline_fixed_2r_time_cut",
    "conservative_1_2r",
    "conservative_1_5r",
    "balanced_1_2r_partial_structure",
    "structure_target_shadow",
    "runner_displacement_shadow",
)

SIZING_MODELS = ("current_risk_based_sizing", "notional_capped_risk_based")


@dataclass(frozen=True)
class LRExpansionDiagnosticResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    all_new_sources_diagnostic_only: bool
    multiple_entry_attempts_diagnostic_only: bool
    exit_profiles_shadow_only: bool
    capped_sizing_proposal_only: bool
    structure_rows: list[dict[str, Any]]
    attempt_rows: list[dict[str, Any]]
    exit_shadow_rows: list[dict[str, Any]]
    sizing_rows: list[dict[str, Any]]
    final_conclusion: str
    next_step: str
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_expansion_diagnostics(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRExpansionDiagnosticResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_id = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_id = {str(row.get("candidate_id")): row for row in execution_rows}
    enriched_exec = [_merge_execution(row, filter_by_id) for row in execution_rows]

    result = LRExpansionDiagnosticResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        all_new_sources_diagnostic_only=True,
        multiple_entry_attempts_diagnostic_only=True,
        exit_profiles_shadow_only=True,
        capped_sizing_proposal_only=True,
        structure_rows=_structure_rows(filter_rows, execution_by_id),
        attempt_rows=_attempt_rows(filter_rows, execution_by_id),
        exit_shadow_rows=_exit_shadow_rows(enriched_exec),
        sizing_rows=_sizing_rows(sizing_rows, execution_by_id),
        final_conclusion="B",
        next_step="PR 11C attempt proposal; keep structure, exit, and sizing changes diagnostic until separately validated.",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _structure_rows(
    filter_rows: list[dict[str, Any]],
    execution_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in STRUCTURE_SOURCES:
        selected = [row for row in filter_rows if _matches_structure_source(row, source)]
        executions = [
            _merge_execution(execution_by_id[str(row.get("candidate_id"))], {str(row.get("candidate_id")): row})
            for row in selected
            if str(row.get("candidate_id")) in execution_by_id
        ]
        rows.append(
            {
                "structure_source": source,
                "diagnostic_only": source in {"PDH/PDL", "Session High/Low", "EQH/EQL"},
                "total_levels": len(selected),
                "active_diagnostic_levels": len(selected),
                "swept_count": len(selected),
                "reclaimed_count": sum(1 for row in selected if row.get("reclaim_time") is not None),
                "candidate_count": len(selected),
                "closed_trades": len(executions),
                **_edge_metrics(executions),
                "asset_breakdown": dict(Counter(str(row.get("asset")) for row in selected)),
                "profile_breakdown": dict(Counter(str(row.get("profile")) for row in selected)),
                "direction_breakdown": dict(Counter(str(row.get("direction")) for row in selected)),
            }
        )
    return rows


def _attempt_rows(
    filter_rows: list[dict[str, Any]],
    execution_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, predicate in ATTEMPTS:
        selected = [row for row in filter_rows if predicate(row)]
        executions = [
            _merge_execution(execution_by_id[str(row.get("candidate_id"))], {str(row.get("candidate_id")): row})
            for row in selected
            if str(row.get("candidate_id")) in execution_by_id
        ]
        event_ids = [str(row.get("event_id") or row.get("candidate_id")) for row in selected]
        duplicates = sum(count - 1 for count in Counter(event_ids).values() if count > 1)
        rows.append(
            {
                "attempt_name": name,
                "diagnostic_only": name != "attempt_1_reclaim_entry",
                "events": len(set(event_ids)),
                "attempts": len(selected),
                "closed_trades": len(executions),
                **_edge_metrics(executions),
                "missed_entry_count": max(0, len(selected) - len(executions)),
                "expired_before_attempt_count": sum(1 for row in selected if row.get("event_state") == "expired"),
                "invalidated_count": sum(1 for row in selected if row.get("event_state") == "invalidated"),
                "duplicate_event_count": duplicates,
            }
        )
    return rows


def _exit_shadow_rows(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    displacement = [row for row in executions if _truthy(row.get("displacement_after_reclaim"))]
    for profile in EXIT_PROFILES:
        selected = displacement if profile == "runner_displacement_shadow" else executions
        net_values = [_shadow_net_r(row, profile) for row in selected]
        exits = _shadow_exits(selected, profile)
        rows.append(
            {
                "exit_profile": profile,
                "shadow_only": profile != "baseline_fixed_2r_time_cut",
                "closed_trades": len(selected),
                "net_R_avg": _avg(net_values),
                "net_R_p50": _pct(net_values, 50),
                "profit_factor": _profit_factor(net_values),
                "win_rate": _ratio(sum(1 for value in net_values if value is not None and value > 0), len(net_values)),
                "MFE_capture_ratio": _avg(
                    [
                        (max(_shadow_gross_r(row, profile), 0.0) / _float(row.get("mfe_R")))
                        for row in selected
                        if (_float(row.get("mfe_R")) or 0.0) > 0
                    ]
                ),
                "time_cut_exit_rate": _ratio(exits.get("time_cut_exit", 0), len(selected)),
                "stop_loss_rate": _ratio(exits.get("stop_loss", 0), len(selected)),
                "take_profit_rate": _ratio(exits.get("take_profit", 0), len(selected)),
                "avg_holding_bars": _avg([_float(row.get("holding_bars")) for row in selected]),
                "max_drawdown": _max_drawdown([value for value in net_values if value is not None]),
                "fee_slippage_sensitivity": "shadow_from_existing_cost_r",
            }
        )
    return rows


def _sizing_rows(
    sizing_rows: list[dict[str, Any]],
    execution_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in SIZING_MODELS:
        model_rows = [row for row in sizing_rows if row.get("sizing_model") == model]
        for tier in ("A", "B", "C", "D"):
            selected = [row for row in model_rows if _quality_tier(row) == tier]
            approved = [row for row in selected if _approved_for_model(row, model)]
            executions = [
                execution_by_id[str(row.get("candidate_id"))]
                for row in approved
                if str(row.get("candidate_id")) in execution_by_id
            ]
            rows.append(
                {
                    "quality_tier": tier,
                    "sizing_model": model,
                    "proposal_only": model == "notional_capped_risk_based",
                    "candidates": len(selected),
                    "formal_approved": sum(1 for row in selected if _truthy(row.get("formal_approved"))),
                    "proposal_approved": sum(1 for row in selected if _truthy(row.get("proposal_approved"))),
                    "closed_trades": len(executions),
                    "actual_risk_pct_after_cap_p50": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in approved], 50),
                    "actual_risk_pct_after_cap_p75": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in approved], 75),
                    "risk_utilization_p50": _pct([_float(row.get("risk_utilization_ratio")) for row in approved], 50),
                    "risk_utilization_p75": _pct([_float(row.get("risk_utilization_ratio")) for row in approved], 75),
                    "notional_cap_hit_ratio": _ratio(
                        sum(1 for row in approved if _truthy(row.get("capped_by_notional"))),
                        len(approved),
                    ),
                    "net_R_avg": _avg([_float(row.get("net_R")) for row in executions]),
                    "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in approved]),
                    "MFE_ge_0_5_ratio": _ratio(
                        sum(1 for row in executions if (_float(row.get("mfe_R")) or 0.0) >= 0.5),
                        len(executions),
                    ),
                    "MFE_ge_1_0_ratio": _ratio(
                        sum(1 for row in executions if (_float(row.get("mfe_R")) or 0.0) >= 1.0),
                        len(executions),
                    ),
                    "time_cut_exit_rate": _ratio(
                        sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"),
                        len(executions),
                    ),
                }
            )
    return rows


def _write_outputs(result: LRExpansionDiagnosticResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_expansion_diagnostic_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_expansion_diagnostic_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_expansion_structure_rows.jsonl", result.structure_rows)
    _write_jsonl(output_dir / "lr_expansion_attempt_rows.jsonl", result.attempt_rows)
    _write_jsonl(output_dir / "lr_expansion_exit_shadow_rows.jsonl", result.exit_shadow_rows)
    _write_jsonl(output_dir / "lr_expansion_sizing_rows.jsonl", result.sizing_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_expansion_diagnostic",
        window="10000w",
        source_command="research_pipeline.cli.research lr-expansion-diagnostics",
        notes="PR11B diagnostic-only expansion framework; no formal strategy changes.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_expansion_diagnostic",
        window="10000w",
        source_command="research_pipeline.cli.research lr-expansion-diagnostics",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11B diagnostic-only LR expansion framework.",
        tags=["PR11B", "proposal_only", "diagnostic_only", "lr_expansion"],
    )


def _report(result: LRExpansionDiagnosticResult) -> str:
    best_attempt = max(result.attempt_rows, key=lambda row: row.get("MFE_R_avg") or -1)
    best_exit = max(result.exit_shadow_rows, key=lambda row: row.get("net_R_avg") or -999)
    lines = [
        "# PR 11B LR Expansion Diagnostic Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- all_new_sources_diagnostic_only = true",
        "- multiple_entry_attempts_diagnostic_only = true",
        "- exit_profiles_shadow_only = true",
        "- capped_sizing_proposal_only = true",
        "",
        "## Structure Source Diagnostic",
    ]
    for row in result.structure_rows:
        lines.append(
            f"- {row['structure_source']}: candidates={row['candidate_count']} closed={row['closed_trades']} "
            f"MFE_avg={row['MFE_R_avg']} MFE>=0.5={row['MFE_ge_0_5_ratio']} net_R={row['net_R_avg']} "
            f"time_cut={row['time_cut_exit_rate']} diagnostic_only={row['diagnostic_only']}"
        )
    lines.append("")
    lines.append("## Event FSM / Attempt Diagnostic")
    for row in result.attempt_rows:
        lines.append(
            f"- {row['attempt_name']}: attempts={row['attempts']} closed={row['closed_trades']} "
            f"MFE_avg={row['MFE_R_avg']} MAE_avg={row['MAE_R_avg']} net_R={row['net_R_avg']} "
            f"duplicates={row['duplicate_event_count']}"
        )
    lines.append("")
    lines.append("## Exit Profile Shadow Simulation")
    for row in result.exit_shadow_rows:
        lines.append(
            f"- {row['exit_profile']}: closed={row['closed_trades']} net_R_avg={row['net_R_avg']} "
            f"PF={row['profit_factor']} win_rate={row['win_rate']} time_cut={row['time_cut_exit_rate']} "
            f"shadow_only={row['shadow_only']}"
        )
    lines.append("")
    lines.append("## Quality-aware Sizing Diagnostic")
    for row in result.sizing_rows:
        lines.append(
            f"- tier {row['quality_tier']} / {row['sizing_model']}: candidates={row['candidates']} "
            f"formal={row['formal_approved']} proposal={row['proposal_approved']} closed={row['closed_trades']} "
            f"risk_util_p50={row['risk_utilization_p50']} MFE>=0.5={row['MFE_ge_0_5_ratio']}"
        )
    lines.extend(
        [
            "",
            "## Readiness",
            f"- MFE 最强 attempt：{best_attempt['attempt_name']}。",
            f"- net_R 最强 shadow exit：{best_exit['exit_profile']}。",
            "- 新 structure source 仍是 diagnostic-only；当前 artifacts 只能验证既有交易是否带有这些标签，不能代表正式 active source 已启用。",
            "- 多次 entry attempt 必须先由 FSM 管理，再进入任何正式 proposal，避免恢复 stale replay。",
            "- notional_capped_risk_based 继续保持 proposal-only。",
            "",
            f"## Final Conclusion: {result.final_conclusion}",
            "B. Entry attempt expansion 有明确诊断价值；下一步进入 PR 11C attempt proposal，再考虑正式 robustness。",
        ]
    )
    return "\n".join(lines) + "\n"


def _matches_structure_source(row: dict[str, Any], source: str) -> bool:
    if source in {"recent_swing", "rolling_range"}:
        return row.get("structure_level_source") == source
    if source == "PDH/PDL":
        return _truthy(row.get("pdh_pdl_tag"))
    if source == "Session High/Low":
        return (
            _truthy(row.get("session_high_low_tag"))
            or _truthy(row.get("london_open_window"))
            or _truthy(row.get("london_ny_overlap"))
            or _truthy(row.get("ny_open_window"))
        )
    if source == "EQH/EQL":
        return _truthy(row.get("eqh_eql_tag"))
    return False


def _quality_tier(row: dict[str, Any]) -> str:
    displacement = _truthy(row.get("displacement_after_reclaim"))
    high_sweep = row.get("sweep_rvol_tier") == "high_sweep_rvol"
    high_wick = row.get("wick_tier") == "high_wick" or row.get("wick_ratio_tier") == "high_wick"
    choch = _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true"
    low_rvol = row.get("sweep_rvol_tier") == "low_sweep_rvol"
    low_mfe_like = row.get("reclaim_rvol_tier") == "high_reclaim_rvol" and not displacement
    if displacement and high_sweep and high_wick and choch:
        return "A"
    if choch or high_sweep or high_wick:
        return "B"
    if low_rvol or (not choch and not displacement):
        return "D" if low_mfe_like else "C"
    return "C"


def _approved_for_model(row: dict[str, Any], model: str) -> bool:
    if model == "current_risk_based_sizing":
        return _truthy(row.get("formal_approved"))
    return _truthy(row.get("proposal_approved"))


def _edge_metrics(executions: list[dict[str, Any]]) -> dict[str, Any]:
    mfe = [_float(row.get("mfe_R")) for row in executions]
    mae = [_float(row.get("mae_R")) for row in executions]
    net = [_float(row.get("net_R")) for row in executions]
    exits = Counter(str(row.get("exit_reason", "")) for row in executions)
    return {
        "MFE_R_avg": _avg(mfe),
        "MFE_R_p50": _pct(mfe, 50),
        "MFE_R_p75": _pct(mfe, 75),
        "MFE_R_p90": _pct(mfe, 90),
        "MAE_R_avg": _avg(mae),
        "MAE_R_p50": _pct(mae, 50),
        "MAE_R_p75": _pct(mae, 75),
        "MAE_R_p90": _pct(mae, 90),
        "MFE_ge_0_5_ratio": _ratio(sum(1 for value in mfe if value is not None and value >= 0.5), len(mfe)),
        "MFE_ge_1_0_ratio": _ratio(sum(1 for value in mfe if value is not None and value >= 1.0), len(mfe)),
        "net_R_avg": _avg(net),
        "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in executions]),
        "time_cut_exit_rate": _ratio(exits.get("time_cut_exit", 0), len(executions)),
    }


def _shadow_net_r(row: dict[str, Any], profile: str) -> float:
    cost = _float(row.get("estimated_cost_r")) or 0.0
    return _shadow_gross_r(row, profile) - cost


def _shadow_gross_r(row: dict[str, Any], profile: str) -> float:
    mfe = _float(row.get("mfe_R")) or 0.0
    mae = _float(row.get("mae_R")) or 0.0
    if profile == "baseline_fixed_2r_time_cut":
        return (_float(row.get("net_R")) or 0.0) + (_float(row.get("estimated_cost_r")) or 0.0)
    if mae >= 1.0:
        return -1.0
    if profile == "conservative_1_2r":
        return 1.2 if mfe >= 1.2 else min(mfe, 0.0)
    if profile == "conservative_1_5r":
        return 1.5 if mfe >= 1.5 else min(mfe, 0.0)
    if profile == "balanced_1_2r_partial_structure":
        return (0.5 * 1.2 + 0.5 * min(mfe, 2.0)) if mfe >= 1.2 else min(mfe, 0.0)
    if profile == "structure_target_shadow":
        target_r = _float(row.get("target_r")) or 2.0
        return min(target_r, mfe) if mfe >= 1.0 else min(mfe, 0.0)
    if profile == "runner_displacement_shadow":
        return min(max(mfe * 0.65, 0.0), 3.0) if mfe >= 1.0 else min(mfe, 0.0)
    return _float(row.get("net_R")) or 0.0


def _shadow_exits(rows: list[dict[str, Any]], profile: str) -> Counter:
    if profile == "baseline_fixed_2r_time_cut":
        return Counter(str(row.get("exit_reason", "")) for row in rows)
    exits: Counter = Counter()
    for row in rows:
        gross = _shadow_gross_r(row, profile)
        if gross >= 1.0:
            exits["take_profit"] += 1
        elif gross <= -1.0:
            exits["stop_loss"] += 1
        else:
            exits["time_cut_exit"] += 1
    return exits


def _merge_execution(row: dict[str, Any], filter_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate_id = str(row.get("candidate_id"))
    payload = dict(filter_by_id.get(candidate_id, {}))
    payload.update(row)
    return payload


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [{key: _typed(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def _typed(value: str) -> Any:
    if value == "":
        return None
    if value in {"True", "False"}:
        return value == "True"
    try:
        return float(value)
    except ValueError:
        return value


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else sum(clean) / len(clean)


def _pct(values: Iterable[float | None], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    index = (len(clean) - 1) * percentile / 100
    lower = int(index)
    upper = min(lower + 1, len(clean) - 1)
    weight = index - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def _ratio(count: int, total: int) -> float | None:
    return None if total == 0 else count / total


def _profit_factor(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    wins = sum(value for value in clean if value > 0)
    losses = abs(sum(value for value in clean if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    high = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        high = max(high, equity)
        drawdown = max(drawdown, high - equity)
    return drawdown
