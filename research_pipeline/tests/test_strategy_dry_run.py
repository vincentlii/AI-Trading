import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.strategy_dry_run import run_strategy_dry_run


class StrategyDryRunTest(unittest.TestCase):
    def test_trend_continuation_dry_run_declares_generic_audit_contract(self) -> None:
        result = run_strategy_dry_run(
            strategy="trend_continuation",
            dataset_window="fixture_window",
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertTrue(payload["dry_run_only"])
        self.assertEqual(payload["audit_input"]["audit_profile"]["performance_row_type"], "closed_trade")
        self.assertIn("proposal_candidate", payload["audit_input"]["audit_profile"]["excluded_performance_row_types"])
        self.assertTrue(all(row["passed"] for row in payload["checks"]))

    def test_strategy_dry_run_cli_writes_manifest_without_formalizing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "strategy-dry-run",
                        "--strategy",
                        "trend_continuation",
                        "--dataset-window",
                        "fixture_window",
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "strategy_dry_run_result.json").exists())
            self.assertTrue((output_dir / "run_manifest.json").exists())
            payload = json.loads((output_dir / "strategy_dry_run_result.json").read_text(encoding="utf-8"))
            self.assertFalse(payload["formal_conclusion_enabled"])
            self.assertEqual(payload["manifest"]["strategy"], "trend_continuation")


if __name__ == "__main__":
    unittest.main()
