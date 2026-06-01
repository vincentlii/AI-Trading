import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_exit_profile_proposal import run_lr_exit_profile_proposal


FILTER_RESULTS = Path("storage/backtest_cache/minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_filter_results.jsonl")
EXECUTION_RESULTS = Path("storage/backtest_cache/minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_execution_results.jsonl")
SIZING_CANDIDATES = Path("storage/backtest_cache/stage6e_sizing/10000w/stage6c_sizing_candidates.csv")


class LRExitProfileProposalTest(unittest.TestCase):
    def test_exit_profile_proposal_keeps_shadow_profiles_proposal_only(self) -> None:
        result = run_lr_exit_profile_proposal(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertTrue(payload["exit_profiles_shadow_only"])
        self.assertEqual(payload["baseline_exit_profile"], "baseline_fixed_2r_time_cut")
        self.assertIn(payload["primary_decision"], {"A", "B", "C", "D", "E", "F"})
        self.assertIn(payload["next_pr_recommendation"], {"PR 11F Quality-aware Sizing Proposal", "PR 11E-fix"})

        setup_names = {row["setup_name"] for row in payload["grouped_rows"]}
        self.assertTrue(
            {
                "recent_swing_attempt_1_reclaim",
                "recent_swing_attempt_4_displacement",
                "Session_HL_attempt_4_displacement",
                "Session_HL_attempt_3_choch_mss",
                "recent_swing_attempt_3_choch_mss",
            }.issubset(setup_names)
        )
        profiles = {row["exit_profile"] for row in payload["grouped_rows"]}
        self.assertTrue(
            {
                "baseline_fixed_2r_time_cut",
                "conservative_1_2r_full",
                "conservative_1_5r_full",
                "partial_1_2r_structure_target",
                "partial_1_5r_structure_target",
                "structure_target_only",
                "runner_displacement",
                "dynamic_time_cut",
            }.issubset(profiles)
        )
        self.assertTrue(
            all(row["same_bar_ambiguous_count"] == 0 for row in payload["grouped_rows"])
        )
        self.assertTrue(
            all(row["liquidation_event_count"] == 0 for row in payload["grouped_rows"])
        )

    def test_exit_profile_proposal_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-exit-profile-proposal",
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
                "lr_exit_profile_proposal_result.json",
                "lr_exit_profile_proposal_report.md",
                "lr_exit_profile_rows.jsonl",
                "lr_exit_profile_grouped_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads(
                (output_dir / "lr_exit_profile_proposal_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertTrue(payload["exit_profiles_shadow_only"])


if __name__ == "__main__":
    unittest.main()
