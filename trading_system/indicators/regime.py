from __future__ import annotations

import math
from collections.abc import Sequence


HIGH_SIGNAL_TO_NOISE_TREND = "HIGH_SIGNAL_TO_NOISE_TREND"
RANDOM_WALK_CHAOS = "RANDOM_WALK_CHAOS"
MEAN_REVERTING_TRANSITION = "MEAN_REVERTING_TRANSITION"


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
