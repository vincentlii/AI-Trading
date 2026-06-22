from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from trading_system.data.okx_cli import Candle


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
FOUR_HOURS_MS = 4 * 60 * 60 * 1000


@dataclass(frozen=True)
class StrictBpPolicy:
    breakout_atr_buffer: float = 0.10
    minimum_body_ratio: float = 0.50
    close_location_fraction: float = 1.0 / 3.0
    swing_left_bars: int = 2
    swing_right_bars: int = 2
    level_half_width_atr: float = 0.06
    pullback_wick_tolerance_atr: float = 0.10
    shallow_retrace_min: float = 0.25
    shallow_retrace_max: float = 0.60
    bos_lookback_bars: int = 3
    bos_max_bars: int = 8


@dataclass(frozen=True)
class StrictLevel:
    level_id: str
    family: str
    direction: str
    price: float
    lower: float
    upper: float
    source_bar_time: int
    confirmed_time: int
    reaction_count: int


@dataclass(frozen=True)
class BosResult:
    status: str
    confirmation_bar_time: int | None = None
    signal_time: int | None = None
    entry_time: int | None = None
    confirmation_price: float | None = None


@dataclass(frozen=True)
class StrictBpEvent:
    event_id: str
    physical_event_key: str
    instrument: str
    setup: str
    level_id: str
    level_family: str
    direction: str
    level_price: float
    breakout_time: int
    acceptance_time: int
    pullback_time: int
    signal_time: int
    entry_time: int
    signal_price: float
    invalidation: float
    atr_4h: float
    trend_state: str


def breakout_direction(
    row: Candle,
    level: StrictLevel,
    *,
    atr: float,
    policy: StrictBpPolicy,
) -> str | None:
    bar_range = row.high - row.low
    if atr <= 0 or bar_range <= 0:
        return None
    body_ratio = abs(row.close - row.open) / bar_range
    if body_ratio < policy.minimum_body_ratio:
        return None
    buffer = atr * policy.breakout_atr_buffer
    clv = (row.close - row.low) / bar_range
    if level.direction == "long":
        if row.close < level.upper + buffer:
            return None
        return "long" if clv >= 1.0 - policy.close_location_fraction else None
    if row.close > level.lower - buffer:
        return None
    return "short" if clv <= policy.close_location_fraction else None


def confirmed_swing_levels(
    rows: Sequence[Candle],
    *,
    atr_values: Sequence[float],
    policy: StrictBpPolicy,
) -> tuple[StrictLevel, ...]:
    levels: list[StrictLevel] = []
    left = policy.swing_left_bars
    right = policy.swing_right_bars
    for index in range(left, len(rows) - right):
        row = rows[index]
        before = rows[index - left:index]
        after = rows[index + 1:index + right + 1]
        atr = atr_values[index]
        if atr <= 0:
            continue
        confirmed_time = rows[index + right].timestamp_ms + FOUR_HOURS_MS
        half_width = atr * policy.level_half_width_atr
        if all(row.high > peer.high for peer in (*before, *after)):
            levels.append(_level(row, "long", row.high, half_width, confirmed_time))
        if all(row.low < peer.low for peer in (*before, *after)):
            levels.append(_level(row, "short", row.low, half_width, confirmed_time))
    return tuple(levels)


def structural_trend_direction(
    levels: Sequence[StrictLevel],
    *,
    cutoff_time: int,
) -> str:
    available = [row for row in levels if row.confirmed_time <= cutoff_time]
    highs = sorted((row for row in available if row.direction == "long"), key=lambda row: row.confirmed_time)
    lows = sorted((row for row in available if row.direction == "short"), key=lambda row: row.confirmed_time)
    if len(highs) < 2 or len(lows) < 2:
        return "unknown"
    higher = highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price
    lower = highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price
    if higher:
        return "long"
    if lower:
        return "short"
    return "unknown"


def repeated_boundary_levels(
    swings: Sequence[StrictLevel],
    *,
    atr: float,
    minimum_separation_ms: int = 3 * FOUR_HOURS_MS,
) -> tuple[StrictLevel, ...]:
    output: list[StrictLevel] = []
    for index, first in enumerate(swings):
        for second in swings[index + 1:]:
            if first.direction != second.direction:
                continue
            if second.source_bar_time - first.source_bar_time < minimum_separation_ms:
                continue
            if abs(second.price - first.price) > 0.15 * atr:
                continue
            price = (first.price + second.price) / 2.0
            half_width = max(abs(first.upper - first.price), abs(second.upper - second.price))
            output.append(StrictLevel(
                level_id=f"boundary-{first.direction}-{first.source_bar_time}-{second.source_bar_time}",
                family="repeated_boundary",
                direction=first.direction,
                price=price,
                lower=price - half_width,
                upper=price + half_width,
                source_bar_time=second.source_bar_time,
                confirmed_time=max(first.confirmed_time, second.confirmed_time),
                reaction_count=2,
            ))
            break
    return tuple(output)


