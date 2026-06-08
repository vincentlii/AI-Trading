from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPORT_FILENAME = "trend_continuation_core_rebuild_report.md"

_VARIANT_METRICS = (
    ("total_windows", "windows"),
    ("structure_zones_found", "zones"),
    ("breakout_event_seeds", "event seeds"),
    ("candidate_ready_windows", "candidate ready"),
    ("raw_candidates", "raw"),
    ("formal_approved", "approved"),
    ("closed_trades", "closed"),
    ("base_net_R_avg", "base avg R"),
    ("stress_net_R_avg", "stress avg R"),
    ("harsh_net_R_avg", "harsh avg R"),
    ("PF", "PF"),
    ("median_R", "median R"),
)

_AUDIT_KEYS = (
    ("full_audit_gate", "Full Audit Gate"),
    ("no_lookahead", "no-lookahead"),
    ("metric_recompute", "metric recompute"),
    ("regression_baseline", "regression baseline"),
    ("robustness", "robustness"),
)

_ENGINE_COMPONENTS = (
    (
        "Structure zone engine",
        "Discovers levels and zones from swings, ranges, compression boundaries, "
        "pivot clusters, prior acceptance/rejection, and local supply/demand evidence.",
    ),
    (
        "Breakout lifecycle",
        "Creates broad event seeds and classifies strong_breakout, accepted_breakout, "
        "weak_but_watch, and failed_breakout. Only failed_breakout is an early terminal state.",
    ),
    (
        "Pullback health",
        "Makes pullback depth, contraction, level hold, time decay, reversal strength, "
        "and retained target space part of the primary signal.",
    ),
    (
        "Relaunch engine",
        "Searches a bounded multi-bar window for micro-break, engulf, two-bar, close-reclaim, "
        "or volume-recovery relaunch evidence.",
    ),
    (
        "Structural stop",
        "Places invalidation outside the retest structure or zone and diagnoses stops that "
        "are structurally too near or too wide before RiskEngine approval.",
    ),
    (
        "Target tradeability",
        "Evaluates the nearest obstacle, structure target, gross RR, cost-adjusted RR, "
        "and cost per R before a candidate may proceed.",
    ),
)


