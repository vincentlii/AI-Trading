import unittest
from pathlib import Path

from research_pipeline.runners.research_flow_audit import run_research_flow_audit


ARTIFACT_DIR = Path("storage/backtest_cache/lr_combined_fix_pr11g")


class ResearchFlowJoinAuditTest(unittest.TestCase):
    def test_join_audit_flags_unmapped_proposal_rows_without_counting_performance(self) -> None:
        result = run_research_flow_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            artifact_index=None,
            registry=None,
            output_dir=None,
        )
        payload = result.as_dict()

        join_rows = payload["join_audit_rows"]
        dynamic = next(row for row in join_rows if row["scope"] == "T1_session_hl_attempt4_dynamic_quality")
        self.assertEqual(dynamic["selected_without_closed_count"], 440)
        self.assertEqual(dynamic["proposal_only_unexecuted_count"], 440)
        self.assertFalse(dynamic["fix_required"])

        variant_b = next(row for row in join_rows if row["scope"] == "Variant B - Tier 1 + Positive Tier 2")
        self.assertEqual(variant_b["closed_count"], 198)
        self.assertGreater(variant_b["selected_without_closed_count"], 0)
        self.assertFalse(variant_b["performance_includes_unclosed_rows"])


if __name__ == "__main__":
    unittest.main()
