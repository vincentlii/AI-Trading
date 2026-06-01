from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.diagnostics.stage6d_edge import build_stage6d_edge_report, read_csv_rows, read_jsonl, write_stage6d_artifacts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Stage 6D capped sizing edge and MFE quality diagnostics.")
    parser.add_argument("--sizing-candidates", required=True)
    parser.add_argument("--execution-results", required=True)
    parser.add_argument("--output-dir", default="storage/backtest_cache/stage6d_edge/10000w")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    sizing_rows = read_csv_rows(_resolve(args.sizing_candidates))
    execution_rows = read_jsonl(_resolve(args.execution_results))
    result = build_stage6d_edge_report(sizing_rows=sizing_rows, execution_rows=execution_rows)
    paths = write_stage6d_artifacts(_resolve(args.output_dir), result)
    best_gate = max(result.gate_rows, key=lambda row: (float(row.get("MFE_R_avg") or -999.0), int(row.get("approved_after_gate") or 0)))
    print(
        " ".join(
            (
                f"tiers={len(result.tier_rows)}",
                f"combos={len(result.combo_rows)}",
                f"gates={len(result.gate_rows)}",
                f"best_gate={best_gate['gate']}",
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
