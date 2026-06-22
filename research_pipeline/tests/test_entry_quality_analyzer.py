from __future__ import annotations

import csv
from dataclasses import replace
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trading_system.data.okx_cli import Candle
from trading_system.data.history import DuckDbCandleRepository, ReadOnlyDuckDbCandleRepository
from trading_system.diagnostics.entry_quality import (
    EntryDiagnostic,
    EntryRecord,
    analyze_entry,
    build_problem_diagnoses,
    build_summary_metrics,
)
from research_pipeline.runners.entry_quality_analyzer import (
    load_entry_rows,
    normalize_entry_row,
    run_entry_quality_analyzer,
)
from scripts.run_entry_quality_analyzer import main as cli_main


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
HOUR_MS = 60 * 60 * 1000


def candle(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=index * FIFTEEN_MINUTES_MS,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=10_000.0,
        is_confirmed=True,
    )


def flat_candles(count: int, *, close: float = 100.0) -> tuple[Candle, ...]:
    return tuple(candle(index, high=close + 0.2, low=close - 0.2, close=close) for index in range(count))


def entry(direction: str = "long", **changes) -> EntryRecord:
    values = {
        "strategy_id": "strategy-a",
        "setup_type": "setup-a",
        "instrument": "BTC-USDT-SWAP",
        "direction": direction,
        "signal_time_ms": None,
        "entry_time_ms": 0,
        "entry_price": 100.0,
        "stop_price": 99.0 if direction == "long" else 101.0,
        "level_price": 99.5 if direction == "long" else 100.5,
        "atr": 2.0,
        "tags": (),
        "quality_score": None,
        "venue": "okx",
        "inst_type": "SWAP",
    }
    values.update(changes)
    return EntryRecord(**values)


