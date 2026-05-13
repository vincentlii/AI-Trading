import unittest

from trading_system.data.universe import (
    DEFAULT_PRIMARY_VENUE,
    DEFAULT_VALIDATION_VENUES,
    SymbolMapping,
    default_symbols,
    get_symbol_mapping,
    required_okx_bars_for_profiles,
    timeframe_to_okx_bar,
)
from trading_system.timeframe_profiles import list_default_profiles


class DataUniverseTests(unittest.TestCase):
    def test_default_symbols_are_fixed_okx_instrument_ids(self):
        self.assertEqual(default_symbols(), ("BTC-USDT", "ETH-USDT", "XAUT-USDT"))

    def test_symbol_mapping_keeps_canonical_and_exchange_symbols_separate(self):
        mapping = get_symbol_mapping("BTC/USDT")

        self.assertEqual(
            mapping,
            SymbolMapping(
                canonical_symbol="BTC/USDT",
                okx_inst_id="BTC-USDT",
                binance_symbol="BTCUSDT",
            ),
        )

    def test_xaut_binance_mapping_is_available_but_must_be_validated_by_exchange_info(self):
        mapping = get_symbol_mapping("XAUT/USDT")

        self.assertEqual(mapping.okx_inst_id, "XAUT-USDT")
        self.assertEqual(mapping.binance_symbol, "XAUTUSDT")

    def test_default_venues_reserve_okx_primary_and_binance_validation(self):
        self.assertEqual(DEFAULT_PRIMARY_VENUE, "okx")
        self.assertEqual(DEFAULT_VALIDATION_VENUES, ("binance",))

    def test_timeframe_to_okx_bar_maps_supported_profile_timeframes(self):
        self.assertEqual(timeframe_to_okx_bar("5m"), "5m")
        self.assertEqual(timeframe_to_okx_bar("15m"), "15m")
        self.assertEqual(timeframe_to_okx_bar("1h"), "1H")
        self.assertEqual(timeframe_to_okx_bar("4h"), "4H")
        self.assertEqual(timeframe_to_okx_bar("1d"), "1D")

    def test_required_okx_bars_for_default_profiles_are_unique_and_ordered(self):
        self.assertEqual(required_okx_bars_for_profiles(), ("5m", "15m", "1H", "4H", "1D"))

    def test_required_okx_bars_can_be_derived_from_supplied_profiles(self):
        profiles = list_default_profiles()

        self.assertEqual(required_okx_bars_for_profiles(profiles), ("5m", "15m", "1H", "4H", "1D"))

    def test_required_okx_bars_do_not_include_1m_from_default_profiles(self):
        self.assertNotIn("1m", required_okx_bars_for_profiles())


if __name__ == "__main__":
    unittest.main()
