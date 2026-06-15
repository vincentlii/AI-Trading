from __future__ import annotations

import math
from datetime import UTC, datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from trading_system.indicators import (
    average_true_range,
    choppiness_index,
    directional_movement_index,
    exponential_moving_average,
    kaufman_efficiency_ratio,
    ttm_squeeze_on,
)


@dataclass(frozen=True)
class MarketRegimeContext:
    status: str
    direction: str | None
    last_close: float
    fast_ema: float
    slow_ema: float
    atr: float
    efficiency_ratio: float
    choppiness: float
    dmi_plus: float | None = None
    dmi_minus: float | None = None
    adx: float | None = None
    ttm_squeeze: bool = False
    evidence: Mapping[str, object] = field(default_factory=dict)

    @property
    def state(self) -> str:
        return self.status


@dataclass(frozen=True)
class PriceActionSetup:
    setup_type: str
    direction: str
    entry_zone_low: float
    entry_zone_high: float
    invalidation_level: float
    target_price: float
    evidence: Mapping[str, object] = field(default_factory=dict)

    @property
    def entry_zone(self) -> Mapping[str, float]:
        return {"low": self.entry_zone_low, "high": self.entry_zone_high}


@dataclass(frozen=True)
class VolumePriceConfirmation:
    status: str
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyParameters:
    trend_gate_policy: str = "strict_mature_trend"
    breakout_buffer_atr: float = 0.5
    breakout_body_ratio_min: float = 0.7
    breakout_close_location_max: float = 0.2
    breakout_rvol_min: float = 2.0
    pullback_rvol_max: float = 0.8
    restart_rvol_min: float = 1.5
    compression_lookback_bars: int = 8
    compression_box_atr_max: float = 1.50
    compression_avg_range_atr_max: float = 0.60
    compression_breakout_buffer_atr: float = 0.15
    compression_breakout_body_ratio_min: float = 0.55
    compression_breakout_rvol_min: float = 1.50
    compression_retest_tolerance_atr: float = 0.10
    compression_min_target_r: float = 1.00
    compression_hold_policy: str = "midpoint_and_boundary"
    compression_stop_policy: str = "breakout_midpoint_or_box_edge"
    compression_stop_buffer_atr: float = 0.10
    compression_box_atr_min: float = 0.00
    compression_min_target_space_atr: float = 0.00
    compression_min_cost_adjusted_rr: float = 0.00
    compression_max_cost_per_r: float = 999.00
    compression_breakout_semantic_policy: str = "legacy"
    compression_acceptance_window_bars: int = 1
    compression_min_breakout_score: float = 0.00
    compression_min_close_outside_box_atr: float = 0.00
    compression_subtype_focus: str = "any"
    compression_entry_policy: str = "confirmation_close"
    bp_lookback_bars: int = 6
    bp_breakout_buffer_atr: float = 0.10
    bp_breakout_body_ratio_min: float = 0.45
    bp_breakout_rvol_min: float = 1.20
    bp_acceptance_window_bars: int = 2
    bp_pullback_max_bars: int = 3
    bp_pullback_tolerance_atr: float = 0.35
    bp_pullback_max_depth_atr: float = 2.20
    bp_pullback_min_depth_atr: float = 0.05
    bp_pullback_volume_ratio_max: float = 0.95
    bp_relaunch_body_ratio_min: float = 0.35
    bp_relaunch_volume_recovery_min: float = 1.00
    bp_stop_buffer_atr: float = 0.10
    bp_min_target_r: float = 1.20
    bp_min_target_space_atr: float = 0.20
    bp_min_cost_adjusted_rr: float = 0.00
    bp_max_cost_per_r: float = 999.00
    bp_min_breakout_score: float = 0.45
    bp_min_relaunch_score: float = 0.35
    bp_variant_policy: str = "level_retest"
    bp_subtype_focus: str = "any"
    mrt_squeeze_filter_enabled: bool = True
    zone_first_touch_weight: float = 0.50
    breakout_absorption_volume_ratio: float = 3.0
    breakout_absorption_body_ratio_max: float = 0.40
    pullback_no_supply_volume_ratio_max: float = 0.80
    sweep_max_atr_multiple: float = 1.5
    sweep_wick_ratio_min: float = 0.25
    sweep_rvol_min: float = 1.5
    countertrend_sweep_rvol_min: float = 2.0
    reclaim_max_bars: int = 5
    reclaim_rvol_max: float = math.inf
    require_choch_for_eth_reversal: bool = False
    require_choch_for_countertrend: bool = False
    invalidation_mode: str = "atr_buffer"
    invalidation_buffer_atr: float = 1.0


def build_market_regime(candles: Sequence[object]) -> MarketRegimeContext | None:
    confirmed = _confirmed_candles(candles)
    if len(confirmed) < 201:
        return None

    highs = [float(candle.high) for candle in confirmed]
    lows = [float(candle.low) for candle in confirmed]
    closes = [float(candle.close) for candle in confirmed]

    fast_ema = exponential_moving_average(closes, 50)
    slow_ema = exponential_moving_average(closes, 200)
    atr = average_true_range(highs, lows, closes, 14)
    efficiency_ratio = kaufman_efficiency_ratio(closes[-15:])
    choppiness = choppiness_index(highs, lows, closes, 14)
    dmi = directional_movement_index(highs, lows, closes, 14)
    squeeze = ttm_squeeze_on(highs, lows, closes, 20)

    ema_direction = "long" if fast_ema > slow_ema else "short" if fast_ema < slow_ema else None
    dmi_direction = "long" if dmi.plus_di > dmi.minus_di else "short" if dmi.minus_di > dmi.plus_di else None
    direction = ema_direction if ema_direction == dmi_direction else ema_direction
    trend_ready = (
        direction is not None
        and dmi.adx >= 25.0
        and efficiency_ratio >= 0.6
        and choppiness <= 38.2
        and abs(fast_ema - slow_ema) >= max(atr * 0.1, 0.0)
    )

    if trend_ready and atr > 0 and abs(closes[-1] - fast_ema) >= atr * 20.0:
        status = "OVERHEATED_TREND_END"
    elif trend_ready:
        status = "TREND"
    elif squeeze:
        status = "COMPRESSION_PENDING_BREAKOUT"
    elif efficiency_ratio <= 0.3 and choppiness >= 61.8:
        status = "RANGE"
    else:
        status = "MEAN_REVERTING_TRANSITION"

    evidence = {
        "status": status,
        "direction": direction,
        "last_close": closes[-1],
        "fast_ema": fast_ema,
        "slow_ema": slow_ema,
        "atr": atr,
        "efficiency_ratio": efficiency_ratio,
        "choppiness": choppiness,
        "dmi_plus": dmi.plus_di,
        "dmi_minus": dmi.minus_di,
        "adx": dmi.adx,
        "ttm_squeeze": squeeze,
        "confirmed_candle_count": len(confirmed),
    }
    return MarketRegimeContext(
        status=status,
        direction=direction,
        last_close=closes[-1],
        fast_ema=fast_ema,
        slow_ema=slow_ema,
        atr=atr,
        efficiency_ratio=efficiency_ratio,
        choppiness=choppiness,
        dmi_plus=dmi.plus_di,
        dmi_minus=dmi.minus_di,
        adx=dmi.adx,
        ttm_squeeze=squeeze,
        evidence=evidence,
    )


def detect_price_action_setup(
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    regime: MarketRegimeContext | None,
    parameters: StrategyParameters | None = None,
    context_features: Mapping[str, Any] | None = None,
) -> PriceActionSetup | None:
    structure = _confirmed_candles(structure_candles)
    entry = _confirmed_candles(entry_candles)
    if regime is None or len(structure) < 5 or not entry:
        return None

    params = parameters or StrategyParameters()
    trend_continuation = _detect_trend_continuation(structure, entry, regime, params, context_features)
    if trend_continuation is not None:
        return trend_continuation

    return _detect_liquidity_reversal(structure, entry, regime, params, context_features)


def confirm_volume_price(
    entry_candles: Sequence[object],
    direction: str,
    context_features: Mapping[str, Any] | None = None,
) -> VolumePriceConfirmation:
    confirmed = _confirmed_candles(entry_candles)
    if len(confirmed) < 2:
        return _volume_result("cooldown", {"reason": "insufficient_confirmed_candles"})

    latest = confirmed[-1]
    use_tod_dow = _volume_config(context_features).get("baseline_mode") == "tod_dow_log_ewma"
    history = confirmed[:-1] if use_tod_dow else confirmed[-21:-1] if len(confirmed) >= 21 else confirmed[:-1]
    latest_volume = _candle_volume(latest)
    volume_baseline = _volume_baseline(history, context_features, anchor=latest, current_volume=latest_volume)
    average_volume = volume_baseline["average_volume"]
    volume_source = str(volume_baseline["volume_source"])
    if average_volume <= 0:
        return _volume_result("anomaly", {"reason": "non_positive_average_volume", "latest_volume": latest_volume})

    volume_ratio = latest_volume / average_volume
    if volume_ratio >= 6.0:
        status = "anomaly"
    elif volume_ratio < 0.8:
        status = "reject"
    elif volume_ratio < 1.5:
        status = "cooldown"
    else:
        status = "confirm" if _price_accepts_direction(latest, direction) else "cooldown"

    evidence = {
        "latest_volume": latest_volume,
        "average_volume": average_volume,
        "volume_ratio": volume_ratio,
        "volume_source": volume_source,
        "price_state": _price_state(latest),
        **volume_baseline,
    }
    if context_features and "ttm_squeeze_on" in context_features:
        evidence["ttm_squeeze_on"] = bool(context_features["ttm_squeeze_on"])
    return _volume_result(status, evidence)


