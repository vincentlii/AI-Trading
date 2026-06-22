from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from typing import MutableSequence, Sequence

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
    max_pre_pullback_extension_atr_hard: float = 2.50
    max_signal_to_level_atr_hard: float = 2.00
    max_pullback_attempt_number: int = 2
    max_pullback_duration_4h_bars: int = 8
    ideal_pre_pullback_extension_atr: float = 1.25
    ideal_signal_to_level_atr: float = 0.75
    ideal_pullback_duration_4h_bars: int = 4
    shallow_retrace_soft_min: float = 0.20
    shallow_retrace_soft_max: float = 0.65
    level_wick_penetration_tolerance_atr: float = 0.20
    require_pullback_close_hold_level: bool = True
    pullback_attempt_trigger_atr: float = 0.10


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
    atr_at_confirmation: float = 0.0


@dataclass(frozen=True)
class BosResult:
    status: str
    confirmation_bar_time: int | None = None
    signal_time: int | None = None
    entry_time: int | None = None
    confirmation_price: float | None = None
    entry_reference_price: float | None = None
    confirmation_delay_bars: int | None = None


@dataclass(frozen=True)
class PullbackCandidate:
    status: str
    pullback_bar_time: int | None = None
    pullback_index: int | None = None
    attempt_number: int = 0
    prior_retrace_count: int = 0
    prior_level_touch_count: int = 0
    retrace_ratio: float | None = None
    depth_atr: float | None = None
    distance_to_level_atr: float | None = None
    pre_pullback_extension_atr: float | None = None
    duration_4h_bars: int | None = None
    bars_acceptance_to_pullback: int | None = None
    close_back_inside_level: bool = False
    wick_penetration_atr: float | None = None
    first_touch_level: bool = False
    visual_geometry_score: float = 0.0
    visual_score_components: tuple[tuple[str, float], ...] = ()
    visual_risk_flags: tuple[str, ...] = ()
    semantic_failure_reason: str | None = None


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
    setup_version: str = "legacy_v1"
    level_lower: float | None = None
    level_upper: float | None = None
    atr_at_breakout: float | None = None
    pullback_attempt_number: int | None = None
    pre_pullback_extension_atr: float | None = None
    retrace_ratio: float | None = None
    pullback_depth_atr: float | None = None
    pullback_distance_to_level_atr: float | None = None
    pullback_duration_4h_bars: int | None = None
    signal_price_to_level_atr: float | None = None
    visual_geometry_score: float | None = None
    visual_risk_flags: tuple[str, ...] = ()


def balanced_v2_policy() -> StrictBpPolicy:
    return StrictBpPolicy(shallow_retrace_min=0.15, shallow_retrace_max=0.75)


def clean_v2_policy() -> StrictBpPolicy:
    return StrictBpPolicy(
        shallow_retrace_min=0.20,
        shallow_retrace_max=0.65,
        max_pre_pullback_extension_atr_hard=1.75,
        max_signal_to_level_atr_hard=1.25,
        max_pullback_attempt_number=1,
        max_pullback_duration_4h_bars=5,
        level_wick_penetration_tolerance_atr=0.15,
    )


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
            levels.append(_level(row, "long", row.high, half_width, confirmed_time, atr_values[index + right]))
        if all(row.low < peer.low for peer in (*before, *after)):
            levels.append(_level(row, "short", row.low, half_width, confirmed_time, atr_values[index + right]))
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
    atr: float | None = None,
    minimum_separation_ms: int = 3 * FOUR_HOURS_MS,
) -> tuple[StrictLevel, ...]:
    output: list[StrictLevel] = []
    for index, first in enumerate(swings):
        for second in swings[index + 1:]:
            if first.direction != second.direction:
                continue
            if second.source_bar_time - first.source_bar_time < minimum_separation_ms:
                continue
            causal_atr_value = second.atr_at_confirmation or atr or 0.0
            if causal_atr_value <= 0 or abs(second.price - first.price) > 0.15 * causal_atr_value:
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
                atr_at_confirmation=causal_atr_value,
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


