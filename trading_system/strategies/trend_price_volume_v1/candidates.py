from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, asdict
from hashlib import sha256

from trading_system.strategies.trend_price_volume_v1.features import (
    build_market_regime,
    confirm_volume_price,
    detect_price_action_setup,
    evaluate_breakout_pullback_diagnostics,
    evaluate_compression_expansion_diagnostics,
    strategy_parameters_from_context,
)
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import (
    CORE_ENGINE_VERSION,
    evaluate_breakout_pullback_core_diagnostics,
)


@dataclass(frozen=True)
class RawCandidate:
    candidate_id: str
    timestamp_ms: int
    structure_timestamp_ms: int | None
    sweep_timestamp_ms: int
    reclaim_timestamp_ms: int | None
    signal_timestamp_ms: int
    entry_timestamp_ms: int
    asset: str
    symbol: str
    venue: str
    inst_id: str
    inst_type: str
    profile: str
    setup: str
    direction: str
    long_or_short: str
    structure_level: float
    sweep_extreme: float
    wick_ratio: float
    sweep_atr_multiple: float
    rolling_rvol: float | None
    tod_dow_rvol: float | None
    reclaim_bars: int
    choch_detected: bool
    bos_detected: bool
    trend_state: str
    trend_direction: str
    signal_close_price: float
    entry_reference_price: float
    actual_entry_price_if_simulated: float
    target_price: float
    stop_price: float
    atr_value: float
    reclaim_rvol: float | None
    countertrend: bool
    raw_volume: float | None
    log_volume: float | None
    volume_baseline_mode: str
    volume_bucket_key: str
    volume_bucket_sample_count: int
    used_fallback_volume_baseline: bool
    sweep_extreme_price: float
    sweep_extreme_low: float
    sweep_extreme_high: float
    sweep_extreme_price_used: float
    reclaim_price: float | None
    invalidation_mode_config: str
    invalidation_mode_effective: str
    invalidation_buffer_atr: float
    stop_formula_used: str
    stop_formula_fallback_reason: str
    atr_used_for_stop: float
    atr_used_for_stop_timeframe: str
    bars_structure_to_sweep: int | None
    bars_sweep_to_reclaim: int | None
    bars_reclaim_to_signal: int | None
    bars_signal_to_entry: int | None
    bars_reclaim_to_entry: int | None
    bars_sweep_to_entry: int | None
    candidate_lifecycle_status: str
    candidate_lifecycle_reason: str
    sweep_event_id: str
    candidate_generation_reason: str
    row_type: str = "candidate"
    event_id: str = ""
    feature_cutoff_time: int | None = None
    structure_confirmed_time: int | None = None
    trend_confirmed_time: int | None = None
    breakout_time: int | None = None
    pullback_confirmed_time: int | None = None
    signal_time: int | None = None
    entry_time: int | None = None
    trend_event_id: str = ""
    bar_confirmed: bool = True
    no_lookahead_safe: bool = True
    strategy_family: str = ""
    compression_event_id: str = ""
    compression_start_time: int | None = None
    compression_end_time: int | None = None
    confirmation_time: int | None = None
    compression_high: float | None = None
    compression_low: float | None = None
    compression_midpoint: float | None = None
    compression_box_height: float | None = None
    compression_box_atr: float | None = None
    compression_avg_range_atr: float | None = None
    breakout_displacement_atr: float | None = None
    breakout_displacement_box_ratio: float | None = None
    breakout_close_location: float | None = None
    breakout_body_ratio: float | None = None
    breakout_body_pct: float | None = None
    breakout_rvol: float | None = None
    breakout_score: float | None = None
    breakout_range_vs_ATR: float | None = None
    breakout_range_vs_box_height: float | None = None
    close_outside_box_distance_ATR: float | None = None
    breakout_volume_z: float | None = None
    volume_expansion_vs_compression: float | None = None
    range_expansion_vs_compression: float | None = None
    body_expansion_vs_compression: float | None = None
    acceptance_window_bars: int | None = None
    close_back_inside_box: bool | None = None
    close_back_inside_box_bar_index: int | None = None
    close_below_breakout_level: bool | None = None
    close_above_breakout_level: bool | None = None
    midpoint_lost_after_breakout: bool | None = None
    wick_back_inside_but_close_hold: bool | None = None
    boundary_hold_after_breakout: bool | None = None
    midpoint_hold_after_breakout: bool | None = None
    followthrough_bar_count: int | None = None
    max_favorable_excursion_before_retest: float | None = None
    max_adverse_excursion_before_acceptance: float | None = None
    high_volume_no_result_after_breakout: bool | None = None
    primary_failure_reason: str = ""
    secondary_failure_reasons: object = None
    ce_subtype: str = ""
    midpoint_hold: bool | None = None
    boundary_hold: bool | None = None
    retest_hold: bool | None = None
    retest_depth_atr: float | None = None
    bars_to_retest: int | None = None
    entry_policy: str = ""
    entry_reference_time: str | None = None
    entry_to_stop: float | None = None
    stop_distance_atr: float | None = None
    stop_distance_box_ratio: float | None = None
    stop_anchor_type: str = ""
    stop_buffer_atr: float | None = None
    stop_inside_box: bool | None = None
    target_space: float | None = None
    target_space_atr: float | None = None
    gross_RR: float | None = None
    cost_adjusted_RR: float | None = None
    cost_per_R: float | None = None
    candidate_quality_tag: str = ""
    breakout_pullback_event_id: str = ""
    breakout_reference_level: float | None = None
    breakout_level_type: str = ""
    breakout_close: float | None = None
    breakout_displacement_ATR: float | None = None
    breakout_displacement_level_ratio: float | None = None
    breakout_range_expansion: float | None = None
    breakout_body_expansion: float | None = None
    acceptance_end_time: int | None = None
    close_back_inside_level: bool | None = None
    close_back_inside_bar_index: int | None = None
    wick_back_but_close_hold: bool | None = None
    immediate_reclaim: bool | None = None
    high_volume_no_result: bool | None = None
    acceptance_score: float | None = None
    acceptance_status: str = ""
    pullback_start_time: int | None = None
    pullback_end_time: int | None = None
    pullback_depth_ATR: float | None = None
    pullback_depth_vs_breakout: float | None = None
    pullback_depth_vs_box: float | None = None
    pullback_bars: int | None = None
    pullback_volume_ratio_vs_breakout: float | None = None
    pullback_volume_contraction: bool | None = None
    pullback_range_contraction: bool | None = None
    pullback_body_contraction: bool | None = None
    pullback_close_location: float | None = None
    pullback_zone_type: str = ""
    pullback_zone_distance_ATR: float | None = None
    pullback_held_level: bool | None = None
    pullback_invalidated: bool | None = None
    pullback_quality_score: float | None = None
    relaunch_time: int | None = None
    relaunch_close: float | None = None
    relaunch_displacement_ATR: float | None = None
    relaunch_body_pct: float | None = None
    relaunch_close_location: float | None = None
    relaunch_volume_recovery: float | None = None
    relaunch_breaks_micro_structure: bool | None = None
    relaunch_score: float | None = None
    stop_distance: float | None = None
    stop_distance_level_ratio: float | None = None
    bp_subtype: str = ""
    core_engine_version: str = ""
    level_id: str = ""
    breakout_event_id: str = ""
    lifecycle_event_id: str = ""
    zone_confirmed_time: int | None = None
    breakout_class: str = ""
    pullback_health_class: str = ""
    relaunch_type: str = ""
    relaunch_quality_class: str = ""
    target_source: str = ""
    target_quality_class: str = ""
    structural_stop_quality: str = ""
    stop_is_structural: bool | None = None
    candidate_rank_score: float | None = None
    setup_evidence: object = None

    def to_row(self) -> dict[str, object]:
        row = asdict(self)
        if not row["event_id"]:
            row["event_id"] = row["sweep_event_id"]
        if not row["trend_event_id"]:
            row["trend_event_id"] = row["event_id"]
        if row["feature_cutoff_time"] is None:
            row["feature_cutoff_time"] = row["signal_timestamp_ms"]
        if row["signal_time"] is None:
            row["signal_time"] = row["signal_timestamp_ms"]
        if row["entry_time"] is None:
            row["entry_time"] = row["entry_timestamp_ms"]
        return row


