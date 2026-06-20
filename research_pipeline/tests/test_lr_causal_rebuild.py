import importlib.util
import inspect
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_pipeline.cli.research import main
from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import LRCausalEvent, LRCausalLevel
from research_pipeline.runners.lr_causal_rebuild import (
    _diagnostic_summaries,
    anatomy_rejection_row,
    causal_atr,
    build_anatomy_rows,
    development_candidate_cutoff,
    level_validity_windows,
    run_lr_causal_anatomy,
    validate_development_window,
)


MINUTE = 60_000
HOUR = 60 * MINUTE


def _candle(timestamp: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


class LRCausalRebuildRunnerTest(unittest.TestCase):
    def test_runner_module_exists(self) -> None:
        spec = importlib.util.find_spec("research_pipeline.runners.lr_causal_rebuild")

        self.assertIsNotNone(spec)

    def test_development_cutoff_keeps_full_trade_path_out_of_holdout(self) -> None:
        holdout_start = 1_735_689_600_000

        cutoff = development_candidate_cutoff(holdout_start)

        self.assertEqual(cutoff, holdout_start - 20 * HOUR)

    def test_anatomy_enters_after_reclaim_and_emits_diagnostic_only_paths(self) -> None:
        event = LRCausalEvent(
            event_id="event-1",
            market_event_key="market-1",
            level_id="level-1",
            level_family="session_high_low",
            direction="long",
            sweep_bar_time=0,
            sweep_time=15 * MINUTE,
            reclaim_bar_time=15 * MINUTE,
            reclaim_time=30 * MINUTE,
            sweep_extreme=98.0,
            reclaim_close=100.0,
            atr_15m=1.0,
            atr_4h=4.0,
            instrument="BTC-USDT-SWAP",
            level_price=99.0,
        )
        candles = (
            _candle(30 * MINUTE, open_=100, high=101, low=99, close=100.5),
            _candle(45 * MINUTE, open_=100.5, high=102, low=100, close=101.5),
            _candle(60 * MINUTE, open_=101.5, high=103, low=101, close=102.5),
        )

        candidate, diagnostics = build_anatomy_rows(event, candles)

        self.assertEqual(candidate["signal_time"], 30 * MINUTE)
        self.assertEqual(candidate["entry_time"], 45 * MINUTE)
        self.assertEqual(candidate["entry_model"], "reclaim_market_next_15m_open")
        self.assertEqual(candidate["row_type"], "proposal_candidate")
        self.assertFalse(candidate["eligible_for_performance"])
        self.assertEqual([row["horizon_bars"] for row in diagnostics], [1, 2])
        self.assertTrue(all(row["row_type"] == "diagnostic" for row in diagnostics))
        self.assertTrue(all(not row["eligible_for_performance"] for row in diagnostics))
        self.assertTrue(all("forward_ATR" in row for row in diagnostics))
        self.assertTrue(all("MFE_ATR" in row for row in diagnostics))
        self.assertTrue(all("MAE_ATR" in row for row in diagnostics))
        summary = _diagnostic_summaries(diagnostics)
        self.assertIn("mean_forward_ATR", summary[0])
        self.assertIn("median_forward_ATR", summary[0])

    def test_anatomy_rejects_stop_on_wrong_side_of_entry(self) -> None:
        event = LRCausalEvent(
            event_id="event-invalid-stop",
            market_event_key="market-invalid-stop",
            level_id="level-invalid-stop",
            level_family="session_high_low",
            direction="long",
            sweep_bar_time=0,
            sweep_time=15 * MINUTE,
            reclaim_bar_time=15 * MINUTE,
            reclaim_time=30 * MINUTE,
            sweep_extreme=101.0,
            reclaim_close=102.0,
            atr_15m=1.0,
            atr_4h=4.0,
        )
        candles = (
            _candle(30 * MINUTE, open_=102, high=103, low=101, close=102),
            _candle(45 * MINUTE, open_=100.5, high=102, low=100, close=101),
        )

        with self.assertRaisesRegex(ValueError, "invalid long stop geometry"):
            build_anatomy_rows(event, candles)

        rejection = anatomy_rejection_row(event, "invalid long stop geometry")
        self.assertEqual(rejection["decision"], "rejected")
        self.assertEqual(rejection["reject_reason"], "invalid long stop geometry")
        self.assertEqual(rejection["event_id"], event.event_id)

    def test_anatomy_path_builder_accepts_shared_timestamp_index(self) -> None:
        parameters = inspect.signature(build_anatomy_rows).parameters

        self.assertIn("timestamps", parameters)

    def test_level_validity_ends_at_next_same_family_and_direction(self) -> None:
        levels = (
            LRCausalLevel("a", "session_high_low", "long", 99.0, 10, 0),
            LRCausalLevel("other", "session_high_low", "short", 101.0, 15, 0),
            LRCausalLevel("b", "session_high_low", "long", 98.0, 20, 0),
        )

        windows = level_validity_windows(levels, end_time=30)

        self.assertEqual(windows["a"], 20)
        self.assertEqual(windows["other"], 30)
        self.assertEqual(windows["b"], 30)

    def test_atr_uses_only_bars_closed_by_cutoff(self) -> None:
        candles = tuple(
            _candle(index * 15 * MINUTE, open_=100, high=102, low=99, close=101)
            for index in range(15)
        ) + (_candle(15 * 15 * MINUTE, open_=100, high=1000, low=1, close=500),)

        atr = causal_atr(candles, cutoff_time=15 * 15 * MINUTE, timeframe_ms=15 * MINUTE, period=14)

        self.assertAlmostEqual(atr, 3.0)

    def test_development_window_cannot_cross_sealed_holdout(self) -> None:
        with self.assertRaisesRegex(ValueError, "sealed holdout"):
            validate_development_window("2024-11-01", "2024-12-02")

        self.assertEqual(
            validate_development_window("2021-01-01", "2021-01-15"),
            ("2021-01-01", "2021-01-15"),
        )

    def test_runner_writes_non_performance_anatomy_artifacts(self) -> None:
        class EmptyRepository:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int, int]] = []

            def load_range(self, inst_id, bar, start_ms, end_ms, **kwargs):
                self.calls.append((bar, start_ms, end_ms))
                return ()

        repository = EmptyRepository()
        target = SimpleNamespace(
            inst_id="BTC-USDT-SWAP",
            venue="okx",
            inst_type="SWAP",
        )
        preset = SimpleNamespace(
            config_fingerprint="test-config",
            to_scan_config=lambda: SimpleNamespace(targets=(target,)),
        )
        with tempfile.TemporaryDirectory() as directory:
            result = run_lr_causal_anatomy(
                repository=repository,
                preset=preset,
                output_root=Path(directory),
                start_date="2021-01-01",
                end_date="2021-01-15",
            )
            run_root = Path(result.run_root)

            manifest = json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "causal_anatomy.v4")
            self.assertEqual(manifest["audit_status"], "not_run_no_closed_trade_unverifiable")
            self.assertFalse(manifest["formal_conclusion_enabled"])
            self.assertTrue((run_root / "candidate_rows.jsonl").exists())
            self.assertTrue((run_root / "level_rows.jsonl").exists())
            self.assertTrue((run_root / "diagnostic_rows.jsonl").exists())
            self.assertEqual((run_root / "closed_trade_rows.jsonl").read_text(encoding="utf-8"), "")
            self.assertEqual({call[0] for call in repository.calls}, {"15m", "4H"})
            holdout_start_ms = 1_733_011_200_000
            self.assertTrue(all(call[2] < holdout_start_ms for call in repository.calls))

    def test_cli_dispatches_development_anatomy_window(self) -> None:
        result = SimpleNamespace(as_json=lambda: "{}", run_root="unused")
        with (
            patch("research_pipeline.cli.research.load_backtest_preset", return_value="preset"),
            patch("research_pipeline.cli.research.DuckDbCandleRepository", return_value="repository"),
            patch(
                "research_pipeline.cli.research.run_lr_causal_anatomy",
                return_value=result,
                create=True,
            ) as runner,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = main(
                [
                    "lr-causal-rebuild",
                    "--stage",
                    "anatomy",
                    "--mode",
                    "development",
                    "--start",
                    "2021-01-01",
                    "--end",
                    "2021-01-15",
                ]
            )

        self.assertEqual(exit_code, 0)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["start_date"], "2021-01-01")
        self.assertEqual(runner.call_args.kwargs["end_date"], "2021-01-15")


if __name__ == "__main__":
    unittest.main()
