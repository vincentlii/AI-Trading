from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository
from trading_system.diagnostics.minimal_lr_filter import run_minimal_execution_replay
from trading_system.diagnostics.stage6_quality import build_stage6_quality_report, read_jsonl, write_stage6_artifacts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Stage 6 quality filter recovery diagnostics.")
    parser.add_argument("--filter-results", default="storage/backtest_cache/minimal_lr_v0_filter/3000w/minimal_lr_v0_filter_results.jsonl")
    parser.add_argument("--execution-results", default="storage/backtest_cache/minimal_lr_v0_filter/3000w/minimal_lr_v0_execution_results.jsonl")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--preset", default="configs/presets/btc_eth_swap_proposal.toml")
    parser.add_argument("--output-dir", default="storage/backtest_cache/stage6_quality_recovery/3000w")
    parser.add_argument("--skip-exit-sensitivity", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve(args.preset))
    filter_rows = read_jsonl(_resolve(args.filter_results))
    execution_rows = read_jsonl(_resolve(args.execution_results))
    result = build_stage6_quality_report(
        filter_rows=filter_rows,
        execution_rows=execution_rows,
        equity=preset.execution.initial_equity,
        max_single_notional_pct=preset.risk.max_single_notional_pct,
    )
    paths = write_stage6_artifacts(_resolve(args.output_dir), result)
    if not args.skip_exit_sensitivity:
        exit_rows = _exit_sensitivity_rows(repository=DuckDbCandleRepository(_resolve(args.db)), filter_rows=filter_rows, preset=preset)
        _write_csv(_resolve(args.output_dir) / "stage6_exit_sensitivity.csv", exit_rows)
    baseline = next(row for row in result.run_rows if row["run"] == "Run 0 Baseline")
    balanced = next(row for row in result.run_rows if row["run"] == "Run 7 Combined Balanced")
    print(
        " ".join(
            (
                f"baseline_formal={baseline['formal_approved']}",
                f"baseline_closed={baseline['closed_trades']}",
                f"balanced_formal={balanced['formal_approved']}",
                f"balanced_closed={balanced['closed_trades']}",
                f"report={paths['report_md']}",
            )
        )
    )
    return 0


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _exit_sensitivity_rows(*, repository, filter_rows, preset):
    variants = (
        ("current", preset),
        ("time_cut_2x", replace(preset, execution=replace(preset.execution, reversal_time_cut_bars=max(1, preset.execution.reversal_time_cut_bars * 2)))),
        ("lower_min_mfe", replace(preset, execution=replace(preset.execution, reversal_time_cut_min_mfe_r=0.3))),
        ("no_time_cut", replace(preset, execution=replace(preset.execution, reversal_time_cut_bars=0, reversal_time_cut_min_mfe_r=0.0))),
    )
    rows = []
    for name, variant in variants:
        executions = run_minimal_execution_replay(repository=repository, filter_rows=filter_rows, preset=variant)
        rows.append(
            {
                "variant": name,
                "closed_trades": len(executions),
                "time_cut_exit_count": sum(1 for row in executions if row.get("exit_reason") == "time_cut_exit"),
                "MFE_R_avg": _avg([float(row.get("mfe_R") or 0.0) for row in executions]),
                "MFE_R_p75": _percentile([float(row.get("mfe_R") or 0.0) for row in executions], 0.75),
                "MFE_R_p90": _percentile([float(row.get("mfe_R") or 0.0) for row in executions], 0.90),
                "net_R_avg": _avg([float(row.get("net_R") or 0.0) for row in executions]),
                "max_adverse_avg": _avg([float(row.get("mae_R") or 0.0) for row in executions]),
            }
        )
    return tuple(rows)


def _avg(values):
    return None if not values else sum(values) / len(values)


def _percentile(values, q):
    numbers = sorted(float(value) for value in values)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * q
    low = int(position)
    high = min(low + 1, len(numbers) - 1)
    fraction = position - low
    return numbers[low] * (1.0 - fraction) + numbers[high] * fraction


def _write_csv(path: Path, rows) -> None:
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())
