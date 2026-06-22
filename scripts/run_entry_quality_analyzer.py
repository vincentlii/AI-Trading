from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_pipeline.runners.entry_quality_analyzer import parse_timestamp_ms, run_entry_quality_analyzer
from trading_system.data.history import ReadOnlyDuckDbCandleRepository


DEFAULT_OUTPUT = Path("AI Trading/08_复盘与报告/Universal Entry Quality Analyzer Report.md")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Analyze entry quality from existing JSONL or CSV records.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", default=Path("storage/history.duckdb"), type=Path)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--max-horizon-hours", default=96, type=int)
    parser.add_argument("--holdout-start", required=True, help="ISO-8601 UTC timestamp or epoch milliseconds")
    parser.add_argument("--venue", default="okx")
    parser.add_argument("--inst-type", default="auto")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    holdout_start_ms = parse_timestamp_ms(args.holdout_start)
    if holdout_start_ms is None:
        raise ValueError("--holdout-start must be ISO-8601 or epoch milliseconds")
    result = run_entry_quality_analyzer(
        input_path=_resolve(args.input),
        output_path=_resolve(args.output),
        repository=ReadOnlyDuckDbCandleRepository(_resolve(args.db)),
        timeframe=args.timeframe,
        max_horizon_hours=args.max_horizon_hours,
        holdout_start_ms=holdout_start_ms,
        default_venue=args.venue,
        default_inst_type=args.inst_type,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
