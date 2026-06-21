from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from research_pipeline.adapters.base import ArtifactContract, AuditProfile
from research_pipeline.adapters.breakout_pullback import BreakoutPullbackAdapter
from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.core.cache.tc_family_event_store import TcFamilyEventStore
from research_pipeline.core.reports.tc_family_trade_count_and_variant_expansion import (
    write_tc_family_trade_count_report,
)
from research_pipeline.core.sizing.capped_risk import apply_capped_risk_sizing
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.strategy_expansion_diagnostics import diagnostic_rows_for_adapter
from research_pipeline.runners.strategy_research_validation import (
    _diagnostic_rows,
    _metrics,
    _regression_baseline,
    _review_log_rows,
    _robustness_rows,
    _summary_rows,
)
from trading_system.backtest.execution import SignalOrderAdapter, simulate_approved_fill
from trading_system.backtest.layered_cache import write_json, write_jsonl
from trading_system.backtest.layered_pipeline import (
    _build_context_rows,
    _execution_row,
    _filter_candidate,
    _input_from_filter_row,
    _tier_preset,
)
from trading_system.backtest.risk import CostEstimate, RiskDecision, SimulatedOrder
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION
from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import (
    FAMILY_VARIANT_IDS,
    compact_family_event,
    family_event_eligible,
    family_variant_setup,
    select_family_candidates,
)


@dataclass(frozen=True)
class TcFamilyTradeCountExpansionResult:
    run_id: str
    run_root: str
    shared_cache_path: str
    shared_cache_reused: bool
    decision: str
    variant_summaries: dict[str, Any]
    report_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_tc_family_trade_count_expansion(
    *,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_root: Path,
    max_entry_windows: int | None = None,
    candidate_end_ms: int | None = None,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
    chunk_size: int = 20,
    timestamp: datetime | None = None,
) -> TcFamilyTradeCountExpansionResult:
    now = timestamp or datetime.now(timezone.utc)
    output_root = Path(output_root)
    cache_fingerprint = _cache_fingerprint(
        repository=repository,
        preset=preset,
        dataset_window=dataset_window,
        max_entry_windows=max_entry_windows,
        candidate_end_ms=candidate_end_ms,
    )
    fingerprint_hash = stable_fingerprint(cache_fingerprint)
    cache_root = output_root / "shared_cache" / fingerprint_hash[:24]
    store = TcFamilyEventStore(cache_root / "family_events.duckdb", cache_fingerprint)
    store.initialize()
    reused = bool(store.status()["complete"])
    cache_status = _ensure_shared_event_store(
        store=store,
        repository=repository,
        preset=preset,
        dataset_window=dataset_window,
        max_entry_windows=max_entry_windows,
        candidate_end_ms=candidate_end_ms,
        chunk_size=max(1, int(chunk_size)),
        cache_root=cache_root,
    )

    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{fingerprint_hash[:12]}"
    run_root = output_root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    variant_summaries: dict[str, Any] = {}
    artifact_paths: list[str] = [str(store.path), str(cache_root / "shared_cache_manifest.json")]
    for variant_id in FAMILY_VARIANT_IDS:
        variant_summary = _run_variant(
            variant_id=variant_id,
            store=store,
            cache_status=cache_status,
            repository=repository,
            preset=preset,
            dataset_window=dataset_window,
            output_dir=run_root / "variants" / variant_id,
            cost_tiers=tuple(cost_tiers),
            candidate_end_ms=candidate_end_ms,
        )
        variant_summaries[variant_id] = variant_summary
        artifact_paths.append(str(run_root / "variants" / variant_id))
        _remove_empty_duckdb_temp(cache_root)

    decision = select_family_decision(variant_summaries)
    decision_reason = _decision_reason(decision, variant_summaries)
    payload = {
        "run_id": run_id,
        "decision": decision,
        "decision_reason": decision_reason,
        "cache_status": cache_status,
        "variant_summaries": variant_summaries,
        "constraints": [
            "proposal-only / diagnostic-only; no formalization and no P6",
            "live_trading_enabled=false; no live order path used",
            "RiskEngine, costs, margin, notional cap, portfolio heat, stop, target, and exit boundaries remain unchanged",
            "performance metrics use row_type=closed_trade only",
            "LR final evidence remains read-only and is not included in this round's performance",
        ],
        "next_actions": _next_actions(decision),
        "artifact_paths": artifact_paths,
        "known_limitations": [
            "This round prioritizes trade count, conversion, and strategy-shape coverage before profit optimization.",
            "Capped risk sizing is proposal-only and may reduce actual PnL while preserving R comparability.",
        ],
    }
    report_path = write_tc_family_trade_count_report(output_dir=run_root, payload=payload)
    result = TcFamilyTradeCountExpansionResult(
        run_id=run_id,
        run_root=str(run_root),
        shared_cache_path=str(store.path),
        shared_cache_reused=reused,
        decision=decision,
        variant_summaries=variant_summaries,
        report_path=str(report_path),
    )
    (run_root / "tc_family_trade_count_and_variant_expansion_result.json").write_text(
        result.as_json() + "\n",
        encoding="utf-8",
    )
    _remove_empty_duckdb_temp(cache_root)
    return result


