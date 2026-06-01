from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.lr_combined_candidate_proposal import (
    COMBOS,
    COST_TIERS,
    _combo_rows,
    _duplicate_selected_events,
    _group_key,
    _group_keys,
    _metrics,
    _read_csv,
    _read_jsonl,
    _write_jsonl,
)
from research_pipeline.runners.register_research_run import register_research_run


UNMAPPED_DYNAMIC_COMBO = "T1_session_hl_attempt4_dynamic_quality"
NEGATIVE_TIER2_COMBO = "T2_recent_swing_attempt3_dynamic_quality"
POSITIVE_TIER2_COMBO = "T2_session_hl_attempt3_dynamic_quality"


VARIANT_COMBOS = {
    "Variant A - Tier 1 only": [
        "T1_session_hl_attempt4_fixed_current",
        "T1_recent_swing_attempt4_dynamic_quality",
    ],
    "Variant B - Tier 1 + Positive Tier 2": [
        "T1_session_hl_attempt4_fixed_current",
        "T1_recent_swing_attempt4_dynamic_quality",
        POSITIVE_TIER2_COMBO,
    ],
    "Variant C - Full original family": [combo.name for combo in COMBOS],
    "Variant D - Dynamic audited family": [
        UNMAPPED_DYNAMIC_COMBO,
        "T1_recent_swing_attempt4_dynamic_quality",
        POSITIVE_TIER2_COMBO,
    ],
}


