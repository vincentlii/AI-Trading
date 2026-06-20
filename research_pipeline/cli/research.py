from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_pipeline.core.analytics.aggregation import AggregationResult
from research_pipeline.runners.artifact_summary import build_artifact_summary
from research_pipeline.runners.aggregate_summaries import build_aggregation_result
from research_pipeline.runners.build_artifact_index import build_and_write_artifact_index
from research_pipeline.runners.edge_analysis import build_edge_analysis
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.legacy_command import legacy_mapping_report, legacy_run_preview
from research_pipeline.runners.lineage_repair import run_lineage_repair
from research_pipeline.runners.list_artifacts import list_artifacts_from_index, list_runs_from_registry
from research_pipeline.runners.lr_attempt_proposal import run_lr_attempt_proposal
from research_pipeline.runners.lr_combined_candidate_fix import run_lr_combined_candidate_fix
from research_pipeline.runners.lr_combined_candidate_proposal import run_lr_combined_candidate_proposal
from research_pipeline.runners.lr_causal_rebuild import run_lr_causal_anatomy
from research_pipeline.runners.lr_multitimeframe_event_research import (
    run_lr_multitimeframe_event_research,
)
from research_pipeline.runners.lr_exit_profile_proposal import run_lr_exit_profile_proposal
from research_pipeline.runners.lr_expansion_diagnostics import run_lr_expansion_diagnostics
from research_pipeline.runners.lr_robustness_fix import run_lr_robustness_fix
from research_pipeline.runners.lr_robustness_validation import run_lr_robustness_validation
from research_pipeline.runners.lr_sizing_proposal import run_lr_sizing_proposal
from research_pipeline.runners.lr_structure_source_proposal import run_lr_structure_source_proposal
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.research_flow_audit import run_research_flow_audit
from research_pipeline.runners.regression_summary import build_regression_summary
from research_pipeline.runners.root_cause_investigation import run_root_cause_investigation
from research_pipeline.runners.sizing_diagnostics import build_sizing_diagnostics
from research_pipeline.runners.smoke_plan import build_smoke_plan
from research_pipeline.runners.stage7_smoke_backtest import run_stage7_smoke_backtest
from research_pipeline.runners.strategy_regression_check import run_strategy_regression_check
from research_pipeline.runners.strategy_research_validation import run_strategy_research_validation
from research_pipeline.runners.strategy_expansion_diagnostics import run_strategy_expansion_diagnostics
from research_pipeline.runners.strategy_summary import build_strategy_summary
from research_pipeline.runners.strategy_dry_run import run_strategy_dry_run
from research_pipeline.runners.tc_family_trade_count_expansion import run_tc_family_trade_count_expansion
from research_pipeline.runners.tc_family_profit_execution_optimization import (
    run_tc_family_profit_execution_optimization,
)
from research_pipeline.runners.tc_family_cost_aware_exit_target import (
    run_tc_family_cost_aware_exit_target,
)
from research_pipeline.runners.tc_family_cost_aware_refinement_with_trend_state import (
    run_tc_family_cost_aware_refinement_with_trend_state,
)
from research_pipeline.runners.tc_family_final_regime_aware_refinement import (
    run_tc_family_final_regime_aware_refinement,
)
from research_pipeline.registry.strategy_registry import default_strategy_registry
from research_pipeline.runners.validate_artifacts import validate_artifact_index
from trading_system.config import load_backtest_preset
from trading_system.data.history import DuckDbCandleRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research_pipeline.cli.research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    regression = subparsers.add_parser(
        "regression-summary",
        help="Read frozen baseline artifacts and print a minimal regression summary.",
    )
    regression.add_argument("--strategy", required=True)
    regression.add_argument("--baseline-dir", required=True)
    regression.add_argument("--format", choices=("json", "markdown"), default="json")

    legacy_list = subparsers.add_parser(
        "legacy-list",
        help="List legacy script wrappers registered in the research pipeline.",
    )
    legacy_list.add_argument("--strategy")

    legacy_run = subparsers.add_parser(
        "legacy-run",
        help="Dry-run a legacy script wrapper and echo the command that would run old logic.",
    )
    legacy_run.add_argument("--name", required=True)
    legacy_run.add_argument("legacy_args", nargs=argparse.REMAINDER)

    artifact_summary = subparsers.add_parser(
        "artifact-summary",
        help="Read existing artifacts and print a normalized research run summary.",
    )
    artifact_summary.add_argument("--strategy", required=True)
    artifact_summary.add_argument("--artifact-dir", required=True)
    artifact_summary.add_argument("--format", choices=("json", "markdown"), default="json")

    aggregate_summaries = subparsers.add_parser(
        "aggregate-summaries",
        help="Read artifact summaries and print a read-only aggregation result.",
    )
    aggregate_summaries.add_argument("--strategy", required=True)
    aggregate_summaries.add_argument("--summary-dir", required=True)
    aggregate_summaries.add_argument("--format", choices=("json", "markdown"), default="json")
    aggregate_summaries.add_argument("--output-dir")

    smoke_plan = subparsers.add_parser(
        "smoke-plan",
        help="Build a proposal-only smoke plan from a read-only aggregation source.",
    )
    smoke_plan.add_argument("--strategy", required=True)
    smoke_plan.add_argument("--aggregation-result", required=True)
    smoke_plan.add_argument("--format", choices=("json", "markdown"), default="json")
    smoke_plan.add_argument("--output-dir")

    edge_analysis = subparsers.add_parser(
        "edge-analysis",
        help="Read existing summaries and print read-only MFE/MAE tag edge analytics.",
    )
    edge_analysis.add_argument("--strategy", required=True)
    edge_source = edge_analysis.add_mutually_exclusive_group(required=True)
    edge_source.add_argument("--summary-dir")
    edge_source.add_argument("--aggregation-result")
    edge_analysis.add_argument("--output-dir")
    edge_analysis.add_argument("--format", choices=("json", "markdown"), default="json")

    sizing_diagnostics = subparsers.add_parser(
        "sizing-diagnostics",
        help="Read existing summaries and print read-only sizing diagnostics.",
    )
    sizing_diagnostics.add_argument("--strategy", required=True)
    sizing_source = sizing_diagnostics.add_mutually_exclusive_group(required=True)
    sizing_source.add_argument("--summary-dir")
    sizing_source.add_argument("--artifact-index")
    sizing_diagnostics.add_argument("--output-dir")
    sizing_diagnostics.add_argument("--format", choices=("json", "markdown"), default="json")

    build_index = subparsers.add_parser(
        "build-artifact-index",
        help="Build an artifact index manifest for an existing artifact directory.",
    )
    build_index.add_argument("--strategy", required=True)
    build_index.add_argument("--stage", required=True)
    build_index.add_argument("--window", required=True)
    build_index.add_argument("--artifact-dir", required=True)
    build_index.add_argument("--output-dir", required=True)
    build_index.add_argument("--source-command", default="")
    build_index.add_argument("--legacy-source", action="store_true")

    register_run = subparsers.add_parser(
        "register-run",
        help="Register an artifact index as a research run.",
    )
    register_run.add_argument("--registry", required=True)
    register_run.add_argument("--artifact-index", required=True)
    register_run.add_argument("--strategy", required=True)
    register_run.add_argument("--stage", required=True)
    register_run.add_argument("--window", required=True)
    register_run.add_argument("--source-command", default="")
    register_run.add_argument("--baseline-ref")
    register_run.add_argument("--notes", default="")
    register_run.add_argument("--tag", action="append", default=None)
    register_run.add_argument("--proposal-only", action="store_true", default=True)
    register_run.add_argument("--formal-conclusion-enabled", action="store_true", default=False)
    register_run.add_argument("--readonly", action="store_true", default=True)
    register_run.add_argument("--legacy-source", action="store_true")

    list_artifacts = subparsers.add_parser("list-artifacts")
    list_artifacts.add_argument("--artifact-index", required=True)
    list_artifacts.add_argument("--strategy")
    list_artifacts.add_argument("--stage")
    list_artifacts.add_argument("--window")

    validate_artifacts = subparsers.add_parser("validate-artifacts")
    validate_artifacts.add_argument("--artifact-index", required=True)

    list_runs = subparsers.add_parser("list-runs")
    list_runs.add_argument("--registry", required=True)

    subparsers.add_parser("list-strategies")

    strategy_dry_run = subparsers.add_parser("strategy-dry-run")
    strategy_dry_run.add_argument("--strategy", required=True)
    strategy_dry_run.add_argument("--dataset-window", default="dry_run_fixture")
    strategy_dry_run.add_argument("--output-dir")
    strategy_dry_run.add_argument("--format", choices=("json", "markdown"), default="json")

    strategy_research_validation = subparsers.add_parser("strategy-research-validation")
    strategy_research_validation.add_argument("--strategy", required=True)
    strategy_research_validation.add_argument("--preset", required=True)
    strategy_research_validation.add_argument("--db", required=True)
    strategy_research_validation.add_argument("--dataset-window", required=True)
    strategy_research_validation.add_argument("--output-root")
    strategy_research_validation.add_argument("--cost-tier", action="append", default=None)
    strategy_research_validation.add_argument("--max-entry-windows", type=int)
    strategy_research_validation.add_argument("--allow-expansion", action="store_true")
    strategy_research_validation.add_argument("--force", action="store_true")
    strategy_research_validation.add_argument("--format", choices=("json", "markdown"), default="json")

    strategy_expansion_diagnostics = subparsers.add_parser("strategy-expansion-diagnostics")
    strategy_expansion_diagnostics.add_argument("--strategy", required=True)
    strategy_expansion_diagnostics.add_argument("--preset", required=True)
    strategy_expansion_diagnostics.add_argument("--db", required=True)
    strategy_expansion_diagnostics.add_argument("--dataset-window", required=True)
    strategy_expansion_diagnostics.add_argument("--output-root")
    strategy_expansion_diagnostics.add_argument("--max-entry-windows", type=int)
    strategy_expansion_diagnostics.add_argument("--run-top-variants", action="store_true")
    strategy_expansion_diagnostics.add_argument("--cost-tier", action="append", default=None)
    strategy_expansion_diagnostics.add_argument("--baseline-artifact-dir")
    strategy_expansion_diagnostics.add_argument("--reuse-baseline", action="store_true")
    strategy_expansion_diagnostics.add_argument("--variant-only", action="store_true")
    strategy_expansion_diagnostics.add_argument("--variant", action="append", default=None)
    strategy_expansion_diagnostics.add_argument("--force", action="store_true")
    strategy_expansion_diagnostics.add_argument("--format", choices=("json", "markdown"), default="json")

    tc_family_expansion = subparsers.add_parser("tc-family-trade-count-expansion")
    tc_family_expansion.add_argument("--preset", required=True)
    tc_family_expansion.add_argument("--db", required=True)
    tc_family_expansion.add_argument("--dataset-window", required=True)
    tc_family_expansion.add_argument("--output-root")
    tc_family_expansion.add_argument("--max-entry-windows", type=int)
    tc_family_expansion.add_argument("--cost-tier", action="append", default=None)
    tc_family_expansion.add_argument("--chunk-size", type=int, default=20)
    tc_family_expansion.add_argument("--format", choices=("json", "markdown"), default="json")

    tc_family_profit = subparsers.add_parser("tc-family-profit-execution-optimization")
    tc_family_profit.add_argument("--preset", required=True)
    tc_family_profit.add_argument("--db", required=True)
    tc_family_profit.add_argument("--dataset-window", required=True)
    tc_family_profit.add_argument("--baseline-run-root", required=True)
    tc_family_profit.add_argument("--output-root")
    tc_family_profit.add_argument("--cost-tier", action="append", default=None)
    tc_family_profit.add_argument("--format", choices=("json", "markdown"), default="json")

    tc_family_cost_exit = subparsers.add_parser("tc-family-cost-aware-exit-target")
    tc_family_cost_exit.add_argument("--preset", required=True)
    tc_family_cost_exit.add_argument("--db", required=True)
    tc_family_cost_exit.add_argument("--dataset-window", required=True)
    tc_family_cost_exit.add_argument("--baseline-run-root", required=True)
    tc_family_cost_exit.add_argument("--output-root")
    tc_family_cost_exit.add_argument("--cost-tier", action="append", default=None)
    tc_family_cost_exit.add_argument("--format", choices=("json", "markdown"), default="json")

    tc_family_cost_refinement = subparsers.add_parser("tc-family-cost-aware-refinement-with-trend-state")
    tc_family_cost_refinement.add_argument("--preset", required=True)
    tc_family_cost_refinement.add_argument("--db", required=True)
    tc_family_cost_refinement.add_argument("--dataset-window", required=True)
    tc_family_cost_refinement.add_argument("--baseline-run-root", required=True)
    tc_family_cost_refinement.add_argument("--output-root")
    tc_family_cost_refinement.add_argument("--cost-tier", action="append", default=None)
    tc_family_cost_refinement.add_argument("--format", choices=("json", "markdown"), default="json")

    tc_family_final_regime = subparsers.add_parser("tc-family-final-regime-aware-refinement")
    tc_family_final_regime.add_argument("--preset", required=True)
    tc_family_final_regime.add_argument("--db", required=True)
    tc_family_final_regime.add_argument("--dataset-window", required=True)
    tc_family_final_regime.add_argument("--baseline-run-root", required=True)
    tc_family_final_regime.add_argument("--output-root")
    tc_family_final_regime.add_argument("--cost-tier", action="append", default=None)
    tc_family_final_regime.add_argument("--format", choices=("json", "markdown"), default="json")

    strategy_summary = subparsers.add_parser("strategy-summary")
    strategy_summary.add_argument("--strategy", required=True)
    strategy_summary.add_argument("--summary-dir", required=True)
    strategy_summary.add_argument("--output-dir")
    strategy_summary.add_argument("--format", choices=("json", "markdown"), default="json")

    strategy_regression = subparsers.add_parser("strategy-regression-check")
    strategy_regression.add_argument("--strategy", required=True)
    strategy_regression.add_argument("--baseline-dir", required=True)
    strategy_regression.add_argument("--summary-dir", required=True)
    strategy_regression.add_argument("--output-dir")
    strategy_regression.add_argument("--format", choices=("json", "markdown"), default="json")

    stage7_smoke = subparsers.add_parser("stage7-smoke-backtest")
    stage7_smoke.add_argument("--filter-results", required=True)
    stage7_smoke.add_argument("--execution-results", required=True)
    stage7_smoke.add_argument("--sizing-candidates", required=True)
    stage7_smoke.add_argument("--output-dir", required=True)
    stage7_smoke.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_expansion = subparsers.add_parser("lr-expansion-diagnostics")
    lr_expansion.add_argument("--filter-results", required=True)
    lr_expansion.add_argument("--execution-results", required=True)
    lr_expansion.add_argument("--sizing-candidates", required=True)
    lr_expansion.add_argument("--output-dir", required=True)
    lr_expansion.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_attempt = subparsers.add_parser("lr-attempt-proposal")
    lr_attempt.add_argument("--filter-results", required=True)
    lr_attempt.add_argument("--execution-results", required=True)
    lr_attempt.add_argument("--sizing-candidates", required=True)
    lr_attempt.add_argument("--output-dir", required=True)
    lr_attempt.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_structure = subparsers.add_parser("lr-structure-source-proposal")
    lr_structure.add_argument("--filter-results", required=True)
    lr_structure.add_argument("--execution-results", required=True)
    lr_structure.add_argument("--sizing-candidates", required=True)
    lr_structure.add_argument("--output-dir", required=True)
    lr_structure.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_exit = subparsers.add_parser("lr-exit-profile-proposal")
    lr_exit.add_argument("--filter-results", required=True)
    lr_exit.add_argument("--execution-results", required=True)
    lr_exit.add_argument("--sizing-candidates", required=True)
    lr_exit.add_argument("--output-dir", required=True)
    lr_exit.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_sizing = subparsers.add_parser("lr-sizing-proposal")
    lr_sizing.add_argument("--filter-results", required=True)
    lr_sizing.add_argument("--execution-results", required=True)
    lr_sizing.add_argument("--sizing-candidates", required=True)
    lr_sizing.add_argument("--output-dir", required=True)
    lr_sizing.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_combined = subparsers.add_parser("lr-combined-candidate-proposal")
    lr_combined.add_argument("--filter-results", required=True)
    lr_combined.add_argument("--execution-results", required=True)
    lr_combined.add_argument("--sizing-candidates", required=True)
    lr_combined.add_argument("--output-dir", required=True)
    lr_combined.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_combined_fix = subparsers.add_parser("lr-combined-candidate-fix")
    lr_combined_fix.add_argument("--filter-results", required=True)
    lr_combined_fix.add_argument("--execution-results", required=True)
    lr_combined_fix.add_argument("--sizing-candidates", required=True)
    lr_combined_fix.add_argument("--output-dir", required=True)
    lr_combined_fix.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_causal_rebuild = subparsers.add_parser("lr-causal-rebuild")
    lr_causal_rebuild.add_argument(
        "--stage",
        choices=("anatomy", "multitimeframe-events"),
        default="anatomy",
    )
    lr_causal_rebuild.add_argument("--mode", choices=("development",), default="development")
    lr_causal_rebuild.add_argument("--preset", default="configs/presets/btc_eth_swap_lr_formal.toml")
    lr_causal_rebuild.add_argument("--db", default="storage/history.duckdb")
    lr_causal_rebuild.add_argument(
        "--output-root",
        default="storage/research_runs/liquidity_reversal/causal_rebuild_v1",
    )
    lr_causal_rebuild.add_argument("--start", default="2020-12-31")
    lr_causal_rebuild.add_argument("--end", default="2024-11-30")
    lr_causal_rebuild.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_robustness = subparsers.add_parser("lr-robustness-validation")
    lr_robustness.add_argument("--artifact-dir", required=True)
    lr_robustness.add_argument("--output-dir", required=True)
    lr_robustness.add_argument("--monte-carlo-seeds", type=int, default=1000)
    lr_robustness.add_argument("--format", choices=("json", "markdown"), default="json")

    lr_robustness_fix = subparsers.add_parser("lr-robustness-fix")
    lr_robustness_fix.add_argument("--artifact-dir", required=True)
    lr_robustness_fix.add_argument("--output-dir", required=True)
    lr_robustness_fix.add_argument("--monte-carlo-seeds", type=int, default=1000)
    lr_robustness_fix.add_argument("--format", choices=("json", "markdown"), default="json")

    flow_audit = subparsers.add_parser("flow-audit")
    flow_audit.add_argument("--strategy", required=True)
    flow_source = flow_audit.add_mutually_exclusive_group(required=True)
    flow_source.add_argument("--artifact-dir")
    flow_source.add_argument("--artifact-index")
    flow_audit.add_argument("--registry")
    flow_audit.add_argument("--output-dir", required=True)
    flow_audit.add_argument("--format", choices=("json", "markdown"), default="json")

    full_audit = subparsers.add_parser("full-audit")
    full_audit.add_argument("--strategy", required=True)
    full_audit.add_argument("--registry")
    full_audit.add_argument("--artifact-dir", required=True)
    full_audit.add_argument("--output-dir", required=True)
    full_audit.add_argument("--format", choices=("json", "markdown"), default="json")

    lineage_repair = subparsers.add_parser("lineage-repair")
    lineage_repair.add_argument("--strategy", required=True)
    lineage_repair.add_argument("--combined-artifact-dir", required=True)
    lineage_repair.add_argument("--filter-results", required=True)
    lineage_repair.add_argument("--execution-results", required=True)
    lineage_repair.add_argument("--output-dir", required=True)
    lineage_repair.add_argument("--format", choices=("json", "markdown"), default="json")

    root_cause = subparsers.add_parser("root-cause-investigation")
    root_cause.add_argument("--strategy", required=True)
    root_cause.add_argument("--artifact-root", default="storage/backtest_cache")
    root_cause.add_argument("--output-dir", required=True)
    root_cause.add_argument("--format", choices=("json", "markdown"), default="json")

    args = parser.parse_args(argv)
    if args.command == "regression-summary":
        summary = build_regression_summary(args.strategy, Path(args.baseline_dir))
        if args.format == "markdown":
            print(summary.as_markdown())
        else:
            print(summary.as_json())
        return 0
    if args.command == "legacy-list":
        print(legacy_mapping_report(strategy=args.strategy))
        return 0
    if args.command == "legacy-run":
        print(legacy_run_preview(args.name, legacy_args=args.legacy_args))
        return 0
    if args.command == "artifact-summary":
        summary = build_artifact_summary(args.strategy, Path(args.artifact_dir))
        if args.format == "markdown":
            print(summary.as_markdown())
        else:
            print(summary.as_json())
        return 0
    if args.command == "aggregate-summaries":
        from research_pipeline.core.reports.aggregation_report import render_aggregation_report

        result = build_aggregation_result(args.strategy, Path(args.summary_dir))
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "aggregation_result.json").write_text(result.as_json(), encoding="utf-8")
            (output_dir / "aggregation_report.md").write_text(
                render_aggregation_report(result), encoding="utf-8"
            )
        if args.format == "markdown":
            print(render_aggregation_report(result))
        else:
            print(result.as_json())
        return 0
    if args.command == "smoke-plan":
        aggregation = _load_aggregation_arg(args.strategy, Path(args.aggregation_result))
        plan = build_smoke_plan(aggregation)
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "smoke_plan.json").write_text(plan.as_json(), encoding="utf-8")
            (output_dir / "smoke_plan.md").write_text(plan.as_markdown(), encoding="utf-8")
        if args.format == "markdown":
            print(plan.as_markdown())
        else:
            print(plan.as_json())
        return 0
    if args.command == "edge-analysis":
        from research_pipeline.core.reports.edge_report import render_edge_report

        analysis = build_edge_analysis(
            args.strategy,
            summary_dir=Path(args.summary_dir) if args.summary_dir else None,
            aggregation_result_path=Path(args.aggregation_result)
            if args.aggregation_result
            else None,
        )
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "edge_analysis_result.json").write_text(
                analysis.as_json(), encoding="utf-8"
            )
            (output_dir / "edge_analysis_report.md").write_text(
                render_edge_report(analysis), encoding="utf-8"
            )
        if args.format == "markdown":
            print(render_edge_report(analysis))
        else:
            print(analysis.as_json())
        return 0
    if args.command == "sizing-diagnostics":
        from research_pipeline.core.reports.sizing_report import render_sizing_report

        diagnostics = build_sizing_diagnostics(
            args.strategy,
            summary_dir=Path(args.summary_dir) if args.summary_dir else None,
            artifact_index_path=Path(args.artifact_index) if args.artifact_index else None,
        )
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "sizing_diagnostics_result.json").write_text(
                diagnostics.as_json(), encoding="utf-8"
            )
            (output_dir / "sizing_diagnostics_report.md").write_text(
                render_sizing_report(diagnostics), encoding="utf-8"
            )
        if args.format == "markdown":
            print(render_sizing_report(diagnostics))
        else:
            print(diagnostics.as_json())
        return 0
    if args.command == "build-artifact-index":
        index, paths = build_and_write_artifact_index(
            artifact_dir=Path(args.artifact_dir),
            output_dir=Path(args.output_dir),
            strategy=args.strategy,
            stage=args.stage,
            window=args.window,
            source_command=args.source_command,
            legacy_source=args.legacy_source,
        )
        print(
            json.dumps(
                {
                    "index_id": index.index_id,
                    "artifact_count": len(index.records),
                    "artifact_index": str(paths["json"]),
                    "artifact_index_md": str(paths["markdown"]),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "register-run":
        run = register_research_run(
            registry_path=Path(args.registry),
            artifact_index_path=Path(args.artifact_index),
            strategy=args.strategy,
            stage=args.stage,
            window=args.window,
            source_command=args.source_command,
            baseline_ref=args.baseline_ref,
            notes=args.notes,
            tags=args.tag,
            proposal_only=args.proposal_only,
            formal_conclusion_enabled=args.formal_conclusion_enabled,
            readonly=args.readonly,
            legacy_source=args.legacy_source,
        )
        print(json.dumps(run.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "list-artifacts":
        print(
            json.dumps(
                list_artifacts_from_index(
                    Path(args.artifact_index),
                    strategy=args.strategy,
                    stage=args.stage,
                    window=args.window,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "validate-artifacts":
        result = validate_artifact_index(Path(args.artifact_index))
        print(result.as_json())
        return 0 if result.passed else 1
    if args.command == "list-runs":
        print(
            json.dumps(
                list_runs_from_registry(Path(args.registry)),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "list-strategies":
        print(
            json.dumps(
                default_strategy_registry().list_strategies(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "strategy-dry-run":
        result = run_strategy_dry_run(
            strategy=args.strategy,
            dataset_window=args.dataset_window,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "run_manifest.md").read_text(encoding="utf-8") if args.output_dir else json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(result.as_json())
        return 0
    if args.command == "strategy-research-validation":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / args.strategy / "research_validation"
        )
        result = run_strategy_research_validation(
            strategy=args.strategy,
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            output_root=output_root,
            cost_tiers=tuple(args.cost_tier or ("base", "stress", "harsh")),
            max_entry_windows=args.max_entry_windows,
            allow_expansion=args.allow_expansion,
            force=args.force,
        )
        if args.format == "markdown":
            print((Path(result.run_root) / "strategy_research_validation_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "strategy-expansion-diagnostics":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / args.strategy / "expansion_diagnostics"
        )
        result = run_strategy_expansion_diagnostics(
            strategy=args.strategy,
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            output_root=output_root,
            max_entry_windows=args.max_entry_windows,
            run_top_variants=args.run_top_variants,
            cost_tiers=tuple(args.cost_tier or ("base",)),
            baseline_artifact_dir=Path(args.baseline_artifact_dir) if args.baseline_artifact_dir else None,
            reuse_baseline=args.reuse_baseline,
            variant_only=args.variant_only,
            variants=tuple(args.variant or ()),
            force=args.force,
        )
        if args.format == "markdown":
            print((Path(result.run_root) / "strategy_expansion_diagnostics_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "tc-family-trade-count-expansion":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / "trend_continuation_family" / "trade_count_variant_expansion"
        )
        result = run_tc_family_trade_count_expansion(
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            output_root=output_root,
            max_entry_windows=args.max_entry_windows,
            cost_tiers=tuple(args.cost_tier or ("base", "stress", "harsh")),
            chunk_size=args.chunk_size,
        )
        if args.format == "markdown":
            print(Path(result.report_path).read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "tc-family-profit-execution-optimization":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / "trend_continuation_family" / "profit_execution_optimization"
        )
        result = run_tc_family_profit_execution_optimization(
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            baseline_run_root=Path(args.baseline_run_root),
            output_root=output_root,
            cost_tiers=tuple(args.cost_tier or ("base", "stress", "harsh")),
        )
        if args.format == "markdown":
            print(Path(result.report_path).read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "tc-family-cost-aware-exit-target":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / "trend_continuation_family" / "cost_aware_exit_target"
        )
        result = run_tc_family_cost_aware_exit_target(
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            baseline_run_root=Path(args.baseline_run_root),
            output_root=output_root,
            cost_tiers=tuple(args.cost_tier or ("base", "stress", "harsh")),
        )
        if args.format == "markdown":
            print(Path(result.report_path).read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "tc-family-cost-aware-refinement-with-trend-state":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / "trend_continuation_family" / "cost_aware_refinement_with_trend_state"
        )
        result = run_tc_family_cost_aware_refinement_with_trend_state(
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            baseline_run_root=Path(args.baseline_run_root),
            output_root=output_root,
            cost_tiers=tuple(args.cost_tier or ("base", "stress", "harsh")),
        )
        if args.format == "markdown":
            print(Path(result.report_path).read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "tc-family-final-regime-aware-refinement":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        output_root = (
            Path(args.output_root)
            if args.output_root
            else Path("storage") / "research_runs" / "trend_continuation_family" / "final_regime_aware_refinement"
        )
        result = run_tc_family_final_regime_aware_refinement(
            repository=repository,
            preset=preset,
            dataset_window=args.dataset_window,
            baseline_run_root=Path(args.baseline_run_root),
            output_root=output_root,
            cost_tiers=tuple(args.cost_tier or ("base", "stress", "harsh")),
        )
        if args.format == "markdown":
            print(Path(result.report_path).read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "strategy-summary":
        summary = build_strategy_summary(args.strategy, summary_dir=Path(args.summary_dir))
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "strategy_summary.json").write_text(summary.as_json(), encoding="utf-8")
            (output_dir / "strategy_summary.md").write_text(summary.as_markdown(), encoding="utf-8")
        if args.format == "markdown":
            print(summary.as_markdown())
        else:
            print(summary.as_json())
        return 0
    if args.command == "strategy-regression-check":
        result = run_strategy_regression_check(
            args.strategy,
            baseline_dir=Path(args.baseline_dir),
            summary_dir=Path(args.summary_dir),
        )
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "strategy_regression_check.json").write_text(
                result.as_json(), encoding="utf-8"
            )
            (output_dir / "strategy_regression_check.md").write_text(
                result.as_markdown(), encoding="utf-8"
            )
        if args.format == "markdown":
            print(result.as_markdown())
        else:
            print(result.as_json())
        return 0
    if args.command == "stage7-smoke-backtest":
        result = run_stage7_smoke_backtest(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "stage7_smoke_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-expansion-diagnostics":
        result = run_lr_expansion_diagnostics(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_expansion_diagnostic_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-attempt-proposal":
        result = run_lr_attempt_proposal(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_attempt_proposal_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-structure-source-proposal":
        result = run_lr_structure_source_proposal(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_structure_source_proposal_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-exit-profile-proposal":
        result = run_lr_exit_profile_proposal(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_exit_profile_proposal_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-sizing-proposal":
        result = run_lr_sizing_proposal(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_sizing_proposal_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-causal-rebuild":
        preset = load_backtest_preset(args.preset)
        repository = DuckDbCandleRepository(Path(args.db))
        if args.stage == "multitimeframe-events":
            result = run_lr_multitimeframe_event_research(
                repository=repository,
                preset=preset,
                output_root=Path(args.output_root),
                start_date=args.start,
                end_date=args.end,
            )
            report_name = "lr_multitimeframe_vpa_causal_event_report.md"
        else:
            result = run_lr_causal_anatomy(
                repository=repository,
                preset=preset,
                output_root=Path(args.output_root),
                start_date=args.start,
                end_date=args.end,
            )
            report_name = "lr_causal_anatomy_report.md"
        if args.format == "markdown":
            print((Path(result.run_root) / report_name).read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-combined-candidate-proposal":
        result = run_lr_combined_candidate_proposal(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_combined_candidate_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-combined-candidate-fix":
        result = run_lr_combined_candidate_fix(
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            sizing_candidates=Path(args.sizing_candidates),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_combined_candidate_fix_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-robustness-validation":
        result = run_lr_robustness_validation(
            artifact_dir=Path(args.artifact_dir),
            output_dir=Path(args.output_dir),
            monte_carlo_seeds=args.monte_carlo_seeds,
        )
        if args.format == "markdown":
            print(
                (Path(args.output_dir) / "lr_robustness_validation_report.md").read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(result.as_json())
        return 0
    if args.command == "lr-robustness-fix":
        result = run_lr_robustness_fix(
            artifact_dir=Path(args.artifact_dir),
            output_dir=Path(args.output_dir),
            monte_carlo_seeds=args.monte_carlo_seeds,
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "lr_robustness_fix_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "flow-audit":
        result = run_research_flow_audit(
            strategy=args.strategy,
            artifact_dir=Path(args.artifact_dir) if args.artifact_dir else None,
            artifact_index=Path(args.artifact_index) if args.artifact_index else None,
            registry=Path(args.registry) if args.registry else None,
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "research_flow_audit_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "full-audit":
        result = run_full_pipeline_audit(
            strategy=args.strategy,
            artifact_dir=Path(args.artifact_dir),
            registry=Path(args.registry) if args.registry else None,
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "full_pipeline_audit_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "lineage-repair":
        result = run_lineage_repair(
            strategy=args.strategy,
            combined_artifact_dir=Path(args.combined_artifact_dir),
            filter_results=Path(args.filter_results),
            execution_results=Path(args.execution_results),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "lineage_repair_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    if args.command == "root-cause-investigation":
        result = run_root_cause_investigation(
            strategy=args.strategy,
            artifact_root=Path(args.artifact_root),
            output_dir=Path(args.output_dir),
        )
        if args.format == "markdown":
            print((Path(args.output_dir) / "root_cause_report.md").read_text(encoding="utf-8"))
        else:
            print(result.as_json())
        return 0
    return 2


def _load_aggregation_arg(strategy: str, path: Path) -> AggregationResult:
    if path.is_dir():
        return build_aggregation_result(strategy, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return AggregationResult(**data)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
