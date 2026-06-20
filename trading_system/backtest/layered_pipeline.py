from __future__ import annotations

import json
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

from trading_system.backtest.contract_risk import estimate_contract_risk
from trading_system.backtest.execution import BacktestExecutionEngine, BacktestSignalInput
from trading_system.backtest.risk import AccountState, CostEstimate, OrderIntent, RiskEngine
from trading_system.backtest.scanner import BacktestScanTarget
from trading_system.backtest.layered_cache import (
    artifact_paths,
    candidate_generation_config_hash,
    context_config_hash,
    data_hash_from_counts,
    execution_config_hash,
    filter_config_hash,
    read_json,
    read_jsonl,
    stable_hash,
    write_csv,
    write_json,
    write_jsonl,
)
from trading_system.config.loader import BacktestPresetConfig
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.reports.proposal_diagnostics import build_diagnostics_markdown, write_diagnostics_report
from trading_system.strategies.base import StrategySignal
from trading_system.strategies.trend_price_volume_v1.candidates import generate_raw_candidates
from trading_system.strategies.trend_price_volume_v1.features import build_market_regime, confirm_volume_price
from trading_system.timeframe_profiles import get_profile


LAYERED_MODES = ("candidate_only", "filter_replay", "full_backtest", "gate_ablation")
FILTER_STAGE_ORDER = (
    "direction_and_trend",
    "volume_filter",
    "reclaim_and_choch",
    "risk_filter",
    "contract_risk_filter",
    "position_aware_filter",
)


@dataclass(frozen=True)
class LayeredProposalResult:
    mode: str
    scanned_windows: int
    raw_candidates_count: int
    cache_manifest: Mapping[str, object]
    context_path: Path
    raw_candidates_path: Path
    filter_results_path: Path
    execution_results_path: Path
    funnel_summary_path: Path
    gate_ablation_path: Path
    diagnostics_report_path: Path
    manifest_path: Path
    summary_rows: tuple[dict[str, object], ...]


def run_layered_proposal(
    *,
    repository,
    preset: BacktestPresetConfig,
    mode: str,
    cache_dir: str | Path,
    max_entry_windows: int | None = None,
    cost_tiers: Sequence[str] = ("base",),
    force_context: bool = False,
    force_candidates: bool = False,
    force_filter: bool = False,
    force_execution: bool = False,
    setup_filter: Sequence[str] | None = None,
    progress_path: str | Path | None = None,
) -> LayeredProposalResult:
    if mode not in LAYERED_MODES:
        raise ValueError(f"unsupported layered mode: {mode}")
    effective_setup_filter = tuple(setup_filter or preset.strategy.enabled_setups)
    paths = artifact_paths(cache_dir)
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    context_rows, raw_rows, coverage_rows, context_status, raw_status = _ensure_candidates(
        repository=repository,
        preset=preset,
        paths=paths,
        max_entry_windows=max_entry_windows,
        force_context=force_context,
        force_candidates=force_candidates,
        setup_filter=effective_setup_filter,
        progress_path=Path(progress_path) if progress_path is not None else None,
    )

    filter_rows: tuple[dict[str, object], ...] = ()
    execution_rows: tuple[dict[str, object], ...] = ()
    gate_rows: tuple[dict[str, object], ...] = ()
    funnel_rows: tuple[dict[str, object], ...] = ()
    filter_status = "not_requested"
    execution_status = "not_requested"
    if mode in {"filter_replay", "full_backtest", "gate_ablation"}:
        filter_rows, filter_status = _ensure_filter_results(
            preset=preset,
            paths=paths,
            raw_rows=raw_rows,
            force_filter=force_filter,
        )
        funnel_rows = _funnel_rows(raw_rows, filter_rows)
        write_csv(paths.funnel_summary_path, funnel_rows, preferred_fields=_FUNNEL_FIELDS)
        _write_stage_progress(
            progress_path,
            stage="filter_complete",
            context_rows=len(context_rows),
            raw_candidates=len(raw_rows),
            filter_rows=len(filter_rows),
        )
    else:
        write_csv(paths.funnel_summary_path, (), preferred_fields=_FUNNEL_FIELDS)

    if mode in {"full_backtest", "gate_ablation"}:
        if mode == "gate_ablation":
            gate_rows = _gate_ablation_rows(raw_rows, filter_rows)
            write_csv(paths.gate_ablation_path, gate_rows, preferred_fields=("stage", "input_count", "passed_count", "rejected_count", "top_reject_reason"))
        execution_rows, execution_status = _ensure_execution_results(
            repository=repository,
            preset=preset,
            paths=paths,
            filter_rows=filter_rows,
            cost_tiers=tuple(cost_tiers),
            force_execution=force_execution,
        )
        _write_stage_progress(
            progress_path,
            stage="execution_complete",
            context_rows=len(context_rows),
            raw_candidates=len(raw_rows),
            filter_rows=len(filter_rows),
            execution_rows=len(execution_rows),
        )
    else:
        write_jsonl(paths.execution_results_path, ())
        if mode != "gate_ablation":
            write_csv(paths.gate_ablation_path, (), preferred_fields=("stage", "input_count", "passed_count", "rejected_count", "top_reject_reason"))

    if mode == "filter_replay":
        write_csv(paths.gate_ablation_path, (), preferred_fields=("stage", "input_count", "passed_count", "rejected_count", "top_reject_reason"))

    manifest = _manifest(
        preset=preset,
        coverage_rows=coverage_rows,
        context_status=context_status,
        raw_status=raw_status,
        filter_status=filter_status,
        execution_status=execution_status,
        context_rows=context_rows,
        raw_rows=raw_rows,
        filter_rows=filter_rows,
        execution_rows=execution_rows,
        max_entry_windows=max_entry_windows,
        cost_tiers=tuple(cost_tiers),
        setup_filter=effective_setup_filter,
        elapsed_seconds=perf_counter() - started,
    )
    write_json(paths.manifest_path, manifest)
    report = build_diagnostics_markdown(
        mode=mode,
        scanned_windows=len(context_rows),
        raw_candidates_count=len(raw_rows),
        filter_rows=filter_rows,
        execution_rows=execution_rows,
        cache_manifest=manifest,
    )
    write_diagnostics_report(paths.diagnostics_report_path, report)
    _write_stage_progress(
        progress_path,
        stage="layered_complete",
        context_rows=len(context_rows),
        raw_candidates=len(raw_rows),
        filter_rows=len(filter_rows),
        execution_rows=len(execution_rows),
        elapsed_seconds=manifest.get("elapsed_seconds"),
    )
    return LayeredProposalResult(
        mode=mode,
        scanned_windows=len(context_rows),
        raw_candidates_count=len(raw_rows),
        cache_manifest=manifest,
        context_path=paths.context_path,
        raw_candidates_path=paths.raw_candidates_path,
        filter_results_path=paths.filter_results_path,
        execution_results_path=paths.execution_results_path,
        funnel_summary_path=paths.funnel_summary_path,
        gate_ablation_path=paths.gate_ablation_path,
        diagnostics_report_path=paths.diagnostics_report_path,
        manifest_path=paths.manifest_path,
        summary_rows=_run_summary_rows(
            mode=mode,
            raw_rows=raw_rows,
            funnel_rows=funnel_rows,
            gate_rows=gate_rows,
            execution_rows=execution_rows,
        ),
    )


