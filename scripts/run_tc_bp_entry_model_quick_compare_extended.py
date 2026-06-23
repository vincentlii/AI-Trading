from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_pipeline.runners.tc_bp_entry_model_quick_compare import run_tc_bp_entry_model_quick_compare_extended
from scripts.run_tc_bp_strict_causal_smoke import ReadOnlyDuckDbCandleRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the diagnostic-only TC BP entry model extended compare.")
    parser.add_argument("--db", type=Path, default=Path("storage/history.duckdb"))
    parser.add_argument("--report", type=Path, default=Path("AI Trading/08_复盘与报告/TC BP Entry Model Quick Compare Extended.md"))
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2024-11-30")
    parser.add_argument("--instrument", action="append", choices=("BTC-USDT-SWAP", "ETH-USDT-SWAP"))
    args = parser.parse_args()
    result = run_tc_bp_entry_model_quick_compare_extended(
        repository=ReadOnlyDuckDbCandleRepository(args.db),
        report_path=args.report,
        start_date=args.start,
        end_date=args.end,
        instruments=tuple(args.instrument) if args.instrument else ("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
    )
    print(result.report_path)
    print(result.decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