class EntryQualityCoreTests(unittest.TestCase):
    def test_summary_contains_complete_public_metric_contract(self) -> None:
        diagnostic = analyze_entry(entry(), flat_candles(16), timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=4)
        names = {row.metric for row in build_summary_metrics(total_entries=1, diagnostics=(diagnostic,), max_horizon_hours=4)}
        expected = {
            "entries", "valid_entries", "missing_stop_rate", "missing_level_rate",
            "avg_MFE_pct", "median_MFE_pct", "avg_MAE_pct", "median_MAE_pct", "MFE_MAE_ratio",
            "avg_MFE_R", "median_MFE_R", "avg_MAE_R", "median_MAE_R",
            "+0.5R_first", "+1R_first", "+2R_first", "invalidation_first", "no_decision_rate",
            "median_time_to_MFE", "median_time_to_0.5R", "median_time_to_1R", "median_time_to_2R",
            "median_time_to_invalidation", "median_entry_to_level_ATR", "median_entry_to_level_pct",
            "median_stop_distance_ATR", "median_stop_distance_pct", "entry_after_signal_delay_median",
        }
        for hours in (1, 4, 12, 24, 48, 72, 96):
            expected.update({f"median_return_{hours}H", f"avg_return_{hours}H", f"win_rate_{hours}H"})
        self.assertEqual(names, expected)

    def test_long_and_short_fixed_returns_are_directional(self) -> None:
        long_rows = list(flat_candles(8))
        short_rows = list(flat_candles(8))
        long_rows[3] = candle(3, high=101.2, low=99.8, close=101.0)
        short_rows[3] = candle(3, high=100.2, low=98.8, close=99.0)

        long_result = analyze_entry(entry("long", stop_price=None), long_rows, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=1)
        short_result = analyze_entry(entry("short", stop_price=None), short_rows, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=1)

        self.assertAlmostEqual(long_result.fixed_returns_pct[1] or 0.0, 1.0)
        self.assertAlmostEqual(short_result.fixed_returns_pct[1] or 0.0, 1.0)

    def test_mfe_mae_pct_and_r_metrics_are_correct(self) -> None:
        rows = list(flat_candles(16))
        rows[0] = candle(0, high=101.2, low=99.5, close=100.8)
        rows[1] = candle(1, high=102.2, low=99.8, close=102.0)
        rows[2] = candle(2, high=103.0, low=98.0, close=101.0)

        result = analyze_entry(entry(), rows, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=4)

        self.assertAlmostEqual(result.mfe_pct or 0.0, 3.0)
        self.assertAlmostEqual(result.mae_pct or 0.0, 2.0)
        self.assertAlmostEqual(result.mfe_r or 0.0, 3.0)
        self.assertAlmostEqual(result.mae_r or 0.0, 2.0)
        self.assertTrue(result.half_r_first)
        self.assertTrue(result.one_r_first)
        self.assertTrue(result.two_r_first)
        self.assertEqual(result.time_to_one_r_minutes, 15)

    def test_invalidation_first_and_same_bar_ambiguity_are_distinct(self) -> None:
        stopped = list(flat_candles(16))
        stopped[0] = candle(0, high=100.2, low=98.8, close=99.2)
        ambiguous = list(flat_candles(16))
        ambiguous[0] = candle(0, high=101.2, low=98.8, close=100.0)

        stopped_result = analyze_entry(entry(), stopped, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=4)
        ambiguous_result = analyze_entry(entry(), ambiguous, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=4)

        self.assertTrue(stopped_result.invalidation_first)
        self.assertEqual(stopped_result.time_to_invalidation_minutes, 15)
        self.assertFalse(ambiguous_result.one_r_first)
        self.assertFalse(ambiguous_result.invalidation_first)
        self.assertTrue(ambiguous_result.path_ambiguous)

    def test_missing_stop_and_level_skip_only_dependent_metrics(self) -> None:
        result = analyze_entry(
            entry(stop_price=None, level_price=None),
            flat_candles(16, close=101.0),
            timeframe_ms=FIFTEEN_MINUTES_MS,
            max_horizon_hours=4,
        )

        self.assertIsNotNone(result.mfe_pct)
        self.assertIsNone(result.mfe_r)
        self.assertIsNone(result.stop_distance_pct)
        self.assertIsNone(result.entry_to_level_pct)

    def test_incomplete_or_gapped_future_window_is_not_calculated(self) -> None:
        insufficient = flat_candles(3, close=101.0)
        gapped = tuple(row for index, row in enumerate(flat_candles(4, close=101.0)) if index != 1)

        short_result = analyze_entry(entry(stop_price=None), insufficient, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=1)
        gap_result = analyze_entry(entry(stop_price=None), gapped, timeframe_ms=FIFTEEN_MINUTES_MS, max_horizon_hours=1)

        self.assertIsNone(short_result.fixed_returns_pct[1])
        self.assertIsNone(short_result.mfe_pct)
        self.assertIsNone(gap_result.fixed_returns_pct[1])
        self.assertIsNone(gap_result.mfe_pct)

    def test_problem_diagnoses_use_fixed_labels_and_eligible_denominators(self) -> None:
        diagnostic = EntryDiagnostic(
            record=entry(stop_price=99.8, level_price=98.0, atr=2.0),
            fixed_returns_pct={24: -0.1},
            complete_window=True,
            mfe_pct=0.3,
            mae_pct=0.8,
            mfe_r=1.5,
            mae_r=4.0,
            time_to_mfe_minutes=60,
            half_r_first=False,
            one_r_first=False,
            two_r_first=False,
            invalidation_first=True,
            no_decision=False,
            path_ambiguous=False,
            time_to_half_r_minutes=None,
            time_to_one_r_minutes=24 * 60,
            time_to_two_r_minutes=None,
            time_to_invalidation_minutes=60,
            entry_to_level_atr=1.0,
            entry_to_level_pct=2.0,
            stop_distance_atr=0.1,
            stop_distance_pct=0.2,
            entry_after_signal_delay_minutes=None,
        )

        no_fast_failure = replace(
            diagnostic,
            mfe_r=0.5,
            mfe_pct=1.0,
            mae_pct=0.5,
            invalidation_first=False,
            time_to_one_r_minutes=None,
            time_to_invalidation_minutes=None,
        )
        diagnoses = {row.problem: row for row in build_problem_diagnoses((diagnostic, no_fast_failure))}

        self.assertEqual(set(diagnoses), {
            "low_MFE_entry",
            "high_MAE_before_profit",
            "fast_invalidation",
            "positive_MFE_but_giveback",
            "chase_entry",
            "tiny_R_entry",
            "large_R_entry",
            "slow_profit_entry",
            "noise_entry",
        })
        self.assertEqual(diagnoses["low_MFE_entry"].count, 1)
        self.assertEqual(diagnoses["large_R_entry"].count, 0)
        self.assertEqual(diagnoses["large_R_entry"].eligible_count, 2)
        self.assertEqual(diagnoses["fast_invalidation"].eligible_count, 2)
        self.assertEqual(diagnoses["slow_profit_entry"].eligible_count, 2)


