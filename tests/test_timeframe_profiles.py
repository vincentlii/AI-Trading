import unittest

from trading_system.timeframe_profiles import (
    BacktestResultSummary,
    evaluate_profile_result,
    get_profile,
    list_default_profiles,
    rank_profile_results,
    required_backtest_metrics,
)


class TimeframeProfileTests(unittest.TestCase):
    def test_default_profiles_define_three_backtest_layers_without_1m(self):
        profiles = list_default_profiles()

        self.assertEqual([profile.key for profile in profiles], ["B", "C", "A"])
        self.assertEqual(get_profile("A").timeframes, ("5m", "15m", "1h"))
        self.assertEqual(get_profile("B").timeframes, ("15m", "1h", "4h"))
        self.assertEqual(get_profile("C").timeframes, ("1h", "4h", "1d"))
        self.assertNotIn("1m", {tf for profile in profiles for tf in profile.timeframes})

    def test_asset_ranking_keeps_standard_swing_as_primary_candidate(self):
        btc_profile = get_profile("B")
        xaut_profile = get_profile("B")

        self.assertEqual(btc_profile.priority_for_asset("BTC/USDT"), 1)
        self.assertEqual(xaut_profile.priority_for_asset("XAUT/USDT"), 1)
        self.assertGreater(get_profile("A").priority_for_asset("XAUT/USDT"), xaut_profile.priority_for_asset("XAUT/USDT"))

    def test_required_backtest_metrics_match_strategy_acceptance_rules(self):
        metrics = required_backtest_metrics()

        self.assertEqual(
            metrics,
            (
                "net_profit",
                "max_drawdown",
                "win_rate",
                "profit_loss_ratio",
                "profit_factor",
                "average_holding_time",
                "expectancy_per_trade",
                "fee_to_gross_profit_ratio",
            ),
        )

    def test_fast_intraday_profile_is_rejected_when_costs_eat_gross_profit(self):
        result = BacktestResultSummary(
            profile_key="A",
            symbol="BTC/USDT",
            gross_profit=1000,
            net_profit=680,
            total_fees=320,
            trade_count=240,
        )

        decision = evaluate_profile_result(result)

        self.assertEqual(decision.status, "rejected")
        self.assertIn("cost", decision.reasons[0])

    def test_slow_trend_profile_is_demoted_when_sample_size_is_too_small(self):
        result = BacktestResultSummary(
            profile_key="C",
            symbol="XAUT/USDT",
            gross_profit=1500,
            net_profit=1300,
            total_fees=80,
            trade_count=12,
        )

        decision = evaluate_profile_result(result, min_trades_for_primary=30)

        self.assertEqual(decision.status, "supporting_only")
        self.assertIn("sample size", decision.reasons[0])

    def test_ranking_prefers_eligible_profitable_profile_over_rejected_or_supporting_layers(self):
        results = (
            BacktestResultSummary(
                profile_key="A",
                symbol="BTC/USDT",
                gross_profit=3000,
                net_profit=2100,
                total_fees=900,
                trade_count=500,
                max_drawdown=0.08,
                profit_factor=1.6,
                expectancy_per_trade=4.2,
            ),
            BacktestResultSummary(
                profile_key="B",
                symbol="BTC/USDT",
                gross_profit=2000,
                net_profit=1400,
                total_fees=120,
                trade_count=80,
                max_drawdown=0.05,
                profit_factor=1.9,
                expectancy_per_trade=17.5,
            ),
            BacktestResultSummary(
                profile_key="C",
                symbol="BTC/USDT",
                gross_profit=2400,
                net_profit=1800,
                total_fees=80,
                trade_count=10,
                max_drawdown=0.06,
                profit_factor=2.1,
                expectancy_per_trade=180.0,
            ),
        )

        ranked = rank_profile_results(results, min_trades_for_primary=30)

        self.assertEqual([item.result.profile_key for item in ranked], ["B", "C", "A"])
        self.assertEqual(ranked[0].decision.status, "candidate")
        self.assertEqual(ranked[-1].decision.status, "rejected")


if __name__ == "__main__":
    unittest.main()
