import unittest
from pathlib import Path

from trading_system.backtest.contract_risk import estimate_contract_risk
from trading_system.backtest.risk import OrderIntent
from trading_system.config import load_backtest_preset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SWAP_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_swap_proposal.toml"


class ContractRiskDiagnosticsTests(unittest.TestCase):
    def test_long_and_short_contract_diagnostics_are_symmetric(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        long_intent = OrderIntent(
            strategy_name="trend_price_volume",
            strategy_version="v1",
            setup_type="liquidity_reversal",
            symbol="BTC/USDT",
            venue="okx",
            direction="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
        )
        short_intent = OrderIntent(
            strategy_name="trend_price_volume",
            strategy_version="v1",
            setup_type="liquidity_reversal",
            symbol="BTC/USDT",
            venue="okx",
            direction="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            target_price=90.0,
        )

        long_diag = estimate_contract_risk(intent=long_intent, quantity=10.0, risk_amount=500.0, preset=preset)
        short_diag = estimate_contract_risk(intent=short_intent, quantity=10.0, risk_amount=500.0, preset=preset)

        self.assertEqual(long_diag.notional, short_diag.notional)
        self.assertEqual(long_diag.margin_required, short_diag.margin_required)
        self.assertEqual(long_diag.gross_exposure, short_diag.gross_exposure)
        self.assertEqual(long_diag.net_exposure, -short_diag.net_exposure)
        self.assertLess(long_diag.liquidation_price, long_intent.entry_price)
        self.assertGreater(short_diag.liquidation_price, short_intent.entry_price)
        self.assertGreater(long_diag.liquidation_distance_pct, 0.0)
        self.assertGreater(short_diag.liquidation_distance_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
