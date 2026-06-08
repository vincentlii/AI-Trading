from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from research_pipeline.core.artifacts.manifest import ArtifactIndex, ArtifactIndexRecord
from research_pipeline.core.cache.keys import stable_fingerprint


SUPPORTED_SUFFIXES = {
    ".json": "json",
    ".csv": "csv",
    ".jsonl": "jsonl",
    ".md": "markdown",
    ".duckdb": "duckdb",
}


def build_index_for_directory(
    artifact_dir: Path,
    strategy: str,
    stage: str,
    window: str,
    source_command: str = "",
    source_files: list[str] | None = None,
    config_hash: str | None = None,
    pipeline_version: str = "research_pipeline.pr7",
    legacy_source: bool = False,
    notes: str = "",
) -> ArtifactIndex:
    artifact_dir = Path(artifact_dir)
    created_at = datetime.now(timezone.utc).isoformat()
    records: list[ArtifactIndexRecord] = []
    for path in sorted(artifact_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        file_hash = _sha256(path)
        record_seed = {
            "path": str(path),
            "file_hash": file_hash,
            "strategy": strategy,
            "stage": stage,
            "window": window,
        }
        records.append(
            ArtifactIndexRecord(
                artifact_id=stable_fingerprint(record_seed)[:24],
                strategy=strategy,
                stage=stage,
                window=window,
                artifact_type=SUPPORTED_SUFFIXES[path.suffix.lower()],
                path=str(path),
                file_hash=file_hash,
                created_at=created_at,
                source_command=source_command,
                source_files=list(source_files or []),
                config_hash=config_hash,
                pipeline_version=pipeline_version,
                legacy_source=legacy_source,
                notes=notes,
            )
        )
    index_seed = {
        "strategy": strategy,
        "stage": stage,
        "window": window,
        "records": [record.artifact_id for record in records],
    }
    baseline_manifest = artifact_dir / "baseline_manifest.json"
    return ArtifactIndex(
        index_id=stable_fingerprint(index_seed)[:24],
        strategy=strategy,
        created_at=created_at,
        records=records,
        baseline_manifest_ref=str(baseline_manifest) if baseline_manifest.exists() else None,
        pipeline_version=pipeline_version,
    )


def write_artifact_index(index: ArtifactIndex, output_dir: Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "artifact_index.json"
    md_path = output_dir / "artifact_index.md"
    json_path.write_text(index.as_json(), encoding="utf-8")
    md_path.write_text(index.as_markdown() + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
