import unittest

from trading_system.data.okx_cli import Candle
from trading_system.strategies import get_strategy
from trading_system.strategies.base import StrategyContext


def _candle(
    index: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
    *,
    confirmed: bool = True,
) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=confirmed,
    )


def _bullish_trend_candles(count: int = 230) -> tuple[Candle, ...]:
    candles: list[Candle] = []
    for index in range(count):
        close = 100.0 + index * 0.45
        candles.append(
            _candle(
                index,
                close - 0.2,
                close + 0.5,
                close - 0.5,
                close,
                volume=500.0 + index,
            )
        )
    return tuple(candles)


def _trend_continuation_structure() -> tuple[Candle, ...]:
    rows = (
        (100.0, 101.0, 99.0, 100.5),
        (100.5, 103.0, 100.0, 102.5),
        (102.5, 105.0, 101.5, 104.5),
        (104.5, 104.8, 101.0, 102.0),
        (102.0, 103.2, 100.2, 101.5),
        (101.5, 104.2, 101.0, 103.8),
        (103.8, 108.2, 103.2, 107.6),
        (107.6, 108.0, 105.0, 106.4),
    )
    return tuple(_candle(index, *row, volume=800.0 + index * 10) for index, row in enumerate(rows))


def _liquidity_reversal_structure() -> tuple[Candle, ...]:
    rows = (
        (110.0, 111.0, 108.0, 109.0),
        (109.0, 110.0, 104.0, 105.0),
        (105.0, 106.0, 100.0, 101.0),
        (101.0, 105.5, 99.4, 104.8),
        (104.8, 108.5, 103.8, 108.0),
        (108.0, 109.0, 105.5, 107.6),
    )
    return tuple(_candle(index, *row, volume=850.0 + index * 15) for index, row in enumerate(rows))


def _entry_candles(*, quiet_latest: bool = False) -> tuple[Candle, ...]:
    candles: list[Candle] = []
    for index in range(24):
        close = 105.0 + (index % 3) * 0.1
        candles.append(
            _candle(
                index,
                close - 0.1,
                close + 0.3,
                close - 0.3,
                close,
                volume=100.0,
            )
        )
    latest_volume = 40.0 if quiet_latest else 320.0
    candles.append(_candle(24, 105.2, 107.0, 104.9, 106.6, volume=latest_volume))
    return tuple(candles)


class TrendPriceVolumeStrategySignalTests(unittest.TestCase):
    def test_missing_required_timeframes_returns_no_signals(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={"15m": _entry_candles()},
        )

        self.assertEqual(strategy.generate_signals(context), ())

    def test_generates_trend_continuation_signal_from_three_timeframes(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(),
                "1h": _trend_continuation_structure(),
                "4h": _bullish_trend_candles(),
            },
        )

        signals = strategy.generate_signals(context)

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.setup_type, "trend_continuation")
        self.assertEqual(signal.direction, "long")
        self.assertEqual(signal.strategy_name, "trend_price_volume")
        self.assertEqual(signal.strategy_version, "v1")
        self.assertEqual(signal.symbol, "BTC/USDT")
        self.assertEqual(signal.venue, "okx")
        self.assertEqual(signal.timeframe_group, "B")
        self.assertEqual(signal.volume_price_evidence["status"], "confirm")
        self.assertGreater(signal.target_hint["reward_to_risk"], 1.5)
        self.assertLess(signal.invalidation_level, signal.entry_zone["low"])

    def test_quiet_latest_volume_rejects_otherwise_valid_signal(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(quiet_latest=True),
                "1h": _trend_continuation_structure(),
                "4h": _bullish_trend_candles(),
            },
        )

        self.assertEqual(strategy.generate_signals(context), ())

    def test_generates_liquidity_reversal_signal_when_sweep_choch_and_volume_confirm(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(),
                "1h": _liquidity_reversal_structure(),
                "4h": _bullish_trend_candles(),
            },
        )

        signals = strategy.generate_signals(context)

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.setup_type, "liquidity_reversal")
        self.assertEqual(signal.direction, "long")
        self.assertEqual(signal.price_action_evidence["sweep_direction"], "down")
        self.assertGreaterEqual(signal.target_hint["reward_to_risk"], 1.5)


if __name__ == "__main__":
    unittest.main()
