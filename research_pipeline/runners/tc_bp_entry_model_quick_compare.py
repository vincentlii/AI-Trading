from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Mapping, Sequence

from trading_system.data.history import DuckDbCandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.tc_bp_strict_causal import (
    FIFTEEN_MINUTES_MS,
    FOUR_HOURS_MS,
    StrictBpPolicy,
    StrictLevel,
    breakout_direction,
    causal_atr,
    confirmed_swing_levels,
    find_first_15m_bos,
    repeated_boundary_levels,
)


HOLDOUT_START = "2024-12-01"
DEFAULT_INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
LEFT_MODELS = ("left_level_edge_limit",)
RIGHT_HARD_MODEL = "right_level_retest_confirm"
SOFT_RIGHT_MODEL = "right_level_retest_confirm_soft_vpa"
MODELS = (*LEFT_MODELS, RIGHT_HARD_MODEL)
COMPREHENSIVE_MODELS = (*LEFT_MODELS, RIGHT_HARD_MODEL, SOFT_RIGHT_MODEL)
DIAGNOSTIC_HORIZONS = (2, 4, 8, 12, 16, 20, 24, 36, 48, 60, 72, 96)
DAY_MS = 24 * 60 * 60 * 1000
LEVEL_MAX_AGE_MS = 180 * DAY_MS
CONTEXT_WARMUP_MS = 187 * DAY_MS
VPA_4H_LOOKBACK = 60
VPA_15M_LOOKBACK = 96


def _structural_trends_for_cutoffs(
    levels: Sequence[StrictLevel],
    cutoff_times: Sequence[int],
    *,
    max_age_ms: int | None = None,
) -> dict[int, str]:
    ordered = sorted(enumerate(levels), key=lambda item: (item[1].confirmed_time, item[0]))
    latest: dict[str, list[StrictLevel]] = {"long": [], "short": []}
    output: dict[int, str] = {}
    cursor = 0
    for cutoff in sorted(set(cutoff_times)):
        while cursor < len(ordered) and ordered[cursor][1].confirmed_time <= cutoff:
            level = ordered[cursor][1]
            bucket = latest[level.direction]
            bucket.append(level)
            if len(bucket) > 2:
                del bucket[0]
            cursor += 1
        if max_age_ms is not None:
            earliest = cutoff - max_age_ms
            for bucket in latest.values():
                while bucket and bucket[0].confirmed_time < earliest:
                    del bucket[0]
        highs = latest["long"]
        lows = latest["short"]
        if len(highs) < 2 or len(lows) < 2:
            output[cutoff] = "unknown"
        elif highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
            output[cutoff] = "long"
        elif highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
            output[cutoff] = "short"
        else:
            output[cutoff] = "unknown"
    return output


@dataclass(frozen=True)
class TrueBreakoutEvent:
    event_id: str
    physical_event_key: str
    instrument: str
    direction: str
    level_id: str
    level_family: str
    level_price: float
    level_lower: float
    level_upper: float
    atr: float
    breakout_time: int
    acceptance_time: int
    breakout_open: float
    breakout_high: float
    breakout_low: float
    breakout_close: float
    acceptance_close: float
    impulse_extreme: float
    trend_state: str
    breakout_attempt_number: int = 1
    trend_score: float = 0.0
    trend_score_label: str = "trend_unknown_or_transition"


@dataclass(frozen=True)
class EntryDiagnostic:
    event_id: str
    model: str
    status: str
    failure_reason: str | None = None
    entry_time: int | None = None
    entry_price: float | None = None
    entry_to_level_atr: float | None = None
    stop_distance_atr: float | None = None
    stop_distance_pct: float | None = None
    path_order: str | None = None
    path_window_complete: bool = False
    one_point_five_r_first: bool | None = None
    two_r_first: bool | None = None
    no_decision: bool | None = None
    time_to_1r_minutes: int | None = None
    time_to_invalidation_minutes: int | None = None
    forward_2h_return_pct: float | None = None
    forward_4h_return_pct: float | None = None
    forward_8h_return_pct: float | None = None
    forward_12h_return_pct: float | None = None
    forward_16h_return_pct: float | None = None
    forward_20h_return_pct: float | None = None
    forward_24h_return_pct: float | None = None
    forward_36h_return_pct: float | None = None
    forward_48h_return_pct: float | None = None
    forward_60h_return_pct: float | None = None
    forward_72h_return_pct: float | None = None
    forward_96h_return_pct: float | None = None
    mfe_pct: float | None = None
    mae_pct: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    horizon_paths: tuple[tuple[int, PathDiagnostic], ...] = ()
    confirmation_type: str | None = None
    retest_lifecycle: str | None = None
    vpa_bucket: str | None = None
    vpa_score: float | None = None
    trend_score_label: str | None = None
    breakout_attempt_number: int | None = None


@dataclass(frozen=True)
class QuickCompareResult:
    report_path: str
    decision: str
    true_breakout_event_count: int
    holdout_start_ms: int


@dataclass(frozen=True)
class PathDiagnostic:
    path_order: str
    window_complete: bool
    one_point_five_r_first: bool
    two_r_first: bool
    no_decision: bool
    time_to_1r_minutes: int | None
    time_to_invalidation_minutes: int | None
    mfe_pct: float | None
    mae_pct: float | None
    mfe_r: float | None
    mae_r: float | None


@dataclass(frozen=True)
class RetestSegment:
    status: str
    lifecycle: str
    start_index: int | None = None
    end_index: int | None = None
    depth_atr: float | None = None
    duration_4h_bars: int | None = None
    close_inside_count: int = 0
    wick_breach: bool = False
    close_breach: bool = False


@dataclass(frozen=True)
class SoftConfirmation:
    status: str
    confirmation_type: str | None = None
    confirmation_index: int | None = None
    signal_time: int | None = None
    entry_time: int | None = None
    entry_reference_price: float | None = None


def build_true_breakout_events(
    instrument: str,
    rows_4h: Sequence[Candle],
    *,
    start_ms: int,
    end_ms: int,
    policy: StrictBpPolicy | None = None,
) -> tuple[TrueBreakoutEvent, ...]:
    policy = policy or StrictBpPolicy()
    if not rows_4h:
        return ()
    atrs = causal_atr(rows_4h)
    swings = confirmed_swing_levels(rows_4h, atr_values=atrs, policy=policy)
    levels = (*swings, *repeated_boundary_levels(swings))
    timestamps = tuple(row.timestamp_ms for row in rows_4h)
    trend_by_cutoff = _structural_trends_for_cutoffs(
        swings,
        tuple(row.timestamp_ms + FOUR_HOURS_MS for row in rows_4h),
        max_age_ms=LEVEL_MAX_AGE_MS,
    )
    selected: dict[tuple[str, int, str], tuple[float, TrueBreakoutEvent]] = {}
    for level in levels:
        first_index = max(1, bisect_left(timestamps, level.confirmed_time))
        for index in range(first_index, len(rows_4h) - 1):
            breakout = rows_4h[index]
            acceptance = rows_4h[index + 1]
            acceptance_time = acceptance.timestamp_ms + FOUR_HOURS_MS
            if acceptance_time > end_ms:
                break
            breakout_time = breakout.timestamp_ms + FOUR_HOURS_MS
            origin_time = level.origin_time if level.origin_time is not None else level.source_bar_time
            if breakout_time - origin_time > LEVEL_MAX_AGE_MS:
                break
            atr = atrs[index]
            direction = breakout_direction(breakout, level, atr=atr, policy=policy)
            if direction is None:
                continue
            previous = rows_4h[index - 1]
            crossed_from_inside = (
                previous.close <= level.upper
                if direction == "long"
                else previous.close >= level.lower
            )
            if not crossed_from_inside:
                continue
            accepted = (
                acceptance.close > level.upper + 0.25 * atr
                if direction == "long"
                else acceptance.close < level.lower - 0.25 * atr
            )
            if not accepted:
                continue
            cutoff = breakout.timestamp_ms + FOUR_HOURS_MS
            trend = trend_by_cutoff[cutoff]
            if trend != direction:
                break
            if acceptance_time < start_ms:
                break
            physical = f"{instrument}:{breakout_time}:{direction}"
            outer = level.upper if direction == "long" else level.lower
            distance = abs(breakout.close - outer) / atr
            event = TrueBreakoutEvent(
                event_id=physical,
                physical_event_key=physical,
                instrument=instrument,
                direction=direction,
                level_id=level.level_id,
                level_family=level.family,
                level_price=level.price,
                level_lower=level.lower,
                level_upper=level.upper,
                atr=atr,
                breakout_time=breakout_time,
                acceptance_time=acceptance_time,
                breakout_open=breakout.open,
                breakout_high=breakout.high,
                breakout_low=breakout.low,
                breakout_close=breakout.close,
                acceptance_close=acceptance.close,
                impulse_extreme=max(breakout.high, acceptance.high) if direction == "long" else min(breakout.low, acceptance.low),
                trend_state=trend,
            )
            key = (instrument, breakout_time, direction)
            current = selected.get(key)
            if current is None or (distance, level.level_id) < (current[0], current[1].level_id):
                selected[key] = (distance, event)
            break
    return tuple(sorted((item[1] for item in selected.values()), key=lambda row: (row.acceptance_time, row.instrument, row.event_id)))


