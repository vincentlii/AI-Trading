from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    strategy_name: str
    asset: str
    profile: str
    direction: str
    signal_time: str
    entry_time: str
    setup: str
    tags: dict[str, Any] = field(default_factory=dict)
    prices: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
