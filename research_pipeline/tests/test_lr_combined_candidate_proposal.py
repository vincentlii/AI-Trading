import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_combined_candidate_proposal import (
    run_lr_combined_candidate_proposal,
)


FILTER_RESULTS = Path("storage/backtest_cache/minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_filter_results.jsonl")
EXECUTION_RESULTS = Path("storage/backtest_cache/minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_execution_results.jsonl")
SIZING_CANDIDATES = Path("storage/backtest_cache/stage6e_sizing/10000w/stage6c_sizing_candidates.csv")


class LRCombinedCandidateProposalTest(unittest.TestCase):
    def test_combined_candidate_proposal_is_proposal_only_and_deduplicated(self) -> None:
        result = run_lr_combined_candidate_proposal(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertTrue(payload["all_combined_candidates_proposal_only"])
        self.assertTrue(payload["dynamic_time_cut_proposal_only"])
        self.assertTrue(payload["quality_aware_capped_sizing_proposal_only"])
        self.assertEqual(payload["duplicate_event_count"], 0)
        self.assertIn(payload["primary_decision"], {"A", "B", "C", "D", "E", "F"})
        self.assertIn(payload["next_pr_recommendation"], {"PR 11H Robustness Validation", "PR 11G-fix"})

        combo_names = {row["combo_name"] for row in payload["combo_rows"]}
        self.assertTrue(
            {
                "T1_session_hl_attempt4_fixed_current",
                "T1_session_hl_attempt4_dynamic_quality",
                "T1_recent_swing_attempt4_dynamic_quality",
                "T2_session_hl_attempt3_dynamic_quality",
                "T2_recent_swing_attempt3_dynamic_quality",
                "T3_recent_swing_attempt4_fixed_current",
                "T3_rolling_range_attempt4_dynamic_quality",
                "T3_session_hl_attempt4_conservative_current",
            }.issubset(combo_names)
        )
        portfolio_rows = [row for row in payload["portfolio_rows"] if row["cost_tier"] == "base"]
        self.assertTrue(portfolio_rows)
        self.assertTrue(all(row["overlapping_event_count"] >= 0 for row in portfolio_rows))

    def test_combined_candidate_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-combined-candidate-proposal",
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
                "lr_combined_candidate_result.json",
                "lr_combined_candidate_report.md",
                "lr_combined_combo_rows.jsonl",
                "lr_combined_event_selection_rows.jsonl",
                "lr_combined_grouped_rows.jsonl",
                "lr_combined_portfolio_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads(
                (output_dir / "lr_combined_candidate_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertTrue(payload["all_combined_candidates_proposal_only"])


if __name__ == "__main__":
    unittest.main()