def pullback_is_valid(
    row: Candle,
    *,
    direction: str,
    level: StrictLevel,
    atr: float,
    setup: str,
    impulse_start: float,
    impulse_extreme: float,
    policy: StrictBpPolicy,
) -> bool:
    tolerance = atr * policy.pullback_wick_tolerance_atr
    if setup == "strict_level_retest_v1":
        if direction == "long":
            return row.low <= level.upper + tolerance and row.low >= level.lower - tolerance and row.close >= level.price
        return row.high >= level.lower - tolerance and row.high <= level.upper + tolerance and row.close <= level.price
    if setup != "strict_shallow_pullback_v1":
        raise ValueError(f"unsupported setup: {setup}")
    impulse = abs(impulse_extreme - impulse_start)
    if impulse <= 0:
        return False
    if direction == "long":
        retrace = (impulse_extreme - row.low) / impulse
        outside = row.low > level.upper and row.close > level.upper
    else:
        retrace = (row.high - impulse_extreme) / impulse
        outside = row.high < level.lower and row.close < level.lower
    return outside and policy.shallow_retrace_min <= retrace <= policy.shallow_retrace_max


def find_first_15m_bos(
    rows: Sequence[Candle],
    *,
    direction: str,
    observation_start: int,
    invalidation: float,
    policy: StrictBpPolicy,
) -> BosResult:
    eligible = [index for index, row in enumerate(rows) if row.is_confirmed and row.timestamp_ms >= observation_start]
    for index in eligible[:policy.bos_max_bars]:
        row = rows[index]
        if direction == "long" and row.low <= invalidation:
            return BosResult(status="failed_before_confirmation")
        if direction == "short" and row.high >= invalidation:
            return BosResult(status="failed_before_confirmation")
        if index < policy.bos_lookback_bars:
            continue
        prior = rows[index - policy.bos_lookback_bars:index]
        midpoint = (row.high + row.low) / 2.0
        confirmed = (
            row.close > max(peer.high for peer in prior) and row.close >= midpoint
            if direction == "long"
            else row.close < min(peer.low for peer in prior) and row.close <= midpoint
        )
        if confirmed:
            signal_time = row.timestamp_ms + FIFTEEN_MINUTES_MS
            return BosResult(
                status="confirmed",
                confirmation_bar_time=row.timestamp_ms,
                signal_time=signal_time,
                entry_time=signal_time + FIFTEEN_MINUTES_MS,
                confirmation_price=row.close,
            )
    return BosResult(status="no_confirmation")


def causal_atr(rows: Sequence[Candle], period: int = 14) -> tuple[float, ...]:
    values: list[float] = []
    true_ranges: list[float] = []
    for index, row in enumerate(rows):
        previous_close = rows[index - 1].close if index else row.close
        true_ranges.append(max(row.high - row.low, abs(row.high - previous_close), abs(row.low - previous_close)))
        window = true_ranges[max(0, index - period + 1):index + 1]
        values.append(sum(window) / len(window))
    return tuple(values)


