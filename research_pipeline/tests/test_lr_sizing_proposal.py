import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_sizing_proposal import run_lr_sizing_proposal


from research_pipeline.tests.fixture_paths import FILTER_RESULTS, EXECUTION_RESULTS, SIZING_CANDIDATES


class LRSizingProposalTest(unittest.TestCase):
    def test_sizing_proposal_keeps_policies_proposal_only_and_audits_time_cut(self) -> None:
        result = run_lr_sizing_proposal(
            filter_results=FILTER_RESULTS,
            execution_results=EXECUTION_RESULTS,
            sizing_candidates=SIZING_CANDIDATES,
            output_dir=None,
        )
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertFalse(payload["formal_conclusion_enabled"])
        self.assertTrue(payload["notional_capped_proposal_only"])
        self.assertTrue(payload["quality_aware_sizing_proposal_only"])
        self.assertIn(payload["primary_decision"], {"A", "B", "C", "D", "E", "F"})
        self.assertIn(payload["next_pr_recommendation"], {"PR 11G Combined LR Candidate Proposal", "PR 11F-fix"})

        policies = {row["sizing_policy"] for row in payload["grouped_rows"]}
        self.assertTrue(
            {
                "current_risk_based_sizing",
                "notional_capped_risk_based",
                "quality_aware_capped_sizing",
            }.issubset(policies)
        )
        exit_contexts = {row["exit_context"] for row in payload["grouped_rows"]}
        self.assertEqual(exit_contexts, {"fixed_2R_time_cut", "dynamic_time_cut"})
        tiers = {row["quality_tier"] for row in payload["tier_rows"]}
        self.assertTrue({"Tier A", "Tier B", "Tier C", "Tier D"}.issubset(tiers))

        for row in payload["grouped_rows"]:
            self.assertIn("profitable_time_cut_ratio", row)
            self.assertIn("loss_time_cut_ratio", row)
            self.assertIn("bad_time_cut_ratio", row)
            self.assertIn("giveback_from_MFE_avg", row)
            self.assertFalse(row["formal_conclusion_enabled"])

    def test_sizing_proposal_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-sizing-proposal",
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
                "lr_sizing_proposal_result.json",
                "lr_sizing_proposal_report.md",
                "lr_sizing_policy_rows.jsonl",
                "lr_sizing_tier_rows.jsonl",
                "lr_sizing_grouped_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads(
                (output_dir / "lr_sizing_proposal_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["proposal_only"])
            self.assertTrue(payload["quality_aware_sizing_proposal_only"])


if __name__ == "__main__":
    unittest.main()