def evaluate_trend_continuation_diagnostics(
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    regime: MarketRegimeContext | None,
    parameters: StrategyParameters | None = None,
    context_features: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    structure = _confirmed_candles(structure_candles)
    entry = _confirmed_candles(entry_candles)
    params = parameters or strategy_parameters_from_context(context_features)
    stages: dict[str, dict[str, Any]] = {}
    metrics: dict[str, Any] = {}

    def add_stage(name: str, passed: bool, **evidence: Any) -> None:
        stages[name] = {"passed": bool(passed), **evidence}

    window_ready = regime is not None and len(structure) >= 6 and len(entry) >= 2
    add_stage(
        "window_ready",
        window_ready,
        structure_count=len(structure),
        entry_count=len(entry),
        regime_present=regime is not None,
    )
    if not window_ready:
        return _trend_diagnostic_result(stages, metrics)

    trend_gate = _trend_gate_passes(regime, params, context_features)
    add_stage(
        "trend_gate",
        trend_gate,
        regime_status=regime.status,
        regime_direction=regime.direction,
        fast_ema=regime.fast_ema,
        slow_ema=regime.slow_ema,
        atr=regime.atr,
        efficiency_ratio=regime.efficiency_ratio,
        choppiness=regime.choppiness,
        dmi_plus=regime.dmi_plus,
        dmi_minus=regime.dmi_minus,
        adx=regime.adx,
        ttm_squeeze=regime.ttm_squeeze,
        trend_gate_policy=params.trend_gate_policy,
    )
    if not trend_gate:
        return _trend_diagnostic_result(stages, metrics)

    direction = str(regime.direction)
    prior = structure[:-2]
    breakout = structure[-2]
    pullback = structure[-1]
    average_range = _average_range(structure[:-1])
    atr = regime.atr if regime.atr > 0 else average_range
    baseline_evidence = _volume_baseline(prior, context_features, anchor=breakout, current_volume=_candle_volume(breakout))
    volume_baseline = baseline_evidence["average_volume"]
    metrics.update(
        {
            "direction": direction,
            "average_range": average_range,
            "atr": atr,
            "volume_baseline": volume_baseline,
            "volume_baseline_mode": baseline_evidence.get("volume_baseline_mode"),
            "volume_source": baseline_evidence.get("volume_source"),
            "volume_bucket_key": baseline_evidence.get("volume_bucket_key"),
            "volume_bucket_sample_count": baseline_evidence.get("volume_bucket_sample_count"),
            "used_fallback_volume_baseline": baseline_evidence.get("used_fallback_volume_baseline"),
            "breakout_timestamp_ms": getattr(breakout, "timestamp_ms", None),
            "pullback_timestamp_ms": getattr(pullback, "timestamp_ms", None),
        }
    )
    baseline_ok = average_range > 0 and volume_baseline > 0
    add_stage(
        "volume_baseline_available",
        baseline_ok,
        average_range=average_range,
        volume_baseline=volume_baseline,
        volume_baseline_mode=baseline_evidence.get("volume_baseline_mode"),
        volume_bucket_sample_count=baseline_evidence.get("volume_bucket_sample_count"),
    )
    if not baseline_ok:
        return _trend_diagnostic_result(stages, metrics)

    breakout_rvol = _candle_volume(breakout) / volume_baseline
    pullback_rvol = _candle_volume(pullback) / volume_baseline
    metrics.update({"breakout_rvol": breakout_rvol, "pullback_rvol": pullback_rvol})
    add_stage(
        "breakout_rvol",
        breakout_rvol >= params.breakout_rvol_min,
        value=breakout_rvol,
        threshold=params.breakout_rvol_min,
        distance_to_threshold=breakout_rvol - params.breakout_rvol_min,
    )
    if breakout_rvol < params.breakout_rvol_min:
        return _trend_diagnostic_result(stages, metrics)
    add_stage(
        "pullback_rvol",
        pullback_rvol <= params.pullback_rvol_max,
        value=pullback_rvol,
        threshold=params.pullback_rvol_max,
        distance_to_threshold=params.pullback_rvol_max - pullback_rvol,
    )
    if pullback_rvol > params.pullback_rvol_max:
        return _trend_diagnostic_result(stages, metrics)

    body = abs(float(breakout.close) - float(breakout.open))
    breakout_range = float(breakout.high) - float(breakout.low)
    range_ok = breakout_range > 0
    add_stage("displacement_range", range_ok, breakout_range=breakout_range)
    if not range_ok:
        return _trend_diagnostic_result(stages, metrics)

    body_ratio = body / breakout_range
    metrics["breakout_body_ratio"] = body_ratio
    add_stage(
        "displacement_body",
        body_ratio >= params.breakout_body_ratio_min,
        value=body_ratio,
        threshold=params.breakout_body_ratio_min,
        distance_to_threshold=body_ratio - params.breakout_body_ratio_min,
    )
    if body_ratio < params.breakout_body_ratio_min:
        return _trend_diagnostic_result(stages, metrics)

    if direction == "long":
        prior_level = max(float(candle.high) for candle in prior)
        close_location = (float(breakout.high) - float(breakout.close)) / breakout_range
        breakout_midpoint = (float(breakout.open) + float(breakout.close)) / 2.0
        bos_distance = float(breakout.close) - (prior_level + atr * params.breakout_buffer_atr)
        has_bos = bos_distance > 0
        pullback_direction = float(pullback.close) < float(breakout.close)
        midpoint_distance = min(float(pullback.low) - breakout_midpoint, float(pullback.close) - prior_level)
        pullback_holds_midpoint = midpoint_distance >= 0
    else:
        prior_level = min(float(candle.low) for candle in prior)
        close_location = (float(breakout.close) - float(breakout.low)) / breakout_range
        breakout_midpoint = (float(breakout.open) + float(breakout.close)) / 2.0
        bos_distance = (prior_level - atr * params.breakout_buffer_atr) - float(breakout.close)
        has_bos = bos_distance > 0
        pullback_direction = float(pullback.close) > float(breakout.close)
        midpoint_distance = min(breakout_midpoint - float(pullback.high), prior_level - float(pullback.close))
        pullback_holds_midpoint = midpoint_distance >= 0

    metrics.update(
        {
            "prior_structure_level": prior_level,
            "breakout_close_location": close_location,
            "breakout_midpoint": breakout_midpoint,
            "bos_distance": bos_distance,
            "pullback_midpoint_distance": midpoint_distance,
        }
    )
    add_stage(
        "BOS",
        has_bos,
        distance_to_threshold=bos_distance,
        breakout_buffer_atr=params.breakout_buffer_atr,
        prior_structure_level=prior_level,
    )
    if not has_bos:
        return _trend_diagnostic_result(stages, metrics)
    add_stage(
        "close_location",
        close_location <= params.breakout_close_location_max,
        value=close_location,
        threshold=params.breakout_close_location_max,
        distance_to_threshold=params.breakout_close_location_max - close_location,
    )
    if close_location > params.breakout_close_location_max:
        return _trend_diagnostic_result(stages, metrics)
    add_stage("pullback_direction", pullback_direction)
    if not pullback_direction:
        return _trend_diagnostic_result(stages, metrics)
    add_stage(
        "pullback_midpoint",
        pullback_holds_midpoint,
        distance_to_threshold=midpoint_distance,
        breakout_midpoint=breakout_midpoint,
    )
    if not pullback_holds_midpoint:
        return _trend_diagnostic_result(stages, metrics)

    restart = _restart_diagnostics(entry, direction, params)
    metrics.update(
        {
            "restart_rvol": restart["latest_rvol"],
            "restart_price_break_distance": restart["price_break_distance"],
        }
    )
    add_stage("restart_price", bool(restart["price_passed"]), distance_to_threshold=restart["price_break_distance"])
    if not restart["price_passed"]:
        return _trend_diagnostic_result(stages, metrics)
    add_stage(
        "restart_rvol",
        bool(restart["rvol_passed"]),
        value=restart["latest_rvol"],
        threshold=params.restart_rvol_min,
        distance_to_threshold=float(restart["latest_rvol"]) - params.restart_rvol_min,
    )
    if not restart["rvol_passed"]:
        return _trend_diagnostic_result(stages, metrics)

    confirmation = confirm_volume_price(entry, direction, context_features=context_features)
    metrics.update(
        {
            "entry_volume_status": confirmation.status,
            "entry_volume_ratio": confirmation.evidence.get("volume_ratio"),
            "entry_volume_baseline_mode": confirmation.evidence.get("volume_baseline_mode"),
            "entry_volume_bucket_sample_count": confirmation.evidence.get("volume_bucket_sample_count"),
            "entry_used_fallback_volume_baseline": confirmation.evidence.get("used_fallback_volume_baseline"),
        }
    )
    confirmation_evidence = dict(confirmation.evidence)
    confirmation_evidence["volume_status"] = confirmation.status
    add_stage("entry_volume_confirmation", confirmation.status == "confirm", **confirmation_evidence)
    return _trend_diagnostic_result(stages, metrics)


def evaluate_compression_expansion_diagnostics(
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    regime: MarketRegimeContext | None,
    parameters: StrategyParameters | None = None,
    context_features: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    structure = _confirmed_candles(structure_candles)
    entry = _confirmed_candles(entry_candles)
    params = parameters or strategy_parameters_from_context(context_features)
    stages: dict[str, dict[str, Any]] = {}
    metrics: dict[str, Any] = {}

    def add_stage(name: str, passed: bool, **evidence: Any) -> None:
        stages[name] = {"passed": bool(passed), **evidence}

    lookback = max(4, int(params.compression_lookback_bars))
    window_ready = len(structure) >= lookback + 2 and len(entry) >= 1
    add_stage(
        "window_ready",
        window_ready,
        structure_count=len(structure),
        entry_count=len(entry),
        lookback_bars=lookback,
        regime_status=None if regime is None else regime.status,
        regime_direction=None if regime is None else regime.direction,
    )
    if not window_ready:
        return _trend_diagnostic_result(stages, metrics)

    semantic_v2 = params.compression_breakout_semantic_policy == "semantic_v2"
    acceptance_window_limit = max(1, min(3, int(params.compression_acceptance_window_bars)))
    selected_breakout_index = len(structure) - 2
    if semantic_v2:
        selected_breakout_index = _select_compression_breakout_index(
            structure,
            lookback=lookback,
            acceptance_window_limit=acceptance_window_limit,
            params=params,
            regime=regime,
        )
    compression = structure[selected_breakout_index - lookback:selected_breakout_index]
    breakout = structure[selected_breakout_index]
    acceptance_window = structure[selected_breakout_index + 1 :]
    confirmation = acceptance_window[-1] if acceptance_window else structure[-1]
    atr = float(regime.atr) if regime is not None and float(regime.atr) > 0 else _average_range(structure)
    compression_high = max(float(candle.high) for candle in compression)
    compression_low = min(float(candle.low) for candle in compression)
    box_height = compression_high - compression_low
    compression_ranges = [float(candle.high) - float(candle.low) for candle in compression]
    avg_compression_range = sum(compression_ranges) / len(compression_ranges)
    compression_detected = box_height > 0 and atr > 0
    metrics.update(
        {
            "compression_start_time": getattr(compression[0], "timestamp_ms", None),
            "compression_end_time": getattr(compression[-1], "timestamp_ms", None),
            "breakout_time": getattr(breakout, "timestamp_ms", None),
            "confirmation_time": getattr(confirmation, "timestamp_ms", None),
            "acceptance_window_bars": len(acceptance_window),
            "compression_high": compression_high,
            "compression_low": compression_low,
            "compression_midpoint": (compression_high + compression_low) / 2.0,
            "compression_box_height": box_height,
            "compression_avg_range": avg_compression_range,
            "atr": atr,
            "compression_box_atr": box_height / atr if atr > 0 else None,
            "compression_avg_range_atr": avg_compression_range / atr if atr > 0 else None,
        }
    )
    add_stage(
        "compression_detected",
        compression_detected,
        compression_high=compression_high,
        compression_low=compression_low,
        box_height=box_height,
        atr=atr,
    )
    if not compression_detected:
        return _trend_diagnostic_result(stages, metrics)

    box_atr = box_height / atr
    avg_range_atr = avg_compression_range / atr
    quality_valid = (
        box_atr >= params.compression_box_atr_min
        and box_atr <= params.compression_box_atr_max
        and avg_range_atr <= params.compression_avg_range_atr_max
    )
    add_stage(
        "compression_quality_valid",
        quality_valid,
        box_atr=box_atr,
        box_atr_min_threshold=params.compression_box_atr_min,
        box_atr_threshold=params.compression_box_atr_max,
        avg_range_atr=avg_range_atr,
        avg_range_atr_threshold=params.compression_avg_range_atr_max,
    )
    if not quality_valid:
        return _trend_diagnostic_result(stages, metrics)

    breakout_buffer = atr * params.compression_breakout_buffer_atr
    breakout_close = float(breakout.close)
    if breakout_close > compression_high + breakout_buffer:
        direction = "long"
        breakout_distance = breakout_close - (compression_high + breakout_buffer)
    elif breakout_close < compression_low - breakout_buffer:
        direction = "short"
        breakout_distance = (compression_low - breakout_buffer) - breakout_close
    else:
        direction = ""
        breakout_distance = 0.0
    metrics.update({"direction": direction, "breakout_distance": breakout_distance, "breakout_buffer": breakout_buffer})
    add_stage(
        "breakout_detected",
        direction in {"long", "short"},
        direction=direction,
        breakout_close=breakout_close,
        breakout_buffer=breakout_buffer,
        distance_to_threshold=breakout_distance,
    )
    if direction not in {"long", "short"}:
        return _trend_diagnostic_result(stages, metrics)

    breakout_range = float(breakout.high) - float(breakout.low)
    breakout_body = abs(float(breakout.close) - float(breakout.open))
    avg_body = sum(abs(float(candle.close) - float(candle.open)) for candle in compression) / len(compression)
    body_ratio = 0.0 if breakout_range <= 0 else breakout_body / breakout_range
    if direction == "long":
        close_location = 0.0 if breakout_range <= 0 else (float(breakout.close) - float(breakout.low)) / breakout_range
        close_outside_box_distance = max(0.0, breakout_close - compression_high)
    else:
        close_location = 0.0 if breakout_range <= 0 else (float(breakout.high) - float(breakout.close)) / breakout_range
        close_outside_box_distance = max(0.0, compression_low - breakout_close)
    breakout_displacement_atr = breakout_range / atr if atr > 0 else None
    breakout_displacement_box_ratio = breakout_range / box_height if box_height > 0 else None
    range_expansion = breakout_range / avg_compression_range if avg_compression_range > 0 else None
    body_expansion = breakout_body / avg_body if avg_body > 0 else None
    close_outside_atr = close_outside_box_distance / atr if atr > 0 else None
    breakout_score_seed = _compression_breakout_score(
        displacement_atr=breakout_displacement_atr,
        displacement_box_ratio=breakout_displacement_box_ratio,
        close_location=close_location,
        body_ratio=body_ratio,
        close_outside_atr=close_outside_atr,
        volume_expansion=None,
        range_expansion=range_expansion,
        body_expansion=body_expansion,
    )
    displacement_valid = (
        breakout_range > 0
        and body_ratio >= params.compression_breakout_body_ratio_min
        and (close_outside_atr is None or close_outside_atr >= params.compression_min_close_outside_box_atr)
        and breakout_score_seed >= params.compression_min_breakout_score
    )
    metrics.update(
        {
            "breakout_range": breakout_range,
            "breakout_displacement_atr": breakout_displacement_atr,
            "breakout_displacement_ATR": breakout_displacement_atr,
            "breakout_displacement_box_ratio": breakout_displacement_box_ratio,
            "breakout_body_ratio": body_ratio,
            "breakout_body_pct": body_ratio,
            "breakout_close_location": close_location,
            "breakout_range_vs_ATR": breakout_displacement_atr,
            "breakout_range_vs_box_height": breakout_displacement_box_ratio,
            "close_outside_box_distance_ATR": close_outside_atr,
            "range_expansion_vs_compression": range_expansion,
            "body_expansion_vs_compression": body_expansion,
            "breakout_score": breakout_score_seed,
        }
    )
    add_stage(
        "breakout_displacement_valid",
        displacement_valid,
        value=body_ratio,
        threshold=params.compression_breakout_body_ratio_min,
        distance_to_threshold=min(
            body_ratio - params.compression_breakout_body_ratio_min,
            (close_outside_atr or 0.0) - params.compression_min_close_outside_box_atr,
            breakout_score_seed - params.compression_min_breakout_score,
        ),
        breakout_score=breakout_score_seed,
        min_breakout_score=params.compression_min_breakout_score,
    )
    if not displacement_valid:
        primary, secondary = _compression_failure_taxonomy(metrics, "breakout_displacement_valid")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary, "ce_subtype": "ambiguous"})
        return _trend_diagnostic_result(stages, metrics)

    baseline_evidence = _volume_baseline(
        compression,
        context_features,
        anchor=breakout,
        current_volume=_candle_volume(breakout),
    )
    volume_baseline = baseline_evidence["average_volume"]
    breakout_rvol = _candle_volume(breakout) / volume_baseline if volume_baseline > 0 else 0.0
    volume_z = _z_score(_candle_volume(breakout), [_candle_volume(candle) for candle in compression])
    breakout_score = _compression_breakout_score(
        displacement_atr=breakout_displacement_atr,
        displacement_box_ratio=breakout_displacement_box_ratio,
        close_location=close_location,
        body_ratio=body_ratio,
        close_outside_atr=close_outside_atr,
        volume_expansion=breakout_rvol,
        range_expansion=range_expansion,
        body_expansion=body_expansion,
    )
    volume_valid = breakout_rvol >= params.compression_breakout_rvol_min
    metrics.update(
        {
            "volume_baseline": volume_baseline,
            "breakout_rvol": breakout_rvol,
            "breakout_RVOL": breakout_rvol,
            "breakout_volume_z": volume_z,
            "volume_expansion_vs_compression": breakout_rvol,
            "breakout_score": breakout_score,
            "volume_baseline_mode": baseline_evidence.get("volume_baseline_mode"),
            "volume_bucket_sample_count": baseline_evidence.get("volume_bucket_sample_count"),
            "used_fallback_volume_baseline": baseline_evidence.get("used_fallback_volume_baseline"),
        }
    )
    add_stage(
        "breakout_volume_valid",
        volume_valid,
        value=breakout_rvol,
        threshold=params.compression_breakout_rvol_min,
        distance_to_threshold=breakout_rvol - params.compression_breakout_rvol_min,
        volume_baseline=volume_baseline,
    )
    if not volume_valid:
        primary, secondary = _compression_failure_taxonomy(metrics, "breakout_volume_valid")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary, "ce_subtype": "ambiguous"})
        return _trend_diagnostic_result(stages, metrics)

    breakout_midpoint = (float(breakout.open) + float(breakout.close)) / 2.0
    acceptance = _compression_acceptance_metrics(
        direction=direction,
        compression_high=compression_high,
        compression_low=compression_low,
        compression_midpoint=(compression_high + compression_low) / 2.0,
        breakout=breakout,
        acceptance_window=acceptance_window,
        atr=atr,
        tolerance_atr=params.compression_retest_tolerance_atr,
    )
    confirmation_close = float(confirmation.close)
    failed_breakout_absent = not bool(acceptance["close_back_inside_box"])
    midpoint_distance = float(acceptance["midpoint_distance"])
    retest_distance = float(acceptance["boundary_distance"])
    continuation_distance = float(acceptance["continuation_distance"])
    midpoint_hold = bool(acceptance["midpoint_hold_after_breakout"])
    boundary_hold = bool(acceptance["boundary_hold_after_breakout"])
    retest_hold = boundary_hold
    if params.compression_hold_policy == "midpoint_or_boundary":
        hold_passed = midpoint_hold or retest_hold
    else:
        hold_passed = midpoint_hold and retest_hold
    metrics.update(
        {
            "breakout_midpoint": breakout_midpoint,
            "midpoint_hold": midpoint_hold,
            "boundary_hold": boundary_hold,
            "retest_hold": retest_hold,
            "continuation_distance": continuation_distance,
            **acceptance,
        }
    )
    add_stage("failed_breakout_absent", failed_breakout_absent, confirmation_close=confirmation_close)
    if not failed_breakout_absent:
        primary, secondary = _compression_failure_taxonomy(metrics, "failed_breakout_absent")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary, "ce_subtype": "ambiguous"})
        return _trend_diagnostic_result(stages, metrics)
    add_stage("midpoint_hold", hold_passed if params.compression_hold_policy == "midpoint_or_boundary" else midpoint_hold, distance_to_threshold=midpoint_distance, hold_policy=params.compression_hold_policy)
    if not bool(stages["midpoint_hold"]["passed"]):
        primary, secondary = _compression_failure_taxonomy(metrics, "midpoint_hold")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary, "ce_subtype": "ambiguous"})
        return _trend_diagnostic_result(stages, metrics)
    add_stage("retest_hold", hold_passed if params.compression_hold_policy == "midpoint_or_boundary" else retest_hold, distance_to_threshold=retest_distance, tolerance_atr=params.compression_retest_tolerance_atr)
    if not bool(stages["retest_hold"]["passed"]):
        primary, secondary = _compression_failure_taxonomy(metrics, "retest_hold")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary, "ce_subtype": "ambiguous"})
        return _trend_diagnostic_result(stages, metrics)
    add_stage("continuation_ready", continuation_distance > 0, distance_to_threshold=continuation_distance)
    if continuation_distance <= 0:
        primary, secondary = _compression_failure_taxonomy(metrics, "continuation_ready")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary, "ce_subtype": "ambiguous"})
        return _trend_diagnostic_result(stages, metrics)
    ce_subtype = _compression_subtype(metrics)
    subtype_focus = params.compression_subtype_focus
    if subtype_focus != "any" and ce_subtype != subtype_focus:
        metrics.update(
            {
                "ce_subtype": ce_subtype,
                "primary_failure_reason": "ambiguous" if ce_subtype == "ambiguous" else "subtype_not_selected",
                "secondary_failure_reasons": [],
            }
        )
        add_stage("subtype_selected", False, ce_subtype=ce_subtype, subtype_focus=subtype_focus)
        return _trend_diagnostic_result(stages, metrics)
    metrics.update({"ce_subtype": ce_subtype, "primary_failure_reason": "", "secondary_failure_reasons": []})

    entry_policy = params.compression_entry_policy
    entry_reference = confirmation_close
    entry_reference_time = getattr(confirmation, "timestamp", None)
    if entry_reference_time is None:
        entry_reference_time = getattr(confirmation, "timestamp_ms", None)
    if entry_policy == "acceptance_retest_close":
        retest_entry_candle = acceptance_window[-1] if acceptance_window else confirmation
        entry_reference = float(retest_entry_candle.close)
        retest_entry_time = getattr(retest_entry_candle, "timestamp", None)
        if retest_entry_time is None:
            retest_entry_time = getattr(retest_entry_candle, "timestamp_ms", None)
        entry_reference_time = retest_entry_time
    else:
        entry_policy = "confirmation_close"
    stop_anchor_type = params.compression_stop_policy
    stop_buffer = atr * params.compression_stop_buffer_atr
    if direction == "long":
        if params.compression_stop_policy in {"opposite_edge_atr_buffer", "opposite_edge_structural_stop"}:
            stop = compression_low - stop_buffer
            stop_anchor_type = "opposite_edge_structural_stop"
        elif params.compression_stop_policy in {"breakout_candle_extreme_atr_buffer", "breakout_extreme_structural_stop"}:
            stop = float(breakout.low) - stop_buffer
            stop_anchor_type = "breakout_extreme_structural_stop"
        elif params.compression_stop_policy == "acceptance_retest_structural_stop":
            retest_low = float(acceptance.get("acceptance_retest_low") or compression_high)
            stop = min(retest_low, compression_high, (compression_high + compression_low) / 2.0) - stop_buffer
            stop_anchor_type = "acceptance_retest_structural_stop"
        else:
            stop = min(compression_high, breakout_midpoint)
            stop_anchor_type = "breakout_midpoint_or_box_edge"
        target = entry_reference + max(box_height, abs(entry_reference - stop) * 2.0)
    else:
        if params.compression_stop_policy in {"opposite_edge_atr_buffer", "opposite_edge_structural_stop"}:
            stop = compression_high + stop_buffer
            stop_anchor_type = "opposite_edge_structural_stop"
        elif params.compression_stop_policy in {"breakout_candle_extreme_atr_buffer", "breakout_extreme_structural_stop"}:
            stop = float(breakout.high) + stop_buffer
            stop_anchor_type = "breakout_extreme_structural_stop"
        elif params.compression_stop_policy == "acceptance_retest_structural_stop":
            retest_high = float(acceptance.get("acceptance_retest_high") or compression_low)
            stop = max(retest_high, compression_low, (compression_high + compression_low) / 2.0) + stop_buffer
            stop_anchor_type = "acceptance_retest_structural_stop"
        else:
            stop = max(compression_low, breakout_midpoint)
            stop_anchor_type = "breakout_midpoint_or_box_edge"
        target = entry_reference - max(box_height, abs(stop - entry_reference) * 2.0)
    stop_distance = abs(entry_reference - stop)
    target_space = abs(target - entry_reference)
    target_r = 0.0 if stop_distance <= 0 else abs(target - entry_reference) / stop_distance
    stop_inside_box = compression_low <= stop <= compression_high
    metrics.update(
        {
            "entry_reference_price": entry_reference,
            "entry_policy": entry_policy,
            "entry_reference_time": entry_reference_time.isoformat() if hasattr(entry_reference_time, "isoformat") else entry_reference_time,
            "stop_price": stop,
            "target_price": target,
            "target_r": target_r,
            "entry_to_stop": stop_distance,
            "stop_distance_atr": stop_distance / atr if atr > 0 else None,
            "stop_distance_ATR": stop_distance / atr if atr > 0 else None,
            "stop_distance_box_ratio": stop_distance / box_height if box_height > 0 else None,
            "stop_anchor_type": stop_anchor_type,
            "stop_buffer_atr": params.compression_stop_buffer_atr if stop_anchor_type != "breakout_midpoint_or_box_edge" else 0.0,
            "stop_inside_box": stop_inside_box,
            "target_space": target_space,
            "target_space_atr": target_space / atr if atr > 0 else None,
            "gross_RR": target_r,
        }
    )
    add_stage(
        "risk_precheck_pass",
        stop_distance > 0 and target_r >= params.compression_min_target_r,
        stop_distance=stop_distance,
        target_r=target_r,
        min_target_r=params.compression_min_target_r,
    )
    return _trend_diagnostic_result(stages, metrics)


