from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.reports.tc_family_cost_aware_refinement_with_trend_state import (
    write_tc_family_cost_aware_refinement_with_trend_state_report,
)
from research_pipeline.runners.tc_family_cost_aware_refinement_with_trend_state import (
    REFINEMENT_VARIANT_IDS,
    build_trend_state_lineage_diagnostics,
    select_refinement_decision,
)


class TcFamilyCostAwareRefinementWithTrendStateTests(unittest.TestCase):
    def test_declares_exactly_three_performance_variants(self) -> None:
        self.assertEqual(
            REFINEMENT_VARIANT_IDS,
            (
                "bp_shallow_cost_aware_admission_v3",
                "bp_shallow_cost_aware_partial_capture_v1",
                "bp_shallow_cost_aware_momentum_failure_exit_v1",
            ),
        )

    def test_trend_state_lineage_uses_closed_trade_entry_state(self) -> None:
        diagnostics = build_trend_state_lineage_diagnostics(
            candidate_rows=[
                {"row_type": "proposal_candidate", "trend_state_at_entry": "TREND"},
                {"row_type": "proposal_candidate", "trend_state_at_entry": "RANGE"},
            ],
            filter_rows=[
                {"row_type": "proposal_candidate", "trend_state_at_entry": "TREND"},
                {"row_type": "proposal_candidate", "trend_state_at_entry": "RANGE"},
            ],
            closed_rows=[
                {"row_type": "closed_trade", "trend_state_at_entry": "TREND"},
                {"row_type": "closed_trade", "trend_state_at_entry": "MEAN_REVERTING_TRANSITION"},
                {"row_type": "summary_row", "trend_state_at_entry": "UNKNOWN"},
            ],
        )

        self.assertEqual(diagnostics["closed_trade_rows"], 2)
        self.assertEqual(diagnostics["closed_trade_unknown_share"], 0.0)
        self.assertEqual(diagnostics["closed_trade_trend_state_split"]["TREND"], 1)
        self.assertTrue(diagnostics["closed_trade_has_trend_state"])

    def test_decision_a_requires_trend_state_coverage(self) -> None:
        decision = select_refinement_decision(
            {
                "bp_shallow_cost_aware_admission_v3": {
                    "closed_trades": 360,
                    "base_net_R_avg": 0.05,
                    "stress_net_R_avg": 0.04,
                    "harsh_net_R_avg": 0.021,
                    "median_R": 0.01,
                    "PF": 1.25,
                    "net_R_avg_excluding_top_1": 0.04,
                    "net_R_avg_excluding_top_2": 0.03,
                    "positive_walk_forward_windows": 4,
                    "full_audit_gate": "passed",
                    "no_lookahead": "passed",
                    "metric_recompute": "passed",
                    "single_dimension_concentration": False,
                    "trend_state_lineage": {"closed_trade_unknown_share": 0.04},
                }
            },
            baseline_summary={"harsh_net_R_avg": -0.004},
        )

        self.assertTrue(decision.startswith("A."))

    def test_decision_d_when_v2_remains_best_and_exits_fail(self) -> None:
        decision = select_refinement_decision(
            {
                "bp_shallow_cost_aware_admission_v3": {"closed_trades": 360, "harsh_net_R_avg": -0.02},
                "bp_shallow_cost_aware_partial_capture_v1": {"closed_trades": 420, "harsh_net_R_avg": -0.03},
                "bp_shallow_cost_aware_momentum_failure_exit_v1": {"closed_trades": 420, "harsh_net_R_avg": -0.03},
            },
            baseline_summary={"harsh_net_R_avg": -0.004},
        )

        self.assertTrue(decision.startswith("D."))

    def test_report_contains_trend_state_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_tc_family_cost_aware_refinement_with_trend_state_report(
                output_dir=Path(temp_dir),
                payload={
                    "run_id": "fixture",
                    "decision": "C. Cost-aware mechanism helps but harsh remains too thin; keep diagnostic only.",
                    "constraints": ["proposal-only"],
                    "baseline_summary": {"closed_trades": 1},
                    "variant_summaries": {"bp_shallow_cost_aware_admission_v3": {"closed_trades": 1}},
                    "trend_state_diagnostics": {"closed_trade_unknown_share": 0.0},
                    "ce_shallow_comparison": {"closed_trades": 1},
                    "artifact_paths": [],
                    "known_limitations": ["fixture"],
                },
            )
            text = path.read_text(encoding="utf-8-sig")

        self.assertIn("# TC Family Cost-Aware Refinement With Trend State Report", text)
        self.assertIn("## 4. Trend State Lineage Fix", text)
        self.assertIn("## 11. Trend State Diagnostics", text)
        self.assertIn("bp_shallow_cost_aware_admission_v3", text)


if __name__ == "__main__":
    unittest.main()
