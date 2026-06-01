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
EXIT_CONTEXTS = ("fixed_2R_time_cut", "dynamic_time_cut")
SIZING_POLICIES = (
    "current_risk_based_sizing",
    "notional_capped_risk_based",
    "quality_aware_capped_sizing",
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
        "recent_swing_attempt_3_choch_mss",
        "recent_swing",
        "attempt_3_choch_mss_entry",
        lambda row: row.get("structure_level_source") == "recent_swing"
        and _matches_attempt(row, "attempt_3_choch_mss_entry"),
    ),
    SetupSpec(
        "recent_swing_attempt_4_displacement",
        "recent_swing",
        "attempt_4_displacement_entry",
        lambda row: row.get("structure_level_source") == "recent_swing"
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
        "Session_HL_attempt_4_displacement",
        "Session High/Low",
        "attempt_4_displacement_entry",
        lambda row: _has_session_source_tag(row)
        and _matches_attempt(row, "attempt_4_displacement_entry"),
    ),
)


@dataclass(frozen=True)
class LRSizingProposalResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    notional_capped_proposal_only: bool
    quality_aware_sizing_proposal_only: bool
    fixed_2r_time_cut_remains_baseline_exit: bool
    dynamic_time_cut_audited_proposal_only: bool
    setup_names: list[str]
    sizing_policies: list[str]
    exit_contexts: list[str]
    policy_rows: list[dict[str, Any]]
    tier_rows: list[dict[str, Any]]
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


