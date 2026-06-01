import unittest
from pathlib import Path

from research_pipeline.core.reports.edge_report import render_edge_report
from research_pipeline.runners.edge_analysis import build_edge_analysis


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class EdgeReportReadonlyTest(unittest.TestCase):
    def test_edge_report_mentions_readonly_boundary_and_top_combo(self) -> None:
        analysis = build_edge_analysis("liquidity_reversal", summary_dir=SUMMARY_DIR)
        report = render_edge_report(analysis)

        self.assertIn("Read-only", report)
        self.assertIn("displacement_after_reclaim", report)
        self.assertIn("CHOCH true", report)


if __name__ == "__main__":
    unittest.main()