def family_audit_profile(variant_id: str) -> AuditProfile:
    setup = family_variant_setup(variant_id)
    lineage = [
        "trade_id",
        "execution_id",
        "candidate_id",
        "event_id",
        "lifecycle_event_id",
        "level_id",
        "breakout_event_id",
        "compression_event_id" if setup == "compression_expansion" else "breakout_pullback_event_id",
    ]
    required_time = [
        "feature_cutoff_time",
        "zone_confirmed_time",
        "breakout_time",
        "acceptance_end_time",
        "signal_time",
        "entry_time",
        "exit_time",
    ]
    checks = [
        ("feature_cutoff_time_lte_signal_time", "feature_cutoff_time", "signal_time"),
        ("zone_confirmed_time_lte_breakout_time", "zone_confirmed_time", "breakout_time"),
        ("breakout_time_lte_acceptance_end_time", "breakout_time", "acceptance_end_time"),
        ("acceptance_end_time_lte_signal_time", "acceptance_end_time", "signal_time"),
        ("signal_time_lt_entry_time", "signal_time", "entry_time"),
        ("entry_time_lte_exit_time", "entry_time", "exit_time"),
    ]
    if variant_id != "ce_lifecycle_native_light_confirm_v1":
        required_time[4:4] = ["pullback_start_time", "pullback_end_time", "relaunch_time"]
        checks[4:4] = [
            ("acceptance_end_time_lte_pullback_start_time", "acceptance_end_time", "pullback_start_time"),
            ("pullback_start_time_lte_pullback_end_time", "pullback_start_time", "pullback_end_time"),
            ("pullback_end_time_lte_relaunch_time", "pullback_end_time", "relaunch_time"),
            ("relaunch_time_lt_signal_time", "relaunch_time", "signal_time"),
        ]
    return AuditProfile(
        required_lineage_fields=lineage,
        required_time_fields=required_time,
        time_order_checks=checks,
    )


def select_family_decision(variant_summaries: Mapping[str, Mapping[str, object]]) -> str:
    ce_native = variant_summaries.get("ce_lifecycle_native_light_confirm_v1", {})
    ce_shallow = variant_summaries.get("ce_lifecycle_shallow_momentum_v1", {})
    bp_shallow = variant_summaries.get("bp_shallow_momentum_capped_risk_v3", {})
    if _robust_path(bp_shallow, minimum_closed=30):
        return "C. BP shallow remains best path; proceed to validation-prep for that subtype only."
    if _robust_path(ce_shallow, minimum_closed=20) and _number(ce_shallow.get("base_net_R_avg")) > _number(
        bp_shallow.get("base_net_R_avg")
    ):
        return "D. CE shallow momentum is best path; proceed to subtype validation."
    discussable = sum(1 for row in variant_summaries.values() if int(row.get("closed_trades") or 0) >= 12)
    if discussable >= 2 and any(_near_positive(row) for row in variant_summaries.values()):
        return "A. Trade count and subtype diversity improved; run one bounded profit-optimization round."
    if int(ce_native.get("closed_trades") or 0) >= 30:
        return "B. CE native revived but needs quality optimization; keep CE diagnostic and optimize next."
    return "E. Results remain too narrow or weak; pause TC family expansion."


