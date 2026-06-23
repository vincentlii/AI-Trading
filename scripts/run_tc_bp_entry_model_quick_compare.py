from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_pipeline.runners.tc_bp_entry_model_quick_compare import run_tc_bp_entry_model_quick_compare
from scripts.run_tc_bp_strict_causal_smoke import ReadOnlyDuckDbCandleRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare TC/BP left-limit and right-confirmation entry diagnostics.")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--report", default="AI Trading/08_复盘与报告/TC BP Entry Model Quick Compare.md")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2024-11-30")
    parser.add_argument("--instrument", action="append", choices=("BTC-USDT-SWAP", "ETH-USDT-SWAP"))
    args = parser.parse_args()
    result = run_tc_bp_entry_model_quick_compare(
        repository=ReadOnlyDuckDbCandleRepository(Path(args.db)),
        report_path=Path(args.report),
        start_date=args.start,
        end_date=args.end,
        instruments=tuple(args.instrument) if args.instrument else ("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
