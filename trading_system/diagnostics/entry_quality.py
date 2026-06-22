from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from statistics import mean, median
from typing import Mapping, Sequence

from trading_system.data.okx_cli import Candle


HOUR_MS = 60 * 60 * 1000
FIXED_HORIZONS_HOURS = (1, 4, 12, 24, 48, 72, 96)


@dataclass(frozen=True)
class EntryRecord:
    strategy_id: str
    setup_type: str | None
    instrument: str
    direction: str
    signal_time_ms: int | None
    entry_time_ms: int
    entry_price: float
    stop_price: float | None
    level_price: float | None
    atr: float | None
    tags: tuple[str, ...]
    quality_score: float | None
    venue: str = "okx"
    inst_type: str = "SWAP"


@dataclass(frozen=True)
class EntryDiagnostic:
    record: EntryRecord
    fixed_returns_pct: Mapping[int, float | None]
    complete_window: bool
    mfe_pct: float | None
    mae_pct: float | None
    mfe_r: float | None
    mae_r: float | None
    time_to_mfe_minutes: int | None
    half_r_first: bool | None
    one_r_first: bool | None
    two_r_first: bool | None
    invalidation_first: bool | None
    no_decision: bool | None
    path_ambiguous: bool
    time_to_half_r_minutes: int | None
    time_to_one_r_minutes: int | None
    time_to_two_r_minutes: int | None
    time_to_invalidation_minutes: int | None
    entry_to_level_atr: float | None
    entry_to_level_pct: float | None
    stop_distance_atr: float | None
    stop_distance_pct: float | None
    entry_after_signal_delay_minutes: int | None


@dataclass(frozen=True)
class SummaryMetric:
    metric: str
    value: object
    note: str


@dataclass(frozen=True)
class ProblemDiagnosis:
    problem: str
    count: int
    eligible_count: int
    rate: float | None
    meaning: str
    suggested_action: str


def analyze_entry(
    record: EntryRecord,
    candles: Sequence[Candle],
    *,
    timeframe_ms: int,
    max_horizon_hours: int = 96,
) -> EntryDiagnostic:
    if timeframe_ms <= 0:
        raise ValueError("timeframe_ms must be positive")
    if not 1 <= max_horizon_hours <= 96:
        raise ValueError("max_horizon_hours must be between 1 and 96")

    confirmed = tuple(sorted((row for row in candles if row.is_confirmed), key=lambda row: row.timestamp_ms))
    first_open = _ceil_to_timeframe(record.entry_time_ms, timeframe_ms)
    timestamps = tuple(row.timestamp_ms for row in confirmed)
    start_index = bisect_left(timestamps, first_open)
    future = confirmed[start_index:]
    fixed_returns = {
        hours: _fixed_return(record, future, timeframe_ms=timeframe_ms, hours=hours)
        if hours <= max_horizon_hours
        else None
        for hours in FIXED_HORIZONS_HOURS
    }

    window = _complete_window(
        future,
        first_open=first_open,
        target_time=record.entry_time_ms + max_horizon_hours * HOUR_MS,
        timeframe_ms=timeframe_ms,
    )
    complete = window is not None
    mfe_pct = mae_pct = mfe_r = mae_r = None
    time_to_mfe = None
    half_first = one_first = two_first = invalidation_first = no_decision = None
    path_ambiguous = False
    time_half = time_one = time_two = time_stop = None
    stop = _valid_stop(record)
    risk = None if stop is None else abs(record.entry_price - stop)

    if window:
        favorable = tuple(_favorable_move(record, row) for row in window)
        adverse = tuple(_adverse_move(record, row) for row in window)
        max_favorable = max(0.0, max(favorable, default=0.0))
        max_adverse = max(0.0, max(adverse, default=0.0))
        mfe_pct = max_favorable / record.entry_price * 100.0
        mae_pct = max_adverse / record.entry_price * 100.0
        mfe_index = favorable.index(max(favorable)) if favorable else 0
        time_to_mfe = _minutes_after_entry(record, window[mfe_index], timeframe_ms)
        if risk is not None and risk > 0:
            mfe_r = max_favorable / risk
            mae_r = max_adverse / risk
            path = _path_order(record, window, stop=stop, risk=risk, timeframe_ms=timeframe_ms)
            half_first = path["half_first"]
            one_first = path["one_first"]
            two_first = path["two_first"]
            invalidation_first = path["invalidation_first"]
            no_decision = path["no_decision"]
            path_ambiguous = path["ambiguous"]
            time_half = path["time_half"]
            time_one = path["time_one"]
            time_two = path["time_two"]
            time_stop = path["time_stop"]

    entry_to_level_atr, entry_to_level_pct = _entry_to_level(record)
    stop_distance_atr = None if risk is None or not record.atr else risk / record.atr
    stop_distance_pct = None if risk is None else risk / record.entry_price * 100.0
    delay = None
    if record.signal_time_ms is not None and record.signal_time_ms <= record.entry_time_ms:
        delay = int((record.entry_time_ms - record.signal_time_ms) / 60_000)

    return EntryDiagnostic(
        record=record,
        fixed_returns_pct=fixed_returns,
        complete_window=complete,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        mfe_r=mfe_r,
        mae_r=mae_r,
        time_to_mfe_minutes=time_to_mfe,
        half_r_first=half_first,
        one_r_first=one_first,
        two_r_first=two_first,
        invalidation_first=invalidation_first,
        no_decision=no_decision,
        path_ambiguous=path_ambiguous,
        time_to_half_r_minutes=time_half,
        time_to_one_r_minutes=time_one,
        time_to_two_r_minutes=time_two,
        time_to_invalidation_minutes=time_stop,
        entry_to_level_atr=entry_to_level_atr,
        entry_to_level_pct=entry_to_level_pct,
        stop_distance_atr=stop_distance_atr,
        stop_distance_pct=stop_distance_pct,
        entry_after_signal_delay_minutes=delay,
    )


