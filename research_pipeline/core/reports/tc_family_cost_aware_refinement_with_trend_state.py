from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def write_tc_family_cost_aware_refinement_with_trend_state_report(
    *,
    output_dir: Path,
    payload: Mapping[str, object],
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tc_family_cost_aware_refinement_with_trend_state_report.md"
    baseline = _mapping(payload.get("baseline_summary"))
    variants = _mapping(payload.get("variant_summaries"))
    trend = _mapping(payload.get("trend_state_diagnostics"))
    ce = _mapping(payload.get("ce_shallow_comparison"))
    lines = [
        "# TC Family Cost-Aware Refinement With Trend State Report",
        "",
        "## 1. Executive Summary",
        f"- Decision: {payload.get('decision', 'unavailable')}",
        f"- Summary: {payload.get('executive_summary', 'See diagnostics below.')}",
        f"- trend_state unknown share: {_fmt(trend.get('closed_trade_unknown_share'))}",
        "",
        "## 2. Research Scope and Constraints",
    ]
    lines.extend(f"- {item}" for item in payload.get("constraints", ()))
    lines.extend(
        [
            "- This round is proposal-only; no formalization, no P6, no live trading.",
            "- Performance uses `row_type=closed_trade` only.",
            "- MAE/MFE and proposal exits use only trade-lifecycle information.",
            "",
            "## 3. Previous Cost-Aware Round Recap",
            "- `bp_shallow_cost_aware_admission_v2` remains the baseline and source artifact.",
            "- CE native, entry timing, and mechanical time stop are not optimized in this round.",
            _single_performance_table("bp_shallow_cost_aware_admission_v2 baseline", baseline),
            "",
            "## 4. Trend State Lineage Fix",
            "- trend_state was previously reported as `unknown` because lifecycle rows carried the old field but closed-trade summaries did not have a repaired `trend_state_at_entry` lineage field.",
            "- This round derives `trend_state_at_entry` from the existing `build_market_regime()`口径 using entry-time safe cutoffs, then propagates it to candidate/filter/closed rows.",
            _trend_lineage_table(trend),
            "",
            "## 5. Baseline Failure Mechanism",
            _path_summary_table({"v2 baseline": baseline}),
            "",
            "## 6. Variant Design",
            "- `bp_shallow_cost_aware_admission_v3`: light second-pass entry-known cost/space refinement on v2 retained trades.",
            "- `bp_shallow_cost_aware_partial_capture_v1`: applies 0.50R partial capture only after v2 cost-aware admission.",
            "- `bp_shallow_cost_aware_momentum_failure_exit_v1`: replaces mechanical time stop with evidence-based no-follow-through exit.",
            "",
            "## 7. Variant Results",
            _variant_table(variants),
            _path_summary_table(variants),
            "",
            "## 8. Cost-Aware Admission Refinement Analysis",
            _variant_detail(variants, "bp_shallow_cost_aware_admission_v3"),
            _retained_removed_table(variants.get("bp_shallow_cost_aware_admission_v3", {})),
            "",
            "## 9. Partial Capture Analysis",
            _variant_detail(variants, "bp_shallow_cost_aware_partial_capture_v1"),
            "",
            "## 10. Momentum Failure Exit Analysis",
            _variant_detail(variants, "bp_shallow_cost_aware_momentum_failure_exit_v1"),
            "",
            "## 11. Trend State Diagnostics",
            _trend_split_table(variants),
            f"- Interpretation: {payload.get('trend_state_interpretation', 'Trend-state split is diagnostic only and was not used for sample selection.')}",
            "",
            "## 12. Return Quality and Robustness",
            _robustness_table(variants),
            "",
            "## 13. Concentration Risk",
            _concentration_table(variants),
            "",
            "## 14. CE Shallow Diagnostic Comparison",
            _single_performance_table("CE shallow comparison", ce),
            "- CE shallow remains diagnostic-only; no new CE optimization variant was run.",
            "",
            "## 15. Decision",
            f"- {payload.get('decision', 'unavailable')}",
            f"- Rationale: {payload.get('decision_reason', 'See fixed thresholds and diagnostics above.')}",
            "",
            "## 16. Next Action Plan",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("next_actions", ()))
    lines.extend(
        [
            "",
            "## 17. Reproducibility Notes",
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
            "| Row | Closed | Base R | Stress R | Harsh R | Total R | Median R | PF | WF +/- |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            f"| {label} | {_v(row, 'closed_trades')} | {_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | {_fmt(row.get('harsh_net_R_avg'))} | {_fmt(row.get('total_R'))} | {_fmt(row.get('median_R'))} | {_fmt(row.get('PF'))} | {_v(row, 'positive_walk_forward_windows')}/{_v(row, 'negative_walk_forward_windows')} |",
        ]
    )


def _variant_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Raw | Approved | Closed | Base R | Stress R | Harsh R | Median R | PF | Ex top1 | Ex top2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = _mapping(raw)
        lines.append(
            f"| {key} | {_v(row, 'raw_candidates')} | {_v(row, 'proposal_approved_after_cap')} | {_v(row, 'closed_trades')} | "
            f"{_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | {_fmt(row.get('harsh_net_R_avg'))} | "
            f"{_fmt(row.get('median_R'))} | {_fmt(row.get('PF'))} | {_fmt(row.get('net_R_avg_excluding_top_1'))} | {_fmt(row.get('net_R_avg_excluding_top_2'))} |"
        )
    return "\n".join(lines)


def _path_summary_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Row | Path closed | MFE avg/median/p75 | MAE avg/median/p75 | Giveback avg/median | MFE>=0.5 | Pos MFE loss | Cost flipped | Never 0.5R |",
        "|---|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = _mapping(raw)
        path = _mapping(row.get("path_diagnostics")) or row
        lines.append(
            f"| {key} | {_v(path, 'closed_trades')} | {_fmt(path.get('MFE_R_avg'))}/{_fmt(path.get('MFE_R_median'))}/{_fmt(path.get('MFE_R_p75'))} | "
            f"{_fmt(path.get('MAE_R_avg'))}/{_fmt(path.get('MAE_R_median'))}/{_fmt(path.get('MAE_R_p75'))} | "
            f"{_fmt(path.get('profit_giveback_R_avg'))}/{_fmt(path.get('profit_giveback_R_median'))} | "
            f"{_fmt(path.get('reached_0_5R_share'))} | {_v(path, 'positive_MFE_but_final_loss')} | {_v(path, 'cost_flipped_to_loss')} | {_v(path, 'never_reached_0_5R_MFE')} |"
        )
    return "\n".join(lines)


def _trend_lineage_table(row: Mapping[str, object]) -> str:
    return "\n".join(
        [
            "| Layer | Coverage | Unknown share |",
            "|---|---:|---:|",
            f"| context | {_fmt(row.get('context_trend_state_coverage'))} | n/a |",
            f"| event | {_fmt(row.get('event_trend_state_coverage'))} | n/a |",
            f"| candidate | {_fmt(row.get('candidate_trend_state_coverage'))} | {_fmt(row.get('candidate_unknown_share'))} |",
            f"| closed_trade | {_fmt(row.get('closed_trade_trend_state_coverage'))} | {_fmt(row.get('closed_trade_unknown_share'))} |",
        ]
    )


def _trend_split_table(rows: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Trend state split | Trend state metrics |",
        "|---|---|---|",
    ]
    for key, raw in rows.items():
        row = _mapping(raw)
        lines.append(
            f"| {key} | `{row.get('trend_state_split', {})}` | `{row.get('trend_state_metrics', {})}` |"
        )
    return "\n".join(lines)


def _retained_removed_table(raw: object) -> str:
    row = _mapping(raw)
    cmp = _mapping(row.get("retained_removed_comparison"))
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
        "| Variant | WF +/- | Full Audit | No-lookahead | Metric recompute | Regression baseline |",
        "|---|---:|---|---|---|---|",
    ]
    for key, raw in rows.items():
        row = _mapping(raw)
        lines.append(
            f"| {key} | {_v(row, 'positive_walk_forward_windows')}/{_v(row, 'negative_walk_forward_windows')} | "
            f"{row.get('full_audit_gate', 'unavailable')} | {row.get('no_lookahead', 'unavailable')} | "
            f"{row.get('metric_recompute', 'unavailable')} | {row.get('regression_baseline', 'unavailable')} |"
        )
    return "\n".join(lines)


def _concentration_table(rows: Mapping[str, object]) -> str:
    lines = ["| Variant | Asset | Profile | Direction | Trend state |", "|---|---|---|---|---|"]
    for key, raw in rows.items():
        row = _mapping(raw)
        lines.append(
            f"| {key} | `{row.get('asset_split', {})}` | `{row.get('profile_split', {})}` | "
            f"`{row.get('direction_split', {})}` | `{row.get('trend_state_split', {})}` |"
        )
    return "\n".join(lines)


def _variant_detail(rows: Mapping[str, object], key: str) -> str:
    row = _mapping(rows.get(key))
    if not row:
        return f"- `{key}`: no result."
    return f"- `{key}`: {row.get('interpretation', 'See tables above.')}"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _v(row: Mapping[str, object], key: str) -> object:
    return row.get(key, 0)


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


__all__ = ("write_tc_family_cost_aware_refinement_with_trend_state_report",)