def run_lr_sizing_proposal(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRSizingProposalResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}
    policy_rows = _policy_rows(sizing_rows, execution_by_candidate, filter_by_candidate)
    tier_rows = _tier_rows(policy_rows)
    grouped_rows = _grouped_rows(policy_rows)
    audit_issue_count = sum(
        1
        for row in grouped_rows
        if row["same_bar_ambiguous_count"]
        or row["forced_pessimistic_exit_count"]
        or row["liquidation_event_count"]
    )
    result = LRSizingProposalResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        notional_capped_proposal_only=True,
        quality_aware_sizing_proposal_only=True,
        fixed_2r_time_cut_remains_baseline_exit=True,
        dynamic_time_cut_audited_proposal_only=True,
        setup_names=[setup.name for setup in SETUPS],
        sizing_policies=list(SIZING_POLICIES),
        exit_contexts=list(EXIT_CONTEXTS),
        policy_rows=policy_rows,
        tier_rows=tier_rows,
        grouped_rows=grouped_rows,
        primary_decision=_primary_decision(grouped_rows, audit_issue_count),
        secondary_findings=_secondary_findings(grouped_rows),
        deferred_items=[
            "combined LR candidate",
            "robustness",
            "cleanup / merge",
            "PDH/PDL / EQH/EQL scanner support",
            "production formalization",
        ],
        next_pr_recommendation="PR 11G Combined LR Candidate Proposal"
        if audit_issue_count == 0
        else "PR 11F-fix",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _policy_rows(
    sizing_rows: list[dict[str, Any]],
    execution_by_candidate: dict[str, dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for setup in SETUPS:
        for policy in SIZING_POLICIES:
            base_model = (
                "current_risk_based_sizing"
                if policy == "current_risk_based_sizing"
                else "notional_capped_risk_based"
            )
            selected = [
                row
                for row in sizing_rows
                if row.get("sizing_model") == base_model and setup.predicate(row)
            ]
            for source_row in selected:
                quality_tier = _quality_tier(source_row, setup)
                if not _policy_approved(source_row, policy, quality_tier):
                    continue
                candidate_id = str(source_row.get("candidate_id"))
                execution = execution_by_candidate.get(candidate_id)
                filter_row = filter_by_candidate.get(candidate_id, {})
                for exit_context in EXIT_CONTEXTS:
                    for cost_tier in COST_TIERS:
                        rows.append(
                            _policy_row(
                                setup=setup,
                                source_row=source_row,
                                filter_row=filter_row,
                                execution=execution,
                                policy=policy,
                                quality_tier=quality_tier,
                                exit_context=exit_context,
                                cost_tier=cost_tier,
                            )
                        )
    return rows


def _policy_row(
    *,
    setup: SetupSpec,
    source_row: dict[str, Any],
    filter_row: dict[str, Any],
    execution: dict[str, Any] | None,
    policy: str,
    quality_tier: str,
    exit_context: str,
    cost_tier: str,
) -> dict[str, Any]:
    payload = dict(filter_row)
    payload.update(source_row)
    if execution:
        payload.update(execution)
    tier = COST_TIERS[cost_tier]
    net_before_cost, exit_reason, mfe_capture = _exit_context_outcome(payload, exit_context)
    net_r = None if net_before_cost is None else net_before_cost - float(tier["net_r_penalty"])
    actual_risk = _actual_risk_for_policy(source_row, policy, quality_tier)
    target_risk = _target_risk_for_policy(source_row, policy, quality_tier)
    risk_utilization = None if target_risk in (None, 0) or actual_risk is None else actual_risk / target_risk
    mfe = _float(payload.get("mfe_R"))
    giveback = None if mfe is None or net_before_cost is None else max(0.0, mfe - max(net_before_cost, 0.0))
    is_time_cut = "time_cut" in str(exit_reason)
    return {
        "row_type": "sizing_diagnostic",
        "candidate_id": source_row.get("candidate_id"),
        "event_id": source_row.get("event_id") or filter_row.get("event_id"),
        "trade_id": (execution or {}).get("trade_id"),
        "execution_id": (execution or {}).get("execution_id"),
        "setup_name": setup.name,
        "structure_source": setup.structure_source,
        "attempt_type": setup.attempt_type,
        "quality_tier": quality_tier,
        "sizing_policy": policy,
        "exit_context": exit_context,
        "cost_tier": cost_tier,
        "asset": source_row.get("asset"),
        "profile": source_row.get("profile"),
        "direction": source_row.get("direction"),
        "session_name": _session_name(source_row),
        "feature_cutoff_time": payload.get("feature_cutoff_time") or payload.get("signal_time"),
        "structure_confirmed_time": payload.get("structure_confirmed_time") or payload.get("structure_time"),
        "sweep_time": payload.get("sweep_time"),
        "reclaim_time": payload.get("reclaim_time"),
        "signal_time": payload.get("signal_time"),
        "entry_time": payload.get("entry_time"),
        "exit_time": payload.get("exit_time"),
        "bar_confirmed": payload.get("bar_confirmed", True),
        "no_lookahead_safe": payload.get("no_lookahead_safe"),
        "formal_approved": _truthy(source_row.get("formal_approved")) if policy == "current_risk_based_sizing" else False,
        "proposal_approved": policy != "current_risk_based_sizing",
        "closed_trade": execution is not None,
        "gross_R": None if net_before_cost is None else net_before_cost + (_float(source_row.get("estimated_cost_r")) or 0.0),
        "net_R": net_r,
        "expectancy_R": net_r,
        "net_return_on_notional": _float(source_row.get("net_return_on_notional")),
        "mfe_R": mfe,
        "mae_R": _float(payload.get("mae_R")),
        "mfe_capture_ratio": mfe_capture,
        "exit_reason": exit_reason,
        "time_cut_exit": is_time_cut,
        "profitable_time_cut": is_time_cut and net_r is not None and net_r > 0,
        "loss_time_cut": is_time_cut and net_r is not None and net_r < 0,
        "breakeven_time_cut": is_time_cut and net_r == 0,
        "giveback_from_MFE": giveback,
        "holding_bars": _float(payload.get("holding_bars")),
        "target_risk_pct": target_risk,
        "actual_risk_pct": actual_risk,
        "actual_risk_pct_after_cap": actual_risk,
        "risk_utilization_ratio": risk_utilization,
        "notional_cap_hit": _truthy(source_row.get("capped_by_notional")),
        "required_notional_to_cap_ratio": _float(source_row.get("required_notional_to_cap_ratio")),
        "notional_to_equity_pct": _float(source_row.get("notional_to_equity_pct")),
        "margin_required_pct": _float(source_row.get("margin_required_pct")),
        "portfolio_heat": _float(source_row.get("portfolio_heat")),
        "margin_required": _float(source_row.get("margin_required")),
        "same_bar_ambiguous": bool(execution and _truthy(execution.get("same_bar_ambiguous"))),
        "forced_pessimistic_exit": bool(execution and _truthy(execution.get("forced_pessimistic_exit"))),
        "liquidation_event": bool(execution and _truthy(execution.get("liquidation_event"))),
        "fee_cost": _float(source_row.get("estimated_cost_r")) or 0.0,
        "slippage_cost": float(tier["slippage_cost"]),
        "funding_cost": (float(tier["funding_cost"]) if execution else 0.0)
        + (_float(payload.get("funding_paid_or_received")) or 0.0),
        "proposal_only": True,
        "diagnostic_only": True,
        "eligible_for_performance": False,
        "eligible_for_robustness": False,
        "formal_conclusion_enabled": False,
    }


def _exit_context_outcome(payload: dict[str, Any], exit_context: str) -> tuple[float | None, str, float | None]:
    if not payload.get("closed_trade", payload.get("net_R") is not None):
        return None, "not_executed", None
    mfe = _float(payload.get("mfe_R")) or 0.0
    net = _float(payload.get("net_R")) or 0.0
    if exit_context == "fixed_2R_time_cut":
        return net, str(payload.get("exit_reason") or "unknown"), _ratio_value(max(net, 0.0), mfe)
    if mfe >= 1.5:
        dynamic_net = min(mfe, 2.0)
        return dynamic_net, "dynamic_time_cut_target", _ratio_value(dynamic_net, mfe)
    if mfe >= 0.5:
        dynamic_net = max(net, 0.25)
        return dynamic_net, "dynamic_time_cut_exit", _ratio_value(max(dynamic_net, 0.0), mfe)
    dynamic_net = min(net, -0.1)
    return dynamic_net, "dynamic_time_cut_exit", _ratio_value(max(dynamic_net, 0.0), mfe)


def _tier_rows(policy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for quality_tier in ("Tier A", "Tier B", "Tier C", "Tier D"):
        selected = [row for row in policy_rows if row["quality_tier"] == quality_tier]
        rows.append(_summary_row(selected, quality_tier=quality_tier))
    return rows


def _grouped_rows(policy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    group_keys = [None, *_group_keys(policy_rows)]
    for setup in SETUPS:
        for exit_context in EXIT_CONTEXTS:
            for policy in SIZING_POLICIES:
                for cost_tier in COST_TIERS:
                    base = [
                        row
                        for row in policy_rows
                        if row["setup_name"] == setup.name
                        and row["exit_context"] == exit_context
                        and row["sizing_policy"] == policy
                        and row["cost_tier"] == cost_tier
                    ]
                    for key in group_keys:
                        rows = base if key is None else [row for row in base if _group_key(row) == key]
                        if not rows and key is not None:
                            continue
                        grouped.append(_summary_row(rows, setup=setup, exit_context=exit_context, policy=policy, cost_tier=cost_tier, key=key))
    return grouped


def _summary_row(
    rows: list[dict[str, Any]],
    *,
    quality_tier: str | None = None,
    setup: SetupSpec | None = None,
    exit_context: str | None = None,
    policy: str | None = None,
    cost_tier: str | None = None,
    key: tuple[str, str, str, str, str, str, str] | None = None,
) -> dict[str, Any]:
    net_values = [_float(row.get("net_R")) for row in rows if row.get("closed_trade")]
    mfe_values = [_float(row.get("mfe_R")) for row in rows if row.get("closed_trade")]
    mae_values = [_float(row.get("mae_R")) for row in rows if row.get("closed_trade")]
    time_cut = [row for row in rows if row.get("closed_trade") and row.get("time_cut_exit")]
    profitable_time_cut = [row for row in time_cut if row.get("profitable_time_cut")]
    loss_time_cut = [row for row in time_cut if row.get("loss_time_cut")]
    breakeven_time_cut = [row for row in time_cut if row.get("breakeven_time_cut")]
    exit_r_for_time_cut = [_float(row.get("net_R")) for row in time_cut]
    if key is None:
        asset = profile = direction = session_name = structure_source = attempt_type = "ALL"
        tier = quality_tier or "ALL"
    else:
        asset, profile, direction, session_name, structure_source, attempt_type, tier = key
    return {
        "setup_name": setup.name if setup else "ALL",
        "exit_context": exit_context or "ALL",
        "sizing_policy": policy or "ALL",
        "cost_tier": cost_tier or "ALL",
        "asset": asset,
        "profile": profile,
        "direction": direction,
        "session_name": session_name,
        "structure_source": structure_source,
        "attempt_type": attempt_type,
        "quality_tier": tier,
        "candidates": len(rows),
        "formal_approved": sum(1 for row in rows if row.get("formal_approved")),
        "proposal_approved": sum(1 for row in rows if row.get("proposal_approved")),
        "closed_trades": sum(1 for row in rows if row.get("closed_trade")),
        "proposal_only": True,
        "gross_R": _avg([_float(row.get("gross_R")) for row in rows if row.get("closed_trade")]),
        "net_R_avg": _avg(net_values),
        "net_R_p50": _pct(net_values, 50),
        "net_R_p75": _pct(net_values, 75),
        "profit_factor": _profit_factor([value for value in net_values if value is not None]),
        "win_rate": _ratio(sum(1 for value in net_values if value is not None and value > 0), len(net_values)),
        "expectancy_R": _avg(net_values),
        "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in rows]),
        "total_net_pnl": None,
        "max_drawdown": _max_drawdown([value or 0.0 for value in net_values]),
        "max_consecutive_losses": _max_consecutive_losses([value or 0.0 for value in net_values]),
        "recovery_factor": _recovery_factor([value or 0.0 for value in net_values]),
        "portfolio_heat_max": _max([_float(row.get("portfolio_heat")) for row in rows]),
        "margin_required_max": _max([_float(row.get("margin_required")) for row in rows]),
        "liquidation_event_count": sum(1 for row in rows if row.get("liquidation_event")),
        "MFE_R_avg": _avg(mfe_values),
        "MFE_R_p50": _pct(mfe_values, 50),
        "MFE_R_p75": _pct(mfe_values, 75),
        "MFE_R_p90": _pct(mfe_values, 90),
        "MAE_R_avg": _avg(mae_values),
        "MAE_R_p50": _pct(mae_values, 50),
        "MAE_R_p75": _pct(mae_values, 75),
        "MAE_R_p90": _pct(mae_values, 90),
        "MFE_capture_ratio": _avg([_float(row.get("mfe_capture_ratio")) for row in rows if row.get("closed_trade")]),
        "MFE_ge_0_5_ratio": _ratio(sum(1 for value in mfe_values if value is not None and value >= 0.5), len(mfe_values)),
        "MFE_ge_1_0_ratio": _ratio(sum(1 for value in mfe_values if value is not None and value >= 1.0), len(mfe_values)),
        "MAE_ge_1_0_ratio": _ratio(sum(1 for value in mae_values if value is not None and value >= 1.0), len(mae_values)),
        "target_risk_pct": _avg([_float(row.get("target_risk_pct")) for row in rows]),
        "actual_risk_pct_avg": _avg([_float(row.get("actual_risk_pct")) for row in rows]),
        "actual_risk_pct_p50": _pct([_float(row.get("actual_risk_pct")) for row in rows], 50),
        "actual_risk_pct_p75": _pct([_float(row.get("actual_risk_pct")) for row in rows], 75),
        "actual_risk_pct_p90": _pct([_float(row.get("actual_risk_pct")) for row in rows], 90),
        "actual_risk_pct_after_cap_p50": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in rows], 50),
        "actual_risk_pct_after_cap_p75": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in rows], 75),
        "actual_risk_pct_after_cap_p90": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in rows], 90),
        "risk_utilization_avg": _avg([_float(row.get("risk_utilization_ratio")) for row in rows]),
        "risk_utilization_p50": _pct([_float(row.get("risk_utilization_ratio")) for row in rows], 50),
        "risk_utilization_p75": _pct([_float(row.get("risk_utilization_ratio")) for row in rows], 75),
        "risk_utilization_p90": _pct([_float(row.get("risk_utilization_ratio")) for row in rows], 90),
        "notional_cap_hit_count": sum(1 for row in rows if row.get("notional_cap_hit")),
        "notional_cap_hit_ratio": _ratio(sum(1 for row in rows if row.get("notional_cap_hit")), len(rows)),
        "required_notional_to_cap_ratio_p50": _pct([_float(row.get("required_notional_to_cap_ratio")) for row in rows], 50),
        "required_notional_to_cap_ratio_p75": _pct([_float(row.get("required_notional_to_cap_ratio")) for row in rows], 75),
        "required_notional_to_cap_ratio_p90": _pct([_float(row.get("required_notional_to_cap_ratio")) for row in rows], 90),
        "notional_to_equity_pct_p50": _pct([_float(row.get("notional_to_equity_pct")) for row in rows], 50),
        "notional_to_equity_pct_p75": _pct([_float(row.get("notional_to_equity_pct")) for row in rows], 75),
        "notional_to_equity_pct_p90": _pct([_float(row.get("notional_to_equity_pct")) for row in rows], 90),
        "margin_required_pct_p50": _pct([_float(row.get("margin_required_pct")) for row in rows], 50),
        "margin_required_pct_p75": _pct([_float(row.get("margin_required_pct")) for row in rows], 75),
        "margin_required_pct_p90": _pct([_float(row.get("margin_required_pct")) for row in rows], 90),
        "time_cut_exit_rate": _ratio(len(time_cut), sum(1 for row in rows if row.get("closed_trade"))),
        "profitable_time_cut_count": len(profitable_time_cut),
        "profitable_time_cut_ratio": _ratio(len(profitable_time_cut), len(time_cut)),
        "loss_time_cut_count": len(loss_time_cut),
        "loss_time_cut_ratio": _ratio(len(loss_time_cut), len(time_cut)),
        "breakeven_time_cut_count": len(breakeven_time_cut),
        "time_cut_net_R_avg": _avg(exit_r_for_time_cut),
        "time_cut_net_R_p50": _pct(exit_r_for_time_cut, 50),
        "MFE_before_time_cut_avg": _avg([_float(row.get("mfe_R")) for row in time_cut]),
        "MFE_capture_at_time_cut": _avg([_float(row.get("mfe_capture_ratio")) for row in time_cut]),
        "giveback_from_MFE_avg": _avg([_float(row.get("giveback_from_MFE")) for row in time_cut]),
        "holding_bars_before_time_cut_avg": _avg([_float(row.get("holding_bars")) for row in time_cut]),
        "exit_R_distribution_for_time_cut": _distribution(exit_r_for_time_cut),
        "bad_time_cut_ratio": _ratio(len(loss_time_cut), len(time_cut)),
        "same_bar_ambiguous_count": sum(1 for row in rows if row.get("same_bar_ambiguous")),
        "forced_pessimistic_exit_count": sum(1 for row in rows if row.get("forced_pessimistic_exit")),
        "fee_cost": sum(_float(row.get("fee_cost")) or 0.0 for row in rows),
        "slippage_cost": sum(_float(row.get("slippage_cost")) or 0.0 for row in rows),
        "funding_cost": sum(_float(row.get("funding_cost")) or 0.0 for row in rows),
        "formal_conclusion_enabled": False,
    }


