import unittest

from research_pipeline.core.analytics.edge import EdgeMetrics
from research_pipeline.core.analytics.push_classification import classify_mfe_push


class EdgePushClassificationTest(unittest.TestCase):
    def test_push_classification_uses_expected_thresholds(self) -> None:
        result = classify_mfe_push([0.1, 0.3, 0.49, 0.5, 0.99, 1.0, 1.7])

        self.assertEqual(result.no_push_count, 1)
        self.assertEqual(result.weak_push_count, 2)
        self.assertEqual(result.medium_push_count, 2)
        self.assertEqual(result.strong_push_count, 2)
        self.assertAlmostEqual(result.strong_push_ratio, 2 / 7)

    def test_edge_metrics_from_aggregation_row_preserves_fields(self) -> None:
        metrics = EdgeMetrics.from_mapping(
            {
                "closed_trades": 137,
                "MFE_R_avg": 1.043551147771528,
                "MFE_R_p50": 0.8565525463077062,
                "MFE_R_p75": 1.4837752589513291,
                "MFE_R_p90": 1.8415111132489637,
                "MAE_R_avg": 0.2059803355062397,
                "net_R_avg": 0.3957664252895689,
                "net_R_p50": 0.5159080429275869,
                "net_return_on_notional_avg": 0.01733582865066706,
                "time_cut_exit_rate": 0.2116788321167883,
                "MFE_R_ge_0_5_ratio": 0.781021897810219,
                "MFE_R_ge_1_0_ratio": 0.44525547445255476,
            }
        )

        self.assertEqual(metrics.closed_trades, 137)
        self.assertAlmostEqual(metrics.MFE_R_avg, 1.043551147771528)
        self.assertAlmostEqual(metrics.MFE_ge_0_5_ratio, 0.781021897810219)


if __name__ == "__main__":
    unittest.main()
