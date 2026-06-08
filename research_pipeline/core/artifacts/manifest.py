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


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    strategy: str
    adapter_version: str
    dataset_window: str
    artifact_contract: dict[str, Any]
    audit_profile: dict[str, Any]
    artifact_paths: dict[str, str] = field(default_factory=dict)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    baseline_ref: str | None = None
    proposal_only: bool = True
    formal_conclusion_enabled: bool = False
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        return "\n".join(
            [
                f"# Run Manifest: {self.strategy}",
                "",
                f"- run_id: {self.run_id}",
                f"- adapter_version: {self.adapter_version}",
                f"- dataset_window: {self.dataset_window}",
                f"- proposal_only: {str(self.proposal_only).lower()}",
                f"- formal_conclusion_enabled: {str(self.formal_conclusion_enabled).lower()}",
                f"- baseline_ref: {self.baseline_ref or ''}",
                f"- artifact_paths: {len(self.artifact_paths)}",
                f"- notes: {self.notes}",
            ]
        )
