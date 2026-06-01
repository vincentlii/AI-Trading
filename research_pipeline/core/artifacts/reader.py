from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.schemas import ArtifactRecord
from research_pipeline.core.reports.readers import read_markdown_report


def read_artifact(path: Path) -> ArtifactRecord:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return ArtifactRecord(str(path), "json", _read_json(path))
    if suffix == ".csv":
        return ArtifactRecord(str(path), "csv", _read_csv(path))
    if suffix == ".jsonl":
        return ArtifactRecord(str(path), "jsonl", _read_jsonl(path))
    if suffix in {".md", ".markdown"}:
        return ArtifactRecord(str(path), "markdown", read_markdown_report(path))
    raise ValueError(f"Unsupported artifact type: {path}")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows
