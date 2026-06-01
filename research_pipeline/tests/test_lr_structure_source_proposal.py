import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_structure_source_proposal import run_lr_structure_source_proposal


FILTER_RESULTS = Path("storage/backtest_cache/minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_filter_results.jsonl")
EXECUTION_RESULTS = Path("storage/backtest_cache/minimal_lr_v0_filter_stage6e/10000w/minimal_lr_v0_execution_results.jsonl")
SIZING_CANDIDATES = Path("storage/backtest_cache/stage6e_sizing/10000w/stage6c_sizing_candidates.csv")


class LRStructureSourceProposalTest(unittest.TestCase):
    def test_structure_source_proposal_keeps_new_sources_proposal_only(self) -> None:
        result = run_lr_structure_source_proposal(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertTrue(payload["session_hl_proposal_only"])
        self.assertIn(payload["primary_decision"], {"A", "B", "C", "D", "E", "F"})
        self.assertIn(payload["next_pr_recommendation"], {"PR 11E Exit Profile Proposal", "PR 11D-fix"})

        sources = {row["structure_source"] for row in payload["level_rows"]}
        self.assertTrue(
            {"recent_swing", "rolling_range", "Session High/Low", "PDH/PDL", "EQH/EQL"}.issubset(
                sources
            )
        )
        session_rows = [
            row for row in payload["level_rows"] if row["structure_source"] == "Session High/Low"
        ]
        self.assertTrue(session_rows)
        self.assertTrue(all(row["structure_confirmed_time"] is not None for row in session_rows))
        self.assertTrue(all(row["no_lookahead_check"] in {"passed", "tag_derived"} for row in session_rows))

        grouped_keys = {
            (row["structure_source"], row["attempt_name"], row["sizing_model"], row["cost_tier"])
            for row in payload["grouped_rows"]
            if row["asset"] == "ALL"
            and row["profile"] == "ALL"
            and row["direction"] == "ALL"
            and row["session_name"] == "ALL"
        }
        self.assertIn(
            ("Session High/Low", "attempt_4_displacement_entry", "current_risk_based_sizing", "base"),
            grouped_keys,
        )
        self.assertIn(
            ("recent_swing", "attempt_1_reclaim_entry", "current_risk_based_sizing", "harsh"),
            grouped_keys,
        )

    def test_structure_source_proposal_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-structure-source-proposal",
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
                "lr_structure_source_proposal_result.json",
                "lr_structure_source_proposal_report.md",
                "lr_structure_level_rows.jsonl",
                "lr_structure_event_rows.jsonl",
                "lr_structure_candidate_rows.jsonl",
                "lr_structure_grouped_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads(
                (output_dir / "lr_structure_source_proposal_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertFalse(payload["formal_conclusion_enabled"])


if __name__ == "__main__":
    unittest.main()