def find_first_pullback_candidate_v2(
    rows: Sequence[Candle],
    *,
    breakout_index: int,
    acceptance_index: int,
    direction: str,
    level: StrictLevel,
    atr: float,
    policy: StrictBpPolicy,
) -> PullbackCandidate:
    if atr <= 0 or acceptance_index <= breakout_index or acceptance_index >= len(rows):
        return PullbackCandidate(status="rejected", semantic_failure_reason="invalid_lifecycle_input")
    impulse_start = level.upper if direction == "long" else level.lower
    running_extreme = (
        max(row.high for row in rows[breakout_index:acceptance_index + 1])
        if direction == "long"
        else min(row.low for row in rows[breakout_index:acceptance_index + 1])
    )
    attempt_number = 0
    prior_retrace_count = 0
    prior_level_touch_count = 0
    in_retrace = False
    attempt_start_index: int | None = None
    attempt_extreme = running_extreme
    limit = min(len(rows), acceptance_index + policy.max_pullback_duration_4h_bars + 1)
    for index in range(acceptance_index + 1, limit):
        row = rows[index]
        pre_bar_extreme = running_extreme
        impulse = abs(pre_bar_extreme - impulse_start)
        if impulse <= 0:
            continue
        adverse_price = row.low if direction == "long" else row.high
        depth = pre_bar_extreme - adverse_price if direction == "long" else adverse_price - pre_bar_extreme
        depth = max(0.0, depth)
        depth_atr = depth / atr
        retrace_ratio = depth / impulse
        level_touch = row.low <= level.upper if direction == "long" else row.high >= level.lower
        trigger = level_touch or depth_atr >= policy.pullback_attempt_trigger_atr or retrace_ratio >= 0.10

        if trigger and not in_retrace:
            attempt_number += 1
            if attempt_number > 1:
                prior_retrace_count += 1
            if level_touch:
                prior_level_touch_count += 1
            if attempt_number > policy.max_pullback_attempt_number:
                return PullbackCandidate(
                    status="rejected",
                    attempt_number=attempt_number,
                    prior_retrace_count=prior_retrace_count,
                    prior_level_touch_count=prior_level_touch_count,
                    semantic_failure_reason="late_or_second_pullback",
                )
            in_retrace = True
            attempt_start_index = index
            attempt_extreme = adverse_price
        elif in_retrace:
            attempt_extreme = min(attempt_extreme, row.low) if direction == "long" else max(attempt_extreme, row.high)
            depth = pre_bar_extreme - attempt_extreme if direction == "long" else attempt_extreme - pre_bar_extreme
            depth = max(0.0, depth)
            depth_atr = depth / atr
            retrace_ratio = depth / impulse

        extension = (pre_bar_extreme - level.upper) / atr if direction == "long" else (level.lower - pre_bar_extreme) / atr
        if extension > policy.max_pre_pullback_extension_atr_hard:
            return PullbackCandidate(
                status="rejected",
                pullback_bar_time=row.timestamp_ms,
                pullback_index=index,
                attempt_number=attempt_number,
                pre_pullback_extension_atr=extension,
                semantic_failure_reason="post_breakout_extension_too_far",
            )

        directional_close_break = row.close > pre_bar_extreme if direction == "long" else row.close < pre_bar_extreme
        if directional_close_break:
            in_retrace = False
            attempt_start_index = None
            running_extreme = max(running_extreme, row.high) if direction == "long" else min(running_extreme, row.low)
            updated_extension = (running_extreme - level.upper) / atr if direction == "long" else (level.lower - running_extreme) / atr
            if updated_extension > policy.max_pre_pullback_extension_atr_hard:
                return PullbackCandidate(
                    status="rejected",
                    pullback_bar_time=row.timestamp_ms,
                    pullback_index=index,
                    attempt_number=attempt_number,
                    pre_pullback_extension_atr=updated_extension,
                    semantic_failure_reason="post_breakout_extension_too_far",
                )
            continue

        if in_retrace and retrace_ratio >= policy.shallow_retrace_min:
            close_inside = row.close < level.upper if direction == "long" else row.close > level.lower
            penetration = max(0.0, level.upper - attempt_extreme) / atr if direction == "long" else max(0.0, attempt_extreme - level.lower) / atr
            distance = (attempt_extreme - level.upper) / atr if direction == "long" else (level.lower - attempt_extreme) / atr
            duration = index - (attempt_start_index or index) + 1
            fields = dict(
                pullback_bar_time=row.timestamp_ms,
                pullback_index=index,
                attempt_number=attempt_number,
                prior_retrace_count=prior_retrace_count,
                prior_level_touch_count=prior_level_touch_count,
                retrace_ratio=retrace_ratio,
                depth_atr=depth_atr,
                distance_to_level_atr=distance,
                pre_pullback_extension_atr=extension,
                duration_4h_bars=duration,
                bars_acceptance_to_pullback=index - acceptance_index,
                close_back_inside_level=close_inside,
                wick_penetration_atr=penetration,
                first_touch_level=level_touch and prior_level_touch_count == 1,
            )
            if policy.require_pullback_close_hold_level and close_inside:
                return PullbackCandidate(status="rejected", semantic_failure_reason="deep_reentry_inside_range", **fields)
            if penetration > policy.level_wick_penetration_tolerance_atr:
                return PullbackCandidate(status="rejected", semantic_failure_reason="deep_reentry_inside_range", **fields)
            if retrace_ratio > policy.shallow_retrace_max:
                return PullbackCandidate(status="rejected", semantic_failure_reason="pullback_too_deep", **fields)
            score, components, flags = _visual_geometry_score(
                attempt_number=attempt_number,
                retrace_ratio=retrace_ratio,
                duration=duration,
                distance_to_level_atr=distance,
                extension_atr=extension,
                wick_penetration_atr=penetration,
                signal_distance_atr=None,
                policy=policy,
            )
            status = "accepted_with_visual_risk" if flags else "accepted"
            return PullbackCandidate(
                status=status,
                visual_geometry_score=score,
                visual_score_components=components,
                visual_risk_flags=flags,
                **fields,
            )

        running_extreme = max(running_extreme, row.high) if direction == "long" else min(running_extreme, row.low)
        updated_extension = (running_extreme - level.upper) / atr if direction == "long" else (level.lower - running_extreme) / atr
        if updated_extension > policy.max_pre_pullback_extension_atr_hard:
            return PullbackCandidate(
                status="rejected",
                pullback_bar_time=row.timestamp_ms,
                pullback_index=index,
                attempt_number=attempt_number,
                pre_pullback_extension_atr=updated_extension,
                semantic_failure_reason="post_breakout_extension_too_far",
            )
    reason = "pullback_too_shallow_noise" if attempt_number else "no_first_pullback_found"
    return PullbackCandidate(
        status="rejected",
        attempt_number=attempt_number,
        prior_retrace_count=prior_retrace_count,
        prior_level_touch_count=prior_level_touch_count,
        semantic_failure_reason=reason,
    )


def _visual_geometry_score(
    *,
    attempt_number: int,
    retrace_ratio: float,
    duration: int,
    distance_to_level_atr: float,
    extension_atr: float,
    wick_penetration_atr: float,
    signal_distance_atr: float | None,
    policy: StrictBpPolicy,
) -> tuple[float, tuple[tuple[str, float], ...], tuple[str, ...]]:
    flags: list[str] = []
    geometry = 20.0
    if not (policy.shallow_retrace_soft_min <= retrace_ratio <= policy.shallow_retrace_soft_max):
        geometry -= 5.0
        flags.append("pullback_too_shallow_noise" if retrace_ratio < policy.shallow_retrace_soft_min else "pullback_too_deep")
    if duration > policy.ideal_pullback_duration_4h_bars:
        geometry -= 5.0
        flags.append("pullback_duration_late")
    if distance_to_level_atr > 0.75:
        geometry -= 5.0
    if 0.35 <= extension_atr <= policy.ideal_pre_pullback_extension_atr:
        extension_score = 20.0
    elif extension_atr <= 1.75:
        extension_score = 10.0
    else:
        extension_score = 5.0
    if extension_atr > policy.ideal_pre_pullback_extension_atr:
        flags.append("pre_pullback_extension_late")
    attempt_score = 20.0 if attempt_number == 1 else 10.0
    if attempt_number == 2:
        flags.append("second_pullback_attempt")
    hold_score = 20.0 if wick_penetration_atr <= 0 else 15.0 if wick_penetration_atr <= 0.10 else 10.0
    if wick_penetration_atr > 0.10:
        flags.append("level_wick_penetration_risk")
    if signal_distance_atr is None or signal_distance_atr <= policy.ideal_signal_to_level_atr:
        chase_score = 20.0
    elif signal_distance_atr <= 1.25:
        chase_score = 10.0
    else:
        chase_score = 5.0
        flags.append("confirmation_chase_risk")
    components = (
        ("pullback_geometry", max(0.0, geometry)),
        ("pre_pullback_extension", extension_score),
        ("pullback_attempt", attempt_score),
        ("level_hold", hold_score),
        ("bos_chase", chase_score),
    )
    return sum(value for _, value in components), components, tuple(sorted(set(flags)))


