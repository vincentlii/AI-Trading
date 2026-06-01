from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run


IDENTITY_FIELDS = ("trade_id", "execution_id", "position_id")
TIME_FIELDS = (
    "feature_cutoff_time",
    "structure_confirmed_time",
    "structure_time",
    "sweep_time",
    "reclaim_time",
    "signal_time",
    "entry_time",
    "exit_time",
    "entry_timestamp_ms",
    "exit_timestamp_ms",
    "bar_confirmed",
    "no_lookahead_safe",
)
JOIN_FIELDS = ("candidate_id", "event_id", "event_key", "proposal_id", "formal_id")
ROW_TYPE_FIELDS = (
    "row_type",
    "closed_trade",
    "formal_approved",
    "proposal_approved",
    "proposal_only",
    "diagnostic_only",
    "selected",
    "eligible_for_performance",
    "eligible_for_robustness",
    "invalid_for_robustness",
)
PERFORMANCE_FIELDS = (
    "net_R",
    "net_r",
    "gross_R",
    "MFE_R",
    "mfe_R",
    "MAE_R",
    "mae_R",
    "exit_reason",
    "fee_cost",
    "slippage_cost",
    "funding_cost",
    "same_bar_ambiguous",
    "liquidation_event",
)
FIELDS_TO_SCAN = tuple(dict.fromkeys(IDENTITY_FIELDS + TIME_FIELDS + JOIN_FIELDS + ROW_TYPE_FIELDS + PERFORMANCE_FIELDS))


ARTIFACT_SPECS = (
    {
        "stage": "filter_replay",
        "label": "minimal_lr_filter_results",
        "path": "minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_filter_results.jsonl",
    },
    {
        "stage": "execution_replay",
        "label": "minimal_lr_execution_results",
        "path": "minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_execution_results.jsonl",
    },
    {
        "stage": "sizing_diagnostics",
        "label": "stage6e_sizing_candidates",
        "path": "stage6e_sizing/10000w/stage6c_sizing_candidates.csv",
    },
    {
        "stage": "attempt_proposal",
        "label": "lr_attempt_candidate_rows",
        "path": "lr_attempt_pr11c/lr_attempt_candidate_rows.jsonl",
    },
    {
        "stage": "structure_source_proposal",
        "label": "lr_structure_candidate_rows",
        "path": "lr_structure_pr11d/lr_structure_candidate_rows.jsonl",
    },
    {
        "stage": "exit_profile_proposal",
        "label": "lr_exit_profile_rows",
        "path": "lr_exit_pr11e/lr_exit_profile_rows.jsonl",
    },
    {
        "stage": "sizing_proposal",
        "label": "lr_sizing_policy_rows",
        "path": "lr_sizing_pr11f/lr_sizing_policy_rows.jsonl",
    },
    {
        "stage": "combined_candidate",
        "label": "lr_combined_combo_rows",
        "path": "lr_combined_pr11g/lr_combined_combo_rows.jsonl",
    },
    {
        "stage": "combined_candidate_fix",
        "label": "lr_combined_fix_variant_rows",
        "path": "lr_combined_fix_pr11g/lr_combined_variant_rows.jsonl",
    },
    {
        "stage": "lineage_repair",
        "label": "lineage_backfill_rows",
        "path": "lineage_repair_pr11g_qa_fix_2/lineage_backfill_rows.jsonl",
    },
)


