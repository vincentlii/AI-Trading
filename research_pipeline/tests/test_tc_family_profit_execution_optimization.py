from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.analytics.execution_path import (
    enrich_execution_path_rows,
    summarize_execution_path_rows,
)
from research_pipeline.core.reports.tc_family_profit_and_execution_optimization import (
    write_tc_family_profit_execution_report,
)
from research_pipeline.runners.tc_family_profit_execution_optimization import (
    OPTIMIZATION_VARIANT_IDS,
    BASELINE_VARIANT_IDS,
    select_profit_execution_decision,
)


def _closed(**overrides):
    row = {
        "row_type": "closed_trade",
        "candidate_id": "c1",
        "variant_id": "bp_shallow_momentum_capped_risk_v3",
        "cost_tier": "base",
        "net_R": -0.2,
        "gross_R": 0.1,
        "mfe_R": 1.2,
        "mae_R": 0.3,
        "bars_to_mfe": 3,
        "bars_to_mae": 1,
        "holding_bars": 8,
        "fee_cost": 1.0,
        "slippage_cost": 0.2,
        "funding_cost": 0.0,
        "actual_risk_after_cap": 100.0,
        "exit_reason": "time_exit",
    }
    row.update(overrides)
    return row


class TcFamilyProfitExecutionOptimizationTests(unittest.TestCase):
    def test_execution_path_diagnostics_classify_good_signal_bad_exit(self) -> None:
        rows = enrich_execution_path_rows(
            [
                _closed(net_R=-0.2, gross_R=0.1, mfe_R=1.2, mae_R=0.3),
                {"row_type": "diagnostic_only", "net_R": 99.0, "mfe_R": 99.0},
            ]
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["exit_efficiency"], -0.2 / 1.2)
        self.assertAlmostEqual(row["profit_giveback_R"], 1.4)
        self.assertTrue(row["positive_MFE_but_final_loss"])
        self.assertTrue(row["final_loss_after_1R_MFE"])
        self.assertTrue(row["good_signal_bad_exit_candidate"])

    def test_execution_path_summary_uses_closed_trade_rows_only(self) -> None:
        summary = summarize_execution_path_rows(
            enrich_execution_path_rows(
                [
                    _closed(candidate_id="winner", net_R=0.4, gross_R=0.5, mfe_R=0.8, mae_R=0.2),
                    _closed(candidate_id="loser", net_R=-0.1, gross_R=0.1, mfe_R=0.6, mae_R=0.5),
                    {"row_type": "summary_row", "net_R": 100.0, "mfe_R": 100.0},
                ]
            )
        )

        self.assertEqual(summary["closed_trades"], 2)
        self.assertEqual(summary["positive_MFE_but_final_loss"], 1)
        self.assertEqual(summary["reached_0_5R_share"], 1.0)
        self.assertIn("MFE_R_median", summary)

    def test_declares_exact_baseline_and_optimization_variants(self) -> None:
        self.assertEqual(
            BASELINE_VARIANT_IDS,
            (
                "ce_lifecycle_native_light_confirm_v1",
                "ce_lifecycle_shallow_momentum_v1",
                "bp_shallow_momentum_capped_risk_v3",
            ),
        )
        self.assertEqual(
            OPTIMIZATION_VARIANT_IDS,
            (
                "bp_shallow_exit_efficiency_v1",
                "ce_shallow_exit_efficiency_v1",
                "bp_shallow_entry_timing_v1",
                "bp_shallow_cost_quality_v1",
            ),
        )

    def test_decision_allows_validation_prep_only_when_all_cost_tiers_are_strong(self) -> None:
        decision = select_profit_execution_decision(
            {
                "bp_shallow_exit_efficiency_v1": {
                    "closed_trades": 260,
                    "base_net_R_avg": 0.08,
                    "stress_net_R_avg": 0.06,
                    "harsh_net_R_avg": 0.04,
                    "median_R": 0.02,
                    "PF": 1.2,
                    "net_R_avg_excluding_top_1": 0.05,
                    "net_R_avg_excluding_top_2": 0.04,
                    "positive_walk_forward_windows": 4,
                    "negative_walk_forward_windows": 1,
                    "full_audit_gate": "passed",
                    "no_lookahead": "passed",
                    "metric_recompute": "passed",
                    "single_dimension_concentration": False,
                }
            }
        )

        self.assertTrue(decision.startswith("A."))

    def test_report_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_tc_family_profit_execution_report(
                output_dir=Path(temp_dir),
                payload={
                    "run_id": "fixture",
                    "decision": "E. No optimization improves enough; pause TC family.",
                    "constraints": ["proposal-only"],
                    "baseline_summaries": {"bp": {"closed_trades": 1}},
                    "optimization_summaries": {"bp_shallow_exit_efficiency_v1": {"closed_trades": 1}},
                    "artifact_paths": [],
                    "known_limitations": ["fixture"],
                },
            )
            text = path.read_text(encoding="utf-8-sig")

        self.assertIn("# TC Family Profit and Execution Optimization Report", text)
        self.assertIn("## 4. Baseline MAE/MFE Diagnostics", text)
        self.assertIn("## 13. Decision", text)
        self.assertIn("bp_shallow_exit_efficiency_v1", text)


if __name__ == "__main__":
    unittest.main()
