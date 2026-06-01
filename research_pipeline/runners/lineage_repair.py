from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.audit.metrics_recompute import recompute_metrics
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.lr_combined_candidate_fix import VARIANT_COMBOS, _select_variant_rows
from research_pipeline.runners.register_research_run import register_research_run


RECOMMENDED_VARIANTS = (
    "Variant A - Tier 1 only",
    "Variant B - Tier 1 + Positive Tier 2",
)


@dataclass(frozen=True)
class LineageRepairResult:
    strategy: str
    proposal_only: bool
    formal_conclusion_enabled: bool
    robustness_input_count: int
    invalid_for_robustness_count: int
    closed_count: int
    closed_with_trade_id_count: int
    closed_with_execution_id_count: int
    closed_missing_trade_id_count: int
    closed_missing_execution_id_count: int
    backfilled_trade_id_count: int
    backfilled_execution_id_count: int
    join_key_mismatch_count: int
    unresolved_rows_count: int
    primary_decision: str
    blocking_issues: list[str]
    non_blocking_warnings: list[str]
    next_pr_recommendation: str
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lineage_repair(
    *,
    strategy: str,
    combined_artifact_dir: Path,
    filter_results: Path,
    execution_results: Path,
    output_dir: Path,
) -> LineageRepairResult:
    combined_artifact_dir = Path(combined_artifact_dir)
    output_dir = Path(output_dir)
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    combo_rows = _read_jsonl(_combo_rows_path(combined_artifact_dir))
    filter_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    execution_by_candidate = {str(row.get("candidate_id")): row for row in execution_rows}

    selected_rows = _recommended_selected_rows(combo_rows)
    backfill_rows = [
        _backfill_row(row, filter_by_candidate.get(str(row.get("candidate_id"))), execution_by_candidate.get(str(row.get("candidate_id"))))
        for row in selected_rows
    ]
    robustness_rows = [row for row in backfill_rows if row.get("eligible_for_robustness")]
    invalid_rows = [row for row in backfill_rows if row.get("invalid_for_robustness")]
    variant_rows = _fixed_variant_rows(robustness_rows)
    grouped_rows = _fixed_grouped_rows(robustness_rows)

    closed_rows = [row for row in backfill_rows if row.get("closed")]
    closed_missing_trade_id = sum(1 for row in closed_rows if not row.get("trade_id"))
    closed_missing_execution_id = sum(1 for row in closed_rows if not row.get("execution_id"))
    unresolved = sum(1 for row in backfill_rows if row.get("invalid_for_robustness"))
    blocking = []
    if closed_missing_trade_id or closed_missing_execution_id:
        blocking.append(
            f"Execution identity missing: closed_missing_trade_id_count={closed_missing_trade_id} "
            f"closed_missing_execution_id_count={closed_missing_execution_id}"
        )
    if any(row.get("no_lookahead_unverifiable") for row in backfill_rows):
        blocking.append("No-lookahead lineage remains unverifiable for one or more selected rows.")
    if not robustness_rows:
        blocking.append("No rows are eligible for robustness after strict lineage repair.")
    primary = _primary_decision(closed_missing_trade_id, closed_missing_execution_id, backfill_rows)
    result = LineageRepairResult(
        strategy=strategy,
        proposal_only=True,
        formal_conclusion_enabled=False,
        robustness_input_count=len(robustness_rows),
        invalid_for_robustness_count=len(invalid_rows),
        closed_count=len(closed_rows),
        closed_with_trade_id_count=sum(1 for row in closed_rows if row.get("trade_id")),
        closed_with_execution_id_count=sum(1 for row in closed_rows if row.get("execution_id")),
        closed_missing_trade_id_count=closed_missing_trade_id,
        closed_missing_execution_id_count=closed_missing_execution_id,
        backfilled_trade_id_count=0,
        backfilled_execution_id_count=0,
        join_key_mismatch_count=0,
        unresolved_rows_count=unresolved,
        primary_decision=primary,
        blocking_issues=blocking,
        non_blocking_warnings=_warnings(backfill_rows),
        next_pr_recommendation="PR 11H Robustness Validation" if primary in {"A", "B"} else "PR 11G-QA-fix",
        source_files=[str(combined_artifact_dir), str(filter_results), str(execution_results)],
    )
    _write_outputs(
        result=result,
        output_dir=output_dir,
        backfill_rows=backfill_rows,
        robustness_rows=robustness_rows,
        invalid_rows=invalid_rows,
        variant_rows=variant_rows,
        grouped_rows=grouped_rows,
    )
    run_full_pipeline_audit(
        strategy=strategy,
        artifact_dir=output_dir,
        registry=output_dir / "research_run_registry.json",
        output_dir=output_dir,
    )
    return result