RISKY_WRITER_FUNCTIONS = (
    {
        "risky_file": "trading_system/backtest/risk.py",
        "risky_function": "OrderIntent / SimulatedOrder / RiskDecision / TradeLogEntry",
        "risk_type": "execution_identity_absent",
        "severity": "high",
        "fix_required": True,
        "notes": "Core order/risk dataclasses do not carry trade_id or execution_id.",
    },
    {
        "risky_file": "trading_system/backtest/execution.py",
        "risky_function": "BacktestFillResult / BacktestExecutionEngine.run",
        "risk_type": "execution_identity_absent",
        "severity": "high",
        "fix_required": True,
        "notes": "Fill results contain entry/exit timestamps but no trade_id/execution_id or candidate/event identity.",
    },
    {
        "risky_file": "trading_system/diagnostics/minimal_lr_filter.py",
        "risky_function": "run_minimal_execution_replay",
        "risk_type": "execution_writer_drops_lineage",
        "severity": "high",
        "fix_required": True,
        "notes": "Execution artifact writes candidate_id and performance, but drops event_id, entry/exit time, row_type, trade_id and execution_id.",
    },
    {
        "risky_file": "research_pipeline/runners/lr_attempt_proposal.py",
        "risky_function": "_build_event_rows / _build_candidate_rows",
        "risk_type": "candidate_writer_incomplete_no_lookahead_contract",
        "severity": "medium",
        "fix_required": True,
        "notes": "Attempt rows preserve event/candidate identity but do not emit feature_cutoff_time, structure_confirmed_time, bar_confirmed or no_lookahead_safe explicitly.",
    },
    {
        "risky_file": "research_pipeline/runners/lr_structure_source_proposal.py",
        "risky_function": "structure candidate writer",
        "risk_type": "candidate_writer_incomplete_no_lookahead_contract",
        "severity": "medium",
        "fix_required": True,
        "notes": "Structure proposal rows are proposal artifacts and need explicit row_type and no-lookahead lineage before robustness use.",
    },
    {
        "risky_file": "research_pipeline/runners/lr_exit_profile_proposal.py",
        "risky_function": "_simulate_exit_row",
        "risk_type": "shadow_rows_look_like_performance",
        "severity": "high",
        "fix_required": True,
        "notes": "Shadow exit rows contain net_R/MFE/MAE but lack trade_id/execution_id, event_id, entry/exit time and row_type; they must remain proposal/diagnostic unless joined to closed_trade rows.",
    },
    {
        "risky_file": "research_pipeline/runners/lr_sizing_proposal.py",
        "risky_function": "sizing proposal writers",
        "risk_type": "diagnostic_rows_require_explicit_contract",
        "severity": "medium",
        "fix_required": True,
        "notes": "Sizing rows must remain sizing_diagnostic/proposal-only and must not become eligible_for_performance.",
    },
    {
        "risky_file": "research_pipeline/runners/lr_combined_candidate_proposal.py",
        "risky_function": "_combo_rows / _combo_row / _metrics",
        "risk_type": "combined_writer_drops_lineage",
        "severity": "high",
        "fix_required": True,
        "notes": "Combined rows merge filter/sizing/execution rows but do not preserve trade_id/execution_id, event_id, entry/exit times, row_type or no-lookahead contract fields.",
    },
    {
        "risky_file": "research_pipeline/runners/lr_combined_candidate_fix.py",
        "risky_function": "variant summary writers",
        "risk_type": "summary_rows_not_robustness_input",
        "severity": "medium",
        "fix_required": True,
        "notes": "Variant rows are summaries; they are valid reports only after row-level closed_trade lineage is fixed.",
    },
)


