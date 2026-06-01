from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository
from trading_system.diagnostics.fresh_lr_scanner import scan_fresh_liquidity_reversal, write_fresh_lr_artifacts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Fresh Liquidity Reversal Minimal v0 event scanner.")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--preset", default="configs/presets/btc_eth_swap_proposal.toml")
    parser.add_argument("--output-dir", default="storage/backtest_cache/fresh_lr_scanner")
    parser.add_argument("--windows", type=int, action="append", help="Entry scan windows. Repeatable. Default: 200/500/1000/3000.")
    parser.add_argument("--reclaim-window", type=int, action="append", help="Diagnostic reclaim window. Repeatable. Default: 3/5/8.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve(args.preset))
    repository = DuckDbCandleRepository(_resolve(args.db))
    windows = tuple(args.windows) if args.windows else (200, 500, 1000, 3000)
    reclaim_windows = tuple(args.reclaim_window) if args.reclaim_window else (3, 5, 8)
    output_root = _resolve(args.output_dir)

    print(f"config_version={preset.config_version}")
    print(f"windows={','.join(str(item) for item in windows)}")
    print(f"reclaim_windows={','.join(str(item) for item in reclaim_windows)}")
    for window in windows:
        result = scan_fresh_liquidity_reversal(
            repository=repository,
            preset=preset,
            max_entry_windows=window,
            reclaim_windows=reclaim_windows,
        )
        paths = write_fresh_lr_artifacts(output_root / f"{window}w", result)
        totals = _totals(result.summary_rows)
        print(
            " ".join(
                (
                    f"window={window}",
                    f"structure={totals['structure_levels_available_count']}",
                    f"sweep={totals['sweep_events_count']}",
                    f"reclaim={totals['reclaim_events_count']}",
                    f"signal={totals['signal_events_count']}",
                    f"candidate={totals['fresh_entry_candidates_count']}",
                    f"expired={totals['expired_events_count']}",
                    f"invalidated={totals['invalidated_events_count']}",
                    f"report={paths['report_md']}",
                )
            )
        )
    return 0


def _totals(rows):
    keys = (
        "structure_levels_available_count",
        "sweep_events_count",
        "reclaim_events_count",
        "signal_events_count",
        "fresh_entry_candidates_count",
        "expired_events_count",
        "invalidated_events_count",
    )
    return {key: sum(int(row.get(key, 0) or 0) for row in rows) for key in keys}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
