from __future__ import annotations

from trading_system.strategies.base import (
    Strategy,
    StrategyContext,
    StrategyMetadata,
    StrategySignal,
)
from trading_system.strategies.registry import StrategyRegistry
from trading_system.strategies.trend_price_volume_v1.strategy import TrendPriceVolumeStrategy


_DEFAULT_REGISTRY = StrategyRegistry()
_DEFAULT_REGISTRY.register(TrendPriceVolumeStrategy())


def list_strategies() -> tuple[StrategyMetadata, ...]:
    return _DEFAULT_REGISTRY.list_metadata()


def get_strategy(name: str, *, version: str = "v1") -> Strategy:
    return _DEFAULT_REGISTRY.get(name, version=version)


__all__ = (
    "Strategy",
    "StrategyContext",
    "StrategyMetadata",
    "StrategyRegistry",
    "StrategySignal",
    "get_strategy",
    "list_strategies",
)