@dataclass(frozen=True)
class RootCauseInvestigationResult:
    strategy: str
    proposal_only: bool
    formal_conclusion_enabled: bool
    primary_decision: str
    next_pr_recommendation: str
    trade_identity_conclusion: str
    no_lookahead_conclusion: str
    combined_writer_conclusion: str
    blocking_root_causes: list[str]
    required_answers: dict[str, str]
    artifacts_to_deprecate_for_robustness: list[str]
    stages_to_rerun_after_fix: list[str]
    first_present_stage_by_field: dict[str, str | None]
    earliest_loss_by_field: dict[str, str | None]
    risky_writer_count: int
    source_artifacts: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_root_cause_investigation(
    *,
    strategy: str,
    artifact_root: Path,
    output_dir: Path,
) -> RootCauseInvestigationResult:
    artifact_root = Path(artifact_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    presence_rows, loaded_sources = _presence_rows(artifact_root)
    first_present = _first_present_by_field(presence_rows)
    earliest_loss = _earliest_loss_by_field(presence_rows)
    result = RootCauseInvestigationResult(
        strategy=strategy,
        proposal_only=True,
        formal_conclusion_enabled=False,
        primary_decision="D",
        next_pr_recommendation="PR 11G-QA-fix-3",
        trade_identity_conclusion=(
            "trade_id/execution_id are not generated by current risk/execution dataclasses or "
            "BacktestFillResult; execution writers also lack schema slots to persist them."
        ),
        no_lookahead_conclusion=(
            "sweep/reclaim/signal/entry times exist in candidate/filter artifacts, but execution and "
            "combined artifacts drop them; feature_cutoff_time, bar_confirmed and no_lookahead_safe are "
            "not explicit in current row-level artifacts."
        ),
        combined_writer_conclusion=(
            "combined writer uses row-level merged rows rather than markdown summary, but those rows are "
            "built from under-specified execution/proposal artifacts and then summarized without execution identity."
        ),
        blocking_root_causes=[
            "execution_identity_not_generated_in_core_execution_schema",
            "minimal_execution_writer_drops_available_entry_exit_time_and_event_lineage",
            "candidate_and_proposal_writers_do_not_emit_full_no_lookahead_contract",
            "combined_writer_does_not_preserve_row_type_or_execution_lineage",
            "shadow/proposal rows can look like performance rows without explicit eligibility fields",
        ],
        required_answers=_required_answers(),
        artifacts_to_deprecate_for_robustness=[
            "minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_execution_results.jsonl",
            "lr_attempt_pr11c/*",
            "lr_structure_pr11d/*",
            "lr_exit_pr11e/*",
            "lr_sizing_pr11f/*",
            "lr_combined_pr11g/*",
            "lr_combined_fix_pr11g/*",
            "lineage_repair_pr11g_qa_fix_2/*",
        ],
        stages_to_rerun_after_fix=[
            "minimal execution replay",
            "PR 11C attempt proposal",
            "PR 11D structure source proposal",
            "PR 11E exit profile proposal",
            "PR 11F sizing proposal",
            "PR 11G combined candidate proposal",
            "PR 11G-fix combined pruning",
            "lineage-repair",
            "full-audit",
        ],
        first_present_stage_by_field=first_present,
        earliest_loss_by_field=earliest_loss,
        risky_writer_count=len(RISKY_WRITER_FUNCTIONS),
        source_artifacts=loaded_sources,
    )
    _write_presence_matrix(output_dir / "lineage_field_presence_matrix.csv", presence_rows)
    _write_jsonl(output_dir / "risky_writer_functions.jsonl", RISKY_WRITER_FUNCTIONS)
    (output_dir / "root_cause_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "root_cause_report.md").write_text(_report(result, presence_rows), encoding="utf-8")
    (output_dir / "artifact_stage_flow.md").write_text(_artifact_stage_flow(), encoding="utf-8")
    (output_dir / "proposed_fix_plan.md").write_text(_fix_plan(), encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=strategy,
        stage="pr11g_qa_root_cause",
        window="10000w",
        source_command="research_pipeline.cli.research root-cause-investigation",
        notes="PR11G-QA root cause investigation; read-only, no strategy changes.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=strategy,
        stage="pr11g_qa_root_cause",
        window="10000w",
        source_command="research_pipeline.cli.research root-cause-investigation",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=True,
        notes="Execution lineage root-cause investigation only; no PR11H entry.",
        tags=["PR11G-QA-root-cause", "audit", "readonly"],
    )
    return result


def _required_answers() -> dict[str, str]:
    return {
        "trade_id_execution_id_generated_or_lost": (
            "They are not generated by the current core risk/execution dataclasses or BacktestFillResult."
        ),
        "loss_file_function_if_generated": (
            "No evidence they were ever generated. Separately, run_minimal_execution_replay drops event_id and entry/exit time fields."
        ),
        "generation_layer_if_missing": (
            "Generate true trade_id/execution_id in execution replay or BacktestExecutionEngine when a real approved fill is created."
        ),
        "no_lookahead_fields_first_exist": (
            "sweep_time/reclaim_time/signal_time/entry_time first exist in filter/sizing candidate artifacts; exit timestamp exists only in BacktestFillResult object; feature_cutoff_time/bar_confirmed/no_lookahead_safe are not explicit upstream."
        ),
        "no_lookahead_fields_lost": (
            "event/time lineage is lost at minimal execution artifact writer and remains absent in combined artifacts."
        ),
        "combined_summary_dependency": (
            "Combined writer does not directly compute from markdown summary, but it uses under-specified row-level merged artifacts and emits summaries that cannot be robustness input."
        ),
        "minimal_fix": (
            "Joint schema and writer fix: add execution identity at fill creation, emit row_type and lineage fields across candidate/filter/execution/proposal/combined writers, and allow performance only from closed_trade rows."
        ),
        "rerun_stages": (
            "Rerun minimal execution, PR 11C, PR 11D, PR 11E, PR 11F, PR 11G, PR 11G-fix, lineage-repair, and full-audit."
        ),
        "deprecated_artifacts": (
            "Old execution and PR 11C-11G derived artifacts without execution identity are invalid for PR 11H robustness input."
        ),
        "full_audit_pass_condition": (
            "Full-audit can pass only after recommended robustness rows have trade_id, execution_id, candidate_id, event_id, verifiable no-lookahead fields, and metrics recompute from row_type=closed_trade."
        ),
    }


def _presence_rows(artifact_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    loaded_sources: list[str] = []
    for order, spec in enumerate(ARTIFACT_SPECS):
        path = artifact_root / str(spec["path"])
        records = _read_rows(path)
        if path.exists():
            loaded_sources.append(str(path))
        row_count = len(records)
        for field in FIELDS_TO_SCAN:
            present_values = [_stringify(record.get(field)) for record in records if _has_value(record.get(field))]
            rows.append(
                {
                    "order": order,
                    "stage": spec["stage"],
                    "artifact_label": spec["label"],
                    "path": str(path),
                    "file_exists": path.exists(),
                    "row_count": row_count,
                    "field": field,
                    "field_group": _field_group(field),
                    "present_count": len(present_values),
                    "missing_count": max(0, row_count - len(present_values)),
                    "present_ratio": _ratio(len(present_values), row_count),
                    "example_value": present_values[0] if present_values else "",
                }
            )
    return rows, loaded_sources


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    rows.append(json.loads(stripped))
        return rows
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    return []


def _first_present_by_field(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field in FIELDS_TO_SCAN:
        field_rows = [row for row in rows if row["field"] == field and row["row_count"]]
        present = next((row for row in field_rows if int(row["present_count"]) > 0), None)
        result[field] = None if present is None else f"{present['stage']}:{present['artifact_label']}"
    return result


def _earliest_loss_by_field(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field in FIELDS_TO_SCAN:
        field_rows = [row for row in rows if row["field"] == field and row["row_count"]]
        seen_present = False
        loss = None
        for row in field_rows:
            if int(row["present_count"]) > 0:
                seen_present = True
                continue
            if seen_present and int(row["present_count"]) == 0:
                loss = f"{row['stage']}:{row['artifact_label']}"
                break
        result[field] = loss
    return result


def _write_presence_matrix(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "order",
        "stage",
        "artifact_label",
        "path",
        "file_exists",
        "row_count",
        "field_group",
        "field",
        "present_count",
        "missing_count",
        "present_ratio",
        "example_value",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _write_jsonl(path: Path, rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _report(result: RootCauseInvestigationResult, rows: list[dict[str, Any]]) -> str:
    identity_rows = [row for row in rows if row["field"] in {"trade_id", "execution_id"}]
    timing_rows = [
        row
        for row in rows
        if row["field"]
        in {
            "feature_cutoff_time",
            "structure_confirmed_time",
            "structure_time",
            "sweep_time",
            "reclaim_time",
            "signal_time",
            "entry_time",
            "exit_time",
            "entry_timestamp_ms",
            "exit_timestamp_ms",
            "bar_confirmed",
            "no_lookahead_safe",
        }
    ]
    lines = [
        "# PR 11G-QA Root Cause Report",
        "",
        "## Conclusion",
        "",
        "Primary Decision: D. 多处都有问题，下一步做 schema + writer 联合修复。",
        "",
        "- trade_id / execution_id 当前不是生成后丢失，而是 core execution / risk schema 从未生成。",
        "- execution writer 还会丢失已经存在的 entry/exit timestamp 与 event lineage。",
        "- candidate/filter artifact 有 sweep/reclaim/signal/entry 时间，但 no-lookahead contract 字段不完整。",
        "- combined writer 没有直接从 Markdown summary 构造 performance，但它合并的是缺少 execution identity 的 row-level artifact，随后输出的 summary rows 不能作为 robustness input。",
        "",
        "## Required Answers",
        "",
        "1. trade_id / execution_id 是从未生成，还是生成后丢失？",
        "",
        "从未在 core execution/risk dataclass 中生成。`BacktestFillResult`、`SimulatedOrder`、`TradeLogEntry` 当前都没有 `trade_id` / `execution_id` 字段。",
        "",
        "2. 如果生成后丢失，在哪个文件 / 函数 / writer 丢失？",
        "",
        "没有证据表明它们曾被生成。另一个独立问题是 `trading_system/diagnostics/minimal_lr_filter.py::run_minimal_execution_replay` 会把可用的 entry/exit timestamp、event_id 和 row_type 从 execution artifact 中省略。",
        "",
        "3. 如果从未生成，应该在哪一层生成？",
        "",
        "应在 execution replay / execution engine 产生真实 fill 时生成，并写入 `BacktestFillResult` 或等价 execution row schema；不能在 combined/report 阶段补造。",
        "",
        "4. no-lookahead 时间字段在哪一层最早存在？",
        "",
        "- `sweep_time` / `reclaim_time` / `signal_time` / `entry_time` 最早在 filter/sizing candidate artifact 中存在。",
        "- `structure_confirmed_time` 没有显式字段；当前最接近的是 `structure_time`。",
        "- `exit_time` 在 `BacktestFillResult.exit_timestamp_ms` 对象中存在，但旧 execution artifact 没写出。",
        "- `feature_cutoff_time` / `bar_confirmed` / `no_lookahead_safe` 当前没有显式 row-level 字段。",
        "",
        "5. 它们在哪一层丢失？",
        "",
        "filter/sizing 后进入 execution artifact 时丢失 event/time lineage；进入 combined writer 后仍未恢复完整 lineage。",
        "",
        "6. combined report 是否错误依赖 summary rows？",
        "",
        "combined writer 主要从 row-level filter/sizing/execution merge 计算，不是直接依赖 Markdown summary。但其输入 execution rows 已缺少 identity/time，且 variant/portfolio summary rows 不能作为 robustness input。",
        "",
        "7. 当前最小修复方案是什么？",
        "",
        "做 schema + writer 联合修复：execution 生成真实 identity，candidate/filter/execution/combined writers 全部写出统一 row_type、identity、time、policy 和 eligibility 字段。",
        "",
        "8. 修复后需要重跑哪些阶段？",
        "",
        "至少重跑 minimal execution replay、PR 11C attempt、PR 11D structure、PR 11E exit、PR 11F sizing、PR 11G combined、PR 11G-fix、lineage-repair、full-audit。",
        "",
        "9. 哪些旧 artifacts 需要废弃？",
        "",
        "所有缺少真实 execution identity 的 `minimal_lr_v0_execution_results.jsonl`、PR 11C-11G derived artifacts、PR 11G-fix、PR 11G-QA-fix-2 robustness input 都不能作为 PR 11H 输入，只能保留为历史 diagnostic。",
        "",
        "10. 修复后 full-audit 应如何通过？",
        "",
        "推荐 robustness rows 必须 100% 具备 `trade_id`、`execution_id`、`candidate_id`、`event_id` 和可验证 no-lookahead 时间字段；performance metrics 必须只从 `row_type=closed_trade` 重算。",
        "",
        "## Identity Field Evidence",
        "",
        "| artifact | stage | rows | trade_id present | execution_id present |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in _labels(identity_rows):
        trade = _find_row(identity_rows, label, "trade_id")
        execution = _find_row(identity_rows, label, "execution_id")
        if trade is None or execution is None:
            continue
        lines.append(
            f"| {trade['artifact_label']} | {trade['stage']} | {trade['row_count']} | {trade['present_count']} | {execution['present_count']} |"
        )
    lines.extend(
        [
            "",
            "## No-lookahead Field Evidence",
            "",
            "| field | first_present | earliest_loss |",
            "|---|---|---|",
        ]
    )
    for field in ("feature_cutoff_time", "structure_confirmed_time", "structure_time", "sweep_time", "reclaim_time", "signal_time", "entry_time", "exit_time", "bar_confirmed", "no_lookahead_safe"):
        lines.append(
            f"| {field} | {result.first_present_stage_by_field.get(field)} | {result.earliest_loss_by_field.get(field)} |"
        )
    lines.extend(
        [
            "",
            "## Risky Writer Functions",
            "",
        ]
    )
    for item in RISKY_WRITER_FUNCTIONS:
        lines.append(f"- {item['severity']}: {item['risky_file']}::{item['risky_function']} - {item['risk_type']}")
    lines.extend(
        [
            "",
            "## Primary Decision",
            "",
            "D. 多处都有问题，下一步做 schema + writer 联合修复。",
            "",
            "## Next PR",
            "",
            "- Next PR = PR 11G-QA-fix-3",
            "- 禁止进入 PR 11H 或 PR 12。",
        ]
    )
    return "\n".join(lines) + "\n"


def _artifact_stage_flow() -> str:
    return "\n".join(
        [
            "# Artifact Stage Flow",
            "",
            "| stage | artifact | current lineage state | root-cause finding |",
            "|---|---|---|---|",
            "| candidate/filter | minimal_lr_v0_filter_results.jsonl | candidate_id/event_id and sweep/reclaim/signal/entry times exist | missing explicit row_type, feature_cutoff_time, structure_confirmed_time, bar_confirmed, no_lookahead_safe |",
            "| execution object | BacktestFillResult | entry_timestamp_ms and exit_timestamp_ms exist in memory | trade_id/execution_id and candidate/event identity are absent |",
            "| execution writer | minimal_lr_v0_execution_results.jsonl | candidate_id and performance metrics are written | event_id, entry/exit time, row_type, trade_id, execution_id are not written |",
            "| attempt proposal | lr_attempt_candidate_rows.jsonl | event/candidate lineage partly restored | no explicit full no-lookahead contract |",
            "| structure proposal | lr_structure_candidate_rows.jsonl | proposal source lineage exists only partially | new source rows still need row_type and no-lookahead fields |",
            "| exit profile | lr_exit_profile_rows.jsonl | shadow performance-like rows exist | lacks execution identity, event_id and entry/exit time; must stay shadow/proposal |",
            "| sizing proposal | lr_sizing_policy_rows.jsonl | sizing diagnostics exist | must remain sizing_diagnostic and ineligible for performance |",
            "| combined proposal | lr_combined_combo_rows.jsonl | merges filter/sizing/execution rows | drops/passes through no execution identity; summary rows are not robustness input |",
            "| lineage repair | lineage_backfill_rows.jsonl | correctly marks rows invalid | cannot backfill true trade_id/execution_id because upstream never generated them |",
            "",
        ]
    )


def _fix_plan() -> str:
    return "\n".join(
        [
            "# Proposed Fix Plan",
            "",
            "## Primary Decision",
            "",
            "D. 多处都有问题，下一步做 schema + writer 联合修复。",
            "",
            "## Minimal Viable Fix",
            "",
            "1. Define one shared research row contract for `raw_candidate`, `formal_approved`, `executed_trade`, `closed_trade`, `sizing_diagnostic`, `diagnostic_only`, `summary_row`.",
            "2. Add true execution identity at execution replay time. `trade_id` and `execution_id` must be generated when a real approved fill is created, using actual candidate/event identity and execution context. Do not generate them in report or combined layers.",
            "3. Extend execution artifact writer to emit `row_type=closed_trade`, `trade_id`, `execution_id`, `candidate_id`, `event_id`, `entry_time`, `exit_time`, `exit_reason`, costs, same-bar fields and performance metrics.",
            "4. Extend candidate/filter writers to emit `row_type`, `feature_cutoff_time`, `structure_confirmed_time`, `bar_confirmed`, `no_lookahead_safe`, `sweep_time`, `reclaim_time`, `signal_time`, `entry_time`.",
            "5. Update attempt/structure/exit/sizing proposal writers so shadow/proposal/sizing rows are explicit and `eligible_for_performance=false` unless joined to a real `closed_trade`.",
            "6. Update combined writer to select only row-level `closed_trade` for performance, preserve all lineage fields, and exclude summary/proposal/diagnostic rows from robustness input.",
            "7. Re-run minimal execution replay and downstream PR 11C-11G artifacts, then run lineage repair and full-audit again.",
            "",
            "## Artifacts To Retire From Robustness Input",
            "",
            "- `minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_execution_results.jsonl`",
            "- `lr_attempt_pr11c/*`",
            "- `lr_structure_pr11d/*`",
            "- `lr_exit_pr11e/*`",
            "- `lr_sizing_pr11f/*`",
            "- `lr_combined_pr11g/*`",
            "- `lr_combined_fix_pr11g/*`",
            "- `lineage_repair_pr11g_qa_fix_2/*`",
            "",
            "这些旧 artifacts 可保留历史追溯，但不得作为 PR 11H robustness input。",
            "",
            "## Verification After Fix",
            "",
            "- `full-audit` Primary Decision must be A or B.",
            "- recommended robustness rows must have 100% `trade_id` and `execution_id`.",
            "- recommended robustness rows must have 100% `candidate_id` and `event_id`.",
            "- no-lookahead checks must be verifiable, not inferred from summary.",
            "- performance metrics must recompute from `row_type=closed_trade` only.",
            "",
            "## Next PR",
            "",
            "Next PR = PR 11G-QA-fix-3。",
            "",
        ]
    )


def _labels(rows: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for row in rows:
        label = str(row["artifact_label"])
        if label not in labels:
            labels.append(label)
    return labels


def _find_row(rows: list[dict[str, Any]], label: str, field: str) -> dict[str, Any] | None:
    return next((row for row in rows if row["artifact_label"] == label and row["field"] == field), None)


def _field_group(field: str) -> str:
    if field in IDENTITY_FIELDS:
        return "identity"
    if field in TIME_FIELDS:
        return "no_lookahead_time"
    if field in JOIN_FIELDS:
        return "join"
    if field in ROW_TYPE_FIELDS:
        return "row_type_contract"
    if field in PERFORMANCE_FIELDS:
        return "performance"
    return "other"


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:120]
    return str(value)[:120]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
