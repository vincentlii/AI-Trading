import unittest
from pathlib import Path

from research_pipeline.core.metrics.baseline import load_baseline_metrics
from research_pipeline.runners.regression_summary import build_regression_summary


BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class RegressionBaselineLoaderTest(unittest.TestCase):
    def test_loader_reads_pr1_key_metrics(self) -> None:
        baseline = load_baseline_metrics(BASELINE_DIR)

        self.assertEqual(baseline.strategy, "liquidity_reversal")
        self.assertEqual(baseline.window, "10000w")
        self.assertEqual(baseline.counts["fresh_candidates"], 5652)
        self.assertEqual(baseline.selected_smoke_combos, ["CHOCH true", "displacement_after_reclaim"])

    def test_regression_summary_outputs_json_and_markdown_payloads(self) -> None:
        summary = build_regression_summary("liquidity_reversal", BASELINE_DIR)

        self.assertEqual(summary.as_dict()["counts"]["closed_trades"], 417)
        self.assertEqual(summary.as_dict()["displacement_after_reclaim"]["closed_trades"], 137)
        self.assertIn("displacement_after_reclaim", summary.as_markdown())


if __name__ == "__main__":
    unittest.main()
