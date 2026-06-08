from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.reports.tc_family_final_regime_aware_refinement import (
    write_tc_family_final_regime_aware_refinement_report,
)
from research_pipeline.runners.tc_family_final_regime_aware_refinement import (
    FINAL_REGIME_VARIANT_IDS,
    build_regime_diagnostic_summary,
    select_final_regime_decision,
)


class TcFamilyFinalRegimeAwareRefinementTests(unittest.TestCase):
    def test_declares_exactly_three_performance_variants(self) -> None:
        self.assertEqual(
            FINAL_REGIME_VARIANT_IDS,
            (
                "bp_shallow_regime_diagnostic_no_filter_v1",
                "bp_shallow_regime_adaptive_exit_v1",
                "bp_shallow_regime_cost_gate_v1",
            ),
        )

    def test_regime_diagnostic_summary_uses_closed_trade_rows_only(self) -> None:
        summary = build_regime_diagnostic_summary(
            [
                {"row_type": "closed_trade", "cost_tier": "base", "trend_state_at_entry": "RANGE", "net_R": 0.4, "asset": "BTC", "profile": "B", "direction": "long", "mfe_R": 0.8, "mae_R": 0.1},
                {"row_type": "closed_trade", "cost_tier": "harsh", "trend_state_at_entry": "RANGE", "net_R": 0.2, "asset": "BTC", "profile": "B", "direction": "long", "mfe_R": 0.8, "mae_R": 0.1},
                {"row_type": "diagnostic_only", "trend_state_at_entry": "RANGE", "net_R": 99.0},
                {"row_type": "summary_row", "trend_state_at_entry": "MEAN_REVERTING_TRANSITION", "net_R": 99.0},
            ]
        )

        self.assertEqual(summary["RANGE"]["closed"], 1)
        self.assertEqual(summary["RANGE"]["base_net_R_avg"], 0.4)
        self.assertEqual(summary["RANGE"]["harsh_net_R_avg"], 0.2)
        self.assertEqual(summary["RANGE"]["asset_split"], {"BTC": 1})
        self.assertNotIn("MEAN_REVERTING_TRANSITION", summary)

    def test_decision_a_requires_harsh_positive_and_audit_pass(self) -> None:
        decision = select_final_regime_decision(
            {
                "bp_shallow_regime_cost_gate_v1": {
                    "closed_trades": 360,
                    "base_net_R_avg": 0.05,
                    "stress_net_R_avg": 0.04,
                    "harsh_net_R_avg": 0.016,
                    "median_R": 0.01,
                    "PF": 1.3,
                    "net_R_avg_excluding_top_1": 0.04,
                    "net_R_avg_excluding_top_2": 0.03,
                    "positive_walk_forward_windows": 4,
                    "full_audit_gate": "passed",
                    "no_lookahead": "passed",
                    "metric_recompute": "passed",
                    "single_dimension_concentration": False,
                    "uses_direct_regime_filter": False,
                }
            },
            baseline_summary={"harsh_net_R_avg": -0.001},
        )

        self.assertTrue(decision.startswith("A."))

    def test_decision_c_when_regime_rules_underperform_baseline(self) -> None:
        decision = select_final_regime_decision(
            {
                "bp_shallow_regime_adaptive_exit_v1": {"closed_trades": 416, "harsh_net_R_avg": -0.02},
                "bp_shallow_regime_cost_gate_v1": {"closed_trades": 330, "harsh_net_R_avg": -0.01},
            },
            baseline_summary={"harsh_net_R_avg": -0.001},
        )

        self.assertTrue(decision.startswith("C."))

    def test_report_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_tc_family_final_regime_aware_refinement_report(
                output_dir=Path(temp_dir),
                payload={
                    "run_id": "fixture",
                    "decision": "B. Regime-aware refinement improved edge but still not enough; keep diagnostic only.",
                    "constraints": ["proposal-only"],
                    "baseline_summary": {"closed_trades": 1},
                    "variant_summaries": {"bp_shallow_regime_cost_gate_v1": {"closed_trades": 1}},
                    "regime_diagnostic_summary": {"RANGE": {"closed": 1}},
                    "ce_shallow_comparison": {"closed_trades": 1},
                    "artifact_paths": [],
                    "known_limitations": ["fixture"],
                },
            )
            text = path.read_text(encoding="utf-8-sig")

        self.assertIn("# TC Family Final Regime-Aware Refinement Report", text)
        self.assertIn("## 4. Regime Diagnostic Summary", text)
        self.assertIn("## 7. Regime Adaptive Exit Analysis", text)
        self.assertIn("## 8. Regime Cost Gate Analysis", text)
        self.assertIn("## 14. Reproducibility Notes", text)


if __name__ == "__main__":
    unittest.main()
