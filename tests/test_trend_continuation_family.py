from __future__ import annotations

import unittest

from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import (
    FAMILY_VARIANT_IDS,
    compact_family_event,
    family_variant_setup,
    select_family_candidates,
)


def _event(**overrides):
    row = {
        "event_key": "ctx-1:event-1",
        "lifecycle_event_id": "event-1",
        "breakout_event_id": "breakout-1",
        "level_id": "level-1",
        "asset": "ETH",
        "symbol": "ETH/USDT",
        "inst_id": "ETH-USDT-SWAP",
        "inst_type": "SWAP",
        "venue": "okx",
        "profile": "C",
        "timestamp_ms": 1_700_000_600_000,
        "direction": "short",
        "breakout_class": "accepted_breakout",
        "breakout_time": 1_700_000_000_000,
        "acceptance_end_time": 1_700_000_180_000,
        "breakout_close": 100.0,
        "breakout_price": 100.0,
        "breakout_RVOL": 1.2,
        "immediate_reclaim": False,
        "high_volume_no_result": False,
        "acceptance_status": "accepted",
        "compression_context": True,
        "compression_score": 0.65,
        "pullback_observed": True,
        "pullback_health_class": "acceptable",
        "pullback_health_score": 0.62,
        "pullback_zone_type": "level_retest",
        "pullback_end_time": 1_700_000_300_000,
        "relaunch_time": 1_700_000_360_000,
        "relaunch_close": 99.5,
        "relaunch_quality_class": "strong",
        "relaunch_score": 0.75,
        "stop": 101.0,
        "stop_distance": 1.5,
        "stop_distance_ATR": 1.5,
        "stop_buffer_ATR": 0.15,
        "structural_stop_quality": "valid",
        "stop_is_structural": True,
        "target": 97.5,
        "target_space": 2.0,
        "target_space_ATR": 2.0,
        "gross_RR": 1.33,
        "target_quality_class": "acceptable",
        "candidate_rank_score": 0.5,
        "zone": {
            "zone_lower": 99.0,
            "zone_upper": 100.0,
            "zone_mid": 99.5,
            "zone_width": 1.0,
            "zone_width_ATR": 1.0,
            "last_touch_time": 1_699_999_900_000,
        },
    }
    row.update(overrides)
    return row


class TrendContinuationFamilyTests(unittest.TestCase):
    def test_family_declares_exactly_one_bounded_variant(self) -> None:
        self.assertEqual(
            FAMILY_VARIANT_IDS,
            (
                "bp_lifecycle_level_zone_v1",
            ),
        )
        self.assertEqual(family_variant_setup(FAMILY_VARIANT_IDS[0]), "breakout_pullback")

    def test_bp_keeps_setup_isolated_and_deduplicates_lifecycle_event(self) -> None:
        selected = select_family_candidates(
            (_event(event_key="ctx-1:event-1"), _event(event_key="ctx-2:event-1", timestamp_ms=1_700_000_700_000)),
            "bp_lifecycle_level_zone_v1",
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["setup"], "breakout_pullback")
        self.assertEqual(selected[0]["variant"], "bp_lifecycle_level_zone_v1")
        self.assertEqual(selected[0]["row_type"], "proposal_candidate")

    def test_candidate_uses_confirmed_context_as_signal_and_feature_cutoff(self) -> None:
        selected = select_family_candidates((_event(),), "bp_lifecycle_level_zone_v1")

        self.assertEqual(selected[0]["signal_time"], 1_700_000_600_000)
        self.assertEqual(selected[0]["feature_cutoff_time"], 1_700_000_600_000)
        self.assertEqual(selected[0]["relaunch_time"], 1_700_000_360_000)

    def test_compact_family_event_keeps_replay_fields_without_full_diagnostic_payload(self) -> None:
        compact = compact_family_event(
            _event(
                stage_results={"large": True},
                parameter_overrides={"unused": 1},
                zone={**_event()["zone"], "unused_nested_field": "drop"},
            )
        )

        self.assertEqual(compact["lifecycle_event_id"], "event-1")
        self.assertEqual(compact["zone"]["zone_lower"], 99.0)
        self.assertNotIn("stage_results", compact)
        self.assertNotIn("parameter_overrides", compact)
        self.assertNotIn("unused_nested_field", compact["zone"])

    def test_family_arbitrates_one_candidate_per_asset_profile_direction_signal(self) -> None:
        selected = select_family_candidates(
            (
                _event(lifecycle_event_id="event-low", candidate_rank_score=0.4),
                _event(lifecycle_event_id="event-high", candidate_rank_score=0.9),
            ),
            "bp_lifecycle_level_zone_v1",
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["lifecycle_event_id"], "event-high")


if __name__ == "__main__":
    unittest.main()