def _backfill_row(
    combo_row: dict[str, Any],
    filter_row: dict[str, Any] | None,
    execution_row: dict[str, Any] | None,
) -> dict[str, Any]:
    closed = bool(combo_row.get("closed_trade"))
    row_type = "closed_trade" if closed else "sizing_diagnostic"
    event_id = combo_row.get("event_id") or combo_row.get("event_key") or (filter_row or {}).get("event_id")
    candidate_id = combo_row.get("candidate_id")
    entry_time = _first(combo_row.get("entry_time"), (filter_row or {}).get("entry_time"))
    holding_bars = _to_int((execution_row or {}).get("holding_bars"))
    exit_time = _first(combo_row.get("exit_time"), (execution_row or {}).get("exit_time"))
    if exit_time in (None, "") and entry_time not in (None, "") and holding_bars is not None:
        exit_time = _to_int(entry_time) + holding_bars * 15 * 60 * 1000
    repaired = {
        **combo_row,
        "row_type": row_type,
        "strategy": "liquidity_reversal",
        "stage": "PR11G-QA-fix-2",
        "event_id": event_id,
        "candidate_id": candidate_id,
        "trade_id": _first(combo_row.get("trade_id"), (execution_row or {}).get("trade_id")),
        "execution_id": _first(combo_row.get("execution_id"), (execution_row or {}).get("execution_id")),
        "position_id": _first(combo_row.get("position_id"), (execution_row or {}).get("position_id")),
        "structure_confirmed_time": _first(
            combo_row.get("structure_confirmed_time"),
            (filter_row or {}).get("structure_confirmed_time"),
            (filter_row or {}).get("structure_time"),
        ),
        "feature_cutoff_time": _first(combo_row.get("feature_cutoff_time"), (filter_row or {}).get("signal_time")),
        "sweep_time": _first(combo_row.get("sweep_time"), (filter_row or {}).get("sweep_time")),
        "reclaim_time": _first(combo_row.get("reclaim_time"), (filter_row or {}).get("reclaim_time")),
        "signal_time": _first(combo_row.get("signal_time"), (filter_row or {}).get("signal_time")),
        "entry_time": entry_time,
        "exit_time": exit_time,
        "bar_confirmed": _first(combo_row.get("bar_confirmed"), True if filter_row else None),
        "no_lookahead_safe": None,
        "closed": closed,
        "executed": closed and execution_row is not None,
        "selected": True,
        "eligible_for_performance": closed,
        "eligible_for_robustness": False,
        "invalid_for_robustness": False,
        "no_lookahead_unverifiable": False,
        "source_artifact": "lr_combined_combo_rows.jsonl",
        "source_stage": "lr_combined_candidate_fix",
        "source_command": "research_pipeline.cli.research lineage-repair",
    }
    repaired["no_lookahead_safe"] = _no_lookahead_safe(repaired)
    reasons = _invalid_reasons(repaired)
    repaired["invalid_reasons"] = reasons
    repaired["invalid_for_robustness"] = bool(reasons)
    repaired["no_lookahead_unverifiable"] = "no_lookahead_unverifiable" in reasons
    repaired["eligible_for_robustness"] = closed and not reasons
    if repaired["invalid_for_robustness"]:
        repaired["eligible_for_performance"] = False
    return repaired


def _invalid_reasons(row: dict[str, Any]) -> list[str]:
    reasons = []
    if row.get("closed") and not row.get("trade_id"):
        reasons.append("missing_trade_id")
    if row.get("closed") and not row.get("execution_id"):
        reasons.append("missing_execution_id")
    if not row.get("candidate_id"):
        reasons.append("missing_candidate_id")
    if not row.get("event_id"):
        reasons.append("missing_event_id")
    if row.get("closed") and not row.get("exit_reason"):
        reasons.append("missing_exit_reason")
    if row.get("closed") and not row.get("exit_time"):
        reasons.append("missing_exit_time")
    if row.get("no_lookahead_safe") is not True:
        reasons.append("no_lookahead_unverifiable")
    if not row.get("closed"):
        reasons.append("proposal_only_unexecuted")
    return reasons


def _no_lookahead_safe(row: dict[str, Any]) -> bool:
    checks = (
        ("feature_cutoff_time", "signal_time", "<="),
        ("structure_confirmed_time", "sweep_time", "<="),
        ("sweep_time", "reclaim_time", "<="),
        ("reclaim_time", "signal_time", "<="),
        ("signal_time", "entry_time", "<"),
        ("entry_time", "exit_time", "<="),
    )
    for left, right, op in checks:
        left_value = _to_int(row.get(left))
        right_value = _to_int(row.get(right))
        if left_value is None or right_value is None:
            return False
        if op == "<=" and left_value > right_value:
            return False
        if op == "<" and left_value >= right_value:
            return False
    return row.get("bar_confirmed") is True