@dataclass(frozen=True)
class LRCombinedCandidateFixResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    all_combined_candidates_proposal_only: bool
    dynamic_time_cut_proposal_only: bool
    quality_aware_capped_sizing_proposal_only: bool
    session_hl_source_proposal_only: bool
    mapping_diagnostics: dict[str, Any]
    combo_rows: list[dict[str, Any]]
    variant_rows: list[dict[str, Any]]
    event_selection_rows: list[dict[str, Any]]
    unmapped_rows: list[dict[str, Any]]
    grouped_rows: list[dict[str, Any]]
    diagnostic_combos: list[dict[str, Any]]
    primary_decision: str
    secondary_findings: list[str]
    deferred_items: list[str]
    next_pr_recommendation: str
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_combined_candidate_fix(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> LRCombinedCandidateFixResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}
    combo_rows = _combo_rows(sizing_rows, filter_by_candidate, execution_by_candidate)

    full_selection, _ = _select_variant_rows(combo_rows, VARIANT_COMBOS["Variant C - Full original family"])
    mapping_diagnostics, unmapped_rows = _mapping_diagnostics(full_selection)
    dynamic_valid = mapping_diagnostics["remaining_unmapped_selected_count"] == 0 and _closed_for_combo(
        full_selection, UNMAPPED_DYNAMIC_COMBO
    ) > 0

    event_selection_rows: list[dict[str, Any]] = []
    grouped_rows: list[dict[str, Any]] = []
    variant_rows: list[dict[str, Any]] = []
    selected_by_variant: dict[str, list[dict[str, Any]]] = {}
    for variant_name, combo_names in VARIANT_COMBOS.items():
        if variant_name.startswith("Variant D") and not dynamic_valid:
            variant_rows.extend(_invalid_variant_rows(variant_name, "dynamic_combo_unmapped"))
            continue
        selected, selections = _select_variant_rows(combo_rows, combo_names)
        selected_by_variant[variant_name] = selected
        event_selection_rows.extend(selections)
        grouped_rows.extend(_grouped_rows_for_variant(variant_name, combo_rows, selected, combo_names))
        variant_rows.extend(_variant_rows(variant_name, selected, selections))

    diagnostic_combos = _diagnostic_combos(full_selection, dynamic_valid)
    primary_decision = _primary_decision(variant_rows)
    result = LRCombinedCandidateFixResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        all_combined_candidates_proposal_only=True,
        dynamic_time_cut_proposal_only=True,
        quality_aware_capped_sizing_proposal_only=True,
        session_hl_source_proposal_only=True,
        mapping_diagnostics=mapping_diagnostics,
        combo_rows=combo_rows,
        variant_rows=variant_rows,
        event_selection_rows=event_selection_rows,
        unmapped_rows=unmapped_rows,
        grouped_rows=grouped_rows,
        diagnostic_combos=diagnostic_combos,
        primary_decision=primary_decision,
        secondary_findings=_secondary_findings(variant_rows, diagnostic_combos, mapping_diagnostics),
        deferred_items=[
            "PR 11H robustness",
            "production formalization",
            "cleanup / merge",
            "PDH/PDL / EQH/EQL scanner support",
            "trend continuation future research",
        ],
        next_pr_recommendation="PR 11H Robustness Validation"
        if primary_decision in {"A", "B", "C", "D", "F"}
        else "PR 11G-fix",
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _select_variant_rows(
    combo_rows: list[dict[str, Any]], combo_names: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed = {name for name in combo_names}
    by_event: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in combo_rows:
        if row["cost_tier"] == "base" and row["combo_name"] in allowed:
            by_event.setdefault((row["event_key"], str(row["direction"])), []).append(row)

    selections: list[dict[str, Any]] = []
    selected_lookup: dict[tuple[str, str], str] = {}
    for (event_key, direction), rows in by_event.items():
        unique = _unique_combo_rows(rows)
        selected = min(unique, key=lambda row: row["priority"])
        suppressed = [row["combo_name"] for row in unique if row["combo_name"] != selected["combo_name"]]
        selected_lookup[(event_key, direction)] = selected["combo_name"]
        selections.append(
            {
                "event_key": event_key,
                "candidate_id": selected.get("candidate_id"),
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

    selected_rows = []
    for row in combo_rows:
        key = (row["event_key"], str(row["direction"]))
        if selected_lookup.get(key) != row["combo_name"]:
            continue
        selected_rows.append(
            {
                **row,
                "selected_combo": row["combo_name"],
                "suppressed_combos": next(
                    (
                        selection["suppressed_combos"]
                        for selection in selections
                        if selection["event_key"] == row["event_key"]
                        and selection["direction"] == str(row["direction"])
                    ),
                    [],
                ),
                "suppression_reason": "",
                "selected": True,
            }
        )
    return selected_rows, selections


def _unique_combo_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_combo: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_combo.setdefault(str(row["combo_name"]), row)
    return list(by_combo.values())


def _mapping_diagnostics(selected_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target = [
        row
        for row in selected_rows
        if row["cost_tier"] == "base" and row["combo_name"] == UNMAPPED_DYNAMIC_COMBO
    ]
    unmapped = [row for row in target if not row.get("closed_trade")]
    unmapped_rows = []
    for row in unmapped:
        reason = "proposal_only_unexecuted" if row.get("sizing_policy") != "current_risk_based_sizing" else "missing_execution_row"
        unmapped_rows.append(
            {
                "combo_name": row["combo_name"],
                "candidate_id": row.get("candidate_id"),
                "event_key": row.get("event_key"),
                "asset": row.get("asset"),
                "profile": row.get("profile"),
                "direction": row.get("direction"),
                "sizing_policy": row.get("sizing_policy"),
                "exit_profile": row.get("exit_profile"),
                "has_trade_id": bool(row.get("trade_id")),
                "has_execution_row": bool(row.get("closed_trade")),
                "unmapped_reason": reason,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    missing_trade_id = sum(1 for row in unmapped_rows if not row["has_trade_id"])
    proposal_only_unexecuted = sum(1 for row in unmapped_rows if row["unmapped_reason"] == "proposal_only_unexecuted")
    missing_execution = len(unmapped_rows)
    diagnostics = {
        "combo_name": UNMAPPED_DYNAMIC_COMBO,
        "selected_without_closed_count": len(unmapped_rows),
        "missing_trade_id_count": missing_trade_id,
        "missing_execution_row_count": missing_execution,
        "join_key_mismatch_count": 0,
        "proposal_only_unexecuted_count": proposal_only_unexecuted,
        "fix_applied": "downgraded_to_diagnostic_excluded_from_main_variants"
        if unmapped_rows
        else "execution_mapping_available",
        "remaining_unmapped_selected_count": len(unmapped_rows),
    }
    return diagnostics, unmapped_rows


def _closed_for_combo(rows: list[dict[str, Any]], combo_name: str) -> int:
    return sum(
        1
        for row in rows
        if row["cost_tier"] == "base" and row["combo_name"] == combo_name and row.get("closed_trade")
    )


def _grouped_rows_for_variant(
    variant_name: str,
    combo_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    combo_names: list[str],
) -> list[dict[str, Any]]:
    rows = []
    for combo in COMBOS:
        if combo.name not in combo_names:
            continue
        for cost_tier in COST_TIERS:
            all_combo = [
                row
                for row in combo_rows
                if row["combo_name"] == combo.name and row["cost_tier"] == cost_tier
            ]
            selected = [
                row
                for row in selected_rows
                if row["combo_name"] == combo.name and row["cost_tier"] == cost_tier
            ]
            rows.append(_summary_row(variant_name, all_combo, selected, combo.name, combo.tier, cost_tier, None))
            for key in _group_keys(selected):
                rows.append(
                    _summary_row(
                        variant_name,
                        all_combo,
                        [row for row in selected if _group_key(row) == key],
                        combo.name,
                        combo.tier,
                        cost_tier,
                        key,
                    )
                )
    return rows


def _summary_row(
    variant_name: str,
    all_combo: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    combo_name: str,
    tier: str,
    cost_tier: str,
    key: tuple[str, str, str, str, str, str, str, str] | None,
) -> dict[str, Any]:
    if key is None:
        asset = profile = direction = structure_source = attempt_type = exit_profile = sizing_policy = group_tier = "ALL"
    else:
        asset, profile, direction, structure_source, attempt_type, exit_profile, sizing_policy, group_tier = key
    return {
        **_metrics(selected),
        "variant_name": variant_name,
        "combo_name": combo_name,
        "tier": tier if key is None else group_tier,
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
        "selected_without_closed_count": sum(1 for row in selected if not row.get("closed_trade")),
        "suppressed_trades": max(0, len({row["event_key"] for row in all_combo}) - len({row["event_key"] for row in selected})),
        "incremental_trades": sum(1 for row in selected if row.get("closed_trade")),
        "incremental_net_R": sum(row.get("net_R") or 0.0 for row in selected if row.get("closed_trade")),
        "duplicate_event_count": _duplicate_selected_events(selected),
        "overlapping_event_count": 0,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _variant_rows(
    variant_name: str, selected_rows: list[dict[str, Any]], selections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    overlapping = sum(1 for selection in selections if selection.get("suppressed_combos"))
    for cost_tier in COST_TIERS:
        selected = [row for row in selected_rows if row["cost_tier"] == cost_tier]
        for tier in ("ALL", "Tier 1", "Tier 2", "Tier 3"):
            tier_rows = selected if tier == "ALL" else [row for row in selected if row["tier"] == tier]
            rows.append(
                {
                    **_metrics(tier_rows),
                    "variant_name": variant_name,
                    "variant_status": "valid",
                    "tier": tier,
                    "cost_tier": cost_tier,
                    "candidates": len({row["event_key"] for row in tier_rows}),
                    "selected_trades": len({row["event_key"] for row in tier_rows}),
                    "selected_without_closed_count": sum(1 for row in tier_rows if not row.get("closed_trade")),
                    "proposal_only_unexecuted_count": sum(
                        1
                        for row in tier_rows
                        if not row.get("closed_trade")
                        and row.get("sizing_policy") != "current_risk_based_sizing"
                    ),
                    "missing_execution_row_count": sum(
                        1
                        for row in tier_rows
                        if not row.get("closed_trade")
                        and row.get("sizing_policy") == "current_risk_based_sizing"
                    ),
                    "suppressed_trades": 0,
                    "incremental_trades": sum(1 for row in tier_rows if row.get("closed_trade")),
                    "incremental_net_R": sum(row.get("net_R") or 0.0 for row in tier_rows if row.get("closed_trade")),
                    "duplicate_event_count": _duplicate_selected_events(tier_rows),
                    "overlapping_event_count": overlapping if tier == "ALL" else 0,
                    "proposal_only": True,
                    "formal_conclusion_enabled": False,
                }
            )
    return rows


def _invalid_variant_rows(variant_name: str, reason: str) -> list[dict[str, Any]]:
    rows = []
    for cost_tier in COST_TIERS:
        rows.append(
            {
                **_metrics([]),
                "variant_name": variant_name,
                "variant_status": "invalid",
                "invalid_reason": reason,
                "tier": "ALL",
                "cost_tier": cost_tier,
                "candidates": 0,
                "selected_trades": 0,
                "selected_without_closed_count": 0,
                "proposal_only_unexecuted_count": 0,
                "missing_execution_row_count": 0,
                "suppressed_trades": 0,
                "incremental_trades": 0,
                "incremental_net_R": 0,
                "duplicate_event_count": 0,
                "overlapping_event_count": 0,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return rows


def _diagnostic_combos(selected_rows: list[dict[str, Any]], dynamic_valid: bool) -> list[dict[str, Any]]:
    diagnostics = []
    for combo_name, reason in (
        (UNMAPPED_DYNAMIC_COMBO, "proposal_only_unexecuted" if not dynamic_valid else "audited_execution_available"),
        (NEGATIVE_TIER2_COMBO, "negative_contribution_downgraded_to_diagnostic"),
        ("T3_recent_swing_attempt4_fixed_current", "tier3_sample_too_small"),
        ("T3_rolling_range_attempt4_dynamic_quality", "tier3_sample_too_small"),
        ("T3_session_hl_attempt4_conservative_current", "tier3_sample_too_small"),
    ):
        base = [row for row in selected_rows if row["combo_name"] == combo_name and row["cost_tier"] == "base"]
        diagnostics.append(
            {
                "combo_name": combo_name,
                "diagnostic_reason": reason,
                "closed_trades": sum(1 for row in base if row.get("closed_trade")),
                "net_R_avg": _metrics(base)["net_R_avg"],
                "total_net_R": _metrics(base)["total_net_R"],
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return diagnostics


def _primary_decision(variant_rows: list[dict[str, Any]]) -> str:
    variant_b_base = _variant_row(variant_rows, "Variant B - Tier 1 + Positive Tier 2", "ALL", "base")
    variant_b_harsh = _variant_row(variant_rows, "Variant B - Tier 1 + Positive Tier 2", "ALL", "harsh")
    variant_a_base = _variant_row(variant_rows, "Variant A - Tier 1 only", "ALL", "base")
    if not variant_b_base or not variant_b_harsh or not variant_a_base:
        return "E"
    if (variant_b_base["duplicate_event_count"] or 0) != 0:
        return "E"
    if (variant_b_base["net_R_avg"] or 0.0) > 0 and (variant_b_harsh["net_R_avg"] or 0.0) > 0:
        if (variant_b_base["total_net_R"] or 0.0) >= (variant_a_base["total_net_R"] or 0.0):
            return "C"
        return "B"
    return "F"


def _secondary_findings(
    variant_rows: list[dict[str, Any]],
    diagnostic_combos: list[dict[str, Any]],
    mapping_diagnostics: dict[str, Any],
) -> list[str]:
    variant_a = _variant_row(variant_rows, "Variant A - Tier 1 only", "ALL", "base")
    variant_b = _variant_row(variant_rows, "Variant B - Tier 1 + Positive Tier 2", "ALL", "base")
    return [
        f"{UNMAPPED_DYNAMIC_COMBO} selected_without_closed={mapping_diagnostics['selected_without_closed_count']}，已降为 diagnostic，不进入主推荐组合。",
        f"{NEGATIVE_TIER2_COMBO} 为负贡献 Tier 2，已从主组合剔除。",
        f"{POSITIVE_TIER2_COMBO} 保留为正贡献 Tier 2，用于补充 Tier 1 未覆盖事件。",
        f"Variant A total_net_R={variant_a.get('total_net_R') if variant_a else None}；Variant B total_net_R={variant_b.get('total_net_R') if variant_b else None}。",
        "Tier 3 样本不足，继续保持 diagnostic-only。",
        "dynamic_time_cut 与 quality-aware sizing 仍为 proposal-only，没有写入正式配置。",
    ]


def _variant_row(rows: list[dict[str, Any]], variant_name: str, tier: str, cost_tier: str) -> dict[str, Any] | None:
    for row in rows:
        if row["variant_name"] == variant_name and row["tier"] == tier and row["cost_tier"] == cost_tier:
            return row
    return None


def _write_outputs(result: LRCombinedCandidateFixResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_combined_candidate_fix_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_combined_candidate_fix_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_combined_variant_rows.jsonl", result.variant_rows)
    _write_jsonl(output_dir / "lr_combined_combo_rows.jsonl", result.combo_rows)
    _write_jsonl(output_dir / "lr_combined_event_selection_rows.jsonl", result.event_selection_rows)
    _write_jsonl(output_dir / "lr_combined_unmapped_rows.jsonl", result.unmapped_rows)
    _write_jsonl(output_dir / "lr_combined_grouped_rows.jsonl", result.grouped_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_combined_candidate_fix",
        window="10000w",
        source_command="research_pipeline.cli.research lr-combined-candidate-fix",
        notes="PR11G-fix proposal-only combined portfolio pruning and execution mapping audit.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_combined_candidate_fix",
        window="10000w",
        source_command="research_pipeline.cli.research lr-combined-candidate-fix",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11G-fix combined pruning; no formal strategy config change.",
        tags=["PR11G-fix", "proposal_only", "combined_lr"],
    )


def _report(result: LRCombinedCandidateFixResult) -> str:
    lines = [
        "# PR 11G-fix Combined Portfolio Pruning + Execution Mapping Fix Report",
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
        "## Execution Mapping Audit",
    ]
    for key, value in result.mapping_diagnostics.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Variant Summary"])
    for row in result.variant_rows:
        if row["tier"] == "ALL" and row["cost_tier"] == "base":
            lines.append(
                f"- {row['variant_name']}: status={row.get('variant_status')} closed={row['closed_trades']} "
                f"net_R={row['net_R_avg']} total_net_R={row['total_net_R']} "
                f"PF={row['profit_factor']} selected_without_closed={row['selected_without_closed_count']} "
                f"proposal_only_unexecuted={row.get('proposal_only_unexecuted_count')}"
            )
    lines.extend(
        [
            "",
            "## Portfolio Mapping Note",
            "- selected_without_closed 中的 proposal_only_unexecuted rows 只用于 proposal sizing 覆盖诊断，不计入 closed_trades / net_R / PF。",
            "- 主推荐 variant 已剔除 closed=0 的核心 unmapped combo，不把未执行 proposal rows 当成 formal closed trades。",
        ]
    )
    lines.extend(["", "## Diagnostic Combos"])
    for row in result.diagnostic_combos:
        lines.append(
            f"- {row['combo_name']}: reason={row['diagnostic_reason']} "
            f"closed={row['closed_trades']} net_R={row['net_R_avg']}"
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
        "A": "Clean combined LR family 通过，按计划进入 PR 11H robustness。",
        "B": "Tier 1 only 通过，Tier 2 保留 diagnostic，按计划进入 PR 11H。",
        "C": "Tier 1 + positive Tier 2 通过，按计划进入 PR 11H。",
        "D": "dynamic audited family 通过，按计划进入 PR 11H。",
        "E": "执行映射仍有问题，继续 PR 11G-fix。",
        "F": "组合不优于单一核心，退回 core setup 后进入 PR 11H。",
    }[decision]