def build_summary_metrics(
    *,
    total_entries: int,
    diagnostics: Sequence[EntryDiagnostic],
    max_horizon_hours: int,
) -> tuple[SummaryMetric, ...]:
    valid = len(diagnostics)
    missing_stop = sum(_valid_stop(row.record) is None for row in diagnostics)
    missing_level = sum(row.record.level_price is None for row in diagnostics)
    metrics = [
        SummaryMetric("entries", total_entries, "input rows"),
        SummaryMetric("valid_entries", valid, f"{total_entries - valid} invalid rows excluded"),
        SummaryMetric("missing_stop_rate", _rate(missing_stop, valid), f"{missing_stop}/{valid} valid entries"),
        SummaryMetric("missing_level_rate", _rate(missing_level, valid), f"{missing_level}/{valid} valid entries"),
    ]
    for hours in FIXED_HORIZONS_HOURS:
        values = [row.fixed_returns_pct.get(hours) for row in diagnostics]
        eligible = _numbers(values)
        note = f"eligible={len(eligible)}/{valid}; directional diagnostic return"
        if hours > max_horizon_hours:
            note = f"disabled by max_horizon_hours={max_horizon_hours}"
        metrics.extend((
            SummaryMetric(f"median_return_{hours}H", _median(eligible), note),
            SummaryMetric(f"avg_return_{hours}H", _mean(eligible), note),
            SummaryMetric(f"win_rate_{hours}H", _rate(sum(value > 0 for value in eligible), len(eligible)), note),
        ))

    mfe_pct = _numbers(row.mfe_pct for row in diagnostics)
    mae_pct = _numbers(row.mae_pct for row in diagnostics)
    mfe_r = _numbers(row.mfe_r for row in diagnostics)
    mae_r = _numbers(row.mae_r for row in diagnostics)
    metrics.extend((
        SummaryMetric("avg_MFE_pct", _mean(mfe_pct), f"complete_window={len(mfe_pct)}/{valid}"),
        SummaryMetric("median_MFE_pct", _median(mfe_pct), f"complete_window={len(mfe_pct)}/{valid}"),
        SummaryMetric("avg_MAE_pct", _mean(mae_pct), f"complete_window={len(mae_pct)}/{valid}"),
        SummaryMetric("median_MAE_pct", _median(mae_pct), f"complete_window={len(mae_pct)}/{valid}"),
        SummaryMetric("MFE_MAE_ratio", _ratio(_mean(mfe_pct), _mean(mae_pct)), "avg_MFE_pct / avg_MAE_pct"),
        SummaryMetric("avg_MFE_R", _mean(mfe_r), f"eligible={len(mfe_r)}/{valid}"),
        SummaryMetric("median_MFE_R", _median(mfe_r), f"eligible={len(mfe_r)}/{valid}"),
        SummaryMetric("avg_MAE_R", _mean(mae_r), f"eligible={len(mae_r)}/{valid}"),
        SummaryMetric("median_MAE_R", _median(mae_r), f"eligible={len(mae_r)}/{valid}"),
    ))

    path_rows = [row for row in diagnostics if row.one_r_first is not None and not row.path_ambiguous]
    ambiguous = sum(row.path_ambiguous for row in diagnostics)
    path_note = f"eligible={len(path_rows)}/{valid}; ambiguous={ambiguous}; invalidation relative to +1R"
    metrics.extend((
        SummaryMetric("+0.5R_first", _bool_rate(path_rows, "half_r_first"), path_note),
        SummaryMetric("+1R_first", _bool_rate(path_rows, "one_r_first"), path_note),
        SummaryMetric("+2R_first", _bool_rate(path_rows, "two_r_first"), path_note),
        SummaryMetric("invalidation_first", _bool_rate(path_rows, "invalidation_first"), path_note),
        SummaryMetric("no_decision_rate", _bool_rate(path_rows, "no_decision"), path_note),
        SummaryMetric("median_time_to_MFE", _median(_numbers(row.time_to_mfe_minutes for row in diagnostics)), "minutes; earliest max favorable bar close"),
        SummaryMetric("median_time_to_0.5R", _median(_numbers(row.time_to_half_r_minutes for row in diagnostics)), "minutes; target before invalidation"),
        SummaryMetric("median_time_to_1R", _median(_numbers(row.time_to_one_r_minutes for row in diagnostics)), "minutes; target before invalidation"),
        SummaryMetric("median_time_to_2R", _median(_numbers(row.time_to_two_r_minutes for row in diagnostics)), "minutes; target before invalidation"),
        SummaryMetric("median_time_to_invalidation", _median(_numbers(row.time_to_invalidation_minutes for row in diagnostics)), "minutes; first stop touch"),
        SummaryMetric("median_entry_to_level_ATR", _median(_numbers(row.entry_to_level_atr for row in diagnostics)), "directional distance"),
        SummaryMetric("median_entry_to_level_pct", _median(_numbers(row.entry_to_level_pct for row in diagnostics)), "directional distance"),
        SummaryMetric("median_stop_distance_ATR", _median(_numbers(row.stop_distance_atr for row in diagnostics)), "absolute stop distance"),
        SummaryMetric("median_stop_distance_pct", _median(_numbers(row.stop_distance_pct for row in diagnostics)), "absolute stop distance"),
        SummaryMetric("entry_after_signal_delay_median", _median(_numbers(row.entry_after_signal_delay_minutes for row in diagnostics)), "minutes; signal_time <= entry_time only"),
    ))
    return tuple(metrics)


