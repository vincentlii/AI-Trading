from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def write_tc_family_cost_aware_exit_target_report(*, output_dir: Path, payload: Mapping[str, object]) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tc_family_cost_aware_exit_target_report.md"
    baseline = payload.get("baseline_summary") if isinstance(payload.get("baseline_summary"), Mapping) else {}
    variants = payload.get("variant_summaries") if isinstance(payload.get("variant_summaries"), Mapping) else {}
    ce = payload.get("ce_shallow_comparison") if isinstance(payload.get("ce_shallow_comparison"), Mapping) else {}
    lines = [
        "# TC Family Cost-Aware Exit Target Report",
        "",
        "## 1. Executive Summary",
        f"- Decision: {payload.get('decision', 'unavailable')}",
        f"- Primary diagnosis: {payload.get('primary_diagnosis', 'unavailable')}",
        "- 本轮只研究 BP shallow cost-aware exit/target；不 formalize，不进入 P6。",
        "",
        "## 2. Research Scope and Constraints",
    ]
    lines.extend(f"- {item}" for item in payload.get("constraints", ()))
    lines.extend(
        [
            "- MAE/MFE and exit decisions use only trade-lifecycle information after entry.",
            "- Performance metrics use `row_type=closed_trade` only.",
            "",
            "## 3. Previous Profit/Execution Round Recap",
            "- 上一轮最佳路径是 `bp_shallow_cost_quality_v1`，但 stress/harsh 仍为负。",
            "- 本轮不继续 entry timing，不优化 CE native，不扩大交易数。",
            _single_performance_table("Previous best", baseline),
            "",
            "## 4. Baseline Failure Mechanism",
            "- Path diagnostics expand base/stress/harsh closed rows; path `Closed` is cost-tier row count, not unique execution count.",
            _path_summary_table({"bp_shallow_cost_quality_v1": baseline}),
            "",
            "## 5. Variant Design",
            "- `bp_shallow_micro_profit_capture_v1`: 0.40R/0.50R soft capture policy with proposal-only partial/breakeven/trailing behavior。",
            "- `bp_shallow_momentum_decay_time_stop_v1`: no-follow-through time stop when early MFE stays below 0.25R。",
            "- `bp_shallow_cost_aware_admission_v2`: entry-known cost/space score, removing the weakest 20%-30% candidates without asset/profile/direction hand-picking。",
            "",
            "## 6. Variant Results",
            _variant_table(variants),
            _path_summary_table(variants),
            "",
            "## 7. Exit and Profit Capture Analysis",
            _variant_detail(variants, "bp_shallow_micro_profit_capture_v1"),
            "",
            "## 8. Momentum Decay / Time Stop Analysis",
            _variant_detail(variants, "bp_shallow_momentum_decay_time_stop_v1"),
            "",
            "## 9. Cost-Aware Admission Analysis",
            _variant_detail(variants, "bp_shallow_cost_aware_admission_v2"),
            _retained_removed_table(variants.get("bp_shallow_cost_aware_admission_v2", {})),
            "",
            "## 10. Return Quality and Robustness",
            _robustness_table(variants),
            "",
            "## 11. Concentration Risk",
            _concentration_table(variants),
            "",
            "## 12. CE Shallow Diagnostic Comparison",
            _single_performance_table("CE shallow comparison", ce),
            "- CE shallow remains diagnostic comparison only; no CE native optimization was run.",
            "",
            "## 13. Decision",
            f"- {payload.get('decision', 'unavailable')}",
            f"- Rationale: {payload.get('decision_reason', 'See diagnostics above.')}",
            "",
            "## 14. Next Action Plan",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("next_actions", ()))
    lines.extend(
        [
            "",
            "## 15. Reproducibility Notes",
            f"- run_id: `{payload.get('run_id', '')}`",
            f"- baseline_run_root: `{payload.get('baseline_run_root', '')}`",
            "- Required artifacts:",
        ]
    )
    lines.extend(f"  - `{item}`" for item in payload.get("artifact_paths", ()))
    lines.append("- Known limitations:")
    lines.extend(f"  - {item}" for item in payload.get("known_limitations", ()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def _single_performance_table(label: str, row: Mapping[str, object]) -> str:
    return "\n".join(
        [
            "| Row | Closed | Base R | Stress R | Harsh R | Total R | Median R | PF |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            f"| {label} | {_v(row, 'closed_trades')} | {_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | {_fmt(row.get('harsh_net_R_avg'))} | {_fmt(row.get('total_R'))} | {_fmt(row.get('median_R'))} | {_fmt(row.get('PF'))} |",
        ]
    )


def _variant_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Raw | Approved | Closed | Base R | Stress R | Harsh R | Median R | PF | Ex top1 | Ex top2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {key} | {_v(row, 'raw_candidates')} | {_v(row, 'proposal_approved_after_cap')} | {_v(row, 'closed_trades')} | "
            f"{_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | {_fmt(row.get('harsh_net_R_avg'))} | "
            f"{_fmt(row.get('median_R'))} | {_fmt(row.get('PF'))} | {_fmt(row.get('net_R_avg_excluding_top_1'))} | {_fmt(row.get('net_R_avg_excluding_top_2'))} |"
        )
    return "\n".join(lines)


def _path_summary_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Row | Path closed | MFE avg/median/p75 | MAE avg/median/p75 | Giveback avg/median | MFE>=0.4 | MFE>=0.5 | MFE>=0.75 | MFE>=1 | Pos MFE loss | Cost flipped | Never 0.5R |",
        "|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        path = row.get("path_diagnostics") if isinstance(row.get("path_diagnostics"), Mapping) else row
        lines.append(
            f"| {key} | {_v(path, 'closed_trades')} | {_fmt(path.get('MFE_R_avg'))}/{_fmt(path.get('MFE_R_median'))}/{_fmt(path.get('MFE_R_p75'))} | "
            f"{_fmt(path.get('MAE_R_avg'))}/{_fmt(path.get('MAE_R_median'))}/{_fmt(path.get('MAE_R_p75'))} | "
            f"{_fmt(path.get('profit_giveback_R_avg'))}/{_fmt(path.get('profit_giveback_R_median'))} | "
            f"{_fmt(path.get('MFE_ge_0_4R_share'))} | {_fmt(path.get('reached_0_5R_share'))} | {_fmt(path.get('reached_0_75R_share'))} | {_fmt(path.get('reached_1R_share'))} | "
            f"{_v(path, 'positive_MFE_but_final_loss')} | {_v(path, 'cost_flipped_to_loss')} | {_v(path, 'never_reached_0_5R_MFE')} |"
        )
    return "\n".join(lines)


def _retained_removed_table(row: object) -> str:
    data = row if isinstance(row, Mapping) else {}
    cmp = data.get("retained_removed_comparison") if isinstance(data.get("retained_removed_comparison"), Mapping) else {}
    return "\n".join(
        [
            "| Group | Count | Avg R | Harsh R | Median R | Cost/R |",
            "|---|---:|---:|---:|---:|---:|",
            f"| retained | {_v(cmp, 'retained_count')} | {_fmt(cmp.get('retained_avg_R'))} | {_fmt(cmp.get('retained_harsh_R'))} | {_fmt(cmp.get('retained_median_R'))} | {_fmt(cmp.get('retained_cost_per_R'))} |",
            f"| removed | {_v(cmp, 'removed_count')} | {_fmt(cmp.get('removed_avg_R'))} | {_fmt(cmp.get('removed_harsh_R'))} | {_fmt(cmp.get('removed_median_R'))} | {_fmt(cmp.get('removed_cost_per_R'))} |",
        ]
    )


def _robustness_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Variant | WF +/- | Full Audit | No-lookahead | Metric recompute | Regression baseline | Sample warning |",
        "|---|---:|---|---|---|---|---|",
    ]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {key} | {_v(row, 'positive_walk_forward_windows')}/{_v(row, 'negative_walk_forward_windows')} | "
            f"{row.get('full_audit_gate', 'unavailable')} | {row.get('no_lookahead', 'unavailable')} | "
            f"{row.get('metric_recompute', 'unavailable')} | {row.get('regression_baseline', 'unavailable')} | {row.get('sample_size_warning', True)} |"
        )
    return "\n".join(lines)


def _concentration_table(rows: Mapping[str, object]) -> str:
    lines = ["| Variant | Asset | Profile | Direction | Trend state |", "|---|---|---|---|---|"]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {key} | `{row.get('asset_split', {})}` | `{row.get('profile_split', {})}` | "
            f"`{row.get('direction_split', {})}` | `{row.get('trend_state_split', {})}` |"
        )
    return "\n".join(lines)


def _variant_detail(rows: Mapping[str, object], key: str) -> str:
    row = rows.get(key) if isinstance(rows.get(key), Mapping) else {}
    if not row:
        return f"- `{key}`: no result."
    return f"- `{key}`: {row.get('interpretation', 'See tables above.')}"


def _v(row: Mapping[str, object], key: str) -> object:
    return row.get(key, 0)


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


__all__ = ("write_tc_family_cost_aware_exit_target_report",)