@dataclass(frozen=True)
class StopPlan:
    price: float
    mode_config: str
    mode_effective: str
    buffer_atr: float
    formula_used: str
    fallback_reason: str


def generate_raw_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    trend_candles: Sequence[object],
    context_features: Mapping[str, object],
    setup_filter: Sequence[str] | None = None,
) -> tuple[RawCandidate, ...]:
    structure = tuple(candle for candle in structure_candles if bool(getattr(candle, "is_confirmed", False)))
    entry = tuple(candle for candle in entry_candles if bool(getattr(candle, "is_confirmed", False)))
    trend = tuple(candle for candle in trend_candles if bool(getattr(candle, "is_confirmed", False)))
    if len(structure) < 5 or not entry:
        return ()

    precomputed_regime = context_features.get("market_regime") if isinstance(context_features, Mapping) else None
    regime = precomputed_regime if hasattr(precomputed_regime, "atr") and hasattr(precomputed_regime, "status") else build_market_regime(trend)
    atr = float(regime.atr) if regime is not None and regime.atr > 0 else _average_range(structure)
    if atr <= 0:
        return ()
    trend_state = regime.status if regime is not None else "unknown"
    trend_direction = regime.direction or "" if regime is not None else ""
    params = strategy_parameters_from_context(context_features)
    allowed_setups = set(setup_filter or ("liquidity_reversal", "trend_continuation"))
    candidates: list[RawCandidate] = []
    if "liquidity_reversal" in allowed_setups:
        candidates.extend(
            _liquidity_candidates(
                symbol=symbol,
                venue=venue,
                inst_id=inst_id,
                inst_type=inst_type,
                profile=profile,
                structure=structure,
                entry=entry,
                atr=atr,
                trend_state=trend_state,
                trend_direction=trend_direction,
                context_features=context_features,
                invalidation_mode=params.invalidation_mode,
                invalidation_buffer_atr=params.invalidation_buffer_atr,
            )
        )
    if "trend_continuation" in allowed_setups:
        candidates.extend(
            _trend_candidates(
                symbol=symbol,
                venue=venue,
                inst_id=inst_id,
                inst_type=inst_type,
                profile=profile,
                structure=structure,
                entry=entry,
                trend=trend,
                regime=regime,
                atr=atr,
                trend_state=trend_state,
                trend_direction=trend_direction,
                context_features=context_features,
                params=params,
            )
        )
    if "compression_expansion" in allowed_setups:
        candidates.extend(
            _compression_candidates(
                symbol=symbol,
                venue=venue,
                inst_id=inst_id,
                inst_type=inst_type,
                profile=profile,
                structure=structure,
                entry=entry,
                trend=trend,
                regime=regime,
                atr=atr,
                trend_state=trend_state,
                trend_direction=trend_direction,
                context_features=context_features,
                params=params,
            )
        )
    if "breakout_pullback" in allowed_setups:
        candidates.extend(
            _breakout_pullback_candidates(
                symbol=symbol,
                venue=venue,
                inst_id=inst_id,
                inst_type=inst_type,
                profile=profile,
                structure=structure,
                entry=entry,
                trend=trend,
                regime=regime,
                atr=atr,
                trend_state=trend_state,
                trend_direction=trend_direction,
                context_features=context_features,
                params=params,
            )
        )
    return tuple(candidates)


