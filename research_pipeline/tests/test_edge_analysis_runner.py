import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_pipeline.cli.research import main


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class EdgeAnalysisRunnerTest(unittest.TestCase):
    def test_edge_analysis_cli_writes_result_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "edge-analysis",
                        "--strategy",
                        "liquidity_reversal",
                        "--summary-dir",
                        str(SUMMARY_DIR),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            result_path = output_dir / "edge_analysis_result.json"
            report_path = output_dir / "edge_analysis_report.md"
            self.assertTrue(result_path.exists())
            self.assertTrue(report_path.exists())

            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["strategy"], "liquidity_reversal")
            self.assertEqual(payload["ranked_combos"][0]["combo_name"], "displacement_after_reclaim")
            self.assertEqual(payload["combo_metrics"][0]["edge_metrics"]["closed_trades"], 137)


if __name__ == "__main__":
    unittest.main()