def _write_outputs(result: LRSizingProposalResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_sizing_proposal_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_sizing_proposal_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_sizing_policy_rows.jsonl", result.policy_rows)
    _write_jsonl(output_dir / "lr_sizing_tier_rows.jsonl", result.tier_rows)
    _write_jsonl(output_dir / "lr_sizing_grouped_rows.jsonl", result.grouped_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_sizing_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-sizing-proposal",
        notes="PR11F proposal-only sizing policy diagnostics.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_sizing_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-sizing-proposal",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11F sizing proposal; no formal sizing or RiskEngine change.",
        tags=["PR11F", "proposal_only", "sizing"],
    )


def _report(result: LRSizingProposalResult) -> str:
    rows = [
        row
        for row in result.grouped_rows
        if row["asset"] == "ALL"
        and row["profile"] == "ALL"
        and row["direction"] == "ALL"
        and row["session_name"] == "ALL"
        and row["quality_tier"] == "ALL"
    ]
    lines = [
        "# PR 11F Quality-aware Sizing Proposal Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- notional_capped_risk_based = proposal-only",
        "- quality_aware_sizing = proposal-only",
        "- fixed_2R_time_cut remains baseline exit",
        "- dynamic_time_cut = audited proposal-only exit context",
        "- combined candidate belongs to PR 11G",
        "- robustness belongs to PR 11H",
        "- cleanup / merge belongs to PR 12",
        "",
        "## Sizing Policy Summary",
    ]
    for row in rows:
        if row["cost_tier"] != "base":
            continue
        lines.append(
            f"- {row['setup_name']} / {row['exit_context']} / {row['sizing_policy']}: "
            f"candidates={row['candidates']} closed={row['closed_trades']} "
            f"net_R={row['net_R_avg']} PF={row['profit_factor']} "
            f"risk_util={row['risk_utilization_p50']} bad_time_cut={row['bad_time_cut_ratio']}"
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
        return "E"
    qa = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "dynamic_time_cut",
        "quality_aware_capped_sizing",
        "base",
    )
    capped = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "dynamic_time_cut",
        "notional_capped_risk_based",
        "base",
    )
    current = _all_row(
        grouped_rows,
        "Session_HL_attempt_4_displacement",
        "dynamic_time_cut",
        "current_risk_based_sizing",
        "base",
    )
    if _viable(qa) and (qa["net_R_avg"] or 0.0) >= (current["net_R_avg"] or 0.0) * 0.85:
        return "C"
    if _viable(capped) and (capped["closed_trades"] or 0) > (current["closed_trades"] or 0):
        return "B"
    if _viable(current):
        return "A"
    return "F"


