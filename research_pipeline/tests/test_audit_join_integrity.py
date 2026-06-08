import unittest
from pathlib import Path

from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit


from research_pipeline.tests.fixture_paths import COMBINED_FIX_DIR as ARTIFACT_DIR


class AuditJoinIntegrityTest(unittest.TestCase):
    def test_recommended_rows_without_execution_identity_are_invalid_for_robustness(self) -> None:
        result = run_full_pipeline_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            registry=None,
            output_dir=None,
        )
        variant = next(row for row in result.as_dict()["join_integrity_rows"] if row["scope"] == "Variant B - Tier 1 + Positive Tier 2")

        self.assertEqual(variant["closed_count"], 42)
        self.assertEqual(variant["missing_trade_id_count"], 42)
        self.assertEqual(variant["invalid_for_robustness_count"], 42)


if __name__ == "__main__":
    unittest.main()
