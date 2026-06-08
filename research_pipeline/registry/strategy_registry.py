from __future__ import annotations

from research_pipeline.adapters.breakout_pullback import BreakoutPullbackAdapter
from research_pipeline.adapters.compression_expansion import CompressionExpansionAdapter
from research_pipeline.adapters.base import StrategyAdapter
from research_pipeline.adapters.liquidity_reversal import LiquidityReversalAdapter
from research_pipeline.adapters.trend_continuation import TrendContinuationAdapter


class StrategyRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, StrategyAdapter] = {}

    def register(self, adapter: StrategyAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, strategy_name: str) -> StrategyAdapter:
        try:
            return self._adapters[strategy_name]
        except KeyError as exc:
            known = ", ".join(sorted(self._adapters)) or "none"
            raise ValueError(f"Unknown strategy: {strategy_name}. Registered: {known}") from exc

    def validate_strategy_exists(self, strategy_name: str) -> None:
        self.get(strategy_name)

    def list_strategies(self) -> list[dict[str, object]]:
        rows = []
        for name in sorted(self._adapters):
            adapter = self._adapters[name]
            metadata = adapter.metadata() if hasattr(adapter, "metadata") else {"name": name}
            rows.append(metadata)
        return rows


def default_strategy_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(LiquidityReversalAdapter())
    registry.register(TrendContinuationAdapter())
    registry.register(CompressionExpansionAdapter())
    registry.register(BreakoutPullbackAdapter())
    return registry
