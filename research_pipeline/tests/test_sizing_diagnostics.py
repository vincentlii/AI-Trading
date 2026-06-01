import unittest
from pathlib import Path

from research_pipeline.runners.sizing_diagnostics import build_sizing_diagnostics


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class SizingDiagnosticsTest(unittest.TestCase):
    def test_reads_key_metrics_and_preserves_capped_proposal_metrics(self) -> None:
        result = build_sizing_diagnostics("liquidity_reversal", summary_dir=SUMMARY_DIR)
        payload = result.as_dict()

        self.assertTrue(payload["proposal_only"])
        self.assertEqual(payload["strategy"], "liquidity_reversal")
        self.assertEqual(payload["window"], "10000w")
        self.assertEqual(payload["fresh_candidates"], 5652)
        self.assertEqual(payload["formal_approved"], 417)
        self.assertEqual(payload["proposal_approved"], 3400)

        capped = payload["models"]["notional_capped_risk_based"]
        self.assertEqual(capped["capped_proposal"]["capped_proposal_approved"], 3400)
        self.assertEqual(capped["notional_cap"]["notional_cap_hit_count"], 5092)
        self.assertAlmostEqual(
            capped["capped_proposal"]["actual_risk_pct_after_cap_p50"],
            0.0017564422157157668,
        )
        self.assertAlmostEqual(
            capped["risk_based"]["risk_utilization_p50"],
            0.35128844314315333,
        )
        self.assertIn("required_notional_to_cap_ratio_p50", capped["missing_fields"])

    def test_missing_fields_are_reported_without_inventing_values(self) -> None:
        result = build_sizing_diagnostics("liquidity_reversal", summary_dir=SUMMARY_DIR)
        current = result.as_dict()["models"]["current_risk_based_sizing"]

        self.assertIn("required_notional_to_cap_ratio_p50", current["missing_fields"])
        self.assertIsNone(current["notional_cap"]["required_notional_to_cap_ratio_p50"])


if __name__ == "__main__":
    unittest.main()
