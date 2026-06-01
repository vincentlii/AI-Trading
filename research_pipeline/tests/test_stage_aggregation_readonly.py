import unittest
from pathlib import Path

from research_pipeline.runners.aggregate_summaries import build_aggregation_result


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class StageAggregationReadonlyTest(unittest.TestCase):
    def test_aggregation_reproduces_stage6e_smoke_ready_combos(self) -> None:
        result = build_aggregation_result("liquidity_reversal", SUMMARY_DIR)
        payload = result.as_dict()

        self.assertEqual(payload["strategy"], "liquidity_reversal")
        self.assertEqual(payload["windows"], ["10000w", "3000w", "5000w"])
        self.assertEqual(payload["smoke_ready_combos"], ["CHOCH true", "displacement_after_reclaim"])
        self.assertIn("displacement_after_reclaim", payload["combo_metrics"])
        self.assertTrue(payload["consistency_flags"]["displacement_after_reclaim"]["multi_window_consistent"])

        displacement = payload["combo_metrics"]["displacement_after_reclaim"]["10000w"]
        self.assertEqual(displacement["closed_trades"], 137)
        self.assertAlmostEqual(displacement["MFE_R_avg"], 1.043551147771528)
        self.assertAlmostEqual(displacement["MFE_R_ge_0_5_ratio"], 0.781021897810219)
        self.assertAlmostEqual(displacement["MFE_R_ge_1_0_ratio"], 0.44525547445255476)

        self.assertNotIn("high_wick", payload["smoke_ready_combos"])
        self.assertNotIn("high_sweep_rvol + CHOCH true + high_wick", payload["smoke_ready_combos"])
        self.assertNotIn("ETH C short", payload["smoke_ready_combos"])


if __name__ == "__main__":
    unittest.main()
