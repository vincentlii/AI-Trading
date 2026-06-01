from __future__ import annotations

from pathlib import Path

from research_pipeline.core.artifacts.validation import ArtifactValidationResult, validate_artifact_index_file


def validate_artifact_index(path: Path) -> ArtifactValidationResult:
    return validate_artifact_index_file(Path(path))
