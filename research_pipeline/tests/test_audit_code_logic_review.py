import unittest
from pathlib import Path

from research_pipeline.core.audit.code_logic_review import build_code_logic_review_rows


class AuditCodeLogicReviewTest(unittest.TestCase):
    def test_code_logic_review_detects_risky_patterns_without_high_severity(self) -> None:
        rows = build_code_logic_review_rows(Path.cwd())

        self.assertTrue(rows)
        self.assertFalse(any(row["severity"] == "high" and row["fix_required"] for row in rows))


if __name__ == "__main__":
    unittest.main()
