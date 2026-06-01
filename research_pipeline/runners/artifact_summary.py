from __future__ import annotations

from pathlib import Path

from research_pipeline.core.artifacts.normalizer import normalize_research_run_summary
from research_pipeline.core.artifacts.schemas import ResearchRunSummary


def build_artifact_summary(strategy: str, artifact_dir: Path) -> ResearchRunSummary:
    return normalize_research_run_summary(strategy, Path(artifact_dir))
