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
) -> PriceActionSetup | None:
    structure = _confirmed_candles(structure_candles)
    entry = _confirmed_candles(entry_candles)
    if regime is None or len(structure) < 5 or not entry:
        return None

    trend_continuation = _detect_trend_continuation(structure, entry, regime)
    if trend_continuation is not None:
        return trend_continuation

    return _detect_liquidity_reversal(structure, entry)


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
    average_volume = _volume_baseline(history, context_features)
    latest_volume = float(latest.volume)
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

    body = abs(float(breakout.close) - float(breakout.open))
    displacement = body >= average_range * 0.5 or (float(breakout.high) - float(breakout.low)) >= average_range * 1.1
    if not displacement:
        return None

    if direction == "long":
        prior_high = max(float(candle.high) for candle in prior)
        has_bos = float(breakout.close) > prior_high
        has_pullback = float(pullback.close) < float(breakout.close) and float(pullback.close) >= prior_high
        if not has_bos or not has_pullback:
            return None
        invalidation = min(float(pullback.low), prior_high) - average_range * 0.25
        entry_low, entry_high = _entry_zone(entry)
        target = float(entry[-1].close) + abs(float(entry[-1].close) - invalidation) * 2.0
    else:
        prior_low = min(float(candle.low) for candle in prior)
        has_bos = float(breakout.close) < prior_low
        has_pullback = float(pullback.close) > float(breakout.close) and float(pullback.close) <= prior_low
        if not has_bos or not has_pullback:
            return None
        invalidation = max(float(pullback.high), prior_low) + average_range * 0.25
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
            "direction": direction,
            "breakout_timestamp_ms": getattr(breakout, "timestamp_ms", None),
            "pullback_timestamp_ms": getattr(pullback, "timestamp_ms", None),
        },
    )


def _detect_liquidity_reversal(
    structure: tuple[object, ...],
    entry: tuple[object, ...],
) -> PriceActionSetup | None:
    average_range = _average_range(structure)
    if average_range <= 0:
        return None

    for index in range(2, len(structure) - 1):
        sweep = structure[index]
        next_candles = structure[index + 1 :]
        previous = structure[index - 1]

        if float(sweep.low) < min(float(candle.low) for candle in structure[:index]):
            choch = next((candle for candle in next_candles if float(candle.close) > float(previous.high)), None)
            if choch is not None:
                invalidation = float(sweep.low) - average_range * 0.1
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
                        "sweep_direction": "down",
                        "sweep_timestamp_ms": getattr(sweep, "timestamp_ms", None),
                        "choch_timestamp_ms": getattr(choch, "timestamp_ms", None),
                    },
                )

        if float(sweep.high) > max(float(candle.high) for candle in structure[:index]):
            choch = next((candle for candle in next_candles if float(candle.close) < float(previous.low)), None)
            if choch is not None:
                invalidation = float(sweep.high) + average_range * 0.1
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
                        "sweep_direction": "up",
                        "sweep_timestamp_ms": getattr(sweep, "timestamp_ms", None),
                        "choch_timestamp_ms": getattr(choch, "timestamp_ms", None),
                    },
                )
    return None


def _confirmed_candles(candles: Sequence[object]) -> tuple[object, ...]:
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _average_range(candles: Sequence[object]) -> float:
    if not candles:
        return 0.0
    return sum(float(candle.high) - float(candle.low) for candle in candles) / len(candles)


def _volume_baseline(history: Sequence[object], context_features: Mapping[str, Any] | None) -> float:
    if context_features and "tod_volume_baseline" in context_features:
        return float(context_features["tod_volume_baseline"])
    return sum(float(candle.volume) for candle in history) / len(history)


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


def _volume_result(status: str, evidence: Mapping[str, object]) -> VolumePriceConfirmation:
    payload = {"status": status, **dict(evidence)}
    return VolumePriceConfirmation(status=status, evidence=payload)


__all__ = (
    "MarketRegimeContext",
    "PriceActionSetup",
    "VolumePriceConfirmation",
    "build_market_regime",
    "detect_price_action_setup",
    "confirm_volume_price",
    "minimum_reward_to_risk",
)