def build_true_breakout_diagnostic_events(
    instrument: str,
    rows_4h: Sequence[Candle],
    *,
    start_ms: int,
    end_ms: int,
    policy: StrictBpPolicy | None = None,
) -> tuple[TrueBreakoutEvent, ...]:
    """Build the widest causal accepted-breakout pool for diagnostic grouping.

    Unlike build_true_breakout_events(), this does not hard-filter trend and
    does not stop after the first accepted breakout on the same level.
    """
    policy = policy or StrictBpPolicy()
    if not rows_4h:
        return ()
    atrs = causal_atr(rows_4h)
    swings = confirmed_swing_levels(rows_4h, atr_values=atrs, policy=policy)
    levels = (*swings, *repeated_boundary_levels(swings))
    timestamps = tuple(row.timestamp_ms for row in rows_4h)
    trend_by_cutoff = _structural_trends_for_cutoffs(
        swings,
        tuple(row.timestamp_ms + FOUR_HOURS_MS for row in rows_4h),
        max_age_ms=LEVEL_MAX_AGE_MS,
    )
    selected: dict[tuple[str, int, str], tuple[float, TrueBreakoutEvent]] = {}
    for level in levels:
        first_index = max(1, bisect_left(timestamps, level.confirmed_time))
        attempt_number = 0
        for index in range(first_index, len(rows_4h) - 1):
            breakout = rows_4h[index]
            acceptance = rows_4h[index + 1]
            acceptance_time = acceptance.timestamp_ms + FOUR_HOURS_MS
            if acceptance_time > end_ms:
                break
            breakout_time = breakout.timestamp_ms + FOUR_HOURS_MS
            origin_time = level.origin_time if level.origin_time is not None else level.source_bar_time
            if breakout_time - origin_time > LEVEL_MAX_AGE_MS:
                break
            atr = atrs[index]
            direction = breakout_direction(breakout, level, atr=atr, policy=policy)
            if direction is None:
                continue
            previous = rows_4h[index - 1]
            crossed_from_inside = (
                previous.close <= level.upper
                if direction == "long"
                else previous.close >= level.lower
            )
            if not crossed_from_inside:
                continue
            accepted = (
                acceptance.close > level.upper + 0.25 * atr
                if direction == "long"
                else acceptance.close < level.lower - 0.25 * atr
            )
            if not accepted:
                continue
            attempt_number += 1
            cutoff = breakout.timestamp_ms + FOUR_HOURS_MS
            trend = trend_by_cutoff.get(cutoff, "unknown")
            trend_score, trend_score_label = _trend_score(rows_4h, index, direction, trend, atr)
            if acceptance_time < start_ms:
                continue
            physical = f"{instrument}:{breakout_time}:{direction}"
            outer = level.upper if direction == "long" else level.lower
            distance = abs(breakout.close - outer) / atr
            event = TrueBreakoutEvent(
                event_id=physical,
                physical_event_key=physical,
                instrument=instrument,
                direction=direction,
                level_id=level.level_id,
                level_family=level.family,
                level_price=level.price,
                level_lower=level.lower,
                level_upper=level.upper,
                atr=atr,
                breakout_time=breakout_time,
                acceptance_time=acceptance_time,
                breakout_open=breakout.open,
                breakout_high=breakout.high,
                breakout_low=breakout.low,
                breakout_close=breakout.close,
                acceptance_close=acceptance.close,
                impulse_extreme=max(breakout.high, acceptance.high) if direction == "long" else min(breakout.low, acceptance.low),
                trend_state=trend,
                breakout_attempt_number=attempt_number,
                trend_score=trend_score,
                trend_score_label=trend_score_label,
            )
            key = (instrument, breakout_time, direction)
            current = selected.get(key)
            if current is None or (distance, level.level_id) < (current[0], current[1].level_id):
                selected[key] = (distance, event)
    return tuple(sorted((item[1] for item in selected.values()), key=lambda row: (row.acceptance_time, row.instrument, row.event_id)))


def evaluate_left_limit(
    event: TrueBreakoutEvent,
    rows_15m: Sequence[Candle],
    *,
    model: str,
    expiry_bars: int = 32,
    path_horizon_hours: int = 48,
) -> EntryDiagnostic:
    model_name = f"left_{model}"
    limit = _left_limit_price(event, model)
    stop = event.level_lower - 0.10 * event.atr if event.direction == "long" else event.level_upper + 0.10 * event.atr
    eligible = [row for row in rows_15m if row.is_confirmed and row.timestamp_ms >= event.acceptance_time]
    running_extreme = event.impulse_extreme
    for row_index, row in enumerate(eligible[:expiry_bars]):
        extension = (running_extreme - event.level_upper) / event.atr if event.direction == "long" else (event.level_lower - running_extreme) / event.atr
        if extension > 2.50:
            return _empty_result(event, model_name, "cancelled", "pre_fill_extension_too_far")
        fill = row.low <= limit if event.direction == "long" else row.high >= limit
        stop_hit = row.low <= stop if event.direction == "long" else row.high >= stop
        if fill and stop_hit:
            risk = abs(limit - stop)
            return EntryDiagnostic(
                event_id=event.event_id,
                model=model_name,
                status="ambiguous_intrabar_path",
                failure_reason="fill_and_stop_same_15m_bar",
                entry_time=row.timestamp_ms + FIFTEEN_MINUTES_MS,
                entry_price=limit,
                entry_to_level_atr=_entry_distance(event, limit),
                stop_distance_atr=risk / event.atr,
                stop_distance_pct=risk / limit * 100.0,
            )
        if fill:
            return _triggered_result(
                event,
                model_name,
                limit,
                row.timestamp_ms + FIFTEEN_MINUTES_MS,
                eligible[row_index + 1:],
                stop,
                path_horizon_hours=path_horizon_hours,
            )
        close_inside = row.close < event.level_upper if event.direction == "long" else row.close > event.level_lower
        penetration = max(0.0, event.level_upper - row.low) / event.atr if event.direction == "long" else max(0.0, row.high - event.level_lower) / event.atr
        if close_inside:
            return _empty_result(event, model_name, "cancelled", "close_back_inside_level")
        if penetration > 0.25:
            return _empty_result(event, model_name, "cancelled", "wick_penetration_too_deep")
        running_extreme = max(running_extreme, row.high) if event.direction == "long" else min(running_extreme, row.low)
    return _empty_result(event, model_name, "expired", "limit_expired_32_bars")


def evaluate_right_confirmation(
    event: TrueBreakoutEvent,
    rows_4h: Sequence[Candle],
    rows_15m: Sequence[Candle],
    *,
    path_horizon_hours: int = 48,
) -> EntryDiagnostic:
    model = "right_level_retest_confirm"
    retests = [row for row in rows_4h if row.is_confirmed and row.timestamp_ms >= event.acceptance_time][:12]
    retest = None
    for row in retests:
        stop = event.level_lower - 0.10 * event.atr if event.direction == "long" else event.level_upper + 0.10 * event.atr
        invalidated = row.low <= stop if event.direction == "long" else row.high >= stop
        if invalidated:
            return _empty_result(event, model, "not_triggered", "retest_invalidated_setup")
        touched = row.low <= event.level_upper + 0.10 * event.atr if event.direction == "long" else row.high >= event.level_lower - 0.10 * event.atr
        if not touched:
            continue
        if not _valid_retest(event, row):
            return _empty_result(event, model, "not_triggered", "retest_failed_level_hold")
        retest = row
        break
    if retest is None:
        return _empty_result(event, model, "not_triggered", "no_valid_level_retest")
    stop = event.level_lower - 0.10 * event.atr if event.direction == "long" else event.level_upper + 0.10 * event.atr
    bos = find_first_15m_bos(
        rows_15m,
        direction=event.direction,
        observation_start=retest.timestamp_ms + FOUR_HOURS_MS,
        invalidation=stop,
        policy=StrictBpPolicy(bos_lookback_bars=3, bos_max_bars=8),
    )
    if (
        bos.status != "confirmed"
        or bos.signal_time is None
        or bos.entry_time is None
        or bos.entry_reference_price is None
    ):
        return _empty_result(event, model, "not_triggered", f"bos_{bos.status}")
    distance = _entry_distance(event, bos.entry_reference_price)
    if distance > 2.0:
        return _empty_result(event, model, "not_triggered", "confirmation_chase_hard_cap")
    index = next((i for i, row in enumerate(rows_15m) if row.timestamp_ms + FIFTEEN_MINUTES_MS == bos.entry_time), None)
    if index is None:
        return _empty_result(event, model, "not_triggered", "missing_entry_bar")
    entry_bar = rows_15m[index]
    failed_before_entry = entry_bar.low <= stop if event.direction == "long" else entry_bar.high >= stop
    if failed_before_entry:
        return _empty_result(event, model, "not_triggered", "failed_before_entry")
    future = rows_15m[index + 1:]
    result = _triggered_result(
        event,
        model,
        bos.entry_reference_price,
        bos.entry_time,
        future,
        stop,
        path_horizon_hours=path_horizon_hours,
    )
    if distance > 1.25:
        return replace(result, failure_reason="confirmation_chase_risk")
    return result


def evaluate_right_confirmation_soft_vpa(
    event: TrueBreakoutEvent,
    rows_4h: Sequence[Candle],
    rows_15m: Sequence[Candle],
    *,
    path_horizon_hours: int = 48,
) -> EntryDiagnostic:
    model = SOFT_RIGHT_MODEL
    stop = event.level_lower - 0.10 * event.atr if event.direction == "long" else event.level_upper + 0.10 * event.atr
    retest = _find_soft_retest_segment(event, rows_4h, stop)
    if retest.status != "accepted" or retest.end_index is None:
        return _empty_result(
            event,
            model,
            "not_triggered",
            retest.status,
            retest_lifecycle=retest.lifecycle,
            trend_score_label=event.trend_score_label,
            breakout_attempt_number=event.breakout_attempt_number,
        )
    observation_start = rows_4h[retest.end_index].timestamp_ms + FOUR_HOURS_MS
    confirmation = _find_soft_15m_confirmation(event, rows_15m, observation_start, stop)
    if (
        confirmation.status != "confirmed"
        or confirmation.entry_time is None
        or confirmation.entry_reference_price is None
        or confirmation.confirmation_index is None
    ):
        return _empty_result(
            event,
            model,
            "not_triggered",
            f"soft_{confirmation.status}",
            retest_lifecycle=retest.lifecycle,
            trend_score_label=event.trend_score_label,
            breakout_attempt_number=event.breakout_attempt_number,
        )
    distance = _entry_distance(event, confirmation.entry_reference_price)
    if distance > 2.0:
        return _empty_result(
            event,
            model,
            "not_triggered",
            "confirmation_chase_hard_cap",
            retest_lifecycle=retest.lifecycle,
            confirmation_type=confirmation.confirmation_type,
            trend_score_label=event.trend_score_label,
            breakout_attempt_number=event.breakout_attempt_number,
        )
    entry_bar = rows_15m[confirmation.confirmation_index + 1]
    entry_close_failed = entry_bar.close <= stop if event.direction == "long" else entry_bar.close >= stop
    if entry_close_failed:
        return _empty_result(
            event,
            model,
            "not_triggered",
            "failed_before_entry_close",
            retest_lifecycle=retest.lifecycle,
            confirmation_type=confirmation.confirmation_type,
            trend_score_label=event.trend_score_label,
            breakout_attempt_number=event.breakout_attempt_number,
        )
    vpa_score, vpa_bucket = _soft_vpa_score(event, rows_4h, rows_15m, retest, confirmation, distance)
    result = _triggered_result(
        event,
        model,
        confirmation.entry_reference_price,
        confirmation.entry_time,
        rows_15m[confirmation.confirmation_index + 2:],
        stop,
        path_horizon_hours=path_horizon_hours,
    )
    return replace(
        result,
        confirmation_type=confirmation.confirmation_type,
        retest_lifecycle=retest.lifecycle,
        vpa_score=vpa_score,
        vpa_bucket=vpa_bucket,
        trend_score_label=event.trend_score_label,
        breakout_attempt_number=event.breakout_attempt_number,
        failure_reason="confirmation_chase_risk" if distance > 1.25 else result.failure_reason,
    )


