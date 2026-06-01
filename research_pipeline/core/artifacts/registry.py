from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_pipeline.core.cache.keys import stable_fingerprint


REGISTRY_VERSION = "research_pipeline.registry.v1"


@dataclass(frozen=True)
class ResearchRunRecord:
    run_id: str
    strategy: str
    stage: str
    window: str
    created_at: str
    artifact_index_path: str
    artifact_count: int
    source_command: str
    pipeline_version: str
    adapter_version: str | None
    baseline_ref: str | None
    notes: str
    tags: list[str] = field(default_factory=list)
    proposal_only: bool = True
    formal_conclusion_enabled: bool = False
    migrated_to_core: bool = False
    readonly: bool = True
    legacy_source: bool = False
    config_hash: str | None = None
    data_hash: str | None = None
    artifact_index_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRunRegistry:
    registry_id: str
    created_at: str
    runs: list[ResearchRunRecord] = field(default_factory=list)
    registry_version: str = REGISTRY_VERSION
    project: str = "trading_system"
    default_strategy: str | None = None
    baseline_refs: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runs"] = [run.as_dict() for run in self.runs]
        return payload

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def create_run_record(
    artifact_index_path: Path,
    artifact_index: dict[str, Any],
    artifact_index_hash: str,
    strategy: str,
    stage: str,
    window: str,
    source_command: str = "",
    adapter_version: str | None = None,
    baseline_ref: str | None = None,
    notes: str = "",
    tags: list[str] | None = None,
    proposal_only: bool = True,
    formal_conclusion_enabled: bool = False,
    migrated_to_core: bool = False,
    readonly: bool = True,
    legacy_source: bool = False,
    config_hash: str | None = None,
    data_hash: str | None = None,
) -> ResearchRunRecord:
    run_seed = {
        "strategy": strategy,
        "stage": stage,
        "window": window,
        "artifact_index_hash": artifact_index_hash,
        "baseline_ref": baseline_ref,
        "tags": sorted(tags or []),
    }
    return ResearchRunRecord(
        run_id=stable_fingerprint(run_seed)[:24],
        strategy=strategy,
        stage=stage,
        window=window,
        created_at=datetime.now(timezone.utc).isoformat(),
        artifact_index_path=str(Path(artifact_index_path)),
        artifact_count=len(artifact_index.get("records", [])),
        source_command=source_command,
        pipeline_version=str(artifact_index.get("pipeline_version", "research_pipeline")),
        adapter_version=adapter_version,
        baseline_ref=baseline_ref or artifact_index.get("baseline_manifest_ref"),
        notes=notes,
        tags=list(tags or []),
        proposal_only=proposal_only,
        formal_conclusion_enabled=formal_conclusion_enabled,
        migrated_to_core=migrated_to_core,
        readonly=readonly,
        legacy_source=legacy_source,
        config_hash=config_hash,
        data_hash=data_hash,
        artifact_index_hash=artifact_index_hash,
    )


def load_research_run_registry(path: Path) -> ResearchRunRegistry:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = [ResearchRunRecord(**run) for run in payload.get("runs", [])]
    return ResearchRunRegistry(
        registry_id=payload["registry_id"],
        created_at=payload["created_at"],
        runs=runs,
        registry_version=payload.get("registry_version", REGISTRY_VERSION),
        project=payload.get("project", "trading_system"),
        default_strategy=payload.get("default_strategy"),
        baseline_refs=list(payload.get("baseline_refs", [])),
        notes=payload.get("notes", ""),
    )


def new_research_run_registry(default_strategy: str | None = None) -> ResearchRunRegistry:
    created_at = datetime.now(timezone.utc).isoformat()
    registry_id = stable_fingerprint(
        {"registry_version": REGISTRY_VERSION, "default_strategy": default_strategy, "created_at": created_at}
    )[:24]
    return ResearchRunRegistry(
        registry_id=registry_id,
        created_at=created_at,
        default_strategy=default_strategy,
    )


def append_run(registry: ResearchRunRegistry, run: ResearchRunRecord) -> ResearchRunRegistry:
    baseline_refs = set(registry.baseline_refs)
    if run.baseline_ref:
        baseline_refs.add(run.baseline_ref)
    return ResearchRunRegistry(
        registry_id=registry.registry_id,
        created_at=registry.created_at,
        runs=[*registry.runs, run],
        registry_version=registry.registry_version,
        project=registry.project,
        default_strategy=registry.default_strategy or run.strategy,
        baseline_refs=sorted(baseline_refs),
        notes=registry.notes,
    )


def write_research_run_registry(path: Path, registry: ResearchRunRegistry) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(registry.as_json() + "\n", encoding="utf-8")
