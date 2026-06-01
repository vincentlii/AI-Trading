from __future__ import annotations

from pathlib import Path

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import ArtifactIndex


def build_artifact_index(
    artifact_dir: Path,
    strategy: str,
    stage: str,
    window: str,
    source_command: str = "",
    source_files: list[str] | None = None,
    config_hash: str | None = None,
    legacy_source: bool = False,
    notes: str = "",
) -> ArtifactIndex:
    return build_index_for_directory(
        artifact_dir=artifact_dir,
        strategy=strategy,
        stage=stage,
        window=window,
        source_command=source_command,
        source_files=source_files,
        config_hash=config_hash,
        legacy_source=legacy_source,
        notes=notes,
    )


def build_and_write_artifact_index(
    artifact_dir: Path,
    output_dir: Path,
    strategy: str,
    stage: str,
    window: str,
    source_command: str = "",
    source_files: list[str] | None = None,
    config_hash: str | None = None,
    legacy_source: bool = False,
    notes: str = "",
) -> tuple[ArtifactIndex, dict[str, Path]]:
    index = build_artifact_index(
        artifact_dir=artifact_dir,
        strategy=strategy,
        stage=stage,
        window=window,
        source_command=source_command,
        source_files=source_files,
        config_hash=config_hash,
        legacy_source=legacy_source,
        notes=notes,
    )
    return index, write_artifact_index(index, output_dir)
