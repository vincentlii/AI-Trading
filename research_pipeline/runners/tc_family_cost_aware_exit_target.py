from __future__ import annotations

import json
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
from research_pipeline.core.reports.tc_family_cost_aware_exit_target import (
    write_tc_family_cost_aware_exit_target_report,
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
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION
from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import family_variant_setup


BASELINE_VARIANT_ID = "bp_shallow_cost_quality_v1"
CE_SHALLOW_COMPARISON_ID = "ce_shallow_exit_efficiency_v1"

COST_AWARE_VARIANT_IDS = (
    "bp_shallow_micro_profit_capture_v1",
    "bp_shallow_momentum_decay_time_stop_v1",
    "bp_shallow_cost_aware_admission_v2",
)


@dataclass(frozen=True)
class TcFamilyCostAwareExitTargetResult:
    run_id: str
    run_root: str
    baseline_run_root: str
    decision: str
    baseline_summary: dict[str, Any]
    variant_summaries: dict[str, Any]
    ce_shallow_comparison: dict[str, Any]
    report_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_tc_family_cost_aware_exit_target(
    *,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    baseline_run_root: Path,
    output_root: Path,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
    timestamp: datetime | None = None,
) -> TcFamilyCostAwareExitTargetResult:
    baseline_run_root = Path(baseline_run_root)
    output_root = Path(output_root)
    now = timestamp or datetime.now(timezone.utc)
    fingerprint = stable_fingerprint(
        {
            "round": "tc_family_cost_aware_exit_target",
            "baseline_run_root": str(baseline_run_root),
            "dataset_window": dataset_window,
            "config_fingerprint": preset.config_fingerprint,
            "core_engine_version": CORE_ENGINE_VERSION,
            "source_variant": BASELINE_VARIANT_ID,
            "variants": COST_AWARE_VARIANT_IDS,
        }
    )
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{fingerprint[:12]}"
    run_root = output_root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    source = _load_source_artifacts(baseline_run_root, BASELINE_VARIANT_ID)
    baseline_summary = _with_path_summary(source)
    ce_shallow_comparison = _with_path_summary(_load_source_artifacts(baseline_run_root, CE_SHALLOW_COMPARISON_ID))

    artifact_paths: list[str] = []
    variant_summaries: dict[str, Any] = {}
    for variant_id in COST_AWARE_VARIANT_IDS:
        output_dir = run_root / "variants" / variant_id
        summary = _run_cost_variant(
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

    decision = select_cost_aware_exit_target_decision(variant_summaries, baseline_summary=baseline_summary)
    payload = {
        "run_id": run_id,
        "baseline_run_root": str(baseline_run_root),
        "decision": decision,
        "decision_reason": _decision_reason(decision, baseline_summary, variant_summaries),
        "primary_diagnosis": _primary_diagnosis(baseline_summary, variant_summaries),
        "constraints": [
            "proposal-only / diagnostic-only; no formalization and no P6",
            "live_trading_enabled=false; no live order path used",
            "RiskEngine, costs, margin, notional cap, portfolio heat, formal stop, formal target, and formal exit boundaries remain unchanged",
            "performance metrics use row_type=closed_trade only",
            "diagnostic/proposal/summary rows remain excluded from performance",
            "LR final evidence remains read-only and is not included in this round's performance",
            "capped risk sizing remains proposal-only with minimum actual risk after cap of 0.10% equity",
        ],
        "baseline_summary": baseline_summary,
        "variant_summaries": variant_summaries,
        "ce_shallow_comparison": ce_shallow_comparison,
        "next_actions": _next_actions(decision),
        "artifact_paths": artifact_paths,
        "known_limitations": [
            "Micro-profit capture uses fixed 0.40R proposal partial/breakeven policy; no parameter grid was run.",
            "Momentum decay time stop uses only the first 6 bars after entry and exits via truncated shadow replay.",
            "Cost-aware admission removes the lowest-scoring entry-known candidates; retained/removed comparison is post-trade diagnostic only.",
        ],
    }
    report_path = write_tc_family_cost_aware_exit_target_report(output_dir=run_root, payload=payload)
    result = TcFamilyCostAwareExitTargetResult(
        run_id=run_id,
        run_root=str(run_root),
        baseline_run_root=str(baseline_run_root),
        decision=decision,
        baseline_summary=baseline_summary,
        variant_summaries=variant_summaries,
        ce_shallow_comparison=ce_shallow_comparison,
        report_path=str(report_path),
    )
    (run_root / "tc_family_cost_aware_exit_target_result.json").write_text(result.as_json() + "\n", encoding="utf-8")
    return result


def select_cost_aware_exit_target_decision(
    variant_summaries: Mapping[str, Mapping[str, object]],
    *,
    baseline_summary: Mapping[str, object] | None = None,
) -> str:
    best_key, best = max(
        variant_summaries.items(),
        key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0,
        default=("", {}),
    )
    if (
        int(best.get("closed_trades") or 0) >= 400
        and (_num(best.get("base_net_R_avg")) or -999.0) > 0
        and (_num(best.get("stress_net_R_avg")) or -999.0) > 0
        and (_num(best.get("harsh_net_R_avg")) or -999.0) >= 0.03
        and (_num(best.get("median_R")) or -999.0) >= 0
        and (_num(best.get("PF")) or 0.0) > 1.15
        and (_num(best.get("net_R_avg_excluding_top_1")) or -999.0) > 0
        and (_num(best.get("net_R_avg_excluding_top_2")) or -999.0) > 0
        and int(best.get("positive_walk_forward_windows") or 0) >= 3
        and best.get("full_audit_gate") == "passed"
        and best.get("no_lookahead") == "passed"
        and best.get("metric_recompute") == "passed"
        and not best.get("single_dimension_concentration")
    ):
        return "A. BP shallow has validation-prep potential; run bounded validation-prep next."
    baseline_harsh = _num((baseline_summary or {}).get("harsh_net_R_avg")) or -999.0
    if (_num(best.get("harsh_net_R_avg")) or -999.0) > baseline_harsh + 0.02 and int(best.get("closed_trades") or 0) >= 400:
        return "B. Exit/target optimization improved edge but not enough; one more bounded refinement allowed."
    cost = variant_summaries.get("bp_shallow_cost_aware_admission_v2", {})
    if best_key == "bp_shallow_cost_aware_admission_v2" and (_num(cost.get("harsh_net_R_avg")) or -999.0) > baseline_harsh:
        return "C. Cost-aware admission helps but edge remains too thin; keep diagnostic only."
    micro = variant_summaries.get("bp_shallow_micro_profit_capture_v1", {})
    time_stop = variant_summaries.get("bp_shallow_momentum_decay_time_stop_v1", {})
    if (
        (_num(micro.get("harsh_net_R_avg")) or -999.0) <= baseline_harsh
        and (_num(time_stop.get("harsh_net_R_avg")) or -999.0) <= baseline_harsh
    ):
        return "D. Profit capture/time stop failed; signal edge likely insufficient."
    return "E. No variant improves enough; pause TC family and move to simpler baseline later."


def _run_cost_variant(
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
    if variant_id == "bp_shallow_cost_aware_admission_v2":
        _apply_cost_aware_admission(filter_rows)
    closed_rows = _execute_cost_variant(
        variant_id=variant_id,
        repository=repository,
        preset=preset,
        filter_rows=filter_rows,
        cost_tiers=cost_tiers,
    )
    enriched = enrich_execution_path_rows(closed_rows)
    path_summary = summarize_execution_path_rows(enriched)
    variant_diagnostics = _variant_specific_diagnostics(variant_id, enriched, source)
    if variant_id == "bp_shallow_cost_aware_admission_v2":
        path_summary["retained_removed_comparison"] = variant_diagnostics["retained_removed_comparison"]
    robustness_rows = _robustness_rows(closed_rows)
    summary_rows = _summary_rows(candidate_rows, filter_rows, closed_rows)
    diagnostic_rows = (
        *_diagnostic_rows(filter_rows, candidate_rows, closed_rows),
        {
            "row_type": "diagnostic_only",
            "diagnostic_only": True,
            "eligible_for_performance": False,
            "diagnostic_name": "tc_family_cost_aware_exit_target",
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "path_summary": path_summary,
            "variant_diagnostics": variant_diagnostics,
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
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_log_rows)
    write_json(output_dir / "regression_baseline.json", regression_baseline)
    setup = family_variant_setup("bp_shallow_momentum_capped_risk_v3")
    manifest = RunManifest(
        run_id=stable_fingerprint({"variant_id": variant_id, "output_dir": str(output_dir)})[:24],
        strategy=setup,
        adapter_version=f"tc_family_cost_aware_exit_target.v1+{CORE_ENGINE_VERSION}",
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
        },
        config_snapshot={
            "config_version": preset.config_version,
            "config_fingerprint": preset.config_fingerprint,
            "setup_filter": [setup],
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "exit_policy": _exit_policy_name(variant_id),
        },
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="TC family cost-aware exit/target round; proposal-only shadow replay.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=setup,
        stage=f"tc_family_cost_aware_exit_target_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-cost-aware-exit-target",
        config_hash=preset.config_fingerprint,
        notes="Proposal-only TC family cost-aware exit/target round; LR final evidence untouched.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=setup,
        stage=f"tc_family_cost_aware_exit_target_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-cost-aware-exit-target",
        adapter_version=manifest.adapter_version,
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        config_hash=preset.config_fingerprint,
        notes="Proposal-only cost-aware exit/target optimization.",
        tags=["tc_family", variant_id, "cost_aware_exit_target"],
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
            "interpretation": _interpret_variant(variant_id, summary, path_summary, variant_diagnostics),
            "single_dimension_concentration": _single_dimension_concentration(summary),
        }
    )
    write_json(output_dir / "variant_summary.json", summary)
    return summary


def _execute_cost_variant(
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
        closed, reject = _simulate_cost_candidate(
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
            closed, _ = _simulate_cost_candidate(
                repository=repository,
                candidate=candidate,
                tier_preset=tier_preset,
                tier_name=tier_name,
                variant_id=variant_id,
            )
            if closed is not None:
                rows.append(closed)
    return tuple(rows)


def _simulate_cost_candidate(
    *,
    repository,
    candidate: Mapping[str, object],
    tier_preset: BacktestPresetConfig,
    tier_name: str,
    variant_id: str,
) -> tuple[dict[str, object] | None, str]:
    if variant_id == "bp_shallow_cost_aware_admission_v2":
        closed, reject = _simulate_capped_candidate(repository=repository, candidate=candidate, tier_preset=tier_preset, tier_name=tier_name)
        if closed is not None:
            closed["exit_policy"] = _exit_policy_name(variant_id)
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
    shadow_time_stop = False
    if variant_id == "bp_shallow_momentum_decay_time_stop_v1":
        cutoff_bars = min(6, len(execution_candles))
        early = execution_candles[:cutoff_bars]
        if cutoff_bars > 0 and _mfe_r(intent, early) < 0.25:
            execution_candles = early
            shadow_time_stop = True
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
            "proposal_time_stop_triggered": shadow_time_stop,
        }
    )
    if shadow_time_stop and closed.get("exit_reason") == "time_exit":
        closed["exit_reason"] = "proposal_momentum_decay_time_stop"
    return closed, ""


def _cost_tier_preset(preset: BacktestPresetConfig, tier_name: str, variant_id: str) -> BacktestPresetConfig:
    tier = _tier_preset(preset, tier_name)
    execution = tier.execution
    if variant_id == "bp_shallow_micro_profit_capture_v1":
        execution = replace(
            execution,
            enable_advanced_exits=True,
            partial_take_profit_r=0.4,
            partial_take_profit_pct=0.4,
            move_stop_to_true_breakeven=True,
            breakeven_after_mfe_r=0.4,
            chandelier_period=3,
            chandelier_atr_multiple=1.5,
        )
    return replace(tier, execution=execution)


def _apply_cost_aware_admission(filter_rows: list[dict[str, object]]) -> None:
    approved = [row for row in filter_rows if row.get("proposal_approved_after_cap")]
    scores = []
    for row in approved:
        score = _cost_aware_score(row)
        row["cost_aware_admission_score"] = score
        scores.append(score)
    if not scores:
        return
    threshold = sorted(scores)[max(0, int(len(scores) * 0.25) - 1)]
    for row in approved:
        if float(row.get("cost_aware_admission_score") or 0.0) <= threshold:
            row["proposal_approved_after_cap"] = False
            row["approved_after_cap"] = False
            row["removed_by_cost_aware_admission"] = True
            row["risk_reject_reason_after_cap"] = "cost_aware_admission_bottom_quartile"
            row["reject_reason"] = "cost_aware_admission_bottom_quartile"
        else:
            row["retained_by_cost_aware_admission"] = True


def _cost_aware_score(row: Mapping[str, object]) -> float:
    target_atr = _num(row.get("target_space_atr")) or _num(row.get("target_space_ATR")) or 0.0
    gross_rr = _num(row.get("gross_RR")) or _num(row.get("target_r")) or 0.0
    relaunch = _num(row.get("relaunch_score")) or 0.0
    pullback = _num(row.get("pullback_quality_score")) or 0.0
    cost_per_r = _num(row.get("cost_per_R")) or 0.0
    actual_risk = _num(row.get("actual_risk_after_cap_pct")) or 0.0
    stop_atr = _num(row.get("stop_distance_atr")) or _num(row.get("stop_atr")) or 0.0
    risk_penalty = 0.2 if 0 < actual_risk < 0.0015 else 0.0
    stop_penalty = 0.1 if stop_atr > 2.5 else 0.0
    return (
        min(target_atr / 3.0, 1.0) * 0.25
        + min(gross_rr / 2.5, 1.0) * 0.20
        + relaunch * 0.20
        + pullback * 0.15
        - min(cost_per_r / 0.25, 1.0) * 0.15
        - risk_penalty
        - stop_penalty
    )


def _variant_specific_diagnostics(
    variant_id: str,
    enriched: Sequence[Mapping[str, object]],
    source: Mapping[str, Any],
) -> dict[str, object]:
    if variant_id == "bp_shallow_micro_profit_capture_v1":
        closed = [row for row in enriched if row.get("row_type") == "closed_trade"]
        triggered = [row for row in closed if row.get("partial_take_profit_hit")]
        return {
            "capture_policy": "0.40R partial_take_profit_40pct + cost_adjusted_breakeven + 3-bar chandelier",
            "capture_trigger_count": len(triggered),
            "partial_TP_count": len(triggered),
            "breakeven_move_count": sum(1 for row in closed if row.get("moved_to_breakeven")),
            "trailing_activation_count": sum(1 for row in closed if row.get("exit_reason") == "chandelier_exit"),
            "average_captured_R": _avg([_num(row.get("final_R")) for row in triggered]),
            "final_loss_after_capture_count": sum(1 for row in triggered if (_num(row.get("final_R")) or 0.0) <= 0),
        }
    if variant_id == "bp_shallow_momentum_decay_time_stop_v1":
        stopped = [row for row in enriched if row.get("proposal_time_stop_triggered")]
        return {
            "time_stop_policy": "exit at current/confirmed close after 6 bars when early MFE < 0.25R",
            "time_stop_trigger_count": len(stopped),
            "avg_R_of_time_stopped_trades": _avg([_num(row.get("final_R")) for row in stopped]),
            "bars_to_exit_distribution": _counts([row.get("bars_in_trade") for row in stopped]),
        }
    if variant_id == "bp_shallow_cost_aware_admission_v2":
        retained_ids = {
            str(row.get("candidate_id") or "")
            for row in source["filter_rows"]
            if row.get("proposal_approved_after_cap") and _cost_aware_score(row) > _source_score_threshold(source["filter_rows"])
        }
        baseline = []
        for row in source["closed_rows"]:
            payload = dict(row)
            if str(payload.get("candidate_id") or "") in retained_ids:
                payload["retained_by_admission"] = True
            else:
                payload["removed_by_admission"] = True
            baseline.append(payload)
        comparison = compare_retained_removed_rows(enrich_execution_path_rows(baseline))
        return {
            "admission_policy": "entry-known score removes lowest 25% of approved candidates",
            "retained_removed_comparison": comparison,
        }
    return {}


def _source_score_threshold(rows: Sequence[Mapping[str, object]]) -> float:
    scores = [_cost_aware_score(row) for row in rows if row.get("proposal_approved_after_cap")]
    if not scores:
        return 0.0
    return sorted(scores)[max(0, int(len(scores) * 0.25) - 1)]


def _load_source_artifacts(run_root: Path, variant_id: str) -> dict[str, Any]:
    variant_dir = run_root / "variants" / variant_id
    if not variant_dir.exists():
        raise FileNotFoundError(f"missing source variant dir: {variant_dir}")
    return {
        "variant_dir": variant_dir,
        "candidate_rows": read_jsonl(variant_dir / "candidate_rows.jsonl"),
        "filter_rows": read_jsonl(variant_dir / "filter_results_research.jsonl"),
        "closed_rows": read_jsonl(variant_dir / "closed_trade_rows.jsonl"),
        "variant_summary": json.loads((variant_dir / "variant_summary.json").read_text(encoding="utf-8")),
    }


def _with_path_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    enriched = enrich_execution_path_rows(source["closed_rows"])
    return {**source["variant_summary"], "path_diagnostics": summarize_execution_path_rows(enriched)}


def _prepare_filter_rows(rows: Sequence[Mapping[str, object]], *, variant_id: str) -> list[dict[str, object]]:
    prepared = []
    for row in rows:
        payload = dict(row)
        payload["source_variant_id"] = payload.get("variant_id")
        payload["variant_id"] = variant_id
        payload["optimization_variant"] = variant_id
        payload["proposal_only"] = True
        payload["formal_conclusion_enabled"] = False
        prepared.append(payload)
    return prepared


def _exit_policy_name(variant_id: str) -> str:
    if "micro_profit_capture" in variant_id:
        return "proposal_micro_profit_capture_0_40r_partial_breakeven_trailing"
    if "momentum_decay_time_stop" in variant_id:
        return "proposal_momentum_decay_time_stop_6bar_0_25r"
    if "cost_aware_admission" in variant_id:
        return "proposal_cost_aware_admission_score_bottom_quartile_removed"
    return "baseline"


def _interpret_variant(
    variant_id: str,
    summary: Mapping[str, object],
    path: Mapping[str, object],
    diagnostics: Mapping[str, object],
) -> str:
    return (
        f"{variant_id}: closed={summary.get('closed_trades', 0)}, "
        f"base/stress/harsh={summary.get('base_net_R_avg')}/{summary.get('stress_net_R_avg')}/{summary.get('harsh_net_R_avg')}, "
        f"median_R={summary.get('median_R')}, MFE_avg={path.get('MFE_R_avg')}, "
        f"positive_MFE_loss={path.get('positive_MFE_but_final_loss')}, diagnostics={diagnostics}."
    )


def _single_dimension_concentration(summary: Mapping[str, object]) -> bool:
    closed = int(summary.get("closed_trades") or 0)
    if closed <= 0:
        return True
    for key in ("asset_split", "profile_split", "direction_split"):
        values = summary.get(key)
        if isinstance(values, Mapping) and values:
            if max(int(value) for value in values.values()) / closed >= 0.80:
                return True
    return False


def _primary_diagnosis(baseline: Mapping[str, object], variants: Mapping[str, Mapping[str, object]]) -> str:
    path = baseline.get("path_diagnostics", {}) if isinstance(baseline.get("path_diagnostics"), Mapping) else {}
    if (_num(path.get("MFE_R_median")) or 0.0) < 0.5 and (_num(path.get("positive_MFE_but_final_loss_share")) or 0.0) > 0.4:
        return "BP shallow has micro-MFE but weak final capture; cost-aware exit/target is the right diagnostic focus."
    best = max(variants.values(), key=lambda row: _num(row.get("harsh_net_R_avg")) or -999.0, default={})
    return f"Best harsh result is {best.get('variant_id', 'unavailable')} with harsh={best.get('harsh_net_R_avg')}."


def _decision_reason(decision: str, baseline: Mapping[str, object], variants: Mapping[str, object]) -> str:
    best_key, best = max(variants.items(), key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0, default=("", {}))
    return (
        f"Baseline harsh={baseline.get('harsh_net_R_avg')}; best harsh variant is {best_key} "
        f"with harsh={best.get('harsh_net_R_avg')}. Decision follows fixed thresholds."
    )


def _next_actions(decision: str) -> tuple[str, ...]:
    if decision.startswith("A."):
        return ("Run validation-prep on the winning BP shallow variant only.", "Add LR complementarity read-only comparison.")
    if decision.startswith("B."):
        return ("Allow one more bounded exit/target refinement on the winning mechanism only.", "Do not add entry timing or new strategy families.")
    if decision.startswith("C."):
        return ("Keep BP shallow diagnostic-only; document cost-aware admission as useful but insufficient.",)
    if decision.startswith("D."):
        return ("Stop profit-capture/time-stop tuning and revisit signal quality or simpler baseline later.",)
    return ("Pause TC family and consider a simpler support/resistance fixed-RR baseline in a later phase.",)


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
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _avg(values: Sequence[float | None]) -> float | None:
    nums = [float(value) for value in values if value is not None]
    return None if not nums else sum(nums) / len(nums)


def _num(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = (
    "BASELINE_VARIANT_ID",
    "COST_AWARE_VARIANT_IDS",
    "TcFamilyCostAwareExitTargetResult",
    "run_tc_family_cost_aware_exit_target",
    "select_cost_aware_exit_target_decision",
)