def _write_stage_progress(progress_path: str | Path | None, **payload: object) -> None:
    if progress_path is None:
        return
    path = Path(progress_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if path.exists():
        try:
            current = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            current = {}
    stages = list(current.get("stages", [])) if isinstance(current.get("stages"), list) else []
    row = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    stages.append(row)
    current.update(row)
    current["stages"] = stages
    write_json(path, current)


def _ensure_candidates(
    *,
    repository,
    preset: BacktestPresetConfig,
    paths,
    max_entry_windows: int | None,
    force_context: bool,
    force_candidates: bool,
    setup_filter: Sequence[str] | None,
    progress_path: Path | None,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...], tuple[dict[str, object], ...], str, str]:
    if paths.context_path.exists() and not force_context:
        context_rows = read_jsonl(paths.context_path)
        context_status = "reused"
    else:
        context_rows, coverage_rows = _build_context_rows(
            repository,
            preset=preset,
            max_entry_windows=max_entry_windows,
            setup_filter=setup_filter,
        )
        write_jsonl(paths.context_path, context_rows)
        context_status = "forced_rebuild" if force_context else "created"
    _write_stage_progress(
        progress_path,
        stage="context_complete",
        context_rows=len(context_rows),
        raw_candidates=None,
    )
    if "coverage_rows" not in locals():
        coverage_rows = _coverage_from_context(context_rows)

    raw_cache_reusable = _raw_cache_reusable(
        preset=preset,
        paths=paths,
        setup_filter=setup_filter,
    )
    if paths.raw_candidates_path.exists() and not force_candidates and not force_context and raw_cache_reusable:
        raw_rows = read_jsonl(paths.raw_candidates_path)
        raw_status = "reused"
    else:
        raw_rows = _build_raw_candidates(
            repository,
            preset=preset,
            context_rows=context_rows,
            setup_filter=setup_filter,
        )
        write_jsonl(paths.raw_candidates_path, raw_rows)
        raw_status = "forced_rebuild" if force_candidates or force_context else "created"
    _write_stage_progress(
        progress_path,
        stage="raw_candidates_complete",
        context_rows=len(context_rows),
        raw_candidates=len(raw_rows),
    )
    return context_rows, raw_rows, tuple(coverage_rows), context_status, raw_status


