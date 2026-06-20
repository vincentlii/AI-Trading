from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass


SESSION_HIGH_LOW = "session_high_low"
PREVIOUS_DAY_HIGH_LOW = "previous_day_high_low"
CONFIRMED_SWING = "confirmed_swing"
LEVEL_FAMILIES = (SESSION_HIGH_LOW, PREVIOUS_DAY_HIGH_LOW, CONFIRMED_SWING)


@dataclass(frozen=True)
class LRCausalLevel:
    level_id: str
    family: str
    direction: str
    price: float
    confirmed_time: int
    source_time: int
    touch_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LRCausalEvent:
    event_id: str
    market_event_key: str
    level_id: str
    level_family: str
    direction: str
    sweep_bar_time: int
    sweep_time: int
    reclaim_bar_time: int
    reclaim_time: int
    sweep_extreme: float
    reclaim_close: float
    atr_15m: float
    atr_4h: float
    instrument: str = ""
    level_price: float = 0.0
    level_confirmed_time: int = 0
    level_source_time: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LREntryOrder:
    order_type: str
    active_time: int
    entry_price: float
    ttl_bars: int = 0


@dataclass(frozen=True)
class LREntryCandidate:
    candidate_id: str
    event_id: str
    market_event_key: str
    entry_model: str
    signal_time: int
    order: LREntryOrder
    stop_price: float
    target_price: float


def build_session_levels(
    candles: Sequence[object],
    *,
    cutoff_time: int,
) -> tuple[LRCausalLevel, ...]:
    session_ms = 8 * 60 * 60 * 1000
    grouped: dict[int, list[object]] = defaultdict(list)
    for candle in candles:
        timestamp = int(getattr(candle, "timestamp_ms"))
        grouped[timestamp - timestamp % session_ms].append(candle)
    levels: list[LRCausalLevel] = []
    for start, rows in sorted(grouped.items()):
        confirmed = start + session_ms
        if confirmed > cutoff_time:
            continue
        low_candle = min(rows, key=lambda row: float(getattr(row, "low")))
        high_candle = max(rows, key=lambda row: float(getattr(row, "high")))
        levels.extend(
            (
                _level(SESSION_HIGH_LOW, "long", float(getattr(low_candle, "low")), confirmed, low_candle),
                _level(SESSION_HIGH_LOW, "short", float(getattr(high_candle, "high")), confirmed, high_candle),
            )
        )
    return tuple(levels)


def build_previous_day_levels(
    candles: Sequence[object],
    *,
    cutoff_time: int,
) -> tuple[LRCausalLevel, ...]:
    day_ms = 24 * 60 * 60 * 1000
    grouped: dict[int, list[object]] = defaultdict(list)
    for candle in candles:
        timestamp = int(getattr(candle, "timestamp_ms"))
        grouped[timestamp - timestamp % day_ms].append(candle)
    completed = [(start, rows) for start, rows in sorted(grouped.items()) if start + day_ms <= cutoff_time]
    if not completed:
        return ()
    start, rows = completed[-1]
    confirmed = start + day_ms
    low_candle = min(rows, key=lambda row: float(getattr(row, "low")))
    high_candle = max(rows, key=lambda row: float(getattr(row, "high")))
    return (
        _level(PREVIOUS_DAY_HIGH_LOW, "long", float(getattr(low_candle, "low")), confirmed, low_candle),
        _level(PREVIOUS_DAY_HIGH_LOW, "short", float(getattr(high_candle, "high")), confirmed, high_candle),
    )


def build_all_previous_day_levels(
    candles: Sequence[object],
    *,
    cutoff_time: int,
) -> tuple[LRCausalLevel, ...]:
    day_ms = 24 * 60 * 60 * 1000
    grouped: dict[int, list[object]] = defaultdict(list)
    for candle in candles:
        timestamp = int(getattr(candle, "timestamp_ms"))
        grouped[timestamp - timestamp % day_ms].append(candle)
    levels: list[LRCausalLevel] = []
    for start, rows in sorted(grouped.items()):
        confirmed = start + day_ms
        if confirmed > cutoff_time:
            continue
        low_candle = min(rows, key=lambda row: float(getattr(row, "low")))
        high_candle = max(rows, key=lambda row: float(getattr(row, "high")))
        levels.extend(
            (
                _level(PREVIOUS_DAY_HIGH_LOW, "long", float(getattr(low_candle, "low")), confirmed, low_candle),
                _level(PREVIOUS_DAY_HIGH_LOW, "short", float(getattr(high_candle, "high")), confirmed, high_candle),
            )
        )
    return tuple(levels)


