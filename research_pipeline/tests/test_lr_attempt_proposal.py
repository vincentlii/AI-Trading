import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_attempt_proposal import run_lr_attempt_proposal


from research_pipeline.tests.fixture_paths import FILTER_RESULTS, EXECUTION_RESULTS, SIZING_CANDIDATES


class LRAttemptProposalTest(unittest.TestCase):
    def test_attempt_proposal_builds_fsm_and_priority_without_formalizing(self) -> None:
        result = run_lr_attempt_proposal(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertEqual(payload["primary_attempt"], "attempt_4_displacement_entry")
        self.assertEqual(payload["secondary_attempt"], "attempt_3_choch_mss_entry")
        self.assertEqual(payload["diagnostic_only_attempts"], ["attempt_2_retest_entry", "attempt_5_fvg_ce_retest"])

        self.assertGreater(len(payload["event_rows"]), 0)
        self.assertGreater(len(payload["candidate_rows"]), 0)
        self.assertEqual(payload["duplicate_event_count"], 0)

        displacement_events = [
            row
            for row in payload["event_rows"]
            if "attempt_4_displacement_entry" in row["all_valid_attempts"]
        ]
        self.assertTrue(displacement_events)
        self.assertTrue(
            all(row["selected_attempt"] == "attempt_4_displacement_entry" for row in displacement_events)
        )

        attempt_keys = {
            (row["attempt_name"], row["sizing_model"], row["cost_tier"])
            for row in payload["grouped_rows"]
            if row["asset"] == "ALL"
            and row["profile"] == "ALL"
            and row["direction"] == "ALL"
            and row["structure_source"] == "ALL"
            and row["session_tag"] == "ALL"
        }
        self.assertIn(("attempt_1_reclaim_entry", "current_risk_based_sizing", "base"), attempt_keys)
        self.assertIn(("attempt_3_choch_mss_entry", "current_risk_based_sizing", "stress"), attempt_keys)
        self.assertIn(("attempt_4_displacement_entry", "notional_capped_risk_based", "harsh"), attempt_keys)
        self.assertIn(payload["primary_decision"], {"A", "B", "C", "D", "E", "F"})
        self.assertEqual(payload["next_pr_recommendation"], "PR 11D Structure Source Proposal")

    def test_attempt_proposal_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-attempt-proposal",
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
                "lr_attempt_proposal_result.json",
                "lr_attempt_proposal_report.md",
                "lr_attempt_event_rows.jsonl",
                "lr_attempt_candidate_rows.jsonl",
                "lr_attempt_grouped_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)

            payload = json.loads(
                (output_dir / "lr_attempt_proposal_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertFalse(payload["formal_conclusion_enabled"])


if __name__ == "__main__":
    unittest.main()