def _liquidity_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
    invalidation_mode: str,
    invalidation_buffer_atr: float,
) -> tuple[RawCandidate, ...]:
    rows: list[RawCandidate] = []
    asset = symbol.split("/", 1)[0].upper()
    for index in range(2, len(structure)):
        sweep = structure[index]
        previous = structure[index - 1]
        next_candles = tuple(structure[index + 1 : index + 6])
        prior = tuple(structure[:index])
        if not prior:
            continue
        prior_low = min(float(candle.low) for candle in prior)
        prior_high = max(float(candle.high) for candle in prior)
        prior_low_candle = min(prior, key=lambda candle: float(candle.low))
        prior_high_candle = max(prior, key=lambda candle: float(candle.high))
        downside_deviation = prior_low - float(sweep.low)
        upside_deviation = float(sweep.high) - prior_high
        if downside_deviation > 0:
            reclaim = _find_reclaim(sweep, next_candles, "long", prior_low)
            choch = next((candle for candle in next_candles if float(candle.close) > float(previous.high)), None)
            signal = _signal_candle(reclaim, choch, sweep)
            entry_candle = _entry_after_signal(entry, int(getattr(signal, "timestamp_ms")))
            if entry_candle is None or int(getattr(entry_candle, "timestamp_ms")) != int(getattr(entry[-1], "timestamp_ms")):
                continue
            volume_evidence = confirm_volume_price((*prior, sweep), "long", context_features=context_features).evidence
            stop = _stop("long", sweep, atr, invalidation_mode, invalidation_buffer_atr)
            entry_price = float(entry_candle.open)
            rows.append(
                _candidate(
                    symbol=symbol,
                    venue=venue,
                    inst_id=inst_id,
                    inst_type=inst_type,
                    profile=profile,
                    setup="liquidity_reversal",
                    direction="long",
                    asset=asset,
                    timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    structure_timestamp_ms=int(getattr(prior_low_candle, "timestamp_ms")),
                    sweep_timestamp_ms=int(getattr(sweep, "timestamp_ms")),
                    reclaim_timestamp_ms=None if reclaim is None else int(getattr(reclaim, "timestamp_ms")),
                    signal_timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    entry_timestamp_ms=int(getattr(entry_candle, "timestamp_ms")),
                    structure_level=prior_low,
                    sweep_extreme=float(sweep.low),
                    sweep_extreme_low=float(sweep.low),
                    sweep_extreme_high=float(sweep.high),
                    wick_ratio=_wick_ratio(sweep, "long"),
                    sweep_atr_multiple=downside_deviation / atr,
                    reclaim_bars=_bars_between(sweep, reclaim),
                    choch_detected=choch is not None,
                    bos_detected=False,
                    trend_state=trend_state,
                    trend_direction=trend_direction,
                    signal_close_price=float(signal.close),
                    entry_reference_price=entry_price,
                    actual_entry_price_if_simulated=entry_price,
                    target_price=entry_price + abs(entry_price - stop.price) * 2.0,
                    stop=stop,
                    atr_value=atr,
                    reclaim=reclaim,
                    volume_evidence=volume_evidence,
                    context_features=context_features,
                    countertrend=trend_direction == "short",
                    bars_structure_to_sweep=index - _candle_index(structure, prior_low_candle),
                    bars_sweep_to_reclaim=_bars_between(sweep, reclaim),
                    bars_reclaim_to_signal=_bars_between(reclaim, signal) if reclaim is not None else None,
                    bars_signal_to_entry=_entry_bars_between(entry, signal, entry_candle),
                    bars_reclaim_to_entry=_entry_bars_between(entry, reclaim, entry_candle) if reclaim is not None else None,
                    bars_sweep_to_entry=_entry_bars_between(entry, sweep, entry_candle),
                    candidate_generation_reason="downside_sweep_structure_event",
                )
            )
        if upside_deviation > 0:
            reclaim = _find_reclaim(sweep, next_candles, "short", prior_high)
            choch = next((candle for candle in next_candles if float(candle.close) < float(previous.low)), None)
            signal = _signal_candle(reclaim, choch, sweep)
            entry_candle = _entry_after_signal(entry, int(getattr(signal, "timestamp_ms")))
            if entry_candle is None or int(getattr(entry_candle, "timestamp_ms")) != int(getattr(entry[-1], "timestamp_ms")):
                continue
            volume_evidence = confirm_volume_price((*prior, sweep), "short", context_features=context_features).evidence
            stop = _stop("short", sweep, atr, invalidation_mode, invalidation_buffer_atr)
            entry_price = float(entry_candle.open)
            rows.append(
                _candidate(
                    symbol=symbol,
                    venue=venue,
                    inst_id=inst_id,
                    inst_type=inst_type,
                    profile=profile,
                    setup="liquidity_reversal",
                    direction="short",
                    asset=asset,
                    timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    structure_timestamp_ms=int(getattr(prior_high_candle, "timestamp_ms")),
                    sweep_timestamp_ms=int(getattr(sweep, "timestamp_ms")),
                    reclaim_timestamp_ms=None if reclaim is None else int(getattr(reclaim, "timestamp_ms")),
                    signal_timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    entry_timestamp_ms=int(getattr(entry_candle, "timestamp_ms")),
                    structure_level=prior_high,
                    sweep_extreme=float(sweep.high),
                    sweep_extreme_low=float(sweep.low),
                    sweep_extreme_high=float(sweep.high),
                    wick_ratio=_wick_ratio(sweep, "short"),
                    sweep_atr_multiple=upside_deviation / atr,
                    reclaim_bars=_bars_between(sweep, reclaim),
                    choch_detected=choch is not None,
                    bos_detected=False,
                    trend_state=trend_state,
                    trend_direction=trend_direction,
                    signal_close_price=float(signal.close),
                    entry_reference_price=entry_price,
                    actual_entry_price_if_simulated=entry_price,
                    target_price=entry_price - abs(stop.price - entry_price) * 2.0,
                    stop=stop,
                    atr_value=atr,
                    reclaim=reclaim,
                    volume_evidence=volume_evidence,
                    context_features=context_features,
                    countertrend=trend_direction == "long",
                    bars_structure_to_sweep=index - _candle_index(structure, prior_high_candle),
                    bars_sweep_to_reclaim=_bars_between(sweep, reclaim),
                    bars_reclaim_to_signal=_bars_between(reclaim, signal) if reclaim is not None else None,
                    bars_signal_to_entry=_entry_bars_between(entry, signal, entry_candle),
                    bars_reclaim_to_entry=_entry_bars_between(entry, reclaim, entry_candle) if reclaim is not None else None,
                    bars_sweep_to_entry=_entry_bars_between(entry, sweep, entry_candle),
                    candidate_generation_reason="upside_sweep_structure_event",
                )
            )
    return tuple(rows)


def _trend_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    trend: Sequence[object],
    regime: object | None,
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
    params: object,
) -> tuple[RawCandidate, ...]:
    if len(structure) < 6 or len(entry) < 2 or regime is None:
        return ()
    setup = detect_price_action_setup(
        structure,
        entry,
        regime,
        params,
        context_features=context_features,
    )
    if setup is None or setup.setup_type != "trend_continuation":
        return ()

    confirmation = confirm_volume_price(entry, setup.direction, context_features=context_features)
    if confirmation.status != "confirm":
        return ()

    evidence = dict(setup.evidence)
    signal = entry[-1]
    signal_ts = int(getattr(signal, "timestamp_ms"))
    breakout_ts = _as_int(evidence.get("breakout_timestamp_ms")) or int(getattr(structure[-2], "timestamp_ms"))
    pullback_ts = _as_int(evidence.get("pullback_timestamp_ms")) or int(getattr(structure[-1], "timestamp_ms"))
    trend_ts = int(getattr(trend[-1], "timestamp_ms")) if trend else signal_ts
    feature_cutoff = max(trend_ts, pullback_ts, signal_ts)
    asset = symbol.split("/", 1)[0].upper()
    direction = setup.direction
    structure_level = max(float(candle.high) for candle in structure[:-2]) if direction == "long" else min(float(candle.low) for candle in structure[:-2])
    sweep_extreme = float(structure[-2].high) if direction == "long" else float(structure[-2].low)
    stop = _manual_stop(direction, setup.invalidation_level, f"trend_continuation_strict_{direction}")
    row = _candidate(
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        inst_type=inst_type,
        profile=profile,
        setup="trend_continuation",
        direction=direction,
        asset=asset,
        timestamp_ms=signal_ts,
        structure_timestamp_ms=breakout_ts,
        sweep_timestamp_ms=breakout_ts,
        reclaim_timestamp_ms=pullback_ts,
        signal_timestamp_ms=signal_ts,
        entry_timestamp_ms=signal_ts,
        structure_level=structure_level,
        sweep_extreme=sweep_extreme,
        sweep_extreme_low=float(structure[-2].low),
        sweep_extreme_high=float(structure[-2].high),
        wick_ratio=_wick_ratio(structure[-2], direction),
        sweep_atr_multiple=abs(float(structure[-2].close) - structure_level) / atr if atr > 0 else 0.0,
        reclaim_bars=_entry_bars_between(structure, structure[-2], structure[-1]) or 0,
        choch_detected=False,
        bos_detected=True,
        trend_state=trend_state,
        trend_direction=trend_direction,
        signal_close_price=float(signal.close),
        entry_reference_price=float(signal.close),
        actual_entry_price_if_simulated=float(signal.close),
        target_price=setup.target_price,
        stop=stop,
        atr_value=atr,
        reclaim=structure[-1],
        volume_evidence={**confirmation.evidence, **evidence},
        context_features=context_features,
        countertrend=trend_direction not in {"", direction},
        bars_structure_to_sweep=None,
        bars_sweep_to_reclaim=_entry_bars_between(structure, structure[-2], structure[-1]),
        bars_reclaim_to_signal=_entry_bars_between(entry, structure[-1], signal),
        bars_signal_to_entry=0,
        bars_reclaim_to_entry=_entry_bars_between(entry, structure[-1], signal),
        bars_sweep_to_entry=_entry_bars_between(entry, structure[-2], signal),
        candidate_generation_reason="strict_bos_displacement_pullback_restart_confirmation",
    )
    payload = row.to_row()
    payload.update(
        {
            "feature_cutoff_time": feature_cutoff,
            "structure_confirmed_time": breakout_ts,
            "trend_confirmed_time": trend_ts,
            "breakout_time": breakout_ts,
            "pullback_confirmed_time": pullback_ts,
            "signal_time": signal_ts,
            "entry_time": signal_ts,
        }
    )
    return (RawCandidate(**{key: payload[key] for key in RawCandidate.__dataclass_fields__}),)


