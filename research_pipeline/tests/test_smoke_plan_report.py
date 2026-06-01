import unittest
import tempfile
import io
from contextlib import redirect_stdout
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.aggregate_summaries import build_aggregation_result
from research_pipeline.runners.smoke_plan import build_smoke_plan


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class SmokePlanReportTest(unittest.TestCase):
    def test_smoke_plan_is_proposal_only_and_selects_frozen_combos(self) -> None:
        aggregation = build_aggregation_result("liquidity_reversal", SUMMARY_DIR)
        plan = build_smoke_plan(aggregation)
        payload = plan.as_dict()

        self.assertEqual(payload["selected_combos"], ["CHOCH true", "displacement_after_reclaim"])
        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertIn("base", payload["cost_tiers"])
        self.assertIn("Do not formalize capped sizing", payload["forbidden_actions"])
        self.assertTrue(payload["source_aggregation_hash"])
        self.assertIn("displacement_after_reclaim", plan.as_markdown())

    def test_cli_can_write_aggregation_and_smoke_plan_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                aggregate_exit = main(
                    [
                        "aggregate-summaries",
                        "--strategy",
                        "liquidity_reversal",
                        "--summary-dir",
                        str(SUMMARY_DIR),
                        "--output-dir",
                        str(temp_path),
                    ]
                )
                smoke_exit = main(
                    [
                        "smoke-plan",
                        "--strategy",
                        "liquidity_reversal",
                        "--aggregation-result",
                        str(temp_path / "aggregation_result.json"),
                        "--output-dir",
                        str(temp_path),
                    ]
                )
            self.assertEqual(aggregate_exit, 0)
            self.assertEqual(smoke_exit, 0)
            self.assertTrue((temp_path / "aggregation_result.json").exists())
            self.assertTrue((temp_path / "aggregation_report.md").exists())
            self.assertTrue((temp_path / "smoke_plan.json").exists())
            self.assertTrue((temp_path / "smoke_plan.md").exists())


if __name__ == "__main__":
    unittest.main()