def build_confirmed_swing_levels(
    candles: Sequence[object],
    *,
    cutoff_time: int,
) -> tuple[LRCausalLevel, ...]:
    timeframe_ms = 4 * 60 * 60 * 1000
    levels: list[LRCausalLevel] = []
    for index in range(2, len(candles) - 2):
        left = candles[index - 2 : index]
        pivot = candles[index]
        right = candles[index + 1 : index + 3]
        confirmed = int(getattr(right[-1], "timestamp_ms")) + timeframe_ms
        if confirmed > cutoff_time:
            continue
        low = float(getattr(pivot, "low"))
        high = float(getattr(pivot, "high"))
        neighbors = (*left, *right)
        if all(low < float(getattr(row, "low")) for row in neighbors):
            levels.append(_level(CONFIRMED_SWING, "long", low, confirmed, pivot))
        if all(high > float(getattr(row, "high")) for row in neighbors):
            levels.append(_level(CONFIRMED_SWING, "short", high, confirmed, pivot))
    return tuple(levels)


def detect_causal_events(
    *,
    levels: Sequence[LRCausalLevel],
    candles_15m: Sequence[object],
    atr_15m: object,
    atr_4h: object,
    instrument: str = "",
    max_reclaim_bars: int = 4,
) -> tuple[LRCausalEvent, ...]:
    bar_ms = 15 * 60 * 1000
    events: list[LRCausalEvent] = []
    for level in levels:
        index = 0
        while index < len(candles_15m):
            sweep = candles_15m[index]
            sweep_time = int(getattr(sweep, "timestamp_ms")) + bar_ms
            if sweep_time <= level.confirmed_time or not bool(getattr(sweep, "is_confirmed", False)):
                index += 1
                continue
            depth = _sweep_depth(level, sweep)
            if depth <= 0:
                index += 1
                continue
            event_atr_15m = _resolve_atr(atr_15m, sweep_time)
            event_atr_4h = _resolve_atr(atr_4h, sweep_time)
            if event_atr_15m <= 0 or event_atr_4h <= 0 or depth > event_atr_4h:
                index += 1
                continue
            reclaim_index = _reclaim_index(level, candles_15m, index, max_reclaim_bars)
            if reclaim_index is None:
                index += 1
                continue
            reclaim = candles_15m[reclaim_index]
            reclaim_time = int(getattr(reclaim, "timestamp_ms")) + bar_ms
            market_key = _stable_id(instrument, level.direction, sweep_time, reclaim_time)
            events.append(
                LRCausalEvent(
                    event_id=_stable_id(market_key, level.level_id),
                    market_event_key=market_key,
                    level_id=level.level_id,
                    level_family=level.family,
                    direction=level.direction,
                    sweep_bar_time=int(getattr(sweep, "timestamp_ms")),
                    sweep_time=sweep_time,
                    reclaim_bar_time=int(getattr(reclaim, "timestamp_ms")),
                    reclaim_time=reclaim_time,
                    sweep_extreme=float(getattr(sweep, "low" if level.direction == "long" else "high")),
                    reclaim_close=float(getattr(reclaim, "close")),
                    atr_15m=event_atr_15m,
                    atr_4h=event_atr_4h,
                    instrument=instrument,
                    level_price=level.price,
                    level_confirmed_time=level.confirmed_time,
                    level_source_time=level.source_time,
                )
            )
            break
    return tuple(events)


def _reclaim_index(
    level: LRCausalLevel,
    candles: Sequence[object],
    sweep_index: int,
    max_reclaim_bars: int,
) -> int | None:
    end = min(len(candles), sweep_index + max_reclaim_bars + 1)
    for index in range(sweep_index, end):
        candle = candles[index]
        if not bool(getattr(candle, "is_confirmed", False)):
            continue
        close = float(getattr(candle, "close"))
        if (level.direction == "long" and close > level.price) or (
            level.direction == "short" and close < level.price
        ):
            return index
    return None


def _sweep_depth(level: LRCausalLevel, candle: object) -> float:
    if level.direction == "long":
        return max(0.0, level.price - float(getattr(candle, "low")))
    return max(0.0, float(getattr(candle, "high")) - level.price)


def _resolve_atr(source: object, timestamp: int) -> float:
    value = source(timestamp) if callable(source) else source
    if value in (None, ""):
        return 0.0
    return float(value)


def _level(family: str, direction: str, price: float, confirmed: int, candle: object) -> LRCausalLevel:
    source_time = int(getattr(candle, "timestamp_ms"))
    return LRCausalLevel(
        level_id=_stable_id(family, direction, price, source_time, confirmed),
        family=family,
        direction=direction,
        price=price,
        confirmed_time=confirmed,
        source_time=source_time,
    )


def _stable_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]


__all__ = (
    "CONFIRMED_SWING",
    "LEVEL_FAMILIES",
    "LRCausalEvent",
    "LRCausalLevel",
    "LREntryCandidate",
    "LREntryOrder",
    "PREVIOUS_DAY_HIGH_LOW",
    "SESSION_HIGH_LOW",
    "build_all_previous_day_levels",
    "build_confirmed_swing_levels",
    "build_previous_day_levels",
    "build_session_levels",
    "detect_causal_events",
)
