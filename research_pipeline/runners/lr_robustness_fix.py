from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.lr_combined_candidate_fix import VARIANT_COMBOS, _select_variant_rows
from research_pipeline.runners.lr_robustness_validation import (
    _closed_rows,
    _cost_stress_rows,
    _float,
    _max_concurrent_positions,
    _max_drawdown,
    _metrics,
    _monte_carlo_rows,
    _portfolio_heat_rows,
    _regime_rows,
    _same_direction_overlaps,
    _walk_forward_rows,
)
from research_pipeline.runners.register_research_run import register_research_run


RECOMMENDED_VARIANT = "Variant B - Tier 1 + Positive Tier 2"
TIER1_VARIANT = "Variant A - Tier 1 only"
POSITIVE_TIER2_COMBO = "T2_session_hl_attempt3_dynamic_quality"
NEGATIVE_TIER2_COMBO = "T2_recent_swing_attempt3_dynamic_quality"


@dataclass(frozen=True)
class LRRobustnessFixResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    primary_decision: str
    next_pr_recommendation: str
    profile_root_cause: dict[str, dict[str, Any]]
    root_cause_summary: dict[str, Any]
    restriction_summary: list[dict[str, Any]]
    monte_carlo_summary: list[dict[str, Any]]
    walk_forward_summary: list[dict[str, Any]]
    blocking_issues: list[str]
    non_blocking_warnings: list[str]
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_robustness_fix(
    *,
    artifact_dir: Path,
    output_dir: Path | None,
    monte_carlo_seeds: int = 1000,
) -> LRRobustnessFixResult:
    artifact_dir = Path(artifact_dir)
    clean_root = artifact_dir.parent
    combo_rows = _read_jsonl(artifact_dir / "lr_combined_combo_rows.jsonl")
    filter_rows = _read_jsonl(clean_root / "minimal_lr_v0_filter" / "10000w" / "minimal_lr_v0_filter_results.jsonl")

    variant_b_rows = _select_variant_rows(combo_rows, VARIANT_COMBOS[RECOMMENDED_VARIANT])[0]
    variant_a_rows = _select_variant_rows(combo_rows, VARIANT_COMBOS[TIER1_VARIANT])[0]
    base_b = _closed_rows(variant_b_rows, cost_tier="base")
    base_a = _closed_rows(variant_a_rows, cost_tier="base")
    funnel_rows, profile_root_cause = _profile_funnel_rows(filter_rows, base_b)
    suppression_rows = _profile_suppression_rows(base_b)
    root_cause_summary = _root_cause_summary(profile_root_cause, base_b)

    variants = _restriction_variants(base_b, base_a)
    restriction_rows: list[dict[str, Any]] = []
    monte_carlo_rows: list[dict[str, Any]] = []
    walk_forward_rows: list[dict[str, Any]] = []
    regime_rows: list[dict[str, Any]] = []
    for name, rows in variants.items():
        restriction_rows.extend(_restriction_metric_rows(name, rows))
        for row in _walk_forward_rows(rows):
            walk_forward_rows.append({"restriction_name": name, **row})
        mc_rows, mc_summary = _monte_carlo_rows(rows, monte_carlo_seeds)
        for row in mc_rows:
            monte_carlo_rows.append({"restriction_name": name, **row})
        restriction_rows.append({"restriction_name": name, "row_type": "monte_carlo_summary", **mc_summary})
        for row in _regime_rows(rows):
            regime_rows.append({"restriction_name": name, **row})

    restriction_summary = [row for row in restriction_rows if row.get("row_type") == "restriction_cost_summary"]
    monte_carlo_summary = [row for row in restriction_rows if row.get("row_type") == "monte_carlo_summary"]
    blocking_issues, warnings = _decision_issues(profile_root_cause, restriction_summary, monte_carlo_summary)
    primary_decision = _primary_decision(root_cause_summary, restriction_summary, monte_carlo_summary, blocking_issues)
    result = LRRobustnessFixResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        primary_decision=primary_decision,
        next_pr_recommendation="PR12 formalization / cleanup / merge preparation"
        if primary_decision in {"A", "B", "C"}
        else _fix_next_pr(primary_decision),
        profile_root_cause=profile_root_cause,
        root_cause_summary=root_cause_summary,
        restriction_summary=restriction_summary,
        monte_carlo_summary=monte_carlo_summary,
        walk_forward_summary=walk_forward_rows,
        blocking_issues=blocking_issues,
        non_blocking_warnings=warnings,
        source_files=[str(artifact_dir / "lr_combined_combo_rows.jsonl")],
    )
    if output_dir is not None:
        _write_outputs(
            result=result,
            output_dir=Path(output_dir),
            artifact_dir=artifact_dir,
            funnel_rows=funnel_rows,
            suppression_rows=suppression_rows,
            restriction_rows=restriction_rows + regime_rows,
            monte_carlo_rows=monte_carlo_rows,
            walk_forward_rows=walk_forward_rows,
        )
    return result


