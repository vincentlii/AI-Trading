import unittest
from pathlib import Path

from trading_system.strategies import get_strategy, list_strategies
from trading_system.strategies.base import (
    Strategy,
    StrategyContext,
    StrategyMetadata,
    StrategySignal,
)
from trading_system.strategies.registry import StrategyRegistry


class StrategyRegistryTests(unittest.TestCase):
    def test_default_registry_lists_initial_strategy_plugin(self):
        strategies = list_strategies()

        self.assertEqual(tuple(item.name for item in strategies), ("trend_price_volume",))
        self.assertEqual(tuple(item.version for item in strategies), ("v1",))

    def test_initial_strategy_metadata_points_to_strategy_document(self):
        strategy = get_strategy("trend_price_volume", version="v1")

        self.assertEqual(strategy.metadata.name, "trend_price_volume")
        self.assertEqual(strategy.metadata.version, "v1")
        self.assertEqual(strategy.metadata.required_timeframe_profile_keys, ("A", "B", "C"))
        self.assertIn("regime.trend_state", strategy.metadata.required_indicators)
        self.assertTrue(strategy.metadata.documentation_path.endswith("strategy.md"))
        self.assertTrue(Path(strategy.metadata.documentation_path).exists())

    def test_initial_strategy_emits_no_signals_without_required_market_context(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
        )

        self.assertEqual(strategy.generate_signals(context), ())

    def test_registry_rejects_duplicate_strategy_name_and_version(self):
        class DummyStrategy(Strategy):
            metadata = StrategyMetadata(
                name="duplicate",
                version="v1",
                description="dummy",
                required_timeframe_profile_keys=("B",),
                required_indicators=(),
                documentation_path="",
            )

            def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
                return ()

        registry = StrategyRegistry()
        registry.register(DummyStrategy())

        with self.assertRaises(ValueError):
            registry.register(DummyStrategy())


if __name__ == "__main__":
    unittest.main()