def _compression_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    trend: Sequence[object],
    regime: object | None,
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
    params: object,
) -> tuple[RawCandidate, ...]:
    if len(structure) < 6 or not entry:
        return ()
    diagnostics = evaluate_compression_expansion_diagnostics(
        structure,
        entry,
        regime,
        parameters=params,
        context_features=context_features,
    )
    if not diagnostics["candidate_ready"]:
        return ()
    metrics = dict(diagnostics["metrics"])
    direction = str(metrics["direction"])
    signal_ts = _as_int(metrics.get("confirmation_time")) or int(getattr(structure[-1], "timestamp_ms"))
    breakout_ts = _as_int(metrics.get("breakout_time")) or int(getattr(structure[-2], "timestamp_ms"))
    compression_start = _as_int(metrics.get("compression_start_time"))
    compression_end = _as_int(metrics.get("compression_end_time"))
    asset = symbol.split("/", 1)[0].upper()
    entry_price = float(metrics["entry_reference_price"])
    stop = _manual_stop(direction, float(metrics["stop_price"]), f"compression_expansion_box_{direction}")
    target = float(metrics["target_price"])
    structure_level = float(metrics["compression_high"] if direction == "long" else metrics["compression_low"])
    sweep_extreme = float(getattr(structure[-2], "high" if direction == "long" else "low"))
    row = _candidate(
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        inst_type=inst_type,
        profile=profile,
        setup="compression_expansion",
        direction=direction,
        asset=asset,
        timestamp_ms=signal_ts,
        structure_timestamp_ms=compression_end,
        sweep_timestamp_ms=breakout_ts,
        reclaim_timestamp_ms=signal_ts,
        signal_timestamp_ms=signal_ts,
        entry_timestamp_ms=signal_ts,
        structure_level=structure_level,
        sweep_extreme=sweep_extreme,
        sweep_extreme_low=float(getattr(structure[-2], "low")),
        sweep_extreme_high=float(getattr(structure[-2], "high")),
        wick_ratio=0.0,
        sweep_atr_multiple=float(metrics.get("compression_box_atr") or 0.0),
        reclaim_bars=_bars_between(structure[-2], structure[-1]),
        choch_detected=False,
        bos_detected=True,
        trend_state=trend_state,
        trend_direction=trend_direction,
        signal_close_price=float(getattr(structure[-1], "close")),
        entry_reference_price=entry_price,
        actual_entry_price_if_simulated=entry_price,
        target_price=target,
        stop=stop,
        atr_value=atr,
        reclaim=structure[-1],
        volume_evidence={
            "rolling_rvol": metrics.get("breakout_rvol"),
            "tod_dow_rvol": None,
            "raw_volume": getattr(structure[-2], "volume", None),
            "volume_baseline_mode": metrics.get("volume_baseline_mode", ""),
            "volume_bucket_sample_count": metrics.get("volume_bucket_sample_count", 0),
            "used_fallback_volume_baseline": metrics.get("used_fallback_volume_baseline", False),
        },
        context_features=context_features,
        countertrend=trend_direction not in {"", direction},
        bars_structure_to_sweep=None,
        bars_sweep_to_reclaim=_bars_between(structure[-2], structure[-1]),
        bars_reclaim_to_signal=0,
        bars_signal_to_entry=0,
        bars_reclaim_to_entry=0,
        bars_sweep_to_entry=_bars_between(structure[-2], structure[-1]),
        candidate_generation_reason="compression_box_breakout_expansion_confirmation",
    )
    payload = row.to_row()
    compression_event_id = sha256(
        f"{symbol}|{profile}|compression_expansion|{direction}|{compression_start}|{compression_end}|{breakout_ts}|{metrics.get('ce_subtype','')}|{metrics.get('stop_anchor_type','')}|{structure_level:.8f}".encode("utf-8")
    ).hexdigest()[:24]
    payload.update(
        {
            "candidate_id": compression_event_id,
            "strategy_family": "compression_expansion_breakout",
            "compression_event_id": compression_event_id,
            "event_id": compression_event_id,
            "sweep_event_id": compression_event_id,
            "trend_event_id": compression_event_id,
            "compression_start_time": compression_start,
            "compression_end_time": compression_end,
            "breakout_time": breakout_ts,
            "confirmation_time": signal_ts,
            "feature_cutoff_time": signal_ts,
            "structure_confirmed_time": compression_end,
            "trend_confirmed_time": int(getattr(trend[-1], "timestamp_ms")) if trend else signal_ts,
            "pullback_confirmed_time": signal_ts,
            "signal_time": signal_ts,
            "entry_time": signal_ts,
            "compression_high": metrics.get("compression_high"),
            "compression_low": metrics.get("compression_low"),
            "compression_midpoint": metrics.get("compression_midpoint"),
            "compression_box_height": metrics.get("compression_box_height"),
            "compression_box_atr": metrics.get("compression_box_atr"),
            "compression_avg_range_atr": metrics.get("compression_avg_range_atr"),
            "breakout_displacement_atr": metrics.get("breakout_displacement_atr"),
            "breakout_displacement_box_ratio": metrics.get("breakout_displacement_box_ratio"),
            "breakout_close_location": metrics.get("breakout_close_location"),
            "breakout_rvol": metrics.get("breakout_rvol"),
            "breakout_body_ratio": metrics.get("breakout_body_ratio"),
            "breakout_body_pct": metrics.get("breakout_body_pct"),
            "breakout_score": metrics.get("breakout_score"),
            "breakout_range_vs_ATR": metrics.get("breakout_range_vs_ATR"),
            "breakout_range_vs_box_height": metrics.get("breakout_range_vs_box_height"),
            "close_outside_box_distance_ATR": metrics.get("close_outside_box_distance_ATR"),
            "breakout_volume_z": metrics.get("breakout_volume_z"),
            "volume_expansion_vs_compression": metrics.get("volume_expansion_vs_compression"),
            "range_expansion_vs_compression": metrics.get("range_expansion_vs_compression"),
            "body_expansion_vs_compression": metrics.get("body_expansion_vs_compression"),
            "acceptance_window_bars": metrics.get("acceptance_window_bars"),
            "close_back_inside_box": metrics.get("close_back_inside_box"),
            "close_back_inside_box_bar_index": metrics.get("close_back_inside_box_bar_index"),
            "close_below_breakout_level": metrics.get("close_below_breakout_level"),
            "close_above_breakout_level": metrics.get("close_above_breakout_level"),
            "midpoint_lost_after_breakout": metrics.get("midpoint_lost_after_breakout"),
            "wick_back_inside_but_close_hold": metrics.get("wick_back_inside_but_close_hold"),
            "boundary_hold_after_breakout": metrics.get("boundary_hold_after_breakout"),
            "midpoint_hold_after_breakout": metrics.get("midpoint_hold_after_breakout"),
            "followthrough_bar_count": metrics.get("followthrough_bar_count"),
            "max_favorable_excursion_before_retest": metrics.get("max_favorable_excursion_before_retest"),
            "max_adverse_excursion_before_acceptance": metrics.get("max_adverse_excursion_before_acceptance"),
            "high_volume_no_result_after_breakout": metrics.get("high_volume_no_result_after_breakout"),
            "primary_failure_reason": metrics.get("primary_failure_reason") or "",
            "secondary_failure_reasons": metrics.get("secondary_failure_reasons") or [],
            "ce_subtype": metrics.get("ce_subtype") or "",
            "midpoint_hold": metrics.get("midpoint_hold"),
            "boundary_hold": metrics.get("boundary_hold"),
            "retest_hold": metrics.get("retest_hold"),
            "retest_depth_atr": metrics.get("retest_depth_atr"),
            "bars_to_retest": metrics.get("bars_to_retest"),
            "entry_policy": metrics.get("entry_policy") or "",
            "entry_reference_time": metrics.get("entry_reference_time"),
            "entry_to_stop": metrics.get("entry_to_stop"),
            "stop_distance_atr": metrics.get("stop_distance_atr"),
            "stop_distance_box_ratio": metrics.get("stop_distance_box_ratio"),
            "stop_anchor_type": metrics.get("stop_anchor_type"),
            "stop_buffer_atr": metrics.get("stop_buffer_atr"),
            "stop_inside_box": metrics.get("stop_inside_box"),
            "target_space": metrics.get("target_space"),
            "target_space_atr": metrics.get("target_space_atr"),
            "gross_RR": metrics.get("gross_RR"),
            "candidate_quality_tag": _compression_quality_tag(metrics),
        }
    )
    return (RawCandidate(**{key: payload[key] for key in RawCandidate.__dataclass_fields__}),)


