import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_CONFIG = ROOT / "configs" / "strategies" / "liquidity_reversal.yaml"
FINAL_BASELINE = ROOT / "storage" / "research_runs" / "liquidity_reversal" / "final" / "final_regression_baseline.json"


class LiquidityReversalFinalConfigTest(unittest.TestCase):
    def test_final_config_matches_pr11h_fix_candidate(self) -> None:
        text = FINAL_CONFIG.read_text(encoding="utf-8")

        self.assertIn("strategy: liquidity_reversal", text)
        self.assertIn("formalized_candidate: restricted_variant_b", text)
        self.assertIn("profile_scope: C_only", text)
        self.assertIn("diagnostic_profiles: [B]", text)
        self.assertIn("portfolio_heat_cap: 0.05", text)
        self.assertIn("unrestricted_variant_b: false", text)
        self.assertIn("full_original_family: false", text)
        self.assertIn("tier3: false", text)
        self.assertIn("pdh_pdl: diagnostic_only", text)
        self.assertIn("eqh_eql: diagnostic_only", text)

    def test_final_regression_baseline_freezes_restricted_variant_b(self) -> None:
        baseline = json.loads(FINAL_BASELINE.read_text(encoding="utf-8"))

        self.assertEqual(baseline["strategy"], "liquidity_reversal")
        self.assertEqual(baseline["final_candidate"], "restricted_variant_b")
        self.assertEqual(baseline["restricted_variant_b"]["closed"], 183)
        self.assertAlmostEqual(baseline["restricted_variant_b"]["total_R"], 85.06990218742838)
        self.assertAlmostEqual(baseline["restricted_variant_b"]["profit_factor"], 7.795271510312894)
        self.assertEqual(baseline["restricted_variant_b"]["max_concurrent_positions"], 10)
        self.assertEqual(baseline["restricted_variant_b"]["same_direction_overlap_count"], 303)
        self.assertAlmostEqual(baseline["restricted_variant_b"]["portfolio_heat_cap"], 0.05)
        self.assertEqual(baseline["full_audit"]["audit_passed"], True)
        self.assertEqual(baseline["duplicate_event_count"], 0)
        self.assertEqual(baseline["liquidation_event_count"], 0)


if __name__ == "__main__":
    unittest.main()
