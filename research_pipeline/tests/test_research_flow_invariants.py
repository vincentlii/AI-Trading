import unittest
from pathlib import Path

from research_pipeline.runners.research_flow_audit import run_research_flow_audit


ARTIFACT_DIR = Path("storage/backtest_cache/lr_combined_fix_pr11g")


class ResearchFlowInvariantAuditTest(unittest.TestCase):
    def test_invariants_block_missing_closed_trade_execution_identity(self) -> None:
        result = run_research_flow_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            artifact_index=None,
            registry=None,
            output_dir=None,
        )
        payload = result.as_dict()
        invariant = next(
            row for row in payload["invariant_rows"] if row["invariant_name"] == "closed_trade_has_execution_identity"
        )

        self.assertFalse(invariant["passed"])
        self.assertTrue(invariant["blocking"])
        self.assertEqual(payload["primary_decision"], "D")
        self.assertEqual(payload["next_pr_recommendation"], "PR 11G-QA-fix")


if __name__ == "__main__":
    unittest.main()
