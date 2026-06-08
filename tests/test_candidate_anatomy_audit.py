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
    def test_compression_expansion_anatomy_classifies_stop_margin_near_miss(self):
        filter_row = {
            "candidate_id": "ce-1",
            "timestamp_ms": 1_700_000_000_000,
            "asset": "ETH",
            "symbol": "ETH/USDT",
            "venue": "okx",
            "inst_id": "ETH-USDT-SWAP",
            "inst_type": "SWAP",
            "profile": "C",
            "setup": "compression_expansion",
            "direction": "long",
            "row_type": "candidate",
            "compression_start_time": 1_699_999_000_000,
            "compression_end_time": 1_699_999_900_000,
            "breakout_time": 1_699_999_960_000,
            "confirmation_time": 1_700_000_000_000,
            "compression_high": 100.8,
            "compression_low": 99.8,
            "compression_midpoint": 100.3,
            "compression_box_height": 1.0,
            "compression_box_atr": 0.5,
            "breakout_displacement_atr": 1.6,
            "breakout_close_location": 0.9,
            "breakout_body_pct": 0.88,
            "breakout_rvol": 2.1,
            "midpoint_hold": True,
            "boundary_hold": True,
            "retest_hold": True,
            "retest_depth_atr": 0.1,
            "bars_to_retest": 1,
            "entry_price": 102.85,
            "entry_reference_price": 102.85,
            "stop_price": 102.35,
            "target_price": 103.85,
            "atr_value": 2.0,
            "entry_to_stop": 0.5,
            "stop_distance_atr": 0.25,
            "stop_anchor_type": "breakout_midpoint_or_box_edge",
            "stop_buffer_atr": 0.0,
            "target_space": 1.0,
            "gross_RR": 2.0,
            "estimated_cost_r": 0.15,
            "formal_approved": False,
            "reject_stage": "risk_filter",
            "reject_reason": "stop_distance_too_near",
            "risk_reason_codes": ["stop_distance_too_near"],
            "margin_required": 120000.0,
            "notional": 120000.0,
            "quantity": 100.0,
            "portfolio_heat": 0.005,
        }

        rows = build_candidate_anatomy_rows(repository=None, filter_rows=(filter_row,))
        summary = summarize_candidate_anatomy(rows)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["setup"], "compression_expansion")
        self.assertEqual(row["risk_reject_reason"], "stop_distance_too_near")
        self.assertEqual(row["stop_distance_too_near_attribution"], "stop_anchor_too_close")
        self.assertEqual(row["margin_reject_attribution"], "stop_distance_position_size_coupling")
        self.assertEqual(row["near_miss_shadow"], "reasonable_near_miss")
        self.assertEqual(row["candidate_quality_tag"], "reasonable_near_miss")
        self.assertEqual(summary["near_miss_shadow_counts"]["reasonable_near_miss"], 1)
        self.assertEqual(summary["risk_reject_reason_counts"]["stop_distance_too_near"], 1)

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
