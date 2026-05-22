import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.download_okx_history import parse_args
from trading_system.data.download import OkxHistoryDownloader
from trading_system.data.history import DownloadState, DuckDbCandleRepository
from trading_system.data.okx_cli import Candle


def candle(timestamp_ms, *, close=1.0, is_confirmed=True):
    return Candle(
        timestamp_ms=timestamp_ms,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10.0,
        volume_currency=20.0,
        volume_currency_quote=30.0,
        is_confirmed=is_confirmed,
    )


class FakeOkxClient:
    def __init__(self, pages=None, failures=None):
        self.pages = pages or {}
        self.failures = failures or {}
        self.calls = []

    def get_candles(self, inst_id, *, bar, limit, after=None, before=None):
        self.calls.append(
            {
                "inst_id": inst_id,
                "bar": bar,
                "limit": limit,
                "after": after,
                "before": before,
            }
        )
        failure = self.failures.get((inst_id, bar))
        if failure is not None:
            raise failure
        return tuple(self.pages.get((inst_id, bar, after), ()))


class OkxHistoryDownloaderTests(unittest.TestCase):
    def repository(self, temporary_directory):
        return DuckDbCandleRepository(Path(temporary_directory) / "history.duckdb")

    def test_download_symbol_bar_saves_only_confirmed_candles_and_updates_state(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)
            client = FakeOkxClient(
                pages={
                    ("BTC-USDT", "1H", None): (
                        candle(3000, close=3.0),
                        candle(2000, close=2.0, is_confirmed=False),
                        candle(1000, close=1.0),
                    )
                }
            )
            downloader = OkxHistoryDownloader(client, repository, cli_version="1.2.3")

            summary = downloader.download_symbol_bar("BTC-USDT", "1H", limit=100, max_pages=1)

            self.assertEqual(summary.venue, "okx")
            self.assertEqual(summary.inst_type, "SPOT")
            self.assertEqual(summary.inst_id, "BTC-USDT")
            self.assertEqual(summary.bar, "1H")
            self.assertEqual(summary.pages_requested, 1)
            self.assertEqual(summary.pages_fetched, 1)
            self.assertEqual(summary.received_count, 3)
            self.assertEqual(summary.saved_count, 2)
            self.assertEqual(summary.skipped_unconfirmed_count, 1)
            self.assertEqual(summary.earliest_ts_ms, 1000)
            self.assertEqual(summary.latest_confirmed_ts_ms, 3000)
            self.assertEqual(summary.row_count, 2)
            self.assertEqual(summary.error, "")

            stored = repository.list_candles("BTC-USDT", "1H")
            self.assertEqual([item.timestamp_ms for item in stored], [1000, 3000])
            self.assertEqual(
                repository.get_download_state("okx", "BTC-USDT", "1H"),
                DownloadState(
                    venue="okx",
                    inst_type="SPOT",
                    inst_id="BTC-USDT",
                    bar="1H",
                    earliest_ts_ms=1000,
                    latest_confirmed_ts_ms=3000,
                    row_count=2,
                    last_success_at_ms=summary.last_success_at_ms,
                    last_error="",
                    cli_version="1.2.3",
                ),
            )

    def test_download_symbol_bar_empty_response_does_not_create_state(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)
            client = FakeOkxClient(pages={("BTC-USDT", "1H", None): ()})
            downloader = OkxHistoryDownloader(client, repository)

            summary = downloader.download_symbol_bar("BTC-USDT", "1H")

            self.assertEqual(summary.pages_requested, 1)
            self.assertEqual(summary.pages_fetched, 0)
            self.assertEqual(summary.received_count, 0)
            self.assertEqual(summary.saved_count, 0)
            self.assertIsNone(summary.earliest_ts_ms)
            self.assertIsNone(summary.latest_confirmed_ts_ms)
            self.assertEqual(summary.row_count, 0)
            self.assertEqual(summary.error, "")
            self.assertIsNone(repository.get_download_state("okx", "BTC-USDT", "1H"))

    def test_download_many_continues_when_one_symbol_bar_fails(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)
            client = FakeOkxClient(
                pages={("ETH-USDT", "1H", None): (candle(5000, close=5.0),)},
                failures={("BTC-USDT", "1H"): RuntimeError("network down")},
            )
            downloader = OkxHistoryDownloader(client, repository)

            summaries = downloader.download_many(("BTC-USDT", "ETH-USDT"), ("1H",), limit=10)

            self.assertEqual(len(summaries), 2)
            self.assertIn("network down", summaries[0].error)
            self.assertEqual(summaries[0].saved_count, 0)
            self.assertEqual(summaries[1].inst_id, "ETH-USDT")
            self.assertEqual(summaries[1].saved_count, 1)
            self.assertEqual(repository.list_candles("ETH-USDT", "1H")[0].timestamp_ms, 5000)

    def test_download_symbol_bar_uses_oldest_timestamp_as_after_cursor(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)
            client = FakeOkxClient(
                pages={
                    ("BTC-USDT", "1H", None): (
                        candle(3000, close=3.0),
                        candle(2000, close=2.0),
                    ),
                    ("BTC-USDT", "1H", 2000): (candle(1000, close=1.0),),
                }
            )
            downloader = OkxHistoryDownloader(client, repository)

            summary = downloader.download_symbol_bar("BTC-USDT", "1H", limit=2, max_pages=2)

            self.assertEqual([call["after"] for call in client.calls], [None, 2000])
            self.assertEqual(summary.pages_fetched, 2)
            self.assertEqual(summary.received_count, 3)
            self.assertEqual(summary.saved_count, 3)
            self.assertEqual([item.timestamp_ms for item in repository.list_candles("BTC-USDT", "1H")], [1000, 2000, 3000])

    def test_download_symbol_bar_stops_when_target_min_candles_is_reached(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)
            client = FakeOkxClient(
                pages={
                    ("BTC-USDT", "1H", None): (
                        candle(3000, close=3.0),
                        candle(2000, close=2.0),
                    ),
                    ("BTC-USDT", "1H", 2000): (candle(1000, close=1.0),),
                    ("BTC-USDT", "1H", 1000): (candle(0, close=0.5),),
                }
            )
            downloader = OkxHistoryDownloader(client, repository)

            summary = downloader.download_symbol_bar("BTC-USDT", "1H", limit=2, max_pages=5, target_min_candles=3)

            self.assertEqual([call["after"] for call in client.calls], [None, 2000])
            self.assertEqual(summary.pages_requested, 5)
            self.assertEqual(summary.pages_fetched, 2)
            self.assertEqual(summary.row_count, 3)

    def test_download_symbol_bar_stops_when_start_timestamp_is_reached(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)
            client = FakeOkxClient(
                pages={
                    ("BTC-USDT", "1H", None): (
                        candle(3000, close=3.0),
                        candle(2000, close=2.0),
                    ),
                    ("BTC-USDT", "1H", 2000): (candle(1000, close=1.0),),
                }
            )
            downloader = OkxHistoryDownloader(client, repository)

            summary = downloader.download_symbol_bar("BTC-USDT", "1H", limit=2, max_pages=5, start_ts_ms=1500)

            self.assertEqual([call["after"] for call in client.calls], [None, 2000])
            self.assertEqual(summary.earliest_ts_ms, 1000)
            self.assertEqual(summary.row_count, 3)


