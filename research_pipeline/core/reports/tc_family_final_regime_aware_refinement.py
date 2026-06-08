from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def write_tc_family_final_regime_aware_refinement_report(
    *,
    output_dir: Path,
    payload: Mapping[str, object],
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tc_family_final_regime_aware_refinement_report.md"
    baseline = _mapping(payload.get("baseline_summary"))
    variants = _mapping(payload.get("variant_summaries"))
    regimes = _mapping(payload.get("regime_diagnostic_summary"))
    ce = _mapping(payload.get("ce_shallow_comparison"))
    lines = [
        "# TC Family Final Regime-Aware Refinement Report",
        "",
        "## 1. Executive Summary",
        f"- Decision: {payload.get('decision', 'unavailable')}",
        f"- Summary: {payload.get('executive_summary', 'See diagnostics below.')}",
        "",
        "## 2. Research Scope and Constraints",
    ]
    lines.extend(f"- {item}" for item in payload.get("constraints", ()))
    lines.extend(
        [
            "- This round is proposal-only / diagnostic-only.",
            "- No formalization, no P6, no live trading, and no risk loosening were performed.",
            "- `trend_state` is used only for diagnostic split and proposal-only policy routing.",
            "- Performance metrics use `row_type=closed_trade` only.",
            "",
            "## 3. Previous Refinement Recap",
            "- `bp_shallow_cost_aware_admission_v3` is the baseline source and current best TC family path.",
            "- Global partial capture improved median R but weakened mean and harsh R.",
            "- Momentum failure exit had no useful trigger evidence in the prior round.",
            "- The repaired `trend_state` split showed regime differences that justify this final diagnostic round.",
            _single_performance_table("v3 baseline", baseline),
            "",
            "## 4. Regime Diagnostic Summary",
            _regime_table(regimes),
            f"- Interpretation: {payload.get('regime_interpretation', 'Regime split is diagnostic only.')}",
            "",
            "## 5. Variant Design",
            "- `bp_shallow_regime_diagnostic_no_filter_v1`: no trade changes; replay v3 with complete regime diagnostics.",
            "- `bp_shallow_regime_adaptive_exit_v1`: route proposal-only exit policy by regime without filtering regimes.",
            "- `bp_shallow_regime_cost_gate_v1`: lightly tighten cost gate only inside thin-edge `MEAN_REVERTING_TRANSITION` candidates.",
            "- No asset/profile/direction hand-picking and no direct regime deletion were used.",
            "",
            "## 6. Variant Results",
            _variant_table(variants),
            _path_summary_table(variants),
            "",
            "## 7. Regime Adaptive Exit Analysis",
            _variant_detail(variants, "bp_shallow_regime_adaptive_exit_v1"),
            _regime_variant_table(variants, "bp_shallow_regime_adaptive_exit_v1"),
            "",
            "## 8. Regime Cost Gate Analysis",
            _variant_detail(variants, "bp_shallow_regime_cost_gate_v1"),
            _retained_removed_table(variants.get("bp_shallow_regime_cost_gate_v1", {})),
            "",
            "## 9. Return Quality and Robustness",
            _robustness_table(variants),
            "",
            "## 10. Concentration Risk",
            _concentration_table(variants),
            "",
            "## 11. CE Shallow Diagnostic Comparison",
            _single_performance_table("CE shallow comparison", ce),
            "- CE shallow remains diagnostic-only; no new CE optimization variant was run.",
            "",
            "## 12. Decision",
            f"- {payload.get('decision', 'unavailable')}",
            f"- Rationale: {payload.get('decision_reason', 'See thresholds and diagnostics above.')}",
            "",
            "## 13. Next Action Plan",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("next_actions", ()))
    lines.extend(
        [
            "",
            "## 14. Reproducibility Notes",
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
        "| Variant | MFE median/p75 | MAE median/p75 | Giveback median | MFE>=0.5 | MFE>=1 | Pos MFE loss | Cost flipped |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for key, raw in rows.items():
        row = _mapping(raw)
        path = _mapping(row.get("path_diagnostics")) or row
        lines.append(
            f"| {key} | {_fmt(path.get('MFE_R_median'))}/{_fmt(path.get('MFE_R_p75'))} | "
            f"{_fmt(path.get('MAE_R_median'))}/{_fmt(path.get('MAE_R_p75'))} | {_fmt(path.get('profit_giveback_R_median'))} | "
            f"{_fmt(path.get('reached_0_5R_share'))} | {_fmt(path.get('reached_1R_share'))} | "
            f"{_v(path, 'positive_MFE_but_final_loss')} | {_v(path, 'cost_flipped_to_loss')} |"
        )
    return "\n".join(lines)


def _regime_table(regimes: Mapping[str, object]) -> str:
    lines = [
        "| Regime | Closed | Base R | Stress R | Harsh R | PF | Median R | MFE med | MAE med | Cost/R med | Target ATR med | Asset/Profile/Direction |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, raw in regimes.items():
        row = _mapping(raw)
        lines.append(
            f"| {key} | {_v(row, 'closed')} | {_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | "
            f"{_fmt(row.get('harsh_net_R_avg'))} | {_fmt(row.get('PF'))} | {_fmt(row.get('median_R'))} | "
            f"{_fmt(row.get('MFE_R_median'))} | {_fmt(row.get('MAE_R_median'))} | {_fmt(row.get('cost_per_R_median'))} | "
            f"{_fmt(row.get('target_space_ATR_median'))} | `{row.get('asset_split', {})}` / `{row.get('profile_split', {})}` / `{row.get('direction_split', {})}` |"
        )
    return "\n".join(lines)


def _regime_variant_table(rows: Mapping[str, object], key: str) -> str:
    row = _mapping(rows.get(key))
    return _regime_table(_mapping(row.get("regime_diagnostic_summary")))


def _retained_removed_table(raw: object) -> str:
    row = _mapping(raw)
    cmp = _mapping(row.get("retained_removed_comparison"))
    return "\n".join(
        [
            "| Group | Count | Avg R | Harsh R | Median R | Cost/R | Target ATR |",
            "|---|---:|---:|---:|---:|---:|---:|",
            f"| retained | {_v(cmp, 'retained_count')} | {_fmt(cmp.get('retained_avg_R'))} | {_fmt(cmp.get('retained_harsh_R'))} | {_fmt(cmp.get('retained_median_R'))} | {_fmt(cmp.get('retained_cost_per_R'))} | {_fmt(cmp.get('retained_target_space_ATR'))} |",
            f"| removed | {_v(cmp, 'removed_count')} | {_fmt(cmp.get('removed_avg_R'))} | {_fmt(cmp.get('removed_harsh_R'))} | {_fmt(cmp.get('removed_median_R'))} | {_fmt(cmp.get('removed_cost_per_R'))} | {_fmt(cmp.get('removed_target_space_ATR'))} |",
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


__all__ = ("write_tc_family_final_regime_aware_refinement_report",)
