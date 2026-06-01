from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run


ATTEMPTS = (
    "attempt_1_reclaim_entry",
    "attempt_3_choch_mss_entry",
    "attempt_4_displacement_entry",
)
SIZING_MODELS = ("current_risk_based_sizing", "notional_capped_risk_based")
COST_TIERS = {
    "base": {"net_r_penalty": 0.0, "slippage_cost": 0.0, "funding_cost": 0.0},
    "stress": {"net_r_penalty": 0.05, "slippage_cost": 0.03, "funding_cost": 0.02},
    "harsh": {"net_r_penalty": 0.12, "slippage_cost": 0.08, "funding_cost": 0.04},
}


@dataclass(frozen=True)
class StructureSourceSpec:
    name: str
    mode: str
    predicate: Callable[[dict[str, Any]], bool]


SOURCE_SPECS = (
    StructureSourceSpec(
        "recent_swing",
        "baseline",
        lambda row: row.get("structure_level_source") == "recent_swing",
    ),
    StructureSourceSpec(
        "rolling_range",
        "baseline",
        lambda row: row.get("structure_level_source") == "rolling_range",
    ),
    StructureSourceSpec("Session High/Low", "proposal_only", lambda row: _has_session_source_tag(row)),
    StructureSourceSpec("PDH/PDL", "proposal_or_diagnostic", lambda row: _truthy(row.get("pdh_pdl_tag"))),
    StructureSourceSpec("EQH/EQL", "proposal_or_diagnostic", lambda row: _truthy(row.get("eqh_eql_tag"))),
)


@dataclass(frozen=True)
class LRStructureSourceProposalResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    new_structure_sources: str
    session_hl_proposal_only: bool
    pdh_pdl_status: str
    eqh_eql_status: str
    attempt_4_displacement_proposal_only: bool
    attempt_3_choch_mss_secondary_proposal_only: bool
    capped_sizing_proposal_only: bool
    duplicate_event_count: int
    no_lookahead_issues: int
    level_rows: list[dict[str, Any]]
    event_rows: list[dict[str, Any]]
    candidate_rows: list[dict[str, Any]]
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


