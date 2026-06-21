from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.cache.tc_family_event_store import (
    FamilyCacheFingerprintError,
    TcFamilyEventStore,
    _event_batch_query,
)


class TcFamilyEventStoreTests(unittest.TestCase):
    def test_event_batches_use_keyset_pagination(self) -> None:
        query, parameters = _event_batch_query(last_event_key="event-2", batch_size=5000)

        self.assertIn("event_key > ?", query)
        self.assertNotIn("OFFSET", query)
        self.assertEqual(parameters, ["event-2", 5000])

    def test_store_deduplicates_events_and_reuses_matching_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "family.duckdb"
            fingerprint = {"dataset": "fixture", "core": "v2", "max_windows": 100}
            store = TcFamilyEventStore(path, fingerprint)
            store.initialize()
            store.append_context_rows(({"context_key": "ctx-1", "timestamp_ms": 1},))
            store.append_event_rows(
                (
                    {"event_key": "ctx-1:event-1", "context_key": "ctx-1", "lifecycle_event_id": "event-1"},
                    {"event_key": "ctx-1:event-1", "context_key": "ctx-1", "lifecycle_event_id": "event-1"},
                )
            )
            store.mark_complete(processed_windows=1)

            reused = TcFamilyEventStore(path, fingerprint)
            reused.initialize()

            self.assertTrue(reused.status()["complete"])
            self.assertEqual(len(reused.load_context_rows()), 1)
            self.assertEqual(len(reused.load_event_rows()), 1)

    def test_store_rejects_mismatched_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "family.duckdb"
            TcFamilyEventStore(path, {"dataset": "a"}).initialize()

            with self.assertRaises(FamilyCacheFingerprintError):
                TcFamilyEventStore(path, {"dataset": "b"}).initialize()

    def test_store_keeps_first_causal_payload_across_context_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "family.duckdb"
            store = TcFamilyEventStore(path, {"dataset": "fixture"})
            store.initialize()

            store.append_event_rows(
                (
                    {"context_key": "ctx-1", "lifecycle_event_id": "event-1", "timestamp_ms": 1},
                    {"context_key": "ctx-2", "lifecycle_event_id": "event-1", "timestamp_ms": 2},
                )
            )

            rows = store.load_event_rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["timestamp_ms"], 1)
            self.assertEqual(rows[0]["context_key"], "ctx-1")

    def test_store_persists_compact_scan_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "family.duckdb"
            store = TcFamilyEventStore(path, {"dataset": "fixture"})
            store.initialize()

            store.write_scan_summary({"total_windows": 12, "breakout_class_distribution": {"accepted_breakout": 3}})

            self.assertEqual(store.read_scan_summary()["total_windows"], 12)


if __name__ == "__main__":
    unittest.main()
