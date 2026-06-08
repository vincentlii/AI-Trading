import unittest
from pathlib import Path

from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit


from research_pipeline.tests.fixture_paths import COMBINED_FIX_DIR as ARTIFACT_DIR


class AuditInvariantsTest(unittest.TestCase):
    def test_full_audit_fails_on_execution_identity_lineage(self) -> None:
        result = run_full_pipeline_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            registry=None,
            output_dir=None,
        )

        self.assertFalse(result.audit_passed)
        self.assertEqual(result.primary_decision, "C")
        self.assertIn("PR 11G-QA-fix", result.next_pr_recommendation)


if __name__ == "__main__":
    unittest.main()