def _ensure_shared_event_store(
    *,
    store: TcFamilyEventStore,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    max_entry_windows: int | None,
    candidate_end_ms: int | None,
    chunk_size: int,
    cache_root: Path,
) -> dict[str, object]:
    status = store.status()
    if status["complete"]:
        return {**status, **store.read_scan_summary(), "reused": True}
    all_context_rows, _ = _build_context_rows(
        repository,
        preset=preset,
        max_entry_windows=max_entry_windows,
        setup_filter=("breakout_pullback",),
    )
    context_rows = _filter_context_rows_by_candidate_end(
        _unique_structure_context_rows(all_context_rows),
        candidate_end_ms=candidate_end_ms,
    )
    processed = min(int(status["processed_windows"]), len(context_rows))
    summary = store.read_scan_summary()
    summary.setdefault("total_windows", len(all_context_rows))
    summary.setdefault("candidate_end_ms", candidate_end_ms)
    summary.setdefault("evaluated_structure_windows", processed)
    summary.setdefault("candidate_ready_windows", 0)
    summary.setdefault("structure_zones_found", 0)
    summary.setdefault("breakout_event_seeds", 0)
    summary.setdefault("lifecycle_event_rows", 0)
    summary.setdefault("compression_context_count", 0)
    summary.setdefault("replay_eligible_event_rows_seen", 0)
    distributions = {
        name: Counter(summary.get(name, {}))
        for name in (
            "breakout_class_distribution",
            "pullback_health_distribution",
            "relaunch_quality_distribution",
            "target_quality_distribution",
        )
    }
    runtime_cache: dict[str, Any] = {}
    adapter = BreakoutPullbackAdapter()
    for start in range(processed, len(context_rows), chunk_size):
        chunk = context_rows[start : start + chunk_size]
        keyed_context = []
        for row in chunk:
            payload = dict(row)
            payload["context_key"] = store.context_key(row)
            keyed_context.append(payload)
        store.append_context_rows(keyed_context)
        diagnostics = diagnostic_rows_for_adapter(
            adapter=adapter,
            repository=repository,
            preset=preset,
            context_rows=chunk,
            variant_id="tc_family_shared_lifecycle_core",
            parameter_overrides=None,
            runtime_cache=runtime_cache,
            event_predicate=lambda row: any(
                family_event_eligible(row, variant_id) for variant_id in FAMILY_VARIANT_IDS
            ),
        )
        context_diagnostics = [row for row in diagnostics if row.get("diagnostic_scope") == "context_window"]
        events = [row for row in diagnostics if row.get("diagnostic_scope") == "event_lifecycle"]
        summary["evaluated_structure_windows"] = int(summary["evaluated_structure_windows"]) + len(context_diagnostics)
        summary["candidate_ready_windows"] = int(summary["candidate_ready_windows"]) + sum(
            1 for row in context_diagnostics if row.get("candidate_ready")
        )
        summary["structure_zones_found"] = int(summary["structure_zones_found"]) + sum(
            int(row.get("structure_zones_found") or 0) for row in context_diagnostics
        )
        summary["breakout_event_seeds"] = int(summary["breakout_event_seeds"]) + sum(
            int(row.get("breakout_event_seeds") or 0) for row in context_diagnostics
        )
        summary["lifecycle_event_rows"] = int(summary["lifecycle_event_rows"]) + len(events)
        summary["compression_context_count"] = int(summary["compression_context_count"]) + sum(
            1 for row in events if row.get("compression_context")
        )
        for row in events:
            distributions["breakout_class_distribution"][str(row.get("breakout_class") or "unknown")] += 1
            distributions["pullback_health_distribution"][str(row.get("pullback_health_class") or "unknown")] += 1
            distributions["relaunch_quality_distribution"][str(row.get("relaunch_quality_class") or "unknown")] += 1
            distributions["target_quality_distribution"][str(row.get("target_quality_class") or "unknown")] += 1
        replay_rows = []
        for row in events:
            if not _event_replay_relevant(row) or not _event_is_causal_at_context(row):
                continue
            compact = compact_family_event(row)
            compact["context_key"] = store.context_key(row)
            compact["event_key"] = str(compact.get("lifecycle_event_id") or compact.get("breakout_event_id") or "")
            replay_rows.append(compact)
        summary["replay_eligible_event_rows_seen"] = int(summary["replay_eligible_event_rows_seen"]) + len(replay_rows)
        store.append_event_rows(replay_rows)
        for name, counter in distributions.items():
            summary[name] = dict(counter)
        processed = start + len(chunk)
        store.write_scan_summary(summary)
        store.mark_progress(processed_windows=processed)
    store.mark_complete(processed_windows=len(context_rows))
    final_status = store.status()
    summary["replay_event_rows"] = final_status["event_rows"]
    store.write_scan_summary(summary)
    _write_shared_cache_artifacts(
        cache_root=cache_root,
        store=store,
        dataset_window=dataset_window,
        config_hash=preset.config_fingerprint,
        summary=summary,
    )
    return {**final_status, **summary, "reused": False}


