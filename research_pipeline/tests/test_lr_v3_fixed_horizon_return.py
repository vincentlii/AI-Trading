from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trading_system.data.okx_cli import Candle
from research_pipeline.runners.lr_v3_fixed_horizon_return import (
    build_fixed_horizon_return_row,
    classify_fixed_horizon_pattern,
    run_lr_v3_fixed_horizon_return_diagnostic,
)


BAR_MS = 15 * 60_000


def _candle(timestamp_ms: int, *, close: float, confirmed: bool = True) -> Candle:
    return Candle(
        timestamp_ms=timestamp_ms,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=confirmed,
    )


def _event(*, direction: str = "long") -> dict[str, object]:
    return {
        "event_id": "event-1",
        "physical_event_key": "physical-1",
        "instrument": "BTC-USDT-SWAP",
        "direction": direction,
        "signal_time": 20 * BAR_MS,
        "signal_close": 100.0,
        "level_price": 99.0,
        "sweep_extreme": 95.0 if direction == "long" else 105.0,
        "event_atr": 10.0,
        "level_family": "previous_day_high_low",
        "reclaim_span_bars": 1,
        "event_timeframe": "1H_sweep_reclaim",
        "reclaim_time": 20 * BAR_MS,
        "feature_cutoff_time": 20 * BAR_MS,
        "bar_confirmed": True,
    }


class LRV3FixedHorizonReturnTest(unittest.TestCase):
    def test_pattern_classifier_requires_unique_and_subgroup_stability(self):
        self.assertEqual(
            classify_fixed_horizon_pattern(
                overall_means={12: 0.13, 24: 0.15, 36: 0.07, 48: 0.14},
                unique_means={12: 0.09, 24: 0.07, 36: -0.03, 48: 0.01},
                subgroup_means=(0.01, 0.25, 0.13, -0.21),
                audit_passed=True,
            ),
            "short_horizon_only",
        )
        self.assertEqual(
            classify_fixed_horizon_pattern(
                overall_means={12: -0.01, 24: -0.02, 36: -0.03, 48: -0.04},
                unique_means={12: -0.01, 24: -0.02, 36: -0.03, 48: -0.04},
                subgroup_means=(-0.01,),
                audit_passed=True,
            ),
            "pause",
        )

    def test_long_and_short_returns_are_direction_normalized(self):
        confirmation = {
            "confirmation_status": "confirmed",
            "confirmation_time": 21 * BAR_MS,
        }
        candles = (
            _candle(20 * BAR_MS, close=100.0),
            _candle(68 * BAR_MS, close=102.0),
            _candle(116 * BAR_MS, close=98.0),
        )

        long_row = build_fixed_horizon_return_row(
            event=_event(), confirmation=confirmation, candles=candles
        )
        short_row = build_fixed_horizon_return_row(
            event=_event(direction="short"), confirmation=confirmation, candles=candles
        )

        self.assertAlmostEqual(long_row["forward_return_pct_12h"], 2.0)
        self.assertAlmostEqual(long_row["forward_return_pct_24h"], -2.0)
        self.assertAlmostEqual(short_row["forward_return_pct_12h"], -2.0)
        self.assertAlmostEqual(short_row["forward_return_pct_24h"], 2.0)

    def test_missing_exact_future_bar_is_not_backfilled(self):
        confirmation = {
            "confirmation_status": "confirmed",
            "confirmation_time": 21 * BAR_MS,
        }
        candles = (
            _candle(20 * BAR_MS, close=100.0),
            _candle(67 * BAR_MS, close=103.0),
        )

        row = build_fixed_horizon_return_row(
            event=_event(), confirmation=confirmation, candles=candles
        )

        self.assertIsNone(row["forward_return_pct_12h"])
        self.assertEqual(row["missing_future_horizons"], ("12h", "24h", "36h", "48h"))

    def test_runner_writes_only_requested_report(self):
        event = _event()
        candles = []
        for index in range(0, 220):
            close = 100.0
            if index == 20:
                close = 102.0
            candles.append(_candle(index * BAR_MS, close=close))

        class Repository:
            def load_range(self, *args, **kwargs):
                return tuple(candles)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "event_rows.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
            (source / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "dataset_window": ["1970-01-01", "1970-01-04"],
                        "holdout_accessed": False,
                        "audit_status": "pass",
                    }
                ),
                encoding="utf-8",
            )
            report = root / "lr_v3_fixed_horizon_return_diagnostic.md"

            result = run_lr_v3_fixed_horizon_return_diagnostic(
                repository=Repository(), source_root=source, report_path=report
            )

            self.assertEqual(result.confirmed_event_count, 1)
            self.assertTrue(result.audit_passed)
            self.assertEqual({path.name for path in root.iterdir()}, {"source", report.name})
            self.assertIn("diagnostic-only", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
