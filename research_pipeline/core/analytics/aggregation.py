from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AggregationResult:
    strategy: str
    windows: list[str]
    grouped_metrics: list[dict[str, Any]]
    combo_metrics: dict[str, dict[str, dict[str, Any]]]
    baseline_metrics: dict[str, dict[str, Any]]
    smoke_ready_combos: list[str]
    consistency_flags: dict[str, dict[str, Any]]
    sample_size_warnings: dict[str, list[str]]
    source_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
