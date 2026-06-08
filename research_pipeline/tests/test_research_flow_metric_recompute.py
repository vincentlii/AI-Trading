import unittest
from research_pipeline.runners.research_flow_audit import run_research_flow_audit


from research_pipeline.tests.fixture_paths import COMBINED_FIX_DIR as ARTIFACT_DIR


class ResearchFlowMetricRecomputeTest(unittest.TestCase):
    def test_recomputes_variant_b_metrics_from_row_level_combo_artifact(self) -> None:
        result = run_research_flow_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            artifact_index=None,
            registry=None,
            output_dir=None,
        )
        payload = result.as_dict()
        checks = {
            row["metric_name"]: row
            for row in payload["metric_recompute_rows"]
            if row["scope"] == "Variant B - Tier 1 + Positive Tier 2" and row["cost_tier"] == "base"
        }

        self.assertEqual(checks["closed_trades"]["recomputed_value"], 42)
        self.assertAlmostEqual(checks["total_net_R"]["recomputed_value"], 23.25)
        self.assertAlmostEqual(checks["net_R_avg"]["recomputed_value"], 23.25 / 42)
        self.assertTrue(all(row["passed"] for row in checks.values()))


if __name__ == "__main__":
    unittest.main()