def run_tc_bp_entry_model_quick_compare(
    *,
    repository: DuckDbCandleRepository,
    report_path: Path,
    start_date: str = "2022-01-01",
    end_date: str = "2024-11-30",
    instruments: Sequence[str] = DEFAULT_INSTRUMENTS,
) -> QuickCompareResult:
    if end_date >= HOLDOUT_START:
        raise ValueError(f"end_date must be before sealed holdout {HOLDOUT_START}")
    start_ms, end_ms = _date_bounds(start_date, end_date)
    holdout_start_ms, _ = _date_bounds(HOLDOUT_START, HOLDOUT_START)
    warmup_ms = start_ms - CONTEXT_WARMUP_MS
    diagnostic_end_ms = min(end_ms + 96 * 60 * 60 * 1000, holdout_start_ms - FIFTEEN_MINUTES_MS - 1)
    events: list[TrueBreakoutEvent] = []
    rows_4h_by_asset: dict[str, Sequence[Candle]] = {}
    rows_15m_by_asset: dict[str, Sequence[Candle]] = {}
    for instrument in instruments:
        rows_4h = repository.load_range(instrument, "4H", warmup_ms, end_ms, inst_type="SWAP")
        rows_15m = repository.load_range(instrument, "15m", warmup_ms, diagnostic_end_ms, inst_type="SWAP")
        rows_4h_by_asset[instrument] = rows_4h
        rows_15m_by_asset[instrument] = rows_15m
        events.extend(build_true_breakout_events(instrument, rows_4h, start_ms=start_ms, end_ms=end_ms))
    entry_rows: list[EntryDiagnostic] = []
    for event in events:
        rows_15m = rows_15m_by_asset[event.instrument]
        for model in LEFT_MODELS:
            entry_rows.append(evaluate_left_limit(event, rows_15m, model=model.removeprefix("left_")))
        entry_rows.append(evaluate_right_confirmation(event, rows_4h_by_asset[event.instrument], rows_15m))
    breakout_metrics = _breakout_metrics(events, rows_15m_by_asset)
    model_metrics = _model_metrics(events, entry_rows)
    paired_metrics = _paired_metrics(entry_rows)
    decision = _decision(len(events), breakout_metrics, model_metrics)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _report(start_date, end_date, instruments, events, breakout_metrics, model_metrics, paired_metrics, decision),
        encoding="utf-8",
    )
    return QuickCompareResult(str(report_path.resolve()), decision, len(events), holdout_start_ms)


def run_tc_bp_entry_model_quick_compare_extended(
    *,
    repository: DuckDbCandleRepository,
    report_path: Path,
    start_date: str = "2022-01-01",
    end_date: str = "2024-11-30",
    instruments: Sequence[str] = DEFAULT_INSTRUMENTS,
) -> QuickCompareResult:
    if end_date >= HOLDOUT_START:
        raise ValueError(f"end_date must be before sealed holdout {HOLDOUT_START}")
    start_ms, end_ms = _date_bounds(start_date, end_date)
    holdout_start_ms, _ = _date_bounds(HOLDOUT_START, HOLDOUT_START)
    warmup_ms = start_ms - CONTEXT_WARMUP_MS
    diagnostic_end_ms = min(end_ms + 96 * 60 * 60 * 1000, holdout_start_ms - FIFTEEN_MINUTES_MS - 1)
    events: list[TrueBreakoutEvent] = []
    rows_4h_by_asset: dict[str, Sequence[Candle]] = {}
    rows_15m_by_asset: dict[str, Sequence[Candle]] = {}
    for instrument in instruments:
        rows_4h = repository.load_range(instrument, "4H", warmup_ms, end_ms, inst_type="SWAP")
        rows_15m = repository.load_range(instrument, "15m", warmup_ms, diagnostic_end_ms, inst_type="SWAP")
        rows_4h_by_asset[instrument] = rows_4h
        rows_15m_by_asset[instrument] = rows_15m
        events.extend(build_true_breakout_events(instrument, rows_4h, start_ms=start_ms, end_ms=end_ms))
    entry_rows: list[EntryDiagnostic] = []
    core_entry_rows: list[EntryDiagnostic] = []
    for event in events:
        rows_15m = rows_15m_by_asset[event.instrument]
        for model in LEFT_MODELS:
            limit_model = model.removeprefix("left_")
            core_entry_rows.append(evaluate_left_limit(event, rows_15m, model=limit_model))
            entry_rows.append(evaluate_left_limit(event, rows_15m, model=limit_model, path_horizon_hours=96))
        core_entry_rows.append(evaluate_right_confirmation(event, rows_4h_by_asset[event.instrument], rows_15m))
        entry_rows.append(
            evaluate_right_confirmation(
                event,
                rows_4h_by_asset[event.instrument],
                rows_15m,
                path_horizon_hours=96,
            )
        )
    breakout_metrics = _breakout_metrics(events, rows_15m_by_asset)
    core_metrics = _model_metrics(events, core_entry_rows)
    extended_metrics = _extended_model_metrics(events, entry_rows)
    paired_metrics = _extended_paired_metrics(entry_rows)
    subgroup_metrics = _subgroup_metrics(events, entry_rows, instruments=instruments)
    decision = _decision(len(events), breakout_metrics, core_metrics)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _extended_report(
            start_date,
            end_date,
            instruments,
            events,
            breakout_metrics,
            core_metrics,
            extended_metrics,
            paired_metrics,
            subgroup_metrics,
            decision,
        ),
        encoding="utf-8",
    )
    return QuickCompareResult(str(report_path.resolve()), decision, len(events), holdout_start_ms)


def run_tc_bp_35m_comprehensive_diagnostic(
    *,
    repository: DuckDbCandleRepository,
    report_path: Path,
    start_date: str = "2022-01-01",
    end_date: str = "2024-11-30",
    instruments: Sequence[str] = ("BTC-USDT-SWAP",),
) -> QuickCompareResult:
    if end_date >= HOLDOUT_START:
        raise ValueError(f"end_date must be before sealed holdout {HOLDOUT_START}")
    start_ms, end_ms = _date_bounds(start_date, end_date)
    holdout_start_ms, _ = _date_bounds(HOLDOUT_START, HOLDOUT_START)
    warmup_ms = start_ms - CONTEXT_WARMUP_MS
    diagnostic_end_ms = min(end_ms + 96 * 60 * 60 * 1000, holdout_start_ms - FIFTEEN_MINUTES_MS - 1)
    events: list[TrueBreakoutEvent] = []
    rows_4h_by_asset: dict[str, Sequence[Candle]] = {}
    rows_15m_by_asset: dict[str, Sequence[Candle]] = {}
    for instrument in instruments:
        rows_4h = repository.load_range(instrument, "4H", warmup_ms, end_ms, inst_type="SWAP")
        rows_15m = repository.load_range(instrument, "15m", warmup_ms, diagnostic_end_ms, inst_type="SWAP")
        rows_4h_by_asset[instrument] = rows_4h
        rows_15m_by_asset[instrument] = rows_15m
        events.extend(build_true_breakout_diagnostic_events(instrument, rows_4h, start_ms=start_ms, end_ms=end_ms))
    entry_rows: list[EntryDiagnostic] = []
    for event in events:
        rows_15m = rows_15m_by_asset[event.instrument]
        left = evaluate_left_limit(event, rows_15m, model="level_edge_limit", path_horizon_hours=48)
        hard = evaluate_right_confirmation(event, rows_4h_by_asset[event.instrument], rows_15m, path_horizon_hours=48)
        soft = evaluate_right_confirmation_soft_vpa(event, rows_4h_by_asset[event.instrument], rows_15m, path_horizon_hours=48)
        entry_rows.extend((left, hard, soft))
    breakout_metrics = _breakout_metrics(events, rows_15m_by_asset)
    model_metrics = _model_metrics(events, entry_rows, models=COMPREHENSIVE_MODELS)
    trend_rows = _grouped_entry_metrics(events, entry_rows, group_field="trend_score_label", models=(LEFT_MODELS[0], SOFT_RIGHT_MODEL))
    attempt_rows = _grouped_entry_metrics(events, entry_rows, group_field="attempt_bucket", models=(LEFT_MODELS[0], SOFT_RIGHT_MODEL))
    lifecycle_rows = _grouped_entry_metrics(events, entry_rows, group_field="retest_lifecycle", models=(SOFT_RIGHT_MODEL,))
    confirmation_rows = _grouped_entry_metrics(events, entry_rows, group_field="confirmation_type", models=(SOFT_RIGHT_MODEL,))
    vpa_rows = _grouped_entry_metrics(events, entry_rows, group_field="vpa_bucket", models=(SOFT_RIGHT_MODEL,))
    decision = _comprehensive_decision(events, breakout_metrics, model_metrics, vpa_rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _comprehensive_report(
            start_date,
            end_date,
            instruments,
            events,
            breakout_metrics,
            model_metrics,
            trend_rows,
            attempt_rows,
            lifecycle_rows,
            confirmation_rows,
            vpa_rows,
            decision,
        ),
        encoding="utf-8",
    )
    return QuickCompareResult(str(report_path.resolve()), decision, len(events), holdout_start_ms)


