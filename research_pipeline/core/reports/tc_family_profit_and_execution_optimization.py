from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def write_tc_family_profit_execution_report(*, output_dir: Path, payload: Mapping[str, object]) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tc_family_profit_and_execution_optimization_report.md"
    baseline = payload.get("baseline_summaries") if isinstance(payload.get("baseline_summaries"), Mapping) else {}
    variants = payload.get("optimization_summaries") if isinstance(payload.get("optimization_summaries"), Mapping) else {}
    lines = [
        "# TC Family Profit and Execution Optimization Report",
        "",
        "## 1. Executive Summary",
        f"- Decision: {payload.get('decision', 'unavailable')}",
        f"- Primary diagnosis: {payload.get('primary_diagnosis', 'unavailable')}",
        "- 本轮只判断收益不足来自信号、入场、出场、成本或 sizing；不 formalize，不进入 P6。",
        "",
        "## 2. Research Scope and Constraints",
    ]
    lines.extend(f"- {item}" for item in payload.get("constraints", ()))
    lines.extend(
        [
            "- MAE/MFE diagnostics are computed after entry and within each closed trade lifecycle only.",
            "- Performance metrics use `row_type=closed_trade` only.",
            "",
            "## 3. Previous Trade Count Round Recap",
            "- 上一轮证明 CE native、CE shallow、BP shallow 均能产生大量 closed trades。",
            "- 本轮不靠单纯提高过滤阈值优化均值，而先判断 MFE/MAE/exit efficiency。",
            _baseline_performance_table(baseline),
            "",
            "## 4. Baseline MAE/MFE Diagnostics",
            "- Path diagnostics expand base/stress/harsh closed rows, so `Closed` in MAE/MFE tables is cost-tier row count, not unique execution count.",
            _path_table(baseline),
            "",
            "## 5. Profit Attribution",
            _attribution_table(baseline),
            "",
            "## 6. Optimization Variant Design",
            "- `bp_shallow_exit_efficiency_v1`: BP shallow proposal-only exit improvement。",
            "- `ce_shallow_exit_efficiency_v1`: CE shallow proposal-only exit improvement。",
            "- `bp_shallow_entry_timing_v1`: BP shallow conservative entry timing / early adverse reduction。",
            "- `bp_shallow_cost_quality_v1`: BP shallow cost and target-space quality filter。",
            "",
            "## 7. Variant Results",
            _variant_performance_table(variants),
            "- Path diagnostics below use the same cost-tier row policy; use the performance table above for unique closed trade counts.",
            _path_table(variants),
            "",
            "## 8. Entry Optimization Analysis",
            _variant_detail(variants, "bp_shallow_entry_timing_v1"),
            "",
            "## 9. Exit Optimization Analysis",
            _variant_detail(variants, "bp_shallow_exit_efficiency_v1"),
            _variant_detail(variants, "ce_shallow_exit_efficiency_v1"),
            "",
            "## 10. Cost Resilience Analysis",
            _variant_detail(variants, "bp_shallow_cost_quality_v1"),
            "",
            "## 11. Return Quality and Robustness",
            _robustness_table(variants),
            "",
            "## 12. Concentration Risk",
            _concentration_table(variants),
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
            f"- shared_cache_path: `{payload.get('shared_cache_path', '')}`",
            "- Required artifacts:",
        ]
    )
    lines.extend(f"  - `{item}`" for item in payload.get("artifact_paths", ()))
    lines.append("- Known limitations:")
    lines.extend(f"  - {item}" for item in payload.get("known_limitations", ()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def _baseline_performance_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Baseline | Raw | Proposal approved | Closed | Base R | Stress R | Harsh R | Median R | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {key} | {_v(row, 'raw_candidates')} | {_v(row, 'proposal_approved_after_cap')} | {_v(row, 'closed_trades')} | "
            f"{_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | {_fmt(row.get('harsh_net_R_avg'))} | "
            f"{_fmt(row.get('median_R'))} | {_fmt(row.get('PF'))} |"
        )
    return "\n".join(lines)


def _variant_performance_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Closed | Base R | Stress R | Harsh R | Total R | Median R | PF | Ex top1 | Ex top2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {key} | {_v(row, 'closed_trades')} | {_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | "
            f"{_fmt(row.get('harsh_net_R_avg'))} | {_fmt(row.get('total_R'))} | {_fmt(row.get('median_R'))} | "
            f"{_fmt(row.get('PF'))} | {_fmt(row.get('net_R_avg_excluding_top_1'))} | {_fmt(row.get('net_R_avg_excluding_top_2'))} |"
        )
    return "\n".join(lines)


def _path_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Row | Closed | MFE avg/median/p75 | MAE avg/median/p75 | Exit eff avg/median | Giveback avg | MFE>=0.5 | MFE>=1 | Pos MFE loss | Early MAE | Cost flipped |",
        "|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        path = row.get("path_diagnostics") if isinstance(row.get("path_diagnostics"), Mapping) else row
        lines.append(
            f"| {key} | {_v(path, 'closed_trades')} | {_fmt(path.get('MFE_R_avg'))}/{_fmt(path.get('MFE_R_median'))}/{_fmt(path.get('MFE_R_p75'))} | "
            f"{_fmt(path.get('MAE_R_avg'))}/{_fmt(path.get('MAE_R_median'))}/{_fmt(path.get('MAE_R_p75'))} | "
            f"{_fmt(path.get('exit_efficiency_avg'))}/{_fmt(path.get('exit_efficiency_median'))} | "
            f"{_fmt(path.get('profit_giveback_R_avg'))} | {_fmt(path.get('reached_0_5R_share'))} | "
            f"{_fmt(path.get('reached_1R_share'))} | {_v(path, 'positive_MFE_but_final_loss')} | {_v(path, 'early_MAE')} | {_v(path, 'cost_flipped_to_loss')} |"
        )
    return "\n".join(lines)


def _attribution_table(rows: Mapping[str, object]) -> str:
    lines = ["| Row | Attribution counts | Path groups |", "|---|---|---|"]
    for key, raw in rows.items():
        row = raw if isinstance(raw, Mapping) else {}
        path = row.get("path_diagnostics") if isinstance(row.get("path_diagnostics"), Mapping) else row
        lines.append(f"| {key} | `{path.get('attribution_counts', {})}` | `{path.get('path_group_counts', {})}` |")
    return "\n".join(lines)


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
            f"{row.get('metric_recompute', 'unavailable')} | {row.get('regression_baseline', 'unavailable')} | "
            f"{row.get('sample_size_warning', True)} |"
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


__all__ = ("write_tc_family_profit_execution_report",)
