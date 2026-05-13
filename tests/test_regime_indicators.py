import unittest

from trading_system.indicators.regime import (
    HIGH_SIGNAL_TO_NOISE_TREND,
    MEAN_REVERTING_TRANSITION,
    RANDOM_WALK_CHAOS,
    choppiness_index,
    classify_regime,
    kaufman_efficiency_ratio,
    true_range,
)


class RegimeIndicatorTests(unittest.TestCase):
    def test_true_range_uses_largest_intrabar_or_gap_distance(self):
        self.assertEqual(true_range(12.0, 9.0, 10.0), 3.0)
        self.assertEqual(true_range(12.0, 11.0, 9.5), 2.5)
        self.assertEqual(true_range(9.5, 8.0, 11.0), 3.0)

    def test_trending_sequence_has_high_efficiency_low_choppiness_and_trend_regime(self):
        closes = [float(price) for price in range(100, 115)]
        highs = [close + 0.1 for close in closes]
        lows = [close - 0.1 for close in closes]

        er = kaufman_efficiency_ratio(closes)
        chop = choppiness_index(highs, lows, closes, period=14)

        self.assertEqual(er, 1.0)
        self.assertLess(chop, 38.2)
        self.assertEqual(classify_regime(er, chop), HIGH_SIGNAL_TO_NOISE_TREND)

    def test_noisy_sequence_has_low_efficiency_high_choppiness_and_random_walk_regime(self):
        closes = [100.0, 101.0] * 8
        highs = [101.0 for _ in closes]
        lows = [100.0 for _ in closes]

        er = kaufman_efficiency_ratio(closes)
        chop = choppiness_index(highs, lows, closes, period=14)

        self.assertLessEqual(er, 0.3)
        self.assertGreaterEqual(chop, 61.8)
        self.assertEqual(classify_regime(er, chop), RANDOM_WALK_CHAOS)

    def test_flat_sequence_avoids_division_by_zero_and_stays_transition(self):
        closes = [100.0] * 15
        highs = [100.0] * 15
        lows = [100.0] * 15

        self.assertEqual(kaufman_efficiency_ratio(closes), 0.0)
        self.assertEqual(choppiness_index(highs, lows, closes, period=14), 0.0)
        self.assertEqual(classify_regime(0.0, 0.0), MEAN_REVERTING_TRANSITION)

    def test_classify_regime_uses_explicit_threshold_boundaries(self):
        self.assertEqual(classify_regime(0.6, 38.2), HIGH_SIGNAL_TO_NOISE_TREND)
        self.assertEqual(classify_regime(0.3, 61.8), RANDOM_WALK_CHAOS)
        self.assertEqual(classify_regime(0.45, 50.0), MEAN_REVERTING_TRANSITION)


if __name__ == "__main__":
    unittest.main()
