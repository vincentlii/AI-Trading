from __future__ import annotations

import bisect
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_pipeline.core.analytics.execution_path import (
    compare_retained_removed_rows,
    enrich_execution_path_rows,
    summarize_execution_path_rows,
)
from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.core.reports.tc_family_cost_aware_refinement_with_trend_state import (
    write_tc_family_cost_aware_refinement_with_trend_state_report,
)
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.strategy_research_validation import (
    _diagnostic_rows,
    _regression_baseline,
    _review_log_rows,
    _robustness_rows,
    _summary_rows,
)
from research_pipeline.runners.tc_family_cost_aware_exit_target import (
    CE_SHALLOW_COMPARISON_ID,
    _cost_aware_score,
    _load_source_artifacts,
    _num,
    _single_dimension_concentration,
    _with_path_summary,
)
from research_pipeline.runners.tc_family_trade_count_expansion import (
    _family_artifact_contract,
    _portfolio_heat_allows,
    _simulate_capped_candidate,
    _tier_preset,
    _variant_summary,
    family_audit_profile,
)
from trading_system.backtest.execution import SignalOrderAdapter, simulate_approved_fill
from trading_system.backtest.layered_cache import read_jsonl, write_json, write_jsonl
from trading_system.backtest.layered_pipeline import _execution_row, _input_from_filter_row
from trading_system.backtest.risk import CostEstimate, RiskDecision, SimulatedOrder
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.trend_price_volume_v1.features import build_market_regime
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION
from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import family_variant_setup
from trading_system.timeframe_profiles import get_profile


BASELINE_VARIANT_ID = "bp_shallow_cost_aware_admission_v2"

REFINEMENT_VARIANT_IDS = (
    "bp_shallow_cost_aware_admission_v3",
    "bp_shallow_cost_aware_partial_capture_v1",
    "bp_shallow_cost_aware_momentum_failure_exit_v1",
)

_UNKNOWN_STATES = {"", "unknown", "UNKNOWN", None}


@dataclass(frozen=True)
class TcFamilyCostAwareRefinementWithTrendStateResult:
    run_id: str
    run_root: str
    baseline_run_root: str
    decision: str
    baseline_summary: dict[str, Any]
    variant_summaries: dict[str, Any]
    trend_state_diagnostics: dict[str, Any]
    ce_shallow_comparison: dict[str, Any]
    report_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_tc_family_cost_aware_refinement_with_trend_state(
    *,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    baseline_run_root: Path,
    output_root: Path,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
    timestamp: datetime | None = None,
) -> TcFamilyCostAwareRefinementWithTrendStateResult:
    baseline_run_root = Path(baseline_run_root)
    output_root = Path(output_root)
    now = timestamp or datetime.now(timezone.utc)
    fingerprint = stable_fingerprint(
        {
            "round": "tc_family_cost_aware_refinement_with_trend_state",
            "baseline_run_root": str(baseline_run_root),
            "dataset_window": dataset_window,
            "config_fingerprint": preset.config_fingerprint,
            "core_engine_version": CORE_ENGINE_VERSION,
            "source_variant": BASELINE_VARIANT_ID,
            "variants": REFINEMENT_VARIANT_IDS,
            "trend_state_lineage": "build_market_regime_entry_safe_v1",
        }
    )
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{fingerprint[:12]}"
    run_root = output_root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    source = _load_source_artifacts(baseline_run_root, BASELINE_VARIANT_ID)
    trend_cache: dict[tuple[str, str, str, str, int], dict[str, object]] = {}
    candle_cache: dict[tuple[str, str, str, str, str], tuple[tuple[int, object], ...]] = {}
    source = _source_with_trend_state(
        source,
        repository=repository,
        trend_cache=trend_cache,
        candle_cache=candle_cache,
    )
    baseline_summary = _with_path_summary(source)
    baseline_summary["trend_state_split"] = _base_trend_state_split(source["closed_rows"])
    trend_state_diagnostics = build_trend_state_lineage_diagnostics(
        candidate_rows=source["candidate_rows"],
        filter_rows=source["filter_rows"],
        closed_rows=source["closed_rows"],
    )
    baseline_summary["trend_state_lineage"] = trend_state_diagnostics
    baseline_summary["trend_state_metrics"] = _trend_state_metrics(source["closed_rows"])
    ce_shallow = _load_ce_shallow_comparison_source(baseline_run_root)
    ce_shallow = _source_with_trend_state(
        ce_shallow,
        repository=repository,
        trend_cache=trend_cache,
        candle_cache=candle_cache,
    )
    ce_shallow_comparison = _with_path_summary(ce_shallow)
    ce_shallow_comparison["trend_state_split"] = _base_trend_state_split(ce_shallow["closed_rows"])
    ce_shallow_comparison["trend_state_metrics"] = _trend_state_metrics(ce_shallow["closed_rows"])

    artifact_paths: list[str] = []
    variant_summaries: dict[str, Any] = {}
    for variant_id in REFINEMENT_VARIANT_IDS:
        output_dir = run_root / "variants" / variant_id
        summary = _run_refinement_variant(
            variant_id=variant_id,
            source=source,
            repository=repository,
            preset=preset,
            dataset_window=dataset_window,
            output_dir=output_dir,
            cost_tiers=tuple(cost_tiers),
        )
        variant_summaries[variant_id] = summary
        artifact_paths.append(str(output_dir))

    decision = select_refinement_decision(variant_summaries, baseline_summary=baseline_summary)
    payload = {
        "run_id": run_id,
        "baseline_run_root": str(baseline_run_root),
        "decision": decision,
        "decision_reason": _decision_reason(decision, baseline_summary, variant_summaries),
        "executive_summary": _executive_summary(decision, baseline_summary, variant_summaries, trend_state_diagnostics),
        "constraints": [
            "proposal-only / diagnostic-only; no formalization and no P6",
            "live_trading_enabled=false; no live order path used",
            "RiskEngine, costs, slippage, margin, notional cap, portfolio heat, formal stop, formal target, and formal exit boundaries remain unchanged",
            "performance metrics use row_type=closed_trade only",
            "diagnostic/proposal/summary rows remain excluded from performance",
            "LR final evidence remains read-only and is not included in this round's performance",
            "capped risk sizing remains proposal-only with minimum actual risk after cap of 0.10% equity",
            "trend_state is diagnostic lineage only and is not used to hand-pick samples",
        ],
        "baseline_summary": baseline_summary,
        "variant_summaries": variant_summaries,
        "trend_state_diagnostics": trend_state_diagnostics,
        "trend_state_interpretation": _trend_state_interpretation(variant_summaries, trend_state_diagnostics),
        "ce_shallow_comparison": ce_shallow_comparison,
        "next_actions": _next_actions(decision),
        "artifact_paths": artifact_paths,
        "known_limitations": [
            "Trend-state repair uses the existing build_market_regime() status at signal/entry-safe cutoff; it does not change historical fills or performance.",
            "Only three bounded performance variants were run; no asset/profile/direction/trend_state hand-picking was applied.",
            "Partial capture and momentum failure exit are proposal-only shadow exits.",
        ],
    }
    report_path = write_tc_family_cost_aware_refinement_with_trend_state_report(output_dir=run_root, payload=payload)
    result = TcFamilyCostAwareRefinementWithTrendStateResult(
        run_id=run_id,
        run_root=str(run_root),
        baseline_run_root=str(baseline_run_root),
        decision=decision,
        baseline_summary=baseline_summary,
        variant_summaries=variant_summaries,
        trend_state_diagnostics=trend_state_diagnostics,
        ce_shallow_comparison=ce_shallow_comparison,
        report_path=str(report_path),
    )
    (run_root / "tc_family_cost_aware_refinement_with_trend_state_result.json").write_text(
        result.as_json() + "\n",
        encoding="utf-8",
    )
    return result


