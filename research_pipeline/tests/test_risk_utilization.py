import unittest

from research_pipeline.core.sizing.risk_utilization import (
    classify_actual_risk_pct,
    risk_utilization_ratio,
)


class RiskUtilizationTest(unittest.TestCase):
    def test_risk_utilization_ratio_uses_actual_over_target_risk(self) -> None:
        self.assertAlmostEqual(risk_utilization_ratio(0.0015, 0.005), 0.3)

    def test_actual_risk_pct_tiers_are_stable(self) -> None:
        self.assertEqual(classify_actual_risk_pct(0.0009), "tiny_risk")
        self.assertEqual(classify_actual_risk_pct(0.001), "low_risk")
        self.assertEqual(classify_actual_risk_pct(0.002), "medium_risk")
        self.assertEqual(classify_actual_risk_pct(0.0035), "near_target_risk")


if __name__ == "__main__":
    unittest.main()