def find_first_15m_bos(
    rows: Sequence[Candle],
    *,
    direction: str,
    observation_start: int,
    invalidation: float,
    policy: StrictBpPolicy,
    timestamps: Sequence[int] | None = None,
) -> BosResult:
    resolved_timestamps = timestamps if timestamps is not None else tuple(row.timestamp_ms for row in rows)
    start_index = bisect_left(resolved_timestamps, observation_start)
    checked = 0
    for index in range(start_index, len(rows)):
        if checked >= policy.bos_max_bars:
            break
        row = rows[index]
        if not row.is_confirmed:
            continue
        checked += 1
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
            next_row = rows[index + 1] if index + 1 < len(rows) and rows[index + 1].is_confirmed else None
            return BosResult(
                status="confirmed",
                confirmation_bar_time=row.timestamp_ms,
                signal_time=signal_time,
                entry_time=signal_time + FIFTEEN_MINUTES_MS,
                confirmation_price=row.close,
                entry_reference_price=None if next_row is None else next_row.close,
                confirmation_delay_bars=checked,
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
    candidate_diagnostics: MutableSequence[dict[str, object]] | None = None,
) -> tuple[StrictBpEvent, ...]:
    policy = policy or StrictBpPolicy()
    balanced_policy = replace(policy, shallow_retrace_min=0.15, shallow_retrace_max=0.75)
    clean_policy = replace(
        balanced_policy,
        shallow_retrace_min=0.20,
        shallow_retrace_max=0.65,
        max_pre_pullback_extension_atr_hard=1.75,
        max_signal_to_level_atr_hard=1.25,
        max_pullback_attempt_number=1,
        max_pullback_duration_4h_bars=5,
        level_wick_penetration_tolerance_atr=0.15,
    )
    atrs = causal_atr(candles_4h)
    swings = confirmed_swing_levels(candles_4h, atr_values=atrs, policy=policy)
    levels = (*swings, *repeated_boundary_levels(swings))
    timestamps_15m = tuple(row.timestamp_ms for row in candles_15m)
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
                        timestamps=timestamps_15m,
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
                            level_lower=level.lower,
                            level_upper=level.upper,
                            atr_at_breakout=atr,
                        )
                    )
                    matched = True
                    break
            candidate = find_first_pullback_candidate_v2(
                candles_4h,
                breakout_index=breakout_index,
                acceptance_index=acceptance_index,
                direction=direction,
                level=level,
                atr=atr,
                policy=balanced_policy,
            )
            physical = f"{instrument}:{level.level_id}:{breakout.timestamp_ms}:{direction}"
            diagnostic = {
                "candidate_id": physical,
                "physical_event_key": f"{instrument}:{breakout.timestamp_ms}:{direction}",
                "instrument": instrument,
                "direction": direction,
                "level_id": level.level_id,
                "breakout_time": breakout.timestamp_ms + FOUR_HOURS_MS,
                "acceptance_time": acceptance.timestamp_ms + FOUR_HOURS_MS,
                **candidate.__dict__,
                "visual_score_components": dict(candidate.visual_score_components),
            }
            if candidate_diagnostics is not None:
                candidate_diagnostics.append(diagnostic)
            if candidate.status in {"accepted", "accepted_with_visual_risk"} and candidate.pullback_index is not None:
                invalidation = level.lower - 0.10 * atr if direction == "long" else level.upper + 0.10 * atr
                bos = find_first_15m_bos(
                    candles_15m,
                    direction=direction,
                    observation_start=candles_4h[candidate.pullback_index].timestamp_ms + FOUR_HOURS_MS,
                    invalidation=invalidation,
                    policy=balanced_policy,
                    timestamps=timestamps_15m,
                )
                diagnostic["bos_status"] = bos.status
                if bos.status == "confirmed" and bos.signal_time is not None and bos.entry_time is not None and bos.confirmation_price is not None:
                    signal_distance = (
                        (bos.confirmation_price - level.upper) / atr
                        if direction == "long"
                        else (level.lower - bos.confirmation_price) / atr
                    )
                    diagnostic["signal_price_to_level_atr"] = signal_distance
                    if signal_distance <= balanced_policy.max_signal_to_level_atr_hard and start_ms <= bos.signal_time <= end_ms:
                        score, _, score_flags = _visual_geometry_score(
                            attempt_number=candidate.attempt_number,
                            retrace_ratio=float(candidate.retrace_ratio),
                            duration=int(candidate.duration_4h_bars),
                            distance_to_level_atr=float(candidate.distance_to_level_atr),
                            extension_atr=float(candidate.pre_pullback_extension_atr),
                            wick_penetration_atr=float(candidate.wick_penetration_atr),
                            signal_distance_atr=signal_distance,
                            policy=balanced_policy,
                        )
                        base_event = StrictBpEvent(
                            event_id=f"{physical}:strict_shallow_pullback_v2_balanced",
                            physical_event_key=physical,
                            instrument=instrument,
                            setup="strict_shallow_pullback_v2_balanced",
                            level_id=level.level_id,
                            level_family=level.family,
                            direction=direction,
                            level_price=level.price,
                            breakout_time=breakout.timestamp_ms + FOUR_HOURS_MS,
                            acceptance_time=acceptance.timestamp_ms + FOUR_HOURS_MS,
                            pullback_time=candles_4h[candidate.pullback_index].timestamp_ms + FOUR_HOURS_MS,
                            signal_time=bos.signal_time,
                            entry_time=bos.entry_time,
                            signal_price=bos.confirmation_price,
                            invalidation=invalidation,
                            atr_4h=atr,
                            trend_state=trend,
                            setup_version="first_pullback_geometry_v2",
                            level_lower=level.lower,
                            level_upper=level.upper,
                            atr_at_breakout=atr,
                            pullback_attempt_number=candidate.attempt_number,
                            pre_pullback_extension_atr=candidate.pre_pullback_extension_atr,
                            retrace_ratio=candidate.retrace_ratio,
                            pullback_depth_atr=candidate.depth_atr,
                            pullback_distance_to_level_atr=candidate.distance_to_level_atr,
                            pullback_duration_4h_bars=candidate.duration_4h_bars,
                            signal_price_to_level_atr=signal_distance,
                            visual_geometry_score=score,
                            visual_risk_flags=tuple(sorted(set((*candidate.visual_risk_flags, *score_flags)))),
                        )
                        output.append(base_event)
                        matched = True
                        if _candidate_passes_policy(candidate, signal_distance, clean_policy):
                            output.append(replace(
                                base_event,
                                event_id=f"{physical}:strict_shallow_pullback_v2_clean",
                                setup="strict_shallow_pullback_v2_clean",
                            ))
                    elif signal_distance > balanced_policy.max_signal_to_level_atr_hard:
                        diagnostic["status"] = "rejected"
                        diagnostic["semantic_failure_reason"] = "confirmation_chase_hard_cap"
                    else:
                        diagnostic["status"] = "rejected"
                        diagnostic["semantic_failure_reason"] = "signal_outside_development_window"
                else:
                    diagnostic["status"] = "rejected"
                    diagnostic["semantic_failure_reason"] = f"bos_{bos.status}"
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


