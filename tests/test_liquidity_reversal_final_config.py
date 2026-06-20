import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_CONFIG = ROOT / "configs" / "strategies" / "liquidity_reversal.yaml"
FINAL_BASELINE = ROOT / "storage" / "research_runs" / "liquidity_reversal" / "final" / "final_regression_baseline.json"


class LiquidityReversalFinalConfigTest(unittest.TestCase):
    def test_untrusted_candidate_is_stopped_after_causal_rebuild(self) -> None:
        text = FINAL_CONFIG.read_text(encoding="utf-8")

        self.assertIn("strategy: liquidity_reversal", text)
        self.assertIn("config_version: research_stopped_2026_06_21", text)
        self.assertIn("status: research_stopped", text)
        self.assertIn("stop_reason: no_robust_positive_execution_edge", text)
        self.assertIn("holdout_accessed: false", text)
        self.assertIn("formalized_candidate: none", text)
        self.assertIn("historical_candidate: restricted_variant_b", text)
        self.assertIn("live_trading_enabled: false", text)
        self.assertEqual(text.count("enabled: true"), 0)
        self.assertIn("profile_scope: C_only", text)
        self.assertIn("diagnostic_profiles: [B]", text)
        self.assertIn("portfolio_heat_cap: 0.05", text)
        self.assertIn("unrestricted_variant_b: false", text)
        self.assertIn("full_original_family: false", text)
        self.assertIn("tier3: false", text)
        self.assertIn("pdh_pdl: diagnostic_only", text)
        self.assertIn("eqh_eql: diagnostic_only", text)

    def test_historical_regression_baseline_remains_read_only(self) -> None:
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
