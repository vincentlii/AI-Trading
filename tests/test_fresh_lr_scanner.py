import unittest

from trading_system.config import load_backtest_preset
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.diagnostics.fresh_lr_scanner import scan_fresh_liquidity_reversal


def _candle(index: int, open_price: float, high: float, low: float, close: float, volume: float = 100.0) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=True,
    )


class FreshLiquidityReversalScannerTests(unittest.TestCase):
    def test_minimal_fresh_sweep_reclaim_emits_one_candidate(self):
        repository = CandleRepository()
        preset = load_backtest_preset("configs/presets/btc_eth_swap_proposal.toml")
        structure = (
            _candle(1, 100.0, 101.0, 99.0, 100.0),
            _candle(2, 100.0, 102.0, 100.0, 101.0),
            _candle(3, 101.0, 102.0, 98.0, 100.0),
            _candle(4, 100.0, 103.0, 99.5, 101.5),
        )
        entry = tuple(_candle(index, 101.0, 102.0, 100.0, 101.0) for index in range(1, 8))
        trend = tuple(_candle(index, 90.0, 91.0, 89.0, 90.5) for index in range(1, 230))
        repository.save_many("BTC-USDT-SWAP", "15m", entry, inst_type="SWAP")
        repository.save_many("BTC-USDT-SWAP", "1H", structure, inst_type="SWAP")
        repository.save_many("BTC-USDT-SWAP", "4H", trend, inst_type="SWAP")
        repository.save_many("BTC-USDT-SWAP", "1D", trend, inst_type="SWAP")

        result = scan_fresh_liquidity_reversal(
            repository=repository,
            preset=preset,
            max_entry_windows=20,
            reclaim_windows=(3, 5, 8),
        )

        btc_b = next(row for row in result.summary_rows if row["asset"] == "BTC" and row["profile"] == "B" and row["direction"] == "long" and row["structure_level_source"] == "rolling_range")
        self.assertGreaterEqual(btc_b["active_structure_levels"], 1)
        self.assertEqual(btc_b["sweep_events_count"], 1)
        self.assertEqual(btc_b["reclaim_events_count"], 1)
        self.assertEqual(btc_b["signal_events_count"], 1)
        self.assertEqual(btc_b["fresh_entry_candidates_count"], 1)
        self.assertEqual(result.duplicate_summary["duplicate_candidate_count"], 0)
        candidate = result.candidate_rows[0]
        self.assertEqual(candidate["event_state"], "emitted")
        self.assertEqual(candidate["structure_level_source"], "rolling_range")
        self.assertEqual(candidate["entry_time"], 1_700_000_000_000 + 5 * 60_000)
        self.assertIn("choch_direction", candidate)
        self.assertIn("trend_state", candidate)
        self.assertIn("sweep_rvol_tier", candidate)
        self.assertIn("reclaim_rvol_tier", candidate)
        self.assertIsNotNone(candidate["sweep_rvol"])
        self.assertIsNotNone(candidate["reclaim_rvol"])
        self.assertNotEqual(candidate["sweep_rvol_tier"], "unknown_sweep_rvol")
        self.assertEqual(candidate["reclaim_bars"], 1)
        self.assertTrue(candidate["reclaim_within_1"])
        self.assertIn("displacement_body_atr", candidate)
        self.assertIn("pullback_retest_after_reclaim", candidate)
        self.assertIn("second_push_after_reclaim", candidate)
        self.assertIn("fvg_exists", candidate)
        self.assertIn("fvg_midpoint", candidate)
        self.assertIn("fvg_retest_hit", candidate)
        self.assertIn("choch_strength", candidate)
        self.assertIn("entry_confirmation_missing_reason", candidate)
        self.assertIn("choch_body_atr", candidate)
        self.assertIn("pdh_pdl_tag", candidate)
        self.assertIn("eqh_eql_tag", candidate)
        self.assertIn("utc_hour", candidate)
        self.assertIn("london_open_window", candidate)
        self.assertIn("ny_open_window", candidate)


if __name__ == "__main__":
    unittest.main()