def render_trend_continuation_core_rebuild_report(
    *,
    baseline_summary: Mapping[str, Any],
    variant_summaries: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Render the concentrated decision report from machine-readable summaries.

    The function is read-only and deliberately does not infer performance from
    diagnostic, proposal, or summary rows.
    """

    baseline = dict(baseline_summary)
    variants = _normalize_variants(variant_summaries)
    meta = dict(metadata or {})
    decision, decision_reason = _decision(baseline, variants, meta)
    best_variant = _best_variant(variants)
    previous = _mapping(baseline.get("previous_round"))

    lines: list[str] = [
        "# Trend Continuation Core Rebuild Report",
        "",
        "## 1. Executive Summary",
        "",
        _executive_summary(decision, decision_reason, baseline, variants, best_variant),
        "",
        "- Status: research / diagnostic / proposal-only.",
        "- No formalization. No P6. No live trading.",
        "- LR final evidence remains untouched and is used only as read-only context.",
        "- Performance metrics are valid only when recomputed from `row_type=closed_trade`.",
        "",
        "## 2. Why Previous TC / CE / BP Failed",
        "",
        "The prior implementations repeatedly behaved like hard-filter breakout detectors: "
        "mature-trend or true-breakout gates removed most windows before pullback and relaunch "
        "could express the trade thesis. This round tests the shared event lifecycle instead "
        "of treating every imperfect breakout as terminal.",
        "",
        _previous_round_table(previous),
        "",
        _failure_summary(baseline),
        "",
        "A poor result in this round does not prove the trend-continuation idea invalid. It "
        "identifies which implementation layer still fails to express structure, lifecycle, "
        "pullback, relaunch, stop, or target semantics.",
        "",
        "## 3. Research Scope and Constraints",
        "",
        "- This round is proposal-only and diagnostic-only.",
        "- No formalization, no P6, no live execution, and `live_trading_enabled=false` remains unchanged.",
        "- Formal configuration, cost, slippage, margin, notional cap, portfolio heat, stop, target, and exit boundaries are unchanged.",
        "- LR final evidence remains untouched; historical CE/BP artifacts are diagnostic context only and cannot enter this round's performance.",
        "- Diagnostic, proposal, and summary rows are excluded from performance metrics.",
        "- Performance, robustness, and return-quality statements must use only `row_type=closed_trade` and recomputed metrics.",
        "- Hardened Research Pipeline boundaries remain required: manifest, artifact contract, cross-run fingerprint checks, Full Audit Gate, no-lookahead, metric recompute, robustness, and regression baseline.",
        "",
        "## 4. Rebuilt Shared Engine Design",
        "",
        *_engine_design_lines(),
        "",
        "The core design changes the decision order: breakout is background context; healthy "
        "pullback, relaunch confirmation, structural invalidation, and cost-adjusted tradeability "
        "determine whether an event can become a trade candidate.",
        "",
        "## 5. Structure Zone Diagnostics",
        "",
        _key_value_table(
            baseline,
            (
                ("total_windows", "Total windows"),
                ("structure_zones_found", "Structure zones found"),
                ("windows_with_structure_zone", "Windows with a zone"),
                ("no_structure_zone", "No-structure-zone failures"),
            ),
        ),
        "",
        _distribution_block("Zone type distribution", baseline.get("structure_zone_type_distribution")),
        "",
        _distribution_block("Zone score summary", baseline.get("structure_zone_score_summary")),
        "",
        _interpretation(
            baseline,
            "structure_zone_interpretation",
            "Compare zone coverage and zone-type concentration with the old single-level implementation. "
            "Broad coverage is useful only when later lifecycle and pullback stages remain selective.",
        ),
        "",
        "## 6. Breakout Lifecycle Diagnostics",
        "",
        _key_value_table(
            baseline,
            (
                ("breakout_event_seeds", "Breakout event seeds"),
                ("candidate_ready_windows", "Candidate-ready windows"),
                ("old_true_breakout_failed", "Old true-breakout failures"),
            ),
            fallback=previous,
        ),
        "",
        _distribution_block("Breakout class distribution", baseline.get("breakout_class_distribution")),
        "",
        _distribution_block("Lifecycle failure taxonomy", baseline.get("breakout_failure_taxonomy")),
        "",
        _lifecycle_interpretation(baseline, previous),
        "",
        "## 7. Pullback Health Diagnostics",
        "",
        _distribution_block("Pullback health classes", baseline.get("pullback_health_distribution")),
        "",
        _distribution_block("Pullback types", baseline.get("pullback_type_distribution")),
        "",
        _distribution_block("Pullback score/depth/contraction summary", baseline.get("pullback_diagnostics")),
        "",
        _interpretation(
            baseline,
            "pullback_interpretation",
            "The decision point is whether healthy and acceptable pullbacks now survive long enough "
            "to be assessed, while failed pullbacks remain terminal.",
        ),
        "",
        "## 8. Relaunch Confirmation Diagnostics",
        "",
        _distribution_block("Relaunch quality classes", baseline.get("relaunch_quality_distribution")),
        "",
        _distribution_block("Relaunch types", baseline.get("relaunch_type_distribution")),
        "",
        _distribution_block("Relaunch score and delay summary", baseline.get("relaunch_diagnostics")),
        "",
        _interpretation(
            baseline,
            "relaunch_interpretation",
            "A bounded multi-bar search should recover valid relaunches without allowing stale events. "
            "Compare micro-break, engulf, two-bar, close-reclaim, and volume-recovery evidence.",
        ),
        "",
        "## 9. Structural Stop and Risk Diagnostics",
        "",
        _variant_diagnostic_table(
            variants,
            (
                ("structural_stop_too_near", "structural stop too near"),
                ("structural_stop_too_wide", "structural stop too wide"),
                ("stop_distance_too_near", "RiskEngine stop too near"),
                ("margin_required_too_high", "margin too high"),
            ),
        ),
        "",
        _distribution_block("Stop anchor x reject reason", baseline.get("stop_anchor_reject_cross_table")),
        "",
        _variant_nested_summary(variants, "stop_anchor_reject_cross_table", "Variant stop anchor x reject reason"),
        "",
        _distribution_block("Stop distance ATR x margin", baseline.get("stop_distance_margin_summary")),
        "",
        _interpretation(
            baseline,
            "risk_interpretation",
            "Structural-stop diagnostics must explain invalidation quality before RiskEngine. Margin "
            "rejections must not be repaired by loosening margin rules.",
        ),
        "",
        "## 10. Target and Cost-Adjusted Tradeability",
        "",
        _variant_diagnostic_table(
            variants,
            (
                ("target_space_insufficient", "target space insufficient"),
                ("cost_adjusted_RR_too_low", "cost-adjusted RR too low"),
                ("nearest_obstacle_too_close", "nearest obstacle too close"),
            ),
        ),
        "",
        _distribution_block("Target source distribution", baseline.get("target_source_distribution")),
        "",
        _distribution_block("Target/RR/cost summary", baseline.get("target_tradeability_summary")),
        "",
        "Candidates with poor target space or cost-adjusted RR remain rejected before RiskEngine; "
        "this round does not lower cost or target feasibility standards.",
        "",
        "## 11. Variant Results",
        "",
        _variant_results_table(variants),
        "",
        *_variant_interpretation_lines(variants),
        "",
        "## 12. Subtype Analysis",
        "",
        _distribution_block("Combined subtype split", baseline.get("subtype_split")),
        "",
        _variant_nested_summary(variants, "subtype_split", "Variant subtype summary"),
        "",
        _interpretation(
            baseline,
            "subtype_interpretation",
            "A promising subtype must retain enough closed trades and robustness after separation; "
            "mixed headline performance alone is not evidence for a subtype refactor.",
        ),
        "",
        "## 13. Return Quality and Robustness",
        "",
        _return_quality_table(variants),
        "",
        _audit_table(variants),
        "",
        _variant_nested_summary(variants, "walk_forward", "Walk-forward summary"),
        "",
        "PF and average R are not sufficient alone. Median R, top-winner concentration, results "
        "excluding top one/two trades, cost tiers, walk-forward coverage, and sample size must agree.",
        "",
        "## 14. Asset / Profile / Direction Split",
        "",
        _variant_nested_summary(variants, "asset_profile_direction_split", "Asset/profile/direction summary"),
        "",
        _interpretation(
            baseline,
            "coverage_interpretation",
            "Results materially dependent on one asset, profile, or direction remain diagnostic and "
            "require another bounded validation round.",
        ),
        "",
        "## 15. Decision",
        "",
        f"**{decision}**",
        "",
        decision_reason,
        "",
        "This decision does not formalize breakout_pullback and does not authorize P6.",
        "",
        "## 16. Next Action Plan",
        "",
        *_next_action_lines(decision, meta),
        "",
        "Unchanged boundaries: no risk loosening, no formal configuration changes, no live trading, "
        "no P6, and no use of non-closed rows in performance metrics.",
        "",
        "## 17. Appendix / Reproducibility Notes",
        "",
        f"- run_id: `{_value(meta.get('run_id', baseline.get('run_id', 'not available')))}`",
        f"- manifest summary: {_value(meta.get('manifest_summary'))}",
        f"- cross-run artifact reuse: {_value(meta.get('cross_run_artifact_reuse', baseline.get('cross_run_artifact_reuse')))}",
        f"- row policy: performance metrics use only `row_type=closed_trade`; diagnostic/proposal/summary rows are excluded.",
        f"- Full Audit Gate summary: {_value(meta.get('full_audit_summary', _aggregate_audit(variants, 'full_audit_gate')))}",
        f"- metric recompute summary: {_value(meta.get('metric_recompute_summary', _aggregate_audit(variants, 'metric_recompute')))}",
        "",
        _sequence_block("Required artifact paths", meta.get("artifact_paths")),
        "",
        _sequence_block("Known limitations", meta.get("known_limitations")),
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_trend_continuation_core_rebuild_report(
    *,
    output_dir: Path,
    baseline_summary: Mapping[str, Any],
    variant_summaries: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Write the concentrated report and return its path."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_FILENAME
    report_path.write_text(
        render_trend_continuation_core_rebuild_report(
            baseline_summary=baseline_summary,
            variant_summaries=variant_summaries,
            metadata=metadata,
        ),
        encoding="utf-8",
    )
    return report_path


def _normalize_variants(
    variants: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if isinstance(variants, Mapping):
        return {str(name): dict(summary) for name, summary in variants.items()}
    normalized: dict[str, dict[str, Any]] = {}
    for index, summary in enumerate(variants, start=1):
        row = dict(summary)
        name = str(row.get("variant_id") or row.get("variant") or f"variant_{index}")
        normalized[name] = row
    return normalized


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _value(value: Any) -> str:
    if value is None or value == "":
        return "not available"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _metric(row: Mapping[str, Any], key: str) -> Any:
    aliases = {
        "PF": ("PF", "pf", "profit_factor"),
        "formal_approved": ("formal_approved", "approved", "approved_candidates"),
        "base_net_R_avg": ("base_net_R_avg", "base net_R_avg", "net_R_avg"),
        "stress_net_R_avg": ("stress_net_R_avg", "stress net_R_avg"),
        "harsh_net_R_avg": ("harsh_net_R_avg", "harsh net_R_avg"),
    }
    for candidate in aliases.get(key, (key,)):
        if candidate in row:
            return row[candidate]
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _engine_design_lines() -> list[str]:
    return [f"- **{name}:** {description}" for name, description in _ENGINE_COMPONENTS]


def _previous_round_table(previous: Mapping[str, Any]) -> str:
    return _key_value_table(
        previous,
        (
            ("old_true_breakout_failed", "Old true_breakout failed"),
            ("old_candidate_ready_windows", "Old candidate-ready windows"),
            ("old_raw_candidates", "Old raw candidates"),
            ("ce_semantic_decision", "CE semantic decision"),
        ),
    )


def _key_value_table(
    values: Mapping[str, Any],
    keys: Sequence[tuple[str, str]],
    *,
    fallback: Mapping[str, Any] | None = None,
) -> str:
    lines = ["| Metric | Value |", "|---|---:|"]
    fallback = fallback or {}
    for key, label in keys:
        value = values.get(key, fallback.get(key))
        lines.append(f"| {label} | {_value(value)} |")
    return "\n".join(lines)


def _distribution_block(title: str, value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return f"**{title}:** not available."
    lines = [f"**{title}**", "", "| Item | Value |", "|---|---:|"]
    for key, item in sorted(value.items(), key=lambda entry: str(entry[0])):
        lines.append(f"| {key} | {_value(item)} |")
    return "\n".join(lines)


def _sequence_block(title: str, value: Any) -> str:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return f"**{title}:** not available."
    return "\n".join([f"**{title}**", "", *(f"- {_value(item)}" for item in value)])


def _interpretation(values: Mapping[str, Any], key: str, fallback: str) -> str:
    return str(values.get(key) or fallback)


def _failure_summary(baseline: Mapping[str, Any]) -> str:
    failures = baseline.get("failure_taxonomy")
    if not isinstance(failures, Mapping) or not failures:
        return "**Current top failure taxonomy:** not available."
    ordered = sorted(failures.items(), key=lambda item: _number(item[1]) or 0, reverse=True)
    rendered = ", ".join(f"{key}={_value(value)}" for key, value in ordered[:8])
    return f"**Current top failure taxonomy:** {rendered}."


def _lifecycle_interpretation(baseline: Mapping[str, Any], previous: Mapping[str, Any]) -> str:
    seeds = _number(baseline.get("breakout_event_seeds"))
    ready = _number(baseline.get("candidate_ready_windows"))
    old_ready = _number(previous.get("old_candidate_ready_windows"))
    if ready is not None and old_ready is not None and ready > old_ready:
        return (
            f"Candidate-ready coverage increased from {_value(old_ready)} to {_value(ready)}. "
            "This supports the claim that lifecycle classification reduced premature elimination; "
            "return quality and audits still decide whether the improvement is useful."
        )
    if seeds is not None and seeds > 0:
        return (
            "The lifecycle engine generated event seeds, but the available summary does not show a "
            "clear candidate-ready improvement over the previous implementation."
        )
    return "No evidence is available that lifecycle classification solved premature breakout elimination."


def _variant_results_table(variants: Mapping[str, Mapping[str, Any]]) -> str:
    if not variants:
        return "No proposal-only variant summaries were supplied."
    headers = ["Variant", *[label for _, label in _VARIANT_METRICS]]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for name, row in variants.items():
        values = [name, *[_value(_metric(row, key)) for key, _ in _VARIANT_METRICS]]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _variant_interpretation_lines(variants: Mapping[str, Mapping[str, Any]]) -> list[str]:
    if not variants:
        return ["No variant interpretation is available."]
    return [
        f"- **{name}:** {row.get('interpretation') or 'Interpretation not supplied; retain as diagnostic evidence only.'}"
        for name, row in variants.items()
    ]


def _variant_diagnostic_table(
    variants: Mapping[str, Mapping[str, Any]],
    keys: Sequence[tuple[str, str]],
) -> str:
    if not variants:
        return "No variant diagnostic summaries were supplied."
    headers = ["Variant", *[label for _, label in keys]]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for name, row in variants.items():
        lines.append(
            "| "
            + " | ".join([name, *[_value(row.get(key)) for key, _ in keys]])
            + " |"
        )
    return "\n".join(lines)


def _return_quality_table(variants: Mapping[str, Mapping[str, Any]]) -> str:
    keys = (
        ("closed_trades", "closed"),
        ("total_R", "total R"),
        ("base_net_R_avg", "base avg R"),
        ("stress_net_R_avg", "stress avg R"),
        ("harsh_net_R_avg", "harsh avg R"),
        ("PF", "PF"),
        ("median_R", "median R"),
        ("win_rate", "win rate"),
        ("top_1_trade_R_contribution", "top 1 contribution"),
        ("top_2_trades_R_contribution", "top 2 contribution"),
        ("net_R_avg_excluding_top_1", "avg R excl top 1"),
        ("net_R_avg_excluding_top_2", "avg R excl top 2"),
    )
    return _variant_diagnostic_table(variants, keys)


def _audit_table(variants: Mapping[str, Mapping[str, Any]]) -> str:
    if not variants:
        return "No audit summaries were supplied."
    headers = ["Variant", *[label for _, label in _AUDIT_KEYS]]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for name, row in variants.items():
        lines.append(
            "| "
            + " | ".join([name, *[_value(row.get(key)) for key, _ in _AUDIT_KEYS]])
            + " |"
        )
    return "\n".join(lines)


def _variant_nested_summary(
    variants: Mapping[str, Mapping[str, Any]], key: str, title: str
) -> str:
    lines = [f"**{title}**", ""]
    found = False
    for name, row in variants.items():
        nested = row.get(key)
        if not isinstance(nested, Mapping) or not nested:
            continue
        found = True
        rendered = ", ".join(
            f"{nested_key}={_value(nested_value)}"
            for nested_key, nested_value in sorted(nested.items(), key=lambda item: str(item[0]))
        )
        lines.append(f"- **{name}:** {rendered}")
    if not found:
        lines.append("- not available")
    return "\n".join(lines)


def _best_variant(variants: Mapping[str, Mapping[str, Any]]) -> str | None:
    if not variants:
        return None

    def score(item: tuple[str, Mapping[str, Any]]) -> tuple[float, float, float]:
        _, row = item
        harsh = _number(_metric(row, "harsh_net_R_avg")) or -999.0
        closed = _number(row.get("closed_trades")) or 0.0
        pf = _number(_metric(row, "PF")) or 0.0
        return harsh, closed, pf

    return max(variants.items(), key=score)[0]


def _audits_pass(row: Mapping[str, Any]) -> bool:
    required = ("full_audit_gate", "no_lookahead", "metric_recompute", "regression_baseline")
    return all(str(row.get(key, "")).lower() in {"pass", "passed", "true"} for key in required)


def _decision(
    baseline: Mapping[str, Any],
    variants: Mapping[str, Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> tuple[str, str]:
    supplied = metadata.get("decision")
    supplied_reason = metadata.get("decision_reason")
    if supplied:
        return str(supplied), str(supplied_reason or "Decision supplied by the validated research summary.")

    for name, row in variants.items():
        closed = _number(row.get("closed_trades")) or 0
        base = _number(_metric(row, "base_net_R_avg"))
        stress = _number(_metric(row, "stress_net_R_avg"))
        harsh = _number(_metric(row, "harsh_net_R_avg"))
        pf = _number(_metric(row, "PF"))
        if (
            closed >= 50
            and base is not None
            and stress is not None
            and harsh is not None
            and min(base, stress, harsh) > 0
            and harsh >= 0.05
            and pf is not None
            and pf > 1.2
            and _audits_pass(row)
        ):
            return (
                "B. Core rebuild shows research_candidate potential but requires validation before formalization.",
                f"{name} meets the minimum sample, cost-tier, PF, and audit conditions for research-candidate potential. "
                "A separate validation round remains mandatory.",
            )

    ready = _number(baseline.get("candidate_ready_windows")) or 0
    old_ready = _number(_mapping(baseline.get("previous_round")).get("old_candidate_ready_windows")) or 0
    closed_values = [_number(row.get("closed_trades")) or 0 for row in variants.values()]
    best_closed = max(closed_values, default=0)
    if ready > old_ready and best_closed >= 30:
        return (
            "A. Core rebuild successful; BP remains diagnostic_candidate and one more bounded validation round is allowed.",
            "Lifecycle coverage and closed-trade sample improved, but the supplied evidence does not meet every "
            "research-candidate-potential condition.",
        )
    if ready > old_ready:
        return (
            "D. Core rebuild improves signal count but edge remains weak; keep backlog.",
            "The rebuilt lifecycle improved candidate-ready coverage, but closed-trade quantity or return quality "
            "is insufficient for another validation claim.",
        )
    return (
        "E. Core rebuild fails to solve true_breakout / pullback / stop issues; pause trend continuation family.",
        "The supplied summaries do not demonstrate a material lifecycle and candidate-ready improvement.",
    )


def _executive_summary(
    decision: str,
    reason: str,
    baseline: Mapping[str, Any],
    variants: Mapping[str, Mapping[str, Any]],
    best_variant: str | None,
) -> str:
    seeds = _value(baseline.get("breakout_event_seeds"))
    ready = _value(baseline.get("candidate_ready_windows"))
    return (
        f"**One-line conclusion:** {decision} Breakout lifecycle produced {seeds} event seeds and "
        f"{ready} candidate-ready windows; best bounded variant: `{best_variant or 'not available'}`. "
        f"{reason}"
    )


def _next_action_lines(decision: str, metadata: Mapping[str, Any]) -> list[str]:
    supplied = metadata.get("next_actions")
    if isinstance(supplied, Sequence) and not isinstance(supplied, (str, bytes)) and supplied:
        return [f"{index}. {_value(action)}" for index, action in enumerate(supplied, start=1)]
    if decision.startswith(("A.", "B.")):
        return [
            "1. Preserve the rebuilt core, run at most one bounded validation round, and pre-register its acceptance criteria.",
            "2. Focus only on the strongest evidenced subtype or lifecycle path; do not reopen broad parameter search.",
            "3. Re-run Full Audit Gate, no-lookahead, metric recompute, robustness, regression baseline, and LR complementarity analysis using read-only LR evidence.",
        ]
    if decision.startswith("C."):
        return [
            "1. Refactor only the evidenced subtype into an isolated proposal-only adapter path.",
            "2. Preserve all lifecycle, lineage, structural-stop, and closed-trade audit boundaries.",
            "3. Stop if subtype isolation does not retain sample and cost-tier robustness.",
        ]
    return [
        "1. Preserve manifests, event summaries, closed-trade rows, audits, and this report as backlog evidence.",
        "2. Do not add further local variants until the identified structure/lifecycle/pullback/relaunch/stop gap has a new testable design.",
        "3. Keep trend continuation paused; no formalization or P6 action is authorized.",
    ]


def _aggregate_audit(variants: Mapping[str, Mapping[str, Any]], key: str) -> str:
    if not variants:
        return "not available"
    values = {name: _value(row.get(key)) for name, row in variants.items()}
    return ", ".join(f"{name}={value}" for name, value in values.items())
