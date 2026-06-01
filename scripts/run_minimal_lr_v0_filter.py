from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository
from trading_system.diagnostics.minimal_lr_filter import (
    read_candidates,
    replay_minimal_lr_v0,
    run_minimal_execution_replay,
    write_execution_rows,
    write_minimal_lr_v0_artifacts,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Minimal LR v0 filter replay from Stage 4 fresh candidates.")
    parser.add_argument("--candidates", default="storage/backtest_cache/fresh_lr_scanner_stage4/3000w/fresh_lr_candidates.jsonl")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--preset", default="configs/presets/btc_eth_swap_proposal.toml")
    parser.add_argument("--output-dir", default="storage/backtest_cache/minimal_lr_v0_filter")
    parser.add_argument("--run-execution", action="store_true", help="Run minimal execution replay for formal approved rows only.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve(args.preset))
    candidates = read_candidates(_resolve(args.candidates))
    result = replay_minimal_lr_v0(candidates=candidates, preset=preset)
    paths = write_minimal_lr_v0_artifacts(_resolve(args.output_dir), result)
    execution_count = 0
    if args.run_execution:
        repository = DuckDbCandleRepository(_resolve(args.db))
        execution_rows = run_minimal_execution_replay(repository=repository, filter_rows=result.filter_rows, preset=preset)
        write_execution_rows(_resolve(args.output_dir) / "minimal_lr_v0_execution_results.jsonl", execution_rows)
        execution_count = len(execution_rows)
    approved = sum(1 for row in result.filter_rows if row.get("formal_approved"))
    shadow_5 = sum(1 for row in result.filter_rows if row.get("shadow_approved_5"))
    shadow_8 = sum(1 for row in result.filter_rows if row.get("shadow_approved_8"))
    print(
        " ".join(
            (
                f"fresh_candidates={len(result.filter_rows)}",
                f"formal_approved={approved}",
                f"shadow_approved_5={shadow_5}",
                f"shadow_approved_8={shadow_8}",
                f"execution_rows={execution_count}",
                f"report={paths['report_md']}",
            )
        )
    )
    return 0


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
