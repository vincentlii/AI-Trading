from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.analytics.execution_path import (
    compare_retained_removed_rows,
    enrich_execution_path_rows,
    summarize_execution_path_rows,
)
from research_pipeline.core.reports.tc_family_cost_aware_exit_target import (
    write_tc_family_cost_aware_exit_target_report,
)
from research_pipeline.runners.tc_family_cost_aware_exit_target import (
    COST_AWARE_VARIANT_IDS,
    select_cost_aware_exit_target_decision,
)


def _closed(**overrides):
    row = {
        "row_type": "closed_trade",
        "candidate_id": "c1",
        "variant_id": "bp_shallow_cost_quality_v1",
        "cost_tier": "base",
        "net_R": -0.1,
        "gross_R": 0.1,
        "mfe_R": 0.6,
        "mae_R": 0.2,
        "bars_to_mfe": 4,
        "bars_to_mae": 2,
        "holding_bars": 20,
        "fee_cost": 1.0,
        "slippage_cost": 0.2,
        "actual_risk_after_cap": 100.0,
        "exit_reason": "time_exit",
    }
    row.update(overrides)
    return row


class TcFamilyCostAwareExitTargetTests(unittest.TestCase):
    def test_declares_exactly_three_bounded_variants(self) -> None:
        self.assertEqual(
            COST_AWARE_VARIANT_IDS,
            (
                "bp_shallow_micro_profit_capture_v1",
                "bp_shallow_momentum_decay_time_stop_v1",
                "bp_shallow_cost_aware_admission_v2",
            ),
        )

    def test_path_summary_reports_micro_mfe_and_never_reached_half_r(self) -> None:
        summary = summarize_execution_path_rows(
            enrich_execution_path_rows(
                [
                    _closed(candidate_id="micro", net_R=-0.1, gross_R=0.1, mfe_R=0.45),
                    _closed(candidate_id="half", net_R=0.1, gross_R=0.2, mfe_R=0.55),
                    {"row_type": "diagnostic_only", "mfe_R": 9.0, "net_R": 9.0},
                ]
            )
        )

        self.assertEqual(summary["closed_trades"], 2)
        self.assertEqual(summary["MFE_ge_0_4R"], 2)
        self.assertEqual(summary["MFE_ge_0_5_final_le_0"], 0)
        self.assertEqual(summary["never_reached_0_5R_MFE"], 1)

    def test_retained_removed_comparison_uses_closed_trade_rows_only(self) -> None:
        rows = enrich_execution_path_rows(
            [
                _closed(candidate_id="kept", net_R=0.2, gross_R=0.3, mfe_R=0.7, retained_by_admission=True),
                _closed(candidate_id="removed", net_R=-0.2, gross_R=0.0, mfe_R=0.3, removed_by_admission=True),
                {"row_type": "summary_row", "retained_by_admission": True, "net_R": 100.0},
            ]
        )

        comparison = compare_retained_removed_rows(rows)

        self.assertEqual(comparison["retained_count"], 1)
        self.assertEqual(comparison["removed_count"], 1)
        self.assertGreater(comparison["retained_avg_R"], comparison["removed_avg_R"])

    def test_decision_requires_all_cost_tiers_for_validation_prep(self) -> None:
        decision = select_cost_aware_exit_target_decision(
            {
                "bp_shallow_micro_profit_capture_v1": {
                    "closed_trades": 420,
                    "base_net_R_avg": 0.06,
                    "stress_net_R_avg": 0.04,
                    "harsh_net_R_avg": 0.035,
                    "median_R": 0.01,
                    "PF": 1.2,
                    "net_R_avg_excluding_top_1": 0.04,
                    "net_R_avg_excluding_top_2": 0.03,
                    "positive_walk_forward_windows": 4,
                    "full_audit_gate": "passed",
                    "no_lookahead": "passed",
                    "metric_recompute": "passed",
                    "single_dimension_concentration": False,
                    "path_diagnostics": {"profit_giveback_R_avg": 0.2, "cost_flipped_to_loss_share": 0.1},
                }
            }
        )

        self.assertTrue(decision.startswith("A."))

    def test_report_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_tc_family_cost_aware_exit_target_report(
                output_dir=Path(temp_dir),
                payload={
                    "run_id": "fixture",
                    "decision": "E. No variant improves enough; pause TC family and move to simpler baseline later.",
                    "constraints": ["proposal-only"],
                    "baseline_summary": {"closed_trades": 1},
                    "variant_summaries": {"bp_shallow_micro_profit_capture_v1": {"closed_trades": 1}},
                    "ce_shallow_comparison": {"closed_trades": 1},
                    "artifact_paths": [],
                    "known_limitations": ["fixture"],
                },
            )
            text = path.read_text(encoding="utf-8-sig")

        self.assertIn("# TC Family Cost-Aware Exit Target Report", text)
        self.assertIn("## 4. Baseline Failure Mechanism", text)
        self.assertIn("## 12. CE Shallow Diagnostic Comparison", text)
        self.assertIn("bp_shallow_micro_profit_capture_v1", text)


if __name__ == "__main__":
    unittest.main()
