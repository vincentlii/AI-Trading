import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_pipeline.cli.research import main


BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ResearchCliSkeletonTest(unittest.TestCase):
    def test_regression_summary_cli_outputs_json_without_running_research_layers(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "regression-summary",
                    "--strategy",
                    "liquidity_reversal",
                    "--baseline-dir",
                    str(BASELINE_DIR),
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["counts"]["formal_approved"], 417)
        self.assertEqual(payload["displacement_after_reclaim"]["closed_trades"], 137)


if __name__ == "__main__":
    unittest.main()
