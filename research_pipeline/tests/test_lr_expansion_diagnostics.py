import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_expansion_diagnostics import run_lr_expansion_diagnostics


from research_pipeline.tests.fixture_paths import FILTER_RESULTS, EXECUTION_RESULTS, SIZING_CANDIDATES


class LRExpansionDiagnosticsTest(unittest.TestCase):
    def test_expansion_diagnostics_are_proposal_only_and_diagnostic_only(self) -> None:
        result = run_lr_expansion_diagnostics(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertTrue(payload["all_new_sources_diagnostic_only"])
        self.assertTrue(payload["multiple_entry_attempts_diagnostic_only"])
        self.assertTrue(payload["exit_profiles_shadow_only"])
        self.assertTrue(payload["capped_sizing_proposal_only"])
        self.assertIn(payload["final_conclusion"], {"A", "B", "C", "D", "E", "F", "G"})

        source_names = {row["structure_source"] for row in payload["structure_rows"]}
        self.assertTrue({"PDH/PDL", "Session High/Low", "EQH/EQL"}.issubset(source_names))

        attempt_names = {row["attempt_name"] for row in payload["attempt_rows"]}
        self.assertTrue(
            {
                "attempt_1_reclaim_entry",
                "attempt_2_retest_entry",
                "attempt_3_choch_mss_entry",
                "attempt_4_displacement_entry",
                "attempt_5_fvg_ce_retest",
            }.issubset(attempt_names)
        )

        exit_profiles = {row["exit_profile"] for row in payload["exit_shadow_rows"]}
        self.assertIn("baseline_fixed_2r_time_cut", exit_profiles)
        self.assertIn("conservative_1_5r", exit_profiles)

        quality_tiers = {row["quality_tier"] for row in payload["sizing_rows"]}
        self.assertTrue({"A", "B", "C", "D"}.issubset(quality_tiers))

    def test_lr_expansion_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-expansion-diagnostics",
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
                "lr_expansion_diagnostic_result.json",
                "lr_expansion_diagnostic_report.md",
                "lr_expansion_structure_rows.jsonl",
                "lr_expansion_attempt_rows.jsonl",
                "lr_expansion_exit_shadow_rows.jsonl",
                "lr_expansion_sizing_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)

            payload = json.loads(
                (output_dir / "lr_expansion_diagnostic_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertFalse(payload["formal_conclusion_enabled"])


if __name__ == "__main__":
    unittest.main()
