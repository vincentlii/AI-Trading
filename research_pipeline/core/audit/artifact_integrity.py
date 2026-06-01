from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def build_artifact_integrity_rows(artifact_dir: Path, registry: Path | None = None) -> list[dict[str, Any]]:
    rows = []
    index_path = Path(artifact_dir) / "artifact_index.json"
    registry_path = registry or (Path(artifact_dir) / "research_run_registry.json")
    rows.append(_file_row("artifact_index", index_path, required=True))
    rows.append(_file_row("research_run_registry", registry_path, required=False))
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for record in index.get("records", []):
            path = Path(record.get("path", ""))
            exists = path.exists()
            file_hash = _sha256(path) if exists else None
            self_referential = path.name in {"artifact_index.json", "artifact_index.md", "research_run_registry.json"}
            rows.append(
                {
                    "artifact_name": path.name,
                    "path": str(path),
                    "exists": exists,
                    "hash_matches": exists and (self_referential or file_hash == record.get("file_hash")),
                    "source_command_present": bool(record.get("source_command")),
                    "config_hash_present": bool(record.get("config_hash")),
                    "pipeline_version_present": bool(record.get("pipeline_version")),
                    "adapter_version_present": bool(record.get("adapter_version")),
                    "blocking": (not exists) or (exists and not self_referential and file_hash != record.get("file_hash")),
                    "notes": "self-referential manifest hash is informational"
                    if self_referential
                    else "config_hash/adapter_version may be absent in legacy proposal artifacts",
                }
            )
    return rows


def _file_row(name: str, path: Path, required: bool) -> dict[str, Any]:
    return {
        "artifact_name": name,
        "path": str(path),
        "exists": path.exists(),
        "hash_matches": None,
        "source_command_present": None,
        "config_hash_present": None,
        "pipeline_version_present": None,
        "adapter_version_present": None,
        "blocking": required and not path.exists(),
        "notes": "",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
