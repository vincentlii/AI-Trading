import unittest
from types import SimpleNamespace

import app


class FakeColumn:
    def __init__(self):
        self.metrics = []

    def metric(self, label, value):
        self.metrics.append((label, value))


class FakeStreamlit:
    def __init__(self):
        self.captions = []
        self.columns_created = []
        self.markdowns = []

    def caption(self, value):
        self.captions.append(value)

    def columns(self, count):
        columns = [FakeColumn() for _ in range(count)]
        self.columns_created.append(columns)
        return columns

    def markdown(self, value, *, unsafe_allow_html=False):
        self.markdowns.append((value, unsafe_allow_html))


class P5DashboardAppTests(unittest.TestCase):
    def test_overview_renders_expected_summary_metrics(self):
        fake_st = FakeStreamlit()
        snapshot = SimpleNamespace(
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
            },
        )

        app._render_overview(fake_st, snapshot)

        self.assertEqual(fake_st.captions, ["btc_eth_p4_4_v1 | abc123"])
        labels = [column.metrics[0][0] for column in fake_st.columns_created[0]]
        self.assertEqual(
            labels,
            ["排名组", "候选", "辅助", "淘汰", "净利润", "数据失败", "跳过扫描", "Proposal"],
        )

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


if __name__ == "__main__":
    unittest.main()