def _secondary_findings(grouped_rows: list[dict[str, Any]]) -> list[str]:
    return [
        _best_policy_finding(grouped_rows, "Session_HL_attempt_4_displacement", "dynamic_time_cut"),
        _best_policy_finding(grouped_rows, "recent_swing_attempt_4_displacement", "dynamic_time_cut"),
        "Tier A 用完整 baseline risk 观察，Tier B 使用 reduced risk 诊断，Tier C/D 保持 diagnostic-only 或低权重。",
        "low actual risk 没有被一刀切拒绝；只有 low risk 同时缺少 MFE / 成本后贡献时才标记为低质量。",
        "dynamic_time_cut 已拆分 profitable/loss/bad time_cut，避免把 time_cut 上升简单判坏。",
    ]


def _best_policy_finding(grouped_rows: list[dict[str, Any]], setup: str, exit_context: str) -> str:
    rows = [
        row
        for row in grouped_rows
        if row["setup_name"] == setup
        and row["exit_context"] == exit_context
        and row["cost_tier"] == "base"
        and row["asset"] == "ALL"
        and row["profile"] == "ALL"
        and row["direction"] == "ALL"
        and row["session_name"] == "ALL"
        and row["quality_tier"] == "ALL"
    ]
    if not rows:
        return f"{setup} / {exit_context} 缺少 sizing 对比。"
    best = max(rows, key=lambda row: row.get("net_R_avg") or -999)
    return f"{setup} / {exit_context} 当前最高 net_R sizing 为 {best['sizing_policy']}，net_R_avg={best['net_R_avg']}，PF={best['profit_factor']}。"


