import unittest

from trading_system.backtest.risk import (
    AccountState,
    CostEstimate,
    OrderIntent,
    PositionState,
    RiskEngine,
    RiskParameters,
)


class RiskEngineTests(unittest.TestCase):
    def engine(self):
        return RiskEngine(RiskParameters())

    def account(self, *, drawdown=0.0, open_positions=()):
        return AccountState(
            equity=100_000.0,
            high_water_mark=100_000.0,
            current_drawdown_pct=drawdown,
            daily_pnl=0.0,
            open_positions=tuple(open_positions),
        )

    def intent(self, **overrides):
        values = {
            "strategy_name": "trend_price_volume",
            "strategy_version": "v1",
            "setup_type": "trend_continuation",
            "symbol": "BTC/USDT",
            "venue": "okx",
            "direction": "LONG",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target_price": 115.0,
            "point_value": 1.0,
        }
        values.update(overrides)
        return OrderIntent(**values)

    def test_single_trade_risk_uses_equity_percentage_for_position_size(self):
        decision = self.engine().evaluate(self.intent(), self.account(), atr=3.0)

        self.assertEqual(decision.status, "approved")
        self.assertEqual(decision.risk_amount, 500.0)
        self.assertEqual(decision.approved_order.quantity, 100.0)
        self.assertEqual(decision.approved_order.notional_value, 10_000.0)

    def test_stop_distance_too_near_or_too_far_is_rejected(self):
        near = self.engine().evaluate(self.intent(stop_loss=99.0), self.account(), atr=2.0)
        far = self.engine().evaluate(self.intent(stop_loss=85.0), self.account(), atr=4.0)

        self.assertEqual(near.status, "rejected")
        self.assertIn("stop_distance_too_near", near.reason_codes)
        self.assertEqual(far.status, "rejected")
        self.assertIn("stop_distance_too_far", far.reason_codes)

    def test_notional_leverage_and_heat_caps_can_reject_orders(self):
        params = RiskParameters(max_single_notional_pct=0.05, max_total_gross_leverage=0.20, max_portfolio_heat_pct=0.005)
        engine = RiskEngine(params)
        large = engine.evaluate(self.intent(stop_loss=99.0), self.account(), atr=1.0)

        self.assertEqual(large.status, "rejected")
        self.assertIn("notional_cap_exceeded", large.reason_codes)

        existing = PositionState(
            symbol="ETH/USDT",
            venue="okx",
            direction="LONG",
            quantity=100.0,
            entry_price=100.0,
            stop_loss=95.0,
            initial_risk_amount=400.0,
            notional_value=10_000.0,
        )
        heat = engine.evaluate(self.intent(stop_loss=95.0), self.account(open_positions=(existing,)), atr=3.0)

        self.assertEqual(heat.status, "rejected")
        self.assertIn("portfolio_heat_exceeded", heat.reason_codes)

    def test_drawdown_thresholds_reduce_risk_and_hard_stop(self):
        engine = self.engine()

        reduced = engine.evaluate(self.intent(), self.account(drawdown=0.02), atr=3.0)
        hard_stop = engine.evaluate(self.intent(), self.account(drawdown=0.05), atr=3.0)

        self.assertEqual(reduced.status, "approved")
        self.assertEqual(reduced.risk_pct, 0.0035)
        self.assertEqual(reduced.risk_amount, 350.0)
        self.assertEqual(hard_stop.status, "rejected")
        self.assertIn("hard_drawdown_stop", hard_stop.reason_codes)

    def test_liquidity_reversal_target_below_minimum_r_is_rejected(self):
        decision = self.engine().evaluate(
            self.intent(setup_type="liquidity_reversal", target_price=106.0),
            self.account(),
            atr=3.0,
        )

        self.assertEqual(decision.status, "rejected")
        self.assertIn("target_reward_below_minimum", decision.reason_codes)

    def test_true_breakeven_includes_fee_spread_slippage_and_funding(self):
        costs = CostEstimate(fees=10.0, spread=5.0, expected_slippage=3.0, funding=2.0)

        long_price = costs.true_breakeven_price(entry_price=100.0, remaining_quantity=10.0, direction="LONG")
        short_price = costs.true_breakeven_price(entry_price=100.0, remaining_quantity=10.0, direction="SHORT")

        self.assertEqual(long_price, 102.0)
        self.assertEqual(short_price, 98.0)


if __name__ == "__main__":
    unittest.main()