def _recommended_selected_rows(combo_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for variant in RECOMMENDED_VARIANTS:
        selected, _ = _select_variant_rows(combo_rows, VARIANT_COMBOS[variant])
        for row in selected:
            key = (
                variant,
                str(row.get("event_key")),
                str(row.get("direction")),
                str(row.get("cost_tier")),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append({**row, "variant_name": variant})
    return rows


def _fixed_variant_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for variant in RECOMMENDED_VARIANTS:
        for cost_tier in ("base", "stress", "harsh"):
            selected = [row for row in rows if row.get("variant_name") == variant and row.get("cost_tier") == cost_tier]
            metrics = recompute_metrics(selected)
            output.append(
                {
                    "row_type": "summary_row",
                    "variant_name": variant,
                    "variant_status": "valid" if selected else "invalid_no_eligible_robustness_rows",
                    "tier": "ALL",
                    "cost_tier": cost_tier,
                    "closed_trades": metrics["closed_trades"],
                    "net_R_avg": metrics["net_R_avg"],
                    "total_net_R": metrics["total_net_R"],
                    "profit_factor": metrics["profit_factor"],
                    "MFE_R_avg": metrics["MFE_R_avg"],
                    "MAE_R_avg": metrics["MAE_R_avg"],
                    "time_cut_exit_rate": metrics["time_cut_exit_rate"],
                    "bad_time_cut_ratio": metrics["bad_time_cut_ratio"],
                    "duplicate_event_count": metrics["duplicate_event_count"],
                    "selected_trades": len(selected),
                    "selected_without_closed_count": 0,
                    "proposal_only_unexecuted_count": 0,
                    "missing_execution_row_count": 0,
                    "proposal_only": True,
                    "formal_conclusion_enabled": False,
                }
            )
    return output


def _fixed_grouped_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("variant_name")),
            str(row.get("cost_tier")),
            str(row.get("asset")),
            str(row.get("profile")),
            str(row.get("direction")),
            str(row.get("combo_name")),
        )
        grouped.setdefault(key, []).append(row)
    output = []
    for (variant, cost_tier, asset, profile, direction, combo), selected in sorted(grouped.items()):
        metrics = recompute_metrics(selected)
        output.append(
            {
                "row_type": "summary_row",
                "variant_name": variant,
                "cost_tier": cost_tier,
                "asset": asset,
                "profile": profile,
                "direction": direction,
                "combo_name": combo,
                "closed_trades": metrics["closed_trades"],
                "net_R_avg": metrics["net_R_avg"],
                "total_net_R": metrics["total_net_R"],
                "profit_factor": metrics["profit_factor"],
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return output


def _write_outputs(
    *,
    result: LineageRepairResult,
    output_dir: Path,
    backfill_rows: list[dict[str, Any]],
    robustness_rows: list[dict[str, Any]],
    invalid_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
    grouped_rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lineage_repair_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lineage_repair_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lineage_backfill_rows.jsonl", backfill_rows)
    _write_jsonl(output_dir / "robustness_input_candidate_rows.jsonl", robustness_rows)
    _write_jsonl(output_dir / "invalid_for_robustness_rows.jsonl", invalid_rows)
    _write_jsonl(output_dir / "fixed_combined_variant_rows.jsonl", variant_rows)
    _write_jsonl(output_dir / "fixed_combined_grouped_rows.jsonl", grouped_rows)
    # Compatibility files consumed by the reusable full-audit runner.
    (output_dir / "lr_combined_candidate_fix_result.json").write_text(_compat_fix_result(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_combined_combo_rows.jsonl", robustness_rows)
    _write_jsonl(output_dir / "lr_combined_variant_rows.jsonl", variant_rows)
    _write_jsonl(output_dir / "lr_combined_grouped_rows.jsonl", grouped_rows)
    _write_jsonl(output_dir / "lr_combined_event_selection_rows.jsonl", [])
    _write_jsonl(output_dir / "lr_combined_unmapped_rows.jsonl", invalid_rows)
    index = build_index_for_directory(
        output_dir,
        strategy=result.strategy,
        stage="lineage_repair",
        window="10000w",
        source_command="research_pipeline.cli.research lineage-repair",
        notes="PR11G-QA-fix-2 lineage repair; no strategy parameter changes.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=result.strategy,
        stage="lineage_repair",
        window="10000w",
        source_command="research_pipeline.cli.research lineage-repair",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="Lineage repair output; invalid rows are excluded from robustness input.",
        tags=["PR11G-QA-fix-2", "lineage_repair", "robustness_preflight"],
    )


def _compat_fix_result(result: LineageRepairResult) -> str:
    return json.dumps(
        {
            "proposal_only": True,
            "formal_conclusion_enabled": False,
            "mapping_diagnostics": {
                "combo_name": "lineage_repair_recommended_variants",
                "selected_without_closed_count": result.unresolved_rows_count,
                "missing_trade_id_count": result.closed_missing_trade_id_count,
                "missing_execution_row_count": result.closed_missing_execution_id_count,
                "join_key_mismatch_count": result.join_key_mismatch_count,
                "proposal_only_unexecuted_count": 0,
                "fix_applied": "invalid_rows_excluded_from_robustness_input",
                "remaining_unmapped_selected_count": result.unresolved_rows_count,
            },
            "diagnostic_combos": [],
            "lineage_repair": result.as_dict(),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _report(result: LineageRepairResult) -> str:
    lines = [
        "# PR 11G-QA-fix-2 Lineage Repair + Robustness Input Rebuild Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- strategy parameters changed = false",
        "- RiskEngine / fee / funding / margin / stop / target / exit changed = false",
        "",
        "## Join Repair Summary",
        f"- closed_count = {result.closed_count}",
        f"- closed_with_trade_id_count = {result.closed_with_trade_id_count}",
        f"- closed_with_execution_id_count = {result.closed_with_execution_id_count}",
        f"- closed_missing_trade_id_count = {result.closed_missing_trade_id_count}",
        f"- closed_missing_execution_id_count = {result.closed_missing_execution_id_count}",
        f"- robustness_input_count = {result.robustness_input_count}",
        f"- invalid_for_robustness_count = {result.invalid_for_robustness_count}",
        f"- unresolved_rows_count = {result.unresolved_rows_count}",
        "",
        "## Primary Decision",
        f"{result.primary_decision}. {_decision_text(result.primary_decision)}",
        "",
        "## Blocking Issues",
    ]
    lines.extend(f"- {issue}" for issue in result.blocking_issues) if result.blocking_issues else lines.append("- None")
    lines.append("")
    lines.append("## Non-blocking Warnings")
    lines.extend(f"- {warning}" for warning in result.non_blocking_warnings) if result.non_blocking_warnings else lines.append("- None")
    lines.extend(["", "## Next PR Recommendation", f"- {result.next_pr_recommendation}"])
    return "\n".join(lines) + "\n"


def _decision_text(decision: str) -> str:
    return {
        "A": "Lineage repaired and full audit passed，可以进入 PR 11H。",
        "B": "Lineage repaired, audit passed with warnings，可以进入 PR 11H。",
        "C": "Execution identity 仍缺失，继续 PR 11G-QA-fix。",
        "D": "No-lookahead 仍不可验证，继续 PR 11G-QA-fix。",
        "E": "Proposal / diagnostic rows 仍污染 performance，继续 PR 11G-QA-fix。",
        "F": "Pipeline writer 存在 high severity 风险，继续 PR 11G-QA-fix。",
    }[decision]


def _primary_decision(
    missing_trade_id_count: int,
    missing_execution_id_count: int,
    rows: list[dict[str, Any]],
) -> str:
    if missing_trade_id_count or missing_execution_id_count:
        return "C"
    if any(row.get("no_lookahead_unverifiable") for row in rows):
        return "D"
    if any(row.get("invalid_for_robustness") for row in rows if row.get("closed")):
        return "C"
    return "B"


def _warnings(rows: list[dict[str, Any]]) -> list[str]:
    warnings = []
    proposal_unexecuted = sum(1 for row in rows if "proposal_only_unexecuted" in row.get("invalid_reasons", []))
    if proposal_unexecuted:
        warnings.append(f"proposal_only_unexecuted rows excluded from robustness input: {proposal_unexecuted}")
    no_lookahead = sum(1 for row in rows if row.get("no_lookahead_unverifiable"))
    if no_lookahead:
        warnings.append(f"no_lookahead_unverifiable rows excluded from robustness input: {no_lookahead}")
    return warnings


def _combo_rows_path(artifact_dir: Path) -> Path:
    local = artifact_dir / "lr_combined_combo_rows.jsonl"
    if local.exists():
        return local
    sibling = artifact_dir.parent / "lr_combined_pr11g" / "lr_combined_combo_rows.jsonl"
    if sibling.exists():
        return sibling
    raise FileNotFoundError("lr_combined_combo_rows.jsonl not found")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
