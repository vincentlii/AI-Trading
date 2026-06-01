import unittest

from trading_system.reports.candidate_anatomy import build_candidate_anatomy_rows, summarize_candidate_anatomy
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle


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


class CandidateAnatomyAuditTests(unittest.TestCase):
    def test_anatomy_rows_infer_structure_age_stop_formula_and_bucket(self):
        repository = CandleRepository()
        structure = (
            _candle(11, 105.0, 106.0, 100.0, 104.0),
            _candle(12, 104.0, 105.0, 101.0, 103.0),
            _candle(13, 103.0, 104.0, 99.0, 103.0),
            _candle(14, 103.0, 104.0, 102.0, 103.0),
            _candle(15, 103.0, 104.0, 102.0, 103.0),
            _candle(16, 103.0, 104.0, 97.0, 101.0),
        )
        entry = tuple(_candle(index, 100.0, 100.25, 99.75, 100.0) for index in range(1, 20))
        repository.save_many("BTC-USDT-SWAP", "1H", structure, inst_type="SWAP")
        repository.save_many("BTC-USDT-SWAP", "15m", entry, inst_type="SWAP")
        repository.save_many("BTC-USDT-SWAP", "4H", entry, inst_type="SWAP")
        filter_row = {
            "candidate_id": "candidate-1",
            "timestamp_ms": structure[-1].timestamp_ms,
            "asset": "BTC",
            "symbol": "BTC/USDT",
            "venue": "okx",
            "inst_id": "BTC-USDT-SWAP",
            "inst_type": "SWAP",
            "profile": "B",
            "setup": "liquidity_reversal",
            "direction": "long",
            "long_or_short": "long",
            "candidate_generation_reason": "downside_sweep_structure_event",
            "structure_level": 99.0,
            "sweep_extreme_price": 97.0,
            "reclaim_price": 101.0,
            "entry_reference_price": 100.0,
            "entry_price": 100.0,
            "stop_price": 96.7,
            "target_price": 106.6,
            "atr_value": 2.0,
            "invalidation_mode": "structure_extreme_buffer",
            "invalidation_buffer_atr": 0.15,
            "wick_ratio": 0.5,
            "sweep_atr_multiple": 1.0,
            "rolling_rvol": 2.0,
            "tod_dow_rvol": 2.0,
            "volume_baseline_mode": "tod_dow_log_ewma",
            "volume_bucket_sample_count": 30,
            "used_fallback_volume_baseline": False,
            "reclaim_rvol": 1.3,
            "reclaim_quality": "acceptable_reclaim",
            "reclaim_bars": 1,
            "choch_detected": True,
            "bos_detected": False,
            "trend_state": "MEAN_REVERTING_TRANSITION",
            "trend_direction": "long",
            "reject_stage": "risk_filter",
            "reject_reason": "stop_distance_too_far",
            "formal_approved": False,
            "shadow_approved_5": True,
            "shadow_approved_8": True,
            "risk_reason_codes": ["stop_distance_too_far"],
        }

        rows = build_candidate_anatomy_rows(repository=repository, filter_rows=(filter_row,))
        summary = summarize_candidate_anatomy(rows)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["structure_level_type"], "range_low")
        self.assertEqual(row["structure_level_age_bars"], 3)
        self.assertEqual(row["reclaim_rvol_tier"], "acceptable_reclaim")
        self.assertEqual(row["stop_formula_used"], "structure_extreme_buffer_long")
        self.assertEqual(row["stop_bucket"], "borderline_stop")
        self.assertEqual(summary["stop_buckets"]["borderline_stop"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