_PROBLEM_TEXT = {
    "low_MFE_entry": ("入场后有利波动不足。", "先复查上游信号质量，不要直接优化出场。"),
    "high_MAE_before_profit": ("不利波动大于有利波动。", "复查入场时机和 invalidation 几何。"),
    "fast_invalidation": ("四小时内先触及 invalidation，未先到 +1R。", "复查信号纯度和 stop 位置。"),
    "positive_MFE_but_giveback": ("曾达到至少 1R，但 24H 方向收益未保留。", "确认入场 edge 后再研究出场效率。"),
    "chase_entry": ("入场距离参考 level 至少 1 ATR。", "复查确认延迟和追价几何。"),
    "tiny_R_entry": ("stop 距离不超过入场价的 0.35%。", "检查 R 指标是否被过小分母放大。"),
    "large_R_entry": ("stop 距离至少为入场价的 2%。", "复查 stop 效率和资金占用，不放宽 RiskEngine。"),
    "slow_profit_entry": ("先到 +1R 需要至少 24 小时。", "复查入场是否过早或持有周期是否错配。"),
    "noise_entry": ("有利和不利波动都低于 0.4%。", "复查信号是否只捕捉到市场噪声。"),
}


def build_problem_diagnoses(diagnostics: Sequence[EntryDiagnostic]) -> tuple[ProblemDiagnosis, ...]:
    specs = (
        ("low_MFE_entry", lambda row: row.mfe_pct is not None, lambda row: row.mfe_pct < 0.5),
        ("high_MAE_before_profit", lambda row: row.mfe_pct is not None and row.mae_pct is not None, lambda row: row.mae_pct > row.mfe_pct and row.mae_pct > 0.7),
        ("fast_invalidation", lambda row: row.invalidation_first is not None, lambda row: row.invalidation_first and row.time_to_invalidation_minutes is not None and row.time_to_invalidation_minutes <= 240),
        ("positive_MFE_but_giveback", lambda row: row.mfe_r is not None and row.fixed_returns_pct.get(24) is not None, lambda row: row.mfe_r >= 1.0 and row.fixed_returns_pct[24] <= 0),
        ("chase_entry", lambda row: row.entry_to_level_atr is not None, lambda row: row.entry_to_level_atr >= 1.0),
        ("tiny_R_entry", lambda row: row.stop_distance_pct is not None, lambda row: row.stop_distance_pct <= 0.35),
        ("large_R_entry", lambda row: row.stop_distance_pct is not None, lambda row: row.stop_distance_pct >= 2.0),
        ("slow_profit_entry", lambda row: row.mfe_r is not None, lambda row: row.mfe_r >= 1.0 and row.time_to_one_r_minutes is not None and row.time_to_one_r_minutes >= 1_440),
        ("noise_entry", lambda row: row.mfe_pct is not None and row.mae_pct is not None, lambda row: row.mfe_pct < 0.4 and row.mae_pct < 0.4),
    )
    output = []
    for name, eligible_test, problem_test in specs:
        eligible = [row for row in diagnostics if eligible_test(row)]
        count = sum(bool(problem_test(row)) for row in eligible)
        meaning, action = _PROBLEM_TEXT[name]
        output.append(ProblemDiagnosis(name, count, len(eligible), _rate(count, len(eligible)), meaning, action))
    return tuple(output)


