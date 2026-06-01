import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.strategy_summary import build_strategy_summary


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class LiquidityReversalAdapterReadonlyPipelineTest(unittest.TestCase):
    def test_strategy_summary_uses_adapter_and_existing_artifacts(self) -> None:
        summary = build_strategy_summary("liquidity_reversal", summary_dir=SUMMARY_DIR)
        payload = summary.as_dict()

        self.assertTrue(payload["adapter_metadata"]["proposal_only"])
        self.assertFalse(payload["adapter_metadata"]["formal_conclusion_enabled"])
        self.assertEqual(payload["baseline_metrics"]["fresh_candidates"], 5652)
        self.assertEqual(payload["smoke_ready_combos"], ["CHOCH true", "displacement_after_reclaim"])
        self.assertEqual(payload["primary_combo"], "displacement_after_reclaim")
        self.assertEqual(payload["edge_summary"]["top_combo"], "displacement_after_reclaim")
        self.assertEqual(payload["sizing_summary"]["notional_capped_risk_based"]["notional_cap_hit_count"], 5092)
        self.assertEqual(payload["missing_artifacts"], [])

    def test_strategy_summary_reports_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = build_strategy_summary("liquidity_reversal", summary_dir=Path(temp_dir))

        self.assertIn("key_metrics.json", summary.as_dict()["missing_artifacts"])

    def test_list_strategies_and_strategy_summary_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["list-strategies"])

        self.assertEqual(exit_code, 0)
        self.assertIn("liquidity_reversal", stdout.getvalue())

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "strategy-summary",
                        "--strategy",
                        "liquidity_reversal",
                        "--summary-dir",
                        str(SUMMARY_DIR),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads((output_dir / "strategy_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["primary_combo"], "displacement_after_reclaim")
            self.assertTrue((output_dir / "strategy_summary.md").exists())


if __name__ == "__main__":
    unittest.main()
