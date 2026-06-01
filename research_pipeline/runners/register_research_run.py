from __future__ import annotations

import json
from pathlib import Path

from research_pipeline.core.artifacts.registry import (
    ResearchRunRecord,
    append_run,
    create_run_record,
    load_research_run_registry,
    new_research_run_registry,
    write_research_run_registry,
)
from research_pipeline.core.artifacts.validation import hash_file


def register_research_run(
    registry_path: Path,
    artifact_index_path: Path,
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
    registry_path = Path(registry_path)
    artifact_index_path = Path(artifact_index_path)
    artifact_index = json.loads(artifact_index_path.read_text(encoding="utf-8"))
    artifact_index_hash = hash_file(artifact_index_path)
    run = create_run_record(
        artifact_index_path=artifact_index_path,
        artifact_index=artifact_index,
        artifact_index_hash=artifact_index_hash,
        strategy=strategy,
        stage=stage,
        window=window,
        source_command=source_command,
        adapter_version=adapter_version,
        baseline_ref=baseline_ref,
        notes=notes,
        tags=tags,
        proposal_only=proposal_only,
        formal_conclusion_enabled=formal_conclusion_enabled,
        migrated_to_core=migrated_to_core,
        readonly=readonly,
        legacy_source=legacy_source,
        config_hash=config_hash,
        data_hash=data_hash,
    )
    registry = (
        load_research_run_registry(registry_path)
        if registry_path.exists()
        else new_research_run_registry(default_strategy=strategy)
    )
    write_research_run_registry(registry_path, append_run(registry, run))
    return run