def _fixed_return(record: EntryRecord, rows: Sequence[Candle], *, timeframe_ms: int, hours: int) -> float | None:
    target = record.entry_time_ms + hours * HOUR_MS
    window = _complete_window(rows, first_open=_ceil_to_timeframe(record.entry_time_ms, timeframe_ms), target_time=target, timeframe_ms=timeframe_ms)
    if not window:
        return None
    sign = 1.0 if record.direction == "long" else -1.0
    return sign * (window[-1].close - record.entry_price) / record.entry_price * 100.0


def _complete_window(rows: Sequence[Candle], *, first_open: int, target_time: int, timeframe_ms: int) -> tuple[Candle, ...] | None:
    if not rows or rows[0].timestamp_ms != first_open:
        return None
    required_index = next((index for index, row in enumerate(rows) if row.timestamp_ms + timeframe_ms >= target_time), None)
    if required_index is None:
        return None
    window = tuple(rows[: required_index + 1])
    if any(right.timestamp_ms - left.timestamp_ms != timeframe_ms for left, right in zip(window, window[1:])):
        return None
    return window


def _path_order(record: EntryRecord, rows: Sequence[Candle], *, stop: float, risk: float, timeframe_ms: int) -> dict[str, object]:
    targets = {multiple: record.entry_price + (risk * multiple if record.direction == "long" else -risk * multiple) for multiple in (0.5, 1.0, 2.0)}
    target_times: dict[float, int | None] = {multiple: None for multiple in targets}
    stop_time = None
    ambiguous_one = False
    for row in rows:
        available_time = row.timestamp_ms + timeframe_ms
        stop_hit = row.low <= stop if record.direction == "long" else row.high >= stop
        hits = {multiple: row.high >= target if record.direction == "long" else row.low <= target for multiple, target in targets.items()}
        if stop_hit and hits[1.0] and stop_time is None and target_times[1.0] is None:
            ambiguous_one = True
        if stop_hit and stop_time is None:
            stop_time = available_time
        for multiple, hit in hits.items():
            if hit and target_times[multiple] is None:
                target_times[multiple] = available_time

    def target_first(multiple: float) -> bool:
        target_time = target_times[multiple]
        return target_time is not None and (stop_time is None or target_time < stop_time)

    def target_minutes(multiple: float) -> int | None:
        return _minutes_between(record.entry_time_ms, target_times[multiple]) if target_first(multiple) else None

    one_time = target_times[1.0]
    return {
        "half_first": target_first(0.5),
        "one_first": target_first(1.0) and not ambiguous_one,
        "two_first": target_first(2.0),
        "invalidation_first": stop_time is not None and (one_time is None or stop_time < one_time) and not ambiguous_one,
        "no_decision": stop_time is None and one_time is None,
        "ambiguous": ambiguous_one,
        "time_half": target_minutes(0.5),
        "time_one": target_minutes(1.0) if not ambiguous_one else None,
        "time_two": target_minutes(2.0),
        "time_stop": _minutes_between(record.entry_time_ms, stop_time),
    }