def _run_variant(
    *,
    variant_id: str,
    store: TcFamilyEventStore,
    cache_status: Mapping[str, object],
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_dir: Path,
    cost_tiers: Sequence[str],
    candidate_end_ms: int | None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = _select_variant_candidates_from_store(store=store, variant_id=variant_id)
    filter_rows_list: list[dict[str, object]] = []
    for candidate in candidate_rows:
        filtered = _filter_candidate(candidate, preset)
        filtered["row_type"] = "formal_approved" if filtered.get("formal_approved") else "rejected_candidate"
        filtered["eligible_for_performance"] = False
        filtered["proposal_only"] = True
        filter_rows_list.append(apply_capped_risk_sizing(filtered, preset))
    closed_rows = _execute_capped_candidates(
        repository=repository,
        preset=preset,
        filter_rows=filter_rows_list,
        cost_tiers=cost_tiers,
    )
    filter_rows = tuple(filter_rows_list)
    summary_rows = tuple(
        {
            **row,
            "proposal_approved_after_cap": sum(1 for item in filter_rows if item.get("proposal_approved_after_cap")),
        }
        for row in _summary_rows(candidate_rows, filter_rows, closed_rows)
    )
    robustness_rows = _robustness_rows(closed_rows)
    diagnostic_rows = (
        *_diagnostic_rows(filter_rows, candidate_rows, closed_rows),
        {
            "row_type": "diagnostic_only",
            "diagnostic_only": True,
            "eligible_for_performance": False,
            "diagnostic_name": "tc_family_shared_cache",
            "variant_id": variant_id,
            "cache_status": dict(cache_status),
        },
    )
    review_log_rows = _review_log_rows(
        strategy=family_variant_setup(variant_id),
        pass_name=variant_id,
        summary_rows=summary_rows,
        diagnostic_rows=diagnostic_rows,
        anatomy_summary={},
    )
    regression_baseline = _regression_baseline(summary_rows)
    write_jsonl(output_dir / "candidate_rows.jsonl", candidate_rows)
    write_jsonl(output_dir / "filter_results_research.jsonl", filter_rows)
    write_jsonl(output_dir / "closed_trade_rows.jsonl", closed_rows)
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_log_rows)
    write_json(output_dir / "regression_baseline.json", regression_baseline)
    setup = family_variant_setup(variant_id)
    manifest = RunManifest(
        run_id=stable_fingerprint({"variant_id": variant_id, "output_dir": str(output_dir)})[:24],
        strategy=setup,
        adapter_version=f"tc_family_trade_count.v1+{CORE_ENGINE_VERSION}",
        dataset_window=dataset_window,
        artifact_contract=_family_artifact_contract().as_dict(),
        audit_profile=family_audit_profile(variant_id).as_dict(),
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
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "shared_cache_fingerprint": store.fingerprint_hash,
            "scan_start_ms": preset.scan.start_ms,
            "scan_end_ms": preset.scan.end_ms,
            "candidate_end_ms": candidate_end_ms,
        },
        baseline_ref=str(store.path),
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="TC family trade-count expansion; shared lifecycle cache and capped proposal sizing.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=setup,
        stage=f"tc_family_trade_count_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-trade-count-expansion",
        config_hash=preset.config_fingerprint,
        notes="Proposal-only family variant; LR final evidence untouched.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=setup,
        stage=f"tc_family_trade_count_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-trade-count-expansion",
        adapter_version=manifest.adapter_version,
        baseline_ref=str(store.path),
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        config_hash=preset.config_fingerprint,
        notes="Proposal-only capped risk sizing family validation.",
        tags=["tc_family", variant_id, "capped_risk_sizing"],
    )
    audit = run_full_pipeline_audit(
        strategy=setup,
        artifact_dir=output_dir,
        registry=None,
        output_dir=output_dir / "full_audit",
    )
    summary = _variant_summary(
        variant_id=variant_id,
        cache_status=cache_status,
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
        robustness_rows=robustness_rows,
        audit=audit,
    )
    write_json(output_dir / "variant_summary.json", summary)
    return summary


def _select_variant_candidates_from_store(
    *,
    store: TcFamilyEventStore,
    variant_id: str,
) -> tuple[dict[str, object], ...]:
    selected_by_signal: dict[tuple[str, str, str, int], dict[str, object]] = {}
    for batch in store.iter_event_batches():
        for candidate in select_family_candidates(batch, variant_id):
            key = _candidate_signal_key(candidate)
            current = selected_by_signal.get(key)
            if current is None or _candidate_rank(candidate) > _candidate_rank(current):
                selected_by_signal[key] = candidate
    return tuple(
        selected_by_signal[key]
        for key in sorted(selected_by_signal, key=lambda item: (item[3], item[0], item[1], item[2]))
    )


def _candidate_signal_key(candidate: Mapping[str, object]) -> tuple[str, str, str, int]:
    return (
        str(candidate.get("asset") or ""),
        str(candidate.get("profile") or ""),
        str(candidate.get("direction") or ""),
        int(candidate.get("timestamp_ms") or 0),
    )


def _candidate_rank(candidate: Mapping[str, object]) -> tuple[float, float, float, str]:
    return (
        _number(candidate.get("candidate_rank_score")) or 0.0,
        _number(candidate.get("compression_score")) or 0.0,
        _number(candidate.get("breakout_score")) or 0.0,
        str(candidate.get("lifecycle_event_id") or ""),
    )