def _breakout_pullback_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    trend: Sequence[object],
    regime: object | None,
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
    params: object,
) -> tuple[RawCandidate, ...]:
    if len(structure) < 8 or not entry:
        return ()
    diagnostics = evaluate_breakout_pullback_core_diagnostics(
        structure,
        entry,
        regime,
        parameters=params,
        context_features=context_features,
    )
    if not diagnostics["candidate_ready"]:
        return ()
    metrics = dict(diagnostics["metrics"])
    direction = str(metrics["direction"])
    signal_ts = _as_int(metrics.get("relaunch_time"))
    breakout_ts = _as_int(metrics.get("breakout_time"))
    pullback_ts = _as_int(metrics.get("pullback_end_time"))
    if signal_ts is None or breakout_ts is None or pullback_ts is None:
        return ()
    breakout = next((candle for candle in structure if int(getattr(candle, "timestamp_ms")) == breakout_ts), None)
    pullback = next((candle for candle in structure if int(getattr(candle, "timestamp_ms")) == pullback_ts), None)
    relaunch = next((candle for candle in structure if int(getattr(candle, "timestamp_ms")) == signal_ts), None)
    if breakout is None or pullback is None or relaunch is None:
        return ()
    entry_price = float(metrics.get("relaunch_close") or getattr(relaunch, "close"))
    stop_price = _as_float(metrics.get("stop"))
    target_price = _as_float(metrics.get("target"))
    if stop_price is None or target_price is None:
        return ()
    zone = metrics.get("zone") if isinstance(metrics.get("zone"), Mapping) else {}
    structure_level = float(zone.get("zone_mid") or metrics.get("breakout_price") or 0.0)
    event_id = str(metrics.get("lifecycle_event_id") or metrics.get("breakout_event_id") or "")
    if not event_id:
        return ()
    row = _candidate(
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        inst_type=inst_type,
        profile=profile,
        setup="breakout_pullback",
        direction=direction,
        asset=symbol.split("/", 1)[0].upper(),
        timestamp_ms=signal_ts,
        structure_timestamp_ms=_as_int(zone.get("last_touch_time")) or breakout_ts,
        sweep_timestamp_ms=breakout_ts,
        reclaim_timestamp_ms=pullback_ts,
        signal_timestamp_ms=signal_ts,
        entry_timestamp_ms=signal_ts,
        structure_level=structure_level,
        sweep_extreme=float(getattr(breakout, "high" if direction == "long" else "low")),
        sweep_extreme_low=float(getattr(breakout, "low")),
        sweep_extreme_high=float(getattr(breakout, "high")),
        wick_ratio=0.0,
        sweep_atr_multiple=float(metrics.get("breakout_distance_ATR") or 0.0),
        reclaim_bars=max(0, _bars_between(breakout, pullback)),
        choch_detected=False,
        bos_detected=True,
        trend_state=trend_state,
        trend_direction=trend_direction,
        signal_close_price=float(getattr(relaunch, "close")),
        entry_reference_price=entry_price,
        actual_entry_price_if_simulated=entry_price,
        target_price=target_price,
        stop=_manual_stop(direction, stop_price, str(metrics.get("stop_anchor_type") or "retest_structure_invalidation_stop")),
        atr_value=atr,
        reclaim=pullback,
        volume_evidence={
            "rolling_rvol": metrics.get("breakout_RVOL"),
            "tod_dow_rvol": None,
            "raw_volume": getattr(breakout, "volume", None),
            "volume_baseline_mode": "trend_continuation_core",
            "volume_bucket_sample_count": 0,
            "used_fallback_volume_baseline": True,
        },
        context_features=context_features,
        countertrend=trend_direction not in {"", direction},
        bars_structure_to_sweep=None,
        bars_sweep_to_reclaim=max(0, _bars_between(breakout, pullback)),
        bars_reclaim_to_signal=max(0, _bars_between(pullback, relaunch)),
        bars_signal_to_entry=0,
        bars_reclaim_to_entry=max(0, _bars_between(pullback, relaunch)),
        bars_sweep_to_entry=max(0, _bars_between(breakout, relaunch)),
        candidate_generation_reason="trend_continuation_core_lifecycle_pullback_relaunch",
    )
    payload = row.to_row()
    flat_metrics = {
        "candidate_id": event_id,
        "event_id": event_id,
        "sweep_event_id": event_id,
        "trend_event_id": event_id,
        "breakout_pullback_event_id": event_id,
        "strategy_family": "breakout_pullback_continuation",
        "core_engine_version": CORE_ENGINE_VERSION,
        "level_id": metrics.get("level_id"),
        "breakout_event_id": metrics.get("breakout_event_id"),
        "lifecycle_event_id": metrics.get("lifecycle_event_id"),
        "zone_confirmed_time": zone.get("last_touch_time"),
        "breakout_class": metrics.get("breakout_class"),
        "pullback_health_class": metrics.get("pullback_health_class"),
        "relaunch_type": metrics.get("relaunch_type"),
        "relaunch_quality_class": metrics.get("relaunch_quality_class"),
        "target_source": metrics.get("target_source"),
        "target_quality_class": metrics.get("target_quality_class"),
        "structural_stop_quality": metrics.get("structural_stop_quality"),
        "stop_is_structural": metrics.get("stop_is_structural"),
        "candidate_rank_score": metrics.get("candidate_rank_score"),
        "setup_evidence": metrics,
        "breakout_time": breakout_ts,
        "acceptance_end_time": _as_int(metrics.get("acceptance_end_time")) or breakout_ts,
        "pullback_start_time": metrics.get("pullback_start_time"),
        "pullback_end_time": pullback_ts,
        "pullback_confirmed_time": pullback_ts,
        "relaunch_time": signal_ts,
        "signal_time": signal_ts,
        "entry_time": signal_ts,
        "feature_cutoff_time": signal_ts,
        "structure_confirmed_time": zone.get("last_touch_time") or breakout_ts,
        "trend_confirmed_time": int(getattr(trend[-1], "timestamp_ms")) if trend else signal_ts,
        "candidate_quality_tag": metrics.get("pullback_health_class") or "",
        "bp_subtype": metrics.get("bp_subtype") or "",
        "stop_anchor_type": metrics.get("stop_anchor_type") or "",
        "stop_distance": metrics.get("stop_distance"),
        "stop_distance_atr": metrics.get("stop_distance_ATR"),
        "stop_distance_level_ratio": metrics.get("stop_distance_zone_ratio"),
        "stop_buffer_atr": metrics.get("stop_buffer_ATR"),
        "entry_to_stop": metrics.get("stop_distance"),
        "target_space": metrics.get("target_space"),
        "target_space_atr": metrics.get("target_space_ATR"),
        "gross_RR": metrics.get("gross_RR"),
        "pullback_quality_score": metrics.get("pullback_health_score"),
        "relaunch_score": metrics.get("relaunch_score"),
        "primary_failure_reason": metrics.get("primary_failure_reason") or "",
        "secondary_failure_reasons": metrics.get("secondary_failure_reasons") or [],
    }
    payload.update(flat_metrics)
    return (RawCandidate(**{key: payload[key] for key in RawCandidate.__dataclass_fields__}),)