def _valid_stop(record: EntryRecord) -> float | None:
    stop = record.stop_price
    if stop is None or stop <= 0:
        return None
    if record.direction == "long" and stop >= record.entry_price:
        return None
    if record.direction == "short" and stop <= record.entry_price:
        return None
    return stop


def _entry_to_level(record: EntryRecord) -> tuple[float | None, float | None]:
    if record.level_price is None or record.level_price <= 0:
        return None, None
    distance = record.entry_price - record.level_price if record.direction == "long" else record.level_price - record.entry_price
    return (None if not record.atr else distance / record.atr, distance / record.entry_price * 100.0)


def _favorable_move(record: EntryRecord, row: Candle) -> float:
    return row.high - record.entry_price if record.direction == "long" else record.entry_price - row.low


def _adverse_move(record: EntryRecord, row: Candle) -> float:
    return record.entry_price - row.low if record.direction == "long" else row.high - record.entry_price


def _minutes_after_entry(record: EntryRecord, row: Candle, timeframe_ms: int) -> int:
    return int((row.timestamp_ms + timeframe_ms - record.entry_time_ms) / 60_000)


def _minutes_between(start: int, end: int | None) -> int | None:
    return None if end is None else int((end - start) / 60_000)


def _ceil_to_timeframe(timestamp_ms: int, timeframe_ms: int) -> int:
    return ((timestamp_ms + timeframe_ms - 1) // timeframe_ms) * timeframe_ms


def _numbers(values) -> list[float]:
    return [float(value) for value in values if value is not None]


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else float(mean(values))


def _median(values: Sequence[float]) -> float | None:
    return None if not values else float(median(values))


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else numerator / denominator


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    return None if numerator is None or denominator is None or denominator <= 0 else numerator / denominator


def _bool_rate(rows: Sequence[EntryDiagnostic], field: str) -> float | None:
    return _rate(sum(bool(getattr(row, field)) for row in rows), len(rows))


__all__ = (
    "EntryDiagnostic",
    "EntryRecord",
    "FIXED_HORIZONS_HOURS",
    "ProblemDiagnosis",
    "SummaryMetric",
    "analyze_entry",
    "build_problem_diagnoses",
    "build_summary_metrics",
)
