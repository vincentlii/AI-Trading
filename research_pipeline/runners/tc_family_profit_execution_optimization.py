from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_pipeline.core.analytics.execution_path import (
    enrich_execution_path_rows,
    summarize_execution_path_rows,
)
from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.core.reports.tc_family_profit_and_execution_optimization import (
    write_tc_family_profit_execution_report,
)
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.strategy_research_validation import (
    _diagnostic_rows,
    _metrics,
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
from trading_system.backtest.layered_cache import read_jsonl, write_json, write_jsonl
from trading_system.backtest.layered_pipeline import _input_from_filter_row, _execution_row
from trading_system.backtest.execution import SignalOrderAdapter, simulate_approved_fill
from trading_system.backtest.risk import CostEstimate, RiskDecision, SimulatedOrder
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION
from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import family_variant_setup


BASELINE_VARIANT_IDS = (
    "ce_lifecycle_native_light_confirm_v1",
    "ce_lifecycle_shallow_momentum_v1",
    "bp_shallow_momentum_capped_risk_v3",
)

OPTIMIZATION_VARIANT_IDS = (
    "bp_shallow_exit_efficiency_v1",
    "ce_shallow_exit_efficiency_v1",
    "bp_shallow_entry_timing_v1",
    "bp_shallow_cost_quality_v1",
)

SOURCE_VARIANT_BY_OPTIMIZATION = {
    "bp_shallow_exit_efficiency_v1": "bp_shallow_momentum_capped_risk_v3",
    "ce_shallow_exit_efficiency_v1": "ce_lifecycle_shallow_momentum_v1",
    "bp_shallow_entry_timing_v1": "bp_shallow_momentum_capped_risk_v3",
    "bp_shallow_cost_quality_v1": "bp_shallow_momentum_capped_risk_v3",
}


@dataclass(frozen=True)
class TcFamilyProfitExecutionOptimizationResult:
    run_id: str
    run_root: str
    baseline_run_root: str
    decision: str
    baseline_summaries: dict[str, Any]
    optimization_summaries: dict[str, Any]
    report_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_tc_family_profit_execution_optimization(
    *,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    baseline_run_root: Path,
    output_root: Path,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
    timestamp: datetime | None = None,
) -> TcFamilyProfitExecutionOptimizationResult:
    baseline_run_root = Path(baseline_run_root)
    output_root = Path(output_root)
    now = timestamp or datetime.now(timezone.utc)
    fingerprint = stable_fingerprint(
        {
            "round": "tc_family_profit_execution_optimization",
            "baseline_run_root": str(baseline_run_root),
            "dataset_window": dataset_window,
            "config_fingerprint": preset.config_fingerprint,
            "core_engine_version": CORE_ENGINE_VERSION,
            "baseline_variants": BASELINE_VARIANT_IDS,
            "optimization_variants": OPTIMIZATION_VARIANT_IDS,
        }
    )
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{fingerprint[:12]}"
    run_root = output_root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    baseline_summaries: dict[str, Any] = {}
    artifact_paths: list[str] = []
    for variant_id in BASELINE_VARIANT_IDS:
        source = _load_baseline_artifacts(baseline_run_root, variant_id)
        enriched = enrich_execution_path_rows(source["closed_rows"])
        path_summary = summarize_execution_path_rows(enriched)
        summary = {**source["variant_summary"], "path_diagnostics": path_summary}
        baseline_summaries[variant_id] = summary
        baseline_dir = run_root / "baseline_diagnostics" / variant_id
        baseline_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(baseline_dir / "execution_path_diagnostics.jsonl", enriched)
        write_json(baseline_dir / "execution_path_summary.json", path_summary)
        artifact_paths.append(str(baseline_dir))

    optimization_summaries: dict[str, Any] = {}
    for variant_id in OPTIMIZATION_VARIANT_IDS:
        source_variant = SOURCE_VARIANT_BY_OPTIMIZATION[variant_id]
        source = _load_baseline_artifacts(baseline_run_root, source_variant)
        output_dir = run_root / "variants" / variant_id
        summary = _run_optimization_variant(
            variant_id=variant_id,
            source_variant=source_variant,
            source=source,
            repository=repository,
            preset=preset,
            dataset_window=dataset_window,
            output_dir=output_dir,
            cost_tiers=tuple(cost_tiers),
        )
        optimization_summaries[variant_id] = summary
        artifact_paths.append(str(output_dir))

    decision = select_profit_execution_decision(optimization_summaries)
    payload = {
        "run_id": run_id,
        "baseline_run_root": str(baseline_run_root),
        "shared_cache_path": _shared_cache_path_from_baseline(baseline_run_root),
        "decision": decision,
        "decision_reason": _decision_reason(decision, baseline_summaries, optimization_summaries),
        "primary_diagnosis": _primary_diagnosis(baseline_summaries, optimization_summaries),
        "constraints": [
            "proposal-only / diagnostic-only; no formalization and no P6",
            "live_trading_enabled=false; no live order path used",
            "RiskEngine, costs, margin, notional cap, portfolio heat, formal stop, formal target, and formal exit boundaries remain unchanged",
            "performance metrics use row_type=closed_trade only",
            "diagnostic/proposal/summary rows remain excluded from performance",
            "LR final evidence remains read-only and is not included in this round's performance",
            "capped risk sizing remains proposal-only with minimum actual risk after cap of 0.10% equity",
        ],
        "baseline_summaries": baseline_summaries,
        "optimization_summaries": optimization_summaries,
        "next_actions": _next_actions(decision),
        "artifact_paths": artifact_paths,
        "known_limitations": [
            "Exit and entry changes are proposal-only shadow replays over the existing TC family artifacts.",
            "The round prioritizes attribution and bounded optimization; it does not search a parameter grid.",
        ],
    }
    report_path = write_tc_family_profit_execution_report(output_dir=run_root, payload=payload)
    result = TcFamilyProfitExecutionOptimizationResult(
        run_id=run_id,
        run_root=str(run_root),
        baseline_run_root=str(baseline_run_root),
        decision=decision,
        baseline_summaries=baseline_summaries,
        optimization_summaries=optimization_summaries,
        report_path=str(report_path),
    )
    (run_root / "tc_family_profit_and_execution_optimization_result.json").write_text(
        result.as_json() + "\n",
        encoding="utf-8",
    )
    return result


def select_profit_execution_decision(optimization_summaries: Mapping[str, Mapping[str, object]]) -> str:
    best = max(optimization_summaries.values(), key=lambda row: _num(row.get("harsh_net_R_avg")) or -999.0, default={})
    if (
        int(best.get("closed_trades") or 0) >= 250
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
        return "A. Execution optimization reveals valid edge; run validation-prep next."
    exit_rows = [
        row
        for key, row in optimization_summaries.items()
        if "exit_efficiency" in key and int(row.get("closed_trades") or 0) >= 250
    ]
    if any((_num(row.get("path_diagnostics", {}).get("exit_efficiency_avg")) or -999.0) > 0 for row in exit_rows):
        return "B. Exit optimization helps but edge still thin; one more bounded exit/target round allowed."
    if all((_num(row.get("path_diagnostics", {}).get("MFE_R_avg")) or 0.0) < 0.5 for row in optimization_summaries.values()):
        return "C. Entry/exit not main issue; signal quality filtering required next."
    if any((_num(row.get("base_net_R_avg")) or -999.0) > 0 and (_num(row.get("harsh_net_R_avg")) or 999.0) < 0 for row in optimization_summaries.values()):
        return "D. Cost structure dominates; keep diagnostic only."
    return "E. No optimization improves enough; pause TC family."


def _run_optimization_variant(
    *,
    variant_id: str,
    source_variant: str,
    source: Mapping[str, Any],
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_dir: Path,
    cost_tiers: Sequence[str],
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = tuple(dict(row, variant_id=variant_id, source_variant_id=source_variant) for row in source["candidate_rows"])
    filter_rows = _prepare_filter_rows(source["filter_rows"], variant_id=variant_id)
    closed_rows = _execute_profit_variant(
        variant_id=variant_id,
        repository=repository,
        preset=preset,
        filter_rows=filter_rows,
        cost_tiers=cost_tiers,
    )
    enriched = enrich_execution_path_rows(closed_rows)
    path_summary = summarize_execution_path_rows(enriched)
    robustness_rows = _robustness_rows(closed_rows)
    summary_rows = _summary_rows(candidate_rows, filter_rows, closed_rows)
    diagnostic_rows = (
        *_diagnostic_rows(filter_rows, candidate_rows, closed_rows),
        {
            "row_type": "diagnostic_only",
            "diagnostic_only": True,
            "eligible_for_performance": False,
            "diagnostic_name": "tc_family_profit_execution_optimization",
            "variant_id": variant_id,
            "source_variant_id": source_variant,
            "path_summary": path_summary,
        },
    )
    review_log_rows = _review_log_rows(
        strategy=family_variant_setup(source_variant),
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
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_log_rows)
    write_json(output_dir / "regression_baseline.json", regression_baseline)
    setup = family_variant_setup(source_variant)
    manifest = RunManifest(
        run_id=stable_fingerprint({"variant_id": variant_id, "output_dir": str(output_dir)})[:24],
        strategy=setup,
        adapter_version=f"tc_family_profit_execution.v1+{CORE_ENGINE_VERSION}",
        dataset_window=dataset_window,
        artifact_contract=_family_artifact_contract().as_dict(),
        audit_profile=family_audit_profile(source_variant).as_dict(),
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
            "source_variant_id": source_variant,
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "exit_policy": _exit_policy_name(variant_id),
        },
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="TC family profit and execution optimization; proposal-only shadow execution.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=setup,
        stage=f"tc_family_profit_execution_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-profit-execution-optimization",
        config_hash=preset.config_fingerprint,
        notes="Proposal-only TC family profit/execution optimization; LR final evidence untouched.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=setup,
        stage=f"tc_family_profit_execution_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-profit-execution-optimization",
        adapter_version=manifest.adapter_version,
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        config_hash=preset.config_fingerprint,
        notes="Proposal-only profit and execution optimization.",
        tags=["tc_family", variant_id, "profit_execution"],
    )
    audit = run_full_pipeline_audit(strategy=setup, artifact_dir=output_dir, registry=None, output_dir=output_dir / "full_audit")
    summary = _variant_summary(
        variant_id=source_variant,
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
            "source_variant_id": source_variant,
            "setup_id": family_variant_setup(source_variant),
            "path_diagnostics": path_summary,
            "interpretation": _interpret_variant(variant_id, summary, path_summary),
            "single_dimension_concentration": _single_dimension_concentration(summary),
        }
    )
    write_json(output_dir / "variant_summary.json", summary)
    return summary


def _execute_profit_variant(
    *,
    variant_id: str,
    repository,
    preset: BacktestPresetConfig,
    filter_rows: list[dict[str, object]],
    cost_tiers: Sequence[str],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    scheduling_tier = "base" if "base" in cost_tiers else str(cost_tiers[0])
    scheduling_preset = _profit_tier_preset(preset, scheduling_tier, variant_id)
    accepted_ids: set[str] = set()
    open_intervals: list[tuple[int, int, float]] = []
    ordered = sorted(filter_rows, key=lambda row: (int(row.get("timestamp_ms") or 0), str(row.get("candidate_id") or "")))
    for candidate in ordered:
        _apply_variant_pre_execution_policy(candidate, variant_id)
        if not candidate.get("proposal_approved_after_cap"):
            candidate["proposal_execution_status"] = "not_approved_after_cap"
            continue
        closed, reject = _simulate_profit_candidate(
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
        tier_preset = _profit_tier_preset(preset, tier_name, variant_id)
        for candidate in ordered:
            if str(candidate.get("candidate_id") or "") not in accepted_ids:
                continue
            closed, _ = _simulate_profit_candidate(
                repository=repository,
                candidate=candidate,
                tier_preset=tier_preset,
                tier_name=tier_name,
                variant_id=variant_id,
            )
            if closed is not None:
                rows.append(closed)
    return tuple(rows)


def _simulate_profit_candidate(
    *,
    repository,
    candidate: Mapping[str, object],
    tier_preset: BacktestPresetConfig,
    tier_name: str,
    variant_id: str,
) -> tuple[dict[str, object] | None, str]:
    if variant_id == "bp_shallow_entry_timing_v1":
        candidate = _delayed_candidate(candidate)
    if _uses_standard_exit(variant_id):
        return _simulate_capped_candidate(repository=repository, candidate=candidate, tier_preset=tier_preset, tier_name=tier_name)
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
    fill = simulate_approved_fill(
        risk_decision=decision,
        execution_candles=signal_input.execution_candles,
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
        }
    )
    return closed, ""


def _profit_tier_preset(preset: BacktestPresetConfig, tier_name: str, variant_id: str) -> BacktestPresetConfig:
    tier = _tier_preset(preset, tier_name)
    execution = tier.execution
    if variant_id in {"bp_shallow_exit_efficiency_v1", "ce_shallow_exit_efficiency_v1"}:
        partial_r = 1.0 if variant_id.startswith("bp_") else 0.75
        execution = replace(
            execution,
            enable_advanced_exits=True,
            partial_take_profit_r=partial_r,
            partial_take_profit_pct=0.5,
            move_stop_to_true_breakeven=True,
            breakeven_after_mfe_r=partial_r,
            chandelier_period=5,
            chandelier_atr_multiple=2.0,
        )
    return replace(tier, execution=execution)


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


def _apply_variant_pre_execution_policy(candidate: dict[str, object], variant_id: str) -> None:
    if variant_id != "bp_shallow_cost_quality_v1":
        return
    reasons = []
    gross_rr = _num(candidate.get("gross_RR")) or _num(candidate.get("target_r")) or 0.0
    target_atr = _num(candidate.get("target_space_atr")) or _num(candidate.get("target_space_ATR")) or 0.0
    actual_risk = _num(candidate.get("actual_risk_after_cap_pct")) or 0.0
    cost_per_r = _num(candidate.get("cost_per_R")) or 0.0
    if gross_rr < 1.15:
        reasons.append("gross_RR_too_low_for_cost_quality")
    if target_atr < 1.0:
        reasons.append("target_space_ATR_too_low_for_cost_quality")
    if 0 < actual_risk < 0.0015:
        reasons.append("actual_risk_after_cap_too_low_for_cost_quality")
    if cost_per_r > 0.20:
        reasons.append("cost_per_R_too_high_for_cost_quality")
    if reasons:
        candidate["proposal_approved_after_cap"] = False
        candidate["approved_after_cap"] = False
        candidate["risk_reject_reason_after_cap"] = ",".join(reasons)
        candidate["reject_reason"] = ",".join(reasons)


def _delayed_candidate(candidate: Mapping[str, object]) -> dict[str, object]:
    payload = dict(candidate)
    delay_ms = _entry_delay_ms(str(payload.get("profile") or "B"))
    timestamp = int(payload.get("timestamp_ms") or payload.get("signal_time") or 0)
    delayed = timestamp + delay_ms
    payload["timestamp_ms"] = delayed
    payload["signal_timestamp_ms"] = delayed
    payload["signal_time"] = delayed
    payload["entry_timestamp_ms"] = delayed
    payload["entry_policy"] = "proposal_one_entry_bar_delay"
    return payload


def _entry_delay_ms(profile: str) -> int:
    return 15 * 60 * 1000 if profile == "C" else 60 * 60 * 1000


def _uses_standard_exit(variant_id: str) -> bool:
    return variant_id in {"bp_shallow_entry_timing_v1", "bp_shallow_cost_quality_v1"}


def _load_baseline_artifacts(baseline_run_root: Path, variant_id: str) -> dict[str, Any]:
    variant_dir = baseline_run_root / "variants" / variant_id
    if not variant_dir.exists():
        raise FileNotFoundError(f"missing baseline variant dir: {variant_dir}")
    return {
        "variant_dir": variant_dir,
        "candidate_rows": read_jsonl(variant_dir / "candidate_rows.jsonl"),
        "filter_rows": read_jsonl(variant_dir / "filter_results_research.jsonl"),
        "closed_rows": read_jsonl(variant_dir / "closed_trade_rows.jsonl"),
        "variant_summary": json.loads((variant_dir / "variant_summary.json").read_text(encoding="utf-8")),
    }


def _exit_policy_name(variant_id: str) -> str:
    if "exit_efficiency" in variant_id:
        return "proposal_advanced_exit_partial_breakeven_chandelier"
    if "entry_timing" in variant_id:
        return "proposal_one_entry_bar_delay"
    if "cost_quality" in variant_id:
        return "proposal_cost_quality_filter"
    return "baseline"


def _interpret_variant(variant_id: str, summary: Mapping[str, object], path: Mapping[str, object]) -> str:
    return (
        f"{variant_id}: closed={summary.get('closed_trades', 0)}, "
        f"base/stress/harsh={summary.get('base_net_R_avg')}/{summary.get('stress_net_R_avg')}/{summary.get('harsh_net_R_avg')}, "
        f"MFE_avg={path.get('MFE_R_avg')}, exit_efficiency_avg={path.get('exit_efficiency_avg')}, "
        f"positive_MFE_loss={path.get('positive_MFE_but_final_loss')}."
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


def _primary_diagnosis(baseline: Mapping[str, Mapping[str, object]], optimized: Mapping[str, Mapping[str, object]]) -> str:
    bp = baseline.get("bp_shallow_momentum_capped_risk_v3", {}).get("path_diagnostics", {})
    ce = baseline.get("ce_lifecycle_shallow_momentum_v1", {}).get("path_diagnostics", {})
    if (_num(bp.get("positive_MFE_but_final_loss_share")) or 0.0) >= 0.25:
        return "BP shallow shows meaningful MFE giveback; exit efficiency is a primary hypothesis."
    if (_num(ce.get("MFE_R_avg")) or 0.0) < 0.5:
        return "CE shallow MFE is thin; signal quality and cost resilience dominate."
    return "Mixed attribution; compare exit, entry, and cost-quality variants."


def _decision_reason(decision: str, baseline: Mapping[str, object], optimized: Mapping[str, object]) -> str:
    best_key, best = max(
        optimized.items(),
        key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0,
        default=("", {}),
    )
    return f"Best harsh variant is {best_key} with harsh avg R={best.get('harsh_net_R_avg')}; decision follows fixed thresholds."


def _next_actions(decision: str) -> tuple[str, ...]:
    if decision.startswith("A."):
        return ("Run validation-prep on the winning variant only.", "Re-run Full Audit, robustness, and LR complementarity read-only.")
    if decision.startswith("B."):
        return ("Run one bounded exit/target round on the best exit variant only.", "Do not add signal families or parameter grids.")
    if decision.startswith("C."):
        return ("Stop exit optimization and design bounded signal-quality filters.",)
    if decision.startswith("D."):
        return ("Keep TC family diagnostic-only and investigate cost-per-R / target-space constraints.",)
    return ("Pause TC family optimization and preserve artifacts for review.",)


def _shared_cache_path_from_baseline(baseline_run_root: Path) -> str:
    result_path = baseline_run_root / "tc_family_trade_count_and_variant_expansion_result.json"
    if not result_path.exists():
        return ""
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return str(payload.get("shared_cache_path") or "")


def _num(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = (
    "BASELINE_VARIANT_IDS",
    "OPTIMIZATION_VARIANT_IDS",
    "TcFamilyProfitExecutionOptimizationResult",
    "run_tc_family_profit_execution_optimization",
    "select_profit_execution_decision",
)
