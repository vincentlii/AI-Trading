from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from trading_system.strategies.trend_price_volume_v1.lr_multitimeframe_event import LRMultiTimeframeEvent


BASELINE_BARS = 20
PERCENTILE_LOOKBACK_BARS = 100


def build_vpa_feature_row(
    event: LRMultiTimeframeEvent,
    candles: Sequence[object],
) -> dict[str, object]:
    indexes = _timestamp_indexes(candles)
    sweep_index = indexes[event.sweep_extreme_bar_time]
    reclaim_index = indexes[event.reclaim_bar_time]
    sweep = candles[sweep_index]
    reclaim = candles[reclaim_index]
    sweep_stats = _causal_bar_stats(candles, sweep_index)
    reclaim_stats = _causal_bar_stats(candles, reclaim_index)
    event_rows = candles[indexes[event.sweep_start_bar_time] : reclaim_index + 1]
    sweep_baseline = _prior_values(candles, sweep_index, BASELINE_BARS, _volume)
    combined_ratio = None
    if len(sweep_baseline) >= BASELINE_BARS:
        baseline = median(sweep_baseline)
        if baseline > 0 and event_rows:
            combined_ratio = sum(_volume(row) for row in event_rows) / (baseline * len(event_rows))
    source_close_times = [int(getattr(row, "timestamp_ms")) + event.timeframe_ms for row in event_rows]
    return {
        "row_type": "vpa_feature",
        "row_role": "tradable_feature",
        "event_id": event.event_id,
        "physical_event_key": event.physical_event_key,
        "instrument": event.instrument,
        "event_timeframe": event.event_timeframe,
        "level_family": event.level_family,
        "direction": event.direction,
        "signal_time": event.signal_time,
        "feature_cutoff_time": event.signal_time,
        "max_source_time": max(source_close_times),
        "sweep_relative_volume": sweep_stats["relative_volume"],
        "reclaim_relative_volume": reclaim_stats["relative_volume"],
        "sweep_volume_percentile": sweep_stats["volume_percentile"],
        "reclaim_volume_percentile": reclaim_stats["volume_percentile"],
        "sweep_volume_bucket": _percentile_bucket(sweep_stats["volume_percentile"]),
        "reclaim_volume_bucket": _percentile_bucket(reclaim_stats["volume_percentile"]),
        "sweep_range_expansion": sweep_stats["range_expansion"],
        "reclaim_range_expansion": reclaim_stats["range_expansion"],
        "sweep_baseline_samples": sweep_stats["baseline_samples"],
        "reclaim_baseline_samples": reclaim_stats["baseline_samples"],
        "sweep_percentile_samples": sweep_stats["percentile_samples"],
        "reclaim_percentile_samples": reclaim_stats["percentile_samples"],
        "wick_ratio": _directional_wick_ratio(sweep, event.direction),
        "close_location_value": _directional_close_location(sweep, event.direction),
        "combined_volume_ratio": combined_ratio,
        "proposal_only": True,
        "eligible_for_performance": False,
        "formal_conclusion_enabled": False,
    }


def build_post_signal_volume_label(
    event: LRMultiTimeframeEvent,
    candles: Sequence[object],
) -> dict[str, object]:
    indexes = _timestamp_indexes(candles)
    reclaim_index = indexes[event.reclaim_bar_time]
    future = list(candles[reclaim_index + 1 : reclaim_index + 4])
    confirmed = [row for row in future if bool(getattr(row, "is_confirmed", False))]
    follow_relative = None
    if confirmed:
        first_index = indexes[int(getattr(confirmed[0], "timestamp_ms"))]
        follow_relative = _causal_bar_stats(candles, first_index)["relative_volume"]
    post_ratio = None
    reclaim_volume = _volume(candles[reclaim_index])
    if confirmed and reclaim_volume > 0:
        post_ratio = sum(_volume(row) for row in confirmed) / len(confirmed) / reclaim_volume
    source_times = [int(getattr(row, "timestamp_ms")) + event.timeframe_ms for row in confirmed]
    return {
        "row_type": "post_signal_volume_label",
        "row_role": "diagnostic_label",
        "event_id": event.event_id,
        "physical_event_key": event.physical_event_key,
        "instrument": event.instrument,
        "event_timeframe": event.event_timeframe,
        "signal_time": event.signal_time,
        "min_source_time": min(source_times) if source_times else None,
        "max_source_time": max(source_times) if source_times else None,
        "follow_through_relative_volume": follow_relative,
        "post_reclaim_volume_ratio_3": post_ratio,
        "post_reclaim_volume_phase": _volume_phase(post_ratio),
        "future_bars_available": len(confirmed),
        "proposal_only": True,
        "eligible_for_performance": False,
        "formal_conclusion_enabled": False,
    }


def _causal_bar_stats(candles: Sequence[object], index: int) -> dict[str, object]:
    baseline_volume = _prior_values(candles, index, BASELINE_BARS, _volume)
    baseline_range = _prior_values(candles, index, BASELINE_BARS, _range)
    percentile_values = _prior_values(candles, index, PERCENTILE_LOOKBACK_BARS, _volume)
    relative_volume = None
    range_expansion = None
    volume_percentile = None
    if len(baseline_volume) >= BASELINE_BARS:
        volume_center = median(baseline_volume)
        range_center = median(baseline_range)
        relative_volume = _safe_ratio(_volume(candles[index]), volume_center)
        range_expansion = _safe_ratio(_range(candles[index]), range_center)
    if len(percentile_values) >= BASELINE_BARS:
        current = _volume(candles[index])
        volume_percentile = sum(value < current for value in percentile_values) / len(percentile_values)
    return {
        "relative_volume": relative_volume,
        "range_expansion": range_expansion,
        "volume_percentile": volume_percentile,
        "baseline_samples": len(baseline_volume),
        "percentile_samples": len(percentile_values),
    }


def _prior_values(candles: Sequence[object], index: int, count: int, getter) -> list[float]:
    rows = candles[max(0, index - count) : index]
    return [getter(row) for row in rows if bool(getattr(row, "is_confirmed", False))]


def _timestamp_indexes(candles: Sequence[object]) -> dict[int, int]:
    return {int(getattr(row, "timestamp_ms")): index for index, row in enumerate(candles)}


def _volume(candle: object) -> float:
    return float(getattr(candle, "volume"))


def _range(candle: object) -> float:
    return float(getattr(candle, "high")) - float(getattr(candle, "low"))


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _directional_wick_ratio(candle: object, direction: str) -> float:
    high = float(getattr(candle, "high"))
    low = float(getattr(candle, "low"))
    open_price = float(getattr(candle, "open"))
    close = float(getattr(candle, "close"))
    span = high - low
    if span <= 0:
        return 0.0
    wick = min(open_price, close) - low if direction == "long" else high - max(open_price, close)
    return max(0.0, wick) / span


def _directional_close_location(candle: object, direction: str) -> float:
    high = float(getattr(candle, "high"))
    low = float(getattr(candle, "low"))
    close = float(getattr(candle, "close"))
    span = high - low
    if span <= 0:
        return 0.0
    value = (close - low) / span if direction == "long" else (high - close) / span
    return min(1.0, max(0.0, value))


def _percentile_bucket(value: object) -> str | None:
    if value is None:
        return None
    number = float(value)
    if number < 0.25:
        return "q1"
    if number < 0.50:
        return "q2"
    if number < 0.75:
        return "q3"
    return "q4"


def _volume_phase(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.8:
        return "contraction"
    if value > 1.2:
        return "expansion"
    return "neutral"


__all__ = ["build_post_signal_volume_label", "build_vpa_feature_row"]
