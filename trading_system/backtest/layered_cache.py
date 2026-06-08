from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from trading_system.config.loader import BacktestPresetConfig


@dataclass(frozen=True)
class LayeredArtifactPaths:
    cache_dir: Path
    manifest_path: Path
    context_path: Path
    raw_candidates_path: Path
    filter_results_path: Path
    execution_results_path: Path
    funnel_summary_path: Path
    gate_ablation_path: Path
    diagnostics_report_path: Path


def artifact_paths(cache_dir: str | Path) -> LayeredArtifactPaths:
    root = Path(cache_dir)
    return LayeredArtifactPaths(
        cache_dir=root,
        manifest_path=root / "cache_manifest.json",
        context_path=root / "context_features.jsonl",
        raw_candidates_path=root / "raw_candidates.jsonl",
        filter_results_path=root / "filter_results.jsonl",
        execution_results_path=root / "execution_results.jsonl",
        funnel_summary_path=root / "funnel_summary.csv",
        gate_ablation_path=root / "gate_ablation.csv",
        diagnostics_report_path=root / "proposal_diagnostics.md",
    )


def stable_hash(value: object) -> str:
    return sha256(json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def context_config_hash(preset: BacktestPresetConfig) -> str:
    return stable_hash(
        {
            "assets": asdict(preset.assets),
            "scan": asdict(preset.scan),
            "volume": preset.strategy.volume,
            "execution": {
                "invalidation_mode": preset.execution.invalidation_mode,
                "invalidation_buffer_atr": preset.execution.invalidation_buffer_atr,
            },
        }
    )


def candidate_generation_config_hash(
    preset: BacktestPresetConfig,
    setup_filter: Sequence[str] | None = None,
    *,
    setup_semantic_version: str = "",
) -> str:
    semantic_version = setup_semantic_version or _setup_semantic_version(setup_filter)
    return stable_hash(
        {
            "strategy": {
                "name": preset.strategy.name,
                "version": preset.strategy.version,
                "enabled_setups": preset.strategy.enabled_setups,
            },
            "profiles": preset.scan.profile_keys,
            "setup_filter": tuple(setup_filter or ()),
            "setup_semantic_version": semantic_version,
        }
    )


def _setup_semantic_version(setup_filter: Sequence[str] | None) -> str:
    versions = {
        "liquidity_reversal": "liquidity_reversal.current",
        "trend_continuation": "trend_continuation.legacy_v1",
        "compression_expansion": "compression_expansion.semantic_v2",
        "breakout_pullback": "trend_continuation_core.v2",
    }
    return "|".join(versions.get(str(setup), f"{setup}.unknown") for setup in tuple(setup_filter or ()))


def filter_config_hash(preset: BacktestPresetConfig) -> str:
    return stable_hash(
        {
            "strategy_parameters": preset.strategy.parameters,
            "risk": asdict(preset.risk),
            "costs": asdict(preset.costs),
            "execution": asdict(preset.execution),
        }
    )


def execution_config_hash(preset: BacktestPresetConfig, cost_tiers: Sequence[str]) -> str:
    return stable_hash(
        {
            "execution": asdict(preset.execution),
            "costs": asdict(preset.costs),
            "cost_tiers": tuple(cost_tiers),
        }
    )


def data_hash_from_counts(counts: Sequence[Mapping[str, object]]) -> str:
    return stable_hash(tuple(sorted((dict(row) for row in counts), key=lambda row: tuple(str(row.get(key, "")) for key in ("inst_id", "bar", "profile")))))


def write_json(path: str | Path, payload: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, object]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(_json_ready(row), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> tuple[dict[str, object], ...]:
    file_path = Path(path)
    if not file_path.exists():
        return ()
    return tuple(json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip())


def write_csv(path: str | Path, rows: Sequence[Mapping[str, object]], *, preferred_fields: Sequence[str] = ()) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows, preferred_fields)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _fieldnames(rows: Sequence[Mapping[str, object]], preferred_fields: Sequence[str]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(str(key) for key in row)
    if not keys:
        return list(preferred_fields)
    ordered = [field for field in preferred_fields if field in keys]
    ordered.extend(sorted(key for key in keys if key not in set(ordered)))
    return ordered


def _csv_value(value: object) -> object:
    if isinstance(value, str | int | float | bool) or value is None:
        return "" if value is None else value
    return json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True)


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


__all__ = (
    "LayeredArtifactPaths",
    "artifact_paths",
    "candidate_generation_config_hash",
    "context_config_hash",
    "data_hash_from_counts",
    "execution_config_hash",
    "filter_config_hash",
    "read_json",
    "read_jsonl",
    "stable_hash",
    "write_csv",
    "write_json",
    "write_jsonl",
)