def _left_limit_price(event: TrueBreakoutEvent, model: str) -> float:
    if model == "level_edge_limit":
        return event.level_upper + 0.05 * event.atr if event.direction == "long" else event.level_lower - 0.05 * event.atr
    midpoint = (event.breakout_high + event.breakout_low) / 2.0
    if model == "breakout_mid_limit":
        return max(event.level_upper, midpoint) if event.direction == "long" else min(event.level_lower, midpoint)
    if model != "impulse_382_limit":
        raise ValueError(f"unsupported left entry model: {model}")
    outer = event.level_upper if event.direction == "long" else event.level_lower
    impulse = abs(event.impulse_extreme - outer)
    return event.impulse_extreme - 0.382 * impulse if event.direction == "long" else event.impulse_extreme + 0.382 * impulse


def _trend_score(rows_4h: Sequence[Candle], index: int, direction: str, swing_trend: str, atr: float) -> tuple[float, str]:
    sign = 1.0 if direction == "long" else -1.0
    score = 0.0
    if swing_trend == direction:
        score += 2.0
    elif swing_trend in {"long", "short"}:
        score -= 2.0
    closes = [row.close for row in rows_4h[: index + 1]]
    if len(closes) >= 3:
        fast = _ema(closes, 20)[-1]
        slow = _ema(closes, 50)[-1]
        if sign * (fast - slow) > 0:
            score += 1.0
        elif sign * (fast - slow) < 0:
            score -= 1.0
    if len(closes) >= 7 and atr > 0:
        slope = (closes[-1] - closes[-7]) / atr
        if sign * slope > 0.25:
            score += 1.0
        elif sign * slope < -0.25:
            score -= 1.0
    if score >= 2.0:
        return score, "trend_score_match"
    if score <= -2.0:
        return score, "trend_opposite"
    return score, "trend_unknown_or_transition"


def _ema(values: Sequence[float], period: int) -> tuple[float, ...]:
    if not values:
        return ()
    alpha = 2.0 / (period + 1.0)
    output = [float(values[0])]
    for value in values[1:]:
        output.append(alpha * float(value) + (1.0 - alpha) * output[-1])
    return tuple(output)


def _valid_retest(event: TrueBreakoutEvent, row: Candle) -> bool:
    if event.direction == "long":
        touched = row.low <= event.level_upper + 0.10 * event.atr
        depth = max(0.0, event.level_upper - row.low) / event.atr
        return touched and depth <= 0.35 and row.close >= event.level_upper
    touched = row.high >= event.level_lower - 0.10 * event.atr
    depth = max(0.0, row.high - event.level_lower) / event.atr
    return touched and depth <= 0.35 and row.close <= event.level_lower


def _find_soft_retest_segment(event: TrueBreakoutEvent, rows_4h: Sequence[Candle], stop: float) -> RetestSegment:
    retests = [(index, row) for index, row in enumerate(rows_4h) if row.is_confirmed and row.timestamp_ms >= event.acceptance_time][:12]
    start_index = None
    min_low = float("inf")
    max_high = float("-inf")
    close_inside_count = 0
    wick_breach = False
    close_breach = False
    for index, row in retests:
        touched = (
            row.low <= event.level_upper + 0.20 * event.atr
            if event.direction == "long"
            else row.high >= event.level_lower - 0.20 * event.atr
        )
        if start_index is None:
            if not touched:
                continue
            start_index = index
        min_low = min(min_low, row.low)
        max_high = max(max_high, row.high)
        if event.direction == "long":
            close_inside = row.close < event.level_upper
            outside_reclaim = row.close >= event.level_upper
            wick_breach = wick_breach or row.low <= stop
            close_breach = close_breach or row.close <= stop
        else:
            close_inside = row.close > event.level_lower
            outside_reclaim = row.close <= event.level_lower
            wick_breach = wick_breach or row.high >= stop
            close_breach = close_breach or row.close >= stop
        close_inside_count = close_inside_count + 1 if close_inside else 0
        if outside_reclaim:
            depth = _soft_retest_depth(event, min_low, max_high)
            lifecycle = _soft_retest_lifecycle(depth, wick_breach, close_breach)
            return RetestSegment(
                status="accepted",
                lifecycle=lifecycle,
                start_index=start_index,
                end_index=index,
                depth_atr=depth,
                duration_4h_bars=index - start_index + 1,
                close_inside_count=close_inside_count,
                wick_breach=wick_breach,
                close_breach=close_breach,
            )
    if start_index is None:
        return RetestSegment(status="no_valid_level_retest", lifecycle="no_retest")
    depth = _soft_retest_depth(event, min_low, max_high)
    if close_inside_count >= 2 or close_breach:
        return RetestSegment(
            status="confirmed_pre_entry_failure",
            lifecycle="confirmed_failure",
            start_index=start_index,
            depth_atr=depth,
            close_inside_count=close_inside_count,
            wick_breach=wick_breach,
            close_breach=close_breach,
        )
    return RetestSegment(
        status="no_reclaim_after_retest",
        lifecycle="no_reclaim_after_retest",
        start_index=start_index,
        depth_atr=depth,
        close_inside_count=close_inside_count,
        wick_breach=wick_breach,
        close_breach=close_breach,
    )


def _soft_retest_depth(event: TrueBreakoutEvent, min_low: float, max_high: float) -> float:
    if event.direction == "long":
        return max(0.0, event.level_upper - min_low) / event.atr
    return max(0.0, max_high - event.level_lower) / event.atr


def _soft_retest_lifecycle(depth: float, wick_breach: bool, close_breach: bool) -> str:
    if close_breach:
        return "close_breach_reclaimed"
    if wick_breach:
        return "wick_breach_reclaimed"
    if depth > 0.35:
        return "deep_but_reclaimed"
    return "shallow_retest"


def _find_soft_15m_confirmation(
    event: TrueBreakoutEvent,
    rows_15m: Sequence[Candle],
    observation_start: int,
    stop: float,
) -> SoftConfirmation:
    candidates = [(index, row) for index, row in enumerate(rows_15m) if row.is_confirmed and row.timestamp_ms >= observation_start]
    stop_close_count = 0
    for checked, (index, row) in enumerate(candidates[:8], start=1):
        if event.direction == "long":
            close_failed = row.close <= stop
            close_location = (row.close - row.low) / (row.high - row.low) if row.high > row.low else 0.5
            level_reclaim = row.close >= event.level_upper and close_location >= 0.5
            previous = rows_15m[max(0, index - 3):index]
            micro_bos = len(previous) == 3 and row.close > max(item.high for item in previous) and close_location >= 0.5
            directional = row.close > row.open and close_location >= 0.5
        else:
            close_failed = row.close >= stop
            close_location = (row.close - row.low) / (row.high - row.low) if row.high > row.low else 0.5
            level_reclaim = row.close <= event.level_lower and close_location <= 0.5
            previous = rows_15m[max(0, index - 3):index]
            micro_bos = len(previous) == 3 and row.close < min(item.low for item in previous) and close_location <= 0.5
            directional = row.close < row.open and close_location <= 0.5
        stop_close_count = stop_close_count + 1 if close_failed else 0
        if stop_close_count >= 2:
            return SoftConfirmation(status="confirmed_pre_entry_failure")
        relaunch_vpa = directional and _relative_range(rows_15m, index, VPA_15M_LOOKBACK) >= 1.10 and _relative_volume(rows_15m, index, VPA_15M_LOOKBACK) >= 1.10
        confirmation_type = None
        if micro_bos:
            confirmation_type = "micro_bos_confirm"
        elif relaunch_vpa:
            confirmation_type = "vpa_relaunch_confirm"
        elif level_reclaim:
            confirmation_type = "level_reclaim_confirm"
        if confirmation_type is None:
            continue
        next_index = index + 1
        if next_index >= len(rows_15m) or rows_15m[next_index].timestamp_ms != row.timestamp_ms + FIFTEEN_MINUTES_MS:
            return SoftConfirmation(status="missing_entry_bar")
        signal_time = row.timestamp_ms + FIFTEEN_MINUTES_MS
        return SoftConfirmation(
            status="confirmed",
            confirmation_type=confirmation_type,
            confirmation_index=index,
            signal_time=signal_time,
            entry_time=signal_time + FIFTEEN_MINUTES_MS,
            entry_reference_price=rows_15m[next_index].close,
        )
    return SoftConfirmation(status="no_confirmation")


def _soft_vpa_score(
    event: TrueBreakoutEvent,
    rows_4h: Sequence[Candle],
    rows_15m: Sequence[Candle],
    retest: RetestSegment,
    confirmation: SoftConfirmation,
    entry_distance_atr: float,
) -> tuple[float, str]:
    breakout_index = _bar_index_by_close_time(rows_4h, event.breakout_time, FOUR_HOURS_MS)
    acceptance_index = _bar_index_by_close_time(rows_4h, event.acceptance_time, FOUR_HOURS_MS)
    score = 0.0
    if breakout_index is not None:
        score += 1.0 if _relative_volume(rows_4h, breakout_index, VPA_4H_LOOKBACK) >= 1.20 else 0.0
        score += 1.0 if _relative_range(rows_4h, breakout_index, VPA_4H_LOOKBACK) >= 1.10 else 0.0
    if acceptance_index is not None:
        score += 1.0 if _relative_range(rows_4h, acceptance_index, VPA_4H_LOOKBACK) >= 0.80 else 0.0
    if retest.lifecycle in {"shallow_retest", "wick_breach_reclaimed", "deep_but_reclaimed", "close_breach_reclaimed"}:
        score += 1.0
    if confirmation.confirmation_index is not None:
        score += 1.0 if _relative_volume(rows_15m, confirmation.confirmation_index, VPA_15M_LOOKBACK) >= 1.10 else 0.0
        score += 1.0 if _relative_range(rows_15m, confirmation.confirmation_index, VPA_15M_LOOKBACK) >= 1.10 else 0.0
    if entry_distance_atr <= 0.75:
        score += 1.0
    elif entry_distance_atr > 1.25:
        score -= 1.0
    if score >= 5.0:
        return score, "strong_vpa"
    if score >= 3.0:
        return score, "normal_vpa"
    return score, "weak_vpa"


def _bar_index_by_close_time(rows: Sequence[Candle], close_time: int, timeframe_ms: int) -> int | None:
    open_time = close_time - timeframe_ms
    return next((index for index, row in enumerate(rows) if row.timestamp_ms == open_time), None)


