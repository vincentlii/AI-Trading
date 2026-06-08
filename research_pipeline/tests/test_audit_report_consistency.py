import unittest
from research_pipeline.core.audit.report_consistency import build_report_consistency_rows
from research_pipeline.tests.fixture_paths import COMBINED_FIX_DIR


class AuditReportConsistencyTest(unittest.TestCase):
    def test_report_consistency_lists_supported_report_types(self) -> None:
        rows = build_report_consistency_rows(COMBINED_FIX_DIR)
        names = {row["report_type"] for row in rows}

        self.assertIn("combined candidate report", names)
        self.assertIn("robustness report", names)


if __name__ == "__main__":
    unittest.main()
