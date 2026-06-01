from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.backtest.layered_pipeline import LAYERED_MODES, run_layered_proposal
from trading_system.data.history import DuckDbCandleRepository
from trading_system.reports.backtest_runs import record_backtest_run


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run BTC/ETH OKX USDT swap proposal diagnostics.")
    parser.add_argument("--db", default="storage/history.duckdb", help="DuckDB path. Relative paths are resolved from project root.")
    parser.add_argument(
        "--preset",
        default="configs/presets/btc_eth_swap_proposal.toml",
        help="Swap proposal preset path. Relative paths are resolved from project root.",
    )
    parser.add_argument(
        "--cost-tier",
        action="append",
        choices=("base", "stress", "harsh"),
        help="Limit run to one cost tier. Repeat for multiple tiers. Default runs all tiers.",
    )
    parser.add_argument(
        "--max-entry-windows",
        type=int,
        default=None,
        help="Limit rolling scan to the latest N entry windows for quick smoke tests.",
    )
    parser.add_argument(
        "--mode",
        choices=LAYERED_MODES,
        default="full_backtest",
        help="Layered proposal mode. Default runs cached full_backtest replay.",
    )
    parser.add_argument(
        "--cache-dir",
        default="storage/backtest_cache",
        help="Directory for layered context/candidate/filter/execution cache artifacts.",
    )
    parser.add_argument("--force-context", action="store_true", help="Rebuild context/features cache.")
    parser.add_argument("--force-candidates", action="store_true", help="Rebuild raw candidates cache.")
    parser.add_argument("--force-filter", action="store_true", help="Rebuild filter replay results.")
    parser.add_argument("--force-execution", action="store_true", help="Rebuild execution replay results.")
    parser.add_argument(
        "--output-dir",
        default="storage/backtest_runs",
        help="Directory for persistent backtest run records. Relative paths are resolved from project root.",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Print results without writing persistent run artifacts.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve_project_path(args.preset))
    repository = DuckDbCandleRepository(_resolve_project_path(args.db))
    print(f"config_version={preset.config_version}")
    print(f"config_fingerprint={preset.config_fingerprint}")
    print(f"funding_mode={preset.costs.funding_mode}")
    print(f"profiles={','.join(preset.scan.profile_keys)}")
    selected_cost_tiers = tuple(args.cost_tier) if args.cost_tier else tuple(tier.name for tier in preset.costs.cost_model_tiers)
    print(f"cost_tiers={','.join(selected_cost_tiers)}")
    print(f"max_entry_windows={args.max_entry_windows if args.max_entry_windows is not None else 'all'}")
    print(f"mode={args.mode}")
    layered = run_layered_proposal(
        repository=repository,
        preset=preset,
        mode=args.mode,
        cache_dir=_resolve_project_path(args.cache_dir),
        max_entry_windows=args.max_entry_windows,
        cost_tiers=selected_cost_tiers,
        force_context=args.force_context,
        force_candidates=args.force_candidates,
        force_filter=args.force_filter,
        force_execution=args.force_execution,
    )
    rows = layered.summary_rows

    print("artifact key value")
    print(f"artifact context_features {layered.context_path}")
    print(f"artifact raw_candidates {layered.raw_candidates_path}")
    print(f"artifact filter_results {layered.filter_results_path}")
    print(f"artifact execution_results {layered.execution_results_path}")
    print(f"artifact funnel_summary {layered.funnel_summary_path}")
    print(f"artifact gate_ablation {layered.gate_ablation_path}")
    print(f"artifact cache_manifest {layered.manifest_path}")
    print(f"artifact proposal_diagnostics {layered.diagnostics_report_path}")
    print(f"scanned_windows={layered.scanned_windows}")
    print(f"raw_candidates={layered.raw_candidates_count}")
    print("summary_rows")
    for row in rows:
        print(" ".join(f"{key}={value}" for key, value in row.items()))
    if args.no_record:
        print("recording=disabled")
    else:
        record = record_backtest_run(
            output_dir=args.output_dir,
            script_name="scripts/run_btc_eth_swap_proposal.py",
            command_args={
                "db": args.db,
                "preset": args.preset,
                "cost_tiers": selected_cost_tiers,
                "max_entry_windows": args.max_entry_windows,
                "mode": args.mode,
                "cache_dir": args.cache_dir,
            },
            preset=preset,
            rows=rows,
            project_root=PROJECT_ROOT,
            extra_artifacts={
                "context_features": layered.context_path,
                "raw_candidates": layered.raw_candidates_path,
                "filter_results": layered.filter_results_path,
                "execution_results": layered.execution_results_path,
                "funnel_summary": layered.funnel_summary_path,
                "gate_ablation": layered.gate_ablation_path,
                "cache_manifest": layered.manifest_path,
                "proposal_diagnostics": layered.diagnostics_report_path,
            },
            cache_manifest=layered.cache_manifest,
        )
        print(f"recorded_run_id={record.run_id}")
        print(f"recorded_run_dir={record.run_dir}")
    return 0


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
