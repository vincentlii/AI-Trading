import unittest

from trading_system.backtest.risk import RiskEngine, RiskParameters
from trading_system.data.okx_cli import Candle
from trading_system.simulation import PaperBrokerConfig, PaperSignalInput, PaperTradingEngine
from trading_system.strategies.base import StrategySignal


def _candle(index: int, open_price: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


def _signal(**overrides) -> StrategySignal:
    values = {
        "strategy_name": "trend_price_volume",
        "strategy_version": "v1",
        "setup_type": "trend_continuation",
        "symbol": "BTC/USDT",
        "venue": "okx",
        "timeframe_group": "B",
        "direction": "long",
        "entry_zone": {"low": 99.0, "high": 101.0, "reference_price": 100.0},
        "invalidation_level": 95.0,
        "target_hint": {"target_price": 110.0},
        "trend_evidence": {"atr": 3.0},
        "price_action_evidence": {},
        "volume_price_evidence": {"status": "confirm"},
        "risk_profile": {},
        "explanation_payload": {},
    }
    values.update(overrides)
    return StrategySignal(**values)


class PaperTradingEngineTests(unittest.TestCase):
    def engine(self, *, risk_parameters=None, **config_overrides):
        return PaperTradingEngine(
            risk_engine=RiskEngine(risk_parameters or RiskParameters()),
            config=PaperBrokerConfig(**config_overrides),
        )

    def test_approved_signal_creates_fill_position_and_review_log(self):
        result = self.engine(fee_rate=0.001, spread=0.5, slippage=0.25).run(
            (PaperSignalInput(_signal(), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),)
        )

        self.assertEqual(result.decisions[0].status, "approved")
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(len(result.positions), 1)
        self.assertEqual(len(result.closed_positions), 1)
        self.assertEqual(len(result.closed_trades), 1)
        self.assertEqual(result.positions[0].entry_price, 100.0)
        self.assertEqual(result.positions[0].stop_loss, 95.0)
        self.assertGreater(result.fills[0].cost_estimate.total, 0.0)
        self.assertGreater(result.equity_curve[-1].equity, 100_000.0)
        self.assertEqual(
            [entry.event_type for entry in result.review_log],
            [
                "signal_received",
                "order_created",
                "fill_recorded",
                "position_opened",
                "exit_recorded",
                "position_closed",
                "equity_updated",
            ],
        )
        self.assertEqual(result.account.open_positions, ())

    def test_stop_exit_records_negative_cost_adjusted_r_multiple(self):
        result = self.engine(fee_rate=0.001).run(
            (PaperSignalInput(_signal(), (_candle(1, 100.0, 102.0, 94.0, 95.0),)),)
        )

        closed_trade = result.closed_trades[0]

        self.assertEqual(closed_trade.exit_reason, "stop_loss")
        self.assertLess(closed_trade.net_pnl, 0.0)
        self.assertLess(closed_trade.r_multiple, 0.0)
        self.assertEqual(result.review_log[-2].event_type, "position_closed")
        self.assertEqual(result.review_log[-2].payload["r_multiple"], closed_trade.r_multiple)

    def test_adapter_rejection_is_recorded_without_order_or_position(self):
        result = self.engine().run(
            (PaperSignalInput(_signal(trend_evidence={}), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),)
        )

        self.assertEqual(result.decisions[0].status, "rejected")
        self.assertEqual(result.decisions[0].reason_codes, ("missing_atr",))
        self.assertEqual(result.fills, ())
        self.assertEqual(result.positions, ())
        self.assertEqual(result.review_log[-1].event_type, "adapter_rejected")
        self.assertEqual(result.review_log[-1].reason_codes, ("missing_atr",))

    def test_risk_rejection_is_recorded_without_fill(self):
        result = self.engine(risk_parameters=RiskParameters(max_single_notional_pct=0.01)).run(
            (PaperSignalInput(_signal(), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),)
        )

        self.assertEqual(result.decisions[0].status, "rejected")
        self.assertIn("notional_cap_exceeded", result.decisions[0].reason_codes)
        self.assertEqual(result.fills, ())
        self.assertEqual(result.positions, ())
        self.assertEqual(result.review_log[-1].event_type, "risk_rejected")
        self.assertIn("notional_cap_exceeded", result.review_log[-1].reason_codes)

    def test_open_positions_feed_next_risk_decision(self):
        result = self.engine(risk_parameters=RiskParameters(max_portfolio_heat_pct=0.005)).run(
            (
                PaperSignalInput(
                    _signal(),
                    (
                        _candle(1, 100.0, 104.0, 99.0, 103.0),
                        _candle(2, 103.0, 104.0, 100.0, 103.0),
                        _candle(3, 103.0, 104.0, 100.0, 103.0),
                    ),
                ),
                PaperSignalInput(_signal(), (_candle(2, 100.0, 104.0, 99.0, 103.0),)),
            )
        )

        self.assertEqual(result.decisions[0].status, "approved")
        self.assertEqual(result.decisions[1].status, "rejected")
        self.assertIn("portfolio_heat_exceeded", result.decisions[1].reason_codes)
        self.assertEqual(len(result.positions), 1)
        self.assertEqual(result.account.open_positions, ())
        self.assertEqual(len(result.closed_positions), 1)


if __name__ == "__main__":
    unittest.main()
