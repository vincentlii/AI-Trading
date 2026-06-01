import unittest

from research_pipeline.adapters.liquidity_reversal import LiquidityReversalAdapter


class LiquidityReversalAdapterRegistrationTest(unittest.TestCase):
    def test_adapter_metadata_marks_proposal_only_and_supported_scope(self) -> None:
        adapter = LiquidityReversalAdapter()
        metadata = adapter.metadata()

        self.assertEqual(metadata["name"], "liquidity_reversal")
        self.assertEqual(metadata["strategy_family"], "price_action_volume")
        self.assertEqual(metadata["status"], "proposal_only")
        self.assertTrue(metadata["proposal_only"])
        self.assertFalse(metadata["formal_conclusion_enabled"])
        self.assertEqual(metadata["supported_assets"], ["BTC", "ETH"])
        self.assertEqual(metadata["supported_markets"], ["SWAP"])
        self.assertEqual(metadata["supported_profiles"], ["B", "C"])
        self.assertEqual(metadata["primary_combo"], "displacement_after_reclaim")
        self.assertIn("notional_capped_risk_based", metadata["sizing_models"])

    def test_real_strategy_methods_remain_disabled_in_pr10(self) -> None:
        adapter = LiquidityReversalAdapter()

        for method_name in (
            "generate_candidates",
            "filter_replay",
            "run_sizing_engine",
            "run_execution",
        ):
            with self.subTest(method_name=method_name):
                with self.assertRaises(NotImplementedError):
                    getattr(adapter, method_name)()


if __name__ == "__main__":
    unittest.main()