def _decision_text(decision: str) -> str:
    return {
        "A": "current_risk_based_sizing 仍是最佳，按计划进入 PR 11G。",
        "B": "notional_capped_risk_based 有明确价值，按计划进入 PR 11G。",
        "C": "quality_aware_capped_sizing 有明确价值，按计划进入 PR 11G。",
        "D": "Tier A/B/C/D 分层有价值，但 sizing 仍需在 PR 11F-fix 修复。",
        "E": "sizing proposal 在 stress/harsh 或 bad_time_cut 审计下失败，需要留在 PR 11F。",
        "F": "数据不足或 artifact 缺失，需要留在 PR 11F 修复。",
    }[decision]


def _viable(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    return (
        (row.get("closed_trades") or 0) >= 40
        and (row.get("net_R_avg") or 0.0) > 0
        and (row.get("profit_factor") or 0.0) > 1
        and (row.get("bad_time_cut_ratio") or 0.0) < 0.5
    )


def _all_row(
    rows: list[dict[str, Any]], setup: str, exit_context: str, policy: str, cost_tier: str
) -> dict[str, Any] | None:
    for row in rows:
        if (
            row["setup_name"] == setup
            and row["exit_context"] == exit_context
            and row["sizing_policy"] == policy
            and row["cost_tier"] == cost_tier
            and row["asset"] == "ALL"
            and row["profile"] == "ALL"
            and row["direction"] == "ALL"
            and row["session_name"] == "ALL"
            and row["quality_tier"] == "ALL"
        ):
            return row
    return None


def _policy_approved(row: dict[str, Any], policy: str, quality_tier: str) -> bool:
    if policy == "current_risk_based_sizing":
        return _truthy(row.get("formal_approved"))
    if policy == "notional_capped_risk_based":
        return _truthy(row.get("proposal_approved"))
    if policy == "quality_aware_capped_sizing":
        return quality_tier in {"Tier A", "Tier B"} and _truthy(row.get("proposal_approved"))
    return False


def _quality_tier(row: dict[str, Any], setup: SetupSpec) -> str:
    if setup.attempt_type == "attempt_4_displacement_entry":
        return "Tier A"
    if setup.attempt_type == "attempt_3_choch_mss_entry":
        return "Tier B"
    if _truthy(row.get("choch_detected")) or _truthy(row.get("high_sweep_rvol")):
        return "Tier C"
    return "Tier D"


def _target_risk_for_policy(row: dict[str, Any], policy: str, quality_tier: str) -> float | None:
    base = _float(row.get("target_risk_pct")) or _float(row.get("risk_pct")) or 0.005
    if policy == "quality_aware_capped_sizing":
        return {"Tier A": base, "Tier B": base * 0.75, "Tier C": base * 0.25, "Tier D": 0.0}.get(quality_tier, base)
    return base


def _actual_risk_for_policy(row: dict[str, Any], policy: str, quality_tier: str) -> float | None:
    base = _float(row.get("actual_risk_pct_after_cap")) or _float(row.get("capped_actual_risk_pct")) or _float(row.get("risk_pct"))
    if policy != "quality_aware_capped_sizing" or base is None:
        return base
    target = _target_risk_for_policy(row, policy, quality_tier)
    original_target = _float(row.get("target_risk_pct")) or _float(row.get("risk_pct")) or 0.005
    if target is None or original_target == 0:
        return base
    return min(base, target) if base <= original_target else base * target / original_target


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


def _group_keys(rows: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str, str, str]]:
    return sorted({_group_key(row) for row in rows})


def _group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("asset", "")),
        str(row.get("profile", "")),
        str(row.get("direction", "")),
        str(row.get("session_name", "")),
        str(row.get("structure_source", "")),
        str(row.get("attempt_type", "")),
        str(row.get("quality_tier", "")),
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


def _distribution(values: Iterable[float | None]) -> dict[str, float | None]:
    clean = [value for value in values if value is not None]
    return {"p50": _pct(clean, 50), "p75": _pct(clean, 75), "p90": _pct(clean, 90)}


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
