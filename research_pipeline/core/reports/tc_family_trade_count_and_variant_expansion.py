from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def write_tc_family_trade_count_report(*, output_dir: Path, payload: Mapping[str, object]) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tc_family_trade_count_and_variant_expansion_report.md"
    variants = payload.get("variant_summaries") if isinstance(payload.get("variant_summaries"), Mapping) else {}
    lines = [
        "# TC Family Trade Count and Variant Expansion Report",
        "",
        "## 1. Executive Summary",
        f"- Decision: {payload.get('decision', 'unavailable')}",
        "- 本轮优先评价交易数、候选转化和策略形态覆盖；收益优化留给后续受限研究。",
        "- 所有结果均为 proposal-only / diagnostic-only，不构成 formalization 或 P6 准入。",
        "",
        "## 2. Research Scope and Constraints",
    ]
    lines.extend(f"- {item}" for item in payload.get("constraints", ()))
    lines.extend(
        [
            "",
            "## 3. Previous Core Rebuild Recap",
            "- Shared lifecycle core 已替代旧 `true_breakout` 一票否决逻辑。",
            "- CE native 不强制 pullback/relaunch；CE shallow 与 BP shallow 保持独立策略形态。",
            "- LR final evidence 只读，本轮绩效不包含 LR、旧 CE 或旧 BP 交易。",
            "",
            "## 4. Capped Risk Sizing Methodology",
            "- 先计算当前 risk-based theoretical size，再按现有 formal single-notional cap 向下截断。",
            "- cap 只能降低仓位和实际风险，不放宽 margin、portfolio heat、stop、target、cost 或 RiskEngine。",
            "- `formal_approved` 保留 cap 前正式判断；proposal 执行资格单独记录为 `proposal_approved_after_cap`。",
            "- cap 后实际风险低于 0.10% equity 的候选不执行，避免仅靠极小仓位制造通过率。",
            "",
            "## 5. Variant Design",
            "- `ce_lifecycle_native_light_confirm_v1`: compression context + lifecycle expansion + light acceptance + structural stop。",
            "- `ce_lifecycle_shallow_momentum_v1`: compression context 作为 shallow pullback/relaunch 的质量过滤器。",
            "- `bp_shallow_momentum_capped_risk_v3`: 独立验证 BP shallow momentum subtype。",
            "",
            "## 6. Signal Funnel and Trade Count Progress",
            _variant_table(variants),
            "",
            "## 7. CE Native Rebuild Analysis",
            _variant_detail(variants, "ce_lifecycle_native_light_confirm_v1"),
            "",
            "## 8. CE Shallow Momentum Analysis",
            _variant_detail(variants, "ce_lifecycle_shallow_momentum_v1"),
            "",
            "## 9. BP Shallow Momentum Validation",
            _variant_detail(variants, "bp_shallow_momentum_capped_risk_v3"),
            "",
            "## 10. RiskEngine and Sizing Diagnostics",
            _sizing_table(variants),
            "- `margin_required_too_high` 的 before/after 对比用于判断 cap 是否只修复 sizing 共因；非 sizing reject 不会被 cap 覆盖。",
            "",
            "## 11. Return Quality and Robustness",
            _return_table(variants),
            _robustness_table(variants),
            "",
            "## 12. Concentration Risk",
            _concentration_table(variants),
            "- 集中度必须结合样本量解释；窄 subtype edge 不等于完整趋势延续家族 edge。",
            "",
            "## 13. Decision",
            f"- {payload.get('decision', 'unavailable')}",
            f"- Rationale: {payload.get('decision_reason', 'See variant data above.')}",
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
            f"- shared_cache_status: `{payload.get('cache_status', {})}`",
            "- Shared cache 仅保存全局去重、紧凑、可重放 lifecycle events；全量事件统计保存在 cache summary。",
            "- Required artifacts:",
        ]
    )
    lines.extend(f"  - `{item}`" for item in payload.get("artifact_paths", ()))
    lines.append("- Known limitations:")
    lines.extend(f"  - {item}" for item in payload.get("known_limitations", ()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def _variant_table(variants: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Entry windows | Evaluated structure windows | Lifecycle seeds | Raw | Formal approved | Proposal approved | Closed | Approved/raw | Closed/approved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant_id, raw in variants.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {variant_id} | {_v(row, 'total_windows')} | {_v(row, 'evaluated_structure_windows')} | {_v(row, 'lifecycle_event_seeds')} | "
            f"{_v(row, 'raw_candidates')} | {_v(row, 'formal_approved')} | "
            f"{_v(row, 'proposal_approved_after_cap')} | {_v(row, 'closed_trades')} | "
            f"{_fmt(row.get('approved_raw'))} | {_fmt(row.get('closed_approved'))} |"
        )
    return "\n".join(lines)


def _return_table(variants: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Base avg R | Stress avg R | Harsh avg R | Total R | PF | Median R | Excl top 1 | Excl top 2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant_id, raw in variants.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {variant_id} | {_fmt(row.get('base_net_R_avg'))} | {_fmt(row.get('stress_net_R_avg'))} | "
            f"{_fmt(row.get('harsh_net_R_avg'))} | {_fmt(row.get('total_R'))} | {_fmt(row.get('PF'))} | "
            f"{_fmt(row.get('median_R'))} | {_fmt(row.get('net_R_avg_excluding_top_1'))} | "
            f"{_fmt(row.get('net_R_avg_excluding_top_2'))} |"
        )
    return "\n".join(lines)


def _robustness_table(variants: Mapping[str, object]) -> str:
    lines = [
        "| Variant | WF positive/negative | Full Audit | No-lookahead | Metric recompute | Regression baseline | Sample warning |",
        "|---|---:|---|---|---|---|---|",
    ]
    for variant_id, raw in variants.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {variant_id} | {_v(row, 'positive_walk_forward_windows')}/{_v(row, 'negative_walk_forward_windows')} | "
            f"{row.get('full_audit_gate', 'unavailable')} | {row.get('no_lookahead', 'unavailable')} | "
            f"{row.get('metric_recompute', 'unavailable')} | {row.get('regression_baseline', 'unavailable')} | "
            f"{row.get('sample_size_warning', True)} |"
        )
    return "\n".join(lines)


def _sizing_table(variants: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Margin high before cap | Margin high after cap | Portfolio heat rejects | Portfolio heat max | Max concurrent | Risk stop near | Risk stop wide | Structural stop near | Structural stop wide | Cap hits |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant_id, raw in variants.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {variant_id} | {_v(row, 'margin_required_too_high_before_cap')} | "
            f"{_v(row, 'margin_required_too_high_after_cap')} | {_v(row, 'portfolio_heat_exceeded_after_cap')} | "
            f"{_fmt(row.get('portfolio_heat_max'))} | {_v(row, 'max_concurrent_positions')} | {_v(row, 'stop_distance_too_near')} | "
            f"{_v(row, 'stop_distance_too_wide')} | {_v(row, 'structural_stop_too_near')} | {_v(row, 'structural_stop_too_wide')} | "
            f"{_v(row, 'capped_by_notional')} |"
        )
    return "\n".join(lines)


def _concentration_table(variants: Mapping[str, object]) -> str:
    lines = [
        "| Variant | Asset split | Profile split | Direction split | Trend state split |",
        "|---|---|---|---|---|",
    ]
    for variant_id, raw in variants.items():
        row = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| {variant_id} | `{row.get('asset_split', {})}` | `{row.get('profile_split', {})}` | "
            f"`{row.get('direction_split', {})}` | `{row.get('trend_state_split', {})}` |"
        )
    return "\n".join(lines)


def _variant_detail(variants: Mapping[str, object], variant_id: str) -> str:
    raw = variants.get(variant_id)
    row = raw if isinstance(raw, Mapping) else {}
    if not row:
        return "- No result."
    return "\n".join(
        [
            f"- raw / proposal approved / closed: {row.get('raw_candidates', 0)} / {row.get('proposal_approved_after_cap', 0)} / {row.get('closed_trades', 0)}",
            f"- breakout classes: `{row.get('breakout_class_distribution', {})}`",
            f"- main reject reasons: `{row.get('reject_reason_distribution', {})}`",
            f"- interpretation: {row.get('interpretation', 'See funnel, sizing, and robustness tables.')}",
        ]
    )


def _v(row: Mapping[str, object], key: str) -> object:
    return row.get(key, 0)


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


__all__ = ("write_tc_family_trade_count_report",)
