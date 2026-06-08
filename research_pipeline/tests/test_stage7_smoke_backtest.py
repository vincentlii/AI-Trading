import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.stage7_smoke_backtest import run_stage7_smoke_backtest


from research_pipeline.tests.fixture_paths import FILTER_RESULTS, EXECUTION_RESULTS, SIZING_CANDIDATES


class Stage7SmokeBacktestTest(unittest.TestCase):
    def test_stage7_smoke_outputs_required_cost_tiers_and_boundaries(self) -> None:
        result = run_stage7_smoke_backtest(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertEqual(payload["combos"], ["CHOCH true", "displacement_after_reclaim"])
        self.assertEqual(payload["cost_tiers"], ["base", "stress", "harsh"])
        self.assertIn(payload["final_conclusion"], {"A", "B", "C", "D", "E", "F"})
        self.assertIn("PR 11B", payload["expansion_readiness"]["next_scope"])

        rows = payload["grouped_rows"]
        keys = {
            (row["combo"], row["sizing_model"], row["cost_tier"])
            for row in rows
            if row["asset"] == "ALL" and row["profile"] == "ALL" and row["direction"] == "ALL"
        }
        self.assertIn(("CHOCH true", "current_risk_based_sizing", "base"), keys)
        self.assertIn(("CHOCH true", "current_risk_based_sizing", "stress"), keys)
        self.assertIn(("CHOCH true", "current_risk_based_sizing", "harsh"), keys)
        self.assertIn(("displacement_after_reclaim", "notional_capped_risk_based", "base"), keys)

    def test_stage7_smoke_cli_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "stage7-smoke-backtest",
                        "--filter-results",
                        str(FILTER_RESULTS),
                        "--execution-results",
                        str(EXECUTION_RESULTS),
                        "--sizing-candidates",
                        str(SIZING_CANDIDATES),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            for name in (
                "stage7_smoke_result.json",
                "stage7_smoke_report.md",
                "stage7_smoke_grouped_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads((output_dir / "stage7_smoke_result.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["proposal_only"])
            self.assertFalse(payload["formal_conclusion_enabled"])


if __name__ == "__main__":
    unittest.main()
