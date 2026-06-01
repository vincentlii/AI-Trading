import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.artifact_summary import build_artifact_summary


BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class LiquidityReversalArtifactSummaryTest(unittest.TestCase):
    def test_normalizer_builds_research_run_summary_from_pr1_artifacts(self) -> None:
        summary = build_artifact_summary("liquidity_reversal", BASELINE_DIR)
        payload = summary.as_dict()

        self.assertEqual(payload["strategy"], "liquidity_reversal")
        self.assertEqual(payload["window"], "10000w")
        self.assertEqual(payload["metrics"]["fresh_candidates"], 5652)
        self.assertEqual(payload["metrics"]["formal_approved"], 417)
        self.assertEqual(payload["metrics"]["proposal_approved"], 3400)
        self.assertEqual(payload["metrics"]["closed_trades"], 417)
        self.assertEqual(payload["smoke"]["selected_combos"], ["CHOCH true", "displacement_after_reclaim"])
        self.assertTrue(payload["smoke"]["proposal_only"])
        self.assertFalse(payload["smoke"]["formal_conclusion_enabled"])

        displacement = {row["combo_name"]: row for row in payload["combos"]}["displacement_after_reclaim"]
        self.assertEqual(displacement["closed_trades"], 137)
        self.assertAlmostEqual(displacement["MFE_R_avg"], 1.043551147771528)
        self.assertAlmostEqual(displacement["MFE_ge_0_5"], 0.781021897810219)
        self.assertAlmostEqual(displacement["MFE_ge_1_0"], 0.44525547445255476)
        self.assertAlmostEqual(displacement["time_cut_exit_rate"], 0.2116788321167883)

    def test_artifact_summary_cli_outputs_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "artifact-summary",
                    "--strategy",
                    "liquidity_reversal",
                    "--artifact-dir",
                    str(BASELINE_DIR),
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["metrics"]["closed_trades"], 417)


if __name__ == "__main__":
    unittest.main()
