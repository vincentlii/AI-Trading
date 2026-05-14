from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


HIGH_SIGNAL_TO_NOISE_TREND = "HIGH_SIGNAL_TO_NOISE_TREND"
RANDOM_WALK_CHAOS = "RANDOM_WALK_CHAOS"
MEAN_REVERTING_TRANSITION = "MEAN_REVERTING_TRANSITION"


@dataclass(frozen=True)
class DmiAdx:
    adx: float
    plus_di: float
    minus_di: float


def _validate_positive_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be positive")


def _validate_matching_price_lengths(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> None:
    if len(highs) != len(lows) or len(lows) != len(closes):
        raise ValueError("highs, lows, and closes must have the same length")


def true_range(high: float, low: float, previous_close: float) -> float:
    return max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close),
    )


def kaufman_efficiency_ratio(closes: Sequence[float]) -> float:
    if len(closes) < 2:
        return 0.0

    net_change = abs(closes[-1] - closes[0])
    total_movement = sum(abs(current - previous) for previous, current in zip(closes, closes[1:]))

    if total_movement == 0:
        return 0.0
    return net_change / total_movement


def choppiness_index(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float:
    if period <= 1:
        raise ValueError("period must be greater than 1")
    if len(highs) != len(lows) or len(lows) != len(closes):
        raise ValueError("highs, lows, and closes must have the same length")
    if len(closes) < period + 1:
        raise ValueError("choppiness_index requires at least period + 1 prices")

    start = len(closes) - period
    true_range_sum = sum(true_range(highs[index], lows[index], closes[index - 1]) for index in range(start, len(closes)))
    highest_high = max(highs[start:])
    lowest_low = min(lows[start:])
    price_range = highest_high - lowest_low

    if true_range_sum <= 0 or price_range <= 0:
        return 0.0

    return 100.0 * math.log10(true_range_sum / price_range) / math.log10(period)


def classify_regime(er: float, chop: float) -> str:
    if er >= 0.6 and chop <= 38.2:
        return HIGH_SIGNAL_TO_NOISE_TREND
    if er <= 0.3 and chop >= 61.8:
        return RANDOM_WALK_CHAOS
    return MEAN_REVERTING_TRANSITION


def exponential_moving_average(values: Sequence[float], period: int) -> float:
    _validate_positive_period(period)
    if not values:
        raise ValueError("exponential_moving_average requires at least one value")

    smoothing = 2.0 / (period + 1.0)
    ema = float(values[0])
    for value in values[1:]:
        ema = (float(value) * smoothing) + (ema * (1.0 - smoothing))
    return ema


def average_true_range(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float:
    _validate_positive_period(period)
    _validate_matching_price_lengths(highs, lows, closes)
    if len(closes) < period + 1:
        raise ValueError("average_true_range requires at least period + 1 prices")

    start = len(closes) - period
    ranges = (true_range(highs[index], lows[index], closes[index - 1]) for index in range(start, len(closes)))
    return sum(ranges) / period


def directional_movement_index(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> DmiAdx:
    _validate_positive_period(period)
    _validate_matching_price_lengths(highs, lows, closes)
    if len(closes) < period + 1:
        raise ValueError("directional_movement_index requires at least period + 1 prices")

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges: list[float] = []
    for index in range(1, len(closes)):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm.append(up_move if up_move > down_move and up_move > 0.0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0.0 else 0.0)
        true_ranges.append(true_range(highs[index], lows[index], closes[index - 1]))

    latest_plus_di, latest_minus_di, _ = _dmi_window(plus_dm[-period:], minus_dm[-period:], true_ranges[-period:])
    dx_values = []
    for end in range(period, len(true_ranges) + 1):
        _, _, dx = _dmi_window(plus_dm[end - period : end], minus_dm[end - period : end], true_ranges[end - period : end])
        dx_values.append(dx)

    recent_dx_values = dx_values[-period:]
    adx = sum(recent_dx_values) / len(recent_dx_values)
    return DmiAdx(adx=adx, plus_di=latest_plus_di, minus_di=latest_minus_di)


def _dmi_window(
    plus_dm: Sequence[float],
    minus_dm: Sequence[float],
    true_ranges: Sequence[float],
) -> tuple[float, float, float]:
    true_range_sum = sum(true_ranges)
    if true_range_sum == 0.0:
        return 0.0, 0.0, 0.0

    plus_di = 100.0 * sum(plus_dm) / true_range_sum
    minus_di = 100.0 * sum(minus_dm) / true_range_sum
    directional_sum = plus_di + minus_di
    dx = 0.0 if directional_sum == 0.0 else 100.0 * abs(plus_di - minus_di) / directional_sum
    return plus_di, minus_di, dx


def ttm_squeeze_on(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
    bollinger_multiplier: float = 2.0,
    keltner_multiplier: float = 1.5,
) -> bool:
    _validate_positive_period(period)
    _validate_matching_price_lengths(highs, lows, closes)
    if len(closes) < period + 1:
        raise ValueError("ttm_squeeze_on requires at least period + 1 prices")

    recent_closes = [float(value) for value in closes[-period:]]
    average_close = sum(recent_closes) / period
    variance = sum((value - average_close) ** 2 for value in recent_closes) / period
    standard_deviation = math.sqrt(variance)

    bollinger_upper = average_close + (bollinger_multiplier * standard_deviation)
    bollinger_lower = average_close - (bollinger_multiplier * standard_deviation)
    keltner_middle = exponential_moving_average(closes[-period:], period)
    atr = average_true_range(highs, lows, closes, period)
    keltner_upper = keltner_middle + (keltner_multiplier * atr)
    keltner_lower = keltner_middle - (keltner_multiplier * atr)

    return bollinger_lower >= keltner_lower and bollinger_upper <= keltner_upper