def _legacy_breakout_pullback_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    trend: Sequence[object],
    regime: object | None,
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
    params: object,
) -> tuple[RawCandidate, ...]:
    if len(structure) < 8 or not entry:
        return ()
    diagnostics = evaluate_breakout_pullback_diagnostics(
        structure,
        entry,
        regime,
        parameters=params,
        context_features=context_features,
    )
    if not diagnostics["candidate_ready"]:
        return ()
    metrics = dict(diagnostics["metrics"])
    direction = str(metrics["direction"])
    signal_ts = _as_int(metrics.get("relaunch_time")) or int(getattr(structure[-1], "timestamp_ms"))
    breakout_ts = _as_int(metrics.get("breakout_time")) or int(getattr(structure[-4], "timestamp_ms"))
    pullback_ts = _as_int(metrics.get("pullback_end_time")) or int(getattr(structure[-2], "timestamp_ms"))
    asset = symbol.split("/", 1)[0].upper()
    entry_price = float(metrics["entry_reference_price"])
    stop = _manual_stop(direction, float(metrics["stop_price"]), f"breakout_pullback_{direction}")
    target = float(metrics["target_price"])
    structure_level = float(metrics.get("breakout_reference_level") or 0.0)
    sweep_extreme = float(getattr(structure[-4], "high" if direction == "long" else "low"))
    row = _candidate(
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        inst_type=inst_type,
        profile=profile,
        setup="breakout_pullback",
        direction=direction,
        asset=asset,
        timestamp_ms=signal_ts,
        structure_timestamp_ms=breakout_ts,
        sweep_timestamp_ms=breakout_ts,
        reclaim_timestamp_ms=pullback_ts,
        signal_timestamp_ms=signal_ts,
        entry_timestamp_ms=signal_ts,
        structure_level=structure_level,
        sweep_extreme=sweep_extreme,
        sweep_extreme_low=float(getattr(structure[-4], "low")),
        sweep_extreme_high=float(getattr(structure[-4], "high")),
        wick_ratio=0.0,
        sweep_atr_multiple=float(metrics.get("breakout_displacement_ATR") or 0.0),
        reclaim_bars=_bars_between(structure[-4], structure[-2]),
        choch_detected=False,
        bos_detected=True,
        trend_state=trend_state,
        trend_direction=trend_direction,
        signal_close_price=float(getattr(structure[-1], "close")),
        entry_reference_price=entry_price,
        actual_entry_price_if_simulated=entry_price,
        target_price=target,
        stop=stop,
        atr_value=atr,
        reclaim=structure[-2],
        volume_evidence={
            "rolling_rvol": metrics.get("breakout_rvol"),
            "tod_dow_rvol": None,
            "raw_volume": getattr(structure[-4], "volume", None),
            "volume_baseline_mode": metrics.get("volume_baseline_mode", ""),
            "volume_bucket_sample_count": metrics.get("volume_bucket_sample_count", 0),
            "used_fallback_volume_baseline": metrics.get("used_fallback_volume_baseline", False),
        },
        context_features=context_features,
        countertrend=trend_direction not in {"", direction},
        bars_structure_to_sweep=None,
        bars_sweep_to_reclaim=_bars_between(structure[-4], structure[-2]),
        bars_reclaim_to_signal=_bars_between(structure[-2], structure[-1]),
        bars_signal_to_entry=0,
        bars_reclaim_to_entry=_bars_between(structure[-2], structure[-1]),
        bars_sweep_to_entry=_bars_between(structure[-4], structure[-1]),
        candidate_generation_reason="breakout_acceptance_pullback_relaunch_confirmation",
    )
    payload = row.to_row()
    event_id = sha256(
        f"{symbol}|{profile}|breakout_pullback|{direction}|{breakout_ts}|{pullback_ts}|{signal_ts}|{metrics.get('bp_subtype','')}|{metrics.get('stop_anchor_type','')}|{structure_level:.8f}".encode("utf-8")
    ).hexdigest()[:24]
    bp_fields = (
        "breakout_reference_level",
        "breakout_level_type",
        "breakout_close",
        "breakout_displacement_ATR",
        "breakout_displacement_level_ratio",
        "breakout_close_location",
        "breakout_body_pct",
        "breakout_range_vs_ATR",
        "breakout_range_expansion",
        "breakout_body_expansion",
        "breakout_RVOL",
        "breakout_volume_z",
        "breakout_score",
        "acceptance_window_bars",
        "close_back_inside_level",
        "close_back_inside_bar_index",
        "wick_back_but_close_hold",
        "immediate_reclaim",
        "high_volume_no_result",
        "boundary_hold_after_breakout",
        "midpoint_hold_after_breakout",
        "acceptance_score",
        "acceptance_status",
        "pullback_start_time",
        "pullback_end_time",
        "pullback_depth_ATR",
        "pullback_depth_vs_breakout",
        "pullback_depth_vs_box",
        "pullback_bars",
        "pullback_volume_ratio_vs_breakout",
        "pullback_volume_contraction",
        "pullback_range_contraction",
        "pullback_body_contraction",
        "pullback_close_location",
        "pullback_zone_type",
        "pullback_zone_distance_ATR",
        "pullback_held_level",
        "pullback_invalidated",
        "pullback_quality_score",
        "relaunch_time",
        "relaunch_close",
        "relaunch_displacement_ATR",
        "relaunch_body_pct",
        "relaunch_close_location",
        "relaunch_volume_recovery",
        "relaunch_breaks_micro_structure",
        "relaunch_score",
        "entry",
        "stop",
        "target",
        "stop_anchor_type",
        "stop_distance",
        "stop_distance_ATR",
        "stop_distance_level_ratio",
        "stop_buffer_ATR",
        "entry_to_stop",
        "target_space",
        "gross_RR",
        "cost_adjusted_RR",
        "cost_per_R",
        "bp_subtype",
        "primary_failure_reason",
        "secondary_failure_reasons",
    )
    payload.update(
        {
            "candidate_id": event_id,
            "event_id": event_id,
            "sweep_event_id": event_id,
            "trend_event_id": event_id,
            "breakout_pullback_event_id": event_id,
            "strategy_family": "breakout_pullback_continuation",
            "breakout_time": breakout_ts,
            "acceptance_end_time": _as_int(metrics.get("acceptance_end_time")) or int(getattr(structure[-3], "timestamp_ms")),
            "pullback_confirmed_time": pullback_ts,
            "signal_time": signal_ts,
            "entry_time": signal_ts,
            "feature_cutoff_time": signal_ts,
            "structure_confirmed_time": breakout_ts,
            "trend_confirmed_time": int(getattr(trend[-1], "timestamp_ms")) if trend else signal_ts,
            "candidate_quality_tag": _breakout_pullback_quality_tag(metrics),
        }
    )
    payload.update({field: metrics.get(field) for field in bp_fields if field in metrics})
    payload["stop_distance_atr"] = metrics.get("stop_distance_ATR")
    payload["stop_buffer_atr"] = metrics.get("stop_buffer_ATR")
    return (RawCandidate(**{key: payload[key] for key in RawCandidate.__dataclass_fields__}),)