def _relative_volume(rows: Sequence[Candle], index: int, lookback: int) -> float:
    baseline = [row.volume for row in rows[max(0, index - lookback):index] if row.volume > 0]
    if not baseline:
        return 1.0
    return rows[index].volume / (sum(baseline) / len(baseline))


def _relative_range(rows: Sequence[Candle], index: int, lookback: int) -> float:
    baseline = [row.high - row.low for row in rows[max(0, index - lookback):index] if row.high > row.low]
    if not baseline or rows[index].high <= rows[index].low:
        return 1.0
    return (rows[index].high - rows[index].low) / (sum(baseline) / len(baseline))


def _triggered_result(
    event: TrueBreakoutEvent,
    model: str,
    entry: float,
    entry_time: int,
    future: Sequence[Candle],
    stop: float,
    *,
    path_horizon_hours: int = 48,
) -> EntryDiagnostic:
    risk = abs(entry - stop)
    horizon_paths = tuple(
        (
            hours,
            _path_diagnostic(event.direction, entry, stop, risk, entry_time, future, horizon_hours=hours),
        )
        for hours in DIAGNOSTIC_HORIZONS
        if hours <= path_horizon_hours
    )
    path = dict(horizon_paths)[path_horizon_hours]
    return EntryDiagnostic(
        event_id=event.event_id,
        model=model,
        status="triggered",
        entry_time=entry_time,
        entry_price=entry,
        entry_to_level_atr=_entry_distance(event, entry),
        stop_distance_atr=risk / event.atr,
        stop_distance_pct=risk / entry * 100.0,
        path_order=path.path_order,
        path_window_complete=path.window_complete,
        two_r_first=path.two_r_first,
        one_point_five_r_first=path.one_point_five_r_first,
        no_decision=path.no_decision,
        time_to_1r_minutes=path.time_to_1r_minutes,
        time_to_invalidation_minutes=path.time_to_invalidation_minutes,
        forward_2h_return_pct=_forward_return(event.direction, entry, entry_time, future, 2),
        forward_4h_return_pct=_forward_return(event.direction, entry, entry_time, future, 4),
        forward_8h_return_pct=_forward_return(event.direction, entry, entry_time, future, 8),
        forward_12h_return_pct=_forward_return(event.direction, entry, entry_time, future, 12),
        forward_16h_return_pct=_forward_return(event.direction, entry, entry_time, future, 16),
        forward_20h_return_pct=_forward_return(event.direction, entry, entry_time, future, 20),
        forward_24h_return_pct=_forward_return(event.direction, entry, entry_time, future, 24),
        forward_36h_return_pct=_forward_return(event.direction, entry, entry_time, future, 36),
        forward_48h_return_pct=_forward_return(event.direction, entry, entry_time, future, 48),
        forward_60h_return_pct=_forward_return(event.direction, entry, entry_time, future, 60),
        forward_72h_return_pct=_forward_return(event.direction, entry, entry_time, future, 72),
        forward_96h_return_pct=_forward_return(event.direction, entry, entry_time, future, 96),
        mfe_pct=path.mfe_pct,
        mae_pct=path.mae_pct,
        mfe_r=path.mfe_r,
        mae_r=path.mae_r,
        horizon_paths=horizon_paths,
        trend_score_label=event.trend_score_label,
        breakout_attempt_number=event.breakout_attempt_number,
    )


def _path_diagnostic(
    direction: str,
    entry: float,
    stop: float,
    risk: float,
    entry_time: int,
    rows: Sequence[Candle],
    *,
    horizon_hours: int,
) -> PathDiagnostic:
    one_r = entry + risk if direction == "long" else entry - risk
    one_point_five_r = entry + 1.5 * risk if direction == "long" else entry - 1.5 * risk
    two_r = entry + 2.0 * risk if direction == "long" else entry - 2.0 * risk
    stop_time = None
    one_r_time = None
    one_point_five_r_time = None
    two_r_time = None
    ambiguous = False
    window_end = entry_time + horizon_hours * 60 * 60 * 1000
    window = [row for row in rows if row.timestamp_ms + FIFTEEN_MINUTES_MS <= window_end]
    window_complete = bool(window) and window[-1].timestamp_ms + FIFTEEN_MINUTES_MS >= window_end
    for row in window:
        stop_hit = row.low <= stop if direction == "long" else row.high >= stop
        one_r_hit = row.high >= one_r if direction == "long" else row.low <= one_r
        one_point_five_r_hit = row.high >= one_point_five_r if direction == "long" else row.low <= one_point_five_r
        two_r_hit = row.high >= two_r if direction == "long" else row.low <= two_r
        source_time = row.timestamp_ms + FIFTEEN_MINUTES_MS
        if stop_hit and one_r_hit and stop_time is None and one_r_time is None:
            ambiguous = True
            break
        if stop_hit and stop_time is None:
            stop_time = source_time
        if one_r_hit and one_r_time is None:
            one_r_time = source_time
        if one_point_five_r_hit and one_point_five_r_time is None:
            one_point_five_r_time = source_time
        if two_r_hit and two_r_time is None:
            two_r_time = source_time
    if not window_complete:
        mfe = None
        mae = None
    elif direction == "long":
        mfe = max((row.high - entry for row in window), default=None)
        mae = max((entry - row.low for row in window), default=None)
    else:
        mfe = max((entry - row.low for row in window), default=None)
        mae = max((row.high - entry for row in window), default=None)
    mfe = None if mfe is None else max(0.0, mfe)
    mae = None if mae is None else max(0.0, mae)
    if ambiguous:
        path_order = "ambiguous_intrabar_path"
    elif one_r_time is not None and (stop_time is None or one_r_time < stop_time):
        path_order = "one_r_first"
    elif stop_time is not None:
        path_order = "invalidation_first"
    else:
        path_order = "no_decision"
    return PathDiagnostic(
        path_order=path_order,
        window_complete=window_complete,
        one_point_five_r_first=one_point_five_r_time is not None and (stop_time is None or one_point_five_r_time < stop_time),
        two_r_first=two_r_time is not None and (stop_time is None or two_r_time < stop_time),
        no_decision=one_r_time is None and stop_time is None,
        time_to_1r_minutes=None if one_r_time is None or (stop_time is not None and one_r_time >= stop_time) else int((one_r_time - entry_time) / 60_000),
        time_to_invalidation_minutes=None if stop_time is None else int((stop_time - entry_time) / 60_000),
        mfe_pct=None if mfe is None else mfe / entry * 100.0,
        mae_pct=None if mae is None else mae / entry * 100.0,
        mfe_r=None if mfe is None or risk <= 0 else mfe / risk,
        mae_r=None if mae is None or risk <= 0 else mae / risk,
    )


def _forward_return(direction: str, entry: float, entry_time: int, rows: Sequence[Candle], hours: int) -> float | None:
    target_time = entry_time + hours * 60 * 60 * 1000
    row = next((item for item in rows if item.timestamp_ms + FIFTEEN_MINUTES_MS >= target_time), None)
    if row is None:
        return None
    sign = 1.0 if direction == "long" else -1.0
    return sign * (row.close - entry) / entry * 100.0


def _entry_distance(event: TrueBreakoutEvent, entry: float) -> float:
    return (entry - event.level_upper) / event.atr if event.direction == "long" else (event.level_lower - entry) / event.atr


def _empty_result(event: TrueBreakoutEvent, model: str, status: str, reason: str, **extra: object) -> EntryDiagnostic:
    return EntryDiagnostic(event_id=event.event_id, model=model, status=status, failure_reason=reason, **extra)


