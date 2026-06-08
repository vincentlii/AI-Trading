from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.audit.artifact_integrity import build_artifact_integrity_rows
from research_pipeline.core.audit.audit_result import FullPipelineAuditResult
from research_pipeline.core.audit.code_logic_review import build_code_logic_review_rows
from research_pipeline.core.audit.lineage import build_lineage_rows
from research_pipeline.core.audit.metrics_recompute import comparison_rows, recompute_metrics
from research_pipeline.core.audit.no_lookahead import build_no_lookahead_rows
from research_pipeline.core.audit.proposal_boundary import build_proposal_boundary_rows
from research_pipeline.core.audit.report_consistency import build_report_consistency_rows
from research_pipeline.core.audit.schema_contract import build_schema_contract_rows
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.research_flow_audit import VARIANT_B, _selected_variant_rows, _variant_row


def run_full_pipeline_audit(
    *,
    strategy: str,
    artifact_dir: Path,
    registry: Path | None,
    output_dir: Path | None,
) -> FullPipelineAuditResult:
    artifact_dir = Path(artifact_dir)
    manifest_path = artifact_dir / "run_manifest.json"
    if manifest_path.exists():
        return _run_manifest_full_pipeline_audit(
            strategy=strategy,
            artifact_dir=artifact_dir,
            manifest_path=manifest_path,
            registry=registry,
            output_dir=output_dir,
        )
    fix_result = _read_json(artifact_dir / "lr_combined_candidate_fix_result.json")
    lineage_repair_result = _read_optional_json(artifact_dir / "lineage_repair_result.json")
    variant_rows = _read_jsonl(artifact_dir / "lr_combined_variant_rows.jsonl")
    combo_rows_path = _combo_rows_path(artifact_dir)
    combo_rows = _read_jsonl(combo_rows_path)
    selected_by_cost = _selected_variant_rows(combo_rows)
    selected_base = selected_by_cost.get("base", [])
    reported_base = _variant_row(variant_rows, VARIANT_B, "ALL", "base") or {}

    schema_rows = _combo_schema_rows(combo_rows)
    schema_rows.extend(
        build_schema_contract_rows(
            artifact_name="lr_combined_variant_rows.jsonl",
            rows=variant_rows,
            inferred_row_type="summary_row",
            required_fields={"variant_name", "closed_trades", "net_R_avg", "total_net_R"},
            blocking_missing_row_type=False,
        )
    )

    lineage_rows = build_lineage_rows(source_artifact=str(combo_rows_path), reported_variant=reported_base)
    join_rows = _join_integrity_rows(fix_result, variant_rows, selected_base)
    proposal_rows = build_proposal_boundary_rows(
        selected_rows=selected_base,
        variant_rows=variant_rows,
        diagnostic_combos=fix_result.get("diagnostic_combos", []),
    )
    no_lookahead_rows = build_no_lookahead_rows(selected_base)
    metric_rows = []
    for cost_tier, rows in selected_by_cost.items():
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
    artifact_rows = build_artifact_integrity_rows(artifact_dir, registry=registry)
    report_rows = build_report_consistency_rows(artifact_dir)
    code_rows = build_code_logic_review_rows(Path.cwd())

    blocking_issues = _blocking_issues(
        join_rows=join_rows,
        proposal_rows=proposal_rows,
        no_lookahead_rows=no_lookahead_rows,
        metric_rows=metric_rows,
        artifact_rows=artifact_rows,
        code_rows=code_rows,
        lineage_repair_result=lineage_repair_result,
    )
    warnings = _warnings(schema_rows, join_rows, no_lookahead_rows, artifact_rows, report_rows, code_rows)
    primary_decision = _primary_decision(blocking_issues)
    result = FullPipelineAuditResult(
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
        schema_contract_rows=schema_rows,
        lineage_rows=lineage_rows,
        join_integrity_rows=join_rows,
        proposal_boundary_rows=proposal_rows,
        no_lookahead_rows=no_lookahead_rows,
        metric_recompute_rows=metric_rows,
        report_consistency_rows=report_rows,
        artifact_integrity_rows=artifact_rows,
        code_logic_review_rows=code_rows,
        source_files=[str(artifact_dir), str(combo_rows_path)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _run_manifest_full_pipeline_audit(
    *,
    strategy: str,
    artifact_dir: Path,
    manifest_path: Path,
    registry: Path | None,
    output_dir: Path | None,
) -> FullPipelineAuditResult:
    manifest = _read_json(manifest_path)
    artifact_paths = {
        key: _resolve_artifact_path(artifact_dir, value)
        for key, value in (manifest.get("artifact_paths") or {}).items()
        if isinstance(value, str) and value
    }
    candidate_rows = _read_optional_jsonl(artifact_paths.get("candidate_rows"))
    filter_rows = _read_optional_jsonl(artifact_paths.get("filter_results"))
    closed_rows = _read_optional_jsonl(artifact_paths.get("closed_trade_rows"))
    diagnostic_rows = _read_optional_jsonl(artifact_paths.get("diagnostic_rows"))
    summary_rows = _read_optional_jsonl(artifact_paths.get("summary_rows"))
    robustness_rows = _read_optional_jsonl(artifact_paths.get("robustness_rows"))
    audit_profile = manifest.get("audit_profile") or {}
    required_lineage = set(audit_profile.get("required_lineage_fields") or ["trade_id", "execution_id", "candidate_id", "event_id"])
    required_time = set(audit_profile.get("required_time_fields") or [])

    schema_rows = []
    schema_rows.extend(
        build_schema_contract_rows(
            artifact_name="candidate_rows.jsonl",
            rows=candidate_rows,
            inferred_row_type="proposal_candidate",
            required_fields={"candidate_id", "event_id", "row_type"},
            blocking_missing_row_type=False,
        )
    )
    schema_rows.extend(
        build_schema_contract_rows(
            artifact_name="closed_trade_rows.jsonl",
            rows=closed_rows,
            inferred_row_type="closed_trade",
            required_fields=required_lineage | required_time | {"row_type", "closed_trade", "net_R", "mfe_R", "mae_R", "cost_tier"},
            blocking_missing_row_type=False,
        )
    )
    schema_rows.extend(
        build_schema_contract_rows(
            artifact_name="summary_rows.jsonl",
            rows=summary_rows,
            inferred_row_type="summary_row",
            required_fields={"row_type", "cost_tier", "closed_trades", "net_R_avg", "total_net_R"},
            blocking_missing_row_type=False,
        )
    )

    lineage_rows = _generic_lineage_rows(closed_rows=closed_rows, candidate_rows=candidate_rows, filter_rows=filter_rows)
    join_rows = _generic_join_integrity_rows(closed_rows=closed_rows, candidate_rows=candidate_rows, filter_rows=filter_rows)
    proposal_rows = _generic_proposal_boundary_rows(
        closed_rows=closed_rows,
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        diagnostic_rows=diagnostic_rows,
        summary_rows=summary_rows,
        robustness_rows=robustness_rows,
    )
    no_lookahead_rows = build_no_lookahead_rows(
        closed_rows,
        time_field_checks=audit_profile.get("time_order_checks"),
    )
    metric_rows = []
    for summary in summary_rows:
        cost_tier = str(summary.get("cost_tier") or "base")
        tier_closed = [row for row in closed_rows if str(row.get("cost_tier") or "base") == cost_tier]
        metric_rows.extend(
            comparison_rows(
                scope=str(summary.get("scope") or strategy),
                cost_tier=cost_tier,
                reported=summary,
                recomputed=recompute_metrics(tier_closed),
                source_artifact=str(artifact_paths.get("closed_trade_rows", "")),
            )
        )
    artifact_rows = build_artifact_integrity_rows(artifact_dir, registry=registry)
    report_rows = build_report_consistency_rows(artifact_dir)
    code_rows = build_code_logic_review_rows(Path.cwd())
    regression_rows = _regression_baseline_rows(artifact_paths)
    robustness_gate_rows = _robustness_gate_rows(robustness_rows)

    blocking_issues = _blocking_issues(
        join_rows=join_rows,
        proposal_rows=proposal_rows + regression_rows + robustness_gate_rows,
        no_lookahead_rows=no_lookahead_rows,
        metric_rows=metric_rows,
        artifact_rows=artifact_rows,
        code_rows=code_rows,
        lineage_repair_result=None,
    )
    warnings = _warnings(schema_rows, join_rows, no_lookahead_rows, artifact_rows, report_rows, code_rows)
    primary_decision = _primary_decision(blocking_issues)
    result = FullPipelineAuditResult(
        strategy=strategy,
        proposal_only=bool(manifest.get("proposal_only", True)),
        formal_conclusion_enabled=bool(manifest.get("formal_conclusion_enabled", False)),
        audit_passed=primary_decision in {"A", "B"},
        primary_decision=primary_decision,
        blocking_issues=blocking_issues,
        non_blocking_warnings=warnings,
        next_pr_recommendation="strategy research validation review" if primary_decision in {"A", "B"} else "manifest/audit input fix",
        schema_contract_rows=schema_rows,
        lineage_rows=lineage_rows,
        join_integrity_rows=join_rows,
        proposal_boundary_rows=proposal_rows + regression_rows + robustness_gate_rows,
        no_lookahead_rows=no_lookahead_rows,
        metric_recompute_rows=metric_rows,
        report_consistency_rows=report_rows,
        artifact_integrity_rows=artifact_rows,
        code_logic_review_rows=code_rows,
        source_files=[str(manifest_path), *[str(path) for path in artifact_paths.values()]],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _resolve_artifact_path(artifact_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    cwd_relative = path.resolve()
    if cwd_relative.exists():
        return cwd_relative
    return (artifact_dir / path).resolve()


def _read_optional_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    return _read_jsonl(path)


def _generic_lineage_rows(
    *,
    closed_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    filter_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = {row.get("candidate_id") for row in candidate_rows}
    filters = {row.get("candidate_id") for row in filter_rows}
    return [
        {
            "scope": "closed_trade_lineage",
            "closed_count": len(closed_rows),
            "candidate_linked_count": sum(1 for row in closed_rows if row.get("candidate_id") in candidates),
            "filter_linked_count": sum(1 for row in closed_rows if row.get("candidate_id") in filters),
            "missing_trade_id_count": sum(1 for row in closed_rows if not row.get("trade_id")),
            "missing_execution_id_count": sum(1 for row in closed_rows if not row.get("execution_id")),
            "missing_event_id_count": sum(1 for row in closed_rows if not row.get("event_id")),
        }
    ]


def _generic_join_integrity_rows(
    *,
    closed_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    filter_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = {row.get("candidate_id") for row in candidate_rows}
    filters = {row.get("candidate_id") for row in filter_rows}
    missing_candidate = sum(1 for row in closed_rows if row.get("candidate_id") not in candidates)
    missing_filter = sum(1 for row in closed_rows if row.get("candidate_id") not in filters)
    missing_trade = sum(1 for row in closed_rows if not row.get("trade_id"))
    missing_execution = sum(1 for row in closed_rows if not row.get("execution_id"))
    return [
        {
            "scope": "manifest_closed_trades",
            "selected_count": len(filter_rows),
            "executed_count": len(closed_rows),
            "closed_count": len(closed_rows),
            "selected_without_closed_count": max(0, len([row for row in filter_rows if row.get("formal_approved")]) - len(closed_rows)),
            "missing_trade_id_count": missing_trade,
            "missing_execution_id_count": missing_execution,
            "missing_execution_row_count": missing_candidate + missing_filter,
            "join_key_mismatch_count": missing_candidate + missing_filter,
            "proposal_only_unexecuted_count": 0,
            "diagnostic_only_count": len([row for row in filter_rows if not row.get("formal_approved")]),
            "invalid_for_robustness_count": sum(1 for row in closed_rows if row.get("invalid_for_robustness")),
            "performance_includes_unclosed_rows": False,
            "fix_required": bool(missing_trade or missing_execution or missing_candidate or missing_filter),
            "notes": "manifest-driven closed trades trace to candidate/filter rows",
        }
    ]


def _generic_proposal_boundary_rows(
    *,
    closed_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    filter_rows: list[dict[str, Any]],
    diagnostic_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    robustness_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    non_closed = [*candidate_rows, *filter_rows, *diagnostic_rows, *summary_rows, *robustness_rows]
    bad_non_closed = [
        row
        for row in non_closed
        if row.get("row_type") != "closed_trade"
        and (row.get("eligible_for_performance") is True or row.get("closed_trade") is True)
    ]
    bad_closed = [row for row in closed_rows if row.get("row_type") != "closed_trade" or not row.get("closed_trade")]
    summary_with_net = [row for row in summary_rows if row.get("net_R") is not None]
    return [
        _audit_row("performance_metrics_from_closed_trade_only", not bad_closed, len(bad_closed), "closed_trade_rows must contain only closed_trade rows"),
        _audit_row("proposal_diagnostic_summary_rows_excluded", not bad_non_closed, len(bad_non_closed), "non-closed artifacts are not eligible for performance"),
        _audit_row("summary_rows_do_not_contain_trade_pnl", not summary_with_net, len(summary_with_net), "summary rows can report aggregates but not row-level net_R"),
    ]


def _regression_baseline_rows(artifact_paths: dict[str, Path]) -> list[dict[str, Any]]:
    path = artifact_paths.get("regression_baseline")
    passed = bool(path and path.exists())
    return [_audit_row("regression_baseline_present", passed, 0 if passed else 1, "regression baseline artifact is required")]


def _robustness_gate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    robustness_types = {row.get("robustness_type") for row in rows}
    required = {"walk_forward", "regime_split", "exposure"}
    missing = sorted(required - robustness_types)
    return [_audit_row("robustness_exposure_restriction_present", not missing, len(missing), f"missing robustness types: {missing}")]


def _audit_row(check_name: str, passed: bool, affected_rows: int, details: str) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "passed": passed,
        "affected_rows": affected_rows,
        "blocking": not passed,
        "details": details,
    }


def _join_integrity_rows(
    fix_result: dict[str, Any],
    variant_rows: list[dict[str, Any]],
    selected_base_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping = fix_result.get("mapping_diagnostics", {})
    rows = [
        {
            "scope": mapping.get("combo_name"),
            "selected_count": mapping.get("selected_without_closed_count"),
            "executed_count": 0,
            "closed_count": 0,
            "selected_without_closed_count": mapping.get("selected_without_closed_count"),
            "missing_trade_id_count": mapping.get("missing_trade_id_count"),
            "missing_execution_id_count": mapping.get("missing_execution_row_count"),
            "missing_execution_row_count": mapping.get("missing_execution_row_count"),
            "join_key_mismatch_count": mapping.get("join_key_mismatch_count"),
            "proposal_only_unexecuted_count": mapping.get("proposal_only_unexecuted_count"),
            "diagnostic_only_count": mapping.get("selected_without_closed_count"),
            "invalid_for_robustness_count": mapping.get("selected_without_closed_count"),
            "performance_includes_unclosed_rows": False,
            "fix_required": False,
            "notes": mapping.get("fix_applied"),
        }
    ]
    for row in variant_rows:
        if row.get("tier") != "ALL" or row.get("cost_tier") != "base":
            continue
        selected_without_closed = int(row.get("selected_without_closed_count") or 0)
        proposal_only_unexecuted = int(row.get("proposal_only_unexecuted_count") or 0)
        closed = int(row.get("closed_trades") or 0)
        closed_rows = _closed_trade_rows(selected_base_rows)
        if row.get("variant_name") == VARIANT_B:
            missing_trade_id = sum(1 for item in closed_rows if not item.get("trade_id"))
            missing_execution_id = sum(1 for item in closed_rows if not item.get("execution_id"))
            invalid_for_robustness = sum(
                1 for item in closed_rows if not item.get("trade_id") or not item.get("execution_id")
            )
            fix_required = bool(closed and (missing_trade_id or missing_execution_id))
            notes = "recommended robustness rows have execution identity" if not fix_required else "recommended robustness rows lack trade_id/execution_id lineage"
        else:
            missing_trade_id = 0
            missing_execution_id = 0
            invalid_for_robustness = 0
            fix_required = False
            notes = "non-recommended variant summary; not used as robustness input"
        rows.append(
            {
                "scope": row.get("variant_name"),
                "selected_count": int(row.get("selected_trades") or 0) + selected_without_closed,
                "executed_count": closed,
                "closed_count": closed,
                "selected_without_closed_count": selected_without_closed,
                "missing_trade_id_count": missing_trade_id,
                "missing_execution_id_count": missing_execution_id,
                "missing_execution_row_count": 0,
                "join_key_mismatch_count": 0,
                "proposal_only_unexecuted_count": proposal_only_unexecuted,
                "diagnostic_only_count": proposal_only_unexecuted,
                "invalid_for_robustness_count": invalid_for_robustness,
                "performance_includes_unclosed_rows": False,
                "fix_required": fix_required,
                "notes": notes,
            }
        )
    return rows


def _closed_trade_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any("row_type" in row for row in rows):
        return [row for row in rows if row.get("row_type") == "closed_trade" and row.get("closed_trade")]
    return [row for row in rows if row.get("closed_trade")]


def _combo_schema_rows(combo_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    closed = [row for row in combo_rows if row.get("closed_trade")]
    unclosed = [row for row in combo_rows if not row.get("closed_trade")]
    rows.extend(
        build_schema_contract_rows(
            artifact_name="lr_combined_combo_rows.jsonl",
            rows=closed,
            inferred_row_type="closed_trade",
            required_fields={"candidate_id", "event_key", "closed_trade", "net_R", "mfe_R", "mae_R", "exit_reason"},
            blocking_missing_row_type=False,
        )
    )
    rows.extend(
        build_schema_contract_rows(
            artifact_name="lr_combined_combo_rows.jsonl",
            rows=unclosed,
            inferred_row_type="proposal_candidate",
            required_fields={"candidate_id", "event_key", "proposal_only", "sizing_policy"},
            blocking_missing_row_type=False,
        )
    )
    return rows


def _blocking_issues(
    *,
    join_rows: list[dict[str, Any]],
    proposal_rows: list[dict[str, Any]],
    no_lookahead_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    code_rows: list[dict[str, Any]],
    lineage_repair_result: dict[str, Any] | None = None,
) -> list[str]:
    issues = []
    if lineage_repair_result:
        if lineage_repair_result.get("closed_missing_trade_id_count") or lineage_repair_result.get(
            "closed_missing_execution_id_count"
        ):
            issues.append(
                "Execution identity missing after lineage repair: "
                f"closed_missing_trade_id_count={lineage_repair_result.get('closed_missing_trade_id_count')} "
                f"closed_missing_execution_id_count={lineage_repair_result.get('closed_missing_execution_id_count')}"
            )
        if lineage_repair_result.get("robustness_input_count") == 0:
            issues.append("Execution identity / lineage repair produced zero eligible robustness rows.")
    issues.extend(
        f"Execution identity missing for {row['scope']}: missing_trade_id_count={row['missing_trade_id_count']} missing_execution_id_count={row['missing_execution_id_count']}"
        for row in join_rows
        if row.get("fix_required")
    )
    issues.extend(
        f"Proposal boundary failed: {row['check_name']}"
        for row in proposal_rows
        if row.get("blocking")
    )
    issues.extend(
        f"No-lookahead unverifiable: {row['check_name']} ({row['details']})"
        for row in no_lookahead_rows
        if row.get("blocking")
    )
    issues.extend(
        f"Metric mismatch: {row['scope']} {row['cost_tier']} {row['metric_name']}"
        for row in metric_rows
        if not row.get("passed")
    )
    issues.extend(
        f"Artifact integrity failed: {row['artifact_name']}"
        for row in artifact_rows
        if row.get("blocking")
    )
    issues.extend(
        f"High severity code logic risk: {row['risk_type']} in {row['risky_file']}"
        for row in code_rows
        if row.get("severity") == "high" and row.get("fix_required")
    )
    return issues


def _warnings(
    schema_rows: list[dict[str, Any]],
    join_rows: list[dict[str, Any]],
    no_lookahead_rows: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
    code_rows: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    warnings.extend(
        f"Schema missing fields in {row['artifact_name']} row_type={row['row_type']}: {row['missing_fields']}"
        for row in schema_rows
        if row.get("missing_fields")
    )
    warnings.extend(
        f"{row['scope']} has selected_without_closed={row['selected_without_closed_count']}; excluded from performance."
        for row in join_rows
        if (row.get("selected_without_closed_count") or 0) > 0
    )
    warnings.extend(
        f"No-lookahead check unavailable: {row['check_name']}"
        for row in no_lookahead_rows
        if not row.get("passed")
    )
    warnings.extend(
        f"Artifact metadata incomplete: {row['artifact_name']}"
        for row in artifact_rows
        if not row.get("blocking")
        and (
            row.get("config_hash_present") is False
            or row.get("adapter_version_present") is False
        )
    )
    warnings.extend(
        f"Report scope unavailable: {row['report_type']}"
        for row in report_rows
        if not row.get("exists")
    )
    warnings.extend(
        f"Code review risk {row['severity']}: {row['risk_type']} in {row['risky_file']}"
        for row in code_rows
        if row.get("severity") not in {"none", "low"}
    )
    return warnings


def _primary_decision(blocking_issues: list[str]) -> str:
    if not blocking_issues:
        return "B"
    if any("Execution identity" in issue for issue in blocking_issues):
        return "C"
    if any("No-lookahead" in issue for issue in blocking_issues):
        return "D"
    if any("Proposal boundary" in issue for issue in blocking_issues):
        return "E"
    if any("code logic" in issue.lower() for issue in blocking_issues):
        return "F"
    return "C"


def _write_outputs(result: FullPipelineAuditResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "full_pipeline_audit_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "full_pipeline_audit_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "audit_schema_contract_rows.jsonl", result.schema_contract_rows)
    _write_jsonl(output_dir / "audit_lineage_rows.jsonl", result.lineage_rows)
    _write_jsonl(output_dir / "audit_join_integrity_rows.jsonl", result.join_integrity_rows)
    _write_jsonl(output_dir / "audit_proposal_boundary_rows.jsonl", result.proposal_boundary_rows)
    _write_jsonl(output_dir / "audit_no_lookahead_rows.jsonl", result.no_lookahead_rows)
    _write_jsonl(output_dir / "audit_metric_recompute_rows.jsonl", result.metric_recompute_rows)
    _write_jsonl(output_dir / "audit_report_consistency_rows.jsonl", result.report_consistency_rows)
    _write_jsonl(output_dir / "audit_artifact_integrity_rows.jsonl", result.artifact_integrity_rows)
    _write_jsonl(output_dir / "audit_code_logic_review_rows.jsonl", result.code_logic_review_rows)
    index = build_index_for_directory(
        output_dir,
        strategy=result.strategy,
        stage="full_pipeline_audit",
        window="10000w",
        source_command="research_pipeline.cli.research full-audit",
        notes="Reusable full research pipeline audit gate; no strategy execution.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=result.strategy,
        stage="full_pipeline_audit",
        window="10000w",
        source_command="research_pipeline.cli.research full-audit",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=True,
        notes="Full audit gate output; no formal strategy config change.",
        tags=["PR11G-QA-fix", "full_audit", "proposal_boundary"],
    )


def _report(result: FullPipelineAuditResult) -> str:
    lines = [
        "# Reusable Research Pipeline Full Audit Gate Report",
        "",
        f"- strategy = {result.strategy}",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        f"- audit_passed = {str(result.audit_passed).lower()}",
        "",
        "## Gate Summary",
        f"- schema_contract_rows = {len(result.schema_contract_rows)}",
        f"- lineage_rows = {len(result.lineage_rows)}",
        f"- join_integrity_rows = {len(result.join_integrity_rows)}",
        f"- proposal_boundary_rows = {len(result.proposal_boundary_rows)}",
        f"- no_lookahead_rows = {len(result.no_lookahead_rows)}",
        f"- metric_recompute_rows = {len(result.metric_recompute_rows)}",
        f"- report_consistency_rows = {len(result.report_consistency_rows)}",
        f"- artifact_integrity_rows = {len(result.artifact_integrity_rows)}",
        f"- code_logic_review_rows = {len(result.code_logic_review_rows)}",
        "",
        "## Primary Decision",
        f"{result.primary_decision}. {_decision_text(result.primary_decision)}",
        "",
        "## Blocking Issues",
    ]
    lines.extend(f"- {issue}" for issue in result.blocking_issues) if result.blocking_issues else lines.append("- None")
    lines.append("")
    lines.append("## Non-blocking Warnings")
    lines.extend(f"- {warning}" for warning in result.non_blocking_warnings[:40]) if result.non_blocking_warnings else lines.append("- None")
    if len(result.non_blocking_warnings) > 40:
        lines.append(f"- ... {len(result.non_blocking_warnings) - 40} more warnings in JSON result")
    lines.extend(["", "## Next PR Recommendation", f"- {result.next_pr_recommendation}"])
    return "\n".join(lines) + "\n"


def _decision_text(decision: str) -> str:
    return {
        "A": "Full pipeline audit passed; eligible for the next robustness review.",
        "B": "Audit passed with non-blocking warnings; carry warnings into the next review.",
        "C": "Audit failed due to execution identity / lineage.",
        "D": "Audit failed due to unverifiable no-lookahead rows.",
        "E": "Audit failed because proposal/diagnostic rows entered performance.",
        "F": "Audit failed due to pipeline-wide code logic risks.",
    }[decision]

def _combo_rows_path(artifact_dir: Path) -> Path:
    local = artifact_dir / "lr_combined_combo_rows.jsonl"
    if local.exists():
        return local
    sibling = artifact_dir.parent / "lr_combined_pr11g" / "lr_combined_combo_rows.jsonl"
    if sibling.exists():
        return sibling
    raise FileNotFoundError("lr_combined_combo_rows.jsonl not found")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