def _build_context_rows(
    repository,
    *,
    preset: BacktestPresetConfig,
    max_entry_windows: int | None,
    setup_filter: Sequence[str] | None,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    rows: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []
    fast_context_only = tuple(setup_filter or ()) in {
        ("trend_continuation",),
        ("compression_expansion",),
        ("breakout_pullback",),
    }
    for target in preset.to_scan_config().targets:
        for profile_key in preset.scan.profile_keys:
            profile = get_profile(profile_key)
            candles = {
                profile.entry_timeframe: _load_timeframe(repository, target, profile.entry_timeframe, preset),
                profile.structure_timeframe: _load_timeframe(repository, target, profile.structure_timeframe, preset),
                profile.trend_timeframe: _load_timeframe(repository, target, profile.trend_timeframe, preset),
            }
            candle_timestamps = {
                timeframe: _candle_timestamps(data)
                for timeframe, data in candles.items()
            }
            for timeframe, data in candles.items():
                coverage.append(
                    {
                        "asset": target.canonical_symbol,
                        "inst_id": target.inst_id,
                        "inst_type": target.inst_type,
                        "profile": profile.key,
                        "bar": timeframe_to_okx_bar(timeframe),
                        "count": len(data),
                        "first_ts": int(getattr(data[0], "timestamp_ms")) if data else None,
                        "last_ts": int(getattr(data[-1], "timestamp_ms")) if data else None,
                    }
                )
            entry = candles[profile.entry_timeframe]
            if not all(candles.values()) or len(entry) < 2:
                continue
            start_index = 0
            if max_entry_windows is not None and max_entry_windows > 0:
                start_index = max(0, len(entry) - max_entry_windows - 1)
            for index in range(start_index, max(0, len(entry) - 1)):
                latest = entry[index]
                timestamp_ms = int(getattr(latest, "timestamp_ms"))
                structure = _candles_until_cached(
                    candles[profile.structure_timeframe],
                    candle_timestamps[profile.structure_timeframe],
                    timestamp_ms,
                )
                trend = _candles_until_cached(
                    candles[profile.trend_timeframe],
                    candle_timestamps[profile.trend_timeframe],
                    timestamp_ms,
                )
                if not structure or not trend:
                    continue
                regime = None if fast_context_only else build_market_regime(trend)
                volume = (
                    {}
                    if fast_context_only
                    else confirm_volume_price(
                        entry[: index + 1],
                        "long",
                        context_features=_context_features(target, profile.key, preset),
                    ).evidence
                )
                rows.append(
                    {
                        "asset": target.canonical_symbol.split("/", 1)[0].upper(),
                        "symbol": target.canonical_symbol,
                        "inst_id": target.inst_id,
                        "inst_type": target.inst_type,
                        "venue": target.venue,
                        "profile": profile.key,
                        "entry_timeframe": profile.entry_timeframe,
                        "structure_timeframe": profile.structure_timeframe,
                        "trend_timeframe": profile.trend_timeframe,
                        "timestamp_ms": timestamp_ms,
                        "open": float(getattr(latest, "open")),
                        "high": float(getattr(latest, "high")),
                        "low": float(getattr(latest, "low")),
                        "close": float(getattr(latest, "close")),
                        "volume": float(getattr(latest, "volume")),
                        "confirmed": bool(getattr(latest, "is_confirmed", False)),
                        "atr": None if regime is None else regime.atr,
                        "rolling_rvol": volume.get("rolling_rvol"),
                        "tod_dow_rvol": volume.get("tod_dow_rvol"),
                        "trend_state": "unknown" if regime is None else regime.status,
                        "trend_direction": "" if regime is None or regime.direction is None else regime.direction,
                        "session": "utc",
                        "utc_hour": _utc_hour(timestamp_ms),
                        "day_of_week": _day_of_week(timestamp_ms),
                        "funding_rate": preset.costs.funding,
                        "spread_estimate": preset.costs.spread_slippage_rate,
                        "volatility_regime": "unknown" if regime is None else regime.status,
                        "volume_bucket_sample_count": volume.get("volume_bucket_sample_count", 0),
                        "used_fallback_volume_baseline": bool(volume.get("used_fallback_volume_baseline", False)),
                    }
                )
    return tuple(rows), tuple(coverage)


def _build_raw_candidates(
    repository,
    *,
    preset: BacktestPresetConfig,
    context_rows: Sequence[Mapping[str, object]],
    setup_filter: Sequence[str] | None,
) -> tuple[dict[str, object], ...]:
    by_id: dict[str, dict[str, object]] = {}
    candle_cache: dict[tuple[str, str, str, str, str], tuple[object, ...]] = {}
    timestamp_cache: dict[tuple[str, str, str, str, str], tuple[int, ...]] = {}
    regime_cache: dict[tuple[str, str, str, int], object | None] = {}
    trend_only = tuple(setup_filter or ()) in {("trend_continuation",), ("compression_expansion",), ("breakout_pullback",)}
    for row in context_rows:
        target = BacktestScanTarget(
            canonical_symbol=str(row["symbol"]),
            inst_id=str(row["inst_id"]),
            venue=str(row["venue"]),
            inst_type=str(row["inst_type"]),
        )
        profile = get_profile(str(row["profile"]))
        timestamp_ms = int(row["timestamp_ms"])
        def cached_timeframe(timeframe: str) -> tuple[object, ...]:
            key = (target.inst_id, target.venue, target.inst_type, timeframe, str(row["symbol"]))
            if key not in candle_cache:
                candle_cache[key] = _load_timeframe(repository, target, timeframe, preset)
                timestamp_cache[key] = _candle_timestamps(candle_cache[key])
            return candle_cache[key]

        def cached_until(timeframe: str, max_bars: int | None = None) -> tuple[object, ...]:
            key = (target.inst_id, target.venue, target.inst_type, timeframe, str(row["symbol"]))
            candles_for_timeframe = cached_timeframe(timeframe)
            return _candles_until_cached(candles_for_timeframe, timestamp_cache[key], timestamp_ms, max_bars=max_bars)

        candles = {
            profile.entry_timeframe: cached_until(profile.entry_timeframe, 96 if trend_only else None),
            profile.structure_timeframe: cached_until(profile.structure_timeframe, 512 if trend_only else None),
            profile.trend_timeframe: cached_until(profile.trend_timeframe, 260 if trend_only else None),
        }
        features = _context_features(target, profile.key, preset)
        trend_candles = candles[profile.trend_timeframe]
        trend_ts = int(getattr(trend_candles[-1], "timestamp_ms")) if trend_candles else 0
        regime_key = (target.inst_id, target.inst_type, profile.key, trend_ts)
        if regime_key not in regime_cache:
            regime_cache[regime_key] = build_market_regime(trend_candles)
        features["market_regime"] = regime_cache[regime_key]
        for candidate in generate_raw_candidates(
            symbol=target.canonical_symbol,
            venue=target.venue,
            inst_id=target.inst_id,
            inst_type=target.inst_type,
            profile=profile.key,
            structure_candles=candles[profile.structure_timeframe],
            entry_candles=candles[profile.entry_timeframe],
            trend_candles=candles[profile.trend_timeframe],
            context_features=features,
            setup_filter=setup_filter,
        ):
            by_id.setdefault(candidate.candidate_id, candidate.to_row())
    return tuple(by_id[key] for key in sorted(by_id))


def _ensure_filter_results(*, preset: BacktestPresetConfig, paths, raw_rows: Sequence[Mapping[str, object]], force_filter: bool) -> tuple[tuple[dict[str, object], ...], str]:
    if paths.filter_results_path.exists() and not force_filter:
        return read_jsonl(paths.filter_results_path), "reused"
    rows = tuple(_filter_candidate(row, preset) for row in raw_rows)
    write_jsonl(paths.filter_results_path, rows)
    return rows, "forced_rebuild" if force_filter else "created"


def _filter_candidate(candidate: Mapping[str, object], preset: BacktestPresetConfig) -> dict[str, object]:
    params = _setup_params(candidate, preset)
    entry = float(candidate["entry_reference_price"])
    stop = float(candidate["stop_price"])
    target = float(candidate["target_price"])
    atr = float(candidate["atr_value"])
    stop_distance = abs(entry - stop)
    stop_atr = None if atr <= 0 else stop_distance / atr
    target_r = 0.0 if stop_distance <= 0 else abs(target - entry) / stop_distance
    reclaim_rvol = _as_float(candidate.get("reclaim_rvol"))
    reclaim_quality = _reclaim_quality(reclaim_rvol)
    reject_stage = ""
    reject_reason = ""

    if candidate["setup"] == "trend_continuation" and (
        candidate.get("trend_state") != "TREND" or candidate.get("trend_direction") not in {"", candidate.get("direction")}
    ):
        reject_stage, reject_reason = "direction_and_trend", "trend_gate_failed"
    if not reject_reason and candidate["setup"] == "liquidity_reversal":
        if float(candidate.get("sweep_atr_multiple") or 0.0) > float(params.get("sweep_max_atr_multiple", 1.5)):
            reject_stage, reject_reason = "reclaim_and_choch", "sweep_too_far"
        elif float(candidate.get("wick_ratio") or 0.0) < float(params.get("sweep_wick_ratio_min", 0.25)):
            reject_stage, reject_reason = "reclaim_and_choch", "wick_ratio_too_low"
    rvol = _candidate_rvol(candidate)
    required_rvol = float(params.get("countertrend_sweep_rvol_min" if candidate.get("countertrend") else "sweep_rvol_min", 1.5))
    if not reject_reason and candidate["setup"] == "liquidity_reversal" and (rvol is None or rvol < required_rvol):
        reject_stage, reject_reason = "volume_filter", "low_sweep_rvol"
    if not reject_reason and candidate["setup"] == "liquidity_reversal":
        if int(candidate.get("reclaim_bars") or 999) > int(params.get("reclaim_max_bars", 5)):
            reject_stage, reject_reason = "reclaim_and_choch", "reclaim_timeout"
        elif reclaim_quality == "high_reclaim_rvol":
            reject_stage, reject_reason = "reclaim_and_choch", "high_reclaim_rvol"
        elif _choch_required(candidate, params) and not bool(candidate.get("choch_detected")):
            reject_stage, reject_reason = "reclaim_and_choch", "choch_required_missing"
    if not reject_reason and candidate["setup"] == "liquidity_reversal" and target_r < preset.risk.min_liquidity_reversal_target_r:
        reject_stage, reject_reason = "risk_filter", "target_r_too_low"
    if not reject_reason and candidate["setup"] == "breakout_pullback":
        structural_quality = str(candidate.get("structural_stop_quality") or "")
        if structural_quality in {"structural_stop_too_near", "structural_stop_too_wide"}:
            reject_stage, reject_reason = "structural_tradeability_filter", structural_quality
        elif candidate.get("stop_is_structural") is False:
            reject_stage, reject_reason = "structural_tradeability_filter", "non_structural_stop"

    intent = OrderIntent(
        strategy_name=preset.strategy.name,
        strategy_version=preset.strategy.version,
        setup_type=str(candidate["setup"]),
        symbol=str(candidate["symbol"]),
        venue=str(candidate["venue"]),
        direction="LONG" if candidate["direction"] == "long" else "SHORT",
        entry_price=entry,
        stop_loss=stop,
        target_price=target,
        point_value=preset.execution.point_value,
    )
    estimated_cost_r = _estimated_cost_r(intent, preset)
    target_space = abs(target - entry)
    target_space_atr = None if atr <= 0 else target_space / atr
    cost_adjusted_rr = target_r - estimated_cost_r
    cost_per_r = estimated_cost_r
    if not reject_reason and candidate["setup"] == "breakout_pullback":
        if target_space_atr is not None and target_space_atr < float(params.get("bp_min_target_space_atr", 0.0)):
            reject_stage, reject_reason = "cost_adjusted_quality_filter", "target_space_insufficient"
        elif cost_adjusted_rr < float(params.get("bp_min_cost_adjusted_rr", 0.0)):
            reject_stage, reject_reason = "cost_adjusted_quality_filter", "cost_adjusted_RR_too_low"
        elif cost_per_r > float(params.get("bp_max_cost_per_r", 999.0)):
            reject_stage, reject_reason = "cost_adjusted_quality_filter", "cost_per_R_too_high"
    risk_decision = RiskEngine(preset.to_risk_parameters()).evaluate(
        intent,
        AccountState(
            equity=preset.execution.initial_equity,
            high_water_mark=preset.execution.initial_equity,
            current_drawdown_pct=0.0,
            daily_pnl=0.0,
            open_positions=(),
        ),
        atr=atr,
        cost_estimate=CostEstimate(),
    )
    if not reject_reason and risk_decision.approved_order is None:
        reject_stage = "risk_filter"
        reject_reason = _risk_reason(risk_decision.reason_codes)

    approved_order = risk_decision.approved_order
    contract = None
    if approved_order is not None:
        contract = estimate_contract_risk(
            intent=intent,
            quantity=approved_order.quantity,
            risk_amount=approved_order.risk_amount,
            preset=preset,
        )
        if not reject_reason and contract.reject_reason:
            reject_stage, reject_reason = "contract_risk_filter", contract.reject_reason

    shadow_approved_5 = _shadow_allowed(stop_atr, preset.risk.min_stop_atr_multiple, 5.0)
    shadow_approved_8 = _shadow_allowed(stop_atr, preset.risk.min_stop_atr_multiple, 8.0)
    if not reject_reason and candidate["setup"] == "compression_expansion":
        if target_space_atr is not None and target_space_atr < float(params.get("compression_min_target_space_atr", 0.0)):
            reject_stage, reject_reason = "cost_adjusted_quality_filter", "target_space_atr_too_low"
        elif cost_adjusted_rr < float(params.get("compression_min_cost_adjusted_rr", 0.0)):
            reject_stage, reject_reason = "cost_adjusted_quality_filter", "cost_adjusted_rr_too_low"
        elif cost_per_r > float(params.get("compression_max_cost_per_r", 999.0)):
            reject_stage, reject_reason = "cost_adjusted_quality_filter", "cost_per_r_too_high"
    formal_approved = risk_decision.approved_order is not None and not reject_reason
    base = dict(candidate)
    base.update(
        {
            "approved": formal_approved,
            "formal_approved": formal_approved,
            "shadow_approved": (not formal_approved) and (shadow_approved_5 or shadow_approved_8),
            "shadow_approved_5": shadow_approved_5,
            "shadow_approved_8": shadow_approved_8,
            "reject_stage": "" if formal_approved else reject_stage or "approved_filter",
            "reject_reason": "" if formal_approved else reject_reason or "filtered_without_reason",
            "entry_price": entry,
            "stop_price": stop,
            "stop_distance_abs": stop_distance,
            "stop_distance_pct": stop_distance / entry if entry > 0 else 0.0,
            "stop_atr_multiple": stop_atr,
            "target_r": target_r,
            "reclaim_quality": reclaim_quality,
            "reclaim_rvol_config_max": float(params.get("reclaim_rvol_max", 0.0)),
            "reclaim_rvol_ideal_max": 1.2,
            "reclaim_rvol_acceptable_max": 1.6,
            "estimated_cost_r": estimated_cost_r,
            "target_space": candidate.get("target_space", target_space),
            "target_space_atr": candidate.get("target_space_atr", target_space_atr),
            "gross_RR": candidate.get("gross_RR", target_r),
            "cost_adjusted_RR": cost_adjusted_rr,
            "cost_per_R": cost_per_r,
            "estimated_funding_r": 0.0 if preset.costs.funding == 0 else abs(preset.costs.funding) / max(stop_distance, 1e-12),
            "min_stop_atr_multiple": preset.risk.min_stop_atr_multiple,
            "max_stop_atr_multiple": preset.risk.max_stop_atr_multiple,
            "invalidation_mode": preset.execution.invalidation_mode,
            "invalidation_mode_config": candidate.get("invalidation_mode_config", preset.execution.invalidation_mode),
            "invalidation_mode_effective": candidate.get("invalidation_mode_effective", candidate.get("invalidation_mode_config", preset.execution.invalidation_mode)),
            "invalidation_buffer_atr": preset.execution.invalidation_buffer_atr,
            "stop_formula_used": candidate.get("stop_formula_used", ""),
            "stop_formula_fallback_reason": candidate.get("stop_formula_fallback_reason", ""),
            "sweep_extreme_price_used": candidate.get("sweep_extreme_price_used", candidate.get("sweep_extreme_price", candidate.get("sweep_extreme", ""))),
            "atr_used_for_stop": candidate.get("atr_used_for_stop", atr),
            "atr_used_for_stop_timeframe": candidate.get("atr_used_for_stop_timeframe", ""),
            "stop_atr_multiple_entry_tf": stop_atr,
            "risk_reason_codes": risk_decision.reason_codes,
        }
    )
    if contract is not None:
        contract_payload = asdict(contract)
        contract_payload["contract_risk_reject_reason"] = contract_payload.pop("reject_reason")
        base.update(contract_payload)
        base["position_size"] = approved_order.quantity if approved_order is not None else 0.0
        base["portfolio_heat_after_entry"] = contract.portfolio_heat
    else:
        shadow_quantity = 0.0 if stop_distance <= 0 else risk_decision.risk_amount / (stop_distance * preset.execution.point_value)
        shadow_notional = abs(shadow_quantity * entry * preset.execution.point_value)
        shadow_margin = shadow_notional / max(preset.risk.max_total_gross_leverage, 1e-12)
        shadow_heat = 0.0 if preset.execution.initial_equity <= 0 else risk_decision.risk_amount / preset.execution.initial_equity
        base.update(
            {
                "fee": 0.0,
                "spread": 0.0,
                "slippage": 0.0,
                "funding_rate": preset.costs.funding,
                "funding_paid_or_received": 0.0,
                "leverage": 0.0 if preset.execution.initial_equity <= 0 else shadow_notional / preset.execution.initial_equity,
                "margin_required": shadow_margin,
                "notional": shadow_notional,
                "position_size": shadow_quantity,
                "liquidation_price": 0.0,
                "liquidation_distance_pct": 0.0,
                "maintenance_margin_ratio": 0.005,
                "gross_exposure": shadow_notional,
                "net_exposure": shadow_notional if intent.direction == "LONG" else -shadow_notional,
                "portfolio_heat": shadow_heat,
                "portfolio_heat_after_entry": shadow_heat,
                "contract_risk_reject_reason": "",
            }
        )
    return base


def _ensure_execution_results(
    *,
    repository,
    preset: BacktestPresetConfig,
    paths,
    filter_rows: Sequence[Mapping[str, object]],
    cost_tiers: Sequence[str],
    force_execution: bool,
) -> tuple[tuple[dict[str, object], ...], str]:
    if paths.execution_results_path.exists() and not force_execution:
        return read_jsonl(paths.execution_results_path), "reused"
    approved = tuple(row for row in filter_rows if row.get("formal_approved") or row.get("shadow_approved"))
    rows: list[dict[str, object]] = []
    candle_cache: dict[tuple[str, str, str, str, str], tuple[object, ...]] = {}
    for tier_name in cost_tiers:
        tier_preset = _tier_preset(preset, tier_name)
        engine = BacktestExecutionEngine(
            risk_engine=RiskEngine(tier_preset.to_risk_parameters()),
            config=tier_preset.to_execution_config(),
        )
        for row in approved:
            if not row.get("formal_approved"):
                continue
            signal_input = _input_from_filter_row(repository, row, tier_preset, candle_cache=candle_cache)
            if signal_input is None:
                continue
            result = engine.run((signal_input,))
            for fill in result.fills:
                rows.append(_execution_row(row, fill, tier_name))
    write_jsonl(paths.execution_results_path, rows)
    return tuple(rows), "forced_rebuild" if force_execution else "created"


def _input_from_filter_row(
    repository,
    row: Mapping[str, object],
    preset: BacktestPresetConfig,
    *,
    candle_cache: dict[tuple[str, str, str, str, str], tuple[object, ...]] | None = None,
) -> BacktestSignalInput | None:
    profile = get_profile(str(row["profile"]))
    target = BacktestScanTarget(
        canonical_symbol=str(row["symbol"]),
        inst_id=str(row["inst_id"]),
        venue=str(row["venue"]),
        inst_type=str(row["inst_type"]),
    )
    cache_key = (target.inst_id, target.venue, target.inst_type, profile.entry_timeframe, str(row["symbol"]))
    if candle_cache is not None and cache_key in candle_cache:
        entry = candle_cache[cache_key]
    else:
        entry = _load_timeframe(repository, target, profile.entry_timeframe, preset)
        if candle_cache is not None:
            candle_cache[cache_key] = entry
    execution_candles = tuple(candle for candle in entry if int(getattr(candle, "timestamp_ms")) > int(row["timestamp_ms"]))[: preset.execution.max_holding_bars]
    if not execution_candles:
        return None
    signal = StrategySignal(
        strategy_name=preset.strategy.name,
        strategy_version=preset.strategy.version,
        setup_type=str(row["setup"]),
        symbol=str(row["symbol"]),
        venue=str(row["venue"]),
        timeframe_group=str(row["profile"]),
        direction=str(row["direction"]),
        entry_zone={"low": float(row["entry_price"]), "high": float(row["entry_price"]), "reference_price": float(row["entry_price"])},
        invalidation_level=float(row["stop_price"]),
        target_hint={"target_price": float(row["target_price"]), "reward_to_risk": float(row["target_r"])},
        trend_evidence={"atr": float(row["atr_value"])},
        price_action_evidence=dict(row),
        volume_price_evidence=dict(row),
        risk_profile={},
        explanation_payload={"strategy_family": _strategy_family_for_setup(str(row["setup"]))},
    )
    return BacktestSignalInput(
        signal=signal,
        execution_candles=execution_candles,
        candidate_id=str(row.get("candidate_id", "")),
        event_id=str(row.get("event_id") or row.get("sweep_event_id") or row.get("candidate_id", "")),
        feature_cutoff_time=_as_int(row.get("feature_cutoff_time") or row.get("signal_timestamp_ms")),
        structure_confirmed_time=_as_int(row.get("structure_confirmed_time") or row.get("structure_timestamp_ms")),
        sweep_time=_as_int(row.get("sweep_time") or row.get("sweep_timestamp_ms")),
        reclaim_time=_as_int(row.get("reclaim_time") or row.get("reclaim_timestamp_ms") or row.get("signal_timestamp_ms")),
        signal_time=_as_int(row.get("signal_time") or row.get("signal_timestamp_ms")),
        bar_confirmed=bool(row.get("bar_confirmed", True)),
        no_lookahead_safe=bool(row.get("no_lookahead_safe", True)),
    )


def _execution_row(candidate: Mapping[str, object], fill, cost_tier: str) -> dict[str, object]:
    return {
        "candidate_id": candidate["candidate_id"],
        "event_id": candidate.get("event_id") or candidate.get("sweep_event_id") or candidate["candidate_id"],
        "trade_id": fill.trade_id,
        "execution_id": fill.execution_id,
        "row_type": "closed_trade",
        "closed_trade": True,
        "eligible_for_performance": True,
        "eligible_for_robustness": True,
        "invalid_for_robustness": False,
        "cost_tier": cost_tier,
        "asset": candidate["asset"],
        "symbol": candidate["symbol"],
        "profile": candidate["profile"],
        "setup": candidate["setup"],
        "direction": candidate["direction"],
        "formal_approved": candidate["formal_approved"],
        "entry_time": fill.entry_timestamp_ms,
        "exit_time": fill.exit_timestamp_ms,
        "feature_cutoff_time": candidate.get("feature_cutoff_time") or candidate.get("signal_timestamp_ms"),
        "structure_confirmed_time": candidate.get("structure_confirmed_time") or candidate.get("structure_timestamp_ms"),
        "sweep_time": candidate.get("sweep_time") or candidate.get("sweep_timestamp_ms"),
        "reclaim_time": candidate.get("reclaim_time") or candidate.get("reclaim_timestamp_ms") or candidate.get("signal_timestamp_ms"),
        "signal_time": candidate.get("signal_time") or candidate.get("signal_timestamp_ms"),
        "trend_confirmed_time": candidate.get("trend_confirmed_time"),
        "breakout_time": candidate.get("breakout_time"),
        "pullback_confirmed_time": candidate.get("pullback_confirmed_time"),
        "compression_event_id": candidate.get("compression_event_id"),
        "compression_start_time": candidate.get("compression_start_time"),
        "compression_end_time": candidate.get("compression_end_time"),
        "confirmation_time": candidate.get("confirmation_time"),
        "trend_event_id": candidate.get("trend_event_id") or candidate.get("event_id") or candidate.get("candidate_id"),
        "breakout_pullback_event_id": candidate.get("breakout_pullback_event_id")
        or candidate.get("event_id")
        or candidate.get("candidate_id"),
        "core_engine_version": candidate.get("core_engine_version"),
        "level_id": candidate.get("level_id"),
        "breakout_event_id": candidate.get("breakout_event_id"),
        "lifecycle_event_id": candidate.get("lifecycle_event_id"),
        "zone_confirmed_time": candidate.get("zone_confirmed_time"),
        "breakout_class": candidate.get("breakout_class"),
        "pullback_health_class": candidate.get("pullback_health_class"),
        "relaunch_type": candidate.get("relaunch_type"),
        "relaunch_quality_class": candidate.get("relaunch_quality_class"),
        "target_source": candidate.get("target_source"),
        "target_quality_class": candidate.get("target_quality_class"),
        "structural_stop_quality": candidate.get("structural_stop_quality"),
        "bp_subtype": candidate.get("bp_subtype"),
        "acceptance_end_time": candidate.get("acceptance_end_time"),
        "pullback_start_time": candidate.get("pullback_start_time"),
        "pullback_end_time": candidate.get("pullback_end_time"),
        "relaunch_time": candidate.get("relaunch_time"),
        "bar_confirmed": candidate.get("bar_confirmed", True),
        "no_lookahead_safe": candidate.get("no_lookahead_safe", True),
        "net_pnl": fill.net_pnl,
        "gross_pnl": fill.gross_pnl,
        "net_R": fill.r_multiple,
        "r_multiple": fill.r_multiple,
        "exit_reason": fill.exit_reason,
        "holding_bars": fill.holding_bars,
        "mae_r": fill.mae_r,
        "mfe_r": fill.mfe_r,
        "mae_R": fill.mae_r,
        "mfe_R": fill.mfe_r,
        "bars_to_mae": fill.bars_to_mae,
        "bars_to_mfe": fill.bars_to_mfe,
        "reached_1R": fill.reached_1r,
        "reached_1_5R": fill.reached_1_5r,
        "reached_2R": fill.reached_2r,
        "moved_to_breakeven": fill.moved_to_breakeven,
        "breakeven_hit": fill.breakeven_hit,
        "partial_take_profit_hit": fill.partial_take_profit_hit,
        "same_bar_ambiguous": fill.same_bar_ambiguous,
        "same_bar_resolution": fill.same_bar_resolution,
        "forced_pessimistic_exit": fill.forced_pessimistic_exit,
        "fee": fill.cost_estimate.fees,
        "spread": fill.cost_estimate.spread,
        "slippage": fill.cost_estimate.expected_slippage,
        "funding_paid_or_received": fill.cost_estimate.funding,
        "fee_cost": fill.cost_estimate.fees,
        "slippage_cost": fill.cost_estimate.expected_slippage,
        "funding_cost": fill.cost_estimate.funding,
        "portfolio_heat": candidate.get("portfolio_heat", 0.0),
        "margin_required": candidate.get("margin_required", 0.0),
        "notional_to_equity_pct": candidate.get("notional_to_equity_pct", candidate.get("notional", 0.0)),
        "utc_hour": _utc_hour(int(fill.entry_timestamp_ms or candidate.get("signal_timestamp_ms") or 0)),
        "trend_state": candidate.get("trend_state", ""),
        "trend_aligned": candidate.get("trend_direction") in {"", candidate.get("direction")},
        "stop_atr": candidate.get("stop_atr_multiple"),
        "sweep_rvol": candidate.get("reclaim_rvol") or candidate.get("rolling_rvol") or candidate.get("tod_dow_rvol"),
        "time_cut_exit": fill.exit_reason == "time_cut_exit",
        "loss_time_cut": fill.exit_reason == "time_cut_exit" and fill.r_multiple < 0,
        "liquidation_event": False,
        "margin_call_event": False,
    }


def _funnel_rows(raw_rows: Sequence[Mapping[str, object]], filter_rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    grouped_raw = Counter(_group_key(row) for row in raw_rows)
    grouped_filters: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in filter_rows:
        grouped_filters[_group_key(row)].append(row)
    rows: list[dict[str, object]] = []
    for key in sorted(set(grouped_raw) | set(grouped_filters)):
        group = grouped_filters.get(key, [])
        reasons = Counter(str(row.get("reject_reason", "")) for row in group if row.get("reject_reason"))
        stages = Counter(str(row.get("reject_stage", "")) for row in group if row.get("reject_stage"))
        reclaim_quality = Counter(str(row.get("reclaim_quality", "")) for row in group if row.get("reclaim_quality"))
        rows.append(
            {
                "asset": key[0],
                "profile": key[1],
                "setup": key[2],
                "direction": key[3],
                "scanned_windows": 0,
                "raw_price_candidates": grouped_raw[key],
                "direction_reject_count": stages["direction_and_trend"],
                "trend_reject_count": reasons["trend_gate_failed"],
                "volume_reject_count": stages["volume_filter"],
                "structure_reject_count": reasons["sweep_too_far"] + reasons["wick_ratio_too_low"],
                "choch_reject_count": reasons["choch_required_missing"],
                "reclaim_reject_count": reasons["reclaim_timeout"] + reasons["high_reclaim_rvol"],
                "risk_reject_count": stages["risk_filter"],
                "target_r_reject_count": reasons["target_r_too_low"],
                "cost_reject_count": reasons["cost_after_r_too_low"],
                "funding_reject_count": reasons["funding_cost_too_high"],
                "margin_reject_count": reasons["margin_required_too_high"],
                "liquidation_risk_reject_count": reasons["liquidation_distance_too_close"],
                "portfolio_heat_reject_count": reasons["portfolio_heat_exceeded"],
                "approved_count": sum(1 for row in group if row.get("formal_approved")),
                "closed_trades_count": 0,
                "ideal_reclaim_count": reclaim_quality["ideal_reclaim"],
                "acceptable_reclaim_count": reclaim_quality["acceptable_reclaim"],
                "high_reclaim_rvol_count": reclaim_quality["high_reclaim_rvol"],
                "top_reject_reason": reasons.most_common(1)[0][0] if reasons else "",
            }
        )
    return tuple(rows)


def _gate_ablation_rows(raw_rows: Sequence[Mapping[str, object]], filter_rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    current = len(raw_rows)
    rows = [{"stage": "raw_structure_only", "input_count": len(raw_rows), "passed_count": len(raw_rows), "rejected_count": 0, "top_reject_reason": ""}]
    stage_specs = (
        ("+direction_and_trend", "direction_and_trend"),
        ("+volume_filter", "volume_filter"),
        ("+reclaim_and_choch", "reclaim_and_choch"),
        ("+risk_filter", "risk_filter"),
        ("+contract_risk_filter", "contract_risk_filter"),
        ("+execution_and_cost", "position_aware_filter"),
    )
    for label, stage in stage_specs:
        rejected = [row for row in filter_rows if row.get("reject_stage") == stage]
        reasons = Counter(str(row.get("reject_reason", "")) for row in rejected if row.get("reject_reason"))
        rejected_count = len(rejected)
        passed = max(0, current - rejected_count)
        rows.append(
            {
                "stage": label,
                "input_count": current,
                "passed_count": passed,
                "rejected_count": rejected_count,
                "top_reject_reason": reasons.most_common(1)[0][0] if reasons else "",
            }
        )
        current = passed
    return tuple(rows)


def _run_summary_rows(
    *,
    mode: str,
    raw_rows: Sequence[Mapping[str, object]],
    funnel_rows: Sequence[Mapping[str, object]],
    gate_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    if mode == "candidate_only":
        return _candidate_summary_rows(raw_rows)
    if mode == "gate_ablation":
        return tuple(dict(row) for row in gate_rows)
    if mode == "full_backtest" and execution_rows:
        return _execution_summary_rows(execution_rows)
    if funnel_rows:
        return tuple(dict(row) for row in funnel_rows)
    return _candidate_summary_rows(raw_rows)


def _execution_summary_rows(execution_rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[str, str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in execution_rows:
        grouped[
            (
                str(row.get("asset", "")),
                str(row.get("profile", "")),
                str(row.get("setup", "")),
                str(row.get("direction", "")),
                str(row.get("cost_tier", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for key, group in sorted(grouped.items()):
        r_values = [float(row.get("r_multiple") or 0.0) for row in group]
        pnl_values = [float(row.get("net_pnl") or 0.0) for row in group]
        wins = [value for value in pnl_values if value > 0]
        losses = [abs(value) for value in pnl_values if value < 0]
        rows.append(
            {
                "asset": key[0],
                "profile": key[1],
                "setup": key[2],
                "direction": key[3],
                "cost_tier": key[4],
                "closed_trades": len(group),
                "net_pnl": sum(pnl_values),
                "expectancy_R": sum(r_values) / len(r_values) if r_values else 0.0,
                "median_R": median(r_values) if r_values else 0.0,
                "win_rate": len(wins) / len(group) if group else 0.0,
                "profit_factor": (sum(wins) / sum(losses)) if losses else 0.0,
            }
        )
    return tuple(rows)


def _manifest(
    *,
    preset: BacktestPresetConfig,
    coverage_rows: Sequence[Mapping[str, object]],
    context_status: str,
    raw_status: str,
    filter_status: str,
    execution_status: str,
    context_rows: Sequence[Mapping[str, object]],
    raw_rows: Sequence[Mapping[str, object]],
    filter_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
    max_entry_windows: int | None,
    cost_tiers: Sequence[str],
    setup_filter: Sequence[str] | None,
    elapsed_seconds: float,
) -> dict[str, object]:
    data_hash = data_hash_from_counts(coverage_rows)
    context_hash = stable_hash({"data_hash": data_hash, "context_config_hash": context_config_hash(preset)})
    raw_hash = stable_hash(
        {
            "context_cache_hash": context_hash,
            "candidate_generation_config_hash": candidate_generation_config_hash(preset, setup_filter),
        }
    )
    filter_hash = stable_hash({"raw_candidate_cache_hash": raw_hash, "filter_config_hash": filter_config_hash(preset)})
    execution_hash = stable_hash({"filter_result_hash": filter_hash, "execution_config_hash": execution_config_hash(preset, cost_tiers)})
    return {
        "schema_version": 1,
        "data_hash": data_hash,
        "context_cache_hash": context_hash,
        "raw_candidate_cache_hash": raw_hash,
        "candidate_generation_config_hash": candidate_generation_config_hash(preset, setup_filter),
        "filter_result_hash": filter_hash,
        "execution_result_hash": execution_hash,
        "context_cache_status": context_status,
        "raw_candidate_cache_status": raw_status,
        "filter_cache_status": filter_status,
        "execution_cache_status": execution_status,
        "max_entry_windows": max_entry_windows,
        "cost_tiers": tuple(cost_tiers),
        "setup_filter": tuple(setup_filter or ()),
        "raw_history_limits": _raw_history_limits(setup_filter),
        "context_rows": len(context_rows),
        "raw_candidates": len(raw_rows),
        "filter_rows": len(filter_rows),
        "execution_rows": len(execution_rows),
        "elapsed_seconds": elapsed_seconds,
        "reuse_rules": {
            "filter_threshold_change": "reuse context and raw_candidates; rerun filter_replay",
            "atr_swing_rvol_trend_choch_change": "rebuild context and raw_candidates",
            "execution_cost_or_exit_change": "reuse filter when filter config unchanged; rerun execution",
        },
    }


def _load_timeframe(repository, target: BacktestScanTarget, timeframe: str, preset: BacktestPresetConfig) -> tuple[object, ...]:
    bar = timeframe_to_okx_bar(timeframe)
    if hasattr(repository, "load_range"):
        return tuple(
            repository.load_range(
                target.inst_id,
                bar,
                0 if preset.scan.start_ms is None else preset.scan.start_ms,
                9_223_372_036_854_775_807 if preset.scan.end_ms is None else preset.scan.end_ms,
                venue=target.venue,
                inst_type=target.inst_type,
                confirmed_only=True,
            )
        )
    try:
        candles = repository.list_candles(target.inst_id, bar, venue=target.venue, inst_type=target.inst_type)
    except TypeError:
        candles = repository.list_candles(target.inst_id, bar)
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _raw_history_limits(setup_filter: Sequence[str] | None) -> dict[str, int] | None:
    if tuple(setup_filter or ()) not in {("trend_continuation",), ("compression_expansion",), ("breakout_pullback",)}:
        return None
    return {
        "entry": 96,
        "structure": 512,
        "trend": 260,
    }


def _raw_cache_reusable(*, preset: BacktestPresetConfig, paths, setup_filter: Sequence[str] | None) -> bool:
    if not paths.manifest_path.exists():
        return setup_filter is None
    try:
        manifest = read_json(paths.manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    expected = tuple(setup_filter or ())
    previous = tuple(manifest.get("setup_filter") or ())
    if previous != expected:
        return False
    return bool(manifest.get("raw_candidate_cache_hash")) and manifest.get(
        "candidate_generation_config_hash"
    ) == candidate_generation_config_hash(preset, setup_filter)


def _strategy_family_for_setup(setup: str) -> str:
    if setup == "liquidity_reversal":
        return "liquidity_sweep_reclaim"
    if setup == "compression_expansion":
        return "compression_expansion_breakout"
    if setup == "breakout_pullback":
        return "breakout_pullback_continuation"
    return "breakout_pullback_continuation"


def _candles_until(candles: Sequence[object], timestamp_ms: int) -> tuple[object, ...]:
    return tuple(candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms)


def _candles_until_cached(
    candles: Sequence[object],
    timestamps: Sequence[int],
    timestamp_ms: int,
    *,
    max_bars: int | None = None,
) -> tuple[object, ...]:
    end = bisect_right(timestamps, timestamp_ms)
    if max_bars is not None and max_bars > 0:
        return tuple(candles[max(0, end - max_bars) : end])
    return tuple(candles[:end])


def _candle_timestamps(candles: Sequence[object]) -> tuple[int, ...]:
    return tuple(int(getattr(candle, "timestamp_ms")) for candle in candles)


def _context_features(target: BacktestScanTarget, profile_key: str, preset: BacktestPresetConfig) -> dict[str, object]:
    profile = get_profile(profile_key)
    strategy_parameters = dict(preset.strategy.parameters)
    strategy_parameters["invalidation_mode"] = preset.execution.invalidation_mode
    strategy_parameters["invalidation_buffer_atr"] = preset.execution.invalidation_buffer_atr
    return {
        "asset": target.canonical_symbol.split("/", 1)[0].upper(),
        "timeframe_group": profile.key,
        "entry_timeframe": profile.entry_timeframe,
        "structure_timeframe": profile.structure_timeframe,
        "trend_timeframe": profile.trend_timeframe,
        "strategy_parameters": strategy_parameters,
        "volume": preset.strategy.volume,
    }


def _setup_params(candidate: Mapping[str, object], preset: BacktestPresetConfig) -> Mapping[str, object]:
    raw = preset.strategy.parameters.get(str(candidate["setup"]), {})
    if isinstance(raw, Mapping) and "assets" in raw:
        assets = raw.get("assets")
        asset = str(candidate.get("asset", "")).upper()
        if isinstance(assets, Mapping) and isinstance(assets.get(asset), Mapping):
            return assets[asset]
    return raw if isinstance(raw, Mapping) else {}


def _choch_required(candidate: Mapping[str, object], params: Mapping[str, object]) -> bool:
    if bool(candidate.get("countertrend")) and bool(params.get("require_choch_for_countertrend", False)):
        return True
    if str(candidate.get("asset", "")).upper() == "ETH" and bool(params.get("require_choch_for_eth_reversal", False)):
        return True
    return False


def _candidate_rvol(candidate: Mapping[str, object]) -> float | None:
    return _as_float(candidate.get("tod_dow_rvol")) or _as_float(candidate.get("rolling_rvol"))


def _estimated_cost_r(intent: OrderIntent, preset: BacktestPresetConfig) -> float:
    risk_amount = preset.execution.initial_equity * preset.risk.risk_pct
    if risk_amount <= 0 or intent.stop_distance <= 0:
        return 0.0
    quantity = risk_amount / (intent.stop_distance * intent.point_value)
    point_quantity = quantity * intent.point_value
    exit_price = intent.target_price or intent.entry_price
    cost = (
        (abs(intent.entry_price * point_quantity) + abs(exit_price * point_quantity)) * preset.costs.fee_rate
        + abs(preset.costs.spread * point_quantity)
        + abs(preset.costs.slippage * point_quantity * 2.0)
        + abs(preset.costs.funding * point_quantity)
    )
    return cost / risk_amount


def _risk_reason(reason_codes: Sequence[str]) -> str:
    mapping = {
        "target_reward_below_minimum": "target_r_too_low",
        "notional_cap_exceeded": "margin_required_too_high",
        "total_gross_leverage_exceeded": "margin_required_too_high",
    }
    if not reason_codes:
        return "risk_rejected"
    return mapping.get(reason_codes[0], reason_codes[0])


def _shadow_allowed(stop_atr: float | None, min_stop: float, max_stop: float) -> bool:
    return stop_atr is not None and min_stop <= stop_atr <= max_stop


def _tier_preset(preset: BacktestPresetConfig, tier_name: str) -> BacktestPresetConfig:
    tier = next((item for item in preset.costs.cost_model_tiers if item.name == tier_name), None)
    if tier is None:
        return preset
    return replace(
        preset,
        costs=replace(
            preset.costs,
            fee_rate=max(preset.costs.fee_rate, tier.fee_rate),
            spread_slippage_rate=tier.spread_slippage_rate,
        ),
    )


def _coverage_from_context(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    grouped = Counter((row["symbol"], row["inst_id"], row["inst_type"], row["profile"]) for row in rows)
    return tuple({"asset": key[0], "inst_id": key[1], "inst_type": key[2], "profile": key[3], "count": count} for key, count in grouped.items())


def _candidate_summary_rows(raw_rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    counts = Counter(_group_key(row) for row in raw_rows)
    return tuple(
        {
            "asset": key[0],
            "profile": key[1],
            "setup": key[2],
            "direction": key[3],
            "raw_candidates": count,
        }
        for key, count in sorted(counts.items())
    )


def _group_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (str(row.get("asset", "")), str(row.get("profile", "")), str(row.get("setup", "")), str(row.get("direction", "")))


def _reclaim_quality(reclaim_rvol: float | None) -> str:
    if reclaim_rvol is None:
        return "unknown_reclaim"
    if reclaim_rvol <= 1.2:
        return "ideal_reclaim"
    if reclaim_rvol <= 1.6:
        return "acceptable_reclaim"
    return "high_reclaim_rvol"


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _utc_hour(timestamp_ms: int) -> int:
    return (timestamp_ms // 3_600_000) % 24


def _day_of_week(timestamp_ms: int) -> int:
    return (timestamp_ms // 86_400_000 + 3) % 7


_FUNNEL_FIELDS = (
    "asset",
    "profile",
    "setup",
    "direction",
    "scanned_windows",
    "raw_price_candidates",
    "direction_reject_count",
    "trend_reject_count",
    "volume_reject_count",
    "structure_reject_count",
    "choch_reject_count",
    "reclaim_reject_count",
    "risk_reject_count",
    "target_r_reject_count",
    "cost_reject_count",
    "funding_reject_count",
    "margin_reject_count",
    "liquidation_risk_reject_count",
    "portfolio_heat_reject_count",
    "approved_count",
    "closed_trades_count",
    "ideal_reclaim_count",
    "acceptable_reclaim_count",
    "high_reclaim_rvol_count",
    "top_reject_reason",
)


__all__ = ("LAYERED_MODES", "LayeredProposalResult", "run_layered_proposal")