def _select_compression_breakout_index(
    structure: Sequence[object],
    *,
    lookback: int,
    acceptance_window_limit: int,
    params: StrategyParameters,
    regime: MarketRegimeContext | None,
) -> int:
    atr = float(regime.atr) if regime is not None and float(regime.atr) > 0 else _average_range(structure)
    default_index = max(lookback, len(structure) - 2)
    best_index = default_index
    best_score = -1.0
    start = max(lookback, len(structure) - acceptance_window_limit - 1)
    stop = max(start, len(structure) - 1)
    for index in range(start, stop):
        compression = structure[index - lookback:index]
        if not compression:
            continue
        high = max(float(candle.high) for candle in compression)
        low = min(float(candle.low) for candle in compression)
        box_height = high - low
        if box_height <= 0 or atr <= 0:
            continue
        breakout = structure[index]
        close = float(breakout.close)
        buffer = atr * params.compression_breakout_buffer_atr
        if close > high + buffer:
            outside = close - high
        elif close < low - buffer:
            outside = low - close
        else:
            continue
        breakout_range = float(breakout.high) - float(breakout.low)
        body = abs(float(breakout.close) - float(breakout.open))
        score = _compression_breakout_score(
            displacement_atr=breakout_range / atr if atr > 0 else None,
            displacement_box_ratio=breakout_range / box_height if box_height > 0 else None,
            close_location=1.0,
            body_ratio=body / breakout_range if breakout_range > 0 else 0.0,
            close_outside_atr=outside / atr if atr > 0 else None,
            volume_expansion=None,
            range_expansion=None,
            body_expansion=None,
        )
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def _compression_breakout_score(
    *,
    displacement_atr: float | None,
    displacement_box_ratio: float | None,
    close_location: float | None,
    body_ratio: float | None,
    close_outside_atr: float | None,
    volume_expansion: float | None,
    range_expansion: float | None,
    body_expansion: float | None,
) -> float:
    parts = [
        _cap_ratio(displacement_atr, 1.5),
        _cap_ratio(displacement_box_ratio, 2.0),
        _cap_ratio(close_location, 0.9),
        _cap_ratio(body_ratio, 0.75),
        _cap_ratio(close_outside_atr, 0.5),
        _cap_ratio(volume_expansion, 2.0),
        _cap_ratio(range_expansion, 2.0),
        _cap_ratio(body_expansion, 2.0),
    ]
    clean = [value for value in parts if value is not None]
    return 0.0 if not clean else sum(clean) / len(clean)


