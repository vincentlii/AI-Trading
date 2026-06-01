import unittest

from research_pipeline.adapters.liquidity_reversal import LiquidityReversalAdapter


class LiquidityReversalAdapterSkeletonTest(unittest.TestCase):
    def test_adapter_exposes_identity_and_baseline_keys_without_running_strategy(self) -> None:
        adapter = LiquidityReversalAdapter()

        self.assertEqual(adapter.name, "liquidity_reversal")
        self.assertTrue(adapter.adapter_version)
        self.assertIn("fresh_candidates", adapter.baseline_metric_keys())
        self.assertIn("displacement_after_reclaim", adapter.baseline_combo_keys())
        self.assertEqual(adapter.required_features(), [])

        with self.assertRaises(NotImplementedError):
            adapter.generate_candidates()


if __name__ == "__main__":
    unittest.main()
