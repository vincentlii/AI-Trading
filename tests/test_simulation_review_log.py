import tempfile
import unittest
from pathlib import Path

from trading_system.simulation import ReviewLogEntry
from trading_system.simulation.review_log import (
    append_review_log_entries,
    load_review_log_entries,
    read_review_log,
)


def _entry(**overrides) -> ReviewLogEntry:
    values = {
        "event_type": "signal_received",
        "timestamp_ms": 1_700_000_000_000,
        "symbol": "BTC/USDT",
        "venue": "okx",
        "strategy_name": "trend_price_volume",
        "strategy_version": "v1",
        "setup_type": "trend_continuation",
        "status": "received",
        "reason_codes": (),
        "payload": {"timeframe_group": "B"},
    }
    values.update(overrides)
    return ReviewLogEntry(**values)


class ReviewLogPersistenceTests(unittest.TestCase):
    def test_appends_and_loads_review_log_entries_as_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review_log.jsonl"
            append_review_log_entries(path, (_entry(),))
            append_review_log_entries(
                path,
                (_entry(event_type="risk_rejected", status="rejected", reason_codes=("stop_distance_too_far",)),),
            )

            entries = load_review_log_entries(path)

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].event_type, "signal_received")
        self.assertEqual(entries[1].reason_codes, ("stop_distance_too_far",))
        self.assertEqual(entries[0].payload["timeframe_group"], "B")

    def test_missing_file_returns_empty_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entries = load_review_log_entries(Path(temp_dir) / "missing.jsonl")

        self.assertEqual(entries, ())

    def test_bad_jsonl_rows_are_reported_without_dropping_valid_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review_log.jsonl"
            append_review_log_entries(path, (_entry(),))
            path.write_text(path.read_text(encoding="utf-8") + "{bad json}\n", encoding="utf-8")

            result = read_review_log(path)

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(len(result.invalid_rows), 1)
        self.assertEqual(result.invalid_rows[0]["line_number"], 2)


if __name__ == "__main__":
    unittest.main()
