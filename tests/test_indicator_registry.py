import unittest

from trading_system.indicators import get_indicator, list_indicators


class IndicatorRegistryTests(unittest.TestCase):
    def test_regime_indicators_are_exposed_as_registered_metadata(self):
        indicators = list_indicators()
        names = tuple(item.name for item in indicators)

        self.assertIn("regime.true_range", names)
        self.assertIn("regime.kaufman_efficiency_ratio", names)
        self.assertIn("regime.choppiness_index", names)
        self.assertIn("regime.classify_regime", names)
        self.assertIn("regime.ema", names)
        self.assertIn("regime.atr", names)
        self.assertIn("regime.adx_dmi", names)
        self.assertIn("regime.ttm_squeeze", names)

    def test_indicator_metadata_can_be_looked_up_by_name(self):
        indicator = get_indicator("regime.choppiness_index")

        self.assertEqual(indicator.category, "regime")
        self.assertEqual(indicator.default_lookback, 14)


if __name__ == "__main__":
    unittest.main()
