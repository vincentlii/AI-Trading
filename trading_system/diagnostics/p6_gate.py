from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from trading_system.backtest.batch import BacktestBatchReport, BacktestBatchRunner
from trading_system.backtest.scanner import BacktestScanConfig
from trading_system.config.loader import BacktestPresetConfig
from trading_system.data.coverage import CoverageThresholds, build_profile_coverage_rows
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.strategies.base import Strategy
from trading_system.timeframe_profiles import get_profile


@dataclass(frozen=True)
class P6GateConfig:
    coverage_thresholds: CoverageThresholds | None = None
    require_formal_backtest: bool = True
    max_audit_windows: int = 200


@dataclass(frozen=True)
class P6GateRow:
    category: str
    status: str
    reason_code: str
    details: Mapping[str, object]


@dataclass(frozen=True)
class P6GateReport:
    rows: tuple[P6GateRow, ...]
    summary: Mapping[str, object]
    position_aware_report: BacktestBatchReport
    failure_attribution_rows: tuple[dict[str, object], ...]

    @property
    def passed(self) -> bool:
        return all(row.status == "pass" for row in self.rows)


def build_p6_gate_report(
    *,
    repository,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    config: P6GateConfig | None = None,
) -> P6GateReport:
    active_config = config or P6GateConfig()
    coverage_rows = _coverage_gate_rows(repository, preset, active_config)
    audit_rows = _no_lookahead_gate_rows(repository, preset, active_config)
    position_aware_report = _run_position_aware_report(repository, preset, strategy)
    position_rows = _position_aware_gate_rows(position_aware_report)
    cost_rows = _cost_after_r_gate_rows(position_aware_report)
    failure_rows = build_failure_attribution_rows(position_aware_report.scan_result)
    failure_gate_rows = _failure_attribution_gate_rows(position_aware_report, failure_rows)
    rows = (*coverage_rows, *audit_rows, *position_rows, *cost_rows, *failure_gate_rows)
    return P6GateReport(
        rows=rows,
        summary=_summary(rows, position_aware_report, failure_rows),
        position_aware_report=position_aware_report,
        failure_attribution_rows=failure_rows,
    )


def build_failure_attribution_rows(scan_result) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for run in scan_result.profile_runs:
        for fill in run.result.fills:
            attribution = _classify_failure(fill)
            if attribution == "passed_trade":
                continue
            rows.append(
                {
                    "symbol": run.target.canonical_symbol,
                    "venue": run.target.venue,
                    "profile": run.profile_key,
                    "entry_timestamp_ms": fill.entry_timestamp_ms,
                    "exit_timestamp_ms": fill.exit_timestamp_ms,
                    "exit_reason": fill.exit_reason,
                    "net_pnl": fill.net_pnl,
                    "gross_pnl": fill.gross_pnl,
                    "cost": fill.cost_estimate.total,
                    "r_multiple": fill.r_multiple,
                    "attribution": attribution,
                }
            )
    return tuple(rows)


def _coverage_gate_rows(repository, preset: BacktestPresetConfig, config: P6GateConfig) -> tuple[P6GateRow, ...]:
    targets = tuple(
        (target.canonical_symbol, target.inst_id, target.venue, target.inst_type)
        for target in preset.assets.targets
    )
    rows = build_profile_coverage_rows(
        repository,
        targets=targets,
        profile_keys=preset.scan.profile_keys,
        thresholds=config.coverage_thresholds,
    )
    gate_rows = []
    for row in rows:
        ready = bool(row["can_run"]) and (not config.require_formal_backtest or bool(row["formal_backtest_ready"]))
        gate_rows.append(
            P6GateRow(
                category="data_coverage",
                status="pass" if ready else "fail",
                reason_code="ready" if ready else str(row["next_action"]),
                details=row,
            )
        )
    return tuple(gate_rows)