class EntryQualityRunnerTests(unittest.TestCase):
    def test_read_only_repository_reuses_existing_candle_loader(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "history.duckdb"
            writable = DuckDbCandleRepository(database)
            writable.save_many("BTC-USDT-SWAP", "15m", flat_candles(2), inst_type="SWAP")

            readonly = ReadOnlyDuckDbCandleRepository(database)
            loaded = readonly.load_range("BTC-USDT-SWAP", "15m", 0, HOUR_MS, inst_type="SWAP")
            with self.assertRaises(PermissionError):
                readonly.save_many("BTC-USDT-SWAP", "15m", flat_candles(1), inst_type="SWAP")

        self.assertEqual(len(loaded), 2)

    def test_read_only_repository_rejects_missing_database(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                ReadOnlyDuckDbCandleRepository(Path(directory) / "missing.duckdb")

    def test_normalizer_accepts_aliases_and_iso_time(self) -> None:
        normalized = normalize_entry_row({
            "strategy": "strategy-a",
            "setup_id": "setup-a",
            "inst_id": "BTC-USDT-SWAP",
            "direction": "long",
            "fill_time": "2024-01-01T00:00:00+00:00",
            "fill_price": "100.0",
            "invalidation_price": "99.0",
            "structure_level": "99.5",
            "atr_at_entry": "2.0",
        })

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.strategy_id, "strategy-a")
        self.assertEqual(normalized.entry_time_ms, 1_704_067_200_000)
        self.assertEqual(normalized.stop_price, 99.0)

    def test_jsonl_and_csv_inputs_are_supported(self) -> None:
        row = {
            "strategy_id": "strategy-a",
            "instrument": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_time": 0,
            "entry_price": 100.0,
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            jsonl = root / "entries.jsonl"
            csv_path = root / "entries.csv"
            jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=tuple(row))
                writer.writeheader()
                writer.writerow(row)

            self.assertEqual(load_entry_rows(jsonl), (row,))
            self.assertEqual(load_entry_rows(csv_path)[0]["strategy_id"], "strategy-a")

    def test_runner_groups_queries_clamps_holdout_and_writes_one_report(self) -> None:
        class RecordingRepository:
            def __init__(self) -> None:
                self.calls: list[tuple[object, ...]] = []

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.calls.append((instrument, timeframe, start_ms, end_ms, kwargs))
                return flat_candles(384, close=101.0)

        rows = [
            {
                "strategy_id": "strategy-a",
                "instrument": "BTC-USDT-SWAP",
                "direction": direction,
                "entry_time": 0,
                "entry_price": 100.0,
                "stop_price": 99.0 if direction == "long" else 101.0,
            }
            for direction in ("long", "short")
        ]
        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "entries.jsonl"
            output = root / "Universal Entry Quality Analyzer Report.md"
            source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            result = run_entry_quality_analyzer(
                input_path=source,
                output_path=output,
                repository=repository,
                timeframe="15m",
                max_horizon_hours=96,
                holdout_start_ms=200 * HOUR_MS,
            )
            report = output.read_text(encoding="utf-8")
            generated = tuple(path.name for path in root.iterdir() if path.suffix == ".md")

        self.assertEqual(result.valid_entries, 2)
        self.assertEqual(len(repository.calls), 1)
        self.assertLess(repository.calls[0][3], 200 * HOUR_MS)
        self.assertEqual(generated, (output.name,))
        self.assertEqual(report.count("| metric | value | note |"), 1)
        self.assertEqual(report.count("| problem | count | rate | meaning | suggested_action |"), 1)
        self.assertIn("missing_stop_rate", report)
        self.assertIn("| win_rate_1H | 50.00% |", report)
        self.assertIn("low_MFE_entry", report)

    def test_runner_fetches_target_close_for_unaligned_entry_time(self) -> None:
        class RecordingRepository:
            def __init__(self) -> None:
                self.end_ms = None

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.end_ms = end_ms
                return ()

        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "entries.jsonl"
            source.write_text(json.dumps({
                "strategy_id": "strategy-a",
                "instrument": "BTC-USDT-SWAP",
                "direction": "long",
                "entry_time": 5 * 60 * 1000,
                "entry_price": 100.0,
            }) + "\n", encoding="utf-8")
            run_entry_quality_analyzer(
                input_path=source,
                output_path=root / "report.md",
                repository=repository,
                timeframe="15m",
                max_horizon_hours=1,
                holdout_start_ms=10 * HOUR_MS,
            )

        self.assertEqual(repository.end_ms, HOUR_MS)

    def test_runner_rejects_entries_at_or_after_holdout(self) -> None:
        class NoQueryRepository:
            def load_range(self, *args, **kwargs):
                self.fail("must not query holdout data")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "entries.jsonl"
            source.write_text(json.dumps({
                "strategy_id": "strategy-a",
                "instrument": "BTC-USDT-SWAP",
                "direction": "long",
                "entry_time": HOUR_MS,
                "entry_price": 100.0,
            }) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "holdout"):
                run_entry_quality_analyzer(
                    input_path=source,
                    output_path=root / "report.md",
                    repository=NoQueryRepository(),
                    timeframe="15m",
                    max_horizon_hours=1,
                    holdout_start_ms=HOUR_MS,
                )

    def test_cli_requires_holdout_and_generates_report_from_read_only_db(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "history.duckdb"
            source = root / "entries.jsonl"
            output = root / "report.md"
            repository = DuckDbCandleRepository(database)
            repository.save_many("BTC-USDT-SWAP", "15m", flat_candles(384, close=101.0), inst_type="SWAP")
            source.write_text(json.dumps({
                "strategy_id": "strategy-a",
                "instrument": "BTC-USDT-SWAP",
                "direction": "long",
                "entry_time": 0,
                "entry_price": 100.0,
                "stop_price": 99.0,
            }) + "\n", encoding="utf-8")

            exit_code = cli_main([
                "--input", str(source),
                "--db", str(database),
                "--output", str(output),
                "--holdout-start", "1970-01-09T08:00:00+00:00",
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            with self.assertRaises(SystemExit):
                cli_main(["--input", str(source), "--db", str(database), "--output", str(output)])


if __name__ == "__main__":
    unittest.main()
