from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.data.history import DuckDbCandleRepository
from trading_system.data.quality import check_repository_symbol_bar
from trading_system.data.universe import default_symbols, required_okx_bars_for_profiles


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Check local DuckDB candle data quality.")
    parser.add_argument("--db", default="storage/history.duckdb", help="DuckDB path. Relative paths are resolved from project root.")
    parser.add_argument("--symbols", nargs="+", default=list(default_symbols()), help="Instrument ids to check.")
    parser.add_argument("--bars", nargs="+", default=list(required_okx_bars_for_profiles()), help="Candle bars to check.")
    parser.add_argument("--venue", default="okx", help="Venue to check.")
    parser.add_argument("--inst-type", default="SPOT", help="Instrument type to check.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repository = DuckDbCandleRepository(_resolve_project_path(args.db))
    reports = []

    for symbol in args.symbols:
        for bar in args.bars:
            report = check_repository_symbol_bar(
                repository,
                symbol,
                bar,
                venue=args.venue,
                inst_type=args.inst_type,
            )
            reports.append(report)
            print(
                f"{report.venue} {report.inst_type} {report.inst_id} {report.bar}: "
                f"status={report.status} rows={report.row_count} "
                f"earliest={report.earliest_ts_ms} latest={report.latest_ts_ms} "
                f"issues={len(report.issues)}"
            )
            for issue in report.issues:
                print(f"  {issue.severity} {issue.code}: {issue.message} ts={issue.timestamp_ms}")

    return 1 if any(not report.passed for report in reports) else 0


def _resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
