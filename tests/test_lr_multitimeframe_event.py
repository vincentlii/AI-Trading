from __future__ import annotations

import unittest

from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import LRCausalLevel
from trading_system.strategies.trend_price_volume_v1.lr_multitimeframe_event import (
    EVENT_POLICIES,
    detect_multitimeframe_events,
)


def _candle(
    timestamp_ms: int,
    *,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    volume: float = 100.0,
    confirmed: bool = True,
) -> Candle:
    return Candle(
        timestamp_ms=timestamp_ms,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=confirmed,
    )


def _level(*, level_id: str = "level-a", family: str = "session_high_low") -> LRCausalLevel:
    return LRCausalLevel(
        level_id=level_id,
        family=family,
        direction="long",
        price=100.0,
        confirmed_time=0,
        source_time=-1,
    )


class LRMultiTimeframeEventTest(unittest.TestCase):
    def test_15m_control_reclaims_within_four_bars_and_uses_reclaim_close_time(self):
        bar_ms = 15 * 60_000
        candles = (
            _candle(bar_ms, low=98.0, close=99.0),
            _candle(2 * bar_ms, low=98.5, close=99.5),
            _candle(3 * bar_ms, low=99.0, close=99.8),
            _candle(4 * bar_ms, low=99.5, close=100.5),
        )

        events = detect_multitimeframe_events(
            levels=(_level(),),
            candles=candles,
            atr_at=lambda _: 10.0,
            policy=EVENT_POLICIES["15m_micro"],
            instrument="BTC-USDT-SWAP",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].reclaim_span_bars, 4)
        self.assertEqual(events[0].signal_time, 5 * bar_ms)
        self.assertEqual(events[0].feature_cutoff_time, events[0].signal_time)

    def test_1h_supports_one_two_or_three_bar_reclaim_but_not_four(self):
        bar_ms = 60 * 60_000
        for reclaim_span in (1, 2, 3):
            candles = [_candle(bar_ms, low=98.0, close=101.0 if reclaim_span == 1 else 99.0)]
            for index in range(2, reclaim_span + 1):
                candles.append(
                    _candle(index * bar_ms, low=98.0, close=101.0 if index == reclaim_span else 99.0)
                )
            events = detect_multitimeframe_events(
                levels=(_level(),),
                candles=tuple(candles),
                atr_at=lambda _: 10.0,
                policy=EVENT_POLICIES["1H_sweep_reclaim"],
                instrument="BTC-USDT-SWAP",
            )
            self.assertEqual(events[0].reclaim_span_bars, reclaim_span)

        four_bar = (
            _candle(bar_ms, low=98.0, close=99.0),
            _candle(2 * bar_ms, low=98.0, close=99.0),
            _candle(3 * bar_ms, low=98.0, close=99.0),
            _candle(4 * bar_ms, low=98.0, close=101.0),
        )
        events = detect_multitimeframe_events(
            levels=(_level(),),
            candles=four_bar,
            atr_at=lambda _: 10.0,
            policy=EVENT_POLICIES["1H_sweep_reclaim"],
            instrument="BTC-USDT-SWAP",
        )
        self.assertEqual(events, ())

    def test_4h_requires_same_bar_wick_reclaim(self):
        bar_ms = 4 * 60 * 60_000
        same_bar = (_candle(bar_ms, low=97.0, close=101.0),)
        next_bar = (
            _candle(bar_ms, low=97.0, close=99.0),
            _candle(2 * bar_ms, low=99.0, close=101.0),
        )

        accepted = detect_multitimeframe_events(
            levels=(_level(),),
            candles=same_bar,
            atr_at=lambda _: 10.0,
            policy=EVENT_POLICIES["4H_wick_reclaim"],
            instrument="BTC-USDT-SWAP",
        )
        rejected = detect_multitimeframe_events(
            levels=(_level(),),
            candles=next_bar,
            atr_at=lambda _: 10.0,
            policy=EVENT_POLICIES["4H_wick_reclaim"],
            instrument="BTC-USDT-SWAP",
        )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].signal_time, 2 * bar_ms)
        self.assertEqual(rejected, ())

    def test_rejects_unconfirmed_and_pre_level_bars_but_keeps_unfiltered_1h_depth(self):
        bar_ms = 60 * 60_000
        policy = EVENT_POLICIES["1H_sweep_reclaim"]
        unconfirmed = (_candle(bar_ms, low=98.0, close=101.0, confirmed=False),)
        pre_level = LRCausalLevel("late", "session_high_low", "long", 100.0, 5 * bar_ms, 0)
        deep = (_candle(4 * bar_ms, low=80.0, close=101.0),)

        self.assertEqual(
            detect_multitimeframe_events(
                levels=(_level(),), candles=unconfirmed, atr_at=lambda _: 10.0, policy=policy
            ),
            (),
        )
        self.assertEqual(
            detect_multitimeframe_events(
                levels=(pre_level,), candles=deep, atr_at=lambda _: 10.0, policy=policy
            ),
            (),
        )
        self.assertEqual(
            len(
                detect_multitimeframe_events(
                    levels=(_level(),), candles=deep, atr_at=lambda _: 10.0, policy=policy
                )
            ),
            1,
        )

    def test_optional_depth_cap_preserves_15m_control_filter(self):
        bar_ms = 15 * 60_000
        deep = (_candle(bar_ms, low=80.0, close=101.0),)

        events = detect_multitimeframe_events(
            levels=(_level(),),
            candles=deep,
            atr_at=lambda _: 2.0,
            sweep_depth_cap_at=lambda _: 10.0,
            policy=EVENT_POLICIES["15m_micro"],
        )

        self.assertEqual(events, ())

    def test_physical_event_key_is_shared_across_level_families(self):
        bar_ms = 4 * 60 * 60_000
        candles = (_candle(bar_ms, low=98.0, close=101.0),)
        levels = (
            _level(level_id="session", family="session_high_low"),
            _level(level_id="pdl", family="previous_day_high_low"),
        )

        events = detect_multitimeframe_events(
            levels=levels,
            candles=candles,
            atr_at=lambda _: 10.0,
            policy=EVENT_POLICIES["4H_wick_reclaim"],
            instrument="BTC-USDT-SWAP",
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].physical_event_key, events[1].physical_event_key)
        self.assertNotEqual(events[0].event_id, events[1].event_id)


if __name__ == "__main__":
    unittest.main()
