from __future__ import annotations

import unittest
from dataclasses import replace

from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.lr_event_anatomy import build_event_anatomy
from trading_system.strategies.trend_price_volume_v1.lr_multitimeframe_event import LRMultiTimeframeEvent


BAR_MS = 15 * 60_000
SIGNAL_TIME = 60 * 60 * 60_000


def _event(direction: str = "long") -> LRMultiTimeframeEvent:
    sweep_extreme = 95.0 if direction == "long" else 105.0
    return LRMultiTimeframeEvent(
        event_id=f"event-{direction}",
        physical_event_key=f"physical-{direction}",
        instrument="BTC-USDT-SWAP",
        event_timeframe="1H_sweep_reclaim",
        timeframe_ms=60 * 60_000,
        level_id="level-1",
        level_family="previous_day_high_low",
        level_price=100.0,
        level_confirmed_time=0,
        level_source_time=0,
        direction=direction,
        sweep_start_bar_time=SIGNAL_TIME - 2 * 60 * 60_000,
        sweep_time=SIGNAL_TIME - 60 * 60_000,
        sweep_extreme_bar_time=SIGNAL_TIME - 2 * 60 * 60_000,
        sweep_extreme=sweep_extreme,
        reclaim_bar_time=SIGNAL_TIME - 60 * 60_000,
        reclaim_time=SIGNAL_TIME,
        signal_time=SIGNAL_TIME,
        signal_close=100.0,
        feature_cutoff_time=SIGNAL_TIME,
        reclaim_span_bars=2,
        sweep_atr=10.0,
        event_atr=10.0,
    )


def _future(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=SIGNAL_TIME + index * BAR_MS,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


class LREventAnatomyTest(unittest.TestCase):
    def test_long_anatomy_emits_horizons_mfe_mae_and_time_to_r(self):
        candles = [
            _future(0, high=104.0, low=99.0, close=103.0),
            _future(1, high=107.0, low=98.0, close=106.0),
            _future(2, high=109.0, low=97.0, close=108.0),
            _future(3, high=112.0, low=96.0, close=110.0),
        ]
        candles.extend(_future(index, high=110.0, low=99.0, close=110.0) for index in range(4, 80))

        row = build_event_anatomy(_event(), tuple(candles))

        self.assertEqual(row["row_role"], "diagnostic_label")
        self.assertAlmostEqual(row["invalidation_price"], 94.0)
        self.assertAlmostEqual(row["diagnostic_r_size"], 6.0)
        self.assertAlmostEqual(row["forward_15m_R"], 0.5)
        self.assertAlmostEqual(row["forward_15m_ATR"], 0.3)
        self.assertAlmostEqual(row["MFE_R"], 2.0)
        self.assertAlmostEqual(row["MAE_R"], 4.0 / 6.0)
        self.assertEqual(row["time_to_0_5R_minutes"], 15)
        self.assertEqual(row["time_to_1R_minutes"], 30)
        self.assertEqual(row["time_to_1_5R_minutes"], 45)
        self.assertEqual(row["time_to_2R_minutes"], 60)
        self.assertEqual(row["follow_through_status"], "follow_through")
        self.assertEqual(row["invalidation_first_status"], "one_r_first")

    def test_same_bar_target_and_invalidation_is_pessimistic(self):
        candles = (_future(0, high=112.0, low=94.0, close=100.0),)

        row = build_event_anatomy(_event(), candles)

        self.assertIsNone(row["time_to_0_5R_minutes"])
        self.assertIsNone(row["time_to_1R_minutes"])
        self.assertEqual(row["follow_through_status"], "invalidation_first")
        self.assertEqual(row["invalidation_first_status"], "invalidation_first")

    def test_short_uses_directional_returns_and_invalidation(self):
        candles = (_future(0, high=101.0, low=97.0, close=97.0),)

        row = build_event_anatomy(_event("short"), candles)

        self.assertAlmostEqual(row["invalidation_price"], 106.0)
        self.assertAlmostEqual(row["diagnostic_r_size"], 6.0)
        self.assertAlmostEqual(row["forward_15m_R"], 0.5)
        self.assertAlmostEqual(row["forward_15m_ATR"], 0.3)
        self.assertEqual(row["time_to_0_5R_minutes"], 15)

    def test_unconfirmed_or_pre_signal_bars_are_not_labels(self):
        pre_signal = replace(_future(-1, high=120.0, low=80.0, close=120.0), is_confirmed=True)
        unconfirmed = replace(_future(0, high=120.0, low=80.0, close=120.0), is_confirmed=False)

        row = build_event_anatomy(_event(), (pre_signal, unconfirmed))

        self.assertIsNone(row["forward_15m_R"])
        self.assertEqual(row["path_bars"], 0)
        self.assertEqual(row["follow_through_status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
