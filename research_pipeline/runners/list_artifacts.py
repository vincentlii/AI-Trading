from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def list_artifacts_from_index(
    path: Path,
    strategy: str | None = None,
    stage: str | None = None,
    window: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = list(payload.get("records", []))
    if strategy is not None:
        records = [record for record in records if record.get("strategy") == strategy]
    if stage is not None:
        records = [record for record in records if record.get("stage") == stage]
    if window is not None:
        records = [record for record in records if record.get("window") == window]
    return {"artifacts": records}


def list_runs_from_registry(path: Path) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"runs": list(payload.get("runs", []))}
