import unittest

from research_pipeline.adapters.liquidity_reversal import LiquidityReversalAdapter
from research_pipeline.registry.strategy_registry import StrategyRegistry, default_strategy_registry


class StrategyRegistryTest(unittest.TestCase):
    def test_registry_registers_and_returns_liquidity_reversal_adapter(self) -> None:
        registry = StrategyRegistry()
        adapter = LiquidityReversalAdapter()
        registry.register(adapter)

        self.assertIs(registry.get("liquidity_reversal"), adapter)
        self.assertEqual(registry.list_strategies()[0]["name"], "liquidity_reversal")

    def test_default_registry_contains_liquidity_reversal_as_proposal_only(self) -> None:
        adapter = default_strategy_registry().get("liquidity_reversal")

        self.assertIsInstance(adapter, LiquidityReversalAdapter)
        self.assertTrue(adapter.proposal_only)
        self.assertFalse(adapter.formal_conclusion_enabled)

    def test_unknown_strategy_has_clear_error(self) -> None:
        registry = StrategyRegistry()

        with self.assertRaisesRegex(ValueError, "Unknown strategy"):
            registry.get("missing_strategy")


if __name__ == "__main__":
    unittest.main()
