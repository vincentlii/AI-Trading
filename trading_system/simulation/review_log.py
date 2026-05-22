from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from trading_system.simulation.paper import ReviewLogEntry


@dataclass(frozen=True)
class ReviewLogReadResult:
    entries: tuple[ReviewLogEntry, ...]
    invalid_rows: tuple[dict[str, object], ...]


def append_review_log_entries(path: str | Path, entries: Iterable[ReviewLogEntry]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(review_log_entry_to_dict(entry), ensure_ascii=False, sort_keys=True))
            file.write("\n")


def load_review_log_entries(path: str | Path) -> tuple[ReviewLogEntry, ...]:
    return read_review_log(path).entries


def read_review_log(path: str | Path) -> ReviewLogReadResult:
    source = Path(path)
    if not source.exists():
        return ReviewLogReadResult(entries=(), invalid_rows=())

    entries: list[ReviewLogEntry] = []
    invalid_rows: list[dict[str, object]] = []
    with source.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
                if not isinstance(payload, Mapping):
                    raise ValueError("row must be a JSON object")
                entries.append(review_log_entry_from_dict(payload))
            except Exception as error:
                invalid_rows.append({"line_number": line_number, "error": str(error)})

    return ReviewLogReadResult(entries=tuple(entries), invalid_rows=tuple(invalid_rows))


def review_log_entry_to_dict(entry: ReviewLogEntry) -> dict[str, object]:
    return {
        "event_type": entry.event_type,
        "timestamp_ms": entry.timestamp_ms,
        "symbol": entry.symbol,
        "venue": entry.venue,
        "strategy_name": entry.strategy_name,
        "strategy_version": entry.strategy_version,
        "setup_type": entry.setup_type,
        "status": entry.status,
        "reason_codes": list(entry.reason_codes),
        "payload": dict(entry.payload),
    }


def review_log_entry_from_dict(row: Mapping[str, object]) -> ReviewLogEntry:
    return ReviewLogEntry(
        event_type=_required_str(row, "event_type"),
        timestamp_ms=_optional_int(row.get("timestamp_ms")),
        symbol=_required_str(row, "symbol"),
        venue=_required_str(row, "venue"),
        strategy_name=_required_str(row, "strategy_name"),
        strategy_version=_required_str(row, "strategy_version"),
        setup_type=_required_str(row, "setup_type"),
        status=_required_str(row, "status"),
        reason_codes=_str_tuple(row.get("reason_codes", ()), "reason_codes"),
        payload=_mapping(row.get("payload", {}), "payload"),
    )


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError("timestamp_ms must be an integer or null")
    return value


def _str_tuple(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(value)


def _mapping(value: object, key: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be a JSON object")
    return dict(value)


__all__ = (
    "ReviewLogReadResult",
    "append_review_log_entries",
    "load_review_log_entries",
    "read_review_log",
    "review_log_entry_from_dict",
    "review_log_entry_to_dict",
)
