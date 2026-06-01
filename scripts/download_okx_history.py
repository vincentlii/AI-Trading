from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.data.download import OkxHistoryDownloader
from trading_system.data.history import DuckDbCandleRepository
from trading_system.data.okx_cli import OkxCliMarketData
from trading_system.data.quality import check_repository_symbol_bar
from trading_system.data.universe import default_symbols, required_okx_bars_for_profiles
from trading_system.config import load_backtest_preset
from trading_system.timeframe_profiles import get_profile


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Download recent OKX public market candles into DuckDB.")
    parser.add_argument("--db", default="storage/history.duckdb", help="DuckDB path. Relative paths are resolved from project root.")
    parser.add_argument("--symbols", nargs="+", default=list(default_symbols()), help="OKX instrument ids to download.")
    parser.add_argument("--bars", nargs="+", default=list(required_okx_bars_for_profiles()), help="OKX candle bars to download.")
    parser.add_argument("--preset", default=None, help="Optional preset path. When set, symbols, bars, and inst_type come from preset targets.")
    parser.add_argument("--limit", type=int, default=100, help="Candles per request.")
    parser.add_argument("--max-pages", type=int, default=1, help="Maximum historical pages per symbol/bar.")
    parser.add_argument("--target-min-candles", type=int, default=None, help="Stop each symbol/bar after at least this many stored candles.")
    parser.add_argument("--start-date", default=None, help="Stop each symbol/bar after earliest candle reaches this UTC date, YYYY-MM-DD.")
    parser.add_argument("--quality-check-after-download", action="store_true", help="Run data quality checks after downloading.")
    parser.add_argument("--okx-command", default=None, help="Optional OKX CLI command path.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    db_path = _resolve_project_path(args.db)
    client = OkxCliMarketData(okx_command=args.okx_command)
    repository = DuckDbCandleRepository(db_path)
    start_ts_ms = _parse_start_date_ms(args.start_date)
    scopes = _download_scopes(args)

    summaries = []
    for inst_type, symbols, bars in scopes:
        downloader = OkxHistoryDownloader(client, repository, inst_type=inst_type)
        summaries.extend(
            downloader.download_many(
                symbols,
                bars,
                limit=args.limit,
                max_pages=args.max_pages,
                target_min_candles=args.target_min_candles,
                start_ts_ms=start_ts_ms,
            )
        )
    for summary in summaries:
        print(
            f"{summary.inst_id} {summary.bar}: "
            f"saved={summary.saved_count} "
            f"skipped={summary.skipped_unconfirmed_count} "
            f"earliest={summary.earliest_ts_ms} "
            f"latest={summary.latest_confirmed_ts_ms} "
            f"error={summary.error}"
        )
        if args.quality_check_after_download:
            report = check_repository_symbol_bar(
                repository,
                summary.inst_id,
                summary.bar,
                venue=summary.venue,
                inst_type=summary.inst_type,
            )
            print(
                f"  quality={report.status} rows={report.row_count} "
                f"issues={len(report.issues)} earliest={report.earliest_ts_ms} latest={report.latest_ts_ms}"
            )

    return 1 if any(summary.error for summary in summaries) else 0


def _resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _parse_start_date_ms(value: str | None) -> int | None:
    if value is None:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _download_scopes(args) -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    if args.preset is None:
        return (("SPOT", tuple(args.symbols), tuple(args.bars)),)
    preset = load_backtest_preset(_resolve_project_path(args.preset))
    bars = required_okx_bars_for_profiles(tuple(get_profile(key) for key in preset.scan.profile_keys))
    grouped: dict[str, list[str]] = {}
    for target in preset.assets.targets:
        grouped.setdefault(target.inst_type, []).append(target.inst_id)
    return tuple((inst_type, tuple(symbols), bars) for inst_type, symbols in grouped.items())


if __name__ == "__main__":
    raise SystemExit(main())
