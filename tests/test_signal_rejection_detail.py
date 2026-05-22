import unittest

from trading_system.diagnostics.rejection_detail import (
    RejectionDetailEvent,
    classify_volume_rejection,
    summarize_rejection_events,
)


def _event(**overrides) -> RejectionDetailEvent:
    values = {
        "symbol": "BTC/USDT",
        "venue": "okx",
        "inst_type": "SPOT",
        "inst_id": "BTC-USDT",
        "profile": "B",
        "entry_timeframe": "15m",
        "strategy_family": "liquidity_sweep_reclaim",
        "setup_type": "liquidity_reversal",
        "direction": "long",
        "timestamp_ms": 1_700_000_000_000,
        "terminal_stage": "volume_price_rejected",
        "volume_status": "reject",
        "volume_reason": "volume_ratio_below_reject_threshold",
        "volume_ratio": 0.7,
        "latest_volume": 70.0,
        "average_volume": 100.0,
        "price_state": "up_close",
    }
    values.update(overrides)
    return RejectionDetailEvent(**values)


class SignalRejectionDetailTests(unittest.TestCase):
    def test_volume_rejection_reason_classification_splits_threshold_and_price_direction(self):
        self.assertEqual(
            classify_volume_rejection(status="reject", volume_ratio=0.7, price_state="up_close", direction="long"),
            "volume_ratio_below_reject_threshold",
        )
        self.assertEqual(
            classify_volume_rejection(status="cooldown", volume_ratio=1.2, price_state="up_close", direction="long"),
            "volume_ratio_below_confirm_threshold",
        )
        self.assertEqual(
            classify_volume_rejection(status="anomaly", volume_ratio=6.5, price_state="up_close", direction="long"),
            "volume_ratio_above_anomaly_threshold",
        )
        self.assertEqual(
            classify_volume_rejection(status="cooldown", volume_ratio=2.0, price_state="down_close", direction="long"),
            "price_direction_not_accepted",
        )

    def test_volume_rejection_rows_count_statuses_and_reasons_by_group(self):
        snapshot = summarize_rejection_events(
            (
                _event(volume_status="reject", volume_reason="volume_ratio_below_reject_threshold", volume_ratio=0.7),
                _event(volume_status="cooldown", volume_reason="volume_ratio_below_confirm_threshold", volume_ratio=1.2),
                _event(volume_status="anomaly", volume_reason="volume_ratio_above_anomaly_threshold", volume_ratio=6.5),
                _event(
                    terminal_stage="risk_rejected",
                    volume_status="confirm",
                    volume_reason="confirmed",
                    volume_ratio=1.8,
                ),
            )
        )

        self.assertEqual(len(snapshot.volume_rejection_rows), 1)
        row = snapshot.volume_rejection_rows[0]
        self.assertEqual(row["reject"], 1)
        self.assertEqual(row["cooldown"], 1)
        self.assertEqual(row["anomaly"], 1)
        self.assertEqual(row["confirm"], 1)
        self.assertEqual(row["volume_ratio_below_reject_threshold"], 1)
        self.assertEqual(row["volume_ratio_below_confirm_threshold"], 1)
        self.assertEqual(row["volume_ratio_above_anomaly_threshold"], 1)

    def test_volume_distribution_rows_report_percentiles(self):
        snapshot = summarize_rejection_events(
            tuple(_event(volume_ratio=value) for value in (1.0, 2.0, 3.0, 4.0))
        )

        row = snapshot.volume_distribution_rows[0]
        self.assertEqual(row["candidate_count"], 4)
        self.assertEqual(row["volume_ratio_min"], 1.0)
        self.assertEqual(row["volume_ratio_p25"], 1.75)
        self.assertEqual(row["volume_ratio_median"], 2.5)
        self.assertEqual(row["volume_ratio_p75"], 3.25)
        self.assertEqual(row["volume_ratio_max"], 4.0)

    def test_risk_rejection_rows_include_stop_atr_reward_and_cost_r_distribution(self):
        snapshot = summarize_rejection_events(
            (
                _event(
                    terminal_stage="risk_rejected",
                    volume_status="confirm",
                    volume_reason="confirmed",
                    volume_ratio=1.8,
                    risk_reason_codes=("stop_distance_too_far",),
                    stop_distance=6.0,
                    atr=2.0,
                    stop_atr_multiple=3.0,
                    reward_to_risk=1.6,
                    estimated_cost_r=0.1,
                    net_reward_to_risk=1.5,
                    max_stop_atr_multiple=3.0,
                ),
                _event(
                    terminal_stage="risk_rejected",
                    volume_status="confirm",
                    volume_reason="confirmed",
                    volume_ratio=2.1,
                    risk_reason_codes=("stop_distance_too_far",),
                    stop_distance=8.0,
                    atr=2.0,
                    stop_atr_multiple=4.0,
                    reward_to_risk=1.2,
                    estimated_cost_r=0.2,
                    net_reward_to_risk=1.0,
                    max_stop_atr_multiple=3.0,
                ),
            )
        )

        row = snapshot.risk_rejection_rows[0]
        self.assertEqual(row["reason_code"], "stop_distance_too_far")
        self.assertEqual(row["candidate_count"], 2)
        self.assertEqual(row["stop_atr_median"], 3.5)
        self.assertEqual(row["max_stop_atr_multiple"], 3.0)
        self.assertEqual(row["reward_to_risk_median"], 1.4)
        self.assertAlmostEqual(row["estimated_cost_r_median"], 0.15)
        self.assertEqual(row["net_reward_to_risk_median"], 1.25)

    def test_near_miss_rows_surface_candidates_closest_to_confirmation_or_risk_limit(self):
        snapshot = summarize_rejection_events(
            (
                _event(volume_status="cooldown", volume_reason="volume_ratio_below_confirm_threshold", volume_ratio=1.49),
                _event(volume_status="cooldown", volume_reason="volume_ratio_below_confirm_threshold", volume_ratio=1.1),
                _event(
                    terminal_stage="risk_rejected",
                    volume_status="confirm",
                    volume_reason="confirmed",
                    volume_ratio=2.0,
                    risk_reason_codes=("stop_distance_too_far",),
                    stop_atr_multiple=3.05,
                    max_stop_atr_multiple=3.0,
                ),
            )
        )

        self.assertGreaterEqual(len(snapshot.near_miss_rows), 2)
        self.assertEqual(snapshot.near_miss_rows[0]["near_miss_type"], "volume_confirm_threshold")
        self.assertEqual(snapshot.near_miss_rows[0]["volume_ratio"], 1.49)
        self.assertEqual(snapshot.near_miss_rows[1]["near_miss_type"], "risk_stop_atr_limit")


if __name__ == "__main__":
    unittest.main()