def _cap_ratio(value: float | None, target: float) -> float | None:
    if value is None or target <= 0:
        return None
    return max(0.0, min(1.0, float(value) / target))


def _z_score(value: float, sample: Sequence[float]) -> float | None:
    clean = [float(item) for item in sample if math.isfinite(float(item))]
    if len(clean) < 2:
        return None
    avg = sum(clean) / len(clean)
    variance = sum((item - avg) ** 2 for item in clean) / len(clean)
    std = math.sqrt(variance)
    if std <= 0:
        return 0.0
    return (float(value) - avg) / std


def _compression_acceptance_metrics(
    *,
    direction: str,
    compression_high: float,
    compression_low: float,
    compression_midpoint: float,
    breakout: object,
    acceptance_window: Sequence[object],
    atr: float,
    tolerance_atr: float,
) -> dict[str, Any]:
    window = tuple(acceptance_window) or (breakout,)
    breakout_level = compression_high if direction == "long" else compression_low
    breakout_close = float(breakout.close)
    close_back_index: int | None = None
    followthrough = 0
    wick_back_close_hold = False
    high_volume_no_result = False
    if direction == "long":
        close_back = lambda candle: float(candle.close) <= compression_high
        close_beyond_breakout = lambda candle: float(candle.close) < breakout_level
        midpoint_lost = any(float(candle.close) < compression_midpoint for candle in window)
        boundary_hold = not any(float(candle.close) < compression_high for candle in window)
        midpoint_hold = not midpoint_lost
        for offset, candle in enumerate(window, start=1):
            if close_back(candle) and close_back_index is None:
                close_back_index = offset
            if float(candle.low) <= compression_high and float(candle.close) > compression_high:
                wick_back_close_hold = True
            if float(candle.close) > breakout_close:
                followthrough += 1
        retest_depth = max(0.0, compression_high - min(float(candle.low) for candle in window)) / atr if atr > 0 else None
        continuation_distance = float(window[-1].close) - compression_high
        midpoint_distance = min(float(candle.close) for candle in window) - compression_midpoint
        boundary_distance = min(float(candle.close) for candle in window) - (compression_high - atr * tolerance_atr)
        mfe = max(float(candle.high) - breakout_close for candle in window)
        mae = max(breakout_close - float(candle.low) for candle in window)
        retest_low = min(float(candle.low) for candle in window)
        retest_high = max(float(candle.high) for candle in window)
    else:
        close_back = lambda candle: float(candle.close) >= compression_low
        close_beyond_breakout = lambda candle: float(candle.close) > breakout_level
        midpoint_lost = any(float(candle.close) > compression_midpoint for candle in window)
        boundary_hold = not any(float(candle.close) > compression_low for candle in window)
        midpoint_hold = not midpoint_lost
        for offset, candle in enumerate(window, start=1):
            if close_back(candle) and close_back_index is None:
                close_back_index = offset
            if float(candle.high) >= compression_low and float(candle.close) < compression_low:
                wick_back_close_hold = True
            if float(candle.close) < breakout_close:
                followthrough += 1
        retest_depth = max(0.0, max(float(candle.high) for candle in window) - compression_low) / atr if atr > 0 else None
        continuation_distance = compression_low - float(window[-1].close)
        midpoint_distance = compression_midpoint - max(float(candle.close) for candle in window)
        boundary_distance = (compression_low + atr * tolerance_atr) - max(float(candle.close) for candle in window)
        mfe = max(breakout_close - float(candle.low) for candle in window)
        mae = max(float(candle.high) - breakout_close for candle in window)
        retest_low = min(float(candle.low) for candle in window)
        retest_high = max(float(candle.high) for candle in window)
    close_beyond = any(close_beyond_breakout(candle) for candle in window)
    ranges = [float(candle.high) - float(candle.low) for candle in window]
    bodies = [abs(float(candle.close) - float(candle.open)) for candle in window]
    if ranges and max(bodies or [0.0]) <= max(ranges) * 0.25 and followthrough == 0:
        high_volume_no_result = True
    return {
        "close_back_inside_box": close_back_index is not None,
        "close_back_inside_box_bar_index": close_back_index,
        "close_below_breakout_level": close_beyond if direction == "long" else False,
        "close_above_breakout_level": close_beyond if direction == "short" else False,
        "midpoint_lost_after_breakout": midpoint_lost,
        "wick_back_inside_but_close_hold": wick_back_close_hold,
        "boundary_hold_after_breakout": boundary_hold,
        "midpoint_hold_after_breakout": midpoint_hold,
        "followthrough_bar_count": followthrough,
        "max_favorable_excursion_before_retest": mfe,
        "max_adverse_excursion_before_acceptance": mae,
        "high_volume_no_result_after_breakout": high_volume_no_result,
        "retest_depth_atr": retest_depth,
        "bars_to_retest": len(window),
        "midpoint_distance": midpoint_distance,
        "boundary_distance": boundary_distance,
        "continuation_distance": continuation_distance,
        "acceptance_retest_low": retest_low,
        "acceptance_retest_high": retest_high,
    }


