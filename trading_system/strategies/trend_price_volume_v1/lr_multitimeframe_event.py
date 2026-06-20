from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import LRCausalLevel


ATRSource = Callable[[int], float | None]


@dataclass(frozen=True)
class EventPolicy:
    name: str
    timeframe_ms: int
    max_reclaim_bars: int
    same_bar_only: bool
    expire_level_on_failed_reclaim: bool


EVENT_POLICIES = {
    "15m_micro": EventPolicy("15m_micro", 15 * 60_000, 4, False, False),
    "1H_sweep_reclaim": EventPolicy("1H_sweep_reclaim", 60 * 60_000, 3, False, True),
    "4H_wick_reclaim": EventPolicy("4H_wick_reclaim", 4 * 60 * 60_000, 1, True, True),
}


@dataclass(frozen=True)
class LRMultiTimeframeEvent:
    event_id: str
    physical_event_key: str
    instrument: str
    event_timeframe: str
    timeframe_ms: int
    level_id: str
    level_family: str
    level_price: float
    level_confirmed_time: int
    level_source_time: int
    direction: str
    sweep_start_bar_time: int
    sweep_time: int
    sweep_extreme_bar_time: int
    sweep_extreme: float
    reclaim_bar_time: int
    reclaim_time: int
    signal_time: int
    signal_close: float
    feature_cutoff_time: int
    reclaim_span_bars: int
    sweep_atr: float
    event_atr: float
    bar_confirmed: bool = True
    no_lookahead_safe: bool = True
    proposal_only: bool = True
    formal_conclusion_enabled: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_multitimeframe_events(
    *,
    levels: Sequence[LRCausalLevel],
    candles: Sequence[object],
    atr_at: ATRSource,
    policy: EventPolicy,
    instrument: str = "",
    sweep_depth_cap_at: ATRSource | None = None,
) -> tuple[LRMultiTimeframeEvent, ...]:
    events: list[LRMultiTimeframeEvent] = []
    for level in levels:
        event = _first_event_for_level(
            level=level,
            candles=candles,
            atr_at=atr_at,
            policy=policy,
            instrument=instrument,
            sweep_depth_cap_at=sweep_depth_cap_at,
        )
        if event is not None:
            events.append(event)
    return tuple(events)


def _first_event_for_level(
    *,
    level: LRCausalLevel,
    candles: Sequence[object],
    atr_at: ATRSource,
    policy: EventPolicy,
    instrument: str,
    sweep_depth_cap_at: ATRSource | None,
) -> LRMultiTimeframeEvent | None:
    for sweep_index, sweep in enumerate(candles):
        sweep_close_time = int(getattr(sweep, "timestamp_ms")) + policy.timeframe_ms
        if sweep_close_time <= level.confirmed_time or not bool(getattr(sweep, "is_confirmed", False)):
            continue
        initial_depth = _sweep_depth(level, sweep)
        if initial_depth <= 0:
            continue
        sweep_atr = _positive_atr(atr_at(sweep_close_time))
        if sweep_atr is None:
            continue
        if sweep_depth_cap_at is not None:
            depth_cap = _positive_atr(sweep_depth_cap_at(sweep_close_time))
            if depth_cap is None or initial_depth > depth_cap:
                continue

        end = min(len(candles), sweep_index + policy.max_reclaim_bars)
        extreme = _extreme_price(level.direction, sweep)
        extreme_bar_time = int(getattr(sweep, "timestamp_ms"))
        for reclaim_index in range(sweep_index, end):
            reclaim = candles[reclaim_index]
            if not bool(getattr(reclaim, "is_confirmed", False)):
                break
            candidate_extreme = _extreme_price(level.direction, reclaim)
            if _is_more_extreme(level.direction, candidate_extreme, extreme):
                extreme = candidate_extreme
                extreme_bar_time = int(getattr(reclaim, "timestamp_ms"))
            if not _is_reclaimed(level, reclaim):
                continue

            reclaim_time = int(getattr(reclaim, "timestamp_ms")) + policy.timeframe_ms
            event_atr = _positive_atr(atr_at(reclaim_time))
            if event_atr is None:
                break
            physical_key = _stable_id(
                instrument,
                level.direction,
                policy.name,
                int(getattr(sweep, "timestamp_ms")),
                reclaim_time,
            )
            return LRMultiTimeframeEvent(
                event_id=_stable_id(physical_key, level.level_id),
                physical_event_key=physical_key,
                instrument=instrument,
                event_timeframe=policy.name,
                timeframe_ms=policy.timeframe_ms,
                level_id=level.level_id,
                level_family=level.family,
                level_price=level.price,
                level_confirmed_time=level.confirmed_time,
                level_source_time=level.source_time,
                direction=level.direction,
                sweep_start_bar_time=int(getattr(sweep, "timestamp_ms")),
                sweep_time=sweep_close_time,
                sweep_extreme_bar_time=extreme_bar_time,
                sweep_extreme=extreme,
                reclaim_bar_time=int(getattr(reclaim, "timestamp_ms")),
                reclaim_time=reclaim_time,
                signal_time=reclaim_time,
                signal_close=float(getattr(reclaim, "close")),
                feature_cutoff_time=reclaim_time,
                reclaim_span_bars=reclaim_index - sweep_index + 1,
                sweep_atr=sweep_atr,
                event_atr=event_atr,
            )
        if policy.expire_level_on_failed_reclaim:
            return None
    return None


def _sweep_depth(level: LRCausalLevel, candle: object) -> float:
    if level.direction == "long":
        return max(0.0, level.price - float(getattr(candle, "low")))
    return max(0.0, float(getattr(candle, "high")) - level.price)


def _extreme_price(direction: str, candle: object) -> float:
    return float(getattr(candle, "low" if direction == "long" else "high"))


def _is_more_extreme(direction: str, candidate: float, current: float) -> bool:
    return candidate < current if direction == "long" else candidate > current


def _is_reclaimed(level: LRCausalLevel, candle: object) -> bool:
    close = float(getattr(candle, "close"))
    return close > level.price if level.direction == "long" else close < level.price


def _positive_atr(value: float | None) -> float | None:
    if value is None or float(value) <= 0:
        return None
    return float(value)


def _stable_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


__all__ = [
    "EVENT_POLICIES",
    "EventPolicy",
    "LRMultiTimeframeEvent",
    "detect_multitimeframe_events",
]