class DownloadOkxHistoryScriptTests(unittest.TestCase):
    def test_parse_args_uses_safe_small_defaults(self):
        args = parse_args([])

        self.assertEqual(args.db, "storage/history.duckdb")
        self.assertEqual(args.symbols, ["BTC-USDT", "ETH-USDT", "XAUT-USDT"])
        self.assertEqual(args.bars, ["5m", "15m", "1H", "4H", "1D"])
        self.assertEqual(args.limit, 100)
        self.assertEqual(args.max_pages, 1)
        self.assertIsNone(args.target_min_candles)
        self.assertIsNone(args.start_date)
        self.assertFalse(args.quality_check_after_download)
        self.assertIsNone(args.okx_command)

    def test_parse_args_accepts_custom_download_scope(self):
        args = parse_args(
            [
                "--db",
                "storage/custom.duckdb",
                "--symbols",
                "BTC-USDT",
                "ETH-USDT",
                "--bars",
                "15m",
                "1H",
                "--limit",
                "10",
                "--max-pages",
                "2",
                "--target-min-candles",
                "1000",
                "--start-date",
                "2023-01-01",
                "--quality-check-after-download",
                "--okx-command",
                "okx-live",
            ]
        )

        self.assertEqual(args.db, "storage/custom.duckdb")
        self.assertEqual(args.symbols, ["BTC-USDT", "ETH-USDT"])
        self.assertEqual(args.bars, ["15m", "1H"])
        self.assertEqual(args.limit, 10)
        self.assertEqual(args.max_pages, 2)
        self.assertEqual(args.target_min_candles, 1000)
        self.assertEqual(args.start_date, "2023-01-01")
        self.assertTrue(args.quality_check_after_download)
        self.assertEqual(args.okx_command, "okx-live")


if __name__ == "__main__":
    unittest.main()