def _compression_failure_taxonomy(metrics: Mapping[str, Any], failed_stage: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if failed_stage == "breakout_displacement_valid":
        if (metrics.get("breakout_displacement_atr") or 0.0) < 0.5:
            reasons.append("displacement_too_small_vs_ATR")
        if (metrics.get("breakout_displacement_box_ratio") or 0.0) < 1.0:
            reasons.append("displacement_too_small_vs_box")
        if (metrics.get("breakout_body_pct") or 0.0) < 0.45:
            reasons.append("no_real_displacement")
        if (metrics.get("breakout_close_location") or 0.0) < 0.65:
            reasons.append("close_location_weak")
        if (metrics.get("close_outside_box_distance_ATR") or 0.0) < 0.05:
            reasons.append("close_outside_box_distance_too_small")
    elif failed_stage == "breakout_volume_valid":
        reasons.append("volume_not_confirmed")
        if (metrics.get("volume_expansion_vs_compression") or 0.0) < 1.2:
            reasons.append("volume_expansion_weak")
    elif failed_stage == "failed_breakout_absent":
        reasons.append("immediate_reclaim_inside_box")
    elif failed_stage == "midpoint_hold":
        if metrics.get("wick_back_inside_but_close_hold"):
            reasons.append("normal_retest_misclassified_candidate")
        reasons.append("midpoint_lost")
    elif failed_stage == "retest_hold":
        if metrics.get("wick_back_inside_but_close_hold"):
            reasons.append("normal_retest_misclassified_candidate")
        reasons.append("boundary_not_held")
    elif failed_stage == "continuation_ready":
        reasons.append("high_volume_no_result_absorption" if metrics.get("high_volume_no_result_after_breakout") else "ambiguous")
    if not reasons:
        reasons.append("ambiguous")
    return reasons[0], reasons[1:]


def _compression_subtype(metrics: Mapping[str, Any]) -> str:
    score = float(metrics.get("breakout_score") or 0.0)
    body = float(metrics.get("breakout_body_pct") or 0.0)
    close_location = float(metrics.get("breakout_close_location") or 0.0)
    followthrough = int(metrics.get("followthrough_bar_count") or 0)
    wick_retest = bool(metrics.get("wick_back_inside_but_close_hold"))
    boundary_hold = bool(metrics.get("boundary_hold_after_breakout"))
    midpoint_hold = bool(metrics.get("midpoint_hold_after_breakout"))
    if score >= 0.62 and body >= 0.55 and close_location >= 0.70 and followthrough >= 1 and not wick_retest:
        return "impulse_breakout"
    if boundary_hold and midpoint_hold and (wick_retest or followthrough >= 1):
        return "acceptance_retest"
    return "ambiguous"


def evaluate_breakout_pullback_diagnostics(
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    regime: MarketRegimeContext | None,
    *,
    parameters: StrategyParameters | None = None,
    context_features: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    params = parameters or strategy_parameters_from_context(context_features)
    structure = _confirmed_candles(structure_candles)
    entry = _confirmed_candles(entry_candles)
    stages: dict[str, dict[str, Any]] = {}
    metrics: dict[str, Any] = {"setup_id": "breakout_pullback"}

    def add_stage(name: str, passed: bool, **payload: Any) -> None:
        stages[name] = {"passed": bool(passed), **payload}

    window_ready = len(structure) >= max(8, params.bp_lookback_bars + 4) and bool(entry)
    add_stage("window_ready", window_ready, structure_count=len(structure), entry_count=len(entry))
    if not window_ready:
        metrics.update({"primary_failure_reason": "sample_unstable", "secondary_failure_reasons": []})
        return _trend_diagnostic_result(stages, metrics)

    atr = float(regime.atr) if regime is not None and float(regime.atr) > 0 else _average_range(structure)
    if atr <= 0:
        add_stage("structure_context", False, atr=atr)
        metrics.update({"primary_failure_reason": "ambiguous", "secondary_failure_reasons": ["no_atr"]})
        return _trend_diagnostic_result(stages, metrics)

    lookback = max(4, int(params.bp_lookback_bars))
    breakout_index = len(structure) - 4
    acceptance_window = tuple(structure[breakout_index + 1:breakout_index + 1 + max(1, min(3, int(params.bp_acceptance_window_bars)))])
    pullback = structure[-2]
    relaunch = structure[-1]
    context_window = structure[breakout_index - lookback:breakout_index]
    if len(context_window) < lookback or not acceptance_window:
        add_stage("structure_context", False, context_count=len(context_window), acceptance_count=len(acceptance_window))
        metrics.update({"primary_failure_reason": "sample_unstable", "secondary_failure_reasons": []})
        return _trend_diagnostic_result(stages, metrics)

    reference_high = max(float(candle.high) for candle in context_window)
    reference_low = min(float(candle.low) for candle in context_window)
    reference_midpoint = (reference_high + reference_low) / 2.0
    level_range = reference_high - reference_low
    avg_range = _average_range(context_window)
    avg_body = sum(abs(float(c.close) - float(c.open)) for c in context_window) / len(context_window)
    breakout = structure[breakout_index]
    breakout_close = float(breakout.close)
    buffer = atr * params.bp_breakout_buffer_atr
    if breakout_close > reference_high + buffer:
        direction = "long"
        breakout_level = reference_high
        close_outside = breakout_close - reference_high
    elif breakout_close < reference_low - buffer:
        direction = "short"
        breakout_level = reference_low
        close_outside = reference_low - breakout_close
    else:
        direction = ""
        breakout_level = reference_high
        close_outside = 0.0
    metrics.update(
        {
            "breakout_reference_level": breakout_level,
            "breakout_level_type": "range_boundary",
            "breakout_time": getattr(breakout, "timestamp_ms", None),
            "breakout_close": breakout_close,
            "direction": direction,
            "reference_high": reference_high,
            "reference_low": reference_low,
            "reference_midpoint": reference_midpoint,
            "reference_range": level_range,
        }
    )
    add_stage("structure_context", level_range > 0, breakout_reference_level=breakout_level, level_range=level_range)
    if level_range <= 0:
        metrics.update({"primary_failure_reason": "ambiguous", "secondary_failure_reasons": ["zero_level_range"]})
        return _trend_diagnostic_result(stages, metrics)
    add_stage("true_breakout", direction in {"long", "short"}, direction=direction, close_outside=close_outside)
    if direction not in {"long", "short"}:
        metrics.update({"primary_failure_reason": "no_real_breakout", "secondary_failure_reasons": ["wick_only_breakout"]})
        return _trend_diagnostic_result(stages, metrics)

    breakout_range = float(breakout.high) - float(breakout.low)
    breakout_body = abs(float(breakout.close) - float(breakout.open))
    body_pct = breakout_body / breakout_range if breakout_range > 0 else 0.0
    close_location = (
        (float(breakout.close) - float(breakout.low)) / breakout_range
        if direction == "long" and breakout_range > 0
        else (float(breakout.high) - float(breakout.close)) / breakout_range if breakout_range > 0 else 0.0
    )
    range_expansion = breakout_range / avg_range if avg_range > 0 else None
    body_expansion = breakout_body / avg_body if avg_body > 0 else None
    baseline = _volume_baseline(context_window, context_features, anchor=breakout, current_volume=_candle_volume(breakout))
    breakout_rvol = _candle_volume(breakout) / baseline["average_volume"] if baseline["average_volume"] > 0 else 0.0
    breakout_score = _compression_breakout_score(
        displacement_atr=breakout_range / atr if atr > 0 else None,
        displacement_box_ratio=breakout_range / level_range if level_range > 0 else None,
        close_location=close_location,
        body_ratio=body_pct,
        close_outside_atr=close_outside / atr if atr > 0 else None,
        volume_expansion=breakout_rvol,
        range_expansion=range_expansion,
        body_expansion=body_expansion,
    )
    quality_valid = (
        breakout_range > 0
        and body_pct >= params.bp_breakout_body_ratio_min
        and breakout_rvol >= params.bp_breakout_rvol_min
        and breakout_score >= params.bp_min_breakout_score
    )
    metrics.update(
        {
            "breakout_displacement_ATR": breakout_range / atr if atr > 0 else None,
            "breakout_displacement_level_ratio": breakout_range / level_range if level_range > 0 else None,
            "breakout_close_location": close_location,
            "breakout_body_pct": body_pct,
            "breakout_range_vs_ATR": breakout_range / atr if atr > 0 else None,
            "breakout_range_expansion": range_expansion,
            "breakout_body_expansion": body_expansion,
            "breakout_RVOL": breakout_rvol,
            "breakout_rvol": breakout_rvol,
            "breakout_volume_z": _z_score(_candle_volume(breakout), [_candle_volume(c) for c in context_window]),
            "breakout_score": breakout_score,
            "volume_baseline_mode": baseline.get("volume_baseline_mode"),
            "volume_bucket_sample_count": baseline.get("volume_bucket_sample_count"),
            "used_fallback_volume_baseline": baseline.get("used_fallback_volume_baseline"),
        }
    )
    add_stage("breakout_quality_valid", quality_valid, breakout_score=breakout_score, breakout_rvol=breakout_rvol)
    if not quality_valid:
        primary, secondary = _breakout_pullback_failure_taxonomy(metrics, "breakout_quality_valid")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary})
        return _trend_diagnostic_result(stages, metrics)

    acceptance = _breakout_pullback_acceptance_metrics(
        direction=direction,
        breakout_level=breakout_level,
        reference_midpoint=reference_midpoint,
        breakout=breakout,
        acceptance_window=acceptance_window,
        atr=atr,
    )
    acceptance_passed = bool(acceptance["acceptance_status"] == "accepted")
    metrics.update(acceptance)
    add_stage("acceptance_window", acceptance_passed, acceptance_status=acceptance["acceptance_status"])
    if not acceptance_passed:
        primary, secondary = _breakout_pullback_failure_taxonomy(metrics, "acceptance_window")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary})
        return _trend_diagnostic_result(stages, metrics)

    pullback_metrics = _breakout_pullback_pullback_metrics(
        direction=direction,
        breakout_level=breakout_level,
        reference_low=reference_low,
        reference_high=reference_high,
        reference_midpoint=reference_midpoint,
        breakout=breakout,
        pullback=pullback,
        atr=atr,
        level_range=level_range,
        params=params,
    )
    metrics.update(pullback_metrics)
    pullback_passed = bool(pullback_metrics["pullback_quality_score"] >= 0.35 and not pullback_metrics["pullback_invalidated"])
    add_stage("healthy_pullback", pullback_passed, pullback_quality_score=pullback_metrics["pullback_quality_score"])
    if not pullback_passed:
        primary, secondary = _breakout_pullback_failure_taxonomy(metrics, "healthy_pullback")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary})
        return _trend_diagnostic_result(stages, metrics)

    relaunch_metrics = _breakout_pullback_relaunch_metrics(
        direction=direction,
        pullback=pullback,
        relaunch=relaunch,
        atr=atr,
        pullback_volume=_candle_volume(pullback),
        params=params,
    )
    metrics.update(relaunch_metrics)
    relaunch_passed = bool(relaunch_metrics["relaunch_score"] >= params.bp_min_relaunch_score)
    add_stage("relaunch_confirmation", relaunch_passed, relaunch_score=relaunch_metrics["relaunch_score"])
    if not relaunch_passed:
        primary, secondary = _breakout_pullback_failure_taxonomy(metrics, "relaunch_confirmation")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary})
        return _trend_diagnostic_result(stages, metrics)

    bp_subtype = _breakout_pullback_subtype(metrics, params.bp_variant_policy)
    if params.bp_subtype_focus != "any" and bp_subtype != params.bp_subtype_focus:
        metrics.update({"bp_subtype": bp_subtype, "primary_failure_reason": "ambiguous", "secondary_failure_reasons": ["subtype_not_selected"]})
        add_stage("subtype_selected", False, bp_subtype=bp_subtype, subtype_focus=params.bp_subtype_focus)
        return _trend_diagnostic_result(stages, metrics)
    add_stage("subtype_selected", True, bp_subtype=bp_subtype, subtype_focus=params.bp_subtype_focus)

    stop_buffer = atr * params.bp_stop_buffer_atr
    entry_reference = float(relaunch.close)
    if direction == "long":
        if params.bp_variant_policy == "boundary_midpoint":
            stop = min(float(pullback.low), breakout_level, reference_midpoint) - stop_buffer
            stop_anchor_type = "boundary_midpoint_structural_stop"
        elif params.bp_variant_policy == "shallow_momentum":
            stop = min(float(pullback.low), float(breakout.low)) - stop_buffer
            stop_anchor_type = "pullback_micro_or_breakout_extreme_stop"
        else:
            stop = float(pullback.low) - stop_buffer
            stop_anchor_type = "pullback_low_high_structural_stop"
        target = entry_reference + max(level_range, abs(entry_reference - stop) * 2.0)
    else:
        if params.bp_variant_policy == "boundary_midpoint":
            stop = max(float(pullback.high), breakout_level, reference_midpoint) + stop_buffer
            stop_anchor_type = "boundary_midpoint_structural_stop"
        elif params.bp_variant_policy == "shallow_momentum":
            stop = max(float(pullback.high), float(breakout.high)) + stop_buffer
            stop_anchor_type = "pullback_micro_or_breakout_extreme_stop"
        else:
            stop = float(pullback.high) + stop_buffer
            stop_anchor_type = "pullback_low_high_structural_stop"
        target = entry_reference - max(level_range, abs(stop - entry_reference) * 2.0)
    stop_distance = abs(entry_reference - stop)
    target_space = abs(target - entry_reference)
    gross_rr = 0.0 if stop_distance <= 0 else target_space / stop_distance
    cost_per_r = 0.0
    cost_adjusted_rr = gross_rr - cost_per_r
    risk_passed = (
        stop_distance > 0
        and gross_rr >= params.bp_min_target_r
        and (target_space / atr if atr > 0 else 0.0) >= params.bp_min_target_space_atr
        and cost_adjusted_rr >= params.bp_min_cost_adjusted_rr
        and cost_per_r <= params.bp_max_cost_per_r
    )
    metrics.update(
        {
            "bp_subtype": bp_subtype,
            "entry_reference_price": entry_reference,
            "entry": entry_reference,
            "entry_time": getattr(relaunch, "timestamp_ms", None),
            "stop_price": stop,
            "stop": stop,
            "target_price": target,
            "target": target,
            "stop_anchor_type": stop_anchor_type,
            "stop_distance": stop_distance,
            "stop_distance_ATR": stop_distance / atr if atr > 0 else None,
            "stop_distance_level_ratio": stop_distance / level_range if level_range > 0 else None,
            "stop_buffer_ATR": params.bp_stop_buffer_atr,
            "entry_to_stop": stop_distance,
            "target_space": target_space,
            "target_space_atr": target_space / atr if atr > 0 else None,
            "gross_RR": gross_rr,
            "cost_adjusted_RR": cost_adjusted_rr,
            "cost_per_R": cost_per_r,
            "primary_failure_reason": "",
            "secondary_failure_reasons": [],
        }
    )
    add_stage("risk_precheck_pass", risk_passed, gross_RR=gross_rr, target_space_atr=metrics["target_space_atr"])
    if not risk_passed:
        primary, secondary = _breakout_pullback_failure_taxonomy(metrics, "risk_precheck_pass")
        metrics.update({"primary_failure_reason": primary, "secondary_failure_reasons": secondary})
        return _trend_diagnostic_result(stages, metrics)
    return _trend_diagnostic_result(stages, metrics)


