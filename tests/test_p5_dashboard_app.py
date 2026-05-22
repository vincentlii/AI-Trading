import unittest
from types import SimpleNamespace

import app


class FakeColumn:
    def __init__(self):
        self.metrics = []

    def metric(self, label, value):
        self.metrics.append((label, value))


class FakeTab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self):
        self.captions = []
        self.columns_created = []
        self.expanders = []
        self.markdowns = []
        self.plotly_charts = []
        self.subheaders = []
        self.tabs_created = []

    def caption(self, value):
        self.captions.append(value)

    def columns(self, count):
        columns = [FakeColumn() for _ in range(count)]
        self.columns_created.append(columns)
        return columns

    def markdown(self, value, *, unsafe_allow_html=False):
        self.markdowns.append((value, unsafe_allow_html))

    def plotly_chart(self, figure, *, use_container_width=False, config=None, key=None):
        self.plotly_charts.append((figure, use_container_width, config, key))

    def subheader(self, value):
        self.subheaders.append(value)

    def tabs(self, labels):
        self.tabs_created.append(tuple(labels))
        return [FakeTab() for _ in labels]

    def expander(self, label, *, expanded=False):
        self.expanders.append((label, expanded))
        return FakeTab()


class P5DashboardAppTests(unittest.TestCase):
    def _snapshot(self):
        return SimpleNamespace(
            config_version="btc_eth_p4_4_v1",
            config_fingerprint="abc123",
            summary={
                "ranked_groups": 6,
                "candidates": 4,
                "supporting_only": 1,
                "rejected": 1,
                "net_profit": 123.456,
                "quality_failures": 0,
                "skipped_runs": 2,
                "proposals": 3,
                "profile_can_run": 6,
                "approved_signals": 0,
                "near_miss_candidates": 5,
                "dashboard_max_entry_windows": 200,
            },
            ranking_rows=(
                {
                    "rank": 1,
                    "status": "candidate",
                    "symbol": "BTC/USDT",
                    "timeframe_group": "B",
                    "strategy_family": "liquidity_sweep_reclaim",
                    "setup_type": "liquidity_reversal",
                    "trade_count": 12,
                    "net_profit": 500.0,
                    "max_drawdown": 0.02,
                    "win_rate": 0.55,
                    "profit_factor": 1.8,
                    "expectancy_per_trade": 41.6,
                    "fee_to_gross_profit_ratio": 0.08,
                },
            ),
            quality_rows=({"symbol": "BTC/USDT", "bar": "1D", "status": "pass", "row_count": 300},),
            skipped_run_rows=(),
            proposal_rows=({"proposal_id": "p1", "status": "loaded", "auto_apply": False},),
            performance_metric_rows=(
                {
                    "symbol": "BTC/USDT",
                    "timeframe_group": "B",
                    "primary_metric_source": "project_backtest_summary",
                    "trade_count": 12,
                    "net_profit": 500.0,
                    "max_drawdown": 0.02,
                    "win_rate": 0.55,
                    "profit_factor": 1.8,
                    "expectancy_per_trade": 41.6,
                },
            ),
            performance_library_rows=({"library": "quantstats", "status": "missing"},),
            performance_artifact_rows=({"library": "quantstats", "status": "not_generated"},),
            data_coverage_rows=({"symbol": "BTC/USDT", "bar": "1D", "row_count": 300, "next_action": "ready"},),
            profile_coverage_rows=({"symbol": "BTC/USDT", "profile": "B", "can_run": True},),
            signal_funnel_rows=(
                {
                    "symbol": "BTC/USDT",
                    "profile": "B",
                    "windows_checked": 200,
                    "data_insufficient": 0,
                    "regime_not_computable": 0,
                    "regime_rejected": 0,
                    "price_action_rejected": 10,
                    "volume_price_rejected": 170,
                    "target_space_insufficient": 0,
                    "risk_rejected": 20,
                    "approved_signal": 0,
                    "reason_codes": ("volume_price:cooldown", "stop_distance_too_far"),
                },
            ),
            volume_rejection_rows=({"symbol": "BTC/USDT", "profile": "B", "reject": 2, "cooldown": 3, "anomaly": 1, "confirm": 1},),
            volume_distribution_rows=({"symbol": "BTC/USDT", "profile": "B", "volume_ratio_median": 1.2},),
            risk_rejection_rows=({"symbol": "BTC/USDT", "profile": "B", "reason_code": "stop_distance_too_far", "candidate_count": 20},),
            near_miss_rows=({"symbol": "BTC/USDT", "near_miss_type": "volume_confirm_threshold", "distance_to_pass": 0.01},),
        )

    def test_tabs_are_chinese_diagnostic_cockpit_sections(self):
        self.assertEqual(
            app.DASHBOARD_TABS,
            (
                "首页",
                "信号诊断",
                "策略排名",
                "风控分析",
                "完整回测",
                "绩效报告",
                "数据质量",
                "Proposal 队列",
                "系统说明",
            ),
        )

    def test_overview_renders_expected_summary_metrics(self):
        fake_st = FakeStreamlit()
        snapshot = self._snapshot()

        app._render_overview(fake_st, snapshot)

        self.assertIn("完整回测主口径", fake_st.markdowns[0][0])
        self.assertIn("近期 200 window 诊断", fake_st.markdowns[0][0])
        labels = [column.metrics[0][0] for column in fake_st.columns_created[0]]
        self.assertEqual(
            labels,
            ["系统状态", "数据质量", "可运行 Profile", "量价拒绝率", "风控拒绝率", "最终信号", "Near Miss", "完整回测净利润"],
        )
        self.assertGreaterEqual(len(fake_st.plotly_charts), 1)
        self.assertTrue(any("完整回测结论摘要" in item[0] for item in fake_st.markdowns))
        self.assertTrue(any("指标说明" in item[0] for item in fake_st.markdowns))
        self.assertTrue(any("指标名称" in item[0] and "RVOL" in item[0] for item in fake_st.markdowns))

    def test_plotly_charts_use_unique_keys_across_tabs(self):
        fake_st = FakeStreamlit()
        snapshot = self._snapshot()

        app._render_overview(fake_st, snapshot)
        app._render_diagnostics(fake_st, snapshot)
        app._render_risk_analysis(fake_st, snapshot)

        keys = [chart[3] for chart in fake_st.plotly_charts]
        self.assertTrue(all(keys))
        self.assertEqual(len(keys), len(set(keys)))

    def test_table_renderer_uses_html_without_dataframe_dependency(self):
        fake_st = FakeStreamlit()

        app._render_table(fake_st, ({"symbol": "BTC/USDT", "reason_codes": ("a", "b"), "score": 1.23456789},))

        self.assertEqual(len(fake_st.markdowns), 1)
        markup, unsafe = fake_st.markdowns[0]
        self.assertTrue(unsafe)
        self.assertIn("<table", markup)
        self.assertIn("BTC/USDT", markup)
        self.assertIn("a, b", markup)
        self.assertIn("1.23457", markup)

    def test_performance_report_renderer_uses_snapshot_rows(self):
        fake_st = FakeStreamlit()
        snapshot = self._snapshot()

        app._render_performance_report(fake_st, snapshot)

        self.assertEqual(fake_st.subheaders, ["绩效指标", "第三方库状态", "报告 Artifact"])
        self.assertEqual(len(fake_st.markdowns), 3)
        self.assertIn("project_backtest_summary", fake_st.markdowns[0][0])
        self.assertIn("quantstats", fake_st.markdowns[1][0])

    def test_diagnostics_renderer_uses_data_coverage_and_signal_funnel_rows(self):
        fake_st = FakeStreamlit()
        snapshot = self._snapshot()

        app._render_diagnostics(fake_st, snapshot)

        self.assertEqual(
            fake_st.subheaders,
            [
                "数据覆盖",
                "Profile 覆盖",
                "信号漏斗",
                "量价拒绝细分",
                "量价 RVOL 分布",
                "风控拒绝细分",
                "最接近通过候选",
            ],
        )
        self.assertEqual(len(fake_st.markdowns), 7)
        self.assertIn("row_count", fake_st.markdowns[0][0])
        self.assertIn("data_insufficient", fake_st.markdowns[2][0])
        self.assertIn("volume_ratio_median", fake_st.markdowns[4][0])
        self.assertIn("stop_distance_too_far", fake_st.markdowns[5][0])
        self.assertGreaterEqual(len(fake_st.plotly_charts), 2)

    def test_full_backtest_renderer_keeps_details_behind_expander(self):
        fake_st = FakeStreamlit()

        app._render_full_backtest(fake_st, self._snapshot())

        self.assertTrue(any("完整回测结论摘要" in item[0] for item in fake_st.markdowns))
        self.assertEqual(fake_st.expanders[0][0], "加载完整回测明细")
        self.assertIn("rank", fake_st.markdowns[-1][0])

    def test_system_info_renderer_explains_read_only_and_metric_scopes(self):
        fake_st = FakeStreamlit()

        app._render_system_info(fake_st, self._snapshot())

        text = "\n".join(item[0] for item in fake_st.markdowns)
        self.assertIn("只读看板", text)
        self.assertIn("近期 200 window", text)
        self.assertIn("P4 完整回测", text)
        self.assertIn("Proposal", text)

    def test_diagnostics_renderer_tolerates_old_cached_snapshot_without_p5_2_rows(self):
        fake_st = FakeStreamlit()
        snapshot = SimpleNamespace(
            data_coverage_rows=({"symbol": "BTC/USDT", "bar": "1D", "row_count": 300},),
            profile_coverage_rows=(),
            signal_funnel_rows=(),
        )

        app._render_diagnostics(fake_st, snapshot)

        self.assertEqual(len(fake_st.markdowns), 1)
        self.assertEqual(fake_st.captions, ["暂无数据", "暂无数据", "暂无数据", "暂无数据", "暂无数据", "暂无数据"])


if __name__ == "__main__":
    unittest.main()
