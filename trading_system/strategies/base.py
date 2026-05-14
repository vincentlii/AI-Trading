from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class StrategyMetadata:
    name: str
    version: str
    description: str
    required_timeframe_profile_keys: tuple[str, ...]
    required_indicators: tuple[str, ...]
    documentation_path: str
    supported_symbols: tuple[str, ...] = ()
    setup_types: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return (self.name, self.version)


@dataclass(frozen=True)
class StrategyContext:
    symbol: str
    venue: str
    timeframe_group: str
    candles_by_timeframe: Mapping[str, tuple[object, ...]] = field(default_factory=dict)
    features: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategySignal:
    strategy_name: str
    strategy_version: str
    setup_type: str
    symbol: str
    venue: str
    timeframe_group: str
    direction: str
    entry_zone: object | None = None
    invalidation_level: float | None = None
    target_hint: object | None = None
    trend_evidence: Mapping[str, object] = field(default_factory=dict)
    price_action_evidence: Mapping[str, object] = field(default_factory=dict)
    volume_price_evidence: Mapping[str, object] = field(default_factory=dict)
    risk_profile: Mapping[str, object] = field(default_factory=dict)
    explanation_payload: Mapping[str, object] = field(default_factory=dict)


class Strategy(ABC):
    metadata: StrategyMetadata

    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        raise NotImplementedError

    def build_explanation_payload(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> Mapping[str, object]:
        return {
            "strategy": self.metadata.name,
            "version": self.metadata.version,
            "symbol": context.symbol,
            "venue": context.venue,
            "timeframe_group": context.timeframe_group,
            "signal": signal,
        }
