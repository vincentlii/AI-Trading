from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository
from trading_system.diagnostics.p6_gate import P6GateConfig, build_p6_gate_report
from trading_system.strategies.trend_price_volume_v1 import TrendPriceVolumeStrategy


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run P6 pre-paper gate diagnostics.")
    parser.add_argument("--db", default="storage/history.duckdb", help="DuckDB path.")
    parser.add_argument("--preset", default="configs/presets/btc_eth_p4_4.toml", help="Backtest preset path.")
    parser.add_argument("--max-position-windows", type=int, default=500, help="Bounded recent windows for position-aware scan.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve_project_path(args.preset))
    repository = DuckDbCandleRepository(_resolve_project_path(args.db))
    report = build_p6_gate_report(
        repository=repository,
        preset=preset,
        strategy=TrendPriceVolumeStrategy(),
        config=P6GateConfig(max_position_aware_windows=args.max_position_windows),
    )
    print(f"passed={report.passed}")
    print(
        "category status reason_code details"
    )
    for row in report.rows:
        print(f"{row.category} {row.status} {row.reason_code} {row.details}")
    print(f"summary={dict(report.summary)}")
    return 0 if report.passed else 1


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
