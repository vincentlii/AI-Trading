from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.backtest import BacktestBatchRunner
from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository
from trading_system.reports.backtest_runs import record_backtest_run
from trading_system.strategies.trend_price_volume_v1 import TrendPriceVolumeStrategy


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run P4.4 BTC/ETH A/B/C batch backtest ranking.")
    parser.add_argument("--db", default="storage/history.duckdb", help="DuckDB path. Relative paths are resolved from project root.")
    parser.add_argument(
        "--preset",
        default="configs/presets/btc_eth_p4_4.toml",
        help="Backtest preset path. Relative paths are resolved from project root.",
    )
    parser.add_argument(
        "--output-dir",
        default="storage/backtest_runs",
        help="Directory for persistent backtest run records. Relative paths are resolved from project root.",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Print results without writing persistent run artifacts.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve_project_path(args.preset))
    repository = DuckDbCandleRepository(_resolve_project_path(args.db))
    report = BacktestBatchRunner(
        repository=repository,
        preset=preset,
        strategy=TrendPriceVolumeStrategy(),
    ).run()

    print(f"config_version={report.config_version}")
    print(f"config_fingerprint={report.config_fingerprint}")
    print(
        "rank status symbol profile strategy_family setup trades net_profit max_drawdown "
        "win_rate pl_ratio profit_factor avg_holding_bars expectancy fee_to_gross_profit"
    )
    rows = report.to_rows()
    for row in rows:
        print(
            f"{row['rank']} {row['status']} {row['symbol']} {row['timeframe_group']} "
            f"{row['strategy_family']} {row['setup_type']} {row['trade_count']} "
            f"{_fmt(row['net_profit'])} {_fmt_pct(row['max_drawdown'])} {_fmt_pct(row['win_rate'])} "
            f"{_fmt(row['profit_loss_ratio'])} {_fmt(row['profit_factor'])} "
            f"{_fmt(row['average_holding_bars'])} {_fmt(row['expectancy_per_trade'])} "
            f"{_fmt_pct(row['fee_to_gross_profit_ratio'])}"
        )

    skipped = [run for run in report.scan_result.profile_runs if run.status != "completed"]
    for run in skipped:
        print(
            f"skipped {run.target.canonical_symbol} {run.profile_key}: "
            f"{','.join(run.reason_codes)}"
        )

    if args.no_record:
        print("recording=disabled")
    else:
        record = record_backtest_run(
            output_dir=args.output_dir,
            script_name="scripts/run_btc_eth_p4_4_backtest.py",
            command_args={
                "db": args.db,
                "preset": args.preset,
            },
            preset=preset,
            rows=rows,
            project_root=PROJECT_ROOT,
        )
        print(f"recorded_run_id={record.run_id}")
        print(f"recorded_run_dir={record.run_dir}")

    return 0


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _fmt(value: object) -> str:
    number = float(value)
    if number == float("inf"):
        return "inf"
    return f"{number:.4f}"


def _fmt_pct(value: object) -> str:
    return f"{float(value):.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