def build_trend_state_lineage_diagnostics(
    *,
    candidate_rows: Sequence[Mapping[str, object]],
    filter_rows: Sequence[Mapping[str, object]],
    closed_rows: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    candidates = [row for row in candidate_rows if row.get("row_type") in {"proposal_candidate", "raw_candidate", "candidate"}]
    filters = list(filter_rows)
    closed = [row for row in closed_rows if row.get("row_type") == "closed_trade"]
    candidate_unknown = _unknown_count(candidates, "trend_state_at_entry")
    filter_unknown = _unknown_count(filters, "trend_state_at_entry")
    closed_unknown = _unknown_count(closed, "trend_state_at_entry")
    return {
        "context_has_trend_state": bool(candidates) and candidate_unknown < len(candidates),
        "event_has_trend_state": bool(candidates) and candidate_unknown < len(candidates),
        "candidate_has_trend_state": bool(candidates) and candidate_unknown < len(candidates),
        "closed_trade_has_trend_state": bool(closed) and closed_unknown < len(closed),
        "candidate_rows": len(candidates),
        "filter_rows": len(filters),
        "closed_trade_rows": len(closed),
        "candidate_trend_state_coverage": _coverage(candidates, candidate_unknown),
        "filter_trend_state_coverage": _coverage(filters, filter_unknown),
        "closed_trade_trend_state_coverage": _coverage(closed, closed_unknown),
        "context_trend_state_coverage": _coverage(candidates, candidate_unknown),
        "event_trend_state_coverage": _coverage(candidates, candidate_unknown),
        "candidate_unknown_share": _share(candidate_unknown, len(candidates)),
        "filter_unknown_share": _share(filter_unknown, len(filters)),
        "closed_trade_unknown_share": _share(closed_unknown, len(closed)),
        "closed_trade_trend_state_split": dict(Counter(_state(row) for row in closed)),
        "missing_reason": dict(Counter(str(row.get("trend_state_missing_reason") or "") for row in closed if _state(row) == "unknown")),
    }


def select_refinement_decision(
    variant_summaries: Mapping[str, Mapping[str, object]],
    *,
    baseline_summary: Mapping[str, object] | None = None,
) -> str:
    best_key, best = max(
        variant_summaries.items(),
        key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0,
        default=("", {}),
    )
    unknown_share = _num(_mapping(best.get("trend_state_lineage")).get("closed_trade_unknown_share")) or 1.0
    if (
        int(best.get("closed_trades") or 0) >= 350
        and (_num(best.get("base_net_R_avg")) or -999.0) > 0
        and (_num(best.get("stress_net_R_avg")) or -999.0) > 0
        and (_num(best.get("harsh_net_R_avg")) or -999.0) >= 0.02
        and (_num(best.get("median_R")) or -999.0) >= 0
        and (_num(best.get("PF")) or 0.0) > 1.2
        and (_num(best.get("net_R_avg_excluding_top_1")) or -999.0) > 0
        and (_num(best.get("net_R_avg_excluding_top_2")) or -999.0) > 0
        and int(best.get("positive_walk_forward_windows") or 0) >= 4
        and best.get("full_audit_gate") == "passed"
        and best.get("no_lookahead") == "passed"
        and best.get("metric_recompute") == "passed"
        and not best.get("single_dimension_concentration")
        and unknown_share < 0.05
    ):
        return "A. BP shallow has validation-prep potential; run bounded validation-prep next."
    baseline_harsh = _num((baseline_summary or {}).get("harsh_net_R_avg")) or -999.0
    if (_num(best.get("harsh_net_R_avg")) or -999.0) >= -0.005 and _trend_state_split_has_signal(best):
        return "B. Refinement improved edge but still needs one final regime-aware diagnostic round."
    if best_key == "bp_shallow_cost_aware_admission_v3" and (_num(best.get("harsh_net_R_avg")) or -999.0) > baseline_harsh:
        return "C. Cost-aware mechanism helps but harsh remains too thin; keep diagnostic only."
    partial = variant_summaries.get("bp_shallow_cost_aware_partial_capture_v1", {})
    failure = variant_summaries.get("bp_shallow_cost_aware_momentum_failure_exit_v1", {})
    if (
        (_num(partial.get("harsh_net_R_avg")) or -999.0) <= baseline_harsh
        and (_num(failure.get("harsh_net_R_avg")) or -999.0) <= baseline_harsh
    ):
        return "D. Partial capture / failure exit failed; retain v2 and stop refinement."
    return "E. No variant improves enough; pause TC family and move to simpler baseline later."


def _run_refinement_variant(
    *,
    variant_id: str,
    source: Mapping[str, Any],
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_dir: Path,
    cost_tiers: Sequence[str],
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = tuple(dict(row, variant_id=variant_id, source_variant_id=BASELINE_VARIANT_ID) for row in source["candidate_rows"])
    filter_rows = _prepare_filter_rows(source["filter_rows"], variant_id=variant_id)
    if variant_id == "bp_shallow_cost_aware_admission_v3":
        _apply_cost_aware_admission_v3(filter_rows)
    closed_rows = _execute_refinement_variant(
        variant_id=variant_id,
        repository=repository,
        preset=preset,
        filter_rows=filter_rows,
        cost_tiers=cost_tiers,
    )
    enriched = enrich_execution_path_rows(closed_rows)
    path_summary = summarize_execution_path_rows(enriched)
    variant_diagnostics = _variant_specific_diagnostics(variant_id, enriched, source, filter_rows)
    if variant_id == "bp_shallow_cost_aware_admission_v3":
        path_summary["retained_removed_comparison"] = variant_diagnostics["retained_removed_comparison"]
    robustness_rows = _robustness_rows(closed_rows)
    summary_rows = _summary_rows(candidate_rows, filter_rows, closed_rows)
    trend_lineage = build_trend_state_lineage_diagnostics(
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
    )
    diagnostic_rows = (
        *_diagnostic_rows(filter_rows, candidate_rows, closed_rows),
        {
            "row_type": "diagnostic_only",
            "diagnostic_only": True,
            "eligible_for_performance": False,
            "diagnostic_name": "tc_family_cost_aware_refinement_with_trend_state",
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "path_summary": path_summary,
            "variant_diagnostics": variant_diagnostics,
            "trend_state_lineage": trend_lineage,
        },
    )
    review_log_rows = _review_log_rows(
        strategy=family_variant_setup("bp_shallow_momentum_capped_risk_v3"),
        pass_name=variant_id,
        summary_rows=summary_rows,
        diagnostic_rows=diagnostic_rows,
        anatomy_summary=path_summary,
    )
    regression_baseline = _regression_baseline(summary_rows)
    write_jsonl(output_dir / "candidate_rows.jsonl", candidate_rows)
    write_jsonl(output_dir / "filter_results_research.jsonl", filter_rows)
    write_jsonl(output_dir / "closed_trade_rows.jsonl", closed_rows)
    write_jsonl(output_dir / "execution_path_diagnostics.jsonl", enriched)
    write_json(output_dir / "execution_path_summary.json", path_summary)
    write_json(output_dir / "variant_diagnostics.json", variant_diagnostics)
    write_json(output_dir / "trend_state_lineage_diagnostics.json", trend_lineage)
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_log_rows)
    write_json(output_dir / "regression_baseline.json", regression_baseline)
    setup = family_variant_setup("bp_shallow_momentum_capped_risk_v3")
    manifest = RunManifest(
        run_id=stable_fingerprint({"variant_id": variant_id, "output_dir": str(output_dir)})[:24],
        strategy=setup,
        adapter_version=f"tc_family_cost_aware_refinement_with_trend_state.v1+{CORE_ENGINE_VERSION}",
        dataset_window=dataset_window,
        artifact_contract=_family_artifact_contract().as_dict(),
        audit_profile=family_audit_profile("bp_shallow_momentum_capped_risk_v3").as_dict(),
        artifact_paths={
            "candidate_rows": str(output_dir / "candidate_rows.jsonl"),
            "filter_results": str(output_dir / "filter_results_research.jsonl"),
            "execution_rows": str(output_dir / "closed_trade_rows.jsonl"),
            "closed_trade_rows": str(output_dir / "closed_trade_rows.jsonl"),
            "diagnostic_rows": str(output_dir / "diagnostic_rows.jsonl"),
            "summary_rows": str(output_dir / "summary_rows.jsonl"),
            "robustness_rows": str(output_dir / "robustness_rows.jsonl"),
            "regression_baseline": str(output_dir / "regression_baseline.json"),
            "review_log_rows": str(output_dir / "review_log_rows.jsonl"),
            "trend_state_lineage_diagnostics": str(output_dir / "trend_state_lineage_diagnostics.json"),
        },
        config_snapshot={
            "config_version": preset.config_version,
            "config_fingerprint": preset.config_fingerprint,
            "setup_filter": [setup],
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "exit_policy": _exit_policy_name(variant_id),
            "trend_state_lineage_policy": "build_market_regime_entry_safe_v1",
        },
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="TC family cost-aware refinement with trend-state lineage; proposal-only shadow replay.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=setup,
        stage=f"tc_family_cost_aware_refinement_with_trend_state_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-cost-aware-refinement-with-trend-state",
        config_hash=preset.config_fingerprint,
        notes="Proposal-only TC family cost-aware refinement; LR final evidence untouched.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=setup,
        stage=f"tc_family_cost_aware_refinement_with_trend_state_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-cost-aware-refinement-with-trend-state",
        adapter_version=manifest.adapter_version,
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        config_hash=preset.config_fingerprint,
        notes="Proposal-only cost-aware refinement with trend-state lineage.",
        tags=["tc_family", variant_id, "trend_state"],
    )
    audit = run_full_pipeline_audit(strategy=setup, artifact_dir=output_dir, registry=None, output_dir=output_dir / "full_audit")
    summary = _variant_summary(
        variant_id="bp_shallow_momentum_capped_risk_v3",
        cache_status={"reused": True, "baseline_ref": str(source["variant_dir"])},
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
        robustness_rows=robustness_rows,
        audit=audit,
    )
    summary.update(
        {
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "setup_id": setup,
            "path_diagnostics": path_summary,
            "variant_diagnostics": variant_diagnostics,
            "retained_removed_comparison": variant_diagnostics.get("retained_removed_comparison", {}),
            "trend_state_lineage": trend_lineage,
            "trend_state_metrics": _trend_state_metrics(closed_rows),
            "interpretation": _interpret_variant(variant_id, summary, path_summary, variant_diagnostics, trend_lineage),
            "single_dimension_concentration": _single_dimension_concentration(summary),
        }
    )
    write_json(output_dir / "variant_summary.json", summary)
    return summary


def _load_ce_shallow_comparison_source(baseline_run_root: Path) -> dict[str, Any]:
    try:
        return _load_source_artifacts(baseline_run_root, CE_SHALLOW_COMPARISON_ID)
    except FileNotFoundError:
        result_path = baseline_run_root / "tc_family_cost_aware_exit_target_result.json"
        if not result_path.exists():
            raise
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        prior_root = payload.get("baseline_run_root")
        if not prior_root:
            raise
        return _load_source_artifacts(Path(prior_root), CE_SHALLOW_COMPARISON_ID)


def _execute_refinement_variant(
    *,
    variant_id: str,
    repository,
    preset: BacktestPresetConfig,
    filter_rows: list[dict[str, object]],
    cost_tiers: Sequence[str],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    scheduling_tier = "base" if "base" in cost_tiers else str(cost_tiers[0])
    scheduling_preset = _cost_tier_preset(preset, scheduling_tier, variant_id)
    accepted_ids: set[str] = set()
    open_intervals: list[tuple[int, int, float]] = []
    ordered = sorted(filter_rows, key=lambda row: (int(row.get("timestamp_ms") or 0), str(row.get("candidate_id") or "")))
    for candidate in ordered:
        if not candidate.get("proposal_approved_after_cap"):
            candidate["proposal_execution_status"] = "not_approved_after_cap"
            continue
        closed, reject = _simulate_refinement_candidate(
            repository=repository,
            candidate=candidate,
            tier_preset=scheduling_preset,
            tier_name=scheduling_tier,
            variant_id=variant_id,
        )
        if closed is None:
            candidate["proposal_execution_status"] = "not_executed"
            candidate["proposal_execution_reject_reason"] = reject
            continue
        if not _portfolio_heat_allows(
            open_intervals,
            entry_time=int(closed["entry_time"]),
            exit_time=int(closed["exit_time"]),
            risk_pct=float(closed["actual_risk_after_cap_pct"]),
            max_heat_pct=preset.risk.max_portfolio_heat_pct,
        ):
            candidate["proposal_approved_after_cap"] = False
            candidate["approved_after_cap"] = False
            candidate["risk_reject_reason_after_cap"] = "portfolio_heat_exceeded_after_cap"
            candidate["proposal_execution_status"] = "not_executed"
            candidate["proposal_execution_reject_reason"] = "portfolio_heat_exceeded_after_cap"
            continue
        accepted_ids.add(str(candidate.get("candidate_id") or ""))
        open_intervals.append((int(closed["entry_time"]), int(closed["exit_time"]), float(closed["actual_risk_after_cap_pct"])))
        candidate["proposal_execution_status"] = "closed"
        candidate["proposal_execution_reject_reason"] = ""
        rows.append(closed)
    for tier_name in cost_tiers:
        if tier_name == scheduling_tier:
            continue
        tier_preset = _cost_tier_preset(preset, tier_name, variant_id)
        for candidate in ordered:
            if str(candidate.get("candidate_id") or "") not in accepted_ids:
                continue
            closed, _ = _simulate_refinement_candidate(
                repository=repository,
                candidate=candidate,
                tier_preset=tier_preset,
                tier_name=tier_name,
                variant_id=variant_id,
            )
            if closed is not None:
                rows.append(closed)
    return tuple(rows)


def _simulate_refinement_candidate(
    *,
    repository,
    candidate: Mapping[str, object],
    tier_preset: BacktestPresetConfig,
    tier_name: str,
    variant_id: str,
) -> tuple[dict[str, object] | None, str]:
    if variant_id == "bp_shallow_cost_aware_admission_v3":
        closed, reject = _simulate_capped_candidate(repository=repository, candidate=candidate, tier_preset=tier_preset, tier_name=tier_name)
        if closed is not None:
            closed["exit_policy"] = _exit_policy_name(variant_id)
            _copy_trend_state(candidate, closed)
        return closed, reject
    signal_input = _input_from_filter_row(repository, candidate, tier_preset)
    if signal_input is None:
        return None, "missing_execution_candles"
    intent, atr, reasons = SignalOrderAdapter().to_order_intent(
        signal_input.signal,
        signal_input.execution_candles,
        point_value=tier_preset.execution.point_value,
    )
    if intent is None or atr is None or reasons:
        return None, ",".join(reasons) or "execution_adapter_rejected"
    point_value = tier_preset.execution.point_value
    cap_notional = float(candidate.get("capped_notional") or 0.0)
    cap_risk = float(candidate.get("actual_risk_after_cap") or 0.0)
    quantity = min(
        float(candidate.get("capped_position_size") or 0.0),
        cap_notional / max(abs(intent.entry_price * point_value), 1e-12),
        cap_risk / max(intent.stop_distance * point_value, 1e-12),
    )
    notional = abs(quantity * intent.entry_price * point_value)
    actual_risk = quantity * intent.stop_distance * point_value
    actual_risk_pct = actual_risk / max(tier_preset.execution.initial_equity, 1e-12)
    margin_required = notional / max(tier_preset.risk.max_total_gross_leverage, 1e-12)
    if actual_risk_pct < 0.001:
        return None, "actual_risk_after_cap_below_minimum"
    if margin_required > tier_preset.execution.initial_equity:
        return None, "margin_required_too_high_after_cap"
    order = SimulatedOrder(
        intent=intent,
        quantity=quantity,
        notional_value=notional,
        risk_amount=actual_risk,
        cost_estimate=CostEstimate(),
    )
    decision = RiskDecision(status="approved", reason_codes=(), risk_pct=actual_risk_pct, risk_amount=actual_risk, approved_order=order)
    execution_candles = signal_input.execution_candles
    failure_exit = False
    if variant_id == "bp_shallow_cost_aware_momentum_failure_exit_v1" and _momentum_failure_exit(candidate, intent, execution_candles):
        execution_candles = execution_candles[: min(8, len(execution_candles))]
        failure_exit = True
    fill = simulate_approved_fill(
        risk_decision=decision,
        execution_candles=execution_candles,
        config=tier_preset.to_execution_config(),
        atr=atr,
        lineage={
            "candidate_id": candidate.get("candidate_id"),
            "event_id": candidate.get("event_id"),
            "feature_cutoff_time": candidate.get("feature_cutoff_time"),
            "structure_confirmed_time": candidate.get("structure_confirmed_time"),
            "sweep_time": candidate.get("sweep_timestamp_ms"),
            "reclaim_time": candidate.get("reclaim_timestamp_ms"),
            "signal_time": candidate.get("signal_time"),
            "bar_confirmed": candidate.get("bar_confirmed", True),
            "no_lookahead_safe": candidate.get("no_lookahead_safe", True),
        },
    )
    closed = _execution_row(candidate, fill, tier_name)
    closed.update(
        {
            "variant_id": variant_id,
            "proposal_approved_after_cap": True,
            "approval_basis": "proposal_approved_after_cap",
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "exit_policy": _exit_policy_name(variant_id),
            "capped_position_size": quantity,
            "capped_notional": notional,
            "margin_required_after_cap": margin_required,
            "actual_risk_after_cap": actual_risk,
            "actual_risk_after_cap_pct": actual_risk_pct,
            "portfolio_heat": actual_risk_pct,
            "proposal_momentum_failure_exit_triggered": failure_exit,
        }
    )
    if failure_exit and closed.get("exit_reason") == "time_exit":
        closed["exit_reason"] = "proposal_momentum_failure_exit"
    _copy_trend_state(candidate, closed)
    return closed, ""


def _source_with_trend_state(
    source: Mapping[str, Any],
    *,
    repository,
    trend_cache: dict[tuple[str, str, str, str, int], dict[str, object]],
    candle_cache: dict[tuple[str, str, str, str, str], tuple[tuple[int, object], ...]],
) -> dict[str, Any]:
    candidate_rows = [
        _enrich_row_trend_state(dict(row), repository=repository, trend_cache=trend_cache, candle_cache=candle_cache)
        for row in source["candidate_rows"]
    ]
    state_by_candidate = {str(row.get("candidate_id") or ""): row for row in candidate_rows}
    filter_rows = []
    for row in source["filter_rows"]:
        payload = _enrich_row_trend_state(dict(row), repository=repository, trend_cache=trend_cache, candle_cache=candle_cache)
        source_candidate = state_by_candidate.get(str(payload.get("candidate_id") or ""))
        if source_candidate is not None:
            _copy_trend_state(source_candidate, payload)
        filter_rows.append(payload)
    closed_rows = []
    state_by_filter = {str(row.get("candidate_id") or ""): row for row in filter_rows}
    for row in source["closed_rows"]:
        payload = dict(row)
        source_filter = state_by_filter.get(str(payload.get("candidate_id") or ""))
        if source_filter is not None:
            _copy_trend_state(source_filter, payload)
        else:
            payload = _enrich_row_trend_state(payload, repository=repository, trend_cache=trend_cache, candle_cache=candle_cache)
        closed_rows.append(payload)
    return {
        **dict(source),
        "candidate_rows": tuple(candidate_rows),
        "filter_rows": tuple(filter_rows),
        "closed_rows": tuple(closed_rows),
    }


def _enrich_row_trend_state(
    row: dict[str, object],
    *,
    repository,
    trend_cache: dict[tuple[str, str, str, str, int], dict[str, object]],
    candle_cache: dict[tuple[str, str, str, str, str], tuple[tuple[int, object], ...]],
) -> dict[str, object]:
    entry_cutoff = _safe_entry_cutoff(row)
    breakout_cutoff = _int(row.get("breakout_time")) or entry_cutoff
    pullback_cutoff = _int(row.get("pullback_end_time")) or entry_cutoff
    relaunch_cutoff = _int(row.get("relaunch_time")) or entry_cutoff
    for field, cutoff in (
        ("trend_state_at_breakout", breakout_cutoff),
        ("trend_state_at_pullback", pullback_cutoff),
        ("trend_state_at_relaunch", relaunch_cutoff),
        ("trend_state_at_entry", entry_cutoff),
        ("trend_state_at_signal", _int(row.get("signal_time")) or entry_cutoff),
    ):
        state = _existing_state(row, field)
        if state == "unknown":
            resolved = _resolve_trend_state(row, cutoff, repository=repository, trend_cache=trend_cache, candle_cache=candle_cache)
            row[field] = resolved["trend_state"]
            row[f"{field}_direction"] = resolved["trend_direction"]
            row[f"{field}_source"] = resolved["source"]
            if resolved["trend_state"] == "unknown":
                row["trend_state_missing_reason"] = resolved["reason"]
    row["trend_state"] = row.get("trend_state_at_entry", row.get("trend_state", "unknown"))
    row["trend_direction"] = row.get("trend_state_at_entry_direction", row.get("trend_direction", ""))
    return row


def _resolve_trend_state(
    row: Mapping[str, object],
    cutoff: int,
    *,
    repository,
    trend_cache: dict[tuple[str, str, str, str, int], dict[str, object]],
    candle_cache: dict[tuple[str, str, str, str, str], tuple[tuple[int, object], ...]],
) -> dict[str, object]:
    profile_key = str(row.get("profile") or "")
    inst_id = str(row.get("inst_id") or row.get("symbol") or "")
    venue = str(row.get("venue") or "okx")
    inst_type = str(row.get("inst_type") or "SPOT")
    if not profile_key or not inst_id or cutoff <= 0:
        return {"trend_state": "unknown", "trend_direction": "", "source": "build_market_regime", "reason": "missing_profile_inst_or_cutoff"}
    try:
        profile = get_profile(profile_key)
    except Exception:
        return {"trend_state": "unknown", "trend_direction": "", "source": "build_market_regime", "reason": "unknown_profile"}
    key = (venue, inst_type, inst_id, profile_key, cutoff)
    if key in trend_cache:
        return trend_cache[key]
    candles_key = (venue, inst_type, inst_id, profile.trend_timeframe, profile_key)
    if candles_key not in candle_cache:
        candles = repository.list_candles(inst_id, profile.trend_timeframe, venue=venue, inst_type=inst_type)
        if not candles and profile.trend_timeframe.upper() != profile.trend_timeframe:
            candles = repository.list_candles(inst_id, profile.trend_timeframe.upper(), venue=venue, inst_type=inst_type)
        candle_cache[candles_key] = tuple((int(getattr(candle, "timestamp_ms")), candle) for candle in candles)
    candles_with_ts = candle_cache[candles_key]
    timestamps = [item[0] for item in candles_with_ts]
    end = bisect.bisect_right(timestamps, cutoff)
    trend_candles = tuple(item[1] for item in candles_with_ts[max(0, end - 260) : end])
    regime = build_market_regime(trend_candles)
    if regime is None:
        result = {
            "trend_state": "unknown",
            "trend_direction": "",
            "source": "build_market_regime",
            "reason": "insufficient_confirmed_trend_candles",
        }
    else:
        result = {
            "trend_state": regime.status,
            "trend_direction": regime.direction or "",
            "source": "build_market_regime",
            "reason": "",
        }
    trend_cache[key] = result
    return result


def _prepare_filter_rows(rows: Sequence[Mapping[str, object]], *, variant_id: str) -> list[dict[str, object]]:
    prepared = []
    for row in rows:
        payload = dict(row)
        payload["source_variant_id"] = payload.get("variant_id")
        payload["variant_id"] = variant_id
        payload["optimization_variant"] = variant_id
        payload["proposal_only"] = True
        payload["formal_conclusion_enabled"] = False
        if payload.get("proposal_approved_after_cap"):
            payload["retained_by_v2_cost_aware_admission"] = True
        prepared.append(payload)
    return prepared


def _apply_cost_aware_admission_v3(filter_rows: list[dict[str, object]]) -> None:
    approved = [row for row in filter_rows if row.get("proposal_approved_after_cap")]
    scored = []
    for row in approved:
        score = _cost_aware_score_v3(row)
        row["cost_aware_admission_v3_score"] = score
        scored.append(score)
    if not scored:
        return
    threshold = sorted(scored)[max(0, int(len(scored) * 0.12) - 1)]
    for row in approved:
        if float(row.get("cost_aware_admission_v3_score") or 0.0) <= threshold:
            row["proposal_approved_after_cap"] = False
            row["approved_after_cap"] = False
            row["removed_by_cost_aware_admission_v3"] = True
            row["risk_reject_reason_after_cap"] = "cost_aware_admission_v3_low_edge"
            row["reject_reason"] = "cost_aware_admission_v3_low_edge"
        else:
            row["retained_by_cost_aware_admission_v3"] = True


def _cost_aware_score_v3(row: Mapping[str, object]) -> float:
    base = _cost_aware_score(row)
    cost_adjusted = _num(row.get("cost_adjusted_RR")) or _num(row.get("cost_adjusted_rr")) or 0.0
    target_quality = 0.1 if str(row.get("target_quality_class") or "") == "good" else 0.0
    stop_quality = 0.1 if str(row.get("structural_stop_quality") or "") == "valid" else -0.2
    cap_penalty = 0.04 if row.get("capped_by_notional") else 0.0
    actual_risk = _num(row.get("actual_risk_after_cap_pct")) or 0.0
    min_risk_penalty = 0.08 if 0 < actual_risk < 0.0015 else 0.0
    return base + min(cost_adjusted / 2.0, 0.25) + target_quality + stop_quality - cap_penalty - min_risk_penalty


def _cost_tier_preset(preset: BacktestPresetConfig, tier_name: str, variant_id: str) -> BacktestPresetConfig:
    tier = _tier_preset(preset, tier_name)
    execution = tier.execution
    if variant_id == "bp_shallow_cost_aware_partial_capture_v1":
        execution = replace(
            execution,
            enable_advanced_exits=True,
            partial_take_profit_r=0.5,
            partial_take_profit_pct=0.35,
            move_stop_to_true_breakeven=True,
            breakeven_after_mfe_r=0.5,
            chandelier_period=5,
            chandelier_atr_multiple=2.5,
        )
    return replace(tier, execution=execution)


def _momentum_failure_exit(candidate: Mapping[str, object], intent, candles: Sequence[object]) -> bool:
    if not candles:
        return False
    window = tuple(candles[: min(8, len(candles))])
    early_mfe = _mfe_r(intent, window)
    if early_mfe >= 0.30:
        return False
    last_close = float(getattr(window[-1], "close"))
    entry = float(intent.entry_price)
    micro_level = _num(candidate.get("relaunch_close")) or entry
    cost_per_r = _num(candidate.get("cost_per_R")) or 0.0
    target_atr = _num(candidate.get("target_space_atr")) or _num(candidate.get("target_space_ATR")) or 999.0
    if intent.direction == "LONG":
        close_back = last_close < min(entry, micro_level)
        threatened_stop = min(float(getattr(candle, "low")) for candle in window) <= entry - intent.stop_distance * 0.55
        engulfed = len(window) >= 2 and float(getattr(window[-1], "close")) < float(getattr(window[-2], "open"))
    else:
        close_back = last_close > max(entry, micro_level)
        threatened_stop = max(float(getattr(candle, "high")) for candle in window) >= entry + intent.stop_distance * 0.55
        engulfed = len(window) >= 2 and float(getattr(window[-1], "close")) > float(getattr(window[-2], "open"))
    thin_edge = cost_per_r >= 0.20 or target_atr <= 1.0
    return bool((close_back or threatened_stop or engulfed) and thin_edge)


def _variant_specific_diagnostics(
    variant_id: str,
    enriched: Sequence[Mapping[str, object]],
    source: Mapping[str, Any],
    filter_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    closed = [row for row in enriched if row.get("row_type") == "closed_trade"]
    if variant_id == "bp_shallow_cost_aware_admission_v3":
        retained_ids = {str(row.get("candidate_id") or "") for row in filter_rows if row.get("proposal_approved_after_cap")}
        baseline = []
        for row in source["closed_rows"]:
            payload = dict(row)
            if str(payload.get("candidate_id") or "") in retained_ids:
                payload["retained_by_admission"] = True
            else:
                payload["removed_by_admission"] = True
            baseline.append(payload)
        return {
            "admission_policy": "entry-known v3 cost/space score removes weakest 12% of v2 retained candidates",
            "retained_removed_comparison": compare_retained_removed_rows(enrich_execution_path_rows(baseline)),
        }
    if variant_id == "bp_shallow_cost_aware_partial_capture_v1":
        triggered = [row for row in closed if row.get("partial_take_profit_hit")]
        mfe_one = [row for row in closed if (_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0) >= 1.0]
        return {
            "capture_policy": "v2 retained only; 0.50R partial_take_profit_35pct + cost-adjusted breakeven + loose chandelier",
            "capture_trigger_count": len(triggered),
            "partial_TP_count": len(triggered),
            "breakeven_move_count": sum(1 for row in closed if row.get("moved_to_breakeven")),
            "final_loss_after_capture_count": sum(1 for row in triggered if (_num(row.get("final_R")) or _num(row.get("net_R")) or 0.0) <= 0),
            "MFE_ge_1R_count": len(mfe_one),
            "MFE_ge_1R_avg_R": _avg([_num(row.get("final_R")) or _num(row.get("net_R")) for row in mfe_one]),
        }
    if variant_id == "bp_shallow_cost_aware_momentum_failure_exit_v1":
        stopped = [row for row in closed if row.get("proposal_momentum_failure_exit_triggered")]
        mfe_one_stopped = [row for row in stopped if (_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0) >= 1.0]
        return {
            "failure_exit_policy": "exit only when first 8 bars show MFE<0.30R plus close-back/threatened-stop/engulf evidence and thin cost/target edge",
            "failure_exit_trigger_count": len(stopped),
            "avg_R_of_failure_exited_trades": _avg([_num(row.get("final_R")) or _num(row.get("net_R")) for row in stopped]),
            "MFE_ge_1R_wrong_exit_count": len(mfe_one_stopped),
            "bars_to_exit_distribution": _counts([row.get("bars_in_trade") or row.get("holding_bars") for row in stopped]),
        }
    return {}


def _trend_state_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    base = [row for row in rows if row.get("row_type") == "closed_trade" and str(row.get("cost_tier") or "base") == "base"]
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in base:
        groups[_state(row)].append(row)
    result: dict[str, dict[str, object]] = {}
    for state, items in sorted(groups.items()):
        net = [_num(row.get("net_R")) or 0.0 for row in items]
        wins = [value for value in net if value > 0]
        losses = [value for value in net if value < 0]
        result[state] = {
            "closed": len(items),
            "avg_R": _avg(net),
            "median_R": _median(net),
            "PF": (sum(wins) / abs(sum(losses))) if losses else None,
            "win_rate": _share(len(wins), len(items)),
            "MFE_median": _median([_num(row.get("mfe_R")) or _num(row.get("MFE_R")) or 0.0 for row in items]),
            "MAE_median": _median([_num(row.get("mae_R")) or _num(row.get("MAE_R")) or 0.0 for row in items]),
            "cost_per_R_median": _median([_num(row.get("cost_per_R")) or 0.0 for row in items]),
        }
    return result


def _base_trend_state_split(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return dict(
        Counter(
            _state(row)
            for row in rows
            if row.get("row_type") == "closed_trade" and str(row.get("cost_tier") or "base") == "base"
        )
    )


def _copy_trend_state(source: Mapping[str, object], target: dict[str, object]) -> None:
    for key in (
        "trend_state_at_breakout",
        "trend_state_at_breakout_direction",
        "trend_state_at_pullback",
        "trend_state_at_pullback_direction",
        "trend_state_at_relaunch",
        "trend_state_at_relaunch_direction",
        "trend_state_at_entry",
        "trend_state_at_entry_direction",
        "trend_state_at_signal",
        "trend_state_at_signal_direction",
        "trend_state_missing_reason",
    ):
        if key in source:
            target[key] = source[key]
    target["trend_state"] = source.get("trend_state_at_entry", source.get("trend_state", "unknown"))
    target["trend_direction"] = source.get("trend_state_at_entry_direction", source.get("trend_direction", ""))


def _exit_policy_name(variant_id: str) -> str:
    if variant_id == "bp_shallow_cost_aware_partial_capture_v1":
        return "proposal_cost_aware_partial_capture_0_50r_35pct_breakeven_loose_trailing"
    if variant_id == "bp_shallow_cost_aware_momentum_failure_exit_v1":
        return "proposal_cost_aware_momentum_failure_exit_evidence_based"
    if variant_id == "bp_shallow_cost_aware_admission_v3":
        return "proposal_cost_aware_admission_v3_entry_known_refinement"
    return "baseline"


def _interpret_variant(
    variant_id: str,
    summary: Mapping[str, object],
    path: Mapping[str, object],
    diagnostics: Mapping[str, object],
    trend_lineage: Mapping[str, object],
) -> str:
    return (
        f"{variant_id}: closed={summary.get('closed_trades', 0)}, "
        f"base/stress/harsh={summary.get('base_net_R_avg')}/{summary.get('stress_net_R_avg')}/{summary.get('harsh_net_R_avg')}, "
        f"median_R={summary.get('median_R')}, MFE_avg={path.get('MFE_R_avg')}, "
        f"trend_unknown={trend_lineage.get('closed_trade_unknown_share')}, diagnostics={diagnostics}."
    )


def _trend_state_interpretation(variants: Mapping[str, Mapping[str, object]], lineage: Mapping[str, object]) -> str:
    if (_num(lineage.get("closed_trade_unknown_share")) or 1.0) >= 0.05:
        return "trend_state coverage is insufficient; no regime conclusion is allowed."
    best = max(variants.values(), key=lambda row: _num(row.get("harsh_net_R_avg")) or -999.0, default={})
    metrics = _mapping(best.get("trend_state_metrics"))
    if not metrics:
        return "trend_state was repaired, but no stable state split can be interpreted from this run."
    positive = [
        state
        for state, raw in metrics.items()
        if isinstance(raw, Mapping) and int(raw.get("closed") or 0) >= 20 and (_num(raw.get("avg_R")) or -999.0) > 0
    ]
    return f"Diagnostic only: stronger states are {positive}; this was not used for sample selection."


def _decision_reason(decision: str, baseline: Mapping[str, object], variants: Mapping[str, object]) -> str:
    best_key, best = max(variants.items(), key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0, default=("", {}))
    return (
        f"Baseline v2 harsh={baseline.get('harsh_net_R_avg')}; best refinement is {best_key} "
        f"with harsh={best.get('harsh_net_R_avg')} and trend_unknown="
        f"{_mapping(best.get('trend_state_lineage')).get('closed_trade_unknown_share')}. Decision follows fixed thresholds."
    )


def _executive_summary(
    decision: str,
    baseline: Mapping[str, object],
    variants: Mapping[str, object],
    trend: Mapping[str, object],
) -> str:
    best_key, best = max(variants.items(), key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0, default=("", {}))
    return (
        f"trend_state lineage repaired to unknown_share={trend.get('closed_trade_unknown_share')}; "
        f"best={best_key}, harsh={best.get('harsh_net_R_avg')}, baseline_harsh={baseline.get('harsh_net_R_avg')}; {decision}"
    )


def _next_actions(decision: str) -> tuple[str, ...]:
    if decision.startswith("A."):
        return ("Run validation-prep on BP shallow cost-aware path only.", "Add read-only LR complementarity comparison.")
    if decision.startswith("B."):
        return ("Run one final regime-aware diagnostic split; do not use trend_state for formal filtering yet.",)
    if decision.startswith("C."):
        return ("Keep BP shallow diagnostic-only; document cost-aware mechanism as useful but too thin.",)
    if decision.startswith("D."):
        return ("Retain v2 as current diagnostic best; stop partial-capture/failure-exit refinement.",)
    return ("Pause TC family and consider a simpler support/resistance fixed-RR baseline later.",)


def _trend_state_split_has_signal(row: Mapping[str, object]) -> bool:
    metrics = _mapping(row.get("trend_state_metrics"))
    positive_groups = 0
    for raw in metrics.values():
        group = _mapping(raw)
        if int(group.get("closed") or 0) >= 20 and (_num(group.get("avg_R")) or -999.0) > 0:
            positive_groups += 1
    return positive_groups > 0


def _existing_state(row: Mapping[str, object], field: str) -> str:
    return _normalize_state(row.get(field) or row.get("trend_state"))


def _state(row: Mapping[str, object]) -> str:
    return _normalize_state(row.get("trend_state_at_entry") or row.get("trend_state"))


def _normalize_state(value: object) -> str:
    return "unknown" if value in _UNKNOWN_STATES else str(value)


def _unknown_count(rows: Sequence[Mapping[str, object]], field: str) -> int:
    return sum(1 for row in rows if _normalize_state(row.get(field) or row.get("trend_state")) == "unknown")


def _safe_entry_cutoff(row: Mapping[str, object]) -> int:
    return (
        _int(row.get("feature_cutoff_time"))
        or _int(row.get("signal_time"))
        or _int(row.get("signal_timestamp_ms"))
        or _int(row.get("entry_timestamp_ms"))
        or _int(row.get("timestamp_ms"))
        or 0
    )


def _mfe_r(intent, candles: Sequence[object]) -> float:
    favorable = 0.0
    for candle in candles:
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        if intent.direction == "LONG":
            favorable = max(favorable, high - intent.entry_price)
        elif intent.direction == "SHORT":
            favorable = max(favorable, intent.entry_price - low)
    return max(0.0, favorable) / max(intent.stop_distance, 1e-12)


def _counts(values: Sequence[object]) -> dict[str, int]:
    return dict(Counter(str(value) for value in values))


def _coverage(rows: Sequence[Mapping[str, object]], unknown_count: int) -> float:
    return 0.0 if not rows else (len(rows) - unknown_count) / len(rows)


def _share(count: int, total: int) -> float:
    return 0.0 if total <= 0 else count / total


def _avg(values: Sequence[float | None]) -> float | None:
    nums = [float(value) for value in values if value is not None]
    return None if not nums else sum(nums) / len(nums)


def _median(values: Sequence[float | None]) -> float | None:
    nums = sorted(float(value) for value in values if value is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    return nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2


def _int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


__all__ = (
    "BASELINE_VARIANT_ID",
    "REFINEMENT_VARIANT_IDS",
    "TcFamilyCostAwareRefinementWithTrendStateResult",
    "build_trend_state_lineage_diagnostics",
    "run_tc_family_cost_aware_refinement_with_trend_state",
    "select_refinement_decision",
)
