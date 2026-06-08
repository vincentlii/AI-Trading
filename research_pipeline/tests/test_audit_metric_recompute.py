import unittest

from research_pipeline.core.audit.metrics_recompute import comparison_rows, recompute_metrics


class AuditMetricRecomputeTest(unittest.TestCase):
    def test_profit_factor_is_undefined_when_there_are_no_losses(self) -> None:
        recomputed = recompute_metrics(
            [
                {"row_type": "closed_trade", "closed_trade": True, "net_R": 0.2},
                {"row_type": "closed_trade", "closed_trade": True, "net_R": 0.4},
            ]
        )

        self.assertIsNone(recomputed["profit_factor"])

    def test_duplicate_event_count_uses_event_id_when_event_key_missing(self) -> None:
        recomputed = recompute_metrics(
            [
                {"row_type": "closed_trade", "closed_trade": True, "cost_tier": "base", "event_id": "ce-1", "direction": "long", "net_R": 0.2},
                {"row_type": "closed_trade", "closed_trade": True, "cost_tier": "base", "event_id": "ce-2", "direction": "long", "net_R": -0.1},
            ]
        )

        self.assertEqual(recomputed["duplicate_event_count"], 0)

    def test_metric_mismatch_fails(self) -> None:
        recomputed = recompute_metrics(
            [
                {"closed_trade": True, "net_R": 1.0, "mfe_R": 1.2, "mae_R": 0.1},
                {"closed_trade": False, "net_R": 100.0},
            ]
        )
        rows = comparison_rows(
            scope="x",
            cost_tier="base",
            reported={"closed_trades": 2, "net_R_avg": 1.0},
            recomputed=recomputed,
            source_artifact="rows.jsonl",
        )
        closed = next(row for row in rows if row["metric_name"] == "closed_trades")

        self.assertFalse(closed["passed"])
        self.assertEqual(closed["recomputed_value"], 1)


if __name__ == "__main__":
    unittest.main()
