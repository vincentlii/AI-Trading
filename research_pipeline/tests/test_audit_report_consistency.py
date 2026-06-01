import unittest
from pathlib import Path

from research_pipeline.core.audit.report_consistency import build_report_consistency_rows


class AuditReportConsistencyTest(unittest.TestCase):
    def test_report_consistency_lists_supported_report_types(self) -> None:
        rows = build_report_consistency_rows(Path("storage/backtest_cache/lr_combined_fix_pr11g"))
        names = {row["report_type"] for row in rows}

        self.assertIn("combined candidate report", names)
        self.assertIn("robustness report", names)


if __name__ == "__main__":
    unittest.main()
