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

    def caption(self, value):
        self.captions.append(value)

    def columns(self, count):
        columns = [FakeColumn() for _ in range(count)]
        self.columns_created.append(columns)
        return columns


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


if __name__ == "__main__":
    unittest.main()
