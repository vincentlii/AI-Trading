import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_combined_candidate_fix import (
    NEGATIVE_TIER2_COMBO,
    UNMAPPED_DYNAMIC_COMBO,
    run_lr_combined_candidate_fix,
)


from research_pipeline.tests.fixture_paths import FILTER_RESULTS, EXECUTION_RESULTS, SIZING_CANDIDATES


class LRCombinedCandidateFixTest(unittest.TestCase):
    def test_fix_downgrades_unmapped_and_negative_combos(self) -> None:
        result = run_lr_combined_candidate_fix(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertEqual(payload["mapping_diagnostics"]["combo_name"], UNMAPPED_DYNAMIC_COMBO)
        self.assertGreater(payload["mapping_diagnostics"]["selected_without_closed_count"], 0)
        self.assertEqual(
            payload["mapping_diagnostics"]["fix_applied"],
            "downgraded_to_diagnostic_excluded_from_main_variants",
        )
        diagnostic_names = {row["combo_name"] for row in payload["diagnostic_combos"]}
        self.assertIn(UNMAPPED_DYNAMIC_COMBO, diagnostic_names)
        self.assertIn(NEGATIVE_TIER2_COMBO, diagnostic_names)
        self.assertIn(payload["primary_decision"], {"A", "B", "C", "D", "E", "F"})
        self.assertIn(payload["next_pr_recommendation"], {"PR 11H Robustness Validation", "PR 11G-fix"})

        variant_b_rows = [
            row
            for row in payload["grouped_rows"]
            if row["variant_name"] == "Variant B - Tier 1 + Positive Tier 2"
            and row["cost_tier"] == "base"
            and row["asset"] == "ALL"
        ]
        variant_b_combos = {row["combo_name"] for row in variant_b_rows}
        self.assertNotIn(UNMAPPED_DYNAMIC_COMBO, variant_b_combos)
        self.assertNotIn(NEGATIVE_TIER2_COMBO, variant_b_combos)

    def test_fix_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-combined-candidate-fix",
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
                "lr_combined_candidate_fix_result.json",
                "lr_combined_candidate_fix_report.md",
                "lr_combined_variant_rows.jsonl",
                "lr_combined_combo_rows.jsonl",
                "lr_combined_event_selection_rows.jsonl",
                "lr_combined_unmapped_rows.jsonl",
                "lr_combined_grouped_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads(
                (output_dir / "lr_combined_candidate_fix_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertTrue(payload["quality_aware_capped_sizing_proposal_only"])


if __name__ == "__main__":
    unittest.main()
