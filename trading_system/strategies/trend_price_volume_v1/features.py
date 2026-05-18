from __future__ import annotations

import math
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
    breakout_buffer_atr: float = 0.5
    breakout_body_ratio_min: float = 0.7
    breakout_close_location_max: float = 0.2
    breakout_rvol_min: float = 2.0
    pullback_rvol_max: float = 0.8
    restart_rvol_min: float = 1.5
    sweep_max_atr_multiple: float = 1.5
    sweep_wick_ratio_min: float = 0.25
    sweep_rvol_min: float = 1.5
    countertrend_sweep_rvol_min: float = 2.0
    reclaim_max_bars: int = 5


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
) -> PriceActionSetup | None:
    structure = _confirmed_candles(structure_candles)
    entry = _confirmed_candles(entry_candles)
    if regime is None or len(structure) < 5 or not entry:
        return None

    params = parameters or StrategyParameters()
    trend_continuation = _detect_trend_continuation(structure, entry, regime, params)
    if trend_continuation is not None:
        return trend_continuation

    return _detect_liquidity_reversal(structure, entry, regime, params)


def confirm_volume_price(
    entry_candles: Sequence[object],
    direction: str,
    context_features: Mapping[str, Any] | None = None,
) -> VolumePriceConfirmation:
    confirmed = _confirmed_candles(entry_candles)
    if len(confirmed) < 2:
        return _volume_result("cooldown", {"reason": "insufficient_confirmed_candles"})

    latest = confirmed[-1]
    history = confirmed[-21:-1] if len(confirmed) >= 21 else confirmed[:-1]
    average_volume, volume_source = _volume_baseline(history, context_features)
    latest_volume = _candle_volume(latest)
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
    }
    if context_features and "ttm_squeeze_on" in context_features:
        evidence["ttm_squeeze_on"] = bool(context_features["ttm_squeeze_on"])
    return _volume_result(status, evidence)


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
) -> PriceActionSetup | None:
    if regime.status != "TREND" or regime.direction not in {"long", "short"} or len(structure) < 6:
        return None

    direction = regime.direction
    prior = structure[:-2]
    breakout = structure[-2]
    pullback = structure[-1]
    average_range = _average_range(structure[:-1])
    if average_range <= 0:
        return None

    volume_baseline, _ = _volume_baseline(prior[-20:], None)
    if volume_baseline <= 0:
        return None

    breakout_rvol = _candle_volume(breakout) / volume_baseline
    pullback_rvol = _candle_volume(pullback) / volume_baseline
    if breakout_rvol < params.breakout_rvol_min or pullback_rvol > params.pullback_rvol_max:
        return None

    atr = regime.atr if regime.atr > 0 else average_range
    body = abs(float(breakout.close) - float(breakout.open))
    breakout_range = float(breakout.high) - float(breakout.low)
    if breakout_range <= 0:
        return None

    body_ratio = body / breakout_range
    if body_ratio < params.breakout_body_ratio_min:
        return None

    if direction == "long":
        prior_high = max(float(candle.high) for candle in prior)
        close_location = (float(breakout.high) - float(breakout.close)) / breakout_range
        breakout_midpoint = (float(breakout.open) + float(breakout.close)) / 2.0
        has_bos = float(breakout.close) > prior_high + atr * params.breakout_buffer_atr
        pullback_holds_midpoint = float(pullback.low) >= breakout_midpoint and float(pullback.close) >= prior_high
        has_pullback = float(pullback.close) < float(breakout.close) and pullback_holds_midpoint
        restart_confirmed = _restart_confirms(entry, "long", params)
        if (
            not has_bos
            or close_location > params.breakout_close_location_max
            or not has_pullback
            or not restart_confirmed
        ):
            return None
        invalidation = min(float(pullback.low), prior_high) - atr
        entry_low, entry_high = _entry_zone(entry)
        target = float(entry[-1].close) + abs(float(entry[-1].close) - invalidation) * 2.0
    else:
        prior_low = min(float(candle.low) for candle in prior)
        close_location = (float(breakout.close) - float(breakout.low)) / breakout_range
        breakout_midpoint = (float(breakout.open) + float(breakout.close)) / 2.0
        has_bos = float(breakout.close) < prior_low - atr * params.breakout_buffer_atr
        pullback_holds_midpoint = float(pullback.high) <= breakout_midpoint and float(pullback.close) <= prior_low
        has_pullback = float(pullback.close) > float(breakout.close) and pullback_holds_midpoint
        restart_confirmed = _restart_confirms(entry, "short", params)
        if (
            not has_bos
            or close_location > params.breakout_close_location_max
            or not has_pullback
            or not restart_confirmed
        ):
            return None
        invalidation = max(float(pullback.high), prior_low) + atr
        entry_low, entry_high = _entry_zone(entry)
        target = float(entry[-1].close) - abs(invalidation - float(entry[-1].close)) * 2.0

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
            "breakout_rvol": breakout_rvol,
            "pullback_rvol": pullback_rvol,
            "breakout_body_ratio": body_ratio,
            "breakout_close_location": close_location,
            "breakout_buffer_atr": params.breakout_buffer_atr,
            "pullback_holds_midpoint": pullback_holds_midpoint,
            "restart_confirmation": restart_confirmed,
        },
    )


