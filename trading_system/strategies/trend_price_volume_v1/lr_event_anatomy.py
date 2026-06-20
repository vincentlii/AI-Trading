from __future__ import annotations

from collections.abc import Sequence

from trading_system.strategies.trend_price_volume_v1.lr_multitimeframe_event import LRMultiTimeframeEvent


BAR_15M_MS = 15 * 60_000
HORIZONS_MINUTES = (15, 30, 60, 120, 240, 480, 1200)
R_THRESHOLDS = (0.5, 1.0, 1.5, 2.0)


def build_event_anatomy(
    event: LRMultiTimeframeEvent,
    future_15m: Sequence[object],
) -> dict[str, object]:
    if event.event_atr <= 0:
        raise ValueError("event anatomy requires positive event ATR")
    invalidation = (
        event.sweep_extreme - 0.10 * event.event_atr
        if event.direction == "long"
        else event.sweep_extreme + 0.10 * event.event_atr
    )
    risk = abs(event.signal_close - invalidation)
    if risk <= 0:
        raise ValueError("event anatomy requires positive diagnostic R")
    path = [
        candle
        for candle in future_15m
        if bool(getattr(candle, "is_confirmed", False))
        and int(getattr(candle, "timestamp_ms")) >= event.signal_time
        and int(getattr(candle, "timestamp_ms")) + BAR_15M_MS <= event.signal_time + 1200 * 60_000
    ]
    close_by_time = {
        int(getattr(candle, "timestamp_ms")) + BAR_15M_MS: float(getattr(candle, "close"))
        for candle in path
    }
    row: dict[str, object] = {
        "row_type": "event_anatomy",
        "row_role": "diagnostic_label",
        "event_id": event.event_id,
        "physical_event_key": event.physical_event_key,
        "instrument": event.instrument,
        "event_timeframe": event.event_timeframe,
        "level_family": event.level_family,
        "direction": event.direction,
        "signal_time": event.signal_time,
        "signal_close": event.signal_close,
        "event_atr": event.event_atr,
        "invalidation_price": invalidation,
        "diagnostic_r_size": risk,
        "path_bars": len(path),
        "label_min_source_time": _source_close_time(path[0]) if path else None,
        "label_max_source_time": _source_close_time(path[-1]) if path else None,
        "proposal_only": True,
        "eligible_for_performance": False,
        "formal_conclusion_enabled": False,
    }
    for minutes in HORIZONS_MINUTES:
        price = close_by_time.get(event.signal_time + minutes * 60_000)
        signed = _signed_change(event.direction, event.signal_close, price) if price is not None else None
        row[f"future_price_{minutes}m"] = price
        row[f"forward_{minutes}m_R"] = signed / risk if signed is not None else None
        row[f"forward_{minutes}m_ATR"] = signed / event.event_atr if signed is not None else None

    favorable, adverse = _path_excursions(event, path)
    row["MFE_R"] = favorable / risk
    row["MAE_R"] = adverse / risk
    row["MFE_ATR"] = favorable / event.event_atr
    row["MAE_ATR"] = adverse / event.event_atr

    threshold_times, invalidation_minutes = _ordered_path_outcomes(event, path, invalidation, risk)
    for threshold in R_THRESHOLDS:
        name = str(threshold).replace(".", "_").removesuffix("_0")
        row[f"time_to_{name}R_minutes"] = threshold_times[threshold]
    half_r = threshold_times[0.5]
    one_r = threshold_times[1.0]
    if half_r is not None and half_r <= 240:
        row["follow_through_status"] = "follow_through"
    elif invalidation_minutes is not None and invalidation_minutes <= 240:
        row["follow_through_status"] = "invalidation_first"
    else:
        row["follow_through_status"] = "unresolved"
    if one_r is not None:
        row["invalidation_first_status"] = "one_r_first"
    elif invalidation_minutes is not None:
        row["invalidation_first_status"] = "invalidation_first"
    else:
        row["invalidation_first_status"] = "unresolved"
    row["invalidation_time_minutes"] = invalidation_minutes
    return row


def _path_excursions(event: LRMultiTimeframeEvent, path: Sequence[object]) -> tuple[float, float]:
    if not path:
        return 0.0, 0.0
    if event.direction == "long":
        favorable = max(0.0, max(float(getattr(row, "high")) for row in path) - event.signal_close)
        adverse = max(0.0, event.signal_close - min(float(getattr(row, "low")) for row in path))
    else:
        favorable = max(0.0, event.signal_close - min(float(getattr(row, "low")) for row in path))
        adverse = max(0.0, max(float(getattr(row, "high")) for row in path) - event.signal_close)
    return favorable, adverse


def _ordered_path_outcomes(
    event: LRMultiTimeframeEvent,
    path: Sequence[object],
    invalidation: float,
    risk: float,
) -> tuple[dict[float, int | None], int | None]:
    threshold_times: dict[float, int | None] = {threshold: None for threshold in R_THRESHOLDS}
    invalidation_minutes: int | None = None
    for candle in path:
        minutes = int((_source_close_time(candle) - event.signal_time) / 60_000)
        invalidated = (
            float(getattr(candle, "low")) <= invalidation
            if event.direction == "long"
            else float(getattr(candle, "high")) >= invalidation
        )
        if invalidated:
            invalidation_minutes = minutes
            break
        favorable_extreme = (
            float(getattr(candle, "high"))
            if event.direction == "long"
            else float(getattr(candle, "low"))
        )
        for threshold in R_THRESHOLDS:
            if threshold_times[threshold] is not None:
                continue
            target = (
                event.signal_close + threshold * risk
                if event.direction == "long"
                else event.signal_close - threshold * risk
            )
            reached = favorable_extreme >= target if event.direction == "long" else favorable_extreme <= target
            if reached:
                threshold_times[threshold] = minutes
    return threshold_times, invalidation_minutes


def _signed_change(direction: str, reference: float, future: float) -> float:
    return future - reference if direction == "long" else reference - future


def _source_close_time(candle: object) -> int:
    return int(getattr(candle, "timestamp_ms")) + BAR_15M_MS


__all__ = ["HORIZONS_MINUTES", "build_event_anatomy"]
