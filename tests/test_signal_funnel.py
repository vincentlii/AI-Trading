import unittest

from trading_system.config import load_backtest_preset
from trading_system.data.okx_cli import Candle
from trading_system.diagnostics.signal_funnel import build_signal_funnel_rows
from trading_system.strategies.trend_price_volume_v1 import TrendPriceVolumeStrategy


PROJECT_PRESET = "configs/presets/btc_eth_p4_4.toml"


def candle(index: int, interval_ms: int, close: float = 100.0, volume: float = 100.0) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * interval_ms,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=True,
    )


class FakeSignalRepository:
    def __init__(self, candles_by_key):
        self.candles_by_key = dict(candles_by_key)

    def load_range(self, inst_id, bar, start_ms, end_ms, *, venue="okx", inst_type="SPOT", confirmed_only=True):
        return tuple(
            item
            for item in self.candles_by_key.get((venue, inst_type, inst_id, bar), ())
            if start_ms <= item.timestamp_ms <= end_ms and (not confirmed_only or item.is_confirmed)
        )


class SignalFunnelTests(unittest.TestCase):
    def test_funnel_reports_data_insufficient_before_strategy_stages(self):
        preset = load_backtest_preset(PROJECT_PRESET)
        repository = FakeSignalRepository(
            {
                ("okx", "SPOT", "BTC-USDT", "15m"): tuple(candle(index, 900_000) for index in range(10)),
            }
        )

        rows = build_signal_funnel_rows(
            repository,
            preset=preset,
            strategy=TrendPriceVolumeStrategy(),
            profile_keys=("B",),
            max_windows_per_profile=5,
        )

        btc = next(row for row in rows if row["symbol"] == "BTC/USDT")
        self.assertEqual(btc["profile"], "B")
        self.assertEqual(btc["data_insufficient"], 1)
        self.assertEqual(btc["approved_signal"], 0)
        self.assertIn("missing_candles:1h", btc["reason_codes"])

    def test_funnel_counts_price_action_rejections_after_regime_is_computable(self):
        preset = load_backtest_preset(PROJECT_PRESET)
        repository = FakeSignalRepository(
            {
                ("okx", "SPOT", "BTC-USDT", "15m"): tuple(candle(index, 900_000) for index in range(230)),
                ("okx", "SPOT", "BTC-USDT", "1H"): tuple(candle(index - 210, 3_600_000) for index in range(230)),
                ("okx", "SPOT", "BTC-USDT", "4H"): tuple(candle(index - 210, 14_400_000) for index in range(230)),
            }
        )

        rows = build_signal_funnel_rows(
            repository,
            preset=preset,
            strategy=TrendPriceVolumeStrategy(),
            profile_keys=("B",),
            max_windows_per_profile=3,
        )

        btc = next(row for row in rows if row["symbol"] == "BTC/USDT")
        self.assertGreaterEqual(btc["windows_checked"], 1)
        self.assertGreater(btc["price_action_rejected"] + btc["regime_rejected"], 0)
        self.assertEqual(btc["approved_signal"], 0)


if __name__ == "__main__":
    unittest.main()
