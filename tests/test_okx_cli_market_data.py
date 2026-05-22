import json
import unittest
from unittest.mock import patch
from pathlib import Path

from trading_system.data.okx_cli import OkxCliMarketData


class FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


class OkxCliMarketDataTests(unittest.TestCase):
    def test_get_ticker_calls_okx_cli_and_parses_numeric_fields(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            payload = [
                {
                    "instId": "BTC-USDT",
                    "last": "79888",
                    "askPx": "79888.1",
                    "bidPx": "79888",
                    "open24h": "81683.3",
                    "high24h": "82134.9",
                    "low24h": "79880",
                    "vol24h": "8967.37440378",
                    "ts": "1778604648000",
                }
            ]
            return FakeCompletedProcess(json.dumps(payload))

        client = OkxCliMarketData(okx_command="okx", runner=runner)
        ticker = client.get_ticker("BTC-USDT")

        self.assertEqual(calls[0][0], ["okx", "market", "ticker", "BTC-USDT", "--json"])
        self.assertTrue(calls[0][1]["check"])
        self.assertEqual(calls[0][1]["encoding"], "utf-8")
        self.assertEqual(calls[0][1]["errors"], "replace")
        self.assertEqual(ticker.inst_id, "BTC-USDT")
        self.assertEqual(ticker.last, 79888.0)
        self.assertEqual(ticker.open_24h, 81683.3)
        self.assertEqual(ticker.volume_24h, 8967.37440378)
        self.assertEqual(ticker.timestamp_ms, 1778604648000)

    def test_get_candles_calls_okx_cli_and_maps_ohlcv_rows(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            payload = [
                [
                    "1778601600000",
                    "80331",
                    "80428.1",
                    "79839.9",
                    "79994",
                    "770.6369446",
                    "61787667.658590807",
                    "61787667.658590807",
                    "0",
                ]
            ]
            return FakeCompletedProcess(json.dumps(payload))

        client = OkxCliMarketData(okx_command="okx", runner=runner)
        candles = client.get_candles("BTC-USDT", bar="1H", limit=1)

        self.assertEqual(calls[0], ["okx", "market", "candles", "BTC-USDT", "--bar", "1H", "--limit", "1", "--json"])
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].timestamp_ms, 1778601600000)
        self.assertEqual(candles[0].open, 80331.0)
        self.assertEqual(candles[0].high, 80428.1)
        self.assertEqual(candles[0].low, 79839.9)
        self.assertEqual(candles[0].close, 79994.0)
        self.assertEqual(candles[0].volume, 770.6369446)
        self.assertFalse(candles[0].is_confirmed)

    def test_get_candles_appends_after_and_before_before_json(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return FakeCompletedProcess(json.dumps([]))

        client = OkxCliMarketData(okx_command="okx", runner=runner)
        candles = client.get_candles(
            "BTC-USDT",
            bar="1H",
            limit=100,
            after=1778601600000,
            before=1778688000000,
        )

        self.assertEqual(candles, ())
        self.assertEqual(
            calls[0],
            [
                "okx",
                "market",
                "candles",
                "BTC-USDT",
                "--bar",
                "1H",
                "--limit",
                "100",
                "--after",
                "1778601600000",
                "--before",
                "1778688000000",
                "--json",
            ],
        )

    def test_constructor_reads_okx_command_from_environment_when_not_explicit(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return FakeCompletedProcess(json.dumps([]))

        with patch.dict("os.environ", {"OKX_CLI_COMMAND": "okx-sandbox"}):
            client = OkxCliMarketData(runner=runner)
            client.get_candles("BTC-USDT", bar="1H", limit=1)

        self.assertEqual(calls[0][0], "okx-sandbox")

    def test_constructor_falls_back_to_windows_npm_okx_command(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return FakeCompletedProcess(json.dumps([]))

        appdata = Path("C:/Users/test/AppData/Roaming")
        with (
            patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=True),
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.exists", return_value=True),
        ):
            client = OkxCliMarketData(runner=runner)
            client.get_candles("BTC-USDT", bar="1H", limit=1)

        self.assertEqual(calls[0][0], str(appdata / "npm" / "okx.cmd"))

    def test_explicit_okx_command_takes_precedence_over_environment(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return FakeCompletedProcess(json.dumps([]))

        with patch.dict("os.environ", {"OKX_CLI_COMMAND": "okx-sandbox"}):
            client = OkxCliMarketData(okx_command="okx-live", runner=runner)
            client.get_candles("BTC-USDT", bar="1H", limit=1)

        self.assertEqual(calls[0][0], "okx-live")

    def test_get_instruments_calls_okx_cli_and_maps_contract_fields(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            payload = [
                {
                    "instId": "BTC-USDT",
                    "instType": "SPOT",
                    "state": "live",
                    "listTime": "1606468572000",
                    "tickSz": "0.1",
                    "lotSz": "0.00000001",
                    "minSz": "0.00001",
                    "baseCcy": "BTC",
                    "quoteCcy": "USDT",
                    "instCategory": "1",
                }
            ]
            return FakeCompletedProcess(json.dumps(payload))

        client = OkxCliMarketData(okx_command="okx", runner=runner)
        instruments = client.get_instruments(inst_type="SPOT", inst_id="BTC-USDT")

        self.assertEqual(
            calls[0],
            [
                "okx",
                "market",
                "instruments",
                "--instType",
                "SPOT",
                "--instId",
                "BTC-USDT",
                "--json",
            ],
        )
        self.assertEqual(len(instruments), 1)
        self.assertEqual(instruments[0].inst_id, "BTC-USDT")
        self.assertEqual(instruments[0].inst_type, "SPOT")
        self.assertEqual(instruments[0].state, "live")
        self.assertEqual(instruments[0].list_time_ms, 1606468572000)
        self.assertEqual(instruments[0].tick_size, "0.1")
        self.assertEqual(instruments[0].lot_size, "0.00000001")
        self.assertEqual(instruments[0].min_size, "0.00001")
        self.assertEqual(instruments[0].base_ccy, "BTC")
        self.assertEqual(instruments[0].quote_ccy, "USDT")
        self.assertEqual(instruments[0].inst_category, "1")


if __name__ == "__main__":
    unittest.main()
