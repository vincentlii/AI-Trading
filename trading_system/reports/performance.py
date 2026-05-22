from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from trading_system.backtest.scanner import BacktestScanResult


@dataclass(frozen=True)
class PerformanceReportSnapshot:
    summary: dict[str, object]
    library_rows: tuple[dict[str, object], ...]
    metric_rows: tuple[dict[str, object], ...]
    drawdown_rows: tuple[dict[str, object], ...]
    artifact_rows: tuple[dict[str, object], ...]


def build_performance_report(
    scan_result: BacktestScanResult,
    *,
    artifact_dir: str | Path | None = None,
) -> PerformanceReportSnapshot:
    library_rows = _library_rows()
    metric_rows = _metric_rows(scan_result)
    drawdown_rows = _drawdown_rows(scan_result)
    artifact_rows = _artifact_rows(scan_result, artifact_dir, library_rows)
    return PerformanceReportSnapshot(
        summary={
            "performance_runs": len(metric_rows),
            "performance_artifacts": sum(1 for row in artifact_rows if row["status"] == "generated"),
            "performance_adapter": "optional_third_party_boundary",
        },
        library_rows=library_rows,
        metric_rows=metric_rows,
        drawdown_rows=drawdown_rows,
        artifact_rows=artifact_rows,
    )


def _library_rows() -> tuple[dict[str, object], ...]:
    return (
        _library_row(
            "quantstats",
            "tear_sheet_html",
            "reporting_p5_display",
        ),
        _library_row(
            "empyrical",
            "performance_metric_cross_check",
            "reporting_validation",
        ),
    )


def _library_row(name: str, purpose: str, allowed_layer: str) -> dict[str, object]:
    available = importlib.util.find_spec(name) is not None
    return {
        "library": name,
        "status": "available" if available else "missing",
        "purpose": purpose,
        "allowed_layer": allowed_layer,
        "boundary": "adapter_only",
    }


def _metric_rows(scan_result: BacktestScanResult) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for run in scan_result.profile_runs:
        summary = run.result.summary
        returns = _returns_from_equity_curve(run.result.equity_curve)
        rows.append(
            {
                "symbol": run.target.canonical_symbol,
                "venue": run.target.venue,
                "timeframe_group": run.profile_key,
                "status": run.status,
                "primary_metric_source": "project_backtest_summary",
                "trade_count": summary.trade_count,
                "net_profit": summary.net_profit,
                "max_drawdown": summary.max_drawdown,
                "win_rate": summary.win_rate,
                "profit_factor": summary.profit_factor,
                "expectancy_per_trade": summary.expectancy_per_trade,
                "event_sharpe": _event_sharpe(returns),
                "return_count": len(returns),
            }
        )
    return tuple(rows)


def _drawdown_rows(scan_result: BacktestScanResult) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for run in scan_result.profile_runs:
        points = tuple(run.result.equity_curve)
        rows.append(
            {
                "symbol": run.target.canonical_symbol,
                "venue": run.target.venue,
                "timeframe_group": run.profile_key,
                "status": run.status,
                "point_count": len(points),
                "start_equity": points[0].equity if points else 0.0,
                "end_equity": points[-1].equity if points else 0.0,
                "max_drawdown": max((point.drawdown_pct for point in points), default=0.0),
            }
        )
    return tuple(rows)


def _artifact_rows(
    scan_result: BacktestScanResult,
    artifact_dir: str | Path | None,
    library_rows: Sequence[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    quantstats_status = next(row["status"] for row in library_rows if row["library"] == "quantstats")
    if artifact_dir is None:
        return (
            {
                "library": "quantstats",
                "status": "not_generated",
                "path": "",
                "reason": "artifact_dir_not_configured",
            },
        )
    if quantstats_status != "available":
        return (
            {
                "library": "quantstats",
                "status": "not_generated",
                "path": "",
                "reason": "optional_quantstats_missing",
            },
        )

    rows: list[dict[str, object]] = []
    for run in scan_result.profile_runs:
        returns = _returns_from_equity_curve(run.result.equity_curve)
        if not returns:
            rows.append(
                {
                    "library": "quantstats",
                    "status": "not_generated",
                    "path": "",
                    "reason": "empty_returns",
                }
            )
            continue
        rows.append(_try_generate_quantstats_report(run, returns, Path(artifact_dir)))
    return tuple(rows)


def _try_generate_quantstats_report(run, returns: Sequence[float], artifact_dir: Path) -> dict[str, object]:
    try:
        import pandas as pd
        import quantstats as qs

        artifact_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{run.target.canonical_symbol.replace('/', '_')}_{run.profile_key}_quantstats.html"
        output_path = artifact_dir / filename
        qs.reports.html(pd.Series(tuple(returns)), output=str(output_path), title=filename)
        return {
            "library": "quantstats",
            "status": "generated",
            "path": str(output_path),
            "reason": "",
        }
    except Exception as error:
        return {
            "library": "quantstats",
            "status": "not_generated",
            "path": "",
            "reason": f"quantstats_generation_failed:{error}",
        }


def _returns_from_equity_curve(equity_curve: Sequence[object]) -> tuple[float, ...]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        previous_equity = float(previous.equity)
        current_equity = float(current.equity)
        if previous_equity <= 0.0:
            returns.append(0.0)
        else:
            returns.append((current_equity / previous_equity) - 1.0)
    return tuple(returns)


def _event_sharpe(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    average = sum(returns) / len(returns)
    variance = sum((value - average) ** 2 for value in returns) / (len(returns) - 1)
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0.0:
        return 0.0
    return average / standard_deviation


__all__ = (
    "PerformanceReportSnapshot",
    "build_performance_report",
)