def _breakout_metrics(events: Sequence[TrueBreakoutEvent], rows_by_asset: Mapping[str, Sequence[Candle]]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for event in events:
        values = {hours: _forward_return(event.direction, event.acceptance_close, event.acceptance_time, rows_by_asset[event.instrument], hours) for hours in (4, 12, 24)}
        rows.append({"asset": event.instrument, "direction": event.direction, **{f"r{hours}": value for hours, value in values.items()}})
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups["overall"].append(row)
        groups[f"asset:{row['asset']}"].append(row)
        groups[f"direction:{row['direction']}"].append(row)
    return {
        "overall": _return_summary(rows),
        "groups": {name: _return_summary(group) for name, group in sorted(groups.items()) if name != "overall"},
    }


def _return_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {"count": len(rows), **{f"median_{hours}h": _median(row.get(f"r{hours}") for row in rows) for hours in (4, 12, 24)}}


def _model_metrics(
    events: Sequence[TrueBreakoutEvent],
    rows: Sequence[EntryDiagnostic],
    *,
    models: Sequence[str] = MODELS,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for model in models:
        selected = [row for row in rows if row.model == model]
        triggered = [row for row in selected if row.status in {"triggered", "ambiguous_intrabar_path"}]
        fixed_return_rows = [row for row in selected if row.status == "triggered"]
        path_rows = [row for row in triggered if row.status == "triggered" and _path_rate_eligible(row)]
        failures = Counter(row.failure_reason or row.status for row in selected if row.status != "triggered")
        output[model] = {
            "events": len(events),
            "triggered": len(triggered),
            "trigger_rate": len(triggered) / len(events) if events else 0.0,
            "one_r_first": sum(row.path_order == "one_r_first" for row in path_rows) / len(path_rows) if path_rows else 0.0,
            "one_point_five_r_first": _bool_rate(path_rows, lambda row: row.one_point_five_r_first is True),
            "two_r_first": _bool_rate(path_rows, lambda row: row.two_r_first is True),
            "invalidation_first": sum(row.path_order == "invalidation_first" for row in path_rows) / len(path_rows) if path_rows else 0.0,
            "median_entry_to_level_atr": _median(row.entry_to_level_atr for row in triggered),
            "median_4h": _median(row.forward_4h_return_pct for row in fixed_return_rows),
            "median_12h": _median(row.forward_12h_return_pct for row in fixed_return_rows),
            "main_failure": failures.most_common(1)[0][0] if failures else "none",
        }
    return output


def _extended_model_metrics(
    events: Sequence[TrueBreakoutEvent],
    rows: Sequence[EntryDiagnostic],
    *,
    models: Sequence[str] = MODELS,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for model in models:
        selected = [row for row in rows if row.model == model]
        fills = [row for row in selected if row.status in {"triggered", "ambiguous_intrabar_path"}]
        triggered = [row for row in selected if row.status == "triggered"]
        path_valid = [row for row in triggered if _path_rate_eligible(row)]
        stop_pct = [float(row.stop_distance_pct) for row in fills if row.stop_distance_pct is not None]
        output[model] = {
            "events": len(events),
            "triggered": len(fills),
            "median_stop_distance_atr": _median(row.stop_distance_atr for row in fills),
            "median_stop_distance_pct": _median(stop_pct),
            "p25_stop_distance_pct": _percentile(stop_pct, 0.25),
            "p75_stop_distance_pct": _percentile(stop_pct, 0.75),
            "median_entry_to_level_atr": _median(row.entry_to_level_atr for row in fills),
            "one_r_first": _bool_rate(path_valid, lambda row: row.path_order == "one_r_first"),
            "one_point_five_r_first": _bool_rate(path_valid, lambda row: row.one_point_five_r_first is True),
            "two_r_first": _bool_rate(path_valid, lambda row: row.two_r_first is True),
            "invalidation_first": _bool_rate(path_valid, lambda row: row.path_order == "invalidation_first"),
            "no_decision_rate": _bool_rate(path_valid, lambda row: row.no_decision is True),
            "median_time_to_1r_minutes": _median(row.time_to_1r_minutes for row in path_valid),
            "median_time_to_invalidation_minutes": _median(row.time_to_invalidation_minutes for row in path_valid),
            **{f"median_{hours}h": _median(getattr(row, f"forward_{hours}h_return_pct") for row in triggered) for hours in DIAGNOSTIC_HORIZONS},
            "median_mfe_pct": _median(row.mfe_pct for row in triggered),
            "median_mae_pct": _median(row.mae_pct for row in triggered),
            "median_mfe_r": _median(row.mfe_r for row in triggered),
            "median_mae_r": _median(row.mae_r for row in triggered),
        }
        for hours in DIAGNOSTIC_HORIZONS:
            paths = [dict(row.horizon_paths).get(hours) for row in triggered]
            paths = [path for path in paths if path is not None]
            output[model].update({
                f"median_mfe_pct_{hours}h": _median(path.mfe_pct for path in paths),
                f"median_mae_pct_{hours}h": _median(path.mae_pct for path in paths),
                f"median_mfe_r_{hours}h": _median(path.mfe_r for path in paths),
                f"median_mae_r_{hours}h": _median(path.mae_r for path in paths),
            })
    return output


def _extended_paired_metrics(rows: Sequence[EntryDiagnostic]) -> list[dict[str, object]]:
    by_key = {(row.event_id, row.model): row for row in rows}
    output: list[dict[str, object]] = []
    for left_model in LEFT_MODELS:
        pairs: list[tuple[EntryDiagnostic, EntryDiagnostic]] = []
        for (event_id, model), left in by_key.items():
            right = by_key.get((event_id, "right_level_retest_confirm"))
            if (
                model == left_model
                and right is not None
                and left.status == "triggered"
                and right.status == "triggered"
            ):
                pairs.append((left, right))
        path_pairs = [pair for pair in pairs if _path_rate_eligible(pair[0]) and _path_rate_eligible(pair[1])]
        row: dict[str, object] = {
            "left_model": left_model,
            "paired_count": len(pairs),
            "left_stop_pct": _median(pair[0].stop_distance_pct for pair in pairs),
            "right_stop_pct": _median(pair[1].stop_distance_pct for pair in pairs),
            "left_two_r_first": _bool_rate([pair[0] for pair in path_pairs], lambda item: item.two_r_first is True),
            "right_two_r_first": _bool_rate([pair[1] for pair in path_pairs], lambda item: item.two_r_first is True),
            "left_mfe_pct": _median(pair[0].mfe_pct for pair in pairs),
            "right_mfe_pct": _median(pair[1].mfe_pct for pair in pairs),
            "left_mae_pct": _median(pair[0].mae_pct for pair in pairs),
            "right_mae_pct": _median(pair[1].mae_pct for pair in pairs),
        }
        for hours in (24, 48, 72, 96):
            row[f"left_{hours}h"] = _median(getattr(pair[0], f"forward_{hours}h_return_pct") for pair in pairs)
            row[f"right_{hours}h"] = _median(getattr(pair[1], f"forward_{hours}h_return_pct") for pair in pairs)
        output.append(row)
    return output


def _subgroup_metrics(
    events: Sequence[TrueBreakoutEvent],
    rows: Sequence[EntryDiagnostic],
    *,
    instruments: Sequence[str] = DEFAULT_INSTRUMENTS,
) -> list[dict[str, object]]:
    event_by_id = {event.event_id: event for event in events}
    output: list[dict[str, object]] = []
    for model in MODELS:
        selected = [row for row in rows if row.model == model and row.status == "triggered"]
        for dimension, values in (
            ("asset", instruments),
            ("direction", ("long", "short")),
        ):
            for value in values:
                group = [row for row in selected if getattr(event_by_id[row.event_id], "instrument" if dimension == "asset" else "direction") == value]
                path_group = [row for row in group if _path_rate_eligible(row)]
                output.append({
                    "model": model,
                    "dimension": dimension,
                    "value": value,
                    "count": len(group),
                    "one_r_first": _bool_rate(path_group, lambda row: row.path_order == "one_r_first"),
                    "one_point_five_r_first": _bool_rate(path_group, lambda row: row.one_point_five_r_first is True),
                    "two_r_first": _bool_rate(path_group, lambda row: row.two_r_first is True),
                    "invalidation_first": _bool_rate(path_group, lambda row: row.path_order == "invalidation_first"),
                    "median_48h": _median(row.forward_48h_return_pct for row in group),
                    "median_72h": _median(row.forward_72h_return_pct for row in group),
                    "median_96h": _median(row.forward_96h_return_pct for row in group),
                    "median_mfe_pct": _median(row.mfe_pct for row in group),
                    "median_mae_pct": _median(row.mae_pct for row in group),
                })
    return output


def _extended_report(
    start: str,
    end: str,
    instruments: Sequence[str],
    events: Sequence[TrueBreakoutEvent],
    breakout: Mapping[str, object],
    core: Mapping[str, Mapping[str, object]],
    extended: Mapping[str, Mapping[str, object]],
    paired: Sequence[Mapping[str, object]],
    subgroups: Sequence[Mapping[str, object]],
    decision: str,
) -> str:
    upstream = dict(breakout["overall"])
    best_by_horizon = {
        hours: max(MODELS, key=lambda model: float(extended[model].get(f"median_{hours}h") or float("-inf")))
        for hours in (48, 72, 96)
    }
    edge = extended["left_level_edge_limit"]
    right = extended["right_level_retest_confirm"]
    edge_has_longer_edge = any(float(edge.get(f"median_{hours}h") or 0.0) > 0.0 for hours in (48, 72, 96))
    edge_not_only_small_r = float(edge["two_r_first"]) > float(edge["invalidation_first"]) and edge_has_longer_edge
    right_overtakes = [
        hours
        for hours in (48, 72, 96)
        if float(right.get(f"median_{hours}h") or float("-inf")) > float(edge.get(f"median_{hours}h") or float("-inf"))
    ]
    lines = [
        "# TC BP Entry Model Quick Compare Extended",
        "",
        "## 实验边界",
        "",
        f"- Development window: `{start}` 至 `{end}`；{' / '.join(instruments)}。",
        f"- 共享 true breakout events: {len(events)}；两个 entry model 共用同一事件池。",
        "- True breakout 使用 fresh cross：前一根 4H close 必须仍在 level 内侧；第一次 accepted breakout 后该 level 即被消耗。",
        "- Level 最长有效 180 天；trend_state 只由 causal confirmed swings 计算；固定 187 天 warmup 保证窗口重叠结果一致。",
        f"- Upstream acceptance-reference 4H / 12H / 24H median signed return: {_fmt(upstream.get('median_4h'))} / {_fmt(upstream.get('median_12h'))} / {_fmt(upstream.get('median_24h'))}。",
        "- Raw OHLCV only；holdout 未读取；未修改正式配置、RiskEngine、cost、exit、sizing。",
        "- 本报告仅含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`；future return、MFE/MAE、path-order 不进入 feature。",
        "- 原始核心表保留原实验 48H path-order 口径；扩展 path-order 与 MFE/MAE 观察窗为入场后最多 96H。",
        "- 同根 15m 同时触发目标和 invalidation 的样本排除出主路径统计。",
        "",
        "## 双模型核心表",
        "",
        "| model | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for model in MODELS:
        row = core[model]
        lines.append(
            f"| {model} | {row['events']} | {row['triggered']} | {row['trigger_rate']:.2%} | "
            f"{row['one_r_first']:.2%} | {row['one_point_five_r_first']:.2%} | {row['two_r_first']:.2%} | "
            f"{row['invalidation_first']:.2%} | {_num(row['median_entry_to_level_atr'])} | "
            f"{_fmt(row['median_4h'])} | {_fmt(row['median_12h'])} | {row['main_failure']} |"
        )
    lines.extend([
        "",
        "## 风险距离",
        "",
        "| model | triggered | median_stop_distance_ATR | median_stop_distance_pct | p25_stop_distance_pct | p75_stop_distance_pct | median_entry_to_level_ATR |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for model in MODELS:
        row = extended[model]
        lines.append(
            f"| {model} | {row['triggered']} | {_num(row['median_stop_distance_atr'])} | {_fmt(row['median_stop_distance_pct'])} | "
            f"{_fmt(row['p25_stop_distance_pct'])} | {_fmt(row['p75_stop_distance_pct'])} | {_num(row['median_entry_to_level_atr'])} |"
        )
    lines.extend([
        "",
        "## R 倍数路径",
        "",
        "| model | +1R_first | +1.5R_first | +2R_first | invalidation_first | no_decision_rate | median_time_to_1R | median_time_to_invalidation |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for model in MODELS:
        row = extended[model]
        lines.append(
            f"| {model} | {row['one_r_first']:.2%} | {row['one_point_five_r_first']:.2%} | {row['two_r_first']:.2%} | {row['invalidation_first']:.2%} | "
            f"{row['no_decision_rate']:.2%} | {_minutes(row['median_time_to_1r_minutes'])} | {_minutes(row['median_time_to_invalidation_minutes'])} |"
        )
    lines.extend([
        "",
        "## 固定时间方向收益",
        "",
        "正值表示沿交易方向移动。96H 为回答长期对照问题而补充。",
        "",
        "| model | 2H | 4H | 8H | 12H | 16H | 20H | 24H | 36H | 48H | 60H | 72H | 96H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for model in MODELS:
        row = extended[model]
        lines.append(f"| {model} | " + " | ".join(_fmt(row[f"median_{hours}h"]) for hours in DIAGNOSTIC_HORIZONS) + " |")
    lines.extend([
        "",
        "## MFE / MAE",
        "",
        "| model | horizon | median_MFE_pct | median_MAE_pct | median_MFE_R | median_MAE_R |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for model in MODELS:
        row = extended[model]
        for hours in DIAGNOSTIC_HORIZONS:
            lines.append(
                f"| {model} | {hours}H | {_fmt(row[f'median_mfe_pct_{hours}h'])} | "
                f"{_fmt(row[f'median_mae_pct_{hours}h'])} | {_num(row[f'median_mfe_r_{hours}h'])} | "
                f"{_num(row[f'median_mae_r_{hours}h'])} |"
            )
    lines.extend([
        "",
        "## Paired Subset 拓展",
        "",
        "| left_model | paired | stop_pct L/R | 24H L/R | 48H L/R | 72H L/R | 96H L/R | +2R_first L/R | MFE_pct L/R | MAE_pct L/R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in paired:
        lines.append(
            f"| {row['left_model']} | {row['paired_count']} | {_fmt(row['left_stop_pct'])} / {_fmt(row['right_stop_pct'])} | "
            f"{_fmt(row['left_24h'])} / {_fmt(row['right_24h'])} | {_fmt(row['left_48h'])} / {_fmt(row['right_48h'])} | "
            f"{_fmt(row['left_72h'])} / {_fmt(row['right_72h'])} | {_fmt(row['left_96h'])} / {_fmt(row['right_96h'])} | "
            f"{row['left_two_r_first']:.2%} / {row['right_two_r_first']:.2%} | {_fmt(row['left_mfe_pct'])} / {_fmt(row['right_mfe_pct'])} | "
            f"{_fmt(row['left_mae_pct'])} / {_fmt(row['right_mae_pct'])} |"
        )
    lines.extend([
        "",
        "## Asset / Direction 简单分组",
        "",
        "| model | group | n | +1R_first | +1.5R_first | +2R_first | invalidation_first | 48H | 72H | 96H | MFE_pct | MAE_pct |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in subgroups:
        value = str(row["value"]).replace("-USDT-SWAP", "")
        lines.append(
            f"| {row['model']} | {row['dimension']}:{value} | {row['count']} | {row['one_r_first']:.2%} | "
            f"{row['one_point_five_r_first']:.2%} | {row['two_r_first']:.2%} | {row['invalidation_first']:.2%} | {_fmt(row['median_48h'])} | "
            f"{_fmt(row['median_72h'])} | {_fmt(row['median_96h'])} | {_fmt(row['median_mfe_pct'])} | {_fmt(row['median_mae_pct'])} |"
        )
    best_text = "、".join(f"{hours}H={best_by_horizon[hours]}" for hours in (48, 72, 96))
    lines.extend([
        "",
        "## 简短结论",
        "",
        f"1. `left_level_edge_limit` 的 +1R 优势{'并非完全由较小 R 造成，但长期证据不稳定，尚不能排除 R 几何放大' if edge_not_only_small_r else '仍有明显的小 R 几何嫌疑'}：其 +2R-first 为 {edge['two_r_first']:.2%}，invalidation-first 为 {edge['invalidation_first']:.2%}，48H/72H/96H 中位方向收益分别为 {_fmt(edge['median_48h'])} / {_fmt(edge['median_72h'])} / {_fmt(edge['median_96h'])}。",
        f"2. 各长期窗口中位数最高模型：{best_text}。这只是 development diagnostic，不是可交易绩效。",
        f"3. `right_level_retest_confirm` {'在 ' + '/'.join(str(value) + 'H' for value in right_overtakes) + ' 高于 left_level_edge_limit' if right_overtakes else '在 48H/72H/96H 均未反超 left_level_edge_limit'}。",
        f"4. {'建议保留右侧确认作为后续对照，左侧 level-edge 仍为主要研究对象。' if right_overtakes or any(float(right.get(f'median_{hours}h') or 0.0) > 0 for hours in (48, 72, 96)) else '当前证据只支持继续观察 left_level_edge_limit；右侧确认可停止扩展。'}",
        "",
        f"本次 decision：`{decision}`。本扩展不改变策略、参数或研究阶段。",
        "",
    ])
    return "\n".join(lines)


def _grouped_entry_metrics(
    events: Sequence[TrueBreakoutEvent],
    rows: Sequence[EntryDiagnostic],
    *,
    group_field: str,
    models: Sequence[str],
) -> list[dict[str, object]]:
    event_by_id = {event.event_id: event for event in events}
    output: list[dict[str, object]] = []
    for model in models:
        selected = [row for row in rows if row.model == model]
        groups: dict[str, list[EntryDiagnostic]] = defaultdict(list)
        event_counts: Counter[str] = Counter()
        event_level_group = group_field in {"trend_score_label", "attempt_bucket"}
        if event_level_group:
            for event in events:
                key = _group_key(event, None, group_field)
                event_counts[key] += 1
        for row in selected:
            key = _group_key(event_by_id[row.event_id], row, group_field)
            groups[key].append(row)
            if not event_level_group:
                event_counts[key] += 1
        for key in sorted(set((*event_counts.keys(), *groups.keys()))):
            group = groups.get(key, [])
            triggered = [row for row in group if row.status == "triggered"]
            path_valid = [row for row in triggered if _path_rate_eligible(row)]
            output.append({
                "model": model,
                "group": key,
                "events": event_counts[key],
                "triggered": len(triggered),
                "trigger_rate": len(triggered) / event_counts[key] if event_counts[key] else 0.0,
                "one_r_first": _bool_rate(path_valid, lambda row: row.path_order == "one_r_first"),
                "one_point_five_r_first": _bool_rate(path_valid, lambda row: row.one_point_five_r_first is True),
                "two_r_first": _bool_rate(path_valid, lambda row: row.two_r_first is True),
                "invalidation_first": _bool_rate(path_valid, lambda row: row.path_order == "invalidation_first"),
                "median_2h": _median(row.forward_2h_return_pct for row in triggered),
                "median_4h": _median(row.forward_4h_return_pct for row in triggered),
                "median_8h": _median(row.forward_8h_return_pct for row in triggered),
                "median_12h": _median(row.forward_12h_return_pct for row in triggered),
                "median_24h": _median(row.forward_24h_return_pct for row in triggered),
                "median_48h": _median(row.forward_48h_return_pct for row in triggered),
            })
    return output


def _group_key(event: TrueBreakoutEvent, row: EntryDiagnostic | None, group_field: str) -> str:
    if group_field == "trend_score_label":
        return event.trend_score_label
    if group_field == "attempt_bucket":
        attempt = event.breakout_attempt_number
        if attempt <= 1:
            return "attempt_1_first_accepted"
        if attempt == 2:
            return "attempt_2_later_accepted"
        return "attempt_3_plus_later_accepted"
    if group_field == "retest_lifecycle":
        return (row.retest_lifecycle if row is not None else None) or "not_applicable"
    if group_field == "confirmation_type":
        return (row.confirmation_type if row is not None else None) or "not_confirmed"
    if group_field == "vpa_bucket":
        return (row.vpa_bucket if row is not None else None) or "missing_vpa"
    raise ValueError(f"unsupported group field: {group_field}")


def _comprehensive_decision(
    events: Sequence[TrueBreakoutEvent],
    breakout: Mapping[str, object],
    model_metrics: Mapping[str, Mapping[str, object]],
    vpa_rows: Sequence[Mapping[str, object]],
) -> str:
    if not events:
        return "data_or_causality_issue_fix_first"
    hard = model_metrics[RIGHT_HARD_MODEL]
    soft = model_metrics[SOFT_RIGHT_MODEL]
    hard_trend_count = sum(event.trend_state == event.direction for event in events)
    non_hard_count = len(events) - hard_trend_count
    if non_hard_count > hard_trend_count * 0.5:
        return "trend_gate_overfiltered_continue_soft_score"
    if int(soft["triggered"]) > int(hard["triggered"]) and float(soft["one_r_first"]) > float(soft["invalidation_first"]):
        return "right_hard_gate_too_strict_soft_vpa_promising"
    strong = next((row for row in vpa_rows if row["group"] == "strong_vpa"), None)
    weak = next((row for row in vpa_rows if row["group"] == "weak_vpa"), None)
    if strong and weak and int(strong["triggered"]) >= 10 and float(strong["one_r_first"]) > float(weak["one_r_first"]):
        return "vpa_separates_quality_continue"
    if float(dict(breakout["overall"]).get("median_12h") or 0.0) <= 0.0:
        return "upstream_breakout_edge_still_failed_stop_bp"
    return "sample_expanded_but_quality_not_improved"


def _comprehensive_report(
    start: str,
    end: str,
    instruments: Sequence[str],
    events: Sequence[TrueBreakoutEvent],
    breakout: Mapping[str, object],
    model_metrics: Mapping[str, Mapping[str, object]],
    trend_rows: Sequence[Mapping[str, object]],
    attempt_rows: Sequence[Mapping[str, object]],
    lifecycle_rows: Sequence[Mapping[str, object]],
    confirmation_rows: Sequence[Mapping[str, object]],
    vpa_rows: Sequence[Mapping[str, object]],
    decision: str,
) -> str:
    upstream = dict(breakout["overall"])
    hard_trend_count = sum(event.trend_state == event.direction for event in events)
    attempt_counts = Counter(_group_key(event, None, "attempt_bucket") for event in events)
    lines = [
        "# TC/BP 35个月综合轻量诊断实验",
        "",
        "## 实验边界",
        "",
        f"- Development window: `{start}` 至 `{end}`；标的：{' / '.join(instruments)}。",
        f"- Holdout start: `{HOLDOUT_START}`，本实验不读取 holdout。",
        "- 本报告只包含 diagnostic labels，不生成 `execution_rows` 或 `closed_trade_rows`。",
        "- 未修改 RiskEngine、正式配置、cost、exit、sizing。",
        "- 事件、trend、VPA、entry diagnostic 均从 raw OHLCV 重新生成，不复用旧缓存。",
        "",
        "## Event funnel",
        "",
        "| item | count | note |",
        "|---|---:|---|",
        f"| raw true breakout candidates | {len(events)} | no trend hard gate；later level attempts allowed |",
        f"| current hard confirmed-swing trend match | {hard_trend_count} | trend_state == breakout direction |",
        f"| no trend gate retained | {len(events)} | diagnostic candidate pool |",
        f"| attempt 1 first accepted | {attempt_counts['attempt_1_first_accepted']} | current first-consume baseline |",
        f"| attempt 2 later accepted | {attempt_counts['attempt_2_later_accepted']} | level consume soft diagnostic |",
        f"| attempt >=3 later accepted | {attempt_counts['attempt_3_plus_later_accepted']} | repeated attempts diagnostic |",
        "",
        f"Upstream acceptance-reference 4H / 12H / 24H median signed return: {_fmt(upstream.get('median_4h'))} / {_fmt(upstream.get('median_12h'))} / {_fmt(upstream.get('median_24h'))}。",
        "",
        "## Entry model core",
        "",
        "备注：`+1R_first`、`+1.5R_first`、`+2R_first`、`invalidation_first` 均统计入场后 48H path-order 观察窗口；2H/4H/8H/12H/24H/48H 列为对应固定持仓时长的方向收益。",
        "",
        "| model | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for model in COMPREHENSIVE_MODELS:
        row = model_metrics[model]
        lines.append(
            f"| {model} | {row['events']} | {row['triggered']} | {row['trigger_rate']:.2%} | "
            f"{row['one_r_first']:.2%} | {row['one_point_five_r_first']:.2%} | {row['two_r_first']:.2%} | "
            f"{row['invalidation_first']:.2%} | {_num(row['median_entry_to_level_atr'])} | "
            f"{_fmt(row['median_4h'])} | {_fmt(row['median_12h'])} | {row['main_failure']} |"
        )
    lines.extend([
        "",
        "## Trend diagnostic",
        "",
        _group_table(trend_rows),
        "",
        "## Level consume / attempt diagnostic",
        "",
        _group_table(attempt_rows),
        "",
        "## Right retest lifecycle",
        "",
        _group_table(lifecycle_rows),
        "",
        "## Confirmation type",
        "",
        _group_table(confirmation_rows),
        "",
        "## VPA attribution",
        "",
        _group_table(vpa_rows),
        "",
        "## Decision",
        "",
        f"`{decision}`",
        "",
        "解释：本实验仍停留在 signal/entry diagnostic。fixed return、MFE/MAE、path-order 均为 diagnostic label，不允许进入 feature、score、gate 或正式策略。",
        "",
    ])
    return "\n".join(lines)


def _group_table(rows: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "| model | group | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | 2H | 4H | 8H | 12H | 24H | 48H |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['group']} | {row['events']} | {row['triggered']} | {row['trigger_rate']:.2%} | "
            f"{row['one_r_first']:.2%} | {row['one_point_five_r_first']:.2%} | {row['two_r_first']:.2%} | "
            f"{row['invalidation_first']:.2%} | {_fmt(row['median_2h'])} | "
            f"{_fmt(row['median_4h'])} | {_fmt(row['median_8h'])} | {_fmt(row['median_12h'])} | "
            f"{_fmt(row['median_24h'])} | {_fmt(row['median_48h'])} |"
        )
    return "\n".join(lines)


def _paired_metrics(rows: Sequence[EntryDiagnostic]) -> list[dict[str, object]]:
    by_key = {(row.event_id, row.model): row for row in rows}
    output = []
    right_model = "right_level_retest_confirm"
    for left_model in LEFT_MODELS:
        pairs = []
        for (event_id, model), left in by_key.items():
            right = by_key.get((event_id, right_model))
            if model == left_model and right is not None and left.status == "triggered" and right.status == "triggered":
                pairs.append((left, right))
        improvements = [float(right.entry_to_level_atr) - float(left.entry_to_level_atr) for left, right in pairs]
        output.append({
            "left_model": left_model,
            "paired_count": len(pairs),
            "left_better_price_rate": sum(value > 0 for value in improvements) / len(improvements) if improvements else 0.0,
            "left_avg_entry_improvement_atr": mean(improvements) if improvements else None,
            "left_one_r_first": _rate(pairs, 0, "one_r_first"),
            "right_one_r_first": _rate(pairs, 1, "one_r_first"),
            "left_invalidation_first": _rate(pairs, 0, "invalidation_first"),
            "right_invalidation_first": _rate(pairs, 1, "invalidation_first"),
        })
    return output


def _decision(event_count: int, breakout: Mapping[str, object], models: Mapping[str, Mapping[str, object]]) -> str:
    if event_count < 80:
        return "inconclusive_need_more_development_scan"
    if float(dict(breakout["overall"]).get("median_12h") or 0.0) <= 0:
        return "stop_bp_upstream_breakout_edge_failed"
    left_pass = any(_model_pass(row, max_entry_atr=0.75) for name, row in models.items() if name.startswith("left_"))
    right_pass = _model_pass(models["right_level_retest_confirm"], max_entry_atr=1.25)
    if left_pass and not right_pass:
        return "prefer_left_limit_entry_for_next_review"
    if right_pass and not left_pass:
        return "prefer_right_confirmation_entry_for_next_review"
    if not left_pass and not right_pass:
        return "stop_bp_entry_models_failed"
    return "inconclusive_need_more_development_scan"


def _model_pass(row: Mapping[str, object], *, max_entry_atr: float) -> bool:
    return bool(
        int(row["triggered"]) >= 30
        and float(row["trigger_rate"]) >= 0.25
        and float(row["one_r_first"]) > float(row["invalidation_first"])
        and row.get("median_entry_to_level_atr") is not None
        and float(row["median_entry_to_level_atr"]) <= max_entry_atr
    )


def _report(start: str, end: str, instruments: Sequence[str], events: Sequence[TrueBreakoutEvent], breakout: Mapping[str, object], models: Mapping[str, Mapping[str, object]], paired: Sequence[Mapping[str, object]], decision: str) -> str:
    overall = dict(breakout["overall"])
    lines = [
        "# TC BP Entry Model Quick Compare",
        "",
        "## 实验范围",
        "",
        f"- Development window: `{start}` 至 `{end}`。",
        f"- {' / '.join(instruments)}；4H structure + 15m entry diagnostic。",
        "- Raw OHLCV only；holdout 未读取；RiskEngine、正式 execution/config、exit/sizing/cost 均未修改。",
        "- 同一 physical breakout/direction 只保留 breakout close 距 level edge 最近的 causal confirmed level；两个 entry model 共用同一事件池。",
        "",
        "## 公共 True Breakout",
        "",
        f"- true_breakout_event_count: {len(events)}",
        f"- acceptance-reference 4H / 12H / 24H median signed return: {_fmt(overall.get('median_4h'))} / {_fmt(overall.get('median_12h'))} / {_fmt(overall.get('median_24h'))}",
        "",
        "| group | events | median_4H | median_12H | median_24H |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in dict(breakout["groups"]).items():
        lines.append(f"| {name} | {row['count']} | {_fmt(row['median_4h'])} | {_fmt(row['median_12h'])} | {_fmt(row['median_24h'])} |")
    lines.extend(["", "## 左侧 vs 右侧", "", "| model | events | triggered | trigger_rate | +1R_first | +1.5R_first | +2R_first | invalidation_first | median_entry_to_level_ATR | median_4H | median_12H | main_failure |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"])
    for model in MODELS:
        row = models[model]
        lines.append(f"| {model} | {row['events']} | {row['triggered']} | {row['trigger_rate']:.2%} | {row['one_r_first']:.2%} | {row['one_point_five_r_first']:.2%} | {row['two_r_first']:.2%} | {row['invalidation_first']:.2%} | {_num(row['median_entry_to_level_atr'])} | {_fmt(row['median_4h'])} | {_fmt(row['median_12h'])} | {row['main_failure']} |")
    lines.extend(["", "## Paired Subset", "", "| left_model | paired_count | left_better_price_rate | left_avg_entry_improvement_ATR | left/right +1R_first | left/right invalidation_first |", "|---|---:|---:|---:|---:|---:|"])
    for row in paired:
        lines.append(f"| {row['left_model']} | {row['paired_count']} | {row['left_better_price_rate']:.2%} | {_num(row['left_avg_entry_improvement_atr'])} | {row['left_one_r_first']:.2%} / {row['right_one_r_first']:.2%} | {row['left_invalidation_first']:.2%} / {row['right_invalidation_first']:.2%} |")
    lines.extend(["", "## Decision", "", f"`{decision}`", "", "本报告仅为 entry diagnostic；future return/path-order 未进入任何 feature 或触发条件。", ""])
    return "\n".join(lines)


def _rate(pairs: Sequence[tuple[EntryDiagnostic, EntryDiagnostic]], index: int, path: str) -> float:
    valid = [pair[index] for pair in pairs if _path_rate_eligible(pair[index])]
    return sum(row.path_order == path for row in valid) / len(valid) if valid else 0.0


def _path_rate_eligible(row: EntryDiagnostic) -> bool:
    return bool(
        row.path_order != "ambiguous_intrabar_path"
        and (row.path_order != "no_decision" or row.path_window_complete)
    )


def _median(values) -> float | None:
    resolved = [float(value) for value in values if value is not None]
    return median(resolved) if resolved else None


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _bool_rate(rows: Sequence[object], predicate) -> float:
    return sum(bool(predicate(row)) for row in rows) / len(rows) if rows else 0.0


def _fmt(value: object) -> str:
    return "n/a" if value is None else f"{float(value):+.4f}%"


def _num(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.4f}"


def _minutes(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.0f} min"


def _date_bounds(start: str, end: str) -> tuple[int, int]:
    left = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    right = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return int(left.timestamp() * 1000), int(right.timestamp() * 1000) - 1
