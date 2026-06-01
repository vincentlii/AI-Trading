from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BaselineMetrics:
    strategy: str
    window: str
    counts: dict[str, int]
    selected_smoke_combos: list[str]
    tracked_combos: dict[str, dict[str, Any]]
    key_metrics: dict[str, Any]
    manifest: dict[str, Any]


def load_baseline_metrics(baseline_dir: Path) -> BaselineMetrics:
    baseline_dir = Path(baseline_dir)
    with (baseline_dir / "key_metrics.json").open("r", encoding="utf-8") as handle:
        key_metrics = json.load(handle)
    with (baseline_dir / "baseline_manifest.json").open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    return BaselineMetrics(
        strategy=manifest["strategy"],
        window=manifest["window"],
        counts={key: int(value) for key, value in key_metrics["counts"].items()},
        selected_smoke_combos=list(manifest["selected_stage7_smoke_combos"]),
        tracked_combos=dict(key_metrics["tracked_combos"]),
        key_metrics=key_metrics,
        manifest=manifest,
    )