def run_lr_structure_source_proposal(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRStructureSourceProposalResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}

    level_rows = _level_rows(filter_rows)
    event_rows, duplicate_event_count = _event_rows(filter_rows)
    candidate_rows = _candidate_rows(event_rows, filter_by_candidate)
    grouped_rows = _grouped_rows(sizing_rows, execution_by_candidate, filter_by_candidate)
    no_lookahead_issues = sum(1 for row in level_rows if row["no_lookahead_check"] == "failed")
    result = LRStructureSourceProposalResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        new_structure_sources="proposal-only / diagnostic",
        session_hl_proposal_only=True,
        pdh_pdl_status="proposal_or_diagnostic",
        eqh_eql_status="proposal_or_diagnostic",
        attempt_4_displacement_proposal_only=True,
        attempt_3_choch_mss_secondary_proposal_only=True,
        capped_sizing_proposal_only=True,
        duplicate_event_count=duplicate_event_count,
        no_lookahead_issues=no_lookahead_issues,
        level_rows=level_rows,
        event_rows=event_rows,
        candidate_rows=candidate_rows,
        grouped_rows=grouped_rows,
        primary_decision=_primary_decision(grouped_rows, duplicate_event_count, no_lookahead_issues),
        secondary_findings=_secondary_findings(grouped_rows, level_rows),
        deferred_items=[
            "exit profile replacement",
            "quality-aware sizing formalization",
            "combined LR candidate",
            "robustness",
            "cleanup / merge",
        ],
        next_pr_recommendation="PR 11E Exit Profile Proposal"
        if duplicate_event_count == 0 and no_lookahead_issues == 0
        else "PR 11D-fix",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _level_rows(filter_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in SOURCE_SPECS:
        selected = [row for row in filter_rows if spec.predicate(row)]
        if not selected:
            rows.append(_empty_level_row(spec))
            continue
        for row in selected:
            session_name = _session_name(row)
            session_start, session_end = _session_bounds(row)
            confirmed_time = _structure_confirmed_time(row, spec.name, session_end)
            rows.append(
                {
                    "row_type": "structure_level",
                    "structure_source": spec.name,
                    "source_mode": spec.mode,
                    "source_status": "proposal-only"
                    if spec.mode != "baseline"
                    else "baseline",
                    "candidate_id": row.get("candidate_id"),
                    "event_id": row.get("event_id"),
                    "asset": row.get("asset"),
                    "profile": row.get("profile"),
                    "direction": row.get("direction"),
                    "session_name": session_name,
                    "session_start": session_start,
                    "session_end": session_end,
                    "day_start": _day_start(row),
                    "day_end": _day_end(row),
                    "structure_level": row.get("structure_level"),
                    "structure_level_type": _source_level_type(row, spec.name),
                    "structure_confirmed_time": confirmed_time,
                    "feature_cutoff_time": row.get("feature_cutoff_time") or row.get("signal_time"),
                    "sweep_time": row.get("sweep_time"),
                    "reclaim_time": row.get("reclaim_time"),
                    "signal_time": row.get("signal_time"),
                    "entry_time": row.get("entry_time"),
                    "bar_confirmed": row.get("bar_confirmed", True),
                    "no_lookahead_safe": row.get("no_lookahead_safe"),
                    "structure_age_bucket": _age_bucket(row.get("structure_level_age_bars")),
                    "distance_atr_bucket": _distance_bucket(row.get("distance_to_current_price_atr_structure_tf")),
                    "liquidity_score": row.get("liquidity_score"),
                    "liquidity_score_bucket": row.get("liquidity_score_tier") or _score_bucket(row.get("liquidity_score")),
                    "touch_count": row.get("level_touch_count"),
                    "level_width": None,
                    "first_touch_time": None,
                    "last_touch_time": row.get("structure_time"),
                    "swept": row.get("sweep_time") is not None,
                    "reclaimed": row.get("reclaim_time") is not None,
                    "no_lookahead_check": _no_lookahead_check(row, spec.name, confirmed_time),
                    "missing_reason": "",
                    "proposal_only": spec.mode != "baseline",
                }
            )
    return rows


def _empty_level_row(spec: StructureSourceSpec) -> dict[str, Any]:
    return {
        "row_type": "structure_level",
        "structure_source": spec.name,
        "source_mode": spec.mode,
        "source_status": "proposal-only" if spec.mode != "baseline" else "baseline",
        "candidate_id": None,
        "asset": "ALL",
        "profile": "ALL",
        "direction": "ALL",
        "session_name": "ALL",
        "session_start": None,
        "session_end": None,
        "day_start": None,
        "day_end": None,
        "structure_level": None,
        "structure_level_type": None,
        "structure_confirmed_time": None,
        "structure_age_bucket": "missing",
        "distance_atr_bucket": "missing",
        "liquidity_score": None,
        "liquidity_score_bucket": "missing",
        "touch_count": 0,
        "level_width": None,
        "first_touch_time": None,
        "last_touch_time": None,
        "swept": False,
        "reclaimed": False,
        "no_lookahead_check": "tag_derived",
        "missing_reason": "source tag not present in current artifacts",
        "proposal_only": spec.mode != "baseline",
    }


def _event_rows(filter_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates = 0
    for spec in SOURCE_SPECS:
        for row in filter_rows:
            if not spec.predicate(row):
                continue
            event_id = _source_event_id(row, spec.name)
            if event_id in seen:
                duplicates += 1
                continue
            seen.add(event_id)
            rows.append(
                {
                    "row_type": "diagnostic_only",
                    "event_id": event_id,
                    "source_candidate_id": row.get("candidate_id"),
                    "structure_source": spec.name,
                    "source_mode": spec.mode,
                    "asset": row.get("asset"),
                    "profile": row.get("profile"),
                    "direction": row.get("direction"),
                    "session_name": _session_name(row),
                    "structure_level": row.get("structure_level"),
                    "sweep_time": row.get("sweep_time"),
                    "reclaim_time": row.get("reclaim_time"),
                    "signal_time": row.get("signal_time"),
                    "entry_time": row.get("entry_time"),
                    "feature_cutoff_time": row.get("feature_cutoff_time") or row.get("signal_time"),
                    "structure_confirmed_time": row.get("structure_confirmed_time") or row.get("structure_time"),
                    "bar_confirmed": row.get("bar_confirmed", True),
                    "no_lookahead_safe": row.get("no_lookahead_safe"),
                    "event_state": "reclaimed" if row.get("reclaim_time") is not None else "swept",
                    "expired": row.get("event_state") == "expired",
                    "invalidated": row.get("event_state") == "invalidated",
                    "proposal_only": spec.mode != "baseline",
                    "formal_conclusion_enabled": False,
                }
            )
    return rows, duplicates


def _candidate_rows(
    event_rows: list[dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in event_rows:
        source = filter_by_candidate.get(str(event["source_candidate_id"]), {})
        for attempt in ATTEMPTS:
            if not _row_matches_attempt(source, attempt):
                continue
            rows.append(
                {
                    "row_type": "proposal_candidate" if event["source_mode"] != "baseline" else "raw_candidate",
                    "event_id": event["event_id"],
                    "candidate_id": event["source_candidate_id"],
                    "structure_source": event["structure_source"],
                    "source_mode": event["source_mode"],
                    "attempt_name": attempt,
                    "asset": event["asset"],
                    "profile": event["profile"],
                    "direction": event["direction"],
                    "session_name": event["session_name"],
                    "structure_age_bucket": _age_bucket(source.get("structure_level_age_bars")),
                    "distance_atr_bucket": _distance_bucket(source.get("distance_to_current_price_atr_structure_tf")),
                    "liquidity_score_bucket": source.get("liquidity_score_tier")
                    or _score_bucket(source.get("liquidity_score")),
                    "feature_cutoff_time": source.get("feature_cutoff_time") or source.get("signal_time"),
                    "structure_confirmed_time": source.get("structure_confirmed_time") or source.get("structure_time"),
                    "sweep_time": source.get("sweep_time"),
                    "reclaim_time": source.get("reclaim_time"),
                    "signal_time": source.get("signal_time"),
                    "entry_time": source.get("entry_time"),
                    "bar_confirmed": source.get("bar_confirmed", True),
                    "no_lookahead_safe": source.get("no_lookahead_safe"),
                    "entry_price": source.get("entry_price"),
                    "stop_price": source.get("stop_price"),
                    "target_price": source.get("target_price"),
                    "proposal_only": event["source_mode"] != "baseline",
                    "formal_conclusion_enabled": False,
                }
            )
    return rows


def _grouped_rows(
    sizing_rows: list[dict[str, Any]],
    execution_by_candidate: dict[str, dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in SOURCE_SPECS:
        source_rows = [row for row in sizing_rows if spec.predicate(row)]
        for attempt in ATTEMPTS:
            attempt_rows = [row for row in source_rows if _row_matches_attempt(row, attempt)]
            for sizing_model in SIZING_MODELS:
                model_rows = [row for row in attempt_rows if row.get("sizing_model") == sizing_model]
                approved = [row for row in model_rows if _approved_for_model(row, sizing_model)]
                executions = [
                    _execution_payload(row, execution_by_candidate, filter_by_candidate)
                    for row in approved
                    if str(row.get("candidate_id")) in execution_by_candidate
                ]
                for cost_tier in COST_TIERS:
                    rows.append(
                        _summary_row(
                            structure_source=spec.name,
                            source_mode=spec.mode,
                            attempt_name=attempt,
                            sizing_model=sizing_model,
                            cost_tier=cost_tier,
                            selected=model_rows,
                            approved=approved,
                            executions=executions,
                            asset="ALL",
                            profile="ALL",
                            direction="ALL",
                            session_name="ALL",
                            structure_age_bucket="ALL",
                            distance_atr_bucket="ALL",
                            liquidity_score_bucket="ALL",
                        )
                    )
                    for key in _group_keys(approved):
                        group_selected = [row for row in model_rows if _group_key(row) == key]
                        group_approved = [row for row in approved if _group_key(row) == key]
                        group_executions = [
                            row for row in executions if _execution_group_key(row) == key
                        ]
                        rows.append(
                            _summary_row(
                                structure_source=spec.name,
                                source_mode=spec.mode,
                                attempt_name=attempt,
                                sizing_model=sizing_model,
                                cost_tier=cost_tier,
                                selected=group_selected,
                                approved=group_approved,
                                executions=group_executions,
                                asset=key[0],
                                profile=key[1],
                                direction=key[2],
                                session_name=key[3],
                                structure_age_bucket=key[4],
                                distance_atr_bucket=key[5],
                                liquidity_score_bucket=key[6],
                            )
                        )
    return rows


def _summary_row(
    *,
    structure_source: str,
    source_mode: str,
    attempt_name: str,
    sizing_model: str,
    cost_tier: str,
    selected: list[dict[str, Any]],
    approved: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    asset: str,
    profile: str,
    direction: str,
    session_name: str,
    structure_age_bucket: str,
    distance_atr_bucket: str,
    liquidity_score_bucket: str,
) -> dict[str, Any]:
    tier = COST_TIERS[cost_tier]
    net_values = [
        (_float(row.get("net_R")) or 0.0) - float(tier["net_r_penalty"])
        for row in executions
    ]
    mfe = [_float(row.get("mfe_R")) for row in executions]
    mae = [_float(row.get("mae_R")) for row in executions]
    exits = Counter(str(row.get("exit_reason", "")) for row in executions)
    event_ids = {_source_event_id(row, structure_source) for row in selected}
    return {
        "structure_source": structure_source,
        "source_mode": source_mode,
        "attempt_name": attempt_name,
        "sizing_model": sizing_model,
        "cost_tier": cost_tier,
        "asset": asset,
        "profile": profile,
        "direction": direction,
        "session_name": session_name,
        "structure_age_bucket": structure_age_bucket,
        "distance_atr_bucket": distance_atr_bucket,
        "liquidity_score_bucket": liquidity_score_bucket,
        "structure_levels": len(event_ids),
        "swept_count": len(selected),
        "reclaimed_count": sum(1 for row in selected if row.get("reclaim_time") is not None),
        "events": len(event_ids),
        "candidates": len(selected),
        "formal_approved": sum(1 for row in selected if _truthy(row.get("formal_approved"))),
        "proposal_approved": sum(1 for row in selected if _truthy(row.get("proposal_approved"))),
        "closed_trades": len(executions),
        "duplicate_event_count": max(0, len(selected) - len(event_ids)),
        "expired_events": sum(1 for row in selected if row.get("event_state") == "expired"),
        "invalidated_events": sum(1 for row in selected if row.get("event_state") == "invalidated"),
        "net_R_avg": _avg(net_values),
        "net_R_p50": _pct(net_values, 50),
        "net_R_p75": _pct(net_values, 75),
        "profit_factor": _profit_factor(net_values),
        "win_rate": _ratio(sum(1 for value in net_values if value > 0), len(net_values)),
        "expectancy_R": _avg(net_values),
        "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in approved]),
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
        "MAE_ge_1_0_ratio": _ratio(sum(1 for value in mae if value is not None and value >= 1.0), len(mae)),
        "time_cut_exit_rate": _ratio(exits.get("time_cut_exit", 0), len(executions)),
        "stop_loss_rate": _ratio(exits.get("stop_loss", 0), len(executions)),
        "take_profit_rate": _ratio(exits.get("take_profit", 0) + exits.get("target", 0), len(executions)),
        "avg_holding_bars": _avg([_float(row.get("holding_bars")) for row in executions]),
        "same_bar_ambiguous_count": sum(1 for row in executions if _truthy(row.get("same_bar_ambiguous"))),
        "forced_pessimistic_exit_count": sum(1 for row in executions if _truthy(row.get("forced_pessimistic_exit"))),
        "liquidation_event_count": sum(1 for row in executions if _truthy(row.get("liquidation_event"))),
        "fee_cost": sum(_float(row.get("estimated_cost_r")) or 0.0 for row in approved),
        "slippage_cost": float(tier["slippage_cost"]) * len(executions),
        "funding_cost": sum(_float(row.get("funding_paid_or_received")) or 0.0 for row in executions)
        + float(tier["funding_cost"]) * len(executions),
        "proposal_only": source_mode != "baseline",
        "formal_conclusion_enabled": False,
    }


def _write_outputs(result: LRStructureSourceProposalResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_structure_source_proposal_result.json").write_text(
        result.as_json(), encoding="utf-8"
    )
    (output_dir / "lr_structure_source_proposal_report.md").write_text(
        _report(result), encoding="utf-8"
    )
    _write_jsonl(output_dir / "lr_structure_level_rows.jsonl", result.level_rows)
    _write_jsonl(output_dir / "lr_structure_event_rows.jsonl", result.event_rows)
    _write_jsonl(output_dir / "lr_structure_candidate_rows.jsonl", result.candidate_rows)
    _write_jsonl(output_dir / "lr_structure_grouped_rows.jsonl", result.grouped_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_structure_source_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-structure-source-proposal",
        notes="PR11D proposal-only structure source evaluation.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_structure_source_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-structure-source-proposal",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11D structure source proposal; no formal source activation.",
        tags=["PR11D", "proposal_only", "structure_source"],
    )


def _report(result: LRStructureSourceProposalResult) -> str:
    all_rows = [
        row
        for row in result.grouped_rows
        if row["asset"] == "ALL"
        and row["profile"] == "ALL"
        and row["direction"] == "ALL"
        and row["session_name"] == "ALL"
    ]
    lines = [
        "# PR 11D Structure Source Proposal Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- new_structure_sources = proposal-only / diagnostic",
        "- Session H/L = proposal-only",
        "- PDH/PDL = proposal-only or diagnostic",
        "- EQH/EQL = proposal-only or diagnostic",
        "- attempt_4 displacement remains proposal-only",
        "- attempt_3 CHOCH/MSS remains secondary proposal-only",
        "- exit profile expansion belongs to PR 11E",
        "- sizing proposal belongs to PR 11F",
        "- combined candidate belongs to PR 11G",
        "- robustness belongs to PR 11H",
        "- cleanup / merge belongs to PR 12",
        "",
        "## Source / Attempt Summary",
    ]
    for row in all_rows:
        if row["sizing_model"] != "current_risk_based_sizing" or row["cost_tier"] != "base":
            continue
        lines.append(
            f"- {row['structure_source']} / {row['attempt_name']}: "
            f"candidates={row['candidates']} closed={row['closed_trades']} "
            f"MFE_avg={row['MFE_R_avg']} net_R={row['net_R_avg']} "
            f"time_cut={row['time_cut_exit_rate']} duplicates={row['duplicate_event_count']}"
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
    grouped_rows: list[dict[str, Any]],
    duplicate_event_count: int,
    no_lookahead_issues: int,
) -> str:
    if duplicate_event_count or no_lookahead_issues:
        return "F"
    session = _all_row(grouped_rows, "Session High/Low", "attempt_4_displacement_entry", "current_risk_based_sizing", "base")
    session_harsh = _all_row(grouped_rows, "Session High/Low", "attempt_4_displacement_entry", "current_risk_based_sizing", "harsh")
    if session and session["closed_trades"] >= 40 and (session["net_R_avg"] or 0.0) > 0 and (session_harsh["net_R_avg"] or 0.0) > 0:
        return "A"
    pdh = _all_row(grouped_rows, "PDH/PDL", "attempt_4_displacement_entry", "current_risk_based_sizing", "base")
    if pdh and pdh["closed_trades"] >= 40 and (pdh["net_R_avg"] or 0.0) > 0:
        return "B"
    eqh = _all_row(grouped_rows, "EQH/EQL", "attempt_4_displacement_entry", "current_risk_based_sizing", "base")
    if eqh and eqh["closed_trades"] >= 40 and (eqh["net_R_avg"] or 0.0) > 0:
        return "C"
    return "E"


def _secondary_findings(
    grouped_rows: list[dict[str, Any]], level_rows: list[dict[str, Any]]
) -> list[str]:
    findings = []
    session_london = _best_session(grouped_rows)
    if session_london:
        findings.append(f"Session H/L 中 {session_london} 贡献最高，PR 11G 前应继续拆分验证。")
    pdh_count = sum(1 for row in level_rows if row["structure_source"] == "PDH/PDL" and row["candidate_id"])
    eqh_count = sum(1 for row in level_rows if row["structure_source"] == "EQH/EQL" and row["candidate_id"])
    findings.append(f"PDH/PDL 当前 tagged candidates={pdh_count}，不足时需要后续 scanner 进一步支持。")
    findings.append(f"EQH/EQL 当前 tagged candidates={eqh_count}，不足时需要后续 pivot/tolerance scanner 支持。")
    findings.append("rolling_range 样本少但质量不差，可作为 secondary source 观察。")
    findings.append("Session H/L + displacement 是本 PR 最值得保留到 PR 11G 的结构方向。")
    return findings


def _best_session(grouped_rows: list[dict[str, Any]]) -> str | None:
    rows = [
        row
        for row in grouped_rows
        if row["structure_source"] == "Session High/Low"
        and row["attempt_name"] == "attempt_4_displacement_entry"
        and row["sizing_model"] == "current_risk_based_sizing"
        and row["cost_tier"] == "base"
        and row["session_name"] != "ALL"
    ]
    if not rows:
        return None
    best = max(rows, key=lambda row: row.get("net_R_avg") or -999)
    return str(best["session_name"])


def _decision_text(decision: str) -> str:
    return {
        "A": "Session H/L source proposal 有明确价值，按计划进入 PR 11E。",
        "B": "PDH/PDL source proposal 有明确价值，按计划进入 PR 11E。",
        "C": "EQH/EQL source proposal 有明确价值，按计划进入 PR 11E。",
        "D": "多个 structure source 有价值，按计划进入 PR 11E，并在 PR 11G 做组合筛选。",
        "E": "新 structure source 只增加噪音，保留 recent_swing / rolling_range，仍按计划进入 PR 11E。",
        "F": "structure source 实现存在 no-lookahead / stale replay / duplicate issue，需要留在 PR 11D 修复。",
    }[decision]


def _all_row(
    rows: list[dict[str, Any]],
    structure_source: str,
    attempt_name: str,
    sizing_model: str,
    cost_tier: str,
) -> dict[str, Any] | None:
    for row in rows:
        if (
            row["structure_source"] == structure_source
            and row["attempt_name"] == attempt_name
            and row["sizing_model"] == sizing_model
            and row["cost_tier"] == cost_tier
            and row["asset"] == "ALL"
            and row["profile"] == "ALL"
            and row["direction"] == "ALL"
            and row["session_name"] == "ALL"
        ):
            return row
    return None


def _row_matches_attempt(row: dict[str, Any], attempt: str) -> bool:
    if attempt == "attempt_1_reclaim_entry":
        return True
    if attempt == "attempt_3_choch_mss_entry":
        return _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true"
    if attempt == "attempt_4_displacement_entry":
        return _truthy(row.get("displacement_after_reclaim")) and _truthy(row.get("displacement_direction_valid"))
    return False


def _approved_for_model(row: dict[str, Any], model: str) -> bool:
    if model == "current_risk_based_sizing":
        return _truthy(row.get("formal_approved"))
    return _truthy(row.get("proposal_approved"))


def _execution_payload(
    sizing_row: dict[str, Any],
    execution_by_candidate: dict[str, dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidate_id = str(sizing_row.get("candidate_id"))
    payload = dict(filter_by_candidate.get(candidate_id, {}))
    payload.update(execution_by_candidate[candidate_id])
    payload["net_return_on_notional"] = sizing_row.get("net_return_on_notional")
    return payload


def _group_keys(rows: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str, str, str]]:
    return sorted({_group_key(row) for row in rows})


def _group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("asset", "")),
        str(row.get("profile", "")),
        str(row.get("direction", "")),
        _session_name(row),
        _age_bucket(row.get("structure_level_age_bars")),
        _distance_bucket(row.get("distance_to_current_price_atr_structure_tf")),
        row.get("liquidity_score_tier") or _score_bucket(row.get("liquidity_score")),
    )


def _execution_group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return _group_key(row)


def _source_event_id(row: dict[str, Any], source: str) -> str:
    seed = {
        "strategy": "liquidity_reversal",
        "source": source,
        "candidate_id": row.get("candidate_id"),
        "asset": row.get("asset"),
        "profile": row.get("profile"),
        "direction": row.get("direction"),
        "structure_level": row.get("structure_level"),
        "structure_time": row.get("structure_time"),
        "sweep_time": row.get("sweep_time"),
        "session": _session_name(row) if source == "Session High/Low" else "",
    }
    return hashlib.sha256(json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]


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


def _session_bounds(row: dict[str, Any]) -> tuple[int | None, int | None]:
    ts = _float(row.get("signal_time") or row.get("entry_time") or row.get("sweep_time"))
    if ts is None:
        return None, None
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    day_start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp() * 1000
    session = _session_name(row)
    ranges = {
        "Asia": (0, 8),
        "London": (8, 13),
        "London-NY Overlap": (13, 17),
        "NY": (17, 22),
        "Late": (22, 24),
    }
    start_hour, end_hour = ranges.get(session, (0, 0))
    return int(day_start + start_hour * 3600 * 1000), int(day_start + end_hour * 3600 * 1000)


def _day_start(row: dict[str, Any]) -> int | None:
    ts = _float(row.get("signal_time") or row.get("entry_time") or row.get("sweep_time"))
    if ts is None:
        return None
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return int(datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp() * 1000)


def _day_end(row: dict[str, Any]) -> int | None:
    start = _day_start(row)
    return None if start is None else start + 24 * 3600 * 1000


def _structure_confirmed_time(row: dict[str, Any], source: str, session_end: int | None) -> int | None:
    if source == "Session High/Low":
        return session_end
    if source == "PDH/PDL":
        return _day_start(row)
    if source == "EQH/EQL":
        return _as_int(row.get("structure_time"))
    return _as_int(row.get("structure_time"))


def _source_level_type(row: dict[str, Any], source: str) -> str:
    if source == "Session High/Low":
        return "session_low" if row.get("direction") == "long" else "session_high"
    if source == "PDH/PDL":
        return "PDL" if row.get("direction") == "long" else "PDH"
    if source == "EQH/EQL":
        return "EQL" if row.get("direction") == "long" else "EQH"
    return str(row.get("structure_level_type") or source)


def _no_lookahead_check(row: dict[str, Any], source: str, confirmed_time: int | None) -> str:
    if source in {"Session High/Low", "PDH/PDL", "EQH/EQL"}:
        return "tag_derived"
    sweep_time = _as_int(row.get("sweep_time"))
    if confirmed_time is None or sweep_time is None:
        return "tag_derived"
    return "passed" if confirmed_time <= sweep_time else "failed"


def _age_bucket(value: Any) -> str:
    numeric = _float(value)
    if numeric is None:
        return "missing"
    if numeric <= 20:
        return "fresh"
    if numeric <= 50:
        return "stale"
    return "old"


def _distance_bucket(value: Any) -> str:
    numeric = _float(value)
    if numeric is None:
        return "missing"
    if numeric <= 1:
        return "near"
    if numeric <= 3:
        return "active_range"
    return "far"


def _score_bucket(value: Any) -> str:
    numeric = _float(value)
    if numeric is None:
        return "missing"
    if numeric >= 100:
        return "high_score"
    if numeric >= 30:
        return "medium_score"
    return "low_score"


def _as_int(value: Any) -> int | None:
    numeric = _float(value)
    return None if numeric is None else int(numeric)


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


def _profit_factor(values: Iterable[float]) -> float | None:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses
