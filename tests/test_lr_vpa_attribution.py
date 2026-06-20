from __future__ import annotations

import unittest

from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.lr_multitimeframe_event import LRMultiTimeframeEvent
from trading_system.strategies.trend_price_volume_v1.lr_vpa_attribution import (
    build_post_signal_volume_label,
    build_vpa_feature_row,
)


HOUR_MS = 60 * 60_000


def _candle(
    index: int,
    *,
    volume: float = 100.0,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
) -> Candle:
    return Candle(
        timestamp_ms=index * HOUR_MS,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=True,
    )


def _event(*, sweep_index: int = 20, reclaim_index: int = 21) -> LRMultiTimeframeEvent:
    reclaim_time = (reclaim_index + 1) * HOUR_MS
    return LRMultiTimeframeEvent(
        event_id="event-1",
        physical_event_key="physical-1",
        instrument="BTC-USDT-SWAP",
        event_timeframe="1H_sweep_reclaim",
        timeframe_ms=HOUR_MS,
        level_id="level-1",
        level_family="previous_day_high_low",
        level_price=100.0,
        level_confirmed_time=0,
        level_source_time=0,
        direction="long",
        sweep_start_bar_time=sweep_index * HOUR_MS,
        sweep_time=(sweep_index + 1) * HOUR_MS,
        sweep_extreme_bar_time=sweep_index * HOUR_MS,
        sweep_extreme=95.0,
        reclaim_bar_time=reclaim_index * HOUR_MS,
        reclaim_time=reclaim_time,
        signal_time=reclaim_time,
        signal_close=101.0,
        feature_cutoff_time=reclaim_time,
        reclaim_span_bars=reclaim_index - sweep_index + 1,
        sweep_atr=5.0,
        event_atr=5.0,
    )


class LRVPAAttributionTest(unittest.TestCase):
    def test_causal_vpa_uses_prior_baselines_and_full_event_window(self):
        candles = [_candle(index) for index in range(20)]
        candles.append(_candle(20, volume=200.0, open_price=100.0, high=101.0, low=95.0, close=99.0))
        candles.append(_candle(21, volume=50.0, open_price=99.0, high=102.0, low=98.0, close=101.0))

        row = build_vpa_feature_row(_event(), tuple(candles))

        self.assertEqual(row["row_role"], "tradable_feature")
        self.assertAlmostEqual(row["sweep_relative_volume"], 2.0)
        self.assertAlmostEqual(row["reclaim_relative_volume"], 0.5)
        self.assertAlmostEqual(row["sweep_volume_percentile"], 1.0)
        self.assertAlmostEqual(row["reclaim_volume_percentile"], 0.0)
        self.assertAlmostEqual(row["combined_volume_ratio"], 1.25)
        self.assertAlmostEqual(row["wick_ratio"], 4.0 / 6.0)
        self.assertAlmostEqual(row["close_location_value"], 4.0 / 6.0)
        self.assertEqual(row["max_source_time"], _event().signal_time)
        self.assertEqual(row["feature_cutoff_time"], _event().signal_time)
        self.assertEqual(row["sweep_volume_bucket"], "q4")
        self.assertEqual(row["reclaim_volume_bucket"], "q1")

    def test_vpa_returns_null_when_prior_sample_is_too_small(self):
        event = _event(sweep_index=5, reclaim_index=5)
        candles = tuple(_candle(index, volume=200.0 if index == 5 else 100.0) for index in range(6))

        row = build_vpa_feature_row(event, candles)

        self.assertIsNone(row["sweep_relative_volume"])
        self.assertIsNone(row["sweep_volume_percentile"])
        self.assertEqual(row["sweep_baseline_samples"], 5)

    def test_post_signal_volume_is_diagnostic_label_only(self):
        candles = [_candle(index) for index in range(20)]
        candles.append(_candle(20, volume=200.0, low=95.0, close=99.0))
        candles.append(_candle(21, volume=50.0, close=101.0))
        candles.extend((_candle(22, volume=150.0), _candle(23, volume=80.0), _candle(24, volume=70.0)))

        row = build_post_signal_volume_label(_event(), tuple(candles))

        self.assertEqual(row["row_role"], "diagnostic_label")
        self.assertGreater(row["min_source_time"], _event().signal_time)
        self.assertAlmostEqual(row["follow_through_relative_volume"], 1.5)
        self.assertAlmostEqual(row["post_reclaim_volume_ratio_3"], 2.0)
        self.assertEqual(row["post_reclaim_volume_phase"], "expansion")
        self.assertNotIn("quality_score", row)
        self.assertNotIn("passed", row)


if __name__ == "__main__":
    unittest.main()
