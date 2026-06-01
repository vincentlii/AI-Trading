import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.strategy_regression_check import run_strategy_regression_check


BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class LiquidityReversalAdapterRegressionCheckTest(unittest.TestCase):
    def test_regression_check_reproduces_frozen_lr_metrics(self) -> None:
        result = run_strategy_regression_check(
            "liquidity_reversal",
            baseline_dir=BASELINE_DIR,
            summary_dir=BASELINE_DIR,
        )
        payload = result.as_dict()

        self.assertTrue(payload["passed"])
        self.assertEqual(payload["checks"]["fresh_candidates"]["actual"], 5652)
        self.assertEqual(payload["checks"]["formal_approved"]["actual"], 417)
        self.assertEqual(payload["checks"]["proposal_approved"]["actual"], 3400)
        self.assertEqual(payload["checks"]["closed_trades"]["actual"], 417)
        self.assertEqual(payload["checks"]["smoke_ready_combos"]["actual"], ["CHOCH true", "displacement_after_reclaim"])
        self.assertAlmostEqual(
            payload["checks"]["displacement_MFE_R_avg"]["actual"],
            1.043551147771528,
        )
        self.assertAlmostEqual(
            payload["checks"]["notional_cap_hit_ratio"]["actual"],
            0.9009200283085633,
        )
        self.assertAlmostEqual(
            payload["checks"]["actual_risk_pct_after_cap_p50"]["actual"],
            0.0017564422157157668,
        )
        self.assertAlmostEqual(
            payload["checks"]["risk_utilization_p50"]["actual"],
            0.35128844314315333,
        )

    def test_strategy_regression_check_cli_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "strategy-regression-check",
                        "--strategy",
                        "liquidity_reversal",
                        "--baseline-dir",
                        str(BASELINE_DIR),
                        "--summary-dir",
                        str(BASELINE_DIR),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(
                (output_dir / "strategy_regression_check.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["passed"])
            self.assertTrue((output_dir / "strategy_regression_check.md").exists())


if __name__ == "__main__":
    unittest.main()
