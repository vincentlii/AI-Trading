from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.backtest.proposal_validation import validate_parameter_proposal
from trading_system.config import load_backtest_preset, load_parameter_proposal
from trading_system.data.history import DuckDbCandleRepository
from trading_system.strategies.trend_price_volume_v1 import TrendPriceVolumeStrategy


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Validate a P4.5 parameter proposal with the P4.4 backtest path.")
    parser.add_argument("--proposal", required=True, help="Proposal JSON path. Relative paths are resolved from project root.")
    parser.add_argument("--db", default="storage/history.duckdb", help="DuckDB path. Relative paths are resolved from project root.")
    parser.add_argument(
        "--preset",
        default="configs/presets/btc_eth_p4_4.toml",
        help="Base preset path. Relative paths are resolved from project root.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    proposal = load_parameter_proposal(_resolve_project_path(args.proposal))
    preset = load_backtest_preset(_resolve_project_path(args.preset))
    repository = DuckDbCandleRepository(_resolve_project_path(args.db))
    validation = validate_parameter_proposal(
        proposal=proposal,
        base_preset=preset,
        repository=repository,
        strategy=TrendPriceVolumeStrategy(),
    )

    print(f"proposal_id={validation.proposal_id}")
    print(f"status={validation.status}")
    print(f"auto_apply={str(validation.auto_apply).lower()}")
    print(f"base_config_version={validation.base_config_version}")
    print(f"base_config_fingerprint={validation.base_config_fingerprint}")
    print(f"proposed_config_fingerprint={validation.proposed_config_fingerprint}")
    print(f"base_rows={len(validation.base_report.to_rows())}")
    print(f"proposed_rows={len(validation.proposed_report.to_rows())}")
    print(
        "rank status symbol profile strategy_family setup trades net_profit max_drawdown "
        "win_rate profit_factor expectancy fee_to_gross_profit"
    )
    for row in validation.proposed_report.to_rows():
        print(
            f"{row['rank']} {row['status']} {row['symbol']} {row['timeframe_group']} "
            f"{row['strategy_family']} {row['setup_type']} {row['trade_count']} "
            f"{_fmt(row['net_profit'])} {_fmt_pct(row['max_drawdown'])} "
            f"{_fmt_pct(row['win_rate'])} {_fmt(row['profit_factor'])} "
            f"{_fmt(row['expectancy_per_trade'])} {_fmt_pct(row['fee_to_gross_profit_ratio'])}"
        )
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