def _execute_capped_candidates(
    *,
    repository,
    preset: BacktestPresetConfig,
    filter_rows: list[dict[str, object]],
    cost_tiers: Sequence[str],
    execution_timeframe: str | None = None,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    scheduling_tier = "base" if "base" in cost_tiers else str(cost_tiers[0])
    scheduling_preset = _tier_preset(preset, scheduling_tier)
    accepted_candidate_ids: set[str] = set()
    open_intervals: list[tuple[int, int, float]] = []
    ordered = sorted(
        filter_rows,
        key=lambda row: (
            int(row.get("timestamp_ms") or 0),
            -(_number(row.get("candidate_rank_score")) or 0.0),
            str(row.get("candidate_id") or ""),
        ),
    )
    for candidate in ordered:
        if not candidate.get("proposal_approved_after_cap"):
            candidate["proposal_execution_status"] = "not_approved_after_cap"
            continue
        closed, reject = _simulate_capped_candidate(
            repository=repository,
            candidate=candidate,
            tier_preset=scheduling_preset,
            tier_name=scheduling_tier,
            execution_timeframe=execution_timeframe,
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
            candidate["approval_basis"] = "rejected_after_cap"
            candidate["proposal_execution_status"] = "not_executed"
            candidate["proposal_execution_reject_reason"] = "portfolio_heat_exceeded_after_cap"
            continue
        accepted_candidate_ids.add(str(candidate.get("candidate_id") or ""))
        open_intervals.append(
            (
                int(closed["entry_time"]),
                int(closed["exit_time"]),
                float(closed["actual_risk_after_cap_pct"]),
            )
        )
        candidate["portfolio_heat"] = closed["actual_risk_after_cap_pct"]
        candidate["portfolio_heat_after_entry"] = closed["actual_risk_after_cap_pct"]
        candidate["proposal_execution_status"] = "closed"
        candidate["proposal_execution_reject_reason"] = ""
        rows.append(closed)

    for tier_name in cost_tiers:
        if tier_name == scheduling_tier:
            continue
        tier_preset = _tier_preset(preset, tier_name)
        for candidate in ordered:
            if str(candidate.get("candidate_id") or "") not in accepted_candidate_ids:
                continue
            closed, _ = _simulate_capped_candidate(
                repository=repository,
                candidate=candidate,
                tier_preset=tier_preset,
                tier_name=tier_name,
                execution_timeframe=execution_timeframe,
            )
            if closed is not None:
                rows.append(closed)
    return tuple(rows)


def _simulate_capped_candidate(
    *,
    repository,
    candidate: Mapping[str, object],
    tier_preset: BacktestPresetConfig,
    tier_name: str,
    execution_timeframe: str | None = None,
) -> tuple[dict[str, object] | None, str]:
    signal_input = _input_from_filter_row(
        repository,
        candidate,
        tier_preset,
        execution_timeframe=execution_timeframe,
    )
    if signal_input is None:
        return None, "missing_execution_candles"
    intent, atr, reasons = SignalOrderAdapter().to_order_intent(
        signal_input.signal,
        signal_input.execution_candles,
        point_value=tier_preset.execution.point_value,
    )
    if intent is None or atr is None or reasons:
        return None, ",".join(reasons) or "execution_adapter_rejected"
    if not _valid_trade_geometry(intent):
        return None, "actual_entry_invalidates_stop_or_target"
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
    if actual_risk_pct > tier_preset.risk.max_portfolio_heat_pct:
        return None, "portfolio_heat_exceeded_after_cap"
    order = SimulatedOrder(
        intent=intent,
        quantity=quantity,
        notional_value=notional,
        risk_amount=actual_risk,
        cost_estimate=CostEstimate(),
    )
    decision = RiskDecision(
        status="approved",
        reason_codes=(),
        risk_pct=actual_risk_pct,
        risk_amount=actual_risk,
        approved_order=order,
    )
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
            "proposal_approved_after_cap": True,
            "approval_basis": "proposal_approved_after_cap",
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "theoretical_risk_based_position_size": candidate.get("theoretical_risk_based_position_size"),
            "capped_position_size": quantity,
            "theoretical_notional": candidate.get("theoretical_notional"),
            "capped_notional": notional,
            "margin_required_before_cap": candidate.get("margin_required_before_cap"),
            "margin_required_after_cap": margin_required,
            "actual_risk_after_cap": actual_risk,
            "actual_risk_after_cap_pct": actual_risk_pct,
            "portfolio_heat": actual_risk_pct,
        }
    )
    return closed, ""


