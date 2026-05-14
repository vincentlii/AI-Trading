import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from scripts.check_data_quality import parse_args
from trading_system.data.history import DuckDbCandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.data.quality import check_repository_symbol_bar


def candle(timestamp_ms, *, confirmed=True, open_=100.0, high=101.0, low=99.0, close=100.0, volume=10.0):
    return Candle(
        timestamp_ms=timestamp_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=confirmed,
    )


class FakeRepository:
    def __init__(self, candles):
        self.candles = tuple(candles)

    def list_candles(self, inst_id, bar, *, venue="okx", inst_type="SPOT"):
        return self.candles


class DataQualityTests(unittest.TestCase):
    def issue_codes(self, report):
        return tuple(issue.code for issue in report.issues)

    def test_continuous_confirmed_candles_pass_quality_checks(self):
        report = check_repository_symbol_bar(
            FakeRepository((candle(0), candle(60_000), candle(120_000))),
            "BTC-USDT",
            "1m",
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.row_count, 3)
        self.assertEqual(report.issues, ())

    def test_detects_gaps_duplicates_unconfirmed_bad_ohlc_and_negative_volume(self):
        report = check_repository_symbol_bar(
            FakeRepository(
                (
                    candle(0),
                    candle(60_000, confirmed=False),
                    candle(60_000),
                    candle(240_000, high=98.0, low=99.0),
                    candle(300_000, volume=-1.0),
                )
            ),
            "BTC-USDT",
            "1m",
        )

        codes = self.issue_codes(report)

        self.assertFalse(report.passed)
        self.assertIn("duplicate_timestamp", codes)
        self.assertIn("unconfirmed_candle", codes)
        self.assertIn("missing_interval", codes)
        self.assertIn("invalid_ohlc", codes)
        self.assertIn("negative_volume", codes)

    def test_empty_data_returns_fail_report_without_raising(self):
        report = check_repository_symbol_bar(FakeRepository(()), "BTC-USDT", "1H")

        self.assertFalse(report.passed)
        self.assertEqual(report.row_count, 0)
        self.assertEqual(self.issue_codes(report), ("empty_data",))

    def test_duckdb_repository_uses_temporary_database_for_quality_checks(self):
        with TemporaryDirectory() as temporary_directory:
            repository = DuckDbCandleRepository(Path(temporary_directory) / "history.duckdb")
            repository.save_many("BTC-USDT", "1H", (candle(0), candle(3_600_000)))

            report = check_repository_symbol_bar(repository, "BTC-USDT", "1H")

            self.assertTrue(report.passed)
            self.assertEqual(report.earliest_ts_ms, 0)
            self.assertEqual(report.latest_ts_ms, 3_600_000)


class CheckDataQualityScriptTests(unittest.TestCase):
    def test_parse_args_uses_project_safe_defaults(self):
        args = parse_args([])

        self.assertEqual(args.db, "storage/history.duckdb")
        self.assertEqual(args.symbols, ["BTC-USDT", "ETH-USDT", "XAUT-USDT"])
        self.assertEqual(args.bars, ["5m", "15m", "1H", "4H", "1D"])

    def test_parse_args_accepts_custom_scope(self):
        args = parse_args(
            [
                "--db",
                "storage/custom.duckdb",
                "--symbols",
                "BTC-USDT",
                "--bars",
                "15m",
                "1H",
            ]
        )

        self.assertEqual(args.db, "storage/custom.duckdb")
        self.assertEqual(args.symbols, ["BTC-USDT"])
        self.assertEqual(args.bars, ["15m", "1H"])


if __name__ == "__main__":
    unittest.main()
