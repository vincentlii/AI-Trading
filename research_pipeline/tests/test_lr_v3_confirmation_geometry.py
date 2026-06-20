from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from trading_system.data.okx_cli import Candle
from research_pipeline.runners.lr_v3_confirmation_geometry import (
    build_confirmation_geometry,
    classify_geometry_decision,
    run_lr_v3_confirmation_geometry,
)


BAR_MS = 15 * 60_000


def _candle(
    timestamp_ms: int,
    *,
    high: float,
    low: float,
    close: float,
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
        is_confirmed=True,
    )


def _event(*, direction: str = "long") -> dict[str, object]:
    return {
        "event_id": "event-1",
        "physical_event_key": "physical-1",
        "instrument": "BTC-USDT-SWAP",
        "direction": direction,
        "signal_time": 4 * BAR_MS,
        "signal_close": 100.0,
        "level_price": 99.0 if direction == "long" else 101.0,
        "sweep_extreme": 95.0 if direction == "long" else 105.0,
        "event_atr": 10.0,
        "level_family": "previous_day_high_low",
    }


class LRV3ConfirmationGeometryTest(unittest.TestCase):
    def test_long_geometry_and_dual_reference_targets_are_recomputed(self):
        confirmation = {
            "confirmation_status": "confirmed",
            "confirmation_time": 5 * BAR_MS,
            "time_to_confirmation_minutes": 15,
        }
        candles = (
            _candle(4 * BAR_MS, high=103.0, low=99.0, close=102.0),
            _candle(5 * BAR_MS, high=107.0, low=100.0, close=106.0),
        )

        row = build_confirmation_geometry(
            event=_event(), confirmation=confirmation, candles=candles, atr_15m=2.0
        )

        self.assertAlmostEqual(row["confirmation_to_level_ATR15m"], 1.5)
        self.assertAlmostEqual(row["confirmation_to_level_ATR1H"], 0.3)
        self.assertAlmostEqual(row["confirmation_to_invalidation_ATR15m"], 4.0)
        self.assertAlmostEqual(row["confirmation_to_invalidation_diagnostic_R"], 8.0 / 6.0)
        self.assertAlmostEqual(row["confirmation_to_1R_ATR15m"], 2.0)
        self.assertAlmostEqual(row["confirmation_to_1R_diagnostic_R"], 4.0 / 6.0)
        self.assertAlmostEqual(row["confirmation_chase_proxy"], 1.0)
        self.assertEqual(row["confirmation_delay_bars"], 1)
        self.assertEqual(row["reclaim_reference_invalidation_first_status"], "one_r_first")
        self.assertEqual(row["confirmation_reference_invalidation_first_status"], "unresolved")
        self.assertEqual(row["confirmation_reference_half_r_first_status"], "half_r_first")

    def test_short_geometry_uses_directional_signs(self):
        confirmation = {
            "confirmation_status": "confirmed",
            "confirmation_time": 5 * BAR_MS,
            "time_to_confirmation_minutes": 15,
        }
        candles = (
            _candle(4 * BAR_MS, high=101.0, low=97.0, close=98.0),
            _candle(5 * BAR_MS, high=100.0, low=93.0, close=94.0),
        )

        row = build_confirmation_geometry(
            event=_event(direction="short"),
            confirmation=confirmation,
            candles=candles,
            atr_15m=2.0,
        )

        self.assertAlmostEqual(row["confirmation_to_level_ATR15m"], 1.5)
        self.assertAlmostEqual(row["confirmation_chase_proxy"], 1.0)
        self.assertEqual(row["reclaim_reference_invalidation_first_status"], "one_r_first")

    def test_forward_240m_label_survives_earlier_invalidation(self):
        confirmation = {
            "confirmation_status": "confirmed",
            "confirmation_time": 5 * BAR_MS,
            "time_to_confirmation_minutes": 15,
        }
        candles = [_candle(4 * BAR_MS, high=103.0, low=99.0, close=102.0)]
        for index in range(5, 21):
            candles.append(
                _candle(
                    index * BAR_MS,
                    high=103.0,
                    low=93.0 if index == 5 else 99.0,
                    close=104.0 if index == 20 else 100.0,
                )
            )

        row = build_confirmation_geometry(
            event=_event(), confirmation=confirmation, candles=tuple(candles), atr_15m=2.0
        )

        self.assertEqual(row["reclaim_reference_invalidation_first_status"], "invalidation_first")
        self.assertAlmostEqual(row["reclaim_reference_forward_240m_R"], 4.0 / 6.0)

    def test_decision_requires_both_references_and_stable_groups(self):
        self.assertEqual(
            classify_geometry_decision(
                reclaim_passed=True,
                confirmation_passed=True,
                stable=True,
                median_chase_atr15m=0.4,
                median_remaining_to_original_1r=0.3,
                audit_passed=True,
            ),
            "A",
        )
        self.assertEqual(
            classify_geometry_decision(
                reclaim_passed=False,
                confirmation_passed=True,
                stable=True,
                median_chase_atr15m=0.4,
                median_remaining_to_original_1r=0.3,
                audit_passed=True,
            ),
            "B",
        )
        self.assertEqual(
            classify_geometry_decision(
                reclaim_passed=True,
                confirmation_passed=True,
                stable=True,
                median_chase_atr15m=1.0,
                median_remaining_to_original_1r=0.3,
                audit_passed=True,
            ),
            "B",
        )
        self.assertEqual(
            classify_geometry_decision(
                reclaim_passed=False,
                confirmation_passed=False,
                stable=False,
                median_chase_atr15m=0.2,
                median_remaining_to_original_1r=0.5,
                audit_passed=True,
            ),
            "C",
        )
        self.assertEqual(
            classify_geometry_decision(
                reclaim_passed=True,
                confirmation_passed=True,
                stable=True,
                median_chase_atr15m=0.2,
                median_remaining_to_original_1r=0.5,
                audit_passed=False,
            ),
            "D",
        )

    def test_runner_writes_only_the_requested_diagnostic_report(self):
        event = {
            **_event(),
            "signal_time": 20 * BAR_MS,
            "reclaim_time": 20 * BAR_MS,
            "reclaim_span_bars": 1,
            "event_timeframe": "1H_sweep_reclaim",
            "bar_confirmed": True,
            "feature_cutoff_time": 20 * BAR_MS,
        }
        candles = []
        for index in range(0, 100):
            high, low, close = 101.0, 99.0, 100.0
            if index == 20:
                high, low, close = 103.0, 99.5, 102.0
            elif index == 21:
                high, low, close = 107.0, 101.0, 106.0
            candles.append(_candle(index * BAR_MS, high=high, low=low, close=close))

        class Repository:
            def load_range(self, *args, **kwargs):
                return tuple(candles)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "event_rows.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
            (source / "anatomy_rows.jsonl").write_text(
                json.dumps(
                    {
                        "event_id": "event-1",
                        "invalidation_first_status": "one_r_first",
                        "time_to_0_5R_minutes": 15,
                        "time_to_1R_minutes": 30,
                        "forward_240m_R": 0.5,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (source / "run_manifest.json").write_text(
                json.dumps({"holdout_accessed": False, "audit_status": "pass"}),
                encoding="utf-8",
            )
            report = root / "lr_v3_confirmation_geometry_diagnostic.md"

            result = run_lr_v3_confirmation_geometry(
                repository=Repository(), source_root=source, report_path=report
            )

            self.assertEqual(result.confirmed_event_count, 1)
            self.assertTrue(result.audit_passed)
            self.assertEqual({path.name for path in root.iterdir()}, {"source", report.name})
            self.assertIn("diagnostic-only", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