def _variant_summary(
    *,
    variant_id: str,
    cache_status: Mapping[str, object],
    candidate_rows: Sequence[Mapping[str, object]],
    filter_rows: Sequence[Mapping[str, object]],
    closed_rows: Sequence[Mapping[str, object]],
    robustness_rows: Sequence[Mapping[str, object]],
    audit,
) -> dict[str, object]:
    base = [row for row in closed_rows if row.get("cost_tier") == "base"]
    tier_metrics = {
        tier: _metrics([row for row in closed_rows if row.get("cost_tier") == tier])
        for tier in ("base", "stress", "harsh")
    }
    base_metrics = tier_metrics["base"]
    proposal_approved = sum(1 for row in filter_rows if row.get("proposal_approved_after_cap"))
    formal_approved = sum(1 for row in filter_rows if row.get("formal_approved"))
    walk_forward = [
        row for row in robustness_rows if row.get("robustness_type") == "walk_forward"
    ]
    exposure = next((row for row in robustness_rows if row.get("robustness_type") == "exposure"), {})
    reject_reasons = Counter(str(row.get("reject_reason") or "approved") for row in filter_rows)
    margin_before = sum(1 for row in filter_rows if row.get("risk_reject_reason_before_cap") == "margin_required_too_high")
    margin_after = sum(1 for row in filter_rows if row.get("risk_reject_reason_after_cap") == "margin_required_too_high")
    return {
        "variant_id": variant_id,
        "setup_id": family_variant_setup(variant_id),
        "total_windows": int(cache_status.get("total_windows") or 0),
        "evaluated_structure_windows": int(cache_status.get("evaluated_structure_windows") or 0),
        "compression_context_count": int(cache_status.get("compression_context_count") or 0),
        "lifecycle_event_seeds": int(cache_status.get("breakout_event_seeds") or 0),
        "candidate_ready_windows": int(cache_status.get("candidate_ready_windows") or 0),
        "raw_candidates": len(candidate_rows),
        "formal_approved": formal_approved,
        "proposal_approved_after_cap": proposal_approved,
        "closed_trades": len(base),
        "approved_raw": _ratio(proposal_approved, len(candidate_rows)),
        "closed_approved": _ratio(len(base), proposal_approved),
        "base_net_R_avg": base_metrics.get("net_R_avg"),
        "stress_net_R_avg": tier_metrics["stress"].get("net_R_avg"),
        "harsh_net_R_avg": tier_metrics["harsh"].get("net_R_avg"),
        "total_R": base_metrics.get("total_net_R"),
        "PF": base_metrics.get("profit_factor"),
        "median_R": base_metrics.get("median_R"),
        "win_rate": base_metrics.get("win_rate"),
        "avg_win_R": base_metrics.get("avg_win_R"),
        "avg_loss_R": base_metrics.get("avg_loss_R"),
        "max_drawdown": base_metrics.get("max_drawdown"),
        "R_std": base_metrics.get("R_std"),
        "top_1_trade_R_contribution": base_metrics.get("top_1_trade_R_contribution"),
        "top_2_trades_R_contribution": base_metrics.get("top_2_trades_R_contribution"),
        "net_R_avg_excluding_top_1": base_metrics.get("net_R_avg_excluding_top_1"),
        "net_R_avg_excluding_top_2": base_metrics.get("net_R_avg_excluding_top_2"),
        "breakout_class_distribution": dict(Counter(str(row.get("breakout_class") or "unknown") for row in candidate_rows)),
        "pullback_health_distribution": dict(Counter(str(row.get("pullback_health_class") or "unknown") for row in candidate_rows)),
        "relaunch_quality_distribution": dict(Counter(str(row.get("relaunch_quality_class") or "unknown") for row in candidate_rows)),
        "stop_anchor_type_distribution": dict(Counter(str(row.get("stop_anchor_type") or "unknown") for row in filter_rows)),
        "target_source_distribution": dict(Counter(str(row.get("target_source") or "unknown") for row in filter_rows)),
        "candidate_quality_tag_distribution": dict(Counter(str(row.get("candidate_quality_tag") or "unknown") for row in candidate_rows)),
        "asset_split": dict(Counter(str(row.get("asset") or "unknown") for row in base)),
        "profile_split": dict(Counter(str(row.get("profile") or "unknown") for row in base)),
        "direction_split": dict(Counter(str(row.get("direction") or "unknown") for row in base)),
        "trend_state_split": dict(Counter(str(row.get("trend_state") or "unknown") for row in base)),
        "reject_reason_distribution": dict(reject_reasons),
        "stop_distance_too_near": reject_reasons["stop_distance_too_near"],
        "stop_distance_too_wide": reject_reasons["stop_distance_too_wide"] + reject_reasons["stop_distance_too_far"],
        "structural_stop_too_near": reject_reasons["structural_stop_too_near"],
        "structural_stop_too_wide": reject_reasons["structural_stop_too_wide"],
        "margin_required_too_high_before_cap": margin_before,
        "margin_required_too_high_after_cap": margin_after,
        "portfolio_heat_exceeded_after_cap": sum(
            1 for row in filter_rows if row.get("risk_reject_reason_after_cap") == "portfolio_heat_exceeded_after_cap"
        ),
        "portfolio_heat_max": exposure.get("portfolio_heat_max"),
        "max_concurrent_positions": exposure.get("max_concurrent_positions"),
        "capped_by_notional": sum(1 for row in filter_rows if row.get("capped_by_notional")),
        "stop_distance_ATR_distribution": _numeric_summary(filter_rows, "stop_atr_multiple"),
        "notional_before_cap_distribution": _numeric_summary(filter_rows, "theoretical_notional"),
        "notional_after_cap_distribution": _numeric_summary(filter_rows, "capped_notional"),
        "position_size_before_cap_distribution": _numeric_summary(filter_rows, "theoretical_risk_based_position_size"),
        "position_size_after_cap_distribution": _numeric_summary(filter_rows, "capped_position_size"),
        "actual_risk_after_cap_distribution": _numeric_summary(filter_rows, "actual_risk_after_cap_pct"),
        "walk_forward_windows": len(walk_forward),
        "positive_walk_forward_windows": sum(1 for row in walk_forward if _number(row.get("net_R_avg")) > 0),
        "negative_walk_forward_windows": sum(1 for row in walk_forward if _number(row.get("net_R_avg")) < 0),
        "full_audit_gate": "passed" if audit.audit_passed else "failed",
        "full_audit_blocking_issues": list(audit.blocking_issues),
        "no_lookahead": "passed" if audit.no_lookahead_rows and all(row.get("passed") for row in audit.no_lookahead_rows) else "failed",
        "metric_recompute": "passed" if audit.metric_recompute_rows and all(row.get("passed") for row in audit.metric_recompute_rows) else "failed",
        "regression_baseline": "present",
        "cross_run_artifact_reuse": "reused" if cache_status.get("reused") else "created",
        "sample_size_warning": len(base) < 30,
        "interpretation": _variant_interpretation(variant_id, len(candidate_rows), proposal_approved, len(base), tier_metrics),
    }