def _no_lookahead_gate_rows(repository, preset: BacktestPresetConfig, config: P6GateConfig) -> tuple[P6GateRow, ...]:
    rows: list[P6GateRow] = []
    for target in preset.assets.targets:
        for profile_key in preset.scan.profile_keys:
            profile = get_profile(profile_key)
            candles_by_timeframe = {
                profile.entry_timeframe: _load_raw_timeframe(repository, target, profile.entry_timeframe, preset),
                profile.structure_timeframe: _load_raw_timeframe(repository, target, profile.structure_timeframe, preset),
                profile.trend_timeframe: _load_raw_timeframe(repository, target, profile.trend_timeframe, preset),
            }
            confirmed = {
                timeframe: tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))
                for timeframe, candles in candles_by_timeframe.items()
            }
            unconfirmed_count = sum(
                1
                for candles in candles_by_timeframe.values()
                for candle in candles
                if not bool(getattr(candle, "is_confirmed", False))
            )
            violation_count = _count_no_lookahead_violations(
                confirmed[profile.entry_timeframe],
                confirmed[profile.structure_timeframe],
                confirmed[profile.trend_timeframe],
                max_windows=config.max_audit_windows,
            )
            status = "pass" if unconfirmed_count == 0 and violation_count == 0 else "fail"
            rows.append(
                P6GateRow(
                    category="no_lookahead",
                    status=status,
                    reason_code="ready" if status == "pass" else "lookahead_or_unconfirmed_candle",
                    details={
                        "symbol": target.canonical_symbol,
                        "profile": profile.key,
                        "unconfirmed_count": unconfirmed_count,
                        "violation_count": violation_count,
                    },
                )
            )
    return tuple(rows)


def _run_position_aware_report(repository, preset: BacktestPresetConfig, strategy: Strategy) -> BacktestBatchReport:
    scan_config = replace(preset.to_scan_config(), position_aware=True)
    return BacktestBatchRunner(
        repository=repository,
        preset=preset,
        strategy=strategy,
        scan_config=scan_config,
    ).run()


def _position_aware_gate_rows(report: BacktestBatchReport) -> tuple[P6GateRow, ...]:
    rows = []
    for run in report.scan_result.profile_runs:
        completed = run.status == "completed"
        rows.append(
            P6GateRow(
                category="position_aware",
                status="pass" if completed else "fail",
                reason_code="ready" if completed else ",".join(run.reason_codes),
                details={
                    "symbol": run.target.canonical_symbol,
                    "profile": run.profile_key,
                    "signal_count": run.signal_count,
                    "trade_count": run.result.summary.trade_count,
                    "suppressed_overlap_count": run.suppressed_overlap_count,
                },
            )
        )
    return tuple(rows)


def _cost_after_r_gate_rows(report: BacktestBatchReport) -> tuple[P6GateRow, ...]:
    fills = tuple(fill for run in report.scan_result.profile_runs for fill in run.result.fills)
    if not fills:
        return (
            P6GateRow(
                category="cost_after_r",
                status="fail",
                reason_code="no_closed_trades",
                details={"trade_count": 0},
            ),
        )
    invalid = [
        fill
        for fill in fills
        if not math.isfinite(float(fill.r_multiple)) or fill.cost_estimate.total < 0
    ]
    return (
        P6GateRow(
            category="cost_after_r",
            status="pass" if not invalid else "fail",
            reason_code="ready" if not invalid else "invalid_cost_after_r",
            details={
                "trade_count": len(fills),
                "invalid_count": len(invalid),
                "median_r_multiple": _median(tuple(float(fill.r_multiple) for fill in fills)),
                "total_cost": sum(float(fill.cost_estimate.total) for fill in fills),
            },
        ),
    )