def _breakout_pullback_acceptance_metrics(
    *,
    direction: str,
    breakout_level: float,
    reference_midpoint: float,
    breakout: object,
    acceptance_window: Sequence[object],
    atr: float,
) -> dict[str, Any]:
    window = tuple(acceptance_window)
    close_back_index: int | None = None
    wick_hold = False
    followthrough = 0
    if direction == "long":
        for offset, candle in enumerate(window, start=1):
            if float(candle.close) <= breakout_level and close_back_index is None:
                close_back_index = offset
            if float(candle.low) <= breakout_level and float(candle.close) > breakout_level:
                wick_hold = True
            if float(candle.close) > float(breakout.close):
                followthrough += 1
        midpoint_lost = any(float(candle.close) < reference_midpoint for candle in window)
        boundary_hold = not any(float(candle.close) <= breakout_level for candle in window)
    else:
        for offset, candle in enumerate(window, start=1):
            if float(candle.close) >= breakout_level and close_back_index is None:
                close_back_index = offset
            if float(candle.high) >= breakout_level and float(candle.close) < breakout_level:
                wick_hold = True
            if float(candle.close) < float(breakout.close):
                followthrough += 1
        midpoint_lost = any(float(candle.close) > reference_midpoint for candle in window)
        boundary_hold = not any(float(candle.close) >= breakout_level for candle in window)
    ranges = [float(c.high) - float(c.low) for c in window]
    bodies = [abs(float(c.close) - float(c.open)) for c in window]
    high_volume_no_result = bool(ranges and max(bodies or [0.0]) <= max(ranges) * 0.25 and followthrough == 0)
    accepted = close_back_index is None and not high_volume_no_result
    return {
        "acceptance_window_bars": len(window),
        "close_back_inside_level": close_back_index is not None,
        "close_back_inside_bar_index": close_back_index,
        "wick_back_but_close_hold": wick_hold,
        "immediate_reclaim": close_back_index == 1,
        "high_volume_no_result": high_volume_no_result,
        "boundary_hold_after_breakout": boundary_hold,
        "midpoint_hold_after_breakout": not midpoint_lost,
        "acceptance_score": (1.0 if accepted else 0.0) + min(0.5, followthrough * 0.25) + (0.25 if wick_hold else 0.0),
        "acceptance_status": "accepted" if accepted else "failed_breakout",
    }


def _breakout_pullback_pullback_metrics(
    *,
    direction: str,
    breakout_level: float,
    reference_low: float,
    reference_high: float,
    reference_midpoint: float,
    breakout: object,
    pullback: object,
    atr: float,
    level_range: float,
    params: StrategyParameters,
) -> dict[str, Any]:
    breakout_volume = _candle_volume(breakout)
    pullback_volume = _candle_volume(pullback)
    breakout_range = max(float(breakout.high) - float(breakout.low), 0.0)
    pullback_range = max(float(pullback.high) - float(pullback.low), 0.0)
    breakout_body = abs(float(breakout.close) - float(breakout.open))
    pullback_body = abs(float(pullback.close) - float(pullback.open))
    if direction == "long":
        depth = max(0.0, float(breakout.close) - float(pullback.low))
        invalidated = float(pullback.close) <= reference_midpoint
        level_distance = abs(float(pullback.low) - breakout_level)
        boundary_distance = abs(float(pullback.low) - reference_high)
        midpoint_distance = abs(float(pullback.low) - reference_midpoint)
        close_location = 0.0 if pullback_range <= 0 else (float(pullback.close) - float(pullback.low)) / pullback_range
        held = float(pullback.close) > reference_midpoint
    else:
        depth = max(0.0, float(pullback.high) - float(breakout.close))
        invalidated = float(pullback.close) >= reference_midpoint
        level_distance = abs(float(pullback.high) - breakout_level)
        boundary_distance = abs(float(pullback.high) - reference_low)
        midpoint_distance = abs(float(pullback.high) - reference_midpoint)
        close_location = 0.0 if pullback_range <= 0 else (float(pullback.high) - float(pullback.close)) / pullback_range
        held = float(pullback.close) < reference_midpoint
    depth_atr = depth / atr if atr > 0 else None
    depth_vs_breakout = depth / breakout_range if breakout_range > 0 else None
    depth_vs_box = depth / level_range if level_range > 0 else None
    volume_ratio = pullback_volume / breakout_volume if breakout_volume > 0 else None
    volume_contraction = volume_ratio is not None and volume_ratio <= params.bp_pullback_volume_ratio_max
    range_contraction = pullback_range <= breakout_range
    body_contraction = pullback_body <= breakout_body
    distances = {
        "level_retest": level_distance,
        "boundary_retest": boundary_distance,
        "midpoint_retest": midpoint_distance,
    }
    zone_type = min(distances, key=distances.get)
    zone_distance = distances[zone_type] / atr if atr > 0 else None
    shallow = depth_atr is not None and depth_atr <= max(params.bp_pullback_min_depth_atr * 6.0, 0.45)
    if params.bp_variant_policy == "shallow_momentum" and shallow:
        zone_type = "shallow_pullback"
    score_parts = [
        1.0 if params.bp_pullback_min_depth_atr <= (depth_atr or 0.0) <= params.bp_pullback_max_depth_atr else 0.0,
        1.0 if volume_contraction else 0.0,
        1.0 if range_contraction else 0.0,
        1.0 if body_contraction else 0.0,
        1.0 if held and not invalidated else 0.0,
        1.0 if zone_distance is not None and zone_distance <= params.bp_pullback_tolerance_atr else 0.0,
    ]
    return {
        "pullback_start_time": getattr(pullback, "timestamp_ms", None),
        "pullback_end_time": getattr(pullback, "timestamp_ms", None),
        "pullback_depth_ATR": depth_atr,
        "pullback_depth_vs_breakout": depth_vs_breakout,
        "pullback_depth_vs_box": depth_vs_box,
        "pullback_bars": 1,
        "pullback_volume_ratio_vs_breakout": volume_ratio,
        "pullback_volume_contraction": volume_contraction,
        "pullback_range_contraction": range_contraction,
        "pullback_body_contraction": body_contraction,
        "pullback_close_location": close_location,
        "pullback_zone_type": zone_type,
        "pullback_zone_distance_ATR": zone_distance,
        "pullback_held_level": held,
        "pullback_invalidated": invalidated,
        "pullback_quality_score": sum(score_parts) / len(score_parts),
    }


def _breakout_pullback_relaunch_metrics(
    *,
    direction: str,
    pullback: object,
    relaunch: object,
    atr: float,
    pullback_volume: float,
    params: StrategyParameters,
) -> dict[str, Any]:
    relaunch_range = max(float(relaunch.high) - float(relaunch.low), 0.0)
    relaunch_body = abs(float(relaunch.close) - float(relaunch.open))
    body_pct = relaunch_body / relaunch_range if relaunch_range > 0 else 0.0
    if direction == "long":
        close_location = 0.0 if relaunch_range <= 0 else (float(relaunch.close) - float(relaunch.low)) / relaunch_range
        displacement = max(0.0, float(relaunch.close) - float(pullback.close))
        micro_break = float(relaunch.close) > float(pullback.high)
    else:
        close_location = 0.0 if relaunch_range <= 0 else (float(relaunch.high) - float(relaunch.close)) / relaunch_range
        displacement = max(0.0, float(pullback.close) - float(relaunch.close))
        micro_break = float(relaunch.close) < float(pullback.low)
    volume_recovery = _candle_volume(relaunch) / pullback_volume if pullback_volume > 0 else None
    score_parts = [
        _cap_ratio(displacement / atr if atr > 0 else None, 0.8) or 0.0,
        _cap_ratio(body_pct, 0.65) or 0.0,
        _cap_ratio(close_location, 0.85) or 0.0,
        _cap_ratio(volume_recovery, params.bp_relaunch_volume_recovery_min * 1.5) or 0.0,
        1.0 if micro_break else 0.0,
    ]
    return {
        "relaunch_time": getattr(relaunch, "timestamp_ms", None),
        "relaunch_close": float(relaunch.close),
        "relaunch_displacement_ATR": displacement / atr if atr > 0 else None,
        "relaunch_body_pct": body_pct,
        "relaunch_close_location": close_location,
        "relaunch_volume_recovery": volume_recovery,
        "relaunch_breaks_micro_structure": micro_break,
        "relaunch_score": sum(score_parts) / len(score_parts),
    }


def _breakout_pullback_subtype(metrics: Mapping[str, Any], policy: str) -> str:
    zone = str(metrics.get("pullback_zone_type") or "")
    if policy == "shallow_momentum" or zone == "shallow_pullback":
        return "shallow_pullback_momentum"
    if policy == "boundary_midpoint":
        if zone == "midpoint_retest":
            return "midpoint_retest_continuation"
        return "boundary_retest_continuation"
    if zone == "midpoint_retest":
        return "midpoint_retest_continuation"
    if zone == "boundary_retest":
        return "boundary_retest_continuation"
    if zone == "level_retest":
        return "level_retest_continuation"
    return "ambiguous"


