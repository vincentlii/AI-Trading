from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    kind: str
    data: Any


@dataclass(frozen=True)
class ResearchRunSummary:
    strategy: str
    run_id: str
    stage: str
    window: str
    source_files: list[str]
    created_at: str | None
    metrics: dict[str, Any]
    combos: list[dict[str, Any]] = field(default_factory=list)
    sizing: list[dict[str, Any]] = field(default_factory=list)
    smoke: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        lines = [
            f"# Artifact Summary: {self.strategy}",
            "",
            f"- run_id: {self.run_id}",
            f"- stage: {self.stage}",
            f"- window: {self.window}",
            f"- fresh_candidates: {self.metrics.get('fresh_candidates')}",
            f"- formal_approved: {self.metrics.get('formal_approved')}",
            f"- proposal_approved: {self.metrics.get('proposal_approved')}",
            f"- closed_trades: {self.metrics.get('closed_trades')}",
            f"- selected_smoke_combos: {', '.join(self.smoke.get('selected_combos', []))}",
        ]
        return "\n".join(lines)
