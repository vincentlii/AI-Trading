from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_pipeline.runners.aggregate_summaries import build_aggregation_result
from research_pipeline.runners.build_artifact_index import build_and_write_artifact_index
from research_pipeline.runners.smoke_plan import build_smoke_plan
from research_pipeline.cli.research import _load_aggregation_arg


DEPRECATION = (
    "[DEPRECATED WRAPPER] use research_pipeline.cli.research smoke-plan "
    "--strategy liquidity_reversal --aggregation-result <path>"
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Deprecated Stage 7 smoke plan wrapper.")
    parser.add_argument("--aggregation-result", default="")
    parser.add_argument("--summary-dir", default="storage/backtest_cache/stage6e_aggregator")
    parser.add_argument("--filter-results", default="")
    parser.add_argument("--execution-results", default="")
    parser.add_argument("--combo", action="append", default=None)
    parser.add_argument("--cost-tier", action="append", default=None)
    parser.add_argument("--output-dir", default="storage/backtest_cache/stage7_smoke_plan")
    parser.add_argument("--build-artifact-index", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    source = _resolve(args.aggregation_result) if args.aggregation_result else _resolve(args.summary_dir)
    aggregation = _load_aggregation_arg("liquidity_reversal", source)
    plan = build_smoke_plan(aggregation)

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "smoke_plan.json").write_text(plan.as_json(), encoding="utf-8")
    (output_dir / "smoke_plan.md").write_text(plan.as_markdown() + "\n", encoding="utf-8")
    (output_dir / "stage7_smoke_plan.md").write_text(plan.as_markdown() + "\n", encoding="utf-8")
    (output_dir / "stage7_smoke_grouped_rows.jsonl").write_text("", encoding="utf-8")
    if args.build_artifact_index:
        build_and_write_artifact_index(
            artifact_dir=output_dir,
            output_dir=output_dir,
            strategy="liquidity_reversal",
            stage="stage7_smoke_plan",
            window="multi",
            source_command="scripts/run_stage7_smoke_plan.py",
            legacy_source=True,
            notes="Deprecated wrapper using research_pipeline proposal-only smoke plan.",
        )

    print(DEPRECATION)
    print(
        f"combos={len(plan.selected_combos)} selected={','.join(plan.selected_combos)} "
        f"formal_conclusion_enabled={plan.formal_conclusion_enabled} report={output_dir / 'stage7_smoke_plan.md'}"
    )
    return 0


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
