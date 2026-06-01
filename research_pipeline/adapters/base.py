from __future__ import annotations

from abc import ABC, abstractmethod


class StrategyAdapter(ABC):
    name: str

    def required_features(self) -> list[str]:
        return []

    def structure_sources(self) -> list[str]:
        return []

    @abstractmethod
    def generate_candidates(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def filter_policy(self):
        raise NotImplementedError

    @abstractmethod
    def sizing_policy(self):
        raise NotImplementedError

    @abstractmethod
    def exit_policy(self):
        raise NotImplementedError