def _failure_attribution_gate_rows(
    report: BacktestBatchReport,
    failure_rows: tuple[dict[str, object], ...],
) -> tuple[P6GateRow, ...]:
    trade_count = sum(run.result.summary.trade_count for run in report.scan_result.profile_runs)
    return (
        P6GateRow(
            category="failure_attribution",
            status="pass" if trade_count > 0 else "fail",
            reason_code="ready" if trade_count > 0 else "no_closed_trades",
            details={
                "trade_count": trade_count,
                "failure_case_count": len(failure_rows),
            },
        ),
    )


def _classify_failure(fill) -> str:
    if fill.net_pnl < 0:
        return "losing_trade"
    if fill.exit_reason == "time_exit":
        return "time_exit"
    gross_abs = abs(float(fill.gross_pnl))
    if gross_abs > 0 and float(fill.cost_estimate.total) / gross_abs >= 0.2:
        return "cost_drag"
    if fill.r_multiple < 0.25:
        return "low_net_r"
    return "passed_trade"


def _load_raw_timeframe(repository, target, timeframe: str, preset: BacktestPresetConfig) -> tuple[object, ...]:
    bar = timeframe_to_okx_bar(timeframe)
    start_ms = 0 if preset.scan.start_ms is None else preset.scan.start_ms
    end_ms = 9_223_372_036_854_775_807 if preset.scan.end_ms is None else preset.scan.end_ms
    if hasattr(repository, "load_range"):
        return tuple(
            repository.load_range(
                target.inst_id,
                bar,
                start_ms,
                end_ms,
                venue=target.venue,
                inst_type=target.inst_type,
                confirmed_only=False,
            )
        )
    try:
        candles = repository.list_candles(target.inst_id, bar, venue=target.venue, inst_type=target.inst_type)
    except TypeError:
        candles = repository.list_candles(target.inst_id, bar)
    return tuple(
        candle
        for candle in candles
        if start_ms <= int(getattr(candle, "timestamp_ms")) <= end_ms
    )


def _count_no_lookahead_violations(
    entry_candles: Sequence[object],
    structure_candles: Sequence[object],
    trend_candles: Sequence[object],
    *,
    max_windows: int,
) -> int:
    if not entry_candles or not structure_candles or not trend_candles:
        return 1
    violations = 0
    start_index = max(0, len(entry_candles) - max_windows - 1)
    for index in range(start_index, max(0, len(entry_candles) - 1)):
        signal_ts = int(getattr(entry_candles[index], "timestamp_ms"))
        execution_ts = int(getattr(entry_candles[index + 1], "timestamp_ms"))
        structure_context = _candles_until(structure_candles, signal_ts)
        trend_context = _candles_until(trend_candles, signal_ts)
        if not structure_context or not trend_context:
            violations += 1
            continue
        if max(int(getattr(candle, "timestamp_ms")) for candle in structure_context) > signal_ts:
            violations += 1
        if max(int(getattr(candle, "timestamp_ms")) for candle in trend_context) > signal_ts:
            violations += 1
        if execution_ts <= signal_ts:
            violations += 1
    return violations


def _candles_until(candles: Sequence[object], timestamp_ms: int) -> tuple[object, ...]:
    return tuple(candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms)


def _summary(
    rows: tuple[P6GateRow, ...],
    report: BacktestBatchReport,
    failure_rows: tuple[dict[str, object], ...],
) -> dict[str, object]:
    return {
        "passed": all(row.status == "pass" for row in rows),
        "gate_count": len(rows),
        "failed_gate_count": sum(1 for row in rows if row.status != "pass"),
        "trade_count": sum(run.result.summary.trade_count for run in report.scan_result.profile_runs),
        "suppressed_overlap_count": sum(run.suppressed_overlap_count for run in report.scan_result.profile_runs),
        "failure_case_count": len(failure_rows),
    }


def _median(values: Sequence[float]) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2.0


__all__ = (
    "P6GateConfig",
    "P6GateReport",
    "P6GateRow",
    "build_failure_attribution_rows",
    "build_p6_gate_report",
)