def _candidate_passes_policy(candidate: PullbackCandidate, signal_distance: float, policy: StrictBpPolicy) -> bool:
    return bool(
        candidate.attempt_number <= policy.max_pullback_attempt_number
        and candidate.duration_4h_bars is not None
        and candidate.duration_4h_bars <= policy.max_pullback_duration_4h_bars
        and candidate.retrace_ratio is not None
        and policy.shallow_retrace_min <= candidate.retrace_ratio <= policy.shallow_retrace_max
        and candidate.pre_pullback_extension_atr is not None
        and candidate.pre_pullback_extension_atr <= policy.max_pre_pullback_extension_atr_hard
        and candidate.wick_penetration_atr is not None
        and candidate.wick_penetration_atr <= policy.level_wick_penetration_tolerance_atr
        and not candidate.close_back_inside_level
        and signal_distance <= policy.max_signal_to_level_atr_hard
    )


def _level(row: Candle, direction: str, price: float, half_width: float, confirmed_time: int, atr_at_confirmation: float = 0.0) -> StrictLevel:
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
        atr_at_confirmation=atr_at_confirmation,
    )


def median_atr(values: Sequence[float]) -> float:
    resolved = sorted(value for value in values if value > 0)
    if not resolved:
        return 0.0
    middle = len(resolved) // 2
    return resolved[middle] if len(resolved) % 2 else (resolved[middle - 1] + resolved[middle]) / 2.0
