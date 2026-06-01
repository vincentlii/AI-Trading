from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

from trading_system.config.loader import BacktestPresetConfig


@dataclass(frozen=True)
class BacktestRunRecordPaths:
    run_id: str
    run_dir: Path
    index_path: Path
    summary_path: Path
    rows_csv_path: Path
    preset_snapshot_path: Path


def record_backtest_run(
    *,
    output_dir: str | Path,
    script_name: str,
    command_args: Mapping[str, object],
    preset: BacktestPresetConfig,
    rows: Sequence[Mapping[str, object]],
    project_root: str | Path,
    git_metadata: Mapping[str, object] | None = None,
    extra_artifacts: Mapping[str, object] | None = None,
    cache_manifest: Mapping[str, object] | None = None,
) -> BacktestRunRecordPaths:
    root = Path(project_root)
    destination = Path(output_dir)
    if not destination.is_absolute():
        destination = root / destination
    destination.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    run_id = f"{created_at.replace(':', '').replace('+0000', 'Z')}-{uuid4().hex[:8]}"
    run_dir = destination / run_id
    run_dir.mkdir(parents=False, exist_ok=False)

    row_payloads = tuple(dict(row) for row in rows)
    preset_snapshot = _preset_snapshot(preset)
    git_payload = dict(git_metadata) if git_metadata is not None else collect_git_metadata(root)
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": created_at,
        "script_name": script_name,
        "command_args": _json_ready(command_args),
        "git": _json_ready(git_payload),
        "config_version": preset.config_version,
        "config_fingerprint": preset.config_fingerprint,
        "row_count": len(row_payloads),
        "extra_artifacts": _json_ready(extra_artifacts or {}),
        "cache_manifest": _json_ready(cache_manifest or {}),
        **preset_snapshot,
    }

    summary_path = run_dir / "summary.json"
    rows_csv_path = run_dir / "rows.csv"
    preset_snapshot_path = run_dir / "preset_snapshot.json"
    index_path = destination / "index.jsonl"

    _write_json(summary_path, summary)
    _write_json(preset_snapshot_path, preset_snapshot)
    _write_csv(rows_csv_path, row_payloads)
    _append_index(
        index_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "created_at_utc": created_at,
            "script_name": script_name,
            "config_version": preset.config_version,
            "config_fingerprint": preset.config_fingerprint,
            "row_count": len(row_payloads),
            "extra_artifacts": _json_ready(extra_artifacts or {}),
            "summary_path": str(summary_path.relative_to(destination)),
            "rows_csv_path": str(rows_csv_path.relative_to(destination)),
            "preset_snapshot_path": str(preset_snapshot_path.relative_to(destination)),
        },
    )

    return BacktestRunRecordPaths(
        run_id=run_id,
        run_dir=run_dir,
        index_path=index_path,
        summary_path=summary_path,
        rows_csv_path=rows_csv_path,
        preset_snapshot_path=preset_snapshot_path,
    )


def collect_git_metadata(project_root: str | Path) -> dict[str, object]:
    root = Path(project_root)
    branch = _git_output(root, "branch", "--show-current")
    commit = _git_output(root, "rev-parse", "--short", "HEAD")
    status = _git_output(root, "status", "--short")
    return {
        "branch": branch,
        "commit": commit,
        "dirty": bool(status),
    }


def _preset_snapshot(preset: BacktestPresetConfig) -> dict[str, object]:
    return {
        "assets": asdict(preset.assets),
        "risk": asdict(preset.risk),
        "costs": asdict(preset.costs),
        "execution": asdict(preset.execution),
        "scan": asdict(preset.scan),
        "strategy": asdict(preset.strategy),
        "ranking": asdict(preset.ranking),
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fieldnames = _csv_fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})


def _append_index(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(_json_ready(payload), ensure_ascii=False, sort_keys=True) + "\n")


def _csv_fieldnames(rows: Sequence[Mapping[str, object]]) -> list[str]:
    preferred = [
        "cost_tier",
        "rank",
        "status",
        "symbol",
        "inst_id",
        "inst_type",
        "contract_mode",
        "allow_short",
        "timeframe_group",
        "strategy_name",
        "strategy_version",
        "strategy_family",
        "setup_type",
        "direction",
        "trade_count",
        "net_profit",
        "expectancy_R",
        "median_R",
        "win_rate",
        "profit_factor",
        "max_drawdown",
    ]
    keys: set[str] = set()
    for row in rows:
        keys.update(str(key) for key in row)
    ordered = [key for key in preferred if key in keys]
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


def _git_output(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ("git", *args),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


__all__ = (
    "BacktestRunRecordPaths",
    "collect_git_metadata",
    "record_backtest_run",
)
