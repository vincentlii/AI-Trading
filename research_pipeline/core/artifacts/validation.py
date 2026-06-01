from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactValidationResult:
    passed: bool
    checked_count: int
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact_index_file(path: Path) -> ArtifactValidationResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    errors: list[str] = []
    records = payload.get("records", [])
    if not records:
        return ArtifactValidationResult(
            passed=False,
            checked_count=0,
            errors=["no_records: artifact index has no records"],
        )
    for record in records:
        artifact_path = Path(record["path"])
        if not artifact_path.exists():
            errors.append(f"missing: {artifact_path}")
            continue
        actual_hash = hash_file(artifact_path)
        expected_hash = record.get("file_hash")
        if actual_hash != expected_hash:
            errors.append(
                f"hash_changed: {artifact_path} expected={expected_hash} actual={actual_hash}"
            )
    return ArtifactValidationResult(
        passed=not errors,
        checked_count=len(records),
        errors=errors,
    )
