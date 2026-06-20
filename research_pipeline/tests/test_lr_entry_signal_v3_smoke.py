from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from trading_system.data.okx_cli import Candle
from research_pipeline.runners.lr_entry_signal_v3_smoke import (
    classify_v3_decision,
    evaluate_structural_confirmation,
    run_lr_entry_signal_v3_smoke,
)


BAR_MS = 15 * 60_000


def _candle(
    timestamp_ms: int,
    *,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    confirmed: bool = True,
) -> Candle:
    return Candle(
        timestamp_ms=timestamp_ms,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=10_000.0,
        is_confirmed=confirmed,
    )


def _event(*, direction: str = "long") -> dict[str, object]:
    return {
        "event_id": "event-1",
        "physical_event_key": "physical-1",
        "instrument": "BTC-USDT-SWAP",
        "event_timeframe": "1H_sweep_reclaim",
        "level_family": "previous_day_high_low",
        "direction": direction,
        "signal_time": 4 * BAR_MS,
        "signal_close": 100.0,
        "sweep_extreme": 95.0 if direction == "long" else 105.0,
        "event_atr": 10.0,
        "reclaim_span_bars": 1,
    }


class LREntrySignalV3SmokeTest(unittest.TestCase):
    def test_long_confirms_on_close_above_previous_high_in_upper_half(self):
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(4 * BAR_MS, high=103.0, low=99.5, close=102.0),
            _candle(5 * BAR_MS, high=107.0, low=101.0, close=106.0),
        )

        row = evaluate_structural_confirmation(_event(), candles)

        self.assertEqual(row["confirmation_status"], "confirmed")
        self.assertEqual(row["time_to_confirmation_minutes"], 15)
        self.assertEqual(row["time_to_0_5R_minutes"], 30)
        self.assertEqual(row["invalidation_first_status"], "one_r_first")

    def test_short_uses_previous_low_and_lower_half(self):
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(4 * BAR_MS, high=100.5, low=97.0, close=98.0),
            _candle(5 * BAR_MS, high=98.0, low=94.0, close=95.0),
        )

        row = evaluate_structural_confirmation(_event(direction="short"), candles)

        self.assertEqual(row["confirmation_status"], "confirmed")
        self.assertEqual(row["time_to_confirmation_minutes"], 15)
        self.assertEqual(row["time_to_0_5R_minutes"], 30)

    def test_invalidation_on_confirmation_bar_is_failed_before_confirmation(self):
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(4 * BAR_MS, high=103.0, low=93.0, close=102.0),
        )

        row = evaluate_structural_confirmation(_event(), candles)

        self.assertEqual(row["confirmation_status"], "failed_before_confirmation")
        self.assertIsNone(row["confirmation_time"])

    def test_only_four_confirmed_post_signal_bars_are_observed(self):
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0),
            _candle(4 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(5 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(6 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(7 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(8 * BAR_MS, high=103.0, low=99.0, close=102.0),
        )

        row = evaluate_structural_confirmation(_event(), candles)

        self.assertEqual(row["confirmation_status"], "no_confirmation")

    def test_unconfirmed_bar_cannot_confirm(self):
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0),
            _candle(4 * BAR_MS, high=103.0, low=99.0, close=102.0, confirmed=False),
        )

        row = evaluate_structural_confirmation(_event(), candles)

        self.assertEqual(row["confirmation_status"], "no_confirmation")
        self.assertIn("missing_confirmed_post_signal_bars", row["data_gaps"])

    def test_missing_early_slot_cannot_shift_confirmation_window_later(self):
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0),
            _candle(5 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(6 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(7 * BAR_MS, high=101.0, low=99.0, close=100.0),
            _candle(8 * BAR_MS, high=103.0, low=99.0, close=102.0),
        )

        row = evaluate_structural_confirmation(_event(), candles)

        self.assertEqual(row["confirmation_status"], "no_confirmation")
        self.assertIn("missing_confirmed_post_signal_bars", row["data_gaps"])

    def test_gate_requires_all_declared_mechanism_thresholds(self):
        decision = classify_v3_decision(
            invalidation_first_rate=0.44,
            one_r_first_rate=0.53,
            event_count=320,
            yearly_counts={2021: 80, 2022: 80, 2023: 80, 2024: 80},
            yearly_improvements={2021: True, 2022: True, 2023: True, 2024: False},
            subgroup_failures=(),
            audit_passed=True,
        )
        self.assertEqual(decision, "A")

        unstable = classify_v3_decision(
            invalidation_first_rate=0.44,
            one_r_first_rate=0.53,
            event_count=320,
            yearly_counts={2021: 80, 2022: 80, 2023: 80, 2024: 80},
            yearly_improvements={2021: True, 2022: True, 2023: False, 2024: False},
            subgroup_failures=("BTC-USDT-SWAP",),
            audit_passed=True,
        )
        self.assertEqual(unstable, "B")

        self.assertEqual(
            classify_v3_decision(
                invalidation_first_rate=0.49,
                one_r_first_rate=0.49,
                event_count=320,
                yearly_counts={2021: 80, 2022: 80, 2023: 80, 2024: 80},
                yearly_improvements={2021: False, 2022: False, 2023: False, 2024: False},
                subgroup_failures=(),
                audit_passed=True,
            ),
            "C",
        )
        self.assertEqual(
            classify_v3_decision(
                invalidation_first_rate=0.40,
                one_r_first_rate=0.55,
                event_count=320,
                yearly_counts={2021: 80, 2022: 80, 2023: 80, 2024: 80},
                yearly_improvements={2021: True, 2022: True, 2023: True, 2024: True},
                subgroup_failures=(),
                audit_passed=False,
            ),
            "D",
        )

    def test_runner_reuses_source_artifacts_and_writes_only_requested_report(self):
        event = {
            **_event(),
            "bar_confirmed": True,
            "feature_cutoff_time": 4 * BAR_MS,
            "reclaim_time": 4 * BAR_MS,
        }
        feature = {
            "event_id": "event-1",
            "reclaim_relative_volume": 1.0,
            "reclaim_range_expansion": 1.0,
            "sweep_relative_volume": 1.0,
            "sweep_range_expansion": 1.0,
            "wick_ratio": 0.5,
            "close_location_value": 0.75,
            "combined_volume_ratio": 1.0,
            "max_source_time": 4 * BAR_MS,
            "feature_cutoff_time": 4 * BAR_MS,
        }
        anatomy = {
            "event_id": "event-1",
            "invalidation_first_status": "one_r_first",
            "time_to_0_5R_minutes": 15,
            "time_to_1R_minutes": 30,
            "invalidation_time_minutes": None,
            "forward_240m_R": 0.5,
        }
        candles = (
            _candle(3 * BAR_MS, high=101.0, low=99.0),
            _candle(4 * BAR_MS, high=103.0, low=99.5, close=102.0),
            _candle(5 * BAR_MS, high=107.0, low=101.0, close=106.0),
            _candle(6 * BAR_MS, high=108.0, low=105.0, close=107.0),
            _candle(7 * BAR_MS, high=109.0, low=106.0, close=108.0),
        )

        class Repository:
            def load_range(self, *args, **kwargs):
                return candles

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for name, rows in (
                ("event_rows.jsonl", (event,)),
                ("vpa_feature_rows.jsonl", (feature,)),
                ("anatomy_rows.jsonl", (anatomy,)),
            ):
                (source / name).write_text(
                    "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
                )
            (source / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "dataset_window": ["2020-12-31", "2024-11-30"],
                        "holdout_accessed": False,
                        "audit_status": "pass",
                    }
                ),
                encoding="utf-8",
            )
            report = root / "lr_entry_signal_v3_smoke_report.md"

            result = run_lr_entry_signal_v3_smoke(
                repository=Repository(), source_root=source, report_path=report
            )

            self.assertEqual(result.event_count, 1)
            self.assertEqual(result.confirmation_count, 1)
            self.assertTrue(result.audit_passed)
            self.assertEqual({path.name for path in root.iterdir()}, {"source", report.name})
            text = report.read_text(encoding="utf-8")
            self.assertIn("diagnostic-only", text)
            self.assertIn("holdout accessed: false", text)


if __name__ == "__main__":
    unittest.main()