def _write_shared_cache_artifacts(
    *,
    cache_root: Path,
    store: TcFamilyEventStore,
    dataset_window: str,
    config_hash: str,
    summary: Mapping[str, object],
) -> None:
    manifest_path = cache_root / "shared_cache_manifest.json"
    write_json(
        manifest_path,
        {
            "row_type": "summary_row",
            "cache_type": "tc_family_shared_lifecycle_event_store",
            "cache_path": str(store.path),
            "fingerprint": store.fingerprint,
            "fingerprint_hash": store.fingerprint_hash,
            "summary": dict(summary),
            "replay_scope": list(FAMILY_VARIANT_IDS),
            "complete": True,
        },
    )
    index = build_index_for_directory(
        cache_root,
        strategy="trend_continuation_family",
        stage="shared_lifecycle_event_cache",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-trade-count-expansion",
        config_hash=config_hash,
        notes="Compact globally deduplicated event store; full repeated lifecycle rows are not persisted.",
    )
    write_artifact_index(index, cache_root)
    register_research_run(
        registry_path=cache_root / "research_run_registry.json",
        artifact_index_path=cache_root / "artifact_index.json",
        strategy="trend_continuation_family",
        stage="shared_lifecycle_event_cache",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-trade-count-expansion",
        adapter_version=f"tc_family_trade_count.v1+{CORE_ENGINE_VERSION}",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=True,
        config_hash=config_hash,
        notes="Reusable compact shared lifecycle event cache.",
        tags=["shared_cache", "lifecycle_core", "compact_deduplicated"],
    )


def _cache_fingerprint(
    *,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    max_entry_windows: int | None,
    candidate_end_ms: int | None,
) -> dict[str, object]:
    database_path = Path(getattr(repository, "database_path", "unknown")).resolve()
    stat = database_path.stat() if database_path.exists() else None
    return {
        "cache_contract": "tc_family_signal_context_event_store.v5",
        "context_sampling_policy": "latest_entry_context_per_structure_bar.v1",
        "core_engine_version": CORE_ENGINE_VERSION,
        "diagnostic_adapter_version": BreakoutPullbackAdapter.adapter_version,
        "dataset_window": dataset_window,
        "database_path": str(database_path),
        "database_size": None if stat is None else stat.st_size,
        "database_mtime_ns": None if stat is None else stat.st_mtime_ns,
        "config_fingerprint": preset.config_fingerprint,
        "max_entry_windows": max_entry_windows,
        "scan_start_ms": preset.scan.start_ms,
        "scan_end_ms": preset.scan.end_ms,
        "candidate_end_ms": candidate_end_ms,
        "assets": [target.inst_id for target in preset.assets.targets],
        "profiles": list(preset.scan.profile_keys),
        "setup_filter": ["breakout_pullback"],
        "replay_variants": list(FAMILY_VARIANT_IDS),
    }


def _filter_context_rows_by_candidate_end(
    rows: Sequence[Mapping[str, object]],
    *,
    candidate_end_ms: int | None,
) -> tuple[dict[str, object], ...]:
    return tuple(
        dict(row)
        for row in rows
        if candidate_end_ms is None or int(row["timestamp_ms"]) <= candidate_end_ms
    )


def _family_artifact_contract() -> ArtifactContract:
    return ArtifactContract(
        required_inputs=["candidate_rows", "filter_results", "execution_rows", "run_manifest"],
        required_outputs=[
            "closed_trade_rows",
            "diagnostic_rows",
            "summary_rows",
            "robustness_rows",
            "regression_baseline",
            "audit_report",
        ],
    )


def _event_replay_relevant(row: Mapping[str, object]) -> bool:
    if str(row.get("breakout_class") or "") == "failed_breakout":
        return False
    if row.get("immediate_reclaim") or row.get("high_volume_no_result"):
        return False
    if row.get("compression_context") and str(row.get("acceptance_status") or "") != "failed":
        return True
    return (
        str(row.get("breakout_class") or "") in {"strong_breakout", "accepted_breakout"}
        and str(row.get("pullback_zone_type") or "") == "shallow_pullback"
        and str(row.get("pullback_health_class") or "") in {"healthy", "acceptable"}
        and str(row.get("relaunch_quality_class") or "") in {"strong", "acceptable"}
        and str(row.get("structural_stop_quality") or "") == "valid"
        and str(row.get("target_quality_class") or "") in {"good", "acceptable"}
    )


def _event_is_causal_at_context(row: Mapping[str, object]) -> bool:
    event_time = row.get("relaunch_time") or row.get("acceptance_end_time")
    context_time = row.get("timestamp_ms")
    timeframe_ms = _timeframe_ms(str(row.get("structure_timeframe") or ""))
    if event_time is None or context_time is None or timeframe_ms <= 0:
        return False
    delay_ms = int(context_time) - int(event_time)
    return 0 <= delay_ms < timeframe_ms


def _timeframe_ms(timeframe: str) -> int:
    normalized = timeframe.strip().lower()
    if len(normalized) < 2 or not normalized[:-1].isdigit():
        return 0
    multiplier = {"m": 60_000, "h": 60 * 60_000, "d": 24 * 60 * 60_000}.get(normalized[-1])
    return 0 if multiplier is None else int(normalized[:-1]) * multiplier