def _candidate(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    setup: str,
    direction: str,
    asset: str,
    timestamp_ms: int,
    structure_timestamp_ms: int | None,
    sweep_timestamp_ms: int,
    reclaim_timestamp_ms: int | None,
    signal_timestamp_ms: int,
    entry_timestamp_ms: int,
    structure_level: float,
    sweep_extreme: float,
    sweep_extreme_low: float,
    sweep_extreme_high: float,
    wick_ratio: float,
    sweep_atr_multiple: float,
    reclaim_bars: int,
    choch_detected: bool,
    bos_detected: bool,
    trend_state: str,
    trend_direction: str,
    signal_close_price: float,
    entry_reference_price: float,
    actual_entry_price_if_simulated: float,
    target_price: float,
    stop: StopPlan,
    atr_value: float,
    reclaim: object | None,
    volume_evidence: Mapping[str, object],
    context_features: Mapping[str, object],
    countertrend: bool,
    bars_structure_to_sweep: int | None,
    bars_sweep_to_reclaim: int | None,
    bars_reclaim_to_signal: int | None,
    bars_signal_to_entry: int | None,
    bars_reclaim_to_entry: int | None,
    bars_sweep_to_entry: int | None,
    candidate_generation_reason: str,
) -> RawCandidate:
    volume = volume_evidence
    reclaim_rvol = _as_float(volume.get("tod_dow_rvol") or volume.get("rolling_rvol"))
    sweep_event_id = f"{symbol}|{profile}|{setup}|{direction}|{structure_timestamp_ms}|{sweep_timestamp_ms}|{reclaim_timestamp_ms}|{structure_level:.8f}|{sweep_extreme:.8f}"
    lifecycle_status, lifecycle_reason = _lifecycle_status(
        reclaim_timestamp_ms=reclaim_timestamp_ms,
        bars_reclaim_to_signal=bars_reclaim_to_signal,
        bars_signal_to_entry=bars_signal_to_entry,
        bars_reclaim_to_entry=bars_reclaim_to_entry,
        entry_reference_price=entry_reference_price,
        reclaim_price=None if reclaim is None else float(getattr(reclaim, "close")),
        atr=atr_value,
    )
    return RawCandidate(
        candidate_id=sha256(sweep_event_id.encode("utf-8")).hexdigest()[:24],
        timestamp_ms=timestamp_ms,
        structure_timestamp_ms=structure_timestamp_ms,
        sweep_timestamp_ms=sweep_timestamp_ms,
        reclaim_timestamp_ms=reclaim_timestamp_ms,
        signal_timestamp_ms=signal_timestamp_ms,
        entry_timestamp_ms=entry_timestamp_ms,
        asset=asset,
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        inst_type=inst_type,
        profile=profile,
        setup=setup,
        direction=direction,
        long_or_short=direction,
        structure_level=structure_level,
        sweep_extreme=sweep_extreme,
        wick_ratio=wick_ratio,
        sweep_atr_multiple=sweep_atr_multiple,
        rolling_rvol=_as_float(volume.get("rolling_rvol")),
        tod_dow_rvol=_as_float(volume.get("tod_dow_rvol")),
        reclaim_bars=reclaim_bars,
        choch_detected=choch_detected,
        bos_detected=bos_detected,
        trend_state=trend_state,
        trend_direction=trend_direction,
        signal_close_price=signal_close_price,
        entry_reference_price=entry_reference_price,
        actual_entry_price_if_simulated=actual_entry_price_if_simulated,
        target_price=target_price,
        stop_price=stop.price,
        atr_value=atr_value,
        reclaim_rvol=reclaim_rvol,
        countertrend=countertrend,
        raw_volume=_as_float(volume.get("raw_volume")),
        log_volume=_as_float(volume.get("log_volume")),
        volume_baseline_mode=str(volume.get("volume_baseline_mode", "")),
        volume_bucket_key=str(volume.get("volume_bucket_key", "")),
        volume_bucket_sample_count=int(volume.get("volume_bucket_sample_count", 0) or 0),
        used_fallback_volume_baseline=bool(volume.get("used_fallback_volume_baseline", False)),
        sweep_extreme_price=sweep_extreme,
        sweep_extreme_low=sweep_extreme_low,
        sweep_extreme_high=sweep_extreme_high,
        sweep_extreme_price_used=sweep_extreme,
        reclaim_price=None if reclaim is None else float(getattr(reclaim, "close")),
        invalidation_mode_config=stop.mode_config,
        invalidation_mode_effective=stop.mode_effective,
        invalidation_buffer_atr=stop.buffer_atr,
        stop_formula_used=stop.formula_used,
        stop_formula_fallback_reason=stop.fallback_reason,
        atr_used_for_stop=atr_value,
        atr_used_for_stop_timeframe=str(context_features.get("trend_timeframe", "")),
        bars_structure_to_sweep=bars_structure_to_sweep,
        bars_sweep_to_reclaim=bars_sweep_to_reclaim,
        bars_reclaim_to_signal=bars_reclaim_to_signal,
        bars_signal_to_entry=bars_signal_to_entry,
        bars_reclaim_to_entry=bars_reclaim_to_entry,
        bars_sweep_to_entry=bars_sweep_to_entry,
        candidate_lifecycle_status=lifecycle_status,
        candidate_lifecycle_reason=lifecycle_reason,
        sweep_event_id=sha256(sweep_event_id.encode("utf-8")).hexdigest()[:24],
        candidate_generation_reason=candidate_generation_reason,
    )


