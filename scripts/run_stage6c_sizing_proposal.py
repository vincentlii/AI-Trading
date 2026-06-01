from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.diagnostics.stage6c_sizing import build_stage6c_sizing_report, read_jsonl, write_stage6c_artifacts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Stage 6C setup-specific sizing proposal diagnostics.")
    parser.add_argument("--filter-results", required=True)
    parser.add_argument("--execution-results", default="")
    parser.add_argument("--preset", default="configs/presets/btc_eth_swap_proposal.toml")
    parser.add_argument("--output-dir", default="storage/backtest_cache/stage6c_sizing/3000w")
    parser.add_argument("--window-label", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve(args.preset))
    filter_rows = read_jsonl(_resolve(args.filter_results))
    execution_rows = read_jsonl(_resolve(args.execution_results)) if args.execution_results else ()
    result = build_stage6c_sizing_report(
        filter_rows=filter_rows,
        execution_rows=execution_rows,
        equity=preset.execution.initial_equity,
        max_single_notional_pct=preset.risk.max_single_notional_pct,
        window_label=args.window_label,
    )
    paths = write_stage6c_artifacts(_resolve(args.output_dir), result)
    current = next(row for row in result.sizing_summary_rows if row["sizing_model"] == "current_risk_based_sizing")
    capped = next(row for row in result.sizing_summary_rows if row["sizing_model"] == "notional_capped_risk_based")
    print(
        " ".join(
            (
                f"fresh={current['fresh_candidates']}",
                f"current_formal={current['formal_approved']}",
                f"capped_proposal={capped['proposal_approved']}",
                f"capped_actual_risk_p50={capped['actual_risk_pct_after_cap_p50']}",
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