def _valid_trade_geometry(intent) -> bool:
    if intent.direction == "LONG":
        return intent.stop_loss < intent.entry_price and (intent.target_price is None or intent.target_price > intent.entry_price)
    return intent.stop_loss > intent.entry_price and (intent.target_price is None or intent.target_price < intent.entry_price)


def _unique_structure_context_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    selected: dict[tuple[str, str, str, str, int], dict[str, object]] = {}
    for row in rows:
        timeframe = str(row.get("structure_timeframe") or "")
        duration = _timeframe_duration_ms(timeframe)
        timestamp = int(row.get("timestamp_ms") or 0)
        key = (
            str(row.get("venue") or ""),
            str(row.get("inst_id") or ""),
            str(row.get("inst_type") or ""),
            str(row.get("profile") or ""),
            timestamp // duration,
        )
        selected[key] = dict(row)
    return tuple(selected.values())


def _timeframe_duration_ms(timeframe: str) -> int:
    unit = timeframe[-1:].lower()
    try:
        value = int(timeframe[:-1])
    except ValueError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe}") from exc
    multipliers = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if unit not in multipliers or value <= 0:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return value * multipliers[unit]


def _portfolio_heat_allows(
    existing_intervals: Sequence[tuple[int, int, float]],
    *,
    entry_time: int,
    exit_time: int,
    risk_pct: float,
    max_heat_pct: float,
) -> bool:
    overlapping_heat = sum(
        interval_risk
        for interval_entry, interval_exit, interval_risk in existing_intervals
        if entry_time <= interval_exit and interval_entry <= exit_time
    )
    return overlapping_heat + risk_pct <= max_heat_pct + 1e-12


def _robust_path(row: Mapping[str, object], *, minimum_closed: int) -> bool:
    return (
        int(row.get("closed_trades") or 0) >= minimum_closed
        and all(_number(row.get(key)) > 0 for key in ("base_net_R_avg", "stress_net_R_avg", "harsh_net_R_avg"))
        and _number(row.get("net_R_avg_excluding_top_1")) > 0
        and _number(row.get("net_R_avg_excluding_top_2")) > 0
        and int(row.get("margin_required_too_high_after_cap") or 0)
        <= int(row.get("margin_required_too_high_before_cap") or 0)
    )


def _near_positive(row: Mapping[str, object]) -> bool:
    values = [row.get(key) for key in ("base_net_R_avg", "stress_net_R_avg", "harsh_net_R_avg")]
    if any(value is None for value in values):
        return False
    return _number(values[0]) >= -0.02 and _number(values[1]) >= -0.05 and _number(values[2]) >= -0.08


def _decision_reason(decision: str, summaries: Mapping[str, Mapping[str, object]]) -> str:
    counts = ", ".join(f"{key} closed={value.get('closed_trades', 0)}" for key, value in summaries.items())
    return f"{decision.split('.', 1)[0]} selected from bounded decision rules; {counts}."


def _next_actions(decision: str) -> list[str]:
    code = decision[:1]
    if code == "A":
        return ["Run one bounded profit-optimization round without changing formal risk or cost boundaries."]
    if code == "B":
        return ["Keep CE native diagnostic and optimize quality while preserving recovered trade count."]
    if code == "C":
        return ["Prepare one bounded BP shallow validation round and test concentration risk before any formalization."]
    if code == "D":
        return ["Prepare CE shallow subtype validation; keep CE native and BP evidence separate."]
    return ["Pause TC family expansion and retain compact shared cache, manifests, and audit evidence for later review."]


def _variant_interpretation(
    variant_id: str,
    raw: int,
    approved: int,
    closed: int,
    tier_metrics: Mapping[str, Mapping[str, object]],
) -> str:
    if closed == 0:
        return f"{variant_id} produced no closed trades; diagnose conversion before any profit optimization."
    base = _number(tier_metrics["base"].get("net_R_avg"))
    harsh = _number(tier_metrics["harsh"].get("net_R_avg"))
    return (
        f"{variant_id} raw/approved/closed={raw}/{approved}/{closed}; "
        f"base avg R={base:.4f}, harsh avg R={harsh:.4f}. "
        "Trade count and conversion are interpreted before profit optimization."
    )


def _numeric_summary(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, float | int | None]:
    clean = sorted(
        value
        for row in rows
        if (value := _number(row.get(field), default=None)) is not None
    )
    if not clean:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {"count": len(clean), "min": clean[0], "median": median(clean), "max": clean[-1]}


def _number(value: object, default: float | None = 0.0) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio(value: int, total: int) -> float | None:
    return None if total == 0 else value / total


def _remove_empty_duckdb_temp(cache_root: Path) -> None:
    temp_dir = Path(cache_root) / "duckdb_tmp"
    if temp_dir.exists() and not any(temp_dir.iterdir()):
        temp_dir.rmdir()


__all__ = (
    "TcFamilyTradeCountExpansionResult",
    "family_audit_profile",
    "run_tc_family_trade_count_expansion",
    "select_family_decision",
)