def _compression_quality_tag(metrics: Mapping[str, object]) -> str:
    box_atr = _as_float(metrics.get("compression_box_atr")) or 0.0
    rvol = _as_float(metrics.get("breakout_rvol")) or 0.0
    gross_rr = _as_float(metrics.get("gross_RR")) or _as_float(metrics.get("target_r")) or 0.0
    midpoint = bool(metrics.get("midpoint_hold"))
    boundary = bool(metrics.get("boundary_hold") or metrics.get("retest_hold"))
    if box_atr <= 0 or gross_rr <= 0:
        return "low_quality_reject"
    if box_atr < 0.25 or gross_rr < 1.0:
        return "low_quality_reject"
    if rvol >= 1.8 and midpoint and boundary and gross_rr >= 1.5:
        return "high_quality_candidate"
    if rvol >= 1.3 and (midpoint or boundary):
        return "reasonable_near_miss"
    return "medium_quality_candidate"


def _breakout_pullback_quality_tag(metrics: Mapping[str, object]) -> str:
    breakout_score = _as_float(metrics.get("breakout_score")) or 0.0
    acceptance_score = _as_float(metrics.get("acceptance_score")) or 0.0
    pullback_score = _as_float(metrics.get("pullback_quality_score")) or 0.0
    relaunch_score = _as_float(metrics.get("relaunch_score")) or 0.0
    gross_rr = _as_float(metrics.get("gross_RR")) or 0.0
    if gross_rr <= 0 or pullback_score < 0.35:
        return "low_quality_reject"
    if breakout_score >= 0.70 and acceptance_score >= 1.0 and pullback_score >= 0.65 and relaunch_score >= 0.60 and gross_rr >= 1.5:
        return "high_quality_candidate"
    if pullback_score >= 0.50 and relaunch_score >= 0.45 and gross_rr >= 1.2:
        return "reasonable_near_miss"
    return "medium_quality_candidate"


def _average_range(candles: Sequence[object]) -> float:
    if not candles:
        return 0.0
    return sum(float(candle.high) - float(candle.low) for candle in candles) / len(candles)


def _find_reclaim(sweep: object, next_candles: Sequence[object], direction: str, level: float) -> object | None:
    candidates = (sweep, *next_candles)
    if direction == "long":
        return next((candle for candle in candidates if float(candle.close) > level), None)
    return next((candle for candle in candidates if float(candle.close) < level), None)


def _signal_candle(reclaim: object | None, choch: object | None, sweep: object) -> object:
    if reclaim is None and choch is None:
        return sweep
    if reclaim is None:
        return choch
    if choch is None:
        return reclaim
    return choch if int(getattr(choch, "timestamp_ms")) >= int(getattr(reclaim, "timestamp_ms")) else reclaim


def _entry_after_signal(entry: Sequence[object], signal_timestamp_ms: int) -> object | None:
    return next((candle for candle in entry if int(getattr(candle, "timestamp_ms")) > signal_timestamp_ms), None)


def _bars_between(first: object, second: object | None) -> int:
    if second is None:
        return 999
    first_ts = int(getattr(first, "timestamp_ms"))
    second_ts = int(getattr(second, "timestamp_ms"))
    return 0 if first_ts == second_ts else 1


def _entry_bars_between(entry: Sequence[object], first: object | None, second: object | None) -> int | None:
    if first is None or second is None:
        return None
    first_ts = int(getattr(first, "timestamp_ms"))
    second_ts = int(getattr(second, "timestamp_ms"))
    first_index = next((index for index, candle in enumerate(entry) if int(getattr(candle, "timestamp_ms")) >= first_ts), None)
    second_index = next((index for index, candle in enumerate(entry) if int(getattr(candle, "timestamp_ms")) >= second_ts), None)
    if first_index is None or second_index is None:
        return None
    return max(0, second_index - first_index)


def _candle_index(candles: Sequence[object], target: object) -> int:
    target_ts = int(getattr(target, "timestamp_ms"))
    return next((index for index, candle in enumerate(candles) if int(getattr(candle, "timestamp_ms")) == target_ts), 0)


def _lifecycle_status(
    *,
    reclaim_timestamp_ms: int | None,
    bars_reclaim_to_signal: int | None,
    bars_signal_to_entry: int | None,
    bars_reclaim_to_entry: int | None,
    entry_reference_price: float,
    reclaim_price: float | None,
    atr: float,
) -> tuple[str, str]:
    if reclaim_timestamp_ms is None:
        return "expired_candidate", "missing_reclaim"
    if bars_reclaim_to_signal is not None and bars_reclaim_to_signal > 3:
        return "expired_candidate", "reclaim_to_signal_delay"
    if bars_reclaim_to_entry is not None and bars_reclaim_to_entry > 3:
        return "expired_candidate", "reclaim_to_entry_delay"
    if reclaim_price is not None and atr > 0 and abs(entry_reference_price - reclaim_price) / atr > 1.5:
        return "expired_candidate", "entry_too_far_from_reclaim"
    if bars_reclaim_to_signal is not None and bars_reclaim_to_signal > 1:
        return "stale_candidate", "reclaim_to_signal_delay"
    if bars_signal_to_entry is not None and bars_signal_to_entry > 1:
        return "stale_candidate", "signal_to_entry_delay"
    return "active_candidate", ""


def _wick_ratio(candle: object, direction: str) -> float:
    candle_range = float(candle.high) - float(candle.low)
    if candle_range <= 0:
        return 0.0
    if direction == "long":
        wick = min(float(candle.open), float(candle.close)) - float(candle.low)
    else:
        wick = float(candle.high) - max(float(candle.open), float(candle.close))
    return max(0.0, wick) / candle_range


def _stop(direction: str, candle: object, atr: float, mode: str, buffer_atr: float) -> StopPlan:
    high = float(candle.high)
    low = float(candle.low)
    if mode == "structure_extreme_buffer" and atr > 0 and math.isfinite(atr):
        if direction == "long":
            price = low - buffer_atr * atr
        else:
            price = high + buffer_atr * atr
        return StopPlan(
            price=price,
            mode_config=mode,
            mode_effective="structure_extreme_buffer",
            buffer_atr=buffer_atr,
            formula_used=f"structure_extreme_buffer_{direction}",
            fallback_reason="",
        )
    return _legacy_stop(
        direction,
        high,
        low,
        atr,
        mode_config=mode,
        fallback_reason="" if mode != "structure_extreme_buffer" else "invalid_atr_for_structure_extreme_buffer",
    )


def _legacy_stop(
    direction: str,
    high: float,
    low: float,
    atr: float,
    *,
    mode_config: str = "atr_buffer",
    fallback_reason: str = "",
) -> StopPlan:
    if direction == "long":
        price = low - atr
    else:
        price = high + atr
    return StopPlan(
        price=price,
        mode_config=mode_config,
        mode_effective="atr_buffer",
        buffer_atr=1.0,
        formula_used=f"legacy_atr_buffer_{direction}",
        fallback_reason=fallback_reason,
    )


def _manual_stop(direction: str, price: float, formula_used: str) -> StopPlan:
    return StopPlan(
        price=price,
        mode_config="atr_buffer",
        mode_effective="atr_buffer",
        buffer_atr=1.0,
        formula_used=formula_used,
        fallback_reason="",
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


__all__ = ("RawCandidate", "generate_raw_candidates")
