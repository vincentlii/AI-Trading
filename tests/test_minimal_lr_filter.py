import unittest

from trading_system.config import load_backtest_preset
from trading_system.diagnostics.minimal_lr_filter import replay_minimal_lr_v0, run_minimal_execution_replay
from trading_system.data.okx_cli import Candle


def _candidate(**overrides):
    row = {
        "event_id": "event-1",
        "asset": "BTC",
        "symbol": "BTC/USDT",
        "inst_id": "BTC-USDT-SWAP",
        "inst_type": "SWAP",
        "venue": "okx",
        "profile": "B",
        "direction": "long",
        "structure_level_source": "recent_swing",
        "structure_level_type": "recent_swing_low",
        "entry_price": 20.0,
        "stop_price": 19.0,
        "target_price": 22.0,
        "stop_atr_entry_tf": 1.0,
        "stop_atr_structure_tf": 1.0,
        "target_r": 2.0,
        "wick_ratio": 0.01,
        "sweep_rvol": None,
        "reclaim_rvol": None,
        "choch_detected": False,
        "trend_aligned": "",
        "liquidity_score": 0.25,
    }
    row.update(overrides)
    return row


class MinimalLRFilterReplayTests(unittest.TestCase):
    def test_v0_keeps_quality_filters_as_tags_not_hard_rejections(self):
        preset = load_backtest_preset("configs/presets/btc_eth_swap_proposal.toml")

        result = replay_minimal_lr_v0(candidates=(_candidate(),), preset=preset)

        self.assertEqual(len(result.filter_rows), 1)
        row = result.filter_rows[0]
        self.assertTrue(row["formal_approved"])
        self.assertEqual(row["reject_reason"], "")
        self.assertEqual(row["wick_ratio_tier"], "low_wick")
        self.assertEqual(row["choch_tag"], "choch_false")

    def test_v0_records_contract_or_risk_reject_reason_without_shadow_promotion(self):
        preset = load_backtest_preset("configs/presets/btc_eth_swap_proposal.toml")

        result = replay_minimal_lr_v0(candidates=(_candidate(entry_price=100.0, stop_price=99.0, target_price=102.0),), preset=preset)

        row = result.filter_rows[0]
        self.assertFalse(row["formal_approved"])
        self.assertEqual(row["reject_stage"], "risk_filter")
        self.assertEqual(row["reject_reason"], "margin_required_too_high")
        self.assertTrue(row["shadow_approved_5"])
        self.assertEqual(row["risk_pct"], 0.005)
        self.assertGreater(row["raw_position_notional_by_risk"], row["max_single_notional"])
        self.assertLess(row["capped_actual_risk_pct"], row["risk_pct"])
        self.assertEqual(row["margin_reject_reason"], "margin_required_too_high")

    def test_minimal_execution_rows_write_closed_trade_lineage_contract(self):
        preset = load_backtest_preset("configs/presets/btc_eth_swap_proposal.toml")
        row = _candidate(
            candidate_id="candidate-1",
            event_id="event-1",
            entry_time=1_700_000_000_000,
            signal_time=1_699_999_940_000,
            sweep_time=1_699_999_820_000,
            reclaim_time=1_699_999_880_000,
            structure_time=1_699_999_700_000,
            entry_price=20.0,
            stop_price=19.0,
            target_price=22.0,
            formal_approved=True,
            stop_atr=1.0,
            target_r=2.0,
        )
        repository = _Repository(
            (
                _candle(0, 20.0, 22.5, 19.5, 22.0),
                _candle(1, 22.0, 23.0, 21.0, 22.5),
            )
        )

        rows = run_minimal_execution_replay(repository=repository, filter_rows=(row,), preset=preset)

        self.assertEqual(len(rows), 1)
        execution = rows[0]
        self.assertEqual(execution["row_type"], "closed_trade")
        self.assertEqual(execution["candidate_id"], "candidate-1")
        self.assertEqual(execution["event_id"], "event-1")
        self.assertTrue(str(execution["trade_id"]).startswith("trade_"))
        self.assertTrue(str(execution["execution_id"]).startswith("exec_"))
        self.assertEqual(execution["entry_time"], 1_700_000_000_000)
        self.assertEqual(execution["exit_time"], 1_700_000_000_000)
        self.assertEqual(execution["structure_confirmed_time"], 1_699_999_700_000)
        self.assertEqual(execution["feature_cutoff_time"], 1_699_999_940_000)
        self.assertTrue(execution["bar_confirmed"])
        self.assertTrue(execution["no_lookahead_safe"])
        self.assertIn("fee_cost", execution)
        self.assertIn("slippage_cost", execution)
        self.assertIn("funding_cost", execution)


def _candle(index: int, open_price: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 900_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


class _Repository:
    def __init__(self, candles):
        self._candles = tuple(candles)

    def load_range(self, *args, **kwargs):
        return self._candles


if __name__ == "__main__":
    unittest.main()
