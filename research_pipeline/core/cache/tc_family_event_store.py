from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from research_pipeline.core.cache.keys import stable_fingerprint


class FamilyCacheFingerprintError(ValueError):
    pass


class TcFamilyEventStore:
    def __init__(self, path: Path, fingerprint: Mapping[str, object]):
        self.path = Path(path)
        self.fingerprint = dict(fingerprint)
        self.fingerprint_hash = stable_fingerprint(self.fingerprint)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        (self.path.parent / "duckdb_tmp").mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS metadata(key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS context_rows(context_key VARCHAR PRIMARY KEY, payload JSON NOT NULL)")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS event_rows(event_key VARCHAR PRIMARY KEY, context_key VARCHAR NOT NULL, lifecycle_event_id VARCHAR, payload JSON NOT NULL)"
            )
            stored = connection.execute("SELECT value FROM metadata WHERE key='fingerprint_hash'").fetchone()
            if stored and str(stored[0]) != self.fingerprint_hash:
                raise FamilyCacheFingerprintError("TC family cache fingerprint mismatch")
            self._set_metadata(connection, "fingerprint_hash", self.fingerprint_hash)
            self._set_metadata(connection, "fingerprint", json.dumps(self.fingerprint, ensure_ascii=False, sort_keys=True))
            if not connection.execute("SELECT value FROM metadata WHERE key='complete'").fetchone():
                self._set_metadata(connection, "complete", "false")
                self._set_metadata(connection, "processed_windows", "0")

    def append_context_rows(self, rows: Sequence[Mapping[str, object]]) -> None:
        payloads = []
        for row in rows:
            context_key = str(row.get("context_key") or self.context_key(row))
            payload = dict(row)
            payload["context_key"] = context_key
            payloads.append((context_key, json.dumps(payload, ensure_ascii=False, sort_keys=True)))
        if not payloads:
            return
        with self._connect() as connection:
            connection.executemany("INSERT OR REPLACE INTO context_rows VALUES (?, ?)", payloads)

    def append_event_rows(self, rows: Sequence[Mapping[str, object]]) -> None:
        payloads = []
        for row in rows:
            context_key = str(row.get("context_key") or "")
            lifecycle_id = str(row.get("lifecycle_event_id") or row.get("breakout_event_id") or "")
            event_key = str(
                row.get("event_key")
                or lifecycle_id
                or stable_fingerprint({"context_key": context_key, "payload": dict(row)})[:24]
            )
            payload = dict(row)
            payload.update({"context_key": context_key, "event_key": event_key})
            payloads.append((event_key, context_key, lifecycle_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)))
        if not payloads:
            return
        with self._connect() as connection:
            connection.executemany("INSERT OR REPLACE INTO event_rows VALUES (?, ?, ?, ?)", payloads)

    def load_context_rows(self) -> tuple[dict[str, object], ...]:
        return self._load_payloads("context_rows", "context_key")

    def load_event_rows(self) -> tuple[dict[str, object], ...]:
        return self._load_payloads("event_rows", "event_key")

    def iter_event_batches(self, batch_size: int = 5000):
        offset = 0
        while True:
            with self._connect() as connection:
                values = connection.execute(
                    "SELECT payload FROM event_rows ORDER BY event_key LIMIT ? OFFSET ?",
                    [int(batch_size), int(offset)],
                ).fetchall()
            if not values:
                return
            yield tuple(json.loads(str(value[0])) for value in values)
            offset += len(values)

    def mark_progress(self, *, processed_windows: int) -> None:
        with self._connect() as connection:
            self._set_metadata(connection, "processed_windows", str(int(processed_windows)))
            self._set_metadata(connection, "updated_at", datetime.now(timezone.utc).isoformat())

    def mark_complete(self, *, processed_windows: int) -> None:
        with self._connect() as connection:
            self._set_metadata(connection, "processed_windows", str(int(processed_windows)))
            self._set_metadata(connection, "complete", "true")
            self._set_metadata(connection, "updated_at", datetime.now(timezone.utc).isoformat())

    def write_scan_summary(self, summary: Mapping[str, object]) -> None:
        with self._connect() as connection:
            self._set_metadata(
                connection,
                "scan_summary",
                json.dumps(dict(summary), ensure_ascii=False, sort_keys=True),
            )

    def read_scan_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            stored = connection.execute("SELECT value FROM metadata WHERE key='scan_summary'").fetchone()
        if not stored:
            return {}
        return dict(json.loads(str(stored[0])))

    def status(self) -> dict[str, object]:
        with self._connect() as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
            context_count = int(connection.execute("SELECT count(*) FROM context_rows").fetchone()[0])
            event_count = int(connection.execute("SELECT count(*) FROM event_rows").fetchone()[0])
        return {
            "fingerprint_hash": metadata.get("fingerprint_hash"),
            "complete": metadata.get("complete") == "true",
            "processed_windows": int(metadata.get("processed_windows", "0")),
            "context_rows": context_count,
            "event_rows": event_count,
        }

    @staticmethod
    def context_key(row: Mapping[str, object]) -> str:
        return stable_fingerprint(
            {
                "inst_id": row.get("inst_id"),
                "inst_type": row.get("inst_type"),
                "venue": row.get("venue"),
                "profile": row.get("profile"),
                "timestamp_ms": row.get("timestamp_ms"),
            }
        )[:24]

    def _load_payloads(self, table: str, order_by: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            values = connection.execute(f"SELECT payload FROM {table} ORDER BY {order_by}").fetchall()
        return tuple(json.loads(str(value[0])) for value in values)

    def _connect(self):
        import duckdb

        connection = duckdb.connect(str(self.path))
        temp_path = str((self.path.parent / "duckdb_tmp").resolve()).replace("'", "''")
        connection.execute(f"SET temp_directory='{temp_path}'")
        return connection

    @staticmethod
    def _set_metadata(connection, key: str, value: str) -> None:
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", [key, value])


__all__ = ("FamilyCacheFingerprintError", "TcFamilyEventStore")
