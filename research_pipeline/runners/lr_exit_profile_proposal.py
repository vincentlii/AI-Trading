from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run


COST_TIERS = {
    "base": {"net_r_penalty": 0.0, "slippage_cost": 0.0, "funding_cost": 0.0},
    "stress": {"net_r_penalty": 0.05, "slippage_cost": 0.03, "funding_cost": 0.02},
    "harsh": {"net_r_penalty": 0.12, "slippage_cost": 0.08, "funding_cost": 0.04},
}
EXIT_PROFILES = (
    "baseline_fixed_2r_time_cut",
    "conservative_1_2r_full",
    "conservative_1_5r_full",
    "partial_1_2r_structure_target",
    "partial_1_5r_structure_target",
    "structure_target_only",
    "runner_displacement",
    "dynamic_time_cut",
)


@dataclass(frozen=True)
class SetupSpec:
    name: str
    structure_source: str
    attempt_type: str
    predicate: Callable[[dict[str, Any]], bool]


SETUPS = (
    SetupSpec(
        "recent_swing_attempt_1_reclaim",
        "recent_swing",
        "attempt_1_reclaim_entry",
        lambda row: row.get("structure_level_source") == "recent_swing",
    ),
    SetupSpec(
        "recent_swing_attempt_4_displacement",
        "recent_swing",
        "attempt_4_displacement_entry",
        lambda row: row.get("structure_level_source") == "recent_swing"
        and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    SetupSpec(
        "Session_HL_attempt_4_displacement",
        "Session High/Low",
        "attempt_4_displacement_entry",
        lambda row: _has_session_source_tag(row)
        and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    SetupSpec(
        "Session_HL_attempt_3_choch_mss",
        "Session High/Low",
        "attempt_3_choch_mss_entry",
        lambda row: _has_session_source_tag(row)
        and _matches_attempt(row, "attempt_3_choch_mss_entry"),
    ),
    SetupSpec(
        "recent_swing_attempt_3_choch_mss",
        "recent_swing",
        "attempt_3_choch_mss_entry",
        lambda row: row.get("structure_level_source") == "recent_swing"
        and _matches_attempt(row, "attempt_3_choch_mss_entry"),
    ),
)


@dataclass(frozen=True)
class LRExitProfileProposalResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    exit_profiles_shadow_only: bool
    baseline_exit_profile: str
    fixed_2r_time_cut_remains_baseline: bool
    setup_names: list[str]
    exit_profiles: list[str]
    cost_tiers: list[str]
    row_rows: list[dict[str, Any]]
    grouped_rows: list[dict[str, Any]]
    primary_decision: str
    secondary_findings: list[str]
    deferred_items: list[str]
    next_pr_recommendation: str
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_exit_profile_proposal(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRExitProfileProposalResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}
    row_rows = _exit_profile_rows(sizing_rows, execution_by_candidate, filter_by_candidate)
    grouped_rows = _grouped_rows(row_rows)
    audit_issue_count = sum(
        1
        for row in grouped_rows
        if row["same_bar_ambiguous_count"]
        or row["forced_pessimistic_exit_count"]
        or row["liquidation_event_count"]
    )
    result = LRExitProfileProposalResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        exit_profiles_shadow_only=True,
        baseline_exit_profile="baseline_fixed_2r_time_cut",
        fixed_2r_time_cut_remains_baseline=True,
        setup_names=[setup.name for setup in SETUPS],
        exit_profiles=list(EXIT_PROFILES),
        cost_tiers=list(COST_TIERS),
        row_rows=row_rows,
        grouped_rows=grouped_rows,
        primary_decision=_primary_decision(grouped_rows, audit_issue_count),
        secondary_findings=_secondary_findings(grouped_rows),
        deferred_items=[
            "quality-aware sizing formalization",
            "combined LR candidate",
            "robustness",
            "cleanup / merge",
            "PDH/PDL / EQH/EQL scanner support",
        ],
        next_pr_recommendation="PR 11F Quality-aware Sizing Proposal"
        if audit_issue_count == 0
        else "PR 11E-fix",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _exit_profile_rows(
    sizing_rows: list[dict[str, Any]],
    execution_by_candidate: dict[str, dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_rows = [row for row in sizing_rows if row.get("sizing_model") == "current_risk_based_sizing"]
    for setup in SETUPS:
        selected = [row for row in current_rows if setup.predicate(row)]
        approved = [row for row in selected if _truthy(row.get("formal_approved"))]
        for sizing_row in approved:
            candidate_id = str(sizing_row.get("candidate_id"))
            if candidate_id not in execution_by_candidate:
                continue
            base_payload = dict(filter_by_candidate.get(candidate_id, {}))
            base_payload.update(execution_by_candidate[candidate_id])
            base_payload.update(
                {
                    "net_return_on_notional": sizing_row.get("net_return_on_notional"),
                    "portfolio_heat": sizing_row.get("portfolio_heat"),
                    "margin_required_pct": sizing_row.get("margin_required_pct"),
                }
            )
            for exit_profile in EXIT_PROFILES:
                if exit_profile == "runner_displacement" and setup.attempt_type != "attempt_4_displacement_entry":
                    continue
                for cost_tier in COST_TIERS:
                    rows.append(
                        _simulate_exit_row(
                            setup=setup,
                            payload=base_payload,
                            exit_profile=exit_profile,
                            cost_tier=cost_tier,
                        )
                    )
    return rows


def _simulate_exit_row(
    *,
    setup: SetupSpec,
    payload: dict[str, Any],
    exit_profile: str,
    cost_tier: str,
) -> dict[str, Any]:
    tier = COST_TIERS[cost_tier]
    mfe = _float(payload.get("mfe_R")) or 0.0
    mae = _float(payload.get("mae_R")) or 0.0
    baseline_net = _float(payload.get("net_R")) or 0.0
    baseline_exit = str(payload.get("exit_reason") or "unknown")
    target_r = _target_r(payload, exit_profile)
    net_before_cost, exit_reason, partial_tp, runner_exit, breakeven, structure_hit = _profile_outcome(
        exit_profile=exit_profile,
        mfe=mfe,
        mae=mae,
        baseline_net=baseline_net,
        baseline_exit=baseline_exit,
        target_r=target_r,
    )
    net_r = net_before_cost - float(tier["net_r_penalty"])
    return {
        "row_type": "diagnostic_only",
        "candidate_id": payload.get("candidate_id"),
        "event_id": payload.get("event_id"),
        "trade_id": payload.get("trade_id"),
        "execution_id": payload.get("execution_id"),
        "setup_name": setup.name,
        "structure_source": setup.structure_source,
        "attempt_type": setup.attempt_type,
        "exit_profile": exit_profile,
        "cost_tier": cost_tier,
        "asset": payload.get("asset"),
        "profile": payload.get("profile"),
        "direction": payload.get("direction"),
        "session_name": _session_name(payload),
        "feature_cutoff_time": payload.get("feature_cutoff_time") or payload.get("signal_time"),
        "structure_confirmed_time": payload.get("structure_confirmed_time") or payload.get("structure_time"),
        "sweep_time": payload.get("sweep_time"),
        "reclaim_time": payload.get("reclaim_time"),
        "signal_time": payload.get("signal_time"),
        "entry_time": payload.get("entry_time"),
        "exit_time": payload.get("exit_time"),
        "bar_confirmed": payload.get("bar_confirmed", True),
        "no_lookahead_safe": payload.get("no_lookahead_safe"),
        "gross_R": net_before_cost + (_float(payload.get("estimated_cost_r")) or 0.0),
        "net_R": net_r,
        "expectancy_R": net_r,
        "net_return_on_notional": _float(payload.get("net_return_on_notional")),
        "mfe_R": mfe,
        "mae_R": mae,
        "mfe_capture_ratio": _ratio_value(max(net_before_cost, 0.0), mfe),
        "exit_reason": exit_reason,
        "partial_tp": partial_tp,
        "runner_exit": runner_exit,
        "breakeven_exit": breakeven,
        "structure_target_hit": structure_hit,
        "holding_bars": _holding_bars(payload, exit_profile, exit_reason),
        "same_bar_ambiguous": _truthy(payload.get("same_bar_ambiguous")),
        "forced_pessimistic_exit": _truthy(payload.get("forced_pessimistic_exit")),
        "entry_and_exit_same_bar": (_float(payload.get("holding_bars")) or 0.0) <= 0,
        "liquidation_event": _truthy(payload.get("liquidation_event")),
        "fee_cost": _float(payload.get("estimated_cost_r")) or 0.0,
        "slippage_cost": float(tier["slippage_cost"]),
        "funding_cost": (_float(payload.get("funding_paid_or_received")) or 0.0)
        + float(tier["funding_cost"]),
        "portfolio_heat": _float(payload.get("portfolio_heat")),
        "margin_required_pct": _float(payload.get("margin_required_pct")),
        "target_distance_r": target_r,
        "shadow_only": True,
        "diagnostic_only": True,
        "eligible_for_performance": False,
        "eligible_for_robustness": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _profile_outcome(
    *,
    exit_profile: str,
    mfe: float,
    mae: float,
    baseline_net: float,
    baseline_exit: str,
    target_r: float,
) -> tuple[float, str, bool, bool, bool, bool]:
    if mae >= 1.0 and mfe < 1.0:
        return -1.0, "stop_loss", False, False, False, False
    if exit_profile == "baseline_fixed_2r_time_cut":
        return baseline_net, baseline_exit, False, False, baseline_exit == "breakeven_stop", False
    if exit_profile == "conservative_1_2r_full":
        return _full_target_outcome(mfe, baseline_net, 1.2)
    if exit_profile == "conservative_1_5r_full":
        return _full_target_outcome(mfe, baseline_net, 1.5)
    if exit_profile == "partial_1_2r_structure_target":
        return _partial_structure_outcome(mfe, baseline_net, partial_r=1.2, target_r=target_r)
    if exit_profile == "partial_1_5r_structure_target":
        return _partial_structure_outcome(mfe, baseline_net, partial_r=1.5, target_r=target_r)
    if exit_profile == "structure_target_only":
        if mfe >= target_r:
            return target_r, "structure_target", False, False, False, True
        return min(baseline_net, target_r * 0.25), "time_cut_exit", False, False, False, False
    if exit_profile == "runner_displacement":
        if mfe >= 1.5:
            runner_r = min(mfe * 0.75, target_r + 1.0)
            return 0.7 * 1.5 + 0.3 * runner_r, "runner_exit", True, True, False, mfe >= target_r
        return min(baseline_net, 0.0), "time_cut_exit", False, False, False, False
    if exit_profile == "dynamic_time_cut":
        if mfe >= 1.5:
            return min(mfe, 2.0), "dynamic_time_cut_target", False, False, False, mfe >= target_r
        if mfe >= 0.5:
            return max(baseline_net, 0.25), "dynamic_time_cut_exit", False, False, False, False
        return min(baseline_net, -0.1), "dynamic_time_cut_exit", False, False, False, False
    return baseline_net, baseline_exit, False, False, False, False


def _full_target_outcome(mfe: float, baseline_net: float, target_r: float) -> tuple[float, str, bool, bool, bool, bool]:
    if mfe >= target_r:
        return target_r, "take_profit", False, False, False, False
    return min(baseline_net, target_r * 0.2), "time_cut_exit", False, False, False, False


def _partial_structure_outcome(
    mfe: float, baseline_net: float, *, partial_r: float, target_r: float
) -> tuple[float, str, bool, bool, bool, bool]:
    if mfe >= target_r:
        return 0.5 * partial_r + 0.5 * target_r, "structure_target", True, False, False, True
    if mfe >= partial_r:
        return 0.5 * partial_r, "partial_tp_time_cut", True, False, False, False
    return min(baseline_net, partial_r * 0.15), "time_cut_exit", False, False, False, False


def _target_r(payload: dict[str, Any], exit_profile: str) -> float:
    target_r = _float(payload.get("target_r")) or 2.0
    distance_r = _float(payload.get("target_distance_atr_entry_tf"))
    stop_atr = _float(payload.get("stop_atr_entry_tf")) or _float(payload.get("stop_atr"))
    if exit_profile in {"structure_target_only", "partial_1_2r_structure_target", "partial_1_5r_structure_target", "runner_displacement"}:
        if distance_r is not None and stop_atr:
            return max(1.0, min(3.0, distance_r / stop_atr))
    return target_r


def _grouped_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    base_keys = [
        ("ALL", "ALL", "ALL", "ALL", None),
        *[(asset, profile, direction, session, key) for asset, profile, direction, session, key in _group_keys(rows)],
    ]
    for setup in SETUPS:
        for exit_profile in EXIT_PROFILES:
            if exit_profile == "runner_displacement" and setup.attempt_type != "attempt_4_displacement_entry":
                continue
            for cost_tier in COST_TIERS:
                setup_rows = [
                    row
                    for row in rows
                    if row["setup_name"] == setup.name
                    and row["exit_profile"] == exit_profile
                    and row["cost_tier"] == cost_tier
                ]
                for asset, profile, direction, session_name, key in base_keys:
                    selected = setup_rows if key is None else [row for row in setup_rows if _row_group_key(row) == key]
                    if not selected and key is not None:
                        continue
                    grouped.append(
                        _summary_row(
                            setup=setup,
                            exit_profile=exit_profile,
                            cost_tier=cost_tier,
                            rows=selected,
                            asset=asset,
                            profile=profile,
                            direction=direction,
                            session_name=session_name,
                        )
                    )
    return grouped


def _summary_row(
    *,
    setup: SetupSpec,
    exit_profile: str,
    cost_tier: str,
    rows: list[dict[str, Any]],
    asset: str,
    profile: str,
    direction: str,
    session_name: str,
) -> dict[str, Any]:
    net_values = [_float(row.get("net_R")) or 0.0 for row in rows]
    mfe_values = [_float(row.get("mfe_R")) for row in rows]
    mae_values = [_float(row.get("mae_R")) for row in rows]
    exits = Counter(str(row.get("exit_reason", "")) for row in rows if row.get("exit_reason"))
    return {
        "setup_name": setup.name,
        "structure_source": setup.structure_source,
        "attempt_type": setup.attempt_type,
        "exit_profile": exit_profile,
        "cost_tier": cost_tier,
        "asset": asset,
        "profile": profile,
        "direction": direction,
        "session_name": session_name,
        "candidates": len(rows),
        "closed_trades": len(rows),
        "gross_R": _avg([_float(row.get("gross_R")) for row in rows]),
        "net_R_avg": _avg(net_values),
        "net_R_p50": _pct(net_values, 50),
        "net_R_p75": _pct(net_values, 75),
        "profit_factor": _profit_factor(net_values),
        "win_rate": _ratio(sum(1 for value in net_values if value > 0), len(net_values)),
        "expectancy_R": _avg(net_values),
        "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in rows]),
        "total_net_pnl": None,
        "max_drawdown": _max_drawdown(net_values),
        "max_consecutive_losses": _max_consecutive_losses(net_values),
        "recovery_factor": _recovery_factor(net_values),
        "portfolio_heat_max": _max([_float(row.get("portfolio_heat")) for row in rows]),
        "liquidation_event_count": sum(1 for row in rows if row.get("liquidation_event")),
        "MFE_R_avg": _avg(mfe_values),
        "MFE_R_p50": _pct(mfe_values, 50),
        "MFE_R_p75": _pct(mfe_values, 75),
        "MFE_R_p90": _pct(mfe_values, 90),
        "MAE_R_avg": _avg(mae_values),
        "MAE_R_p50": _pct(mae_values, 50),
        "MAE_R_p75": _pct(mae_values, 75),
        "MAE_R_p90": _pct(mae_values, 90),
        "MFE_capture_ratio": _avg([_float(row.get("mfe_capture_ratio")) for row in rows]),
        "MFE_ge_0_5_ratio": _ratio(sum(1 for value in mfe_values if value is not None and value >= 0.5), len(mfe_values)),
        "MFE_ge_1_0_ratio": _ratio(sum(1 for value in mfe_values if value is not None and value >= 1.0), len(mfe_values)),
        "MAE_ge_1_0_ratio": _ratio(sum(1 for value in mae_values if value is not None and value >= 1.0), len(mae_values)),
        "exit_reason_distribution": dict(exits),
        "time_cut_exit_rate": _ratio(exits.get("time_cut_exit", 0) + exits.get("dynamic_time_cut_exit", 0), len(rows)),
        "stop_loss_rate": _ratio(exits.get("stop_loss", 0), len(rows)),
        "take_profit_rate": _ratio(exits.get("take_profit", 0) + exits.get("structure_target", 0) + exits.get("dynamic_time_cut_target", 0), len(rows)),
        "partial_tp_rate": _ratio(sum(1 for row in rows if row.get("partial_tp")), len(rows)),
        "runner_exit_rate": _ratio(sum(1 for row in rows if row.get("runner_exit")), len(rows)),
        "breakeven_exit_rate": _ratio(sum(1 for row in rows if row.get("breakeven_exit")), len(rows)),
        "structure_target_hit_rate": _ratio(sum(1 for row in rows if row.get("structure_target_hit")), len(rows)),
        "avg_holding_bars": _avg([_float(row.get("holding_bars")) for row in rows]),
        "median_holding_bars": _pct([_float(row.get("holding_bars")) for row in rows], 50),
        "same_bar_ambiguous_count": sum(1 for row in rows if row.get("same_bar_ambiguous")),
        "forced_pessimistic_exit_count": sum(1 for row in rows if row.get("forced_pessimistic_exit")),
        "entry_and_exit_same_bar_count": sum(1 for row in rows if row.get("entry_and_exit_same_bar")),
        "fee_cost": sum(_float(row.get("fee_cost")) or 0.0 for row in rows),
        "slippage_cost": sum(_float(row.get("slippage_cost")) or 0.0 for row in rows),
        "funding_cost": sum(_float(row.get("funding_cost")) or 0.0 for row in rows),
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _write_outputs(result: LRExitProfileProposalResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_exit_profile_proposal_result.json").write_text(
        result.as_json(), encoding="utf-8"
    )
    (output_dir / "lr_exit_profile_proposal_report.md").write_text(
        _report(result), encoding="utf-8"
    )
    _write_jsonl(output_dir / "lr_exit_profile_rows.jsonl", result.row_rows)
    _write_jsonl(output_dir / "lr_exit_profile_grouped_rows.jsonl", result.grouped_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_exit_profile_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-exit-profile-proposal",
        notes="PR11E proposal-only shadow exit profile evaluation.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_exit_profile_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-exit-profile-proposal",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11E exit profile proposal; no formal exit replacement.",
        tags=["PR11E", "proposal_only", "exit_profile", "shadow"],
    )


def _report(result: LRExitProfileProposalResult) -> str:
    all_rows = [
        row
        for row in result.grouped_rows
        if row["asset"] == "ALL"
        and row["profile"] == "ALL"
        and row["direction"] == "ALL"
        and row["session_name"] == "ALL"
    ]
    lines = [
        "# PR 11E Exit Profile Proposal Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- exit_profiles = proposal-only / shadow",
        "- fixed_2r_time_cut remains baseline",
        "- structure source proposal belongs to PR 11D result",
        "- sizing proposal belongs to PR 11F",
        "- combined candidate belongs to PR 11G",
        "- robustness belongs to PR 11H",
        "- cleanup / merge belongs to PR 12",
        "",
        "## Exit Profile Summary",
    ]
    for row in all_rows:
        if row["cost_tier"] != "base":
            continue
        lines.append(
            f"- {row['setup_name']} / {row['exit_profile']}: "
            f"closed={row['closed_trades']} net_R={row['net_R_avg']} "
            f"PF={row['profit_factor']} MFE_capture={row['MFE_capture_ratio']} "
            f"time_cut={row['time_cut_exit_rate']}"
        )
    lines.extend(
        [
            "",
            "## Primary Decision",
            f"{result.primary_decision}. {_decision_text(result.primary_decision)}",
            "",
            "## Secondary Findings",
        ]
    )
    lines.extend(f"- {finding}" for finding in result.secondary_findings)
    lines.append("")
    lines.append("## Deferred Items")
    lines.extend(f"- {item}" for item in result.deferred_items)
    lines.extend(["", "## Next PR Recommendation", f"- {result.next_pr_recommendation}"])
    return "\n".join(lines) + "\n"


def _primary_decision(grouped_rows: list[dict[str, Any]], audit_issue_count: int) -> str:
    if audit_issue_count:
        return "F"
    displacement = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "runner_displacement",
        "base",
    )
    baseline = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "baseline_fixed_2r_time_cut",
        "base",
    )
    if _improves(displacement, baseline):
        return "A"
    structure = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "structure_target_only",
        "base",
    )
    if _improves(structure, baseline):
        return "B"
    partial = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "partial_1_5r_structure_target",
        "base",
    )
    if _improves(partial, baseline):
        return "C"
    dynamic = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "dynamic_time_cut",
        "base",
    )
    if _improves(dynamic, baseline):
        return "D"
    return "E"


def _secondary_findings(grouped_rows: list[dict[str, Any]]) -> list[str]:
    return [
        _best_profile_finding(grouped_rows, "Session_HL_attempt_4_displacement"),
        _best_profile_finding(grouped_rows, "Session_HL_attempt_3_choch_mss"),
        "runner_displacement 只在 displacement setup 上输出，避免把 runner 误套到 coverage setup。",
        "structure target 使用现有 target distance 字段做 shadow，缺失时回退到 fixed R，不替换正式 target。",
        "低于 1R 的快速止盈未纳入主候选，避免成本敏感微利出场制造虚假胜率。",
    ]


def _best_profile_finding(grouped_rows: list[dict[str, Any]], setup_name: str) -> str:
    rows = [
        row
        for row in grouped_rows
        if row["setup_name"] == setup_name
        and row["cost_tier"] == "base"
        and row["asset"] == "ALL"
        and row["profile"] == "ALL"
        and row["direction"] == "ALL"
        and row["session_name"] == "ALL"
    ]
    if not rows:
        return f"{setup_name} 没有可比较 exit profile。"
    best = max(rows, key=lambda row: row.get("net_R_avg") or -999)
    return f"{setup_name} 当前 shadow 最优为 {best['exit_profile']}，net_R_avg={best['net_R_avg']}，PF={best['profit_factor']}。"


def _decision_text(decision: str) -> str:
    return {
        "A": "runner_displacement exit 有明确价值，按计划进入 PR 11F。",
        "B": "structure_target exit 有明确价值，按计划进入 PR 11F。",
        "C": "partial_tp_structure_target 有明确价值，按计划进入 PR 11F。",
        "D": "dynamic_time_cut 有明确价值，按计划进入 PR 11F。",
        "E": "当前 fixed 2R / time_cut 仍优于 shadow exit，按计划进入 PR 11F。",
        "F": "exit profile 存在执行审计 / same-bar / 成本问题，需要留在 PR 11E 修复。",
    }[decision]


def _improves(candidate: dict[str, Any] | None, baseline: dict[str, Any] | None) -> bool:
    if not candidate or not baseline:
        return False
    if candidate["closed_trades"] < 40:
        return False
    candidate_harsh = candidate.get("net_R_avg") or 0.0
    baseline_net = baseline.get("net_R_avg") or 0.0
    candidate_pf = candidate.get("profit_factor") or 0.0
    baseline_pf = baseline.get("profit_factor") or 0.0
    return candidate_harsh > baseline_net and candidate_pf >= baseline_pf


def _all_row(
    rows: list[dict[str, Any]], setup_name: str, exit_profile: str, cost_tier: str
) -> dict[str, Any] | None:
    for row in rows:
        if (
            row["setup_name"] == setup_name
            and row["exit_profile"] == exit_profile
            and row["cost_tier"] == cost_tier
            and row["asset"] == "ALL"
            and row["profile"] == "ALL"
            and row["direction"] == "ALL"
            and row["session_name"] == "ALL"
        ):
            return row
    return None


def _matches_attempt(row: dict[str, Any], attempt: str) -> bool:
    if attempt == "attempt_1_reclaim_entry":
        return True
    if attempt == "attempt_3_choch_mss_entry":
        return _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true"
    if attempt == "attempt_4_displacement_entry":
        return _truthy(row.get("displacement_after_reclaim")) and _truthy(row.get("displacement_direction_valid"))
    return False


def _has_session_source_tag(row: dict[str, Any]) -> bool:
    return (
        _truthy(row.get("session_high_low_tag"))
        or _truthy(row.get("london_open_window"))
        or _truthy(row.get("london_ny_overlap"))
        or _truthy(row.get("ny_open_window"))
    )


def _session_name(row: dict[str, Any]) -> str:
    hour = int(_float(row.get("utc_hour")) or 0)
    if 0 <= hour < 8:
        return "Asia"
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 17:
        return "London-NY Overlap"
    if 17 <= hour < 22:
        return "NY"
    if 22 <= hour < 24:
        return "Late"
    return "Other"


def _holding_bars(payload: dict[str, Any], exit_profile: str, exit_reason: str) -> float | None:
    base = _float(payload.get("holding_bars"))
    if base is None:
        return None
    if exit_reason in {"take_profit", "structure_target"}:
        return max(1.0, base * 0.6)
    if exit_profile in {"runner_displacement", "dynamic_time_cut"}:
        return base * 1.5
    return base


def _group_keys(rows: list[dict[str, Any]]) -> list[tuple[str, str, str, str, tuple[str, str, str, str]]]:
    keys = sorted({_row_group_key(row) for row in rows})
    return [(key[0], key[1], key[2], key[3], key) for key in keys]


def _row_group_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("asset", "")),
        str(row.get("profile", "")),
        str(row.get("direction", "")),
        str(row.get("session_name", "")),
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
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


def _ratio_value(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _max(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else max(clean)


def _profit_factor(values: Iterable[float]) -> float | None:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return abs(max_dd)


def _max_consecutive_losses(values: Iterable[float]) -> int:
    current = 0
    longest = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _recovery_factor(values: Iterable[float]) -> float | None:
    values_list = list(values)
    drawdown = _max_drawdown(values_list)
    if drawdown == 0:
        return None
    return sum(values_list) / drawdown
