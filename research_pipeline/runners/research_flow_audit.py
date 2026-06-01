from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_pipeline.core.audit.audit_result import ResearchFlowAuditResult
from research_pipeline.core.audit.cross_report import build_cross_report_rows
from research_pipeline.core.audit.invariants import build_invariant_rows
from research_pipeline.core.audit.joins import build_join_rows
from research_pipeline.core.audit.lineage import build_lineage_rows
from research_pipeline.core.audit.metrics_recompute import comparison_rows, recompute_metrics


VARIANT_B = "Variant B - Tier 1 + Positive Tier 2"
VARIANT_B_COMBOS = {
    "T1_session_hl_attempt4_fixed_current",
    "T1_recent_swing_attempt4_dynamic_quality",
    "T2_session_hl_attempt3_dynamic_quality",
}


def run_research_flow_audit(
    *,
    strategy: str,
    artifact_dir: Path | None,
    artifact_index: Path | None,
    registry: Path | None,
    output_dir: Path | None,
) -> ResearchFlowAuditResult:
    del registry
    resolved_dir = _resolve_artifact_dir(artifact_dir=artifact_dir, artifact_index=artifact_index)
    fix_result = _read_json(resolved_dir / "lr_combined_candidate_fix_result.json")
    variant_rows = _read_jsonl(resolved_dir / "lr_combined_variant_rows.jsonl")
    combo_rows_path = _combo_rows_path(resolved_dir)
    combo_rows = _read_jsonl(combo_rows_path)
    selected_rows_by_cost = _selected_variant_rows(combo_rows)

    reported_base = _variant_row(variant_rows, VARIANT_B, "ALL", "base") or {}
    lineage_rows = build_lineage_rows(source_artifact=str(combo_rows_path), reported_variant=reported_base)
    join_rows = build_join_rows(
        mapping_diagnostics=fix_result.get("mapping_diagnostics", {}),
        variant_rows=variant_rows,
    )
    metric_rows: list[dict[str, Any]] = []
    for cost_tier, rows in selected_rows_by_cost.items():
        reported = _variant_row(variant_rows, VARIANT_B, "ALL", cost_tier) or {}
        metric_rows.extend(
            comparison_rows(
                scope=VARIANT_B,
                cost_tier=cost_tier,
                reported=reported,
                recomputed=recompute_metrics(rows),
                source_artifact=str(combo_rows_path),
            )
        )
    invariant_rows = build_invariant_rows(
        selected_rows=selected_rows_by_cost.get("base", []),
        reported_variant=reported_base,
        metric_rows=[row for row in metric_rows if row["scope"] == VARIANT_B and row["cost_tier"] == "base"],
    )
    cross_report_rows = build_cross_report_rows(resolved_dir)
    blocking_issues = _blocking_issues(join_rows, invariant_rows, metric_rows, cross_report_rows)
    warnings = _warnings(join_rows, invariant_rows, cross_report_rows)
    primary_decision = _primary_decision(blocking_issues, warnings, metric_rows, invariant_rows)
    result = ResearchFlowAuditResult(
        strategy=strategy,
        proposal_only=True,
        formal_conclusion_enabled=False,
        audit_passed=primary_decision in {"A", "B"},
        primary_decision=primary_decision,
        blocking_issues=blocking_issues,
        non_blocking_warnings=warnings,
        next_pr_recommendation="PR 11H Robustness Validation"
        if primary_decision in {"A", "B"}
        else "PR 11G-QA-fix",
        lineage_rows=lineage_rows,
        join_audit_rows=join_rows,
        invariant_rows=invariant_rows,
        metric_recompute_rows=metric_rows,
        cross_report_rows=cross_report_rows,
        source_files=[
            str(resolved_dir / "lr_combined_candidate_fix_result.json"),
            str(resolved_dir / "lr_combined_variant_rows.jsonl"),
            str(combo_rows_path),
        ],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _resolve_artifact_dir(*, artifact_dir: Path | None, artifact_index: Path | None) -> Path:
    if artifact_dir is not None:
        return Path(artifact_dir)
    if artifact_index is None:
        raise ValueError("artifact_dir or artifact_index is required")
    return Path(artifact_index).parent


def _combo_rows_path(artifact_dir: Path) -> Path:
    local = artifact_dir / "lr_combined_combo_rows.jsonl"
    if local.exists():
        return local
    sibling = artifact_dir.parent / "lr_combined_pr11g" / "lr_combined_combo_rows.jsonl"
    if sibling.exists():
        return sibling
    raise FileNotFoundError("lr_combined_combo_rows.jsonl not found in artifact_dir or sibling lr_combined_pr11g")


def _selected_variant_rows(combo_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    base_candidates = [
        row
        for row in combo_rows
        if row.get("cost_tier") == "base" and row.get("combo_name") in VARIANT_B_COMBOS
    ]
    selected_lookup: dict[tuple[str, str], str] = {}
    by_event: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in base_candidates:
        by_event.setdefault((str(row.get("event_key")), str(row.get("direction"))), []).append(row)
    for event_key, rows in by_event.items():
        selected = min(_unique_combo_rows(rows), key=lambda row: row.get("priority") or 999)
        selected_lookup[event_key] = str(selected.get("combo_name"))
    selected_by_cost = {cost_tier: [] for cost_tier in ("base", "stress", "harsh")}
    for row in combo_rows:
        cost_tier = str(row.get("cost_tier"))
        key = (str(row.get("event_key")), str(row.get("direction")))
        if cost_tier in selected_by_cost and selected_lookup.get(key) == row.get("combo_name"):
            selected_by_cost[cost_tier].append(row)
    return selected_by_cost


def _unique_combo_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_combo: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_combo.setdefault(str(row.get("combo_name")), row)
    return list(by_combo.values())


def _variant_row(rows: list[dict[str, Any]], variant_name: str, tier: str, cost_tier: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("variant_name") == variant_name and row.get("tier") == tier and row.get("cost_tier") == cost_tier:
            return row
    return None


def _blocking_issues(
    join_rows: list[dict[str, Any]],
    invariant_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    cross_report_rows: list[dict[str, Any]],
) -> list[str]:
    issues = []
    issues.extend(
        f"Join fix required for {row['scope']}: missing_execution_row_count={row['missing_execution_row_count']}"
        for row in join_rows
        if row.get("fix_required")
    )
    issues.extend(
        f"Invariant failed: {row['invariant_name']} ({row['details']})"
        for row in invariant_rows
        if row.get("blocking") and not row.get("passed")
    )
    issues.extend(
        f"Metric mismatch: {row['scope']} {row['cost_tier']} {row['metric_name']} reported={row['reported_value']} recomputed={row['recomputed_value']}"
        for row in metric_rows
        if not row.get("passed")
    )
    issues.extend(
        f"Cross-report source missing or unacceptable: {row['scope']} {row['metric_name']}"
        for row in cross_report_rows
        if not row.get("acceptable")
    )
    return issues


def _warnings(
    join_rows: list[dict[str, Any]],
    invariant_rows: list[dict[str, Any]],
    cross_report_rows: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    warnings.extend(
        f"{row['scope']} has {row['selected_without_closed_count']} selected_without_closed rows; excluded from performance."
        for row in join_rows
        if (row.get("selected_without_closed_count") or 0) > 0 and not row.get("fix_required")
    )
    warnings.extend(
        f"Invariant unavailable: {row['invariant_name']} ({row['details']})"
        for row in invariant_rows
        if not row.get("blocking") and not row.get("passed")
    )
    warnings.extend(
        f"Cross-report definition change: {row['scope']} {row['metric_name']} ({row['metric_changed_reason']})"
        for row in cross_report_rows
        if row.get("acceptable") and row.get("metric_changed_reason")
    )
    return warnings


def _primary_decision(
    blocking_issues: list[str],
    warnings: list[str],
    metric_rows: list[dict[str, Any]],
    invariant_rows: list[dict[str, Any]],
) -> str:
    if blocking_issues:
        if any("closed_trade_has_execution_identity" in issue for issue in blocking_issues):
            return "D"
        if any("Metric mismatch" in issue for issue in blocking_issues):
            return "C"
        if any("proposal" in issue.lower() for issue in blocking_issues):
            return "F"
        if any("lookahead" in issue.lower() or "lifecycle" in issue.lower() for issue in blocking_issues):
            return "E"
        return "D"
    if any(not row.get("passed") for row in metric_rows):
        return "C"
    if any(row["invariant_name"] == "proposal_only_rows_excluded_from_performance" and not row["passed"] for row in invariant_rows):
        return "F"
    return "B" if warnings else "A"


def _write_outputs(result: ResearchFlowAuditResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "research_flow_audit_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "research_flow_audit_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "research_flow_lineage_rows.jsonl", result.lineage_rows)
    _write_jsonl(output_dir / "research_flow_join_audit_rows.jsonl", result.join_audit_rows)
    _write_jsonl(output_dir / "research_flow_invariant_rows.jsonl", result.invariant_rows)
    _write_jsonl(output_dir / "research_flow_metric_recompute_rows.jsonl", result.metric_recompute_rows)
    _write_jsonl(output_dir / "research_flow_cross_report_rows.jsonl", result.cross_report_rows)


def _report(result: ResearchFlowAuditResult) -> str:
    lines = [
        "# PR 11G-QA Research Flow Integrity Audit Report",
        "",
        f"- strategy = {result.strategy}",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        f"- audit_passed = {str(result.audit_passed).lower()}",
        "",
        "## Join Integrity",
    ]
    for row in result.join_audit_rows:
        lines.append(
            f"- {row['scope']}: selected={row['selected_count']} closed={row['closed_count']} "
            f"selected_without_closed={row['selected_without_closed_count']} "
            f"proposal_only_unexecuted={row['proposal_only_unexecuted_count']} fix_required={row['fix_required']}"
        )
    lines.extend(["", "## Metric Recompute"])
    for row in result.metric_recompute_rows:
        if row["scope"] == VARIANT_B and row["cost_tier"] == "base":
            lines.append(
                f"- {row['metric_name']}: reported={row['reported_value']} recomputed={row['recomputed_value']} "
                f"passed={row['passed']}"
            )
    lines.extend(["", "## Invariants"])
    for row in result.invariant_rows:
        lines.append(
            f"- {row['invariant_name']}: passed={row['passed']} blocking={row['blocking']} details={row['details']}"
        )
    lines.extend(["", "## Primary Decision", f"{result.primary_decision}. {_decision_text(result.primary_decision)}"])
    lines.append("")
    lines.append("## Blocking Issues")
    lines.extend(f"- {issue}" for issue in result.blocking_issues) if result.blocking_issues else lines.append("- None")
    lines.append("")
    lines.append("## Non-blocking Warnings")
    lines.extend(f"- {warning}" for warning in result.non_blocking_warnings) if result.non_blocking_warnings else lines.append("- None")
    lines.extend(["", "## Next PR Recommendation", f"- {result.next_pr_recommendation}"])
    return "\n".join(lines) + "\n"


def _decision_text(decision: str) -> str:
    return {
        "A": "Audit passed，可以进入 PR 11H robustness。",
        "B": "Audit found non-blocking issues，可以进入 PR 11H，但需带 warning。",
        "C": "Audit failed due to metric mismatch，必须修 report / metrics。",
        "D": "Audit failed due to join / execution mapping，必须修 mapping。",
        "E": "Audit failed due to lookahead / event lifecycle，必须修 scanner / FSM。",
        "F": "Audit failed due to proposal rows entering performance，必须修 row typing。",
    }[decision]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
