from __future__ import annotations

from trading_system.strategies.base import Strategy, StrategyMetadata


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[tuple[str, str], Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        key = strategy.metadata.key
        if key in self._strategies:
            name, version = key
            raise ValueError(f"Strategy is already registered: {name}@{version}")
        self._strategies[key] = strategy

    def get(self, name: str, *, version: str = "v1") -> Strategy:
        key = (name, version)
        try:
            return self._strategies[key]
        except KeyError as error:
            raise KeyError(f"Unknown strategy: {name}@{version}") from error

    def list_metadata(self) -> tuple[StrategyMetadata, ...]:
        return tuple(
            self._strategies[key].metadata
            for key in sorted(self._strategies)
        )
