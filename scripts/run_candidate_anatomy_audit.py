from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.backtest.layered_cache import artifact_paths, read_jsonl
from trading_system.backtest.layered_pipeline import run_layered_proposal
from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository
from trading_system.reports.candidate_anatomy import (
    build_candidate_anatomy_rows,
    summarize_candidate_anatomy,
    write_candidate_anatomy_artifacts,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run liquidity reversal candidate anatomy audit from layered cache.")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--preset", default="configs/presets/btc_eth_swap_proposal.toml")
    parser.add_argument("--cache-dir", default="storage/backtest_cache/btc_eth_swap_50w_raw")
    parser.add_argument("--output-dir", default="storage/backtest_cache/candidate_anatomy_50w")
    parser.add_argument("--max-entry-windows", type=int, default=50)
    parser.add_argument("--force-candidates", action="store_true")
    parser.add_argument("--force-filter", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    preset = load_backtest_preset(_resolve(args.preset))
    repository = DuckDbCandleRepository(_resolve(args.db))
    cache_dir = _resolve(args.cache_dir)
    paths = artifact_paths(cache_dir)

    if args.force_candidates or not paths.raw_candidates_path.exists() or not paths.context_path.exists():
        run_layered_proposal(
            repository=repository,
            preset=preset,
            mode="candidate_only",
            cache_dir=cache_dir,
            max_entry_windows=args.max_entry_windows,
            cost_tiers=("base",),
            force_context=args.force_candidates,
            force_candidates=args.force_candidates,
        )

    if args.force_filter or not paths.filter_results_path.exists():
        run_layered_proposal(
            repository=repository,
            preset=preset,
            mode="filter_replay",
            cache_dir=cache_dir,
            max_entry_windows=args.max_entry_windows,
            cost_tiers=("base",),
            force_filter=True,
        )

    filter_rows = read_jsonl(paths.filter_results_path)
    anatomy_rows = build_candidate_anatomy_rows(repository=repository, filter_rows=filter_rows, preset=preset)
    summary = summarize_candidate_anatomy(anatomy_rows)
    outputs = write_candidate_anatomy_artifacts(output_dir=_resolve(args.output_dir), rows=anatomy_rows, summary=summary)

    print(f"cache_dir={cache_dir}")
    print(f"raw_candidates={len(filter_rows)}")
    print(f"anatomy_rows={len(anatomy_rows)}")
    print(f"formal_approved={summary['formal_approved_count']}")
    print(f"shadow_approved_5={summary['shadow_approved_5_count']}")
    print(f"shadow_approved_8={summary['shadow_approved_8_count']}")
    for bucket, payload in summary["stop_buckets"].items():
        print(f"{bucket}={payload['count']} ratio={payload['ratio']:.4f}")
    for name, path in outputs.items():
        print(f"artifact {name} {path}")
    return 0


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
