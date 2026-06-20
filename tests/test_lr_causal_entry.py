import importlib.util
import unittest

from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import (
    build_all_previous_day_levels,
    build_confirmed_swing_levels,
    build_previous_day_levels,
    build_session_levels,
    detect_causal_events,
)


MINUTE = 60_000
HOUR = 60 * MINUTE
DAY = 24 * HOUR


def _candle(timestamp: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


class LRCausalEntryPublicAPITest(unittest.TestCase):
    def test_causal_entry_module_exists(self) -> None:
        spec = importlib.util.find_spec(
            "trading_system.strategies.trend_price_volume_v1.lr_causal_entry"
        )

        self.assertIsNotNone(spec)

    def test_session_levels_are_visible_only_after_session_close(self) -> None:
        candles = tuple(
            _candle(
                index * 15 * MINUTE,
                open_=100.0,
                high=101.0 + index,
                low=99.0 - index,
                close=100.0,
            )
            for index in range(32)
        )

        before = build_session_levels(candles, cutoff_time=8 * HOUR - 1)
        after = build_session_levels(candles, cutoff_time=8 * HOUR)

        self.assertEqual(before, ())
        self.assertEqual(len(after), 2)
        self.assertEqual({level.direction for level in after}, {"long", "short"})
        self.assertTrue(all(level.confirmed_time == 8 * HOUR for level in after))

    def test_previous_day_levels_use_only_completed_utc_day(self) -> None:
        candles = (
            _candle(0, open_=100, high=110, low=90, close=105),
            _candle(12 * HOUR, open_=105, high=120, low=95, close=110),
            _candle(DAY, open_=110, high=130, low=100, close=125),
        )

        levels = build_previous_day_levels(candles, cutoff_time=DAY)

        self.assertEqual({level.price for level in levels}, {90.0, 120.0})
        self.assertTrue(all(level.confirmed_time == DAY for level in levels))

    def test_all_previous_day_levels_are_built_in_one_history_pass(self) -> None:
        candles = (
            _candle(0, open_=100, high=110, low=90, close=105),
            _candle(DAY, open_=105, high=120, low=95, close=110),
            _candle(2 * DAY, open_=110, high=130, low=100, close=125),
        )

        levels = build_all_previous_day_levels(candles, cutoff_time=3 * DAY)

        self.assertEqual(len(levels), 6)
        self.assertEqual(
            [level.confirmed_time for level in levels if level.direction == "long"],
            [DAY, 2 * DAY, 3 * DAY],
        )

    def test_swing_level_waits_for_two_right_hand_bars_to_close(self) -> None:
        lows = (10.0, 9.0, 5.0, 8.0, 9.0)
        candles = tuple(
            _candle(index * 4 * HOUR, open_=low + 1, high=low + 2, low=low, close=low + 1)
            for index, low in enumerate(lows)
        )

        before = build_confirmed_swing_levels(candles, cutoff_time=20 * HOUR - 1)
        after = build_confirmed_swing_levels(candles, cutoff_time=20 * HOUR)

        self.assertFalse(any(level.price == 5.0 for level in before))
        level = next(level for level in after if level.direction == "long" and level.price == 5.0)
        self.assertEqual(level.confirmed_time, 20 * HOUR)

    def test_reclaim_event_uses_bar_close_and_dedupes_physical_signal(self) -> None:
        level_candles = tuple(
            _candle(index * 15 * MINUTE, open_=100, high=101, low=99, close=100)
            for index in range(32)
        )
        levels = build_session_levels(level_candles, cutoff_time=8 * HOUR)
        long_level = next(level for level in levels if level.direction == "long")
        duplicate_level = type(long_level)(
            level_id="another-level",
            family="previous_day_high_low",
            direction="long",
            price=long_level.price,
            confirmed_time=long_level.confirmed_time,
            source_time=long_level.source_time,
        )
        path = (
            _candle(8 * HOUR, open_=100, high=100, low=98, close=98.5),
            _candle(8 * HOUR + 15 * MINUTE, open_=98.5, high=100, low=98.4, close=99.5),
        )

        events = detect_causal_events(
            levels=(long_level, duplicate_level),
            candles_15m=path,
            atr_15m=1.0,
            atr_4h=4.0,
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(len({event.market_event_key for event in events}), 1)
        self.assertEqual(events[0].sweep_time, 8 * HOUR + 15 * MINUTE)
        self.assertEqual(events[0].reclaim_time, 8 * HOUR + 30 * MINUTE)
        self.assertLess(events[0].sweep_time, events[0].reclaim_time)
        self.assertEqual(events[0].level_confirmed_time, long_level.confirmed_time)
        self.assertEqual(events[0].level_source_time, long_level.source_time)

    def test_each_level_emits_only_its_first_reclaim_event(self) -> None:
        level_candles = tuple(
            _candle(index * 15 * MINUTE, open_=100, high=101, low=99, close=100)
            for index in range(32)
        )
        level = next(
            level
            for level in build_session_levels(level_candles, cutoff_time=8 * HOUR)
            if level.direction == "long"
        )
        path = (
            _candle(8 * HOUR, open_=100, high=100, low=98, close=98.5),
            _candle(8 * HOUR + 15 * MINUTE, open_=98.5, high=100, low=98.4, close=99.5),
            _candle(8 * HOUR + 30 * MINUTE, open_=99.5, high=100, low=98, close=98.5),
            _candle(8 * HOUR + 45 * MINUTE, open_=98.5, high=100, low=98.4, close=99.5),
        )

        events = detect_causal_events(levels=(level,), candles_15m=path, atr_15m=1.0, atr_4h=4.0)

        self.assertEqual(len(events), 1)

    def test_event_atr_is_resolved_at_sweep_close_not_level_confirmation(self) -> None:
        level_candles = tuple(
            _candle(index * 15 * MINUTE, open_=100, high=101, low=99, close=100)
            for index in range(32)
        )
        level = next(
            level
            for level in build_session_levels(level_candles, cutoff_time=8 * HOUR)
            if level.direction == "long"
        )
        path = (
            _candle(8 * HOUR, open_=100, high=100, low=98, close=99.5),
        )
        atr_15m_calls: list[int] = []
        atr_4h_calls: list[int] = []

        events = detect_causal_events(
            levels=(level,),
            candles_15m=path,
            atr_15m=lambda timestamp: atr_15m_calls.append(timestamp) or 2.0,
            atr_4h=lambda timestamp: atr_4h_calls.append(timestamp) or 5.0,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(atr_15m_calls, [8 * HOUR + 15 * MINUTE])
        self.assertEqual(atr_4h_calls, [8 * HOUR + 15 * MINUTE])
        self.assertEqual((events[0].atr_15m, events[0].atr_4h), (2.0, 5.0))


if __name__ == "__main__":
    unittest.main()
