import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from trading_system.data.history import (
    CandleKey,
    CandleRepository,
    DownloadState,
    DuckDbCandleRepository,
    required_bars_for_profiles,
)
from trading_system.data.okx_cli import Candle
from trading_system.timeframe_profiles import list_default_profiles


def candle(timestamp_ms, close=1.0):
    return Candle(
        timestamp_ms=timestamp_ms,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10.0,
        volume_currency=20.0,
        volume_currency_quote=30.0,
        is_confirmed=True,
    )


class CandleRepositoryTests(unittest.TestCase):
    def test_save_many_deduplicates_by_timestamp_and_lists_in_ascending_order(self):
        repository = CandleRepository()

        repository.save_many(
            "BTC-USDT",
            "1H",
            (
                candle(3000, close=3.0),
                candle(1000, close=1.0),
                candle(2000, close=2.0),
                candle(2000, close=22.0),
            ),
        )

        candles = repository.list_candles("BTC-USDT", "1H")

        self.assertEqual([item.timestamp_ms for item in candles], [1000, 2000, 3000])
        self.assertEqual(candles[1].close, 22.0)

    def test_latest_timestamp_returns_latest_saved_candle_timestamp_for_key(self):
        repository = CandleRepository()

        self.assertIsNone(repository.latest_timestamp("BTC-USDT", "1H"))

        repository.save_many("BTC-USDT", "1H", (candle(1000), candle(3000), candle(2000)))
        repository.save_many("ETH-USDT", "1H", (candle(9000),))

        self.assertEqual(repository.latest_timestamp("BTC-USDT", "1H"), 3000)
        self.assertEqual(repository.latest_timestamp("ETH-USDT", "1H"), 9000)

    def test_candle_key_identifies_instrument_and_bar(self):
        self.assertEqual(CandleKey("BTC-USDT", "1H"), CandleKey("BTC-USDT", "1H"))
        self.assertNotEqual(CandleKey("BTC-USDT", "1H"), CandleKey("BTC-USDT", "4H"))


