import unittest
from pathlib import Path

from research_pipeline.core.reports.readers import read_markdown_report


BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ReportReaderTest(unittest.TestCase):
    def test_reads_markdown_raw_text_and_section_titles(self) -> None:
        report = read_markdown_report(BASELINE_DIR / "stage7_smoke_plan_snapshot.md")

        self.assertIn("Stage 7 Smoke", report.raw_text)
        self.assertIn("Required Outputs", report.section_titles)
        self.assertIn("Grouped Preview", report.section_titles)


if __name__ == "__main__":
    unittest.main()
