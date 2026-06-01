import unittest
from pathlib import Path

from research_pipeline.core.reports.sizing_report import render_sizing_report
from research_pipeline.runners.sizing_diagnostics import build_sizing_diagnostics


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class SizingReportReadonlyTest(unittest.TestCase):
    def test_report_states_readonly_and_proposal_boundary(self) -> None:
        result = build_sizing_diagnostics("liquidity_reversal", summary_dir=SUMMARY_DIR)
        report = render_sizing_report(result)

        self.assertIn("Read-only", report)
        self.assertIn("proposal_only: True", report)
        self.assertIn("notional_capped_risk_based", report)
        self.assertIn("proposal approval is not formal approval", report)


if __name__ == "__main__":
    unittest.main()
