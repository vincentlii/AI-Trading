import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class SizingDiagnosticsRunnerTest(unittest.TestCase):
    def test_cli_writes_sizing_result_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "sizing-diagnostics",
                        "--strategy",
                        "liquidity_reversal",
                        "--summary-dir",
                        str(SUMMARY_DIR),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            result_path = output_dir / "sizing_diagnostics_result.json"
            report_path = output_dir / "sizing_diagnostics_report.md"
            self.assertTrue(result_path.exists())
            self.assertTrue(report_path.exists())
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["proposal_only"])
            self.assertEqual(
                payload["models"]["notional_capped_risk_based"]["capped_proposal"][
                    "capped_proposal_approved"
                ],
                3400,
            )

    def test_cli_can_read_key_metrics_from_artifact_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            index = build_index_for_directory(
                SUMMARY_DIR,
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
            )
            paths = write_artifact_index(index, output_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "sizing-diagnostics",
                        "--strategy",
                        "liquidity_reversal",
                        "--artifact-index",
                        str(paths["json"]),
                        "--output-dir",
                        str(output_dir / "sizing"),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(
                (output_dir / "sizing" / "sizing_diagnostics_result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["models"]["notional_capped_risk_based"]["notional_cap"]["notional_cap_hit_count"], 5092)


if __name__ == "__main__":
    unittest.main()