def _breakout_pullback_failure_taxonomy(metrics: Mapping[str, Any], failed_stage: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if failed_stage == "breakout_quality_valid":
        if (metrics.get("breakout_score") or 0.0) <= 0:
            reasons.append("no_real_breakout")
        if (metrics.get("breakout_body_pct") or 0.0) < 0.35:
            reasons.append("wick_only_breakout")
        if (metrics.get("breakout_displacement_ATR") or 0.0) < 0.4:
            reasons.append("displacement_too_small")
        if (metrics.get("breakout_close_location") or 0.0) < 0.55:
            reasons.append("close_location_weak")
        if (metrics.get("breakout_RVOL") or 0.0) < 1.0:
            reasons.append("volume_expansion_weak")
    elif failed_stage == "acceptance_window":
        if metrics.get("close_back_inside_level"):
            reasons.append("close_back_inside_level")
        if metrics.get("immediate_reclaim"):
            reasons.append("immediate_reclaim")
        if metrics.get("high_volume_no_result"):
            reasons.append("high_volume_no_result")
        if metrics.get("midpoint_hold_after_breakout") is False:
            reasons.append("midpoint_lost")
        if metrics.get("boundary_hold_after_breakout") is False:
            reasons.append("boundary_lost")
        if not reasons:
            reasons.append("acceptance_window_failed")
    elif failed_stage == "healthy_pullback":
        if metrics.get("pullback_depth_ATR") is None:
            reasons.append("no_pullback")
        elif (metrics.get("pullback_depth_ATR") or 0.0) > 2.2:
            reasons.append("pullback_too_deep")
        elif (metrics.get("pullback_depth_ATR") or 0.0) < 0.05:
            reasons.append("pullback_too_shallow")
        if metrics.get("pullback_invalidated"):
            reasons.append("pullback_invalidated_level")
        if metrics.get("pullback_volume_contraction") is False:
            reasons.append("pullback_volume_too_high")
        if metrics.get("pullback_range_contraction") is False:
            reasons.append("pullback_range_expanded")
        if str(metrics.get("pullback_zone_type") or "") == "":
            reasons.append("pullback_zone_unclear")
    elif failed_stage == "relaunch_confirmation":
        if (metrics.get("relaunch_score") or 0.0) <= 0:
            reasons.append("no_relaunch")
        if (metrics.get("relaunch_body_pct") or 0.0) < 0.30:
            reasons.append("relaunch_weak_body")
        if (metrics.get("relaunch_close_location") or 0.0) < 0.50:
            reasons.append("relaunch_weak_close")
        if (metrics.get("relaunch_volume_recovery") or 0.0) < 1.0:
            reasons.append("relaunch_no_volume_recovery")
        if not metrics.get("relaunch_breaks_micro_structure"):
            reasons.append("relaunch_no_micro_structure_break")
    elif failed_stage == "risk_precheck_pass":
        if (metrics.get("gross_RR") or 0.0) < 1.0:
            reasons.append("target_space_insufficient")
        if (metrics.get("cost_adjusted_RR") or 0.0) < 0.0:
            reasons.append("cost_adjusted_RR_too_low")
    if not reasons:
        reasons.append("ambiguous")
    return reasons[0], reasons[1:]


def minimum_reward_to_risk(
    entry_price: float,
    invalidation_level: float,
    target_price: float,
) -> float | None:
    risk = abs(float(entry_price) - float(invalidation_level))
    if risk <= 0 or not math.isfinite(risk):
        return None

    reward = abs(float(target_price) - float(entry_price))
    if not math.isfinite(reward):
        return None
    return reward / risk


def _detect_trend_continuation(
    structure: tuple[object, ...],
    entry: tuple[object, ...],
    regime: MarketRegimeContext,
    params: StrategyParameters,
    context_features: Mapping[str, Any] | None,
) -> PriceActionSetup | None:
    diagnostics = evaluate_trend_continuation_diagnostics(
        structure,
        entry,
        regime,
        parameters=params,
        context_features=context_features,
    )
    if not diagnostics["candidate_ready"]:
        return None

    direction = str(diagnostics["metrics"]["direction"])
    breakout = structure[-2]
    pullback = structure[-1]
    atr = float(diagnostics["metrics"]["atr"])
    prior_level = float(diagnostics["metrics"]["prior_structure_level"])
    if direction == "long":
        invalidation = min(float(pullback.low), prior_level) - atr
        entry_low, entry_high = _entry_zone(entry)
        target = float(entry[-1].close) + abs(float(entry[-1].close) - invalidation) * 2.0
    else:
        invalidation = max(float(pullback.high), prior_level) + atr
        entry_low, entry_high = _entry_zone(entry)
        target = float(entry[-1].close) - abs(invalidation - float(entry[-1].close)) * 2.0

    stages = diagnostics["stages"]
    metrics = diagnostics["metrics"]
    return PriceActionSetup(
        setup_type="trend_continuation",
        direction=direction,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        invalidation_level=invalidation,
        target_price=target,
        evidence={
            "structure": "BOS_DISPLACEMENT_PULLBACK",
            "strategy_family": "breakout_pullback_continuation",
            "trend_gate_role": "hard_gate",
            "direction": direction,
            "breakout_timestamp_ms": getattr(breakout, "timestamp_ms", None),
            "pullback_timestamp_ms": getattr(pullback, "timestamp_ms", None),
            "breakout_rvol": metrics.get("breakout_rvol"),
            "pullback_rvol": metrics.get("pullback_rvol"),
            "breakout_body_ratio": metrics.get("breakout_body_ratio"),
            "breakout_close_location": metrics.get("breakout_close_location"),
            "breakout_buffer_atr": params.breakout_buffer_atr,
            "pullback_holds_midpoint": stages["pullback_midpoint"]["passed"],
            "restart_confirmation": stages["restart_price"]["passed"] and stages["restart_rvol"]["passed"],
            "restart_rvol": metrics.get("restart_rvol"),
            "volume_baseline_mode": metrics.get("volume_baseline_mode"),
            "volume_bucket_sample_count": metrics.get("volume_bucket_sample_count"),
            "used_fallback_volume_baseline": metrics.get("used_fallback_volume_baseline"),
        },
    )


def _detect_liquidity_reversal(
    structure: tuple[object, ...],
    entry: tuple[object, ...],
    regime: MarketRegimeContext,
    params: StrategyParameters,
    context_features: Mapping[str, Any] | None,
) -> PriceActionSetup | None:
    average_range = _average_range(structure)
    if average_range <= 0:
        return None

    atr = regime.atr if regime.atr > 0 else average_range
    for index in range(2, len(structure) - 1):
        sweep = structure[index]
        next_candles = structure[index + 1 : index + 1 + params.reclaim_max_bars]
        previous = structure[index - 1]
        volume_baseline_evidence = _volume_baseline(
            structure[:index],
            _structure_volume_features(context_features),
            anchor=sweep,
            current_volume=_candle_volume(sweep),
        )
        volume_baseline = volume_baseline_evidence["average_volume"]
        if volume_baseline <= 0:
            continue
        sweep_rvol = _candle_volume(sweep) / volume_baseline

        prior_low = min(float(candle.low) for candle in structure[:index])
        downside_deviation = prior_low - float(sweep.low)
        if downside_deviation > 0:
            reclaim = _find_reclaim_candle(sweep, next_candles, "long", prior_low)
            choch = next((candle for candle in next_candles if float(candle.close) > float(previous.high)), None)
            countertrend = regime.direction == "short"
            required_rvol = params.countertrend_sweep_rvol_min if countertrend else params.sweep_rvol_min
            wick_ratio = _wick_ratio(sweep, "long")
            reclaim_rvol = _candle_volume(reclaim) / volume_baseline if reclaim is not None and volume_baseline > 0 else None
            if (
                reclaim is not None
                and choch is not None
                and downside_deviation <= atr * params.sweep_max_atr_multiple
                and wick_ratio >= params.sweep_wick_ratio_min
                and sweep_rvol >= required_rvol
                and (reclaim_rvol is None or reclaim_rvol <= params.reclaim_rvol_max)
            ):
                reclaim_bars = _bars_between(sweep, reclaim)
                invalidation = _invalidation_level("long", sweep, atr, params)
                entry_low, entry_high = _entry_zone(entry)
                target = float(entry[-1].close) + abs(float(entry[-1].close) - invalidation) * 2.0
                return PriceActionSetup(
                    setup_type="liquidity_reversal",
                    direction="long",
                    entry_zone_low=entry_low,
                    entry_zone_high=entry_high,
                    invalidation_level=invalidation,
                    target_price=target,
                    evidence={
                        "structure": "SWEEP_CHOCH",
                        "strategy_family": "liquidity_sweep_reclaim",
                        "trend_gate_role": "soft_context",
                        "sweep_direction": "down",
                        "sweep_timestamp_ms": getattr(sweep, "timestamp_ms", None),
                        "reclaim_timestamp_ms": getattr(reclaim, "timestamp_ms", None),
                        "choch_timestamp_ms": getattr(choch, "timestamp_ms", None),
                        "sweep_rvol": sweep_rvol,
                        "required_sweep_rvol": required_rvol,
                        "sweep_wick_ratio": wick_ratio,
                        "sweep_deviation_atr": downside_deviation / atr,
                        "reclaim_bars": reclaim_bars,
                        "reclaim_rvol": reclaim_rvol,
                        "reclaim_rvol_max": params.reclaim_rvol_max,
                        "countertrend": countertrend,
                        "invalidation_mode": params.invalidation_mode,
                        "invalidation_buffer_atr": params.invalidation_buffer_atr,
                        "sweep_extreme_price": float(sweep.low),
                        "reclaim_price": float(reclaim.close),
                        "structure_level": prior_low,
                        "volume_baseline_mode": volume_baseline_evidence["volume_baseline_mode"],
                    },
                )

        prior_high = max(float(candle.high) for candle in structure[:index])
        upside_deviation = float(sweep.high) - prior_high
        if upside_deviation > 0:
            reclaim = _find_reclaim_candle(sweep, next_candles, "short", prior_high)
            choch = next((candle for candle in next_candles if float(candle.close) < float(previous.low)), None)
            countertrend = regime.direction == "long"
            required_rvol = params.countertrend_sweep_rvol_min if countertrend else params.sweep_rvol_min
            wick_ratio = _wick_ratio(sweep, "short")
            reclaim_rvol = _candle_volume(reclaim) / volume_baseline if reclaim is not None and volume_baseline > 0 else None
            if (
                reclaim is not None
                and choch is not None
                and upside_deviation <= atr * params.sweep_max_atr_multiple
                and wick_ratio >= params.sweep_wick_ratio_min
                and sweep_rvol >= required_rvol
                and (reclaim_rvol is None or reclaim_rvol <= params.reclaim_rvol_max)
            ):
                reclaim_bars = _bars_between(sweep, reclaim)
                invalidation = _invalidation_level("short", sweep, atr, params)
                entry_low, entry_high = _entry_zone(entry)
                target = float(entry[-1].close) - abs(invalidation - float(entry[-1].close)) * 2.0
                return PriceActionSetup(
                    setup_type="liquidity_reversal",
                    direction="short",
                    entry_zone_low=entry_low,
                    entry_zone_high=entry_high,
                    invalidation_level=invalidation,
                    target_price=target,
                    evidence={
                        "structure": "SWEEP_CHOCH",
                        "strategy_family": "liquidity_sweep_reclaim",
                        "trend_gate_role": "soft_context",
                        "sweep_direction": "up",
                        "sweep_timestamp_ms": getattr(sweep, "timestamp_ms", None),
                        "reclaim_timestamp_ms": getattr(reclaim, "timestamp_ms", None),
                        "choch_timestamp_ms": getattr(choch, "timestamp_ms", None),
                        "sweep_rvol": sweep_rvol,
                        "required_sweep_rvol": required_rvol,
                        "sweep_wick_ratio": wick_ratio,
                        "sweep_deviation_atr": upside_deviation / atr,
                        "reclaim_bars": reclaim_bars,
                        "reclaim_rvol": reclaim_rvol,
                        "reclaim_rvol_max": params.reclaim_rvol_max,
                        "countertrend": countertrend,
                        "invalidation_mode": params.invalidation_mode,
                        "invalidation_buffer_atr": params.invalidation_buffer_atr,
                        "sweep_extreme_price": float(sweep.high),
                        "reclaim_price": float(reclaim.close),
                        "structure_level": prior_high,
                        "volume_baseline_mode": volume_baseline_evidence["volume_baseline_mode"],
                    },
                )
    return None


def strategy_parameters_from_context(context_features: Mapping[str, Any] | None) -> StrategyParameters:
    if not context_features:
        return StrategyParameters()
    raw = context_features.get("strategy_parameters")
    if not isinstance(raw, Mapping):
        return StrategyParameters()
    allowed = set(StrategyParameters.__dataclass_fields__)
    values = {key: value for key, value in raw.items() if key in allowed}
    trend_raw = raw.get("trend_continuation")
    if isinstance(trend_raw, Mapping):
        values.update({key: value for key, value in trend_raw.items() if key in allowed})
    compression_raw = raw.get("compression_expansion")
    if isinstance(compression_raw, Mapping):
        values.update({key: value for key, value in compression_raw.items() if key in allowed})
    breakout_pullback_raw = raw.get("breakout_pullback")
    if isinstance(breakout_pullback_raw, Mapping):
        values.update({key: value for key, value in breakout_pullback_raw.items() if key in allowed})
    liquidity_raw = raw.get("liquidity_reversal")
    if isinstance(liquidity_raw, Mapping):
        values.update({key: value for key, value in liquidity_raw.items() if key in allowed})
        assets = liquidity_raw.get("assets")
        asset = str(context_features.get("asset", "")).upper()
        if isinstance(assets, Mapping) and isinstance(assets.get(asset), Mapping):
            values.update({key: value for key, value in assets[asset].items() if key in allowed})
    return StrategyParameters(**values)


def _confirmed_candles(candles: Sequence[object]) -> tuple[object, ...]:
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _average_range(candles: Sequence[object]) -> float:
    if not candles:
        return 0.0
    return sum(float(candle.high) - float(candle.low) for candle in candles) / len(candles)


def _volume_baseline(
    history: Sequence[object],
    context_features: Mapping[str, Any] | None,
    *,
    anchor: object | None = None,
    current_volume: float | None = None,
) -> dict[str, Any]:
    history = tuple(history)
    current = 0.0 if current_volume is None else float(current_volume)
    if not history:
        return {
            "average_volume": 0.0,
            "volume_source": "base",
            "raw_volume": current,
            "log_volume": _safe_log(current, 1e-12),
            "rolling_rvol": None,
            "tod_dow_rvol": None,
            "volume_baseline_mode": "rolling_ewma",
            "volume_bucket_key": "",
            "volume_bucket_sample_count": 0,
            "used_fallback_volume_baseline": True,
        }
    if context_features and "tod_volume_baseline" in context_features:
        baseline = float(context_features["tod_volume_baseline"])
        return {
            "average_volume": baseline,
            "volume_source": "tod",
            "raw_volume": current,
            "log_volume": _safe_log(current, 1e-12),
            "rolling_rvol": None if baseline <= 0 else current / baseline,
            "tod_dow_rvol": None if baseline <= 0 else current / baseline,
            "volume_baseline_mode": "tod",
            "volume_bucket_key": "",
            "volume_bucket_sample_count": len(history),
            "used_fallback_volume_baseline": False,
        }
    source = "quote" if any(_has_quote_volume(candle) for candle in history) else "base"
    config = _volume_config(context_features)
    rolling_baseline = _rolling_ewma_volume(history)
    rolling_rvol = None if rolling_baseline <= 0 else current / rolling_baseline
    evidence = {
        "average_volume": rolling_baseline,
        "volume_source": source,
        "raw_volume": current,
        "log_volume": _safe_log(current, _epsilon(config)),
        "rolling_rvol": rolling_rvol,
        "tod_dow_rvol": None,
        "volume_baseline_mode": "rolling_ewma",
        "volume_bucket_key": "",
        "volume_bucket_sample_count": len(history),
        "used_fallback_volume_baseline": False,
    }
    if config.get("baseline_mode") != "tod_dow_log_ewma" or anchor is None:
        return evidence

    bucket_key = _volume_bucket_key(context_features, anchor)
    bucket_history = tuple(candle for candle in history if _volume_bucket_key(context_features, candle) == bucket_key)
    min_samples = int(config.get("min_bucket_samples", 30))
    evidence["volume_bucket_key"] = bucket_key
    evidence["volume_bucket_sample_count"] = len(bucket_history)
    if len(bucket_history) < min_samples:
        evidence["used_fallback_volume_baseline"] = True
        return evidence

    log_baseline = _log_ewma_baseline(bucket_history, half_life_days=float(config.get("half_life_days", 90)), epsilon=_epsilon(config))
    baseline = math.exp(log_baseline)
    evidence.update(
        {
            "average_volume": baseline,
            "tod_dow_rvol": math.exp(_safe_log(current, _epsilon(config)) - log_baseline),
            "volume_baseline_mode": "tod_dow_log_ewma",
            "used_fallback_volume_baseline": False,
        }
    )
    return evidence


def _candle_volume(candle: object) -> float:
    quote = getattr(candle, "volume_currency_quote", None)
    if quote is not None:
        value = float(quote)
        if value > 0 and math.isfinite(value):
            return value
    return float(getattr(candle, "volume", 0.0))


def _has_quote_volume(candle: object) -> bool:
    quote = getattr(candle, "volume_currency_quote", None)
    if quote is None:
        return False
    value = float(quote)
    return value > 0 and math.isfinite(value)


def _entry_zone(entry: Sequence[object]) -> tuple[float, float]:
    latest = entry[-1]
    return (float(latest.low), float(latest.high))


def _price_accepts_direction(candle: object, direction: str) -> bool:
    if direction == "long":
        return float(candle.close) > float(candle.open)
    if direction == "short":
        return float(candle.close) < float(candle.open)
    return False


def _price_state(candle: object) -> str:
    if float(candle.close) > float(candle.open):
        return "up_close"
    if float(candle.close) < float(candle.open):
        return "down_close"
    return "flat_close"


def _restart_confirms(entry: Sequence[object], direction: str, params: StrategyParameters) -> bool:
    diagnostics = _restart_diagnostics(entry, direction, params)
    return bool(diagnostics["price_passed"] and diagnostics["rvol_passed"])


def _trend_gate_passes(
    regime: MarketRegimeContext,
    params: StrategyParameters,
    context_features: Mapping[str, Any] | None,
) -> bool:
    profile = str((context_features or {}).get("timeframe_group") or (context_features or {}).get("profile") or "").upper()
    direction_ok = regime.direction in {"long", "short"}
    if params.trend_gate_policy == "strict_mature_trend":
        return regime.status == "TREND" and direction_ok
    ema_gap = abs(float(regime.fast_ema) - float(regime.slow_ema))
    min_gap = max(float(regime.atr) * 0.1, 0.0)
    if params.trend_gate_policy == "fresh_trend_b_v1":
        return (
            profile == "B"
            and direction_ok
            and (regime.adx or 0.0) >= 22.0
            and regime.efficiency_ratio >= 0.45
            and regime.choppiness <= 50.0
            and ema_gap >= min_gap * 0.5
        )
    if params.trend_gate_policy == "transition_trend_b_v1":
        return (
            profile == "B"
            and direction_ok
            and regime.status == "MEAN_REVERTING_TRANSITION"
            and (regime.adx or 0.0) >= 20.0
            and regime.efficiency_ratio >= 0.35
            and regime.choppiness <= 55.0
            and ema_gap >= min_gap * 0.3
        )
    if params.trend_gate_policy == "compression_expansion_watchlist_v1":
        return profile == "B" and direction_ok and regime.status == "COMPRESSION_PENDING_BREAKOUT"
    if params.trend_gate_policy == "profile_c_structure_proxy_v1":
        structure_regime = (context_features or {}).get("structure_regime")
        return (
            profile == "C"
            and hasattr(structure_regime, "status")
            and getattr(structure_regime, "status") == "TREND"
            and getattr(structure_regime, "direction", None) in {"long", "short"}
        )
    if params.trend_gate_policy == "near_threshold_mature_trend_v1":
        failures = 0
        if not direction_ok:
            failures += 1
        if (regime.adx or 0.0) < 25.0:
            failures += 1 if (regime.adx or 0.0) >= 22.0 else 2
        if regime.efficiency_ratio < 0.6:
            failures += 1 if regime.efficiency_ratio >= 0.5 else 2
        if regime.choppiness > 38.2:
            failures += 1 if regime.choppiness <= 45.0 else 2
        if ema_gap < min_gap:
            failures += 1 if ema_gap >= min_gap * 0.5 else 2
        return failures <= 1
    return regime.status == "TREND" and direction_ok


def _restart_diagnostics(entry: Sequence[object], direction: str, params: StrategyParameters) -> dict[str, object]:
    if len(entry) < 2:
        return {"price_passed": False, "rvol_passed": False, "latest_rvol": 0.0, "price_break_distance": 0.0}
    latest = entry[-1]
    previous = entry[-4:-1] if len(entry) >= 4 else entry[:-1]
    baseline_evidence = _volume_baseline(previous[-20:], None, anchor=latest, current_volume=_candle_volume(latest))
    baseline = baseline_evidence["average_volume"]
    latest_rvol = _candle_volume(latest) / baseline if baseline > 0 else 0.0
    accepts_direction = _price_accepts_direction(latest, direction)
    if direction == "long":
        price_break_distance = float(latest.close) - max(float(candle.high) for candle in previous)
        price_break = price_break_distance > 0
    elif direction == "short":
        price_break_distance = min(float(candle.low) for candle in previous) - float(latest.close)
        price_break = price_break_distance > 0
    else:
        price_break_distance = 0.0
        price_break = False
    return {
        "price_passed": bool(accepts_direction and price_break),
        "rvol_passed": bool(latest_rvol >= params.restart_rvol_min),
        "latest_rvol": latest_rvol,
        "price_break_distance": price_break_distance,
        "accepts_direction": accepts_direction,
        "volume_baseline": baseline,
        "volume_baseline_mode": baseline_evidence.get("volume_baseline_mode"),
    }


def _trend_diagnostic_result(
    stages: Mapping[str, Mapping[str, Any]],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    first_failed_stage = ""
    for name, stage in stages.items():
        if not bool(stage.get("passed")):
            first_failed_stage = name
            break
    return {
        "candidate_ready": bool(stages) and first_failed_stage == "",
        "first_failed_stage": first_failed_stage,
        "stages": dict(stages),
        "metrics": dict(metrics),
    }


def _find_reclaim_candle(
    sweep: object,
    next_candles: Sequence[object],
    direction: str,
    level: float,
) -> object | None:
    candidates = (sweep, *next_candles)
    if direction == "long":
        return next((candle for candle in candidates if float(candle.close) > level), None)
    if direction == "short":
        return next((candle for candle in candidates if float(candle.close) < level), None)
    return None


def _wick_ratio(candle: object, direction: str) -> float:
    candle_range = float(candle.high) - float(candle.low)
    if candle_range <= 0:
        return 0.0
    if direction == "long":
        wick = min(float(candle.open), float(candle.close)) - float(candle.low)
    elif direction == "short":
        wick = float(candle.high) - max(float(candle.open), float(candle.close))
    else:
        wick = 0.0
    return max(wick, 0.0) / candle_range


def _bars_between(first: object, second: object) -> int:
    first_ts = getattr(first, "timestamp_ms", None)
    second_ts = getattr(second, "timestamp_ms", None)
    if first_ts is None or second_ts is None:
        return 0 if first is second else 1
    return 0 if first_ts == second_ts else 1


def _invalidation_level(direction: str, sweep: object, atr: float, params: StrategyParameters) -> float:
    if params.invalidation_mode == "structure_extreme_buffer":
        if direction == "long":
            return float(sweep.low) - params.invalidation_buffer_atr * atr
        return float(sweep.high) + params.invalidation_buffer_atr * atr
    if direction == "long":
        return float(sweep.low) - atr
    return float(sweep.high) + atr


def _volume_config(context_features: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not context_features:
        return {}
    raw = context_features.get("volume")
    return raw if isinstance(raw, Mapping) else {}


def _structure_volume_features(context_features: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not context_features:
        return None
    features = dict(context_features)
    if "structure_timeframe" in features:
        features["entry_timeframe"] = features["structure_timeframe"]
    return features


def _epsilon(config: Mapping[str, Any]) -> float:
    raw = config.get("epsilon", 1e-12)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1e-12
    return value if value > 0 else 1e-12


def _safe_log(value: float, epsilon: float) -> float:
    return math.log(max(float(value), epsilon))


def _rolling_ewma_volume(history: Sequence[object]) -> float:
    if not history:
        return 0.0
    return sum(_candle_volume(candle) for candle in history) / len(history)


def _log_ewma_baseline(history: Sequence[object], *, half_life_days: float, epsilon: float) -> float:
    if not history:
        return 0.0
    alpha = 1.0 - math.exp(math.log(0.5) / max(half_life_days, 1.0))
    value = _safe_log(_candle_volume(history[0]), epsilon)
    for candle in history[1:]:
        value = alpha * _safe_log(_candle_volume(candle), epsilon) + (1.0 - alpha) * value
    return value


def _volume_bucket_key(context_features: Mapping[str, Any] | None, candle: object) -> str:
    asset = ""
    timeframe = ""
    if context_features:
        asset = str(context_features.get("asset", ""))
        timeframe = str(context_features.get("entry_timeframe", context_features.get("timeframe", "")))
    timestamp_ms = int(getattr(candle, "timestamp_ms"))
    current = datetime.fromtimestamp(timestamp_ms / 1000, UTC)
    return f"{asset}|{timeframe}|{current.weekday()}|{current.hour}"


def _volume_result(status: str, evidence: Mapping[str, object]) -> VolumePriceConfirmation:
    payload = {"status": status, **dict(evidence)}
    return VolumePriceConfirmation(status=status, evidence=payload)


__all__ = (
    "MarketRegimeContext",
    "PriceActionSetup",
    "StrategyParameters",
    "VolumePriceConfirmation",
    "build_market_regime",
    "detect_price_action_setup",
    "evaluate_breakout_pullback_diagnostics",
    "evaluate_compression_expansion_diagnostics",
    "evaluate_trend_continuation_diagnostics",
    "confirm_volume_price",
    "minimum_reward_to_risk",
    "strategy_parameters_from_context",
)
