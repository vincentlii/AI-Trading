import unittest

from trading_system.data.okx_cli import Candle
from trading_system.simulation import (
    HistoricalReplayMarketEventSource,
    MarketEvent,
    OkxCandlePollingSource,
    PaperBrokerConfig,
    PaperTradingEngine,
)
from trading_system.backtest.risk import RiskEngine, RiskParameters
from trading_system.strategies.base import StrategySignal


def _candle(index: int, *, confirmed: bool = True) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=100.0,
        high=111.0,
        low=99.0,
        close=110.0,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=11_000.0,
        is_confirmed=confirmed,
    )


def _signal() -> StrategySignal:
    return StrategySignal(
        strategy_name="trend_price_volume",
        strategy_version="v1",
        setup_type="trend_continuation",
        symbol="BTC/USDT",
        venue="okx",
        timeframe_group="B",
        direction="long",
        entry_zone={"low": 99.0, "high": 101.0},
        invalidation_level=95.0,
        target_hint={"target_price": 110.0},
        trend_evidence={"atr": 3.0},
        price_action_evidence={},
        volume_price_evidence={"status": "confirm"},
        risk_profile={},
        explanation_payload={},
    )


class FakeMarketData:
    def __init__(self):
        self.calls = 0

    def get_candles(self, inst_id, *, bar, limit, after=None, before=None):
        self.calls += 1
        return (_candle(2, confirmed=False), _candle(1, confirmed=True))


class SimulationEventSourceTests(unittest.TestCase):
    def test_historical_replay_yields_sorted_confirmed_market_events(self):
        source = HistoricalReplayMarketEventSource(
            symbol="BTC/USDT",
            inst_id="BTC-USDT",
            bar="15m",
            candles=(_candle(2, confirmed=False), _candle(1, confirmed=True), _candle(0, confirmed=True)),
        )

        events = source.events()

        self.assertEqual([event.timestamp_ms for event in events], [_candle(0).timestamp_ms, _candle(1).timestamp_ms])
        self.assertTrue(all(event.is_confirmed for event in events))

    def test_okx_polling_source_returns_new_confirmed_events_only(self):
        source = OkxCandlePollingSource(
            market_data=FakeMarketData(),
            symbol="BTC/USDT",
            inst_id="BTC-USDT",
            bar="15m",
            limit=2,
        )

        first = source.poll_once()
        second = source.poll_once()

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].inst_id, "BTC-USDT")
        self.assertEqual(second, ())

    def test_paper_engine_can_consume_market_events_with_signal_provider(self):
        engine = PaperTradingEngine(
            risk_engine=RiskEngine(RiskParameters()),
            config=PaperBrokerConfig(),
        )
        event = MarketEvent(
            timestamp_ms=_candle(1).timestamp_ms,
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT",
            bar="15m",
            candle=_candle(1),
        )

        result = engine.run_market_events((event,), lambda _event: (_signal(),))

        self.assertEqual(result.decisions[0].status, "approved")
        self.assertEqual(len(result.closed_trades), 1)


if __name__ == "__main__":
    unittest.main()
