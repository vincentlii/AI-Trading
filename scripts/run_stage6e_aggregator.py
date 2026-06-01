from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_pipeline.core.reports.aggregation_report import render_aggregation_report
from research_pipeline.runners.aggregate_summaries import build_aggregation_result
from research_pipeline.runners.build_artifact_index import build_and_write_artifact_index


DEPRECATION = (
    "[DEPRECATED WRAPPER] use research_pipeline.cli.research aggregate-summaries "
    "--strategy liquidity_reversal --summary-dir <path>"
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Deprecated Stage 6E aggregation wrapper.")
    parser.add_argument("--window-result", action="append", default=None)
    parser.add_argument("--summary-dir", default="storage/backtest_cache/stage6e_aggregator")
    parser.add_argument("--output-dir", default="storage/backtest_cache/stage6e_aggregator")
    parser.add_argument("--build-artifact-index", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    summary_dir = _resolve(args.summary_dir)
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = build_aggregation_result("liquidity_reversal", summary_dir)
    report = render_aggregation_report(result)

    (output_dir / "aggregation_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "aggregation_report.md").write_text(report + "\n", encoding="utf-8")
    (output_dir / "stage6e_aggregator_final_report.md").write_text(report + "\n", encoding="utf-8")
    _copy_comparison(summary_dir, output_dir)
    if args.build_artifact_index:
        build_and_write_artifact_index(
            artifact_dir=output_dir,
            output_dir=output_dir,
            strategy="liquidity_reversal",
            stage="stage6e_aggregation",
            window="multi",
            source_command="scripts/run_stage6e_aggregator.py",
            legacy_source=True,
            notes="Deprecated wrapper using research_pipeline read-only aggregation.",
        )

    print(DEPRECATION)
    print(
        f"windows={len(result.windows)} smoke_ready={','.join(result.smoke_ready_combos)} "
        f"report={output_dir / 'stage6e_aggregator_final_report.md'}"
    )
    return 0


def _copy_comparison(summary_dir: Path, output_dir: Path) -> None:
    snapshot = summary_dir / "stage6e_aggregated_comparison_snapshot.csv"
    legacy = summary_dir / "stage6e_aggregated_comparison.csv"
    source = snapshot if snapshot.exists() else legacy
    destination = output_dir / "stage6e_aggregated_comparison.csv"
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
