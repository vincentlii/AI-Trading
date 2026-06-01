import unittest

from research_pipeline.core.audit.lineage import build_lineage_rows


class AuditLineageTest(unittest.TestCase):
    def test_performance_lineage_uses_closed_trade_rows(self) -> None:
        rows = build_lineage_rows(
            source_artifact="combo_rows.jsonl",
            reported_variant={"closed_trades": 2, "selected_without_closed_count": 3, "selected_trades": 5},
        )
        net = next(row for row in rows if row["metric_name"] == "net_R_avg")
        selected = next(row for row in rows if row["metric_name"] == "selected_trades")

        self.assertEqual(net["source_row_type"], "closed_trade")
        self.assertTrue(net["can_enter_performance_metrics"])
        self.assertFalse(selected["can_enter_performance_metrics"])


if __name__ == "__main__":
    unittest.main()
