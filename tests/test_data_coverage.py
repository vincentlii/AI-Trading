import unittest

from trading_system.data.coverage import (
    CoverageThresholds,
    build_bar_coverage_rows,
    build_profile_coverage_rows,
)
from trading_system.data.okx_cli import Candle


def candle(timestamp_ms: int, *, confirmed: bool = True) -> Candle:
    return Candle(
        timestamp_ms=timestamp_ms,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=10.0,
        volume_currency=10.0,
        volume_currency_quote=1000.0,
        is_confirmed=confirmed,
    )


class FakeCoverageRepository:
    def __init__(self, candles_by_key):
        self.candles_by_key = dict(candles_by_key)

    def list_candles(self, inst_id, bar, *, venue="okx", inst_type="SPOT"):
        return tuple(self.candles_by_key.get((venue, inst_type, inst_id, bar), ()))


class DataCoverageTests(unittest.TestCase):
    def test_bar_coverage_rows_expose_thresholds_and_quality_issues(self):
        repository = FakeCoverageRepository(
            {
                ("okx", "SPOT", "BTC-USDT", "1H"): tuple(candle(index * 3_600_000) for index in range(300)),
                ("okx", "SPOT", "BTC-USDT", "4H"): tuple(candle(index * 14_400_000) for index in range(1000)),
                ("okx", "SPOT", "BTC-USDT", "1D"): (
                    candle(0),
                    candle(86_400_000, confirmed=False),
                    candle(172_800_000),
                ),
            }
        )

        rows = build_bar_coverage_rows(
            repository,
            targets=(("BTC/USDT", "BTC-USDT", "okx", "SPOT"),),
            bars=("1H", "4H", "1D"),
            thresholds=CoverageThresholds(runnable=300, diagnostic=1000, formal_years=1),
        )

        rows_by_bar = {row["bar"]: row for row in rows}
        self.assertTrue(rows_by_bar["1H"]["meets_regime_minimum"])
        self.assertTrue(rows_by_bar["1H"]["meets_minimum_runnable"])
        self.assertFalse(rows_by_bar["1H"]["meets_initial_diagnostic"])
        self.assertTrue(rows_by_bar["4H"]["meets_initial_diagnostic"])
        self.assertFalse(rows_by_bar["1D"]["quality_pass"])
        self.assertIn("unconfirmed_candle", rows_by_bar["1D"]["quality_issue_codes"])

    def test_profile_coverage_rows_identify_blocking_timeframes(self):
        repository = FakeCoverageRepository(
            {
                ("okx", "SPOT", "BTC-USDT", "15m"): tuple(candle(index * 900_000) for index in range(300)),
                ("okx", "SPOT", "BTC-USDT", "1H"): tuple(candle(index * 3_600_000) for index in range(299)),
                ("okx", "SPOT", "BTC-USDT", "4H"): tuple(candle(index * 14_400_000) for index in range(1000)),
            }
        )

        rows = build_profile_coverage_rows(
            repository,
            targets=(("BTC/USDT", "BTC-USDT", "okx", "SPOT"),),
            profile_keys=("B",),
            thresholds=CoverageThresholds(runnable=300, diagnostic=1000, formal_years=1),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "B")
        self.assertFalse(rows[0]["can_run"])
        self.assertEqual(rows[0]["blocking_timeframes"], ("1h",))
        self.assertEqual(rows[0]["minimum_row_count"], 299)


if __name__ == "__main__":
    unittest.main()
