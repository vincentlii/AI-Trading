from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArtifactIndexRecord:
    artifact_id: str
    strategy: str
    stage: str
    window: str
    artifact_type: str
    path: str
    file_hash: str
    created_at: str
    source_command: str
    source_files: list[str]
    config_hash: str | None
    pipeline_version: str
    legacy_source: bool
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactIndex:
    index_id: str
    strategy: str
    created_at: str
    records: list[ArtifactIndexRecord] = field(default_factory=list)
    baseline_manifest_ref: str | None = None
    pipeline_version: str = "research_pipeline.pr7"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["records"] = [record.as_dict() for record in self.records]
        return payload

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        lines = [
            f"# Artifact Index: {self.strategy}",
            "",
            f"- index_id: {self.index_id}",
            f"- created_at: {self.created_at}",
            f"- records: {len(self.records)}",
            f"- baseline_manifest_ref: {self.baseline_manifest_ref or ''}",
            "",
            "| Artifact | Type | Stage | Window | Hash |",
            "|---|---|---|---|---|",
        ]
        for record in self.records:
            lines.append(
                f"| `{record.path}` | {record.artifact_type} | {record.stage} | "
                f"{record.window} | `{record.file_hash[:12]}` |"
            )
        return "\n".join(lines)
