from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from trading_system.data.quality import bar_duration_ms, check_repository_symbol_bar
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.timeframe_profiles import get_profile


REGIME_MINIMUM_CANDLES = 201


@dataclass(frozen=True)
class CoverageThresholds:
    runnable: int = 300
    diagnostic: int = 1000
    formal_years: int = 1


TargetTuple = tuple[str, str, str, str]


def build_bar_coverage_rows(
    repository,
    *,
    targets: Iterable[TargetTuple],
    bars: Sequence[str],
    thresholds: CoverageThresholds | None = None,
) -> tuple[dict[str, object], ...]:
    active_thresholds = thresholds or CoverageThresholds()
    rows: list[dict[str, object]] = []
    for canonical_symbol, inst_id, venue, inst_type in targets:
        for bar in bars:
            quality = check_repository_symbol_bar(
                repository,
                inst_id,
                bar,
                venue=venue,
                inst_type=inst_type,
            )
            formal_target = _formal_target_candles(bar, active_thresholds.formal_years)
            rows.append(
                {
                    "symbol": canonical_symbol,
                    "venue": venue,
                    "inst_type": inst_type,
                    "inst_id": inst_id,
                    "bar": bar,
                    "row_count": quality.row_count,
                    "earliest_ts_ms": quality.earliest_ts_ms,
                    "latest_ts_ms": quality.latest_ts_ms,
                    "meets_regime_minimum": quality.row_count >= REGIME_MINIMUM_CANDLES,
                    "meets_minimum_runnable": quality.row_count >= active_thresholds.runnable,
                    "meets_initial_diagnostic": quality.row_count >= active_thresholds.diagnostic,
                    "formal_target_candles": formal_target,
                    "meets_formal_backtest": quality.row_count >= formal_target,
                    "quality_pass": quality.passed,
                    "quality_issue_count": len(quality.issues),
                    "quality_issue_codes": tuple(issue.code for issue in quality.issues),
                    "next_action": _next_bar_action(quality.row_count, formal_target, quality.passed, active_thresholds),
                }
            )
    return tuple(rows)


def build_profile_coverage_rows(
    repository,
    *,
    targets: Iterable[TargetTuple],
    profile_keys: Sequence[str],
    thresholds: CoverageThresholds | None = None,
) -> tuple[dict[str, object], ...]:
    active_thresholds = thresholds or CoverageThresholds()
    rows: list[dict[str, object]] = []
    for canonical_symbol, inst_id, venue, inst_type in targets:
        for profile_key in profile_keys:
            profile = get_profile(profile_key)
            timeframe_counts: dict[str, int] = {}
            blocking: list[str] = []
            quality_failures: list[str] = []
            diagnostic_ready = True
            formal_ready = True
            for timeframe in profile.timeframes:
                bar = timeframe_to_okx_bar(timeframe)
                quality = check_repository_symbol_bar(
                    repository,
                    inst_id,
                    bar,
                    venue=venue,
                    inst_type=inst_type,
                )
                timeframe_counts[timeframe] = quality.row_count
                if quality.row_count < active_thresholds.runnable:
                    blocking.append(timeframe)
                if quality.row_count < active_thresholds.diagnostic:
                    diagnostic_ready = False
                if quality.row_count < _formal_target_candles(bar, active_thresholds.formal_years):
                    formal_ready = False
                if not quality.passed:
                    quality_failures.append(timeframe)

            rows.append(
                {
                    "symbol": canonical_symbol,
                    "venue": venue,
                    "inst_type": inst_type,
                    "inst_id": inst_id,
                    "profile": profile.key,
                    "entry_timeframe": profile.entry_timeframe,
                    "structure_timeframe": profile.structure_timeframe,
                    "trend_timeframe": profile.trend_timeframe,
                    "timeframe_counts": dict(timeframe_counts),
                    "minimum_row_count": min(timeframe_counts.values()) if timeframe_counts else 0,
                    "can_compute_regime": timeframe_counts.get(profile.trend_timeframe, 0) >= REGIME_MINIMUM_CANDLES,
                    "can_run": not blocking and not quality_failures,
                    "diagnostic_ready": diagnostic_ready and not quality_failures,
                    "formal_backtest_ready": formal_ready and not quality_failures,
                    "blocking_timeframes": tuple(blocking),
                    "quality_failure_timeframes": tuple(quality_failures),
                    "next_action": _next_profile_action(blocking, quality_failures, diagnostic_ready, formal_ready),
                }
            )
    return tuple(rows)


def _formal_target_candles(bar: str, years: int) -> int:
    year_ms = 365 * 24 * 60 * 60_000
    return int(math.ceil((year_ms * max(years, 1)) / bar_duration_ms(bar)))


def _next_bar_action(row_count: int, formal_target: int, quality_pass: bool, thresholds: CoverageThresholds) -> str:
    if not quality_pass:
        return "fix_data_quality"
    if row_count < REGIME_MINIMUM_CANDLES:
        return "backfill_regime_minimum"
    if row_count < thresholds.runnable:
        return "backfill_minimum_runnable"
    if row_count < thresholds.diagnostic:
        return "backfill_initial_diagnostic"
    if row_count < formal_target:
        return "backfill_formal_backtest"
    return "ready"


def _next_profile_action(
    blocking: Sequence[str],
    quality_failures: Sequence[str],
    diagnostic_ready: bool,
    formal_ready: bool,
) -> str:
    if quality_failures:
        return "fix_profile_data_quality"
    if blocking:
        return "backfill_profile_minimum"
    if not diagnostic_ready:
        return "backfill_profile_diagnostic"
    if not formal_ready:
        return "backfill_profile_formal"
    return "ready"


__all__ = (
    "CoverageThresholds",
    "REGIME_MINIMUM_CANDLES",
    "build_bar_coverage_rows",
    "build_profile_coverage_rows",
)
