from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_pipeline.runners.tc_bp_strict_causal_smoke import run_tc_bp_strict_causal_smoke
from trading_system.data.history import DuckDbCandleRepository


class ReadOnlyDuckDbCandleRepository(DuckDbCandleRepository):
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def _connect(self):
        import duckdb

        return duckdb.connect(str(self.database_path), read_only=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Profile C strict causal BP signal smoke.")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--output-root", default="storage/research_runs/trend_continuation_family/bp_strict_causal_smoke")
    parser.add_argument("--start", default="2024-07-01")
    parser.add_argument("--end", default="2024-11-30")
    parser.add_argument("--visual-review-status", default="generated_pending_human_review")
    args = parser.parse_args()
    result = run_tc_bp_strict_causal_smoke(
        repository=ReadOnlyDuckDbCandleRepository(Path(args.db)),
        output_root=Path(args.output_root),
        start_date=args.start,
        end_date=args.end,
        visual_review_status=args.visual_review_status,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