def scan_strict_bp_events(
    *,
    instrument: str,
    candles_4h: Sequence[Candle],
    candles_15m: Sequence[Candle],
    start_ms: int,
    end_ms: int,
    policy: StrictBpPolicy | None = None,
) -> tuple[StrictBpEvent, ...]:
    policy = policy or StrictBpPolicy()
    atrs = causal_atr(candles_4h)
    swings = confirmed_swing_levels(candles_4h, atr_values=atrs, policy=policy)
    levels = (*swings, *repeated_boundary_levels(swings, atr=median_atr(atrs)))
    output: list[StrictBpEvent] = []
    used: set[tuple[str, str]] = set()
    for level in levels:
        first_index = next((i for i, row in enumerate(candles_4h) if row.timestamp_ms >= level.confirmed_time), None)
        if first_index is None:
            continue
        for breakout_index in range(first_index, len(candles_4h) - 2):
            breakout = candles_4h[breakout_index]
            if breakout.timestamp_ms > end_ms:
                break
            direction = breakout_direction(breakout, level, atr=atrs[breakout_index], policy=policy)
            if direction is None or (level.level_id, direction) in used:
                continue
            cutoff = breakout.timestamp_ms + FOUR_HOURS_MS
            trend = structural_trend_direction(levels, cutoff_time=cutoff)
            if trend != direction:
                continue
            acceptance_index = breakout_index + 1
            acceptance = candles_4h[acceptance_index]
            atr = atrs[breakout_index]
            separated = (
                acceptance.close >= level.upper + 0.25 * atr
                if direction == "long"
                else acceptance.close <= level.lower - 0.25 * atr
            )
            if not separated:
                continue
            impulse_start = level.upper if direction == "long" else level.lower
            impulse_extreme = max(breakout.high, acceptance.high) if direction == "long" else min(breakout.low, acceptance.low)
            matched = False
            for setup, max_bars in (("strict_level_retest_v1", 12), ("strict_shallow_pullback_v1", 8)):
                for pullback_index in range(acceptance_index + 1, min(len(candles_4h), acceptance_index + max_bars + 1)):
                    pullback = candles_4h[pullback_index]
                    if pullback.timestamp_ms > end_ms:
                        break
                    if not pullback_is_valid(
                        pullback,
                        direction=direction,
                        level=level,
                        atr=atrs[pullback_index],
                        setup=setup,
                        impulse_start=impulse_start,
                        impulse_extreme=impulse_extreme,
                        policy=policy,
                    ):
                        continue
                    invalidation = level.lower - 0.10 * atr if direction == "long" else level.upper + 0.10 * atr
                    bos = find_first_15m_bos(
                        candles_15m,
                        direction=direction,
                        observation_start=pullback.timestamp_ms + FOUR_HOURS_MS,
                        invalidation=invalidation,
                        policy=policy,
                    )
                    if bos.status != "confirmed" or bos.signal_time is None or bos.entry_time is None or bos.confirmation_price is None:
                        break
                    if not (start_ms <= bos.signal_time <= end_ms and bos.signal_time < bos.entry_time):
                        break
                    physical = f"{instrument}:{level.level_id}:{breakout.timestamp_ms}:{direction}"
                    event_id = f"{physical}:{setup}"
                    output.append(
                        StrictBpEvent(
                            event_id=event_id,
                            physical_event_key=physical,
                            instrument=instrument,
                            setup=setup,
                            level_id=level.level_id,
                            level_family=level.family,
                            direction=direction,
                            level_price=level.price,
                            breakout_time=breakout.timestamp_ms + FOUR_HOURS_MS,
                            acceptance_time=acceptance.timestamp_ms + FOUR_HOURS_MS,
                            pullback_time=pullback.timestamp_ms + FOUR_HOURS_MS,
                            signal_time=bos.signal_time,
                            entry_time=bos.entry_time,
                            signal_price=bos.confirmation_price,
                            invalidation=invalidation,
                            atr_4h=atrs[pullback_index],
                            trend_state=trend,
                        )
                    )
                    matched = True
                    break
            if matched:
                used.add((level.level_id, direction))
                break
    deduplicated: dict[tuple[str, int, str, str], StrictBpEvent] = {}
    for event in output:
        key = (event.instrument, event.breakout_time, event.direction, event.setup)
        current = deduplicated.get(key)
        if current is None or abs(event.signal_price - event.level_price) < abs(current.signal_price - current.level_price):
            physical = f"{event.instrument}:{event.breakout_time}:{event.direction}"
            deduplicated[key] = replace(
                event,
                event_id=f"{physical}:{event.setup}",
                physical_event_key=physical,
            )
    return tuple(sorted(deduplicated.values(), key=lambda row: (row.signal_time, row.instrument, row.event_id)))


def _level(row: Candle, direction: str, price: float, half_width: float, confirmed_time: int) -> StrictLevel:
    return StrictLevel(
        level_id=f"swing-{direction}-{row.timestamp_ms}",
        family="confirmed_swing",
        direction=direction,
        price=price,
        lower=price - half_width,
        upper=price + half_width,
        source_bar_time=row.timestamp_ms,
        confirmed_time=confirmed_time,
        reaction_count=1,
    )


def median_atr(values: Sequence[float]) -> float:
    resolved = sorted(value for value in values if value > 0)
    if not resolved:
        return 0.0
    middle = len(resolved) // 2
    return resolved[middle] if len(resolved) % 2 else (resolved[middle - 1] + resolved[middle]) / 2.0
