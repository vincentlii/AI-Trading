import unittest
from pathlib import Path

from trading_system.reports.lr_regression_baseline import load_baseline


class LiquidityReversalRegressionBaselineTest(unittest.TestCase):
    def test_stage6e_10000w_baseline_loads_and_freezes_key_metrics(self) -> None:
        baseline_dir = (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "regression_baselines"
            / "liquidity_reversal"
            / "stage6e_10000w"
        )

        baseline = load_baseline(baseline_dir)
        metrics = baseline["key_metrics"]
        manifest = baseline["manifest"]

        self.assertEqual(manifest["strategy"], "liquidity_reversal")
        self.assertEqual(manifest["window"], "10000w")
        self.assertEqual(
            manifest["selected_stage7_smoke_combos"],
            ["CHOCH true", "displacement_after_reclaim"],
        )

        self.assertEqual(metrics["counts"]["fresh_candidates"], 5652)
        self.assertEqual(metrics["counts"]["formal_approved"], 417)
        self.assertEqual(metrics["counts"]["proposal_approved"], 3400)
        self.assertEqual(metrics["counts"]["closed_trades"], 417)

        displacement = metrics["tracked_combos"]["displacement_after_reclaim"]
        self.assertEqual(displacement["closed_trades"], 137)
        self.assertAlmostEqual(displacement["MFE_R_avg"], 1.043551147771528)
        self.assertAlmostEqual(displacement["MFE_R_ge_0_5_ratio"], 0.781021897810219)
        self.assertAlmostEqual(displacement["MFE_R_ge_1_0_ratio"], 0.44525547445255476)
        self.assertAlmostEqual(displacement["time_cut_exit_rate"], 0.2116788321167883)

        choch = metrics["tracked_combos"]["CHOCH true"]
        self.assertTrue(choch["stage7_smoke_ready"])

        capped = metrics["sizing"]["notional_capped_risk_based"]
        self.assertEqual(capped["proposal_approved"], 3400)
        self.assertEqual(capped["notional_cap_hit_count"], 5092)


if __name__ == "__main__":
    unittest.main()
