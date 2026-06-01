import unittest

from research_pipeline.core.sizing.notional_cap import (
    classify_required_notional_to_cap_ratio,
    notional_cap_hit_ratio,
)


class NotionalCapDiagnosticsTest(unittest.TestCase):
    def test_notional_cap_hit_ratio_uses_candidate_count(self) -> None:
        self.assertAlmostEqual(notional_cap_hit_ratio(5092, 5652), 0.9009200283085633)

    def test_required_notional_to_cap_tiers_are_stable(self) -> None:
        self.assertEqual(classify_required_notional_to_cap_ratio(1.5), "near_cap")
        self.assertEqual(classify_required_notional_to_cap_ratio(2.2), "moderate_above_cap")
        self.assertEqual(classify_required_notional_to_cap_ratio(4.9), "far_above_cap")
        self.assertEqual(classify_required_notional_to_cap_ratio(5.1), "extreme_above_cap")


if __name__ == "__main__":
    unittest.main()