class DuckDbCandleRepositoryTests(unittest.TestCase):
    def repository(self, temporary_directory):
        return DuckDbCandleRepository(Path(temporary_directory) / "history.duckdb")

    def test_save_many_deduplicates_by_full_key_and_lists_in_ascending_order(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)

            repository.save_many(
                "BTC-USDT",
                "1H",
                (
                    candle(3000, close=3.0),
                    candle(1000, close=1.0),
                    candle(2000, close=2.0),
                ),
                venue="okx",
                inst_type="SPOT",
            )
            repository.save_many(
                "BTC-USDT",
                "1H",
                (candle(2000, close=22.0),),
                venue="okx",
                inst_type="SPOT",
            )
            repository.save_many(
                "BTC-USDT",
                "1H",
                (candle(2000, close=222.0),),
                venue="binance",
                inst_type="SPOT",
            )

            candles = repository.list_candles("BTC-USDT", "1H", venue="okx", inst_type="SPOT")

            self.assertEqual([item.timestamp_ms for item in candles], [1000, 2000, 3000])
            self.assertEqual(candles[1].close, 22.0)
            self.assertEqual(
                repository.list_candles("BTC-USDT", "1H", venue="binance", inst_type="SPOT")[0].close,
                222.0,
            )

    def test_load_range_filters_confirmed_candles_by_default(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)

            repository.save_many(
                "BTC-USDT",
                "1H",
                (
                    candle(1000, close=1.0),
                    candle(2000, close=2.0),
                    Candle(
                        timestamp_ms=3000,
                        open=3.0,
                        high=3.0,
                        low=3.0,
                        close=3.0,
                        volume=10.0,
                        volume_currency=20.0,
                        volume_currency_quote=30.0,
                        is_confirmed=False,
                    ),
                    candle(4000, close=4.0),
                ),
            )

            confirmed = repository.load_range("BTC-USDT", "1H", 1500, 3500)
            all_candles = repository.load_range(
                "BTC-USDT",
                "1H",
                1500,
                3500,
                confirmed_only=False,
            )

            self.assertEqual([item.timestamp_ms for item in confirmed], [2000])
            self.assertEqual([item.timestamp_ms for item in all_candles], [2000, 3000])

    def test_latest_and_earliest_timestamp_are_scoped_by_venue_and_instrument_type(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)

            self.assertIsNone(repository.latest_timestamp("BTC-USDT", "1H"))
            self.assertIsNone(repository.earliest_timestamp("BTC-USDT", "1H"))

            repository.save_many("BTC-USDT", "1H", (candle(3000), candle(1000)))
            repository.save_many(
                "BTC-USDT",
                "1H",
                (candle(9000),),
                venue="okx",
                inst_type="SWAP",
            )

            self.assertEqual(repository.earliest_timestamp("BTC-USDT", "1H"), 1000)
            self.assertEqual(repository.latest_timestamp("BTC-USDT", "1H"), 3000)
            self.assertEqual(
                repository.latest_timestamp("BTC-USDT", "1H", venue="okx", inst_type="SWAP"),
                9000,
            )

    def test_download_state_can_be_written_overwritten_and_read(self):
        with TemporaryDirectory() as temporary_directory:
            repository = self.repository(temporary_directory)

            self.assertIsNone(repository.get_download_state("okx", "BTC-USDT", "1H"))
            self.assertIsNone(repository.get_download_state("okx", "BTC-USDT", "1H", inst_type="SWAP"))

            repository.update_download_state(
                DownloadState(
                    venue="okx",
                    inst_type="SPOT",
                    inst_id="BTC-USDT",
                    bar="1H",
                    earliest_ts_ms=1000,
                    latest_confirmed_ts_ms=2000,
                    row_count=2,
                    last_success_at_ms=12345,
                    last_error="",
                    cli_version="1.0.0",
                )
            )
            repository.update_download_state(
                DownloadState(
                    venue="okx",
                    inst_type="SPOT",
                    inst_id="BTC-USDT",
                    bar="1H",
                    earliest_ts_ms=500,
                    latest_confirmed_ts_ms=3000,
                    row_count=4,
                    last_success_at_ms=67890,
                    last_error="rate limited",
                    cli_version="1.0.1",
                )
            )

            self.assertEqual(
                repository.get_download_state("okx", "BTC-USDT", "1H"),
                DownloadState(
                    venue="okx",
                    inst_type="SPOT",
                    inst_id="BTC-USDT",
                    bar="1H",
                    earliest_ts_ms=500,
                    latest_confirmed_ts_ms=3000,
                    row_count=4,
                    last_success_at_ms=67890,
                    last_error="rate limited",
                    cli_version="1.0.1",
                ),
            )

            repository.update_download_state(
                DownloadState(
                    venue="okx",
                    inst_type="SWAP",
                    inst_id="BTC-USDT",
                    bar="1H",
                    earliest_ts_ms=800,
                    latest_confirmed_ts_ms=900,
                    row_count=1,
                    last_success_at_ms=99999,
                    last_error="",
                    cli_version="1.0.1",
                )
            )

            self.assertEqual(
                repository.get_download_state("okx", "BTC-USDT", "1H", inst_type="SWAP"),
                DownloadState(
                    venue="okx",
                    inst_type="SWAP",
                    inst_id="BTC-USDT",
                    bar="1H",
                    earliest_ts_ms=800,
                    latest_confirmed_ts_ms=900,
                    row_count=1,
                    last_success_at_ms=99999,
                    last_error="",
                    cli_version="1.0.1",
                ),
            )


class RequiredBarsForProfilesTests(unittest.TestCase):
    def test_required_bars_for_default_profiles_are_unique_okx_cli_bars(self):
        bars = required_bars_for_profiles(list_default_profiles())

        self.assertEqual(bars, ("5m", "15m", "1H", "4H", "1D"))


if __name__ == "__main__":
    unittest.main()