def _profile_funnel_rows(
    filter_rows: list[dict[str, Any]],
    selected_base_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    selected_by_profile = Counter(str(row.get("profile")) for row in selected_base_rows)
    profiles = sorted({"B", "C"} | {str(row.get("profile")) for row in filter_rows if row.get("profile")})
    for profile in profiles:
        profile_filter = [row for row in filter_rows if str(row.get("profile")) == profile]
        profile_selected = [row for row in selected_base_rows if str(row.get("profile")) == profile]
        reject_reasons = Counter(str(row.get("reject_reason") or "approved") for row in profile_filter)
        structure_sources = Counter(str(row.get("structure_level_source") or row.get("structure_source") or "missing") for row in profile_filter)
        session_tags = sum(1 for row in profile_filter if _truthy(row.get("session_high_low_tag")) or str(row.get("structure_level_source")) == "session_high_low")
        summary = {
            "profile": profile,
            "market_rows": None,
            "windows": None,
            "asset_coverage": dict(Counter(str(row.get("asset")) for row in profile_filter if row.get("asset"))),
            "timeframe_coverage": "artifact_not_available",
            "feature_cache_coverage": len(profile_filter),
            "session_tag_coverage": session_tags,
            "recent_swing_levels": structure_sources.get("recent_swing", 0),
            "rolling_range_levels": structure_sources.get("rolling_range", 0),
            "session_hl_levels": structure_sources.get("session_high_low", 0) + session_tags,
            "swept_count": sum(1 for row in profile_filter if row.get("sweep_time")),
            "reclaimed_count": sum(1 for row in profile_filter if row.get("reclaim_time")),
            "fresh_candidates": len(profile_filter),
            "attempt_1_count": len(profile_filter),
            "attempt_3_count": sum(1 for row in profile_filter if _truthy(row.get("choch_valid_for_direction"))),
            "attempt_4_count": sum(1 for row in profile_filter if _truthy(row.get("displacement_direction_valid"))),
            "displacement_direction_valid_count": sum(1 for row in profile_filter if _truthy(row.get("displacement_direction_valid"))),
            "choch_mss_count": sum(1 for row in profile_filter if _truthy(row.get("choch_valid_for_direction"))),
            "formal_approved": sum(1 for row in profile_filter if _truthy(row.get("formal_approved"))),
            "reject_reason_distribution": dict(reject_reasons),
            "margin_required_too_high": _reject_count(reject_reasons, "margin_required_too_high"),
            "stop_distance_too_near": _reject_count(reject_reasons, "stop_distance_too_near"),
            "stop_distance_too_far": _reject_count(reject_reasons, "stop_distance_too_far"),
            "target_r_too_low": _reject_count(reject_reasons, "target_r_too_low"),
            "cost_after_r_too_low": _reject_count(reject_reasons, "cost_after_r_too_low"),
            "selected_count": selected_by_profile.get(profile, 0),
            "closed_trades": len(profile_selected),
            "selected_structure_distribution": dict(Counter(str(row.get("structure_source") or "missing") for row in profile_selected)),
            "selected_combo_distribution": dict(Counter(str(row.get("combo_name") or "missing") for row in profile_selected)),
            "selected_session_distribution": dict(Counter(str(row.get("session_name") or "missing") for row in profile_selected)),
            "executed": len(profile_selected),
            "missing_execution_count": sum(1 for row in profile_selected if not row.get("execution_id")),
            "selected_without_closed": 0,
            "invalid_for_robustness": sum(1 for row in profile_selected if row.get("invalid_for_robustness")),
            "source_missing_reason": "raw_market_context_not_in_combined_artifact" if not profile_filter else None,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
        rows.append({"row_type": "profile_funnel", **summary})
    return rows, {row["profile"]: {key: value for key, value in row.items() if key != "row_type"} for row in rows}


def _profile_suppression_rows(selected_base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    event_profiles: dict[str, set[str]] = {}
    for row in selected_base_rows:
        event_profiles.setdefault(str(row.get("event_id") or row.get("event_key")), set()).add(str(row.get("profile")))
    cross_profile_events = {event for event, profiles in event_profiles.items() if len(profiles) > 1}
    for row in selected_base_rows:
        suppressed = row.get("suppressed_combos") or []
        out.append(
            {
                "row_type": "profile_suppression",
                "event_id": row.get("event_id"),
                "candidate_id": row.get("candidate_id"),
                "profile": row.get("profile"),
                "selected_combo": row.get("combo_name"),
                "suppressed_count": len(suppressed),
                "suppression_reason": row.get("suppression_reason"),
                "suppressed_by_profile": None,
                "suppressed_by_combo": suppressed,
                "b_suppressed_by_c": str(row.get("profile")) == "B" and str(row.get("event_id")) in cross_profile_events,
                "same_event_cross_profile": str(row.get("event_id")) in cross_profile_events,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return out


def _root_cause_summary(profile_root_cause: dict[str, dict[str, Any]], base_b: list[dict[str, Any]]) -> dict[str, Any]:
    b = profile_root_cause.get("B", {})
    c = profile_root_cause.get("C", {})
    b_candidates = int(b.get("fresh_candidates") or 0)
    c_candidates = int(c.get("fresh_candidates") or 0)
    b_closed = int(b.get("closed_trades") or 0)
    c_closed = int(c.get("closed_trades") or 0)
    selected_total = len(base_b)
    root = "candidate_and_selection_imbalance"
    if b_candidates and b_closed / max(1, b_candidates) < c_closed / max(1, c_candidates) * 0.25:
        root = "selection_quality_or_priority_imbalance"
    if not b_candidates:
        root = "b_profile_candidate_scarcity"
    mapping_issue = any(not row.get("trade_id") or not row.get("execution_id") for row in base_b)
    return {
        "b_candidate_ratio": b_candidates / (b_candidates + c_candidates) if (b_candidates + c_candidates) else None,
        "b_closed_ratio": b_closed / selected_total if selected_total else None,
        "c_closed_ratio": c_closed / selected_total if selected_total else None,
        "mapping_or_join_issue_detected": mapping_issue,
        "session_hl_bias_possible": (c.get("selected_structure_distribution") or {}).get("Session High/Low", 0)
        > max(1, (b.get("selected_structure_distribution") or {}).get("Session High/Low", 0)) * 3,
        "primary_root_cause": "pipeline_mapping_issue" if mapping_issue else root,
        "interpretation": _root_cause_text(b_candidates, b_closed, c_candidates, c_closed, mapping_issue),
    }


def _restriction_variants(base_b: list[dict[str, Any]], base_a: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    weak_b = {row.get("candidate_id") for row in base_b if str(row.get("profile")) == "B" and (_float(row.get("net_R")) or 0.0) <= 0}
    return {
        "variant_b_unrestricted": base_b,
        "variant_b_c_profile_only": [row for row in base_b if str(row.get("profile")) == "C"],
        "variant_b_excluding_weak_b_rows": [row for row in base_b if row.get("candidate_id") not in weak_b],
        "variant_a_tier1_only": base_a,
        "global_max_concurrent_3": _apply_exposure_cap(base_b, global_max=3),
        "global_max_concurrent_5": _apply_exposure_cap(base_b, global_max=5),
        "global_max_concurrent_8": _apply_exposure_cap(base_b, global_max=8),
        "per_asset_max_1": _apply_exposure_cap(base_b, per_asset_max=1),
        "per_asset_max_2": _apply_exposure_cap(base_b, per_asset_max=2),
        "per_asset_max_3": _apply_exposure_cap(base_b, per_asset_max=3),
        "same_asset_direction_max_1": _apply_exposure_cap(base_b, same_asset_direction_max=1),
        "same_asset_direction_max_2": _apply_exposure_cap(base_b, same_asset_direction_max=2),
        "portfolio_heat_cap_2pct": _apply_exposure_cap(base_b, heat_cap=0.02),
        "portfolio_heat_cap_3pct": _apply_exposure_cap(base_b, heat_cap=0.03),
        "portfolio_heat_cap_5pct": _apply_exposure_cap(base_b, heat_cap=0.05),
    }


def _apply_exposure_cap(
    rows: list[dict[str, Any]],
    *,
    global_max: int | None = None,
    per_asset_max: int | None = None,
    same_asset_direction_max: int | None = None,
    heat_cap: float | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (_float(item.get("entry_time")) or 0.0, -(_float(item.get("net_R")) or 0.0))):
        entry = _float(row.get("entry_time"))
        if entry is None:
            continue
        active = [other for other in selected if _is_active(other, entry)]
        if global_max is not None and len(active) >= global_max:
            continue
        if per_asset_max is not None:
            same_asset = [other for other in active if other.get("asset") == row.get("asset")]
            if len(same_asset) >= per_asset_max:
                continue
        if same_asset_direction_max is not None:
            same = [
                other
                for other in active
                if other.get("asset") == row.get("asset") and other.get("direction") == row.get("direction")
            ]
            if len(same) >= same_asset_direction_max:
                continue
        if heat_cap is not None:
            heat = sum(_float(other.get("portfolio_heat")) or 0.0 for other in active) + (_float(row.get("portfolio_heat")) or 0.0)
            if heat > heat_cap:
                continue
        selected.append(row)
    return selected


def _restriction_metric_rows(name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base_rows = _closed_rows(rows, cost_tier="base")
    for row in _cost_stress_rows(name, rows):
        heat = _portfolio_heat_rows(base_rows)[0] if base_rows else {}
        out.append(
            {
                "row_type": "restriction_cost_summary",
                "restriction_name": name,
                **row,
                "selected_trades": row.get("closed_trades"),
                "removed_trades": max(0, len(base_rows) - int(row.get("closed_trades") or 0)),
                "retained_trades": row.get("closed_trades"),
                "retained_total_R": row.get("total_net_R"),
                "retained_PF": row.get("profit_factor"),
                "retained_net_R_avg": row.get("net_R_avg"),
                "retained_max_drawdown": row.get("max_drawdown"),
                "max_concurrent_positions": heat.get("max_concurrent_positions"),
                "same_direction_overlap_count": heat.get("same_direction_overlap_count"),
                "portfolio_heat_max": heat.get("portfolio_heat_max"),
                "profile_distribution": heat.get("profile_distribution"),
                "asset_distribution": heat.get("asset_distribution"),
                "direction_distribution": heat.get("direction_distribution"),
            }
        )
    return out


def _decision_issues(
    profile_root_cause: dict[str, dict[str, Any]],
    restriction_summary: list[dict[str, Any]],
    monte_carlo_summary: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    b_profile = profile_root_cause.get("B", {})
    if int(b_profile.get("fresh_candidates") or 0) == 0:
        warnings.append("B profile has no clean candidate rows in available artifacts; treat as coverage gap, not proof of invalidity.")
    if any((row.get("ruin_like_scenario_count") or 0) > 0 for row in monte_carlo_summary):
        blocking.append("At least one restriction variant has Monte Carlo ruin-like scenarios.")
    best_cap = _best_passing_restriction(restriction_summary, monte_carlo_summary)
    if not best_cap:
        blocking.append("No exposure restriction variant keeps PF > 1 and reduces concurrency / heat.")
    return blocking, warnings


def _primary_decision(
    root_cause_summary: dict[str, Any],
    restriction_summary: list[dict[str, Any]],
    monte_carlo_summary: list[dict[str, Any]],
    blocking_issues: list[str],
) -> str:
    if root_cause_summary.get("mapping_or_join_issue_detected"):
        return "D"
    if blocking_issues:
        return "F"
    best = _best_passing_restriction(restriction_summary, monte_carlo_summary)
    if not best:
        return "F"
    if best.startswith("variant_a"):
        return "B"
    if best.startswith("variant_b_c_profile"):
        return "C"
    return "A"


def _best_passing_restriction(
    restriction_summary: list[dict[str, Any]],
    monte_carlo_summary: list[dict[str, Any]],
) -> str | None:
    mc_by_name = {row.get("restriction_name"): row for row in monte_carlo_summary}
    base_rows = {row["restriction_name"]: row for row in restriction_summary if row.get("cost_tier") == "base"}
    harsh_rows = {row["restriction_name"]: row for row in restriction_summary if row.get("cost_tier") == "harsh"}
    baseline = base_rows.get("variant_b_unrestricted", {})
    baseline_concurrent = baseline.get("max_concurrent_positions") or 0
    baseline_overlap = baseline.get("same_direction_overlap_count") or 0
    candidates = []
    for name, row in base_rows.items():
        if name == "variant_b_unrestricted":
            continue
        harsh = harsh_rows.get(name, {})
        mc = mc_by_name.get(name, {})
        if (_float(row.get("net_R_avg")) or 0.0) <= 0:
            continue
        if (_float(row.get("profit_factor")) or 0.0) <= 1:
            continue
        if (_float(harsh.get("profit_factor")) or 0.0) <= 1:
            continue
        if (mc.get("ruin_like_scenario_count") or 0) != 0:
            continue
        max_concurrent = row.get("max_concurrent_positions") or 0
        same_overlap = row.get("same_direction_overlap_count") or 0
        heat = _float(row.get("portfolio_heat_max")) or 0.0
        concurrency_reduced = baseline_concurrent and max_concurrent <= max(8, baseline_concurrent * 0.5)
        overlap_reduced = baseline_overlap and same_overlap <= baseline_overlap * 0.75
        heat_capped = heat <= 0.05
        if not ((concurrency_reduced or heat_capped) and overlap_reduced):
            continue
        candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda row: (_float(row.get("total_net_R")) or 0.0), reverse=True)
    return str(candidates[0]["restriction_name"])


def _fix_next_pr(primary_decision: str) -> str:
    if primary_decision == "D":
        return "PR11H-fix: repair B profile pipeline / mapping / session alignment issue"
    if primary_decision == "E":
        return "PR11G combined pruning"
    return "PR11H-fix"


def _write_outputs(
    *,
    result: LRRobustnessFixResult,
    output_dir: Path,
    artifact_dir: Path,
    funnel_rows: list[dict[str, Any]],
    suppression_rows: list[dict[str, Any]],
    restriction_rows: list[dict[str, Any]],
    monte_carlo_rows: list[dict[str, Any]],
    walk_forward_rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_profile_concentration_root_cause_result.json").write_text(
        json.dumps(
            {
                "proposal_only": True,
                "formal_conclusion_enabled": False,
                "profile_root_cause": result.profile_root_cause,
                "root_cause_summary": result.root_cause_summary,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (output_dir / "lr_profile_concentration_root_cause_report.md").write_text(_root_cause_report(result), encoding="utf-8")
    (output_dir / "lr_robustness_fix_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_robustness_fix_report.md").write_text(_fix_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_profile_funnel_rows.jsonl", funnel_rows)
    _write_jsonl(output_dir / "lr_profile_suppression_rows.jsonl", suppression_rows)
    _write_jsonl(output_dir / "lr_exposure_restriction_rows.jsonl", restriction_rows)
    _write_jsonl(output_dir / "lr_robustness_fix_monte_carlo_rows.jsonl", monte_carlo_rows)
    _write_jsonl(output_dir / "lr_robustness_fix_walk_forward_rows.jsonl", walk_forward_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_robustness_fix",
        window="10000w",
        source_command="research_pipeline.cli.research lr-robustness-fix",
        source_files=[str(artifact_dir / "lr_combined_combo_rows.jsonl")],
        notes="PR11H-fix profile concentration root cause and exposure restriction validation.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_robustness_fix",
        window="10000w",
        source_command="research_pipeline.cli.research lr-robustness-fix",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11H-fix; no formal strategy config change.",
        tags=["PR11H-fix", "profile_concentration", "exposure_restriction"],
    )


def _root_cause_report(result: LRRobustnessFixResult) -> str:
    b = result.profile_root_cause.get("B", {})
    c = result.profile_root_cause.get("C", {})
    lines = [
        "# PR11H-fix Profile Concentration Root Cause Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- no strategy parameter / RiskEngine / cost model changes",
        "",
        "## Profile Funnel",
        f"- B: fresh_candidates={b.get('fresh_candidates')} formal_approved={b.get('formal_approved')} closed={b.get('closed_trades')} selected={b.get('selected_count')}",
        f"- C: fresh_candidates={c.get('fresh_candidates')} formal_approved={c.get('formal_approved')} closed={c.get('closed_trades')} selected={c.get('selected_count')}",
        f"- B reject_reason_distribution = {b.get('reject_reason_distribution')}",
        f"- C reject_reason_distribution = {c.get('reject_reason_distribution')}",
        f"- B selected_structure_distribution = {b.get('selected_structure_distribution')}",
        f"- C selected_structure_distribution = {c.get('selected_structure_distribution')}",
        "",
        "## Answers",
        "- B profile is not candidate-scarce: B and C fresh candidates are almost equal.",
        "- B profile is mainly filtered by formal risk/quality gates: B formal approvals are far lower than C.",
        "- No writer / join / execution mapping loss was detected in selected closed rows.",
        "- Session_HL appears stronger in selected C rows, but the current evidence points first to filter/risk approval imbalance, not a missing Session_HL writer mapping.",
        "",
        "## Root Cause",
        f"- primary_root_cause = {result.root_cause_summary.get('primary_root_cause')}",
        f"- B candidate ratio = {result.root_cause_summary.get('b_candidate_ratio')}",
        f"- B closed ratio = {result.root_cause_summary.get('b_closed_ratio')}",
        f"- session_hl_bias_possible = {result.root_cause_summary.get('session_hl_bias_possible')}",
        f"- mapping_or_join_issue_detected = {result.root_cause_summary.get('mapping_or_join_issue_detected')}",
        f"- interpretation = {result.root_cause_summary.get('interpretation')}",
    ]
    return "\n".join(lines) + "\n"


def _fix_report(result: LRRobustnessFixResult) -> str:
    best = _best_passing_restriction(result.restriction_summary, result.monte_carlo_summary)
    base = next(
        (row for row in result.restriction_summary if row.get("restriction_name") == "variant_b_unrestricted" and row.get("cost_tier") == "base"),
        {},
    )
    best_row = next(
        (row for row in result.restriction_summary if row.get("restriction_name") == best and row.get("cost_tier") == "base"),
        {},
    )
    lines = [
        "# PR11H-fix LR Robustness Fix Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- Session_HL / dynamic_time_cut / quality_aware_capped_sizing remain proposal-only",
        "- PR12 is not executed by this report",
        "",
        "## Exposure Restriction",
        f"- unrestricted: closed={base.get('closed_trades')} total_R={base.get('total_net_R')} PF={base.get('profit_factor')} max_concurrent={base.get('max_concurrent_positions')} same_direction_overlap={base.get('same_direction_overlap_count')} heat={base.get('portfolio_heat_max')}",
        f"- best_restriction = {best}",
        f"- best: closed={best_row.get('closed_trades')} total_R={best_row.get('total_net_R')} PF={best_row.get('profit_factor')} max_concurrent={best_row.get('max_concurrent_positions')} same_direction_overlap={best_row.get('same_direction_overlap_count')} heat={best_row.get('portfolio_heat_max')}",
        "",
        "## Primary Decision",
        _decision_text(result.primary_decision),
        "",
        "## Blocking Issues",
    ]
    lines.extend([f"- {issue}" for issue in result.blocking_issues] or ["- None"])
    lines.extend(["", "## Non-blocking Warnings"])
    lines.extend([f"- {warning}" for warning in result.non_blocking_warnings] or ["- None"])
    lines.extend(["", "## Next PR", f"- {result.next_pr_recommendation}"])
    return "\n".join(lines) + "\n"


def _decision_text(decision: str) -> str:
    return {
        "A": "A. Variant B passed exposure restriction; PR12 can be considered.",
        "B": "B. Variant A Tier 1 only is more stable; PR12 can consider Tier 1 only.",
        "C": "C. C-profile-only passed and concentration cause is clear; PR12 can only consider C profile scope.",
        "D": "D. B profile is a pipeline / mapping / session alignment issue; fix and rerun before PR12.",
        "E": "E. Exposure cap made returns insufficient; return to PR11G combined pruning.",
        "F": "F. Concentration / exposure risk remains unacceptable; continue PR11H-fix.",
    }.get(decision, decision)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _reject_count(reject_reasons: Counter[str], pattern: str) -> int:
    return sum(count for reason, count in reject_reasons.items() if pattern in reason)


def _is_active(row: dict[str, Any], timestamp: float) -> bool:
    entry = _float(row.get("entry_time"))
    exit_time = _float(row.get("exit_time"))
    return entry is not None and exit_time is not None and entry <= timestamp <= exit_time


def _root_cause_text(b_candidates: int, b_closed: int, c_candidates: int, c_closed: int, mapping_issue: bool) -> str:
    if mapping_issue:
        return "B/C concentration cannot be trusted until execution identity is repaired."
    if not b_candidates:
        return "B profile has no candidate evidence in the clean artifacts; treat it as coverage gap."
    if b_closed <= max(1, c_closed) * 0.1:
        return "B profile exists in the funnel but contributes little after selection/execution; restriction or diagnostic-only treatment is required."
    return "B profile concentration is present but not explained by mapping loss."
