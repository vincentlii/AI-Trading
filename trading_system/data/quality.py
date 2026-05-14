from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataQualityIssue:
    code: str
    severity: str
    message: str
    timestamp_ms: int | None = None


@dataclass(frozen=True)
class DataQualityReport:
    venue: str
    inst_type: str
    inst_id: str
    bar: str
    row_count: int
    earliest_ts_ms: int | None
    latest_ts_ms: int | None
    expected_interval_ms: int
    issues: tuple[DataQualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def status(self) -> str:
        if self.passed:
            return "pass"
        return "fail"


def check_repository_symbol_bar(
    repository,
    inst_id: str,
    bar: str,
    *,
    venue: str = "okx",
    inst_type: str = "SPOT",
) -> DataQualityReport:
    candles = _list_candles(repository, inst_id, bar, venue=venue, inst_type=inst_type)
    interval_ms = bar_duration_ms(bar)
    issues: list[DataQualityIssue] = []

    if not candles:
        return DataQualityReport(
            venue=venue,
            inst_type=inst_type,
            inst_id=inst_id,
            bar=bar,
            row_count=0,
            earliest_ts_ms=None,
            latest_ts_ms=None,
            expected_interval_ms=interval_ms,
            issues=(
                DataQualityIssue(
                    code="empty_data",
                    severity="error",
                    message=f"No candles found for {venue}:{inst_type}:{inst_id}:{bar}.",
                ),
            ),
        )

    timestamps = [candle.timestamp_ms for candle in candles]
    sorted_timestamps = sorted(timestamps)
    if timestamps != sorted_timestamps:
        issues.append(
            DataQualityIssue(
                code="time_order",
                severity="error",
                message="Candles are not returned in ascending timestamp order.",
            )
        )

    seen: set[int] = set()
    duplicates: set[int] = set()
    for timestamp in timestamps:
        if timestamp in seen:
            duplicates.add(timestamp)
        seen.add(timestamp)
    for timestamp in sorted(duplicates):
        issues.append(
            DataQualityIssue(
                code="duplicate_timestamp",
                severity="error",
                message=f"Duplicate candle timestamp: {timestamp}.",
                timestamp_ms=timestamp,
            )
        )

    candles_by_timestamp = {candle.timestamp_ms: candle for candle in candles}
    unique_sorted_timestamps = sorted(candles_by_timestamp)
    for previous, current in zip(unique_sorted_timestamps, unique_sorted_timestamps[1:]):
        delta = current - previous
        if delta != interval_ms:
            issues.append(
                DataQualityIssue(
                    code="missing_interval",
                    severity="error",
                    message=f"Expected interval {interval_ms} ms, found {delta} ms.",
                    timestamp_ms=current,
                )
            )

    for candle in candles:
        issues.extend(_validate_candle(candle))

    return DataQualityReport(
        venue=venue,
        inst_type=inst_type,
        inst_id=inst_id,
        bar=bar,
        row_count=len(candles),
        earliest_ts_ms=min(timestamps),
        latest_ts_ms=max(timestamps),
        expected_interval_ms=interval_ms,
        issues=tuple(issues),
    )


def bar_duration_ms(bar: str) -> int:
    normalized = bar.strip()
    if normalized.endswith("m"):
        return int(normalized[:-1]) * 60_000
    if normalized.endswith("H"):
        return int(normalized[:-1]) * 60 * 60_000
    if normalized.endswith("D"):
        return int(normalized[:-1]) * 24 * 60 * 60_000
    raise ValueError(f"Unsupported bar: {bar}")


def _list_candles(repository, inst_id: str, bar: str, *, venue: str, inst_type: str):
    try:
        return repository.list_candles(inst_id, bar, venue=venue, inst_type=inst_type)
    except TypeError:
        return repository.list_candles(inst_id, bar)


def _validate_candle(candle) -> tuple[DataQualityIssue, ...]:
    issues: list[DataQualityIssue] = []

    if not candle.is_confirmed:
        issues.append(
            DataQualityIssue(
                code="unconfirmed_candle",
                severity="error",
                message="Unconfirmed candle found in history set.",
                timestamp_ms=candle.timestamp_ms,
            )
        )

    if candle.high < candle.low or not (candle.low <= candle.open <= candle.high) or not (candle.low <= candle.close <= candle.high):
        issues.append(
            DataQualityIssue(
                code="invalid_ohlc",
                severity="error",
                message="OHLC values are inconsistent.",
                timestamp_ms=candle.timestamp_ms,
            )
        )

    if candle.volume < 0 or candle.volume_currency < 0 or candle.volume_currency_quote < 0:
        issues.append(
            DataQualityIssue(
                code="negative_volume",
                severity="error",
                message="Negative volume value found.",
                timestamp_ms=candle.timestamp_ms,
            )
        )

    return tuple(issues)
