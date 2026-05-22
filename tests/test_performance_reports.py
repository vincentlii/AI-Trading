import math
import unittest

from trading_system.backtest.execution import BacktestRunResult, BacktestSummary, EquityPoint
from trading_system.backtest.scanner import BacktestProfileScan, BacktestScanResult, BacktestScanTarget
from trading_system.reports.performance import build_performance_report


class PerformanceReportTests(unittest.TestCase):
    def test_report_keeps_project_metrics_primary_when_optional_libraries_are_missing(self):
        result = BacktestRunResult(
            decisions=(),
            fills=(),
            equity_curve=(
                EquityPoint(timestamp_ms=None, equity=100_000.0, drawdown_pct=0.0),
                EquityPoint(timestamp_ms=1, equity=101_000.0, drawdown_pct=0.0),
                EquityPoint(timestamp_ms=2, equity=100_500.0, drawdown_pct=0.0049504950495049506),
            ),
            summary=BacktestSummary(
                net_profit=500.0,
                max_drawdown=0.0049504950495049506,
                win_rate=0.5,
                profit_loss_ratio=2.0,
                profit_factor=2.0,
                average_holding_bars=3.0,
                expectancy_per_trade=250.0,
                cost_to_gross_profit_ratio=0.1,
                trade_count=2,
                gross_profit=1_000.0,
                gross_loss=-500.0,
                total_cost=100.0,
            ),
        )
        scan_result = BacktestScanResult(
            profile_runs=(
                BacktestProfileScan(
                    target=BacktestScanTarget(canonical_symbol="BTC/USDT", inst_id="BTC-USDT"),
                    profile_key="A",
                    status="completed",
                    reason_codes=(),
                    candle_counts_by_timeframe={"5m": 3},
                    signal_count=2,
                    result=result,
                ),
            ),
            group_summaries=(),
        )

        report = build_performance_report(scan_result)

        self.assertEqual(report.summary["performance_runs"], 1)
        self.assertEqual(report.metric_rows[0]["symbol"], "BTC/USDT")
        self.assertEqual(report.metric_rows[0]["timeframe_group"], "A")
        self.assertEqual(report.metric_rows[0]["primary_metric_source"], "project_backtest_summary")
        self.assertEqual(report.metric_rows[0]["net_profit"], 500.0)
        self.assertEqual(report.metric_rows[0]["trade_count"], 2)
        self.assertGreater(report.metric_rows[0]["event_sharpe"], 0.0)
        self.assertTrue(math.isclose(report.drawdown_rows[0]["max_drawdown"], result.summary.max_drawdown))
        self.assertIn(report.library_rows[0]["status"], {"available", "missing"})
        self.assertEqual(report.artifact_rows[0]["status"], "not_generated")


if __name__ == "__main__":
    unittest.main()
