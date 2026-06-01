from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run


PROPOSAL_ATTEMPTS = (
    "attempt_1_reclaim_entry",
    "attempt_3_choch_mss_entry",
    "attempt_4_displacement_entry",
)
DIAGNOSTIC_ONLY_ATTEMPTS = ("attempt_2_retest_entry", "attempt_5_fvg_ce_retest")
ATTEMPT_PRIORITY = (
    "attempt_4_displacement_entry",
    "attempt_3_choch_mss_entry",
    "attempt_1_reclaim_entry",
)
SIZING_MODELS = ("current_risk_based_sizing", "notional_capped_risk_based")
COST_TIERS = {
    "base": {"net_r_penalty": 0.0, "slippage_cost": 0.0, "funding_cost": 0.0},
    "stress": {"net_r_penalty": 0.05, "slippage_cost": 0.03, "funding_cost": 0.02},
    "harsh": {"net_r_penalty": 0.12, "slippage_cost": 0.08, "funding_cost": 0.04},
}


@dataclass(frozen=True)
class LRAttemptProposalResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    primary_attempt: str
    secondary_attempt: str
    baseline_attempt: str
    diagnostic_only_attempts: list[str]
    duplicate_event_count: int
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


def run_lr_attempt_proposal(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRAttemptProposalResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}
    event_rows, duplicate_event_count = _build_event_rows(filter_rows)
    candidate_rows = _build_candidate_rows(event_rows, filter_by_candidate)
    grouped_rows = _grouped_rows(sizing_rows, execution_by_candidate, filter_by_candidate)
    result = LRAttemptProposalResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        primary_attempt="attempt_4_displacement_entry",
        secondary_attempt="attempt_3_choch_mss_entry",
        baseline_attempt="attempt_1_reclaim_entry",
        diagnostic_only_attempts=list(DIAGNOSTIC_ONLY_ATTEMPTS),
        duplicate_event_count=duplicate_event_count,
        event_rows=event_rows,
        candidate_rows=candidate_rows,
        grouped_rows=grouped_rows,
        primary_decision=_primary_decision(grouped_rows, duplicate_event_count),
        secondary_findings=[
            "Session High/Low 后续值得 PR 11D 重点验证。",
            "structure_target_shadow / runner_displacement_shadow 后续值得 PR 11E 验证。",
            "Tier A sizing 后续值得 PR 11F 验证，但本 PR 不正式化。",
            "FVG/CE retest 目前只保留 diagnostic-only。",
            "CHOCH/MSS 适合作为 fallback，不适合作为主 setup。",
        ],
        deferred_items=[
            "PDH/PDL",
            "EQH/EQL",
            "Session H/L active source",
            "exit profile replacement",
            "quality-aware sizing formalization",
            "capped sizing formalization",
            "Stage 8 robustness",
            "cleanup / merge",
        ],
        next_pr_recommendation="PR 11D Structure Source Proposal"
        if duplicate_event_count == 0
        else "Stay in PR 11C to fix event lifecycle duplicates",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _build_event_rows(filter_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_event: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for row in filter_rows:
        event_id = _event_id(row)
        if event_id in by_event:
            duplicates += 1
            continue
        all_valid = _valid_attempts(row)
        selected = _selected_attempt(all_valid)
        suppressed = [attempt for attempt in all_valid if attempt != selected]
        by_event[event_id] = {
            "row_type": "diagnostic_only",
            "event_id": event_id,
            "source_candidate_id": row.get("candidate_id"),
            "strategy": "liquidity_reversal",
            "asset": row.get("asset"),
            "profile": row.get("profile"),
            "direction": row.get("direction"),
            "structure_level_id": _structure_level_id(row),
            "structure_source": row.get("structure_level_source"),
            "structure_level_type": row.get("structure_level_type"),
            "structure_level": row.get("structure_level"),
            "sweep_time": row.get("sweep_time"),
            "reclaim_time": row.get("reclaim_time"),
            "signal_time": row.get("signal_time"),
            "entry_time": row.get("entry_time"),
            "feature_cutoff_time": row.get("feature_cutoff_time") or row.get("signal_time"),
            "structure_confirmed_time": row.get("structure_confirmed_time") or row.get("structure_time"),
            "bar_confirmed": row.get("bar_confirmed", True),
            "no_lookahead_safe": row.get("no_lookahead_safe"),
            "event_state": _event_state(selected),
            "selected_attempt": selected,
            "all_valid_attempts": all_valid,
            "suppressed_attempts": suppressed,
            "suppression_reason": "higher_priority_attempt_selected" if suppressed else "",
            "max_attempts_per_event": 1,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
    return list(by_event.values()), duplicates


def _build_candidate_rows(
    event_rows: list[dict[str, Any]],
    filter_by_candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in event_rows:
        source = filter_by_candidate.get(str(event["source_candidate_id"]), {})
        for attempt in PROPOSAL_ATTEMPTS + DIAGNOSTIC_ONLY_ATTEMPTS:
            if attempt not in event["all_valid_attempts"]:
                continue
            rows.append(
                {
                    "row_type": "proposal_candidate" if attempt in PROPOSAL_ATTEMPTS else "diagnostic_only",
                    "event_id": event["event_id"],
                    "candidate_id": source.get("candidate_id"),
                    "attempt_name": attempt,
                    "selected_attempt": event["selected_attempt"],
                    "proposal_path": attempt in PROPOSAL_ATTEMPTS,
                    "diagnostic_only": attempt in DIAGNOSTIC_ONLY_ATTEMPTS,
                    "asset": event["asset"],
                    "profile": event["profile"],
                    "direction": event["direction"],
                    "structure_source": event["structure_source"],
                    "session_tag": _session_tag(source),
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
                    "displacement_body_atr": source.get("displacement_body_atr"),
                    "displacement_volume": source.get("sweep_rvol"),
                    "displacement_close_beyond_structure": source.get("displacement_close_beyond_structure"),
                    "choch_strength": source.get("choch_strength"),
                    "all_valid_attempts": event["all_valid_attempts"],
                    "suppressed_attempts": event["suppressed_attempts"],
                    "suppression_reason": event["suppression_reason"],
                    "proposal_only": True,
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
    for attempt in PROPOSAL_ATTEMPTS:
        for sizing_model in SIZING_MODELS:
            selected = [
                row
                for row in sizing_rows
                if row.get("sizing_model") == sizing_model and _row_matches_attempt(row, attempt)
            ]
            approved = [row for row in selected if _approved_for_model(row, sizing_model)]
            executions = [
                _execution_payload(row, execution_by_candidate, filter_by_candidate)
                for row in approved
                if str(row.get("candidate_id")) in execution_by_candidate
            ]
            for cost_tier in COST_TIERS:
                rows.append(
                    _summary_row(
                        attempt_name=attempt,
                        sizing_model=sizing_model,
                        cost_tier=cost_tier,
                        selected=selected,
                        approved=approved,
                        executions=executions,
                        asset="ALL",
                        profile="ALL",
                        direction="ALL",
                        structure_source="ALL",
                        session_tag="ALL",
                    )
                )
                for key in _group_keys(approved):
                    asset, profile, direction, structure_source, session_tag = key
                    group_selected = [row for row in selected if _row_group_key(row) == key]
                    group_approved = [row for row in approved if _row_group_key(row) == key]
                    group_executions = [
                        row for row in executions if _execution_group_key(row) == key
                    ]
                    rows.append(
                        _summary_row(
                            attempt_name=attempt,
                            sizing_model=sizing_model,
                            cost_tier=cost_tier,
                            selected=group_selected,
                            approved=group_approved,
                            executions=group_executions,
                            asset=asset,
                            profile=profile,
                            direction=direction,
                            structure_source=structure_source,
                            session_tag=session_tag,
                        )
                    )
    return rows


def _summary_row(
    *,
    attempt_name: str,
    sizing_model: str,
    cost_tier: str,
    selected: list[dict[str, Any]],
    approved: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    asset: str,
    profile: str,
    direction: str,
    structure_source: str,
    session_tag: str,
) -> dict[str, Any]:
    tier = COST_TIERS[cost_tier]
    net_values = [
        (_float(row.get("net_R")) or 0.0) - float(tier["net_r_penalty"])
        for row in executions
    ]
    mfe = [_float(row.get("mfe_R")) for row in executions]
    mae = [_float(row.get("mae_R")) for row in executions]
    exits = Counter(str(row.get("exit_reason", "")) for row in executions)
    event_ids = {_event_id(row) for row in selected}
    return {
        "attempt_name": attempt_name,
        "sizing_model": sizing_model,
        "cost_tier": cost_tier,
        "asset": asset,
        "profile": profile,
        "direction": direction,
        "structure_source": structure_source,
        "session_tag": session_tag,
        "events": len(event_ids),
        "attempts": len(selected),
        "candidates": len(selected),
        "formal_approved": sum(1 for row in selected if _truthy(row.get("formal_approved"))),
        "proposal_approved": sum(1 for row in selected if _truthy(row.get("proposal_approved"))),
        "closed_trades": len(executions),
        "expired_events": sum(1 for row in selected if row.get("event_state") == "expired"),
        "invalidated_events": sum(1 for row in selected if row.get("event_state") == "invalidated"),
        "duplicate_event_count": max(0, len(selected) - len(event_ids)),
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
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _write_outputs(result: LRAttemptProposalResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_attempt_proposal_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_attempt_proposal_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_attempt_event_rows.jsonl", result.event_rows)
    _write_jsonl(output_dir / "lr_attempt_candidate_rows.jsonl", result.candidate_rows)
    _write_jsonl(output_dir / "lr_attempt_grouped_rows.jsonl", result.grouped_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_attempt_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-attempt-proposal",
        notes="PR11C attempt proposal; proposal-only displacement-first FSM.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_attempt_proposal",
        window="10000w",
        source_command="research_pipeline.cli.research lr-attempt-proposal",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11C proposal-only attempt FSM replay.",
        tags=["PR11C", "proposal_only", "attempt_fsm"],
    )


def _report(result: LRAttemptProposalResult) -> str:
    all_rows = [
        row
        for row in result.grouped_rows
        if row["asset"] == "ALL"
        and row["profile"] == "ALL"
        and row["direction"] == "ALL"
        and row["structure_source"] == "ALL"
        and row["session_tag"] == "ALL"
    ]
    lines = [
        "# PR 11C Attempt Proposal - Displacement-first FSM",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- attempt_4_displacement_entry = proposal-only",
        "- attempt_3_choch_mss_entry = secondary proposal-only",
        "- attempt_2 / attempt_5 = diagnostic-only",
        "- capped sizing = proposal-only",
        "- structure source expansion belongs to PR 11D",
        "- exit profile expansion belongs to PR 11E",
        "- sizing proposal belongs to PR 11F",
        "- combined candidate belongs to PR 11G",
        "- robustness belongs to PR 11H",
        "- cleanup / merge belongs to PR 12",
        "",
        "## Attempt Smoke Replay",
    ]
    for row in all_rows:
        lines.append(
            f"- {row['attempt_name']} / {row['sizing_model']} / {row['cost_tier']}: "
            f"events={row['events']} closed={row['closed_trades']} net_R={row['net_R_avg']} "
            f"PF={row['profit_factor']} MFE>=0.5={row['MFE_ge_0_5_ratio']} "
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


def _decision_text(decision: str) -> str:
    return {
        "A": "attempt_4 displacement proposal 通过 smoke，按计划进入 PR 11D structure source proposal。",
        "B": "attempt_4 displacement 有效但频率仍低，按计划进入 PR 11D structure source proposal。",
        "C": "attempt_3 CHOCH/MSS 与 attempt_4 组合更优，按计划进入 PR 11D structure source proposal。",
        "D": "attempt proposal 在 stress/harsh 下退化，需要留在 PR 11C 修复 attempt / cost issue。",
        "E": "FSM 或数据不足，需要留在 PR 11C 修 event lifecycle。",
        "F": "不如 LR v1 smoke baseline，放弃 attempt proposal，但仍按计划进入 PR 11D 做 structure diagnostic/proposal。",
    }[decision]


def _primary_decision(rows: list[dict[str, Any]], duplicate_event_count: int) -> str:
    if duplicate_event_count:
        return "E"
    displacement_base = _all_row(rows, "attempt_4_displacement_entry", "current_risk_based_sizing", "base")
    displacement_harsh = _all_row(rows, "attempt_4_displacement_entry", "current_risk_based_sizing", "harsh")
    if not displacement_base or displacement_base["closed_trades"] < 40:
        return "E"
    if (displacement_harsh["net_R_avg"] or 0.0) <= 0:
        return "D"
    if displacement_base["closed_trades"] < 200:
        return "B"
    return "A"


def _all_row(
    rows: list[dict[str, Any]], attempt_name: str, sizing_model: str, cost_tier: str
) -> dict[str, Any] | None:
    for row in rows:
        if (
            row["attempt_name"] == attempt_name
            and row["sizing_model"] == sizing_model
            and row["cost_tier"] == cost_tier
            and row["asset"] == "ALL"
            and row["profile"] == "ALL"
            and row["direction"] == "ALL"
        ):
            return row
    return None


def _valid_attempts(row: dict[str, Any]) -> list[str]:
    attempts = ["attempt_1_reclaim_entry"]
    if _truthy(row.get("pullback_retest_after_reclaim")):
        attempts.append("attempt_2_retest_entry")
    if _has_choch(row):
        attempts.append("attempt_3_choch_mss_entry")
    if _has_displacement(row):
        attempts.append("attempt_4_displacement_entry")
    if _truthy(row.get("fvg_exists")) or _truthy(row.get("fvg_retest_hit")):
        attempts.append("attempt_5_fvg_ce_retest")
    return attempts


def _selected_attempt(all_valid: list[str]) -> str:
    for attempt in ATTEMPT_PRIORITY:
        if attempt in all_valid:
            return attempt
    return "attempt_1_reclaim_entry"


def _event_state(selected_attempt: str) -> str:
    return {
        "attempt_4_displacement_entry": "attempt_4_displacement_signaled",
        "attempt_3_choch_mss_entry": "attempt_3_choch_mss_signaled",
        "attempt_1_reclaim_entry": "attempt_1_reclaim_signaled",
    }.get(selected_attempt, "reclaimed")


def _row_matches_attempt(row: dict[str, Any], attempt: str) -> bool:
    if attempt == "attempt_1_reclaim_entry":
        return True
    if attempt == "attempt_3_choch_mss_entry":
        return _has_choch(row)
    if attempt == "attempt_4_displacement_entry":
        return _has_displacement(row)
    return False


def _has_choch(row: dict[str, Any]) -> bool:
    return _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true"


def _has_displacement(row: dict[str, Any]) -> bool:
    return _truthy(row.get("displacement_after_reclaim")) and _truthy(
        row.get("displacement_direction_valid")
    )


def _event_id(row: dict[str, Any]) -> str:
    seed = {
        "strategy": "liquidity_reversal",
        "asset": row.get("asset"),
        "profile": row.get("profile"),
        "direction": row.get("direction"),
        "structure_level_id": _structure_level_id(row),
        "sweep_time": row.get("sweep_time"),
    }
    return hashlib.sha256(json.dumps(seed, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


def _structure_level_id(row: dict[str, Any]) -> str:
    return "|".join(
        str(row.get(key, ""))
        for key in (
            "structure_level_source",
            "structure_level_type",
            "structure_level",
            "structure_time",
        )
    )


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


def _approved_for_model(row: dict[str, Any], model: str) -> bool:
    if model == "current_risk_based_sizing":
        return _truthy(row.get("formal_approved"))
    return _truthy(row.get("proposal_approved"))


def _group_keys(rows: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    return sorted({_row_group_key(row) for row in rows})


def _row_group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("asset", "")),
        str(row.get("profile", "")),
        str(row.get("direction", "")),
        str(row.get("structure_level_source", "")),
        _session_tag(row),
    )


def _execution_group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("asset", "")),
        str(row.get("profile", "")),
        str(row.get("direction", "")),
        str(row.get("structure_level_source", "")),
        _session_tag(row),
    )


def _session_tag(row: dict[str, Any]) -> str:
    if _truthy(row.get("london_ny_overlap")):
        return "london_ny_overlap"
    if _truthy(row.get("london_open_window")):
        return "london_open"
    if _truthy(row.get("ny_open_window")):
        return "ny_open"
    if _truthy(row.get("funding_settlement_plus_2h_window")):
        return "funding_plus_2h"
    return "other"


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
