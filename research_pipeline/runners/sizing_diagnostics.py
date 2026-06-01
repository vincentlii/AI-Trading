from __future__ import annotations

import json
from pathlib import Path

from research_pipeline.core.artifacts.reader import read_artifact
from research_pipeline.core.sizing.diagnostics import build_model_diagnostics
from research_pipeline.core.sizing.schemas import SizingDiagnostics


def build_sizing_diagnostics(
    strategy: str,
    *,
    summary_dir: Path | None = None,
    artifact_index_path: Path | None = None,
) -> SizingDiagnostics:
    if strategy != "liquidity_reversal":
        raise ValueError(f"Unsupported strategy for read-only sizing diagnostics: {strategy}")
    key_metrics_path = _resolve_key_metrics_path(
        summary_dir=summary_dir,
        artifact_index_path=artifact_index_path,
    )
    payload = read_artifact(key_metrics_path).data
    counts = payload.get("counts", {})
    sizing = payload.get("sizing", {})
    fresh_candidates = _int(counts.get("fresh_candidates"))
    models = {
        model_name: build_model_diagnostics(
            model_name,
            row,
            fresh_candidates=fresh_candidates,
        )
        for model_name, row in sizing.items()
    }
    missing_fields = sorted(
        {field for model in models.values() for field in model.missing_fields}
    )
    return SizingDiagnostics(
        strategy=strategy,
        stage="read_only_sizing_diagnostics",
        window=str(payload.get("window") or _window_from_path(key_metrics_path)),
        fresh_candidates=fresh_candidates,
        formal_approved=_int(counts.get("formal_approved")),
        proposal_approved=_int(counts.get("proposal_approved")),
        closed_trades=_int(counts.get("closed_trades")),
        models=models,
        source_files=[str(key_metrics_path)],
        missing_fields=missing_fields,
        proposal_only=True,
        readonly=True,
    )


def _resolve_key_metrics_path(
    *,
    summary_dir: Path | None,
    artifact_index_path: Path | None,
) -> Path:
    if summary_dir is not None:
        path = Path(summary_dir) / "key_metrics.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing key_metrics.json in {summary_dir}")
        return path
    if artifact_index_path is None:
        raise ValueError("summary_dir or artifact_index_path is required")
    index = json.loads(Path(artifact_index_path).read_text(encoding="utf-8"))
    for record in index.get("records", []):
        candidate = Path(record["path"])
        if candidate.name == "key_metrics.json":
            return candidate
    raise FileNotFoundError(f"Artifact index has no key_metrics.json: {artifact_index_path}")


def _window_from_path(path: Path) -> str:
    for part in reversed(Path(path).parts):
        if part.endswith("w"):
            return part
    return ""


def _int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))
