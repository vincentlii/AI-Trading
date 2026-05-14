import unittest

from trading_system.indicators.regime import (
    average_true_range,
    directional_movement_index,
    exponential_moving_average,
    ttm_squeeze_on,
)


class ExtendedRegimeIndicatorTests(unittest.TestCase):
    def test_exponential_moving_average_uses_standard_recursive_smoothing(self):
        self.assertAlmostEqual(exponential_moving_average([1, 2, 3, 4, 5], period=3), 4.0625)

    def test_average_true_range_includes_gap_distance(self):
        highs = [10.0, 11.0, 15.0]
        lows = [9.0, 10.0, 14.0]
        closes = [9.5, 10.5, 14.5]

        self.assertAlmostEqual(average_true_range(highs, lows, closes, period=2), 3.0)

    def test_directional_movement_index_identifies_bullish_trend(self):
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        lows = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0]
        closes = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5]

        dmi = directional_movement_index(highs, lows, closes, period=3)

        self.assertGreater(dmi.plus_di, dmi.minus_di)
        self.assertGreater(dmi.adx, 0.0)

    def test_ttm_squeeze_returns_true_for_low_volatility_sequence(self):
        closes = [100.0] * 21
        highs = [100.1] * 21
        lows = [99.9] * 21

        self.assertTrue(ttm_squeeze_on(highs, lows, closes, period=20))

    def test_price_sequences_must_have_matching_lengths(self):
        with self.assertRaisesRegex(ValueError, "same length"):
            average_true_range([1.0, 2.0], [1.0], [1.0, 2.0], period=1)

    def test_period_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "period must be positive"):
            exponential_moving_average([1.0, 2.0], period=0)


if __name__ == "__main__":
    unittest.main()
