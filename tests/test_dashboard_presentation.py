import unittest
from types import SimpleNamespace

from trading_system.dashboard.presentation import (
    label_for,
    localized_rows,
    near_miss_summary,
    full_backtest_summary,
    rejection_reason_top,
    risk_reason_rows,
    signal_funnel_points,
    volume_reason_rows,
)


class DashboardPresentationTests(unittest.TestCase):
    def test_chinese_field_mapping_keeps_unknown_fields_as_original_keys(self):
        self.assertEqual(label_for("net_profit"), "净利润")
        self.assertEqual(label_for("unknown_field"), "unknown_field")
        self.assertEqual(localized_rows(({"symbol": "BTC/USDT", "net_profit": 12.0},))[0]["交易对"], "BTC/USDT")

    def test_signal_funnel_points_use_fixed_stage_order(self):
        points = signal_funnel_points(
            (
                {"windows_checked": 10, "volume_price_rejected": 6, "risk_rejected": 2, "approved_signal": 1},
                {"windows_checked": 5, "volume_price_rejected": 2, "risk_rejected": 1, "approved_signal": 0},
            )
        )

        self.assertEqual([point["key"] for point in points][:3], ["windows_checked", "data_insufficient", "regime_not_computable"])
        self.assertEqual(points[0]["value"], 15)
        self.assertEqual(points[5]["value"], 8)
        self.assertEqual(points[-1]["value"], 1)

    def test_rejection_reason_top_counts_reason_codes(self):
        rows = (
            {"reason_codes": ("volume_price:cooldown", "stop_distance_too_far")},
            {"reason_codes": ("volume_price:cooldown",)},
        )

        self.assertEqual(rejection_reason_top(rows)[0], {"reason": "volume_price:cooldown", "count": 2})

    def test_volume_and_risk_reason_rows_summarize_counts(self):
        self.assertEqual(volume_reason_rows(({"reject": 2, "cooldown": 3, "anomaly": 1, "confirm": 4},))[1]["count"], 3)
        self.assertEqual(
            risk_reason_rows(({"reason_code": "stop_distance_too_far", "candidate_count": 7},))[0],
            {"reason": "stop_distance_too_far", "count": 7},
        )

    def test_near_miss_summary_sorts_by_distance(self):
        rows = (
            {"symbol": "ETH/USDT", "distance_to_pass": 0.4},
            {"symbol": "BTC/USDT", "distance_to_pass": 0.1},
        )

        self.assertEqual(near_miss_summary(rows)[0]["symbol"], "BTC/USDT")

    def test_full_backtest_summary_uses_ranking_rows_as_primary_source(self):
        snapshot = SimpleNamespace(
            summary={"net_profit": 500.0},
            ranking_rows=(
                {
                    "symbol": "BTC/USDT",
                    "timeframe_group": "B",
                    "strategy_family": "liquidity_sweep_reclaim",
                    "setup_type": "liquidity_reversal",
                    "trade_count": 12,
                    "max_drawdown": 0.02,
                    "win_rate": 0.55,
                    "profit_factor": 1.8,
                },
            ),
        )

        cards = full_backtest_summary(snapshot)

        self.assertEqual(cards[0].title, "最佳组合")
        self.assertIn("BTC/USDT", str(cards[0].value))
        self.assertEqual(cards[1].value, "500")
        self.assertEqual(cards[3].value, "2.00%")


if __name__ == "__main__":
    unittest.main()
