from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.audit.no_lookahead import build_no_lookahead_rows
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.registry.strategy_registry import default_strategy_registry
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.strategy_research_validation import _diagnostic_rows, _summary_rows


class StrategyResearchValidationTests(unittest.TestCase):
    def test_summary_rows_keep_selected_without_closed_out_of_performance_metrics(self) -> None:
        filter_rows = (
            {"row_type": "filter_result", "formal_approved": True, "cost_tier": "base"},
            {"row_type": "filter_result", "formal_approved": True, "cost_tier": "base"},
        )
        closed_rows = (
            {"row_type": "closed_trade", "closed_trade": True, "cost_tier": "base", "net_R": 1.0},
        )

        summary = _summary_rows((), filter_rows, closed_rows)[0]
        diagnostics = _diagnostic_rows(filter_rows, (), closed_rows)

        self.assertEqual(summary["selected_without_closed_count"], 0)
        self.assertEqual(diagnostics[0]["approved_without_closed_count"], 1)

    def test_no_lookahead_uses_adapter_time_order_checks(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")
        row = {
            "feature_cutoff_time": 100,
            "trend_confirmed_time": 80,
            "breakout_time": 90,
            "pullback_confirmed_time": 95,
            "signal_time": 100,
            "entry_time": 101,
            "exit_time": 110,
            "bar_confirmed": True,
            "same_bar_ambiguous": False,
            "no_lookahead_safe": True,
        }

        rows = build_no_lookahead_rows(
            [row],
            time_field_checks=adapter.audit_profile().time_order_checks,
        )

        self.assertTrue(all(not item["blocking"] for item in rows), rows)
        self.assertIn("breakout_time_lte_pullback_confirmed_time", {item["check_name"] for item in rows})

    def test_breakout_pullback_no_lookahead_verifies_complete_lifecycle_order(self) -> None:
        adapter = default_strategy_registry().get("breakout_pullback")
        row = {
            "zone_confirmed_time": 80,
            "breakout_time": 90,
            "acceptance_end_time": 92,
            "pullback_start_time": 93,
            "pullback_end_time": 96,
            "relaunch_time": 98,
            "signal_time": 100,
            "entry_time": 101,
            "exit_time": 110,
            "bar_confirmed": True,
            "same_bar_ambiguous": False,
            "no_lookahead_safe": True,
        }

        rows = build_no_lookahead_rows(
            [row],
            time_field_checks=adapter.audit_profile().time_order_checks,
        )

        checks = {item["check_name"]: item for item in rows}
        expected_order_checks = {
            "zone_confirmed_time_lte_breakout_time",
            "breakout_time_lte_acceptance_end_time",
            "acceptance_end_time_lte_pullback_start_time",
            "pullback_start_time_lte_pullback_end_time",
            "pullback_end_time_lte_relaunch_time",
            "relaunch_time_lte_signal_time",
            "signal_time_lt_entry_time",
            "entry_time_lte_exit_time",
        }
        self.assertTrue(expected_order_checks.issubset(checks))
        self.assertTrue(all(not checks[name]["blocking"] for name in expected_order_checks), checks)

    def test_breakout_pullback_no_lookahead_blocks_zone_and_lifecycle_order_violations(self) -> None:
        adapter = default_strategy_registry().get("breakout_pullback")
        row = {
            "zone_confirmed_time": 91,
            "breakout_time": 90,
            "acceptance_end_time": 92,
            "pullback_start_time": 95,
            "pullback_end_time": 94,
            "relaunch_time": 98,
            "signal_time": 100,
            "entry_time": 101,
            "exit_time": 110,
            "bar_confirmed": True,
            "same_bar_ambiguous": False,
            "no_lookahead_safe": True,
        }

        rows = build_no_lookahead_rows(
            [row],
            time_field_checks=adapter.audit_profile().time_order_checks,
        )

        checks = {item["check_name"]: item for item in rows}
        self.assertTrue(checks["zone_confirmed_time_lte_breakout_time"]["blocking"])
        self.assertTrue(checks["pullback_start_time_lte_pullback_end_time"]["blocking"])

    def test_manifest_driven_full_audit_accepts_non_lr_artifacts(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            candidate_rows = [
                {
                    "row_type": "proposal_candidate",
                    "candidate_id": "tc-1",
                    "event_id": "event-1",
                    "eligible_for_performance": False,
                },
                {
                    "row_type": "proposal_candidate",
                    "candidate_id": "tc-2",
                    "event_id": "event-2",
                    "eligible_for_performance": False,
                },
            ]
            filter_rows = [
                {"candidate_id": "tc-1", "formal_approved": True, "row_type": "formal_approved"},
                {"candidate_id": "tc-2", "formal_approved": True, "row_type": "formal_approved"},
            ]
            closed_rows = [
                {
                    "row_type": "closed_trade",
                    "closed_trade": True,
                    "eligible_for_performance": True,
                    "trade_id": "trade-1",
                    "execution_id": "exec-1",
                    "candidate_id": "tc-1",
                    "event_id": "event-1",
                    "event_key": "event-1",
                    "trend_event_id": "trend-1",
                    "feature_cutoff_time": 100,
                    "trend_confirmed_time": 80,
                    "breakout_time": 90,
                    "pullback_confirmed_time": 95,
                    "signal_time": 100,
                    "entry_time": 101,
                    "exit_time": 110,
                    "bar_confirmed": True,
                    "same_bar_ambiguous": False,
                    "no_lookahead_safe": True,
                    "cost_tier": "base",
                    "net_R": 1.0,
                    "mfe_R": 1.5,
                    "mae_R": -0.2,
                    "time_cut_exit": False,
                    "loss_time_cut": False,
                    "invalid_for_robustness": False,
                },
                {
                    "row_type": "closed_trade",
                    "closed_trade": True,
                    "eligible_for_performance": True,
                    "trade_id": "trade-2",
                    "execution_id": "exec-2",
                    "candidate_id": "tc-2",
                    "event_id": "event-2",
                    "event_key": "event-2",
                    "trend_event_id": "trend-2",
                    "feature_cutoff_time": 200,
                    "trend_confirmed_time": 180,
                    "breakout_time": 190,
                    "pullback_confirmed_time": 195,
                    "signal_time": 200,
                    "entry_time": 201,
                    "exit_time": 210,
                    "bar_confirmed": True,
                    "same_bar_ambiguous": False,
                    "no_lookahead_safe": True,
                    "cost_tier": "base",
                    "net_R": -0.5,
                    "mfe_R": 0.4,
                    "mae_R": -0.8,
                    "time_cut_exit": False,
                    "loss_time_cut": False,
                    "invalid_for_robustness": False,
                },
            ]
            summary_rows = [
                {
                    "row_type": "summary_row",
                    "scope": "trend_continuation_baseline",
                    "cost_tier": "base",
                    "closed_trades": 2,
                    "net_R_avg": 0.25,
                    "total_net_R": 0.5,
                    "profit_factor": 2.0,
                    "MFE_R_avg": 0.95,
                    "MAE_R_avg": -0.5,
                    "time_cut_exit_rate": 0.0,
                    "bad_time_cut_ratio": None,
                    "duplicate_event_count": 0,
                    "selected_without_closed_count": 0,
                }
            ]
            robustness_rows = [
                {"row_type": "robustness_diagnostic", "robustness_type": "walk_forward"},
                {"row_type": "robustness_diagnostic", "robustness_type": "regime_split"},
                {"row_type": "robustness_diagnostic", "robustness_type": "exposure"},
            ]
            _write_jsonl(artifact_dir / "candidate_rows.jsonl", candidate_rows)
            _write_jsonl(artifact_dir / "filter_results_research.jsonl", filter_rows)
            _write_jsonl(artifact_dir / "closed_trade_rows.jsonl", closed_rows)
            _write_jsonl(artifact_dir / "diagnostic_rows.jsonl", [])
            _write_jsonl(artifact_dir / "summary_rows.jsonl", summary_rows)
            _write_jsonl(artifact_dir / "robustness_rows.jsonl", robustness_rows)
            (artifact_dir / "regression_baseline.json").write_text(
                json.dumps({"row_type": "regression_baseline"}, sort_keys=True),
                encoding="utf-8",
            )
            manifest = RunManifest(
                run_id="tc-fixture",
                strategy="trend_continuation",
                adapter_version=adapter.adapter_version,
                dataset_window="fixture",
                artifact_contract=adapter.artifact_contract().as_dict(),
                audit_profile=adapter.audit_profile().as_dict(),
                artifact_paths={
                    "candidate_rows": str(artifact_dir / "candidate_rows.jsonl"),
                    "filter_results": str(artifact_dir / "filter_results_research.jsonl"),
                    "closed_trade_rows": str(artifact_dir / "closed_trade_rows.jsonl"),
                    "diagnostic_rows": str(artifact_dir / "diagnostic_rows.jsonl"),
                    "summary_rows": str(artifact_dir / "summary_rows.jsonl"),
                    "robustness_rows": str(artifact_dir / "robustness_rows.jsonl"),
                    "regression_baseline": str(artifact_dir / "regression_baseline.json"),
                },
            )
            (artifact_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
            index = build_index_for_directory(
                artifact_dir,
                strategy="trend_continuation",
                stage="research_validation_fixture",
                window="fixture",
                source_command="fixture",
                config_hash="fixture",
            )
            write_artifact_index(index, artifact_dir)

            result = run_full_pipeline_audit(
                strategy="trend_continuation",
                artifact_dir=artifact_dir,
                registry=None,
                output_dir=None,
            )

        self.assertTrue(result.audit_passed, result.blocking_issues)
        self.assertFalse(result.blocking_issues)
        self.assertTrue(all(row["passed"] for row in result.metric_recompute_rows), result.metric_recompute_rows)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
