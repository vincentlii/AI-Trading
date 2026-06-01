from __future__ import annotations

import csv
import hashlib
import json
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


@dataclass(frozen=True)
class ComboSpec:
    name: str
    tier: str
    structure_source: str
    attempt_type: str
    exit_profile: str
    sizing_policy: str
    priority: int
    predicate: Callable[[dict[str, Any]], bool]


COMBOS = (
    ComboSpec(
        "T1_session_hl_attempt4_fixed_current",
        "Tier 1",
        "Session High/Low",
        "attempt_4_displacement_entry",
        "fixed_2R_time_cut",
        "current_risk_based_sizing",
        1,
        lambda row: _has_session_source_tag(row) and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    ComboSpec(
        "T1_session_hl_attempt4_dynamic_quality",
        "Tier 1",
        "Session High/Low",
        "attempt_4_displacement_entry",
        "dynamic_time_cut",
        "quality_aware_capped_sizing",
        2,
        lambda row: _has_session_source_tag(row) and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    ComboSpec(
        "T1_recent_swing_attempt4_dynamic_quality",
        "Tier 1",
        "recent_swing",
        "attempt_4_displacement_entry",
        "dynamic_time_cut",
        "quality_aware_capped_sizing",
        3,
        lambda row: row.get("structure_level_source") == "recent_swing"
        and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    ComboSpec(
        "T2_session_hl_attempt3_dynamic_quality",
        "Tier 2",
        "Session High/Low",
        "attempt_3_choch_mss_entry",
        "dynamic_time_cut",
        "quality_aware_capped_sizing",
        4,
        lambda row: _has_session_source_tag(row) and _matches_attempt(row, "attempt_3_choch_mss_entry"),
    ),
    ComboSpec(
        "T2_recent_swing_attempt3_dynamic_quality",
        "Tier 2",
        "recent_swing",
        "attempt_3_choch_mss_entry",
        "dynamic_time_cut",
        "quality_aware_capped_sizing",
        5,
        lambda row: row.get("structure_level_source") == "recent_swing"
        and _matches_attempt(row, "attempt_3_choch_mss_entry"),
    ),
    ComboSpec(
        "T3_recent_swing_attempt4_fixed_current",
        "Tier 3",
        "recent_swing",
        "attempt_4_displacement_entry",
        "fixed_2R_time_cut",
        "current_risk_based_sizing",
        6,
        lambda row: row.get("structure_level_source") == "recent_swing"
        and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    ComboSpec(
        "T3_rolling_range_attempt4_dynamic_quality",
        "Tier 3",
        "rolling_range",
        "attempt_4_displacement_entry",
        "dynamic_time_cut",
        "quality_aware_capped_sizing",
        7,
        lambda row: row.get("structure_level_source") == "rolling_range"
        and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
    ComboSpec(
        "T3_session_hl_attempt4_conservative_current",
        "Tier 3",
        "Session High/Low",
        "attempt_4_displacement_entry",
        "conservative_1_5R_full",
        "current_risk_based_sizing",
        8,
        lambda row: _has_session_source_tag(row) and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
)


@dataclass(frozen=True)
class LRCombinedCandidateProposalResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    all_combined_candidates_proposal_only: bool
    dynamic_time_cut_proposal_only: bool
    quality_aware_capped_sizing_proposal_only: bool
    session_hl_source_proposal_only: bool
    duplicate_event_count: int
    overlapping_event_count: int
    combo_rows: list[dict[str, Any]]
    event_selection_rows: list[dict[str, Any]]
    grouped_rows: list[dict[str, Any]]
    portfolio_rows: list[dict[str, Any]]
    primary_decision: str
    secondary_findings: list[str]
    deferred_items: list[str]
    next_pr_recommendation: str
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_combined_candidate_proposal(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRCombinedCandidateProposalResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}
    combo_rows = _combo_rows(sizing_rows, filter_by_candidate, execution_by_candidate)
    event_selection_rows, overlapping_event_count = _event_selection_rows(combo_rows)
    selected_rows = [row for row in combo_rows if row["event_key"] in {event["event_key"] for event in event_selection_rows}]
    selected_keys = {event["event_key"]: event["selected_combo"] for event in event_selection_rows}
    selected_rows = [row for row in selected_rows if selected_keys.get(row["event_key"]) == row["combo_name"]]
    for row in selected_rows:
        row["selected"] = True
    grouped_rows = _grouped_rows(combo_rows, selected_rows)
    portfolio_rows = _portfolio_rows(selected_rows, overlapping_event_count)
    duplicate_event_count = _duplicate_selected_events(selected_rows)
    result = LRCombinedCandidateProposalResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        all_combined_candidates_proposal_only=True,
        dynamic_time_cut_proposal_only=True,
        quality_aware_capped_sizing_proposal_only=True,
        session_hl_source_proposal_only=True,
        duplicate_event_count=duplicate_event_count,
        overlapping_event_count=overlapping_event_count,
        combo_rows=combo_rows,
        event_selection_rows=event_selection_rows,
        grouped_rows=grouped_rows,
        portfolio_rows=portfolio_rows,
        primary_decision=_primary_decision(portfolio_rows, grouped_rows, duplicate_event_count),
        secondary_findings=_secondary_findings(grouped_rows, portfolio_rows),
        deferred_items=[
            "PR 11H robustness",
            "production formalization",
            "cleanup / merge",
            "PDH/PDL / EQH/EQL scanner support",
            "trend continuation future research",
        ],
        next_pr_recommendation="PR 11H Robustness Validation"
        if duplicate_event_count == 0
        else "PR 11G-fix",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _combo_rows(
    sizing_rows: list[dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
    execution_by_candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for combo in COMBOS:
        model = "current_risk_based_sizing" if combo.sizing_policy == "current_risk_based_sizing" else "notional_capped_risk_based"
        for row in sizing_rows:
            if row.get("sizing_model") != model or not combo.predicate(row):
                continue
            if not _approved_for_policy(row, combo.sizing_policy, combo.attempt_type):
                continue
            candidate_id = str(row.get("candidate_id"))
            filter_row = filter_by_candidate.get(candidate_id, {})
            execution = execution_by_candidate.get(candidate_id)
            base = dict(filter_row)
            base.update(row)
            if execution:
                base.update(execution)
            for cost_tier in COST_TIERS:
                rows.append(_combo_row(combo, base, execution is not None, cost_tier))
    return rows


def _combo_row(combo: ComboSpec, payload: dict[str, Any], closed: bool, cost_tier: str) -> dict[str, Any]:
    tier = COST_TIERS[cost_tier]
    net_before_cost, exit_reason, mfe_capture = _exit_outcome(payload, combo.exit_profile)
    net_r = None if net_before_cost is None else net_before_cost - float(tier["net_r_penalty"])
    actual_risk = _actual_risk(payload, combo.sizing_policy, combo.attempt_type)
    target_risk = _target_risk(payload, combo.sizing_policy, combo.attempt_type)
    row_type = "closed_trade" if closed else "proposal_candidate"
    return {
        "row_type": row_type,
        "combo_name": combo.name,
        "tier": combo.tier,
        "priority": combo.priority,
        "event_key": _event_key(payload),
        "event_id": payload.get("event_id"),
        "candidate_id": payload.get("candidate_id"),
        "trade_id": payload.get("trade_id"),
        "execution_id": payload.get("execution_id"),
        "selected_combo": None,
        "suppressed_combos": [],
        "suppression_reason": "",
        "structure_source": combo.structure_source,
        "attempt_type": combo.attempt_type,
        "exit_profile": combo.exit_profile,
        "sizing_policy": combo.sizing_policy,
        "cost_tier": cost_tier,
        "asset": payload.get("asset"),
        "profile": payload.get("profile"),
        "direction": payload.get("direction"),
        "session_name": _session_name(payload),
        "closed_trade": closed,
        "executed": closed,
        "selected": False,
        "eligible_for_performance": closed,
        "eligible_for_robustness": closed,
        "invalid_for_robustness": False,
        "structure_confirmed_time": payload.get("structure_confirmed_time") or payload.get("structure_time"),
        "feature_cutoff_time": payload.get("feature_cutoff_time") or payload.get("signal_time"),
        "sweep_time": payload.get("sweep_time"),
        "reclaim_time": payload.get("reclaim_time"),
        "signal_time": payload.get("signal_time"),
        "entry_time": payload.get("entry_time"),
        "exit_time": payload.get("exit_time"),
        "bar_confirmed": payload.get("bar_confirmed", True),
        "no_lookahead_safe": payload.get("no_lookahead_safe"),
        "gross_R": None if net_before_cost is None else net_before_cost + (_float(payload.get("estimated_cost_r")) or 0.0),
        "net_R": net_r,
        "net_return_on_notional": _float(payload.get("net_return_on_notional")),
        "mfe_R": _float(payload.get("mfe_R")),
        "MFE_R": _float(payload.get("mfe_R")),
        "mae_R": _float(payload.get("mae_R")),
        "MAE_R": _float(payload.get("mae_R")),
        "mfe_capture_ratio": mfe_capture,
        "exit_reason": exit_reason,
        "time_cut_exit": "time_cut" in str(exit_reason),
        "profitable_time_cut": "time_cut" in str(exit_reason) and net_r is not None and net_r > 0,
        "loss_time_cut": "time_cut" in str(exit_reason) and net_r is not None and net_r < 0,
        "giveback_from_MFE": _giveback(_float(payload.get("mfe_R")), net_before_cost),
        "actual_risk_pct_after_cap": actual_risk,
        "risk_utilization": None if not target_risk or actual_risk is None else actual_risk / target_risk,
        "notional_cap_hit": _truthy(payload.get("capped_by_notional")),
        "notional_to_equity_pct": _float(payload.get("notional_to_equity_pct")),
        "margin_required_pct": _float(payload.get("margin_required_pct")),
        "portfolio_heat": _float(payload.get("portfolio_heat")),
        "margin_required": _float(payload.get("margin_required")),
        "same_bar_ambiguous": _truthy(payload.get("same_bar_ambiguous")),
        "forced_pessimistic_exit": _truthy(payload.get("forced_pessimistic_exit")),
        "liquidation_event": _truthy(payload.get("liquidation_event")),
        "fee_cost": _float(payload.get("estimated_cost_r")) or 0.0,
        "slippage_cost": float(tier["slippage_cost"]),
        "funding_cost": (_float(payload.get("funding_paid_or_received")) or 0.0) + float(tier["funding_cost"]),
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _event_selection_rows(combo_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_event: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in combo_rows:
        if row["cost_tier"] != "base":
            continue
        by_event.setdefault((row["event_key"], str(row["direction"])), []).append(row)
    selection_rows = []
    overlapping = 0
    for (event_key, direction), rows in by_event.items():
        unique = _unique_combo_rows(rows)
        if len(unique) > 1:
            overlapping += 1
        selected = min(unique, key=lambda row: row["priority"])
        suppressed = [row["combo_name"] for row in unique if row["combo_name"] != selected["combo_name"]]
        selection_rows.append(
            {
                "event_key": event_key,
                "asset": selected.get("asset"),
                "profile": selected.get("profile"),
                "direction": direction,
                "selected_combo": selected["combo_name"],
                "selected_tier": selected["tier"],
                "suppressed_combos": suppressed,
                "suppression_reason": "higher_priority_combo_selected" if suppressed else "",
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return selection_rows, overlapping


def _unique_combo_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_combo: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_combo.setdefault(str(row["combo_name"]), row)
    return list(by_combo.values())


def _grouped_rows(combo_rows: list[dict[str, Any]], selected_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for combo in COMBOS:
        for cost_tier in COST_TIERS:
            all_combo = [row for row in combo_rows if row["combo_name"] == combo.name and row["cost_tier"] == cost_tier]
            selected = [row for row in selected_rows if row["combo_name"] == combo.name and row["cost_tier"] == cost_tier]
            rows.append(_summary_row(all_combo, selected, combo=combo, cost_tier=cost_tier, key=None))
            for key in _group_keys(selected):
                rows.append(_summary_row(all_combo, [row for row in selected if _group_key(row) == key], combo=combo, cost_tier=cost_tier, key=key))
    return rows


def _portfolio_rows(selected_rows: list[dict[str, Any]], overlapping_event_count: int) -> list[dict[str, Any]]:
    rows = []
    for cost_tier in COST_TIERS:
        selected = [row for row in selected_rows if row["cost_tier"] == cost_tier]
        rows.append(_portfolio_summary(selected, cost_tier=cost_tier, tier="ALL", overlapping_event_count=overlapping_event_count))
        for tier in ("Tier 1", "Tier 2", "Tier 3"):
            rows.append(_portfolio_summary([row for row in selected if row["tier"] == tier], cost_tier=cost_tier, tier=tier, overlapping_event_count=overlapping_event_count))
    return rows


def _summary_row(
    all_combo: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    *,
    combo: ComboSpec,
    cost_tier: str,
    key: tuple[str, str, str, str, str, str, str, str] | None,
) -> dict[str, Any]:
    if key is None:
        asset = profile = direction = structure_source = attempt_type = exit_profile = sizing_policy = tier = "ALL"
    else:
        asset, profile, direction, structure_source, attempt_type, exit_profile, sizing_policy, tier = key
    return {
        **_metrics(selected),
        "combo_name": combo.name,
        "tier": combo.tier if key is None else tier,
        "cost_tier": cost_tier,
        "asset": asset,
        "profile": profile,
        "direction": direction,
        "structure_source": structure_source,
        "attempt_type": attempt_type,
        "exit_profile": exit_profile,
        "sizing_policy": sizing_policy,
        "candidates": len({row["event_key"] for row in all_combo}),
        "selected_trades": len({row["event_key"] for row in selected}),
        "suppressed_trades": max(0, len({row["event_key"] for row in all_combo}) - len({row["event_key"] for row in selected})),
        "incremental_trades": len([row for row in selected if row.get("closed_trade")]),
        "duplicate_event_count": _duplicate_selected_events(selected),
        "overlapping_event_count": 0,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _portfolio_summary(
    selected: list[dict[str, Any]], *, cost_tier: str, tier: str, overlapping_event_count: int
) -> dict[str, Any]:
    return {
        **_metrics(selected),
        "portfolio": "combined_lr_family",
        "tier": tier,
        "cost_tier": cost_tier,
        "candidates": len({row["event_key"] for row in selected}),
        "selected_trades": len({row["event_key"] for row in selected}),
        "suppressed_trades": 0,
        "incremental_trades": sum(1 for row in selected if row.get("closed_trade")),
        "duplicate_event_count": _duplicate_selected_events(selected),
        "overlapping_event_count": overlapping_event_count if tier == "ALL" else 0,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [row for row in rows if row.get("row_type") == "closed_trade" and row.get("closed_trade")]
    net = [_float(row.get("net_R")) for row in closed]
    mfe = [_float(row.get("mfe_R")) for row in closed]
    mae = [_float(row.get("mae_R")) for row in closed]
    time_cut = [row for row in closed if row.get("time_cut_exit")]
    total_net = sum(value for value in net if value is not None)
    return {
        "closed_trades": len(closed),
        "gross_R": _avg([_float(row.get("gross_R")) for row in closed]),
        "net_R_avg": _avg(net),
        "net_R_p50": _pct(net, 50),
        "net_R_p75": _pct(net, 75),
        "total_net_R": total_net,
        "profit_factor": _profit_factor([value for value in net if value is not None]),
        "win_rate": _ratio(sum(1 for value in net if value is not None and value > 0), len(net)),
        "expectancy_R": _avg(net),
        "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in rows]),
        "contribution_to_portfolio_net_R": total_net,
        "max_drawdown": _max_drawdown([value or 0.0 for value in net]),
        "max_consecutive_losses": _max_consecutive_losses([value or 0.0 for value in net]),
        "recovery_factor": _recovery_factor([value or 0.0 for value in net]),
        "portfolio_heat_max": _max([_float(row.get("portfolio_heat")) for row in rows]),
        "margin_required_max": _max([_float(row.get("margin_required")) for row in rows]),
        "liquidation_event_count": sum(1 for row in rows if row.get("liquidation_event")),
        "MFE_R_avg": _avg(mfe),
        "MFE_R_p50": _pct(mfe, 50),
        "MFE_R_p75": _pct(mfe, 75),
        "MFE_R_p90": _pct(mfe, 90),
        "MAE_R_avg": _avg(mae),
        "MAE_R_p50": _pct(mae, 50),
        "MAE_R_p75": _pct(mae, 75),
        "MAE_R_p90": _pct(mae, 90),
        "MFE_capture_ratio": _avg([_float(row.get("mfe_capture_ratio")) for row in closed]),
        "MFE_ge_0_5_ratio": _ratio(sum(1 for value in mfe if value is not None and value >= 0.5), len(mfe)),
        "MFE_ge_1_0_ratio": _ratio(sum(1 for value in mfe if value is not None and value >= 1.0), len(mfe)),
        "time_cut_exit_rate": _ratio(len(time_cut), len(closed)),
        "profitable_time_cut_ratio": _ratio(sum(1 for row in time_cut if row.get("profitable_time_cut")), len(time_cut)),
        "loss_time_cut_ratio": _ratio(sum(1 for row in time_cut if row.get("loss_time_cut")), len(time_cut)),
        "bad_time_cut_ratio": _ratio(sum(1 for row in time_cut if row.get("loss_time_cut")), len(time_cut)),
        "time_cut_net_R_avg": _avg([_float(row.get("net_R")) for row in time_cut]),
        "giveback_from_MFE_avg": _avg([_float(row.get("giveback_from_MFE")) for row in time_cut]),
        "actual_risk_pct_after_cap_p50": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in rows], 50),
        "actual_risk_pct_after_cap_p75": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in rows], 75),
        "actual_risk_pct_after_cap_p90": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in rows], 90),
        "risk_utilization_p50": _pct([_float(row.get("risk_utilization")) for row in rows], 50),
        "risk_utilization_p75": _pct([_float(row.get("risk_utilization")) for row in rows], 75),
        "risk_utilization_p90": _pct([_float(row.get("risk_utilization")) for row in rows], 90),
        "notional_cap_hit_ratio": _ratio(sum(1 for row in rows if row.get("notional_cap_hit")), len(rows)),
        "notional_to_equity_pct_p50": _pct([_float(row.get("notional_to_equity_pct")) for row in rows], 50),
        "notional_to_equity_pct_p75": _pct([_float(row.get("notional_to_equity_pct")) for row in rows], 75),
        "notional_to_equity_pct_p90": _pct([_float(row.get("notional_to_equity_pct")) for row in rows], 90),
        "margin_required_pct_p50": _pct([_float(row.get("margin_required_pct")) for row in rows], 50),
        "margin_required_pct_p75": _pct([_float(row.get("margin_required_pct")) for row in rows], 75),
        "margin_required_pct_p90": _pct([_float(row.get("margin_required_pct")) for row in rows], 90),
        "same_bar_ambiguous_count": sum(1 for row in rows if row.get("same_bar_ambiguous")),
        "forced_pessimistic_exit_count": sum(1 for row in rows if row.get("forced_pessimistic_exit")),
        "fee_cost": sum(_float(row.get("fee_cost")) or 0.0 for row in rows),
        "slippage_cost": sum(_float(row.get("slippage_cost")) or 0.0 for row in rows),
        "funding_cost": sum(_float(row.get("funding_cost")) or 0.0 for row in rows),
    }


def _write_outputs(result: LRCombinedCandidateProposalResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_combined_candidate_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_combined_candidate_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_combined_combo_rows.jsonl", result.combo_rows)
    _write_jsonl(output_dir / "lr_combined_event_selection_rows.jsonl", result.event_selection_rows)
    _write_jsonl(output_dir / "lr_combined_grouped_rows.jsonl", result.grouped_rows)
    _write_jsonl(output_dir / "lr_combined_portfolio_rows.jsonl", result.portfolio_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_combined_candidate_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-combined-candidate-proposal",
        notes="PR11G proposal-only combined LR candidate evaluation.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_combined_candidate_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-combined-candidate-proposal",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11G combined candidate proposal; no formal strategy config change.",
        tags=["PR11G", "proposal_only", "combined_lr"],
    )


def _report(result: LRCombinedCandidateProposalResult) -> str:
    lines = [
        "# PR 11G Combined LR Candidate Proposal Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- all_combined_candidates = proposal-only",
        "- dynamic_time_cut = audited proposal-only",
        "- quality_aware_capped_sizing = proposal-only",
        "- Session_HL source = proposal-only",
        "- robustness belongs to PR 11H",
        "- cleanup / merge belongs to PR 12",
        "",
        "## Combined Portfolio Summary",
    ]
    for row in result.portfolio_rows:
        if row["cost_tier"] == "base":
            lines.append(
                f"- {row['tier']}: selected={row['selected_trades']} closed={row['closed_trades']} "
                f"net_R={row['net_R_avg']} total_net_R={row['total_net_R']} "
                f"PF={row['profit_factor']} bad_time_cut={row['bad_time_cut_ratio']}"
            )
    lines.extend(["", "## Combo Summary"])
    for row in result.grouped_rows:
        if row["cost_tier"] == "base" and row["asset"] == "ALL":
            lines.append(
                f"- {row['combo_name']}: candidates={row['candidates']} selected={row['selected_trades']} "
                f"closed={row['closed_trades']} net_R={row['net_R_avg']} "
                f"incremental={row['incremental_trades']}"
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


def _primary_decision(
    portfolio_rows: list[dict[str, Any]], grouped_rows: list[dict[str, Any]], duplicate_event_count: int
) -> str:
    if duplicate_event_count:
        return "F"
    base = _portfolio_row(portfolio_rows, "ALL", "base")
    harsh = _portfolio_row(portfolio_rows, "ALL", "harsh")
    tier2 = _portfolio_row(portfolio_rows, "Tier 2", "base")
    tier1 = _portfolio_row(portfolio_rows, "Tier 1", "base")
    if not base or not harsh or (base["closed_trades"] or 0) == 0:
        return "F"
    if (base["net_R_avg"] or 0.0) > 0 and (harsh["net_R_avg"] or 0.0) > 0 and (tier2["closed_trades"] or 0) > 0:
        if (tier1["net_R_avg"] or 0.0) > 0 and (tier2["net_R_avg"] or 0.0) > 0:
            return "A"
        return "B"
    return "E"


def _secondary_findings(
    grouped_rows: list[dict[str, Any]], portfolio_rows: list[dict[str, Any]]
) -> list[str]:
    tier2 = _portfolio_row(portfolio_rows, "Tier 2", "base")
    tier3 = _portfolio_row(portfolio_rows, "Tier 3", "base")
    best_combo = max(
        [row for row in grouped_rows if row["cost_tier"] == "base" and row["asset"] == "ALL"],
        key=lambda row: row.get("total_net_R") or -999,
    )
    return [
        f"Tier 2 coverage incremental_trades={tier2['incremental_trades'] if tier2 else 0}，用于补充 Tier 1 未覆盖事件。",
        f"Tier 3 diagnostic incremental_trades={tier3['incremental_trades'] if tier3 else 0}，默认不进入主正式候选。",
        f"当前组合总贡献最高的单 combo 是 {best_combo['combo_name']}，total_net_R={best_combo['total_net_R']}。",
        "dynamic_time_cut 在组合层仍保持 proposal-only，需 PR 11H 做稳健性验证。",
        "quality-aware sizing 未写入正式配置，PR 11G 仅用于组合归因和风险预算候选筛选。",
    ]


def _decision_text(decision: str) -> str:
    return {
        "A": "Combined LR family 有明确价值，按计划进入 PR 11H robustness。",
        "B": "只有 Tier 1 有价值，Tier 2/3 保留 diagnostic，按计划进入 PR 11H。",
        "C": "Tier 2 coverage 有增量价值，但需要 PR 11G-fix 调整去重 / 风险预算。",
        "D": "dynamic_time_cut 或 quality-aware sizing 在组合层面失效，需要 PR 11G-fix。",
        "E": "combined portfolio 不优于单一 setup，退回单一核心组合后进入 PR 11H。",
        "F": "数据或执行审计不足，需要留在 PR 11G 修复。",
    }[decision]


def _portfolio_row(rows: list[dict[str, Any]], tier: str, cost_tier: str) -> dict[str, Any] | None:
    for row in rows:
        if row["tier"] == tier and row["cost_tier"] == cost_tier:
            return row
    return None


def _approved_for_policy(row: dict[str, Any], policy: str, attempt_type: str) -> bool:
    if policy == "current_risk_based_sizing":
        return _truthy(row.get("formal_approved"))
    if policy == "quality_aware_capped_sizing":
        return attempt_type in {"attempt_3_choch_mss_entry", "attempt_4_displacement_entry"} and _truthy(row.get("proposal_approved"))
    return _truthy(row.get("proposal_approved"))


def _exit_outcome(payload: dict[str, Any], exit_profile: str) -> tuple[float | None, str, float | None]:
    if payload.get("net_R") is None:
        return None, "not_executed", None
    mfe = _float(payload.get("mfe_R")) or 0.0
    baseline_net = _float(payload.get("net_R")) or 0.0
    if exit_profile == "fixed_2R_time_cut":
        return baseline_net, str(payload.get("exit_reason") or "unknown"), _ratio_value(max(baseline_net, 0.0), mfe)
    if exit_profile == "conservative_1_5R_full":
        if mfe >= 1.5:
            return 1.5, "take_profit", _ratio_value(1.5, mfe)
        return min(baseline_net, 0.3), "time_cut_exit", _ratio_value(max(min(baseline_net, 0.3), 0.0), mfe)
    if mfe >= 1.5:
        net = min(mfe, 2.0)
        return net, "dynamic_time_cut_target", _ratio_value(net, mfe)
    if mfe >= 0.5:
        net = max(baseline_net, 0.25)
        return net, "dynamic_time_cut_exit", _ratio_value(max(net, 0.0), mfe)
    net = min(baseline_net, -0.1)
    return net, "dynamic_time_cut_exit", _ratio_value(max(net, 0.0), mfe)


def _target_risk(payload: dict[str, Any], policy: str, attempt_type: str) -> float | None:
    base = _float(payload.get("target_risk_pct")) or _float(payload.get("risk_pct")) or 0.005
    if policy == "quality_aware_capped_sizing" and attempt_type == "attempt_3_choch_mss_entry":
        return base * 0.75
    return base


def _actual_risk(payload: dict[str, Any], policy: str, attempt_type: str) -> float | None:
    base = _float(payload.get("actual_risk_pct_after_cap")) or _float(payload.get("capped_actual_risk_pct")) or _float(payload.get("risk_pct"))
    target = _target_risk(payload, policy, attempt_type)
    original = _float(payload.get("target_risk_pct")) or _float(payload.get("risk_pct")) or 0.005
    if policy != "quality_aware_capped_sizing" or base is None or target is None or original == 0:
        return base
    return min(base, target) if base <= original else base * target / original


def _event_key(row: dict[str, Any]) -> str:
    if row.get("event_id"):
        return str(row.get("event_id"))
    if row.get("candidate_id"):
        return str(row.get("candidate_id"))
    seed = {
        "asset": row.get("asset"),
        "profile": row.get("profile"),
        "direction": row.get("direction"),
        "sweep_time": row.get("sweep_time"),
        "reclaim_time": row.get("reclaim_time"),
        "structure_level": row.get("structure_level"),
    }
    return hashlib.sha256(json.dumps(seed, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _duplicate_selected_events(rows: list[dict[str, Any]]) -> int:
    keys = [row["event_key"] for row in rows if row["cost_tier"] == "base"]
    return len(keys) - len(set(keys))


def _matches_attempt(row: dict[str, Any], attempt: str) -> bool:
    if attempt == "attempt_3_choch_mss_entry":
        return _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true"
    if attempt == "attempt_4_displacement_entry":
        return _truthy(row.get("displacement_after_reclaim")) and _truthy(row.get("displacement_direction_valid"))
    return True


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


def _group_keys(rows: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str, str, str, str]]:
    return sorted({_group_key(row) for row in rows})


def _group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        str(row.get("asset", "")),
        str(row.get("profile", "")),
        str(row.get("direction", "")),
        str(row.get("structure_source", "")),
        str(row.get("attempt_type", "")),
        str(row.get("exit_profile", "")),
        str(row.get("sizing_policy", "")),
        str(row.get("tier", "")),
    )


def _giveback(mfe: float | None, net_before_cost: float | None) -> float | None:
    if mfe is None or net_before_cost is None:
        return None
    return max(0.0, mfe - max(net_before_cost, 0.0))


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
    clean = list(values)
    wins = sum(value for value in clean if value > 0)
    losses = abs(sum(value for value in clean if value < 0))
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