def _detect_liquidity_reversal(
    structure: tuple[object, ...],
    entry: tuple[object, ...],
    regime: MarketRegimeContext,
    params: StrategyParameters,
) -> PriceActionSetup | None:
    average_range = _average_range(structure)
    if average_range <= 0:
        return None

    atr = regime.atr if regime.atr > 0 else average_range
    for index in range(2, len(structure) - 1):
        sweep = structure[index]
        next_candles = structure[index + 1 : index + 1 + params.reclaim_max_bars]
        previous = structure[index - 1]
        volume_baseline, _ = _volume_baseline(structure[:index][-20:], None)
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
            if (
                reclaim is not None
                and choch is not None
                and downside_deviation <= atr * params.sweep_max_atr_multiple
                and wick_ratio >= params.sweep_wick_ratio_min
                and sweep_rvol >= required_rvol
            ):
                reclaim_bars = _bars_between(sweep, reclaim)
                invalidation = float(sweep.low) - atr
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
                        "countertrend": countertrend,
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
            if (
                reclaim is not None
                and choch is not None
                and upside_deviation <= atr * params.sweep_max_atr_multiple
                and wick_ratio >= params.sweep_wick_ratio_min
                and sweep_rvol >= required_rvol
            ):
                reclaim_bars = _bars_between(sweep, reclaim)
                invalidation = float(sweep.high) + atr
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
                        "countertrend": countertrend,
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
    return StrategyParameters(**values)


def _confirmed_candles(candles: Sequence[object]) -> tuple[object, ...]:
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _average_range(candles: Sequence[object]) -> float:
    if not candles:
        return 0.0
    return sum(float(candle.high) - float(candle.low) for candle in candles) / len(candles)


def _volume_baseline(history: Sequence[object], context_features: Mapping[str, Any] | None) -> tuple[float, str]:
    if context_features and "tod_volume_baseline" in context_features:
        return (float(context_features["tod_volume_baseline"]), "tod")
    source = "quote" if any(_has_quote_volume(candle) for candle in history) else "base"
    return (sum(_candle_volume(candle) for candle in history) / len(history), source)


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
    if len(entry) < 2:
        return False
    latest = entry[-1]
    previous = entry[-4:-1] if len(entry) >= 4 else entry[:-1]
    baseline, _ = _volume_baseline(previous[-20:], None)
    latest_rvol = _candle_volume(latest) / baseline if baseline > 0 else 0.0
    if latest_rvol < params.restart_rvol_min or not _price_accepts_direction(latest, direction):
        return False
    if direction == "long":
        return float(latest.close) > max(float(candle.high) for candle in previous)
    if direction == "short":
        return float(latest.close) < min(float(candle.low) for candle in previous)
    return False


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
    "confirm_volume_price",
    "minimum_reward_to_risk",
    "strategy_parameters_from_context",
)
