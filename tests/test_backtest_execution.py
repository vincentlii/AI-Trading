import unittest

from trading_system.backtest.execution import (
    BacktestExecutionConfig,
    BacktestExecutionEngine,
    BacktestSignalInput,
    SignalOrderAdapter,
)
from trading_system.backtest.risk import RiskEngine, RiskParameters
from trading_system.data.okx_cli import Candle
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


class BacktestExecutionTests(unittest.TestCase):
    def engine(self, **config_overrides):
        config = BacktestExecutionConfig(**config_overrides)
        risk_engine = RiskEngine(RiskParameters())
        return BacktestExecutionEngine(risk_engine=risk_engine, config=config)

    def test_strategy_signal_converts_to_order_intent_from_next_candle_open(self):
        adapter = SignalOrderAdapter()

        intent, atr, reasons = adapter.to_order_intent(_signal(), (_candle(1, 100.0, 104.0, 99.0, 103.0),))

        self.assertEqual(reasons, ())
        self.assertEqual(atr, 3.0)
        self.assertEqual(intent.direction, "LONG")
        self.assertEqual(intent.entry_price, 100.0)
        self.assertEqual(intent.stop_loss, 95.0)
        self.assertEqual(intent.target_price, 110.0)

    def test_missing_required_signal_inputs_are_recorded_as_rejections(self):
        engine = self.engine()
        bad_inputs = (
            BacktestSignalInput(_signal(trend_evidence={}), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),
            BacktestSignalInput(_signal(invalidation_level=None), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),
            BacktestSignalInput(_signal(target_hint={}), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),
            BacktestSignalInput(_signal(direction="sideways"), (_candle(1, 100.0, 104.0, 99.0, 103.0),)),
            BacktestSignalInput(_signal(), ()),
        )

        result = engine.run(bad_inputs)

        self.assertEqual(len(result.fills), 0)
        self.assertEqual([decision.status for decision in result.decisions], ["rejected"] * 5)
        reason_codes = [decision.reason_codes[0] for decision in result.decisions]
        self.assertEqual(
            reason_codes,
            [
                "missing_atr",
                "missing_stop_loss",
                "missing_target_price",
                "invalid_direction",
                "missing_execution_candles",
            ],
        )

    def test_risk_rejection_does_not_generate_fill(self):
        engine = BacktestExecutionEngine(
            risk_engine=RiskEngine(RiskParameters(max_single_notional_pct=0.01)),
            config=BacktestExecutionConfig(),
        )

        result = engine.run((BacktestSignalInput(_signal(), (_candle(1, 100.0, 111.0, 99.0, 110.0),)),))

        self.assertEqual(len(result.fills), 0)
        self.assertEqual(result.decisions[0].status, "rejected")
        self.assertIn("notional_cap_exceeded", result.decisions[0].reason_codes)

    def test_approved_long_target_generates_positive_fill_and_equity_curve(self):
        result = self.engine().run(
            (BacktestSignalInput(_signal(), (_candle(1, 100.0, 111.0, 99.0, 110.0),)),)
        )

        self.assertEqual(result.decisions[0].status, "approved")
        self.assertEqual(len(result.fills), 1)
        fill = result.fills[0]
        self.assertEqual(fill.exit_reason, "target")
        self.assertEqual(fill.gross_pnl, 1000.0)
        self.assertEqual(fill.net_pnl, 1000.0)
        self.assertEqual(result.equity_curve[-1].equity, 101000.0)
        self.assertEqual(result.summary.net_profit, 1000.0)

    def test_approved_long_stop_generates_negative_fill(self):
        result = self.engine().run(
            (BacktestSignalInput(_signal(), (_candle(1, 100.0, 102.0, 94.0, 95.0),)),)
        )

        fill = result.fills[0]

        self.assertEqual(fill.exit_reason, "stop_loss")
        self.assertEqual(fill.gross_pnl, -500.0)
        self.assertEqual(fill.net_pnl, -500.0)
        self.assertEqual(result.summary.max_drawdown, 0.005)

    def test_short_target_and_stop_are_symmetric(self):
        short = _signal(direction="short", invalidation_level=105.0, target_hint={"target_price": 90.0})

        target = self.engine().run((BacktestSignalInput(short, (_candle(1, 100.0, 101.0, 89.0, 90.0),)),))
        stop = self.engine().run((BacktestSignalInput(short, (_candle(1, 100.0, 106.0, 98.0, 105.0),)),))

        self.assertEqual(target.fills[0].exit_reason, "target")
        self.assertEqual(target.fills[0].gross_pnl, 1000.0)
        self.assertEqual(stop.fills[0].exit_reason, "stop_loss")
        self.assertEqual(stop.fills[0].gross_pnl, -500.0)

    def test_same_bar_target_and_stop_uses_conservative_stop_first(self):
        result = self.engine().run(
            (BacktestSignalInput(_signal(), (_candle(1, 100.0, 111.0, 94.0, 109.0),)),)
        )

        self.assertEqual(result.fills[0].exit_reason, "stop_loss")
        self.assertEqual(result.fills[0].exit_price, 95.0)

    def test_time_exit_uses_last_close_after_max_holding_bars(self):
        result = self.engine(max_holding_bars=2).run(
            (
                BacktestSignalInput(
                    _signal(),
                    (
                        _candle(1, 100.0, 104.0, 96.0, 102.0),
                        _candle(2, 102.0, 105.0, 97.0, 103.0),
                        _candle(3, 103.0, 110.0, 94.0, 109.0),
                    ),
                ),
            )
        )

        fill = result.fills[0]

        self.assertEqual(fill.exit_reason, "time_exit")
        self.assertEqual(fill.exit_price, 103.0)
        self.assertEqual(fill.holding_bars, 2)

    def test_costs_reduce_net_pnl_and_are_included_in_summary(self):
        result = self.engine(fee_rate=0.001, spread=1.0, slippage=0.5, funding=2.0).run(
            (BacktestSignalInput(_signal(), (_candle(1, 100.0, 111.0, 99.0, 110.0),)),)
        )

        fill = result.fills[0]

        self.assertEqual(fill.gross_pnl, 1000.0)
        self.assertGreater(fill.cost_estimate.total, 0.0)
        self.assertEqual(fill.net_pnl, fill.gross_pnl - fill.cost_estimate.total)
        self.assertEqual(result.summary.net_profit, fill.net_pnl)
        self.assertGreater(result.summary.cost_to_gross_profit_ratio, 0.0)

    def test_equity_curve_and_summary_update_across_multiple_fills(self):
        result = self.engine().run(
            (
                BacktestSignalInput(_signal(), (_candle(1, 100.0, 111.0, 99.0, 110.0),)),
                BacktestSignalInput(_signal(), (_candle(2, 100.0, 102.0, 94.0, 95.0),)),
            )
        )

        self.assertEqual(len(result.fills), 2)
        self.assertEqual(len(result.equity_curve), 3)
        self.assertEqual(result.summary.trade_count, 2)
        self.assertEqual(result.summary.win_rate, 0.5)
        self.assertEqual(result.summary.expectancy_per_trade, 247.5)
        self.assertGreater(result.summary.max_drawdown, 0.0)

    def test_advanced_exit_partials_at_1r_then_stops_remaining_at_true_breakeven(self):
        result = self.engine(enable_advanced_exits=True, fee_rate=0.001).run(
            (
                BacktestSignalInput(
                    _signal(target_hint={"target_price": 120.0}),
                    (
                        _candle(1, 100.0, 106.0, 101.0, 105.0),
                        _candle(2, 105.0, 106.0, 100.1, 101.0),
                    ),
                ),
            )
        )

        fill = result.fills[0]

        self.assertEqual(fill.exit_reason, "breakeven_stop")
        self.assertEqual([event.event_type for event in fill.exit_events], ["partial_take_profit", "breakeven_stop"])
        self.assertEqual(fill.exit_events[0].price, 105.0)
        self.assertGreater(fill.exit_events[1].price, 100.0)
        self.assertAlmostEqual(fill.exit_events[0].quantity, fill.order.quantity * 0.5)
        self.assertAlmostEqual(fill.exit_events[1].quantity, fill.order.quantity * 0.5)
        self.assertEqual(fill.trade_log.exit_events, fill.exit_events)

    def test_advanced_exit_uses_chandelier_for_remaining_position_after_partial(self):
        result = self.engine(
            enable_advanced_exits=True,
            chandelier_period=2,
            chandelier_atr_multiple=1.0,
        ).run(
            (
                BacktestSignalInput(
                    _signal(target_hint={"target_price": 120.0}),
                    (
                        _candle(1, 100.0, 106.0, 101.0, 105.0),
                        _candle(2, 105.0, 108.0, 104.0, 107.0),
                        _candle(3, 107.0, 107.5, 104.5, 105.0),
                    ),
                ),
            )
        )

        fill = result.fills[0]

        self.assertEqual(fill.exit_reason, "chandelier_exit")
        self.assertEqual([event.event_type for event in fill.exit_events], ["partial_take_profit", "chandelier_exit"])
        self.assertEqual(fill.exit_events[1].price, 105.0)

    def test_advanced_time_stop_exits_remaining_after_partial(self):
        result = self.engine(enable_advanced_exits=True, max_holding_bars=2).run(
            (
                BacktestSignalInput(
                    _signal(target_hint={"target_price": 120.0}),
                    (
                        _candle(1, 100.0, 106.0, 101.0, 105.0),
                        _candle(2, 105.0, 107.0, 101.0, 106.0),
                        _candle(3, 106.0, 120.0, 90.0, 100.0),
                    ),
                ),
            )
        )

        fill = result.fills[0]

        self.assertEqual(fill.exit_reason, "time_exit")
        self.assertEqual([event.event_type for event in fill.exit_events], ["partial_take_profit", "time_exit"])
        self.assertEqual(fill.exit_price, 106.0)
        self.assertEqual(fill.holding_bars, 2)

    def test_advanced_short_exits_are_symmetric(self):
        short = _signal(
            direction="short",
            invalidation_level=105.0,
            target_hint={"target_price": 80.0},
        )

        result = self.engine(
            enable_advanced_exits=True,
            chandelier_period=2,
            chandelier_atr_multiple=1.0,
        ).run(
            (
                BacktestSignalInput(
                    short,
                    (
                        _candle(1, 100.0, 100.5, 94.0, 95.0),
                        _candle(2, 95.0, 96.0, 92.0, 93.0),
                        _candle(3, 93.0, 95.5, 92.5, 95.0),
                    ),
                ),
            )
        )

        fill = result.fills[0]

        self.assertEqual(fill.exit_reason, "chandelier_exit")
        self.assertEqual([event.event_type for event in fill.exit_events], ["partial_take_profit", "chandelier_exit"])
        self.assertEqual(fill.exit_events[0].price, 95.0)
        self.assertEqual(fill.exit_events[1].price, 95.0)


if __name__ == "__main__":
    unittest.main()
