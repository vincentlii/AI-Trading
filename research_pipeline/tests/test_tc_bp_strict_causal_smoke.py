from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.tc_bp_strict_causal import (
    FOUR_HOURS_MS,
    FIFTEEN_MINUTES_MS,
    StrictBpPolicy,
    StrictLevel,
    balanced_v2_policy,
    breakout_direction,
    clean_v2_policy,
    confirmed_swing_levels,
    find_first_pullback_candidate_v2,
    find_first_15m_bos,
    pullback_is_valid,
    repeated_boundary_levels,
    structural_trend_direction,
)
from research_pipeline.runners.tc_bp_strict_causal_smoke import (
    HOLDOUT_START,
    audit_event_rows,
    evaluate_signal_gate,
    run_tc_bp_strict_causal_smoke,
)


def candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    step_ms: int = FOUR_HOURS_MS,
    volume: float = 100.0,
    confirmed: bool = True,
) -> Candle:
    return Candle(
        timestamp_ms=index * step_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=confirmed,
    )


class StrictBpSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = StrictBpPolicy()
        self.level = StrictLevel(
            level_id="swing-high-1",
            family="confirmed_swing",
            direction="long",
            price=100.0,
            lower=99.4,
            upper=100.6,
            source_bar_time=0,
            confirmed_time=FOUR_HOURS_MS,
            reaction_count=1,
        )

    def test_wick_break_that_closes_inside_is_rejected(self) -> None:
        row = candle(5, 99.8, 102.0, 99.0, 100.2)

        self.assertIsNone(breakout_direction(row, self.level, atr=10.0, policy=self.policy))

    def test_close_confirmed_breakout_requires_buffer_body_and_close_location(self) -> None:
        row = candle(5, 99.0, 103.0, 98.5, 102.5)

        self.assertEqual(breakout_direction(row, self.level, atr=10.0, policy=self.policy), "long")

    def test_confirmed_swing_is_available_after_two_right_bars_close(self) -> None:
        rows = (
            candle(0, 96, 98, 95, 97),
            candle(1, 97, 100, 96, 99),
            candle(2, 99, 106, 98, 104),
            candle(3, 104, 105, 100, 102),
            candle(4, 102, 103, 99, 101),
        )

        levels = confirmed_swing_levels(rows, atr_values=(10.0,) * len(rows), policy=self.policy)

        high = next(level for level in levels if level.direction == "long")
        self.assertEqual(high.source_bar_time, rows[2].timestamp_ms)
        self.assertEqual(high.confirmed_time, rows[4].timestamp_ms + FOUR_HOURS_MS)

    def test_repeated_boundary_requires_two_separated_confirmed_reactions(self) -> None:
        swings = (
            StrictLevel("h1", "confirmed_swing", "long", 100.0, 99.5, 100.5, 0, 3, 1),
            StrictLevel("h2", "confirmed_swing", "long", 100.4, 99.9, 100.9, 4, 7, 1),
        )

        levels = repeated_boundary_levels(swings, atr=10.0, minimum_separation_ms=3)

        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0].reaction_count, 2)
        self.assertEqual(levels[0].confirmed_time, 7)

    def test_structural_trend_needs_two_confirmed_highs_and_lows(self) -> None:
        levels = (
            StrictLevel("h1", "confirmed_swing", "long", 100, 99, 101, 0, 1, 1),
            StrictLevel("l1", "confirmed_swing", "short", 90, 89, 91, 1, 2, 1),
            StrictLevel("h2", "confirmed_swing", "long", 110, 109, 111, 2, 3, 1),
            StrictLevel("l2", "confirmed_swing", "short", 95, 94, 96, 3, 4, 1),
        )

        self.assertEqual(structural_trend_direction(levels, cutoff_time=5), "long")
        self.assertEqual(structural_trend_direction(levels[:3], cutoff_time=5), "unknown")

    def test_pullback_rejects_close_through_far_edge(self) -> None:
        row = candle(8, 102, 103, 98.5, 99.0)

        self.assertFalse(
            pullback_is_valid(
                row,
                direction="long",
                level=self.level,
                atr=10.0,
                setup="strict_level_retest_v1",
                impulse_start=100.6,
                impulse_extreme=106.0,
                policy=self.policy,
            )
        )

    def test_shallow_pullback_stays_outside_zone_and_retraces_bounded_impulse(self) -> None:
        row = candle(8, 105, 105.5, 103.0, 104.0)

        self.assertTrue(
            pullback_is_valid(
                row,
                direction="long",
                level=self.level,
                atr=10.0,
                setup="strict_shallow_pullback_v1",
                impulse_start=100.6,
                impulse_extreme=106.0,
                policy=self.policy,
            )
        )

    def test_bos_requires_break_of_three_confirmed_bars_not_previous_close(self) -> None:
        rows = (
            candle(0, 100, 101, 99, 100, step_ms=FIFTEEN_MINUTES_MS),
            candle(1, 100, 102, 99.5, 101, step_ms=FIFTEEN_MINUTES_MS),
            candle(2, 101, 103, 100, 102, step_ms=FIFTEEN_MINUTES_MS),
            candle(3, 102, 102.8, 101, 102.5, step_ms=FIFTEEN_MINUTES_MS),
            candle(4, 102.5, 104.5, 102, 104.0, step_ms=FIFTEEN_MINUTES_MS),
            candle(5, 104.0, 105.0, 103.5, 104.5, step_ms=FIFTEEN_MINUTES_MS),
        )

        bos = find_first_15m_bos(
            rows,
            direction="long",
            observation_start=rows[3].timestamp_ms,
            invalidation=98.0,
            policy=self.policy,
        )

        self.assertEqual(bos.confirmation_bar_time, rows[4].timestamp_ms)
        self.assertEqual(bos.signal_time, rows[4].timestamp_ms + FIFTEEN_MINUTES_MS)
        self.assertEqual(bos.entry_time, rows[5].timestamp_ms + FIFTEEN_MINUTES_MS)

    def test_bos_fails_when_invalidation_is_touched_first(self) -> None:
        rows = (
            candle(0, 100, 101, 99, 100, step_ms=FIFTEEN_MINUTES_MS),
            candle(1, 100, 102, 99.5, 101, step_ms=FIFTEEN_MINUTES_MS),
            candle(2, 101, 103, 100, 102, step_ms=FIFTEEN_MINUTES_MS),
            candle(3, 102, 103, 97.5, 102.5, step_ms=FIFTEEN_MINUTES_MS),
            candle(4, 102.5, 105, 102, 104.5, step_ms=FIFTEEN_MINUTES_MS),
        )

        bos = find_first_15m_bos(
            rows,
            direction="long",
            observation_start=rows[3].timestamp_ms,
            invalidation=98.0,
            policy=self.policy,
        )

        self.assertEqual(bos.status, "failed_before_confirmation")

    def test_bos_does_not_cross_a_missing_entry_bar_gap(self) -> None:
        rows = (
            candle(0, 100, 101, 99, 100, step_ms=FIFTEEN_MINUTES_MS),
            candle(1, 100, 102, 99.5, 101, step_ms=FIFTEEN_MINUTES_MS),
            candle(2, 101, 103, 100, 102, step_ms=FIFTEEN_MINUTES_MS),
            candle(3, 102, 102.8, 101, 102.5, step_ms=FIFTEEN_MINUTES_MS),
            candle(4, 102.5, 104.5, 102, 104.0, step_ms=FIFTEEN_MINUTES_MS),
            candle(6, 104.0, 105.0, 103.5, 104.5, step_ms=FIFTEEN_MINUTES_MS),
        )

        bos = find_first_15m_bos(
            rows,
            direction="long",
            observation_start=rows[3].timestamp_ms,
            invalidation=98.0,
            policy=self.policy,
        )

        self.assertEqual(bos.status, "missing_entry_bar")
        self.assertIsNone(bos.entry_time)

    def test_v2_uses_running_extreme_and_accepts_first_shallow_pullback(self) -> None:
        rows = (
            candle(0, 99, 103, 98, 102),
            candle(1, 102, 106, 101, 105),
            candle(2, 105, 112, 105.5, 111),
            candle(3, 111, 112, 108, 109),
        )

        candidate = find_first_pullback_candidate_v2(
            rows,
            breakout_index=0,
            acceptance_index=1,
            direction="long",
            level=self.level,
            atr=10.0,
            policy=balanced_v2_policy(),
        )

        self.assertEqual(candidate.status, "accepted")
        self.assertEqual(candidate.attempt_number, 1)
        self.assertEqual(candidate.pullback_bar_time, rows[3].timestamp_ms)
        self.assertAlmostEqual(candidate.pre_pullback_extension_atr or 0.0, 1.14)
        self.assertAlmostEqual(candidate.retrace_ratio or 0.0, 4.0 / 11.4)

    def test_v2_preserves_second_attempt_with_visual_risk(self) -> None:
        rows = (
            candle(0, 99, 103, 98, 102),
            candle(1, 102, 106, 101, 105),
            candle(2, 105, 106, 105.4, 105.5),
            candle(3, 105.5, 108, 105.4, 107.5),
            candle(4, 107.5, 108, 105.0, 106.0),
        )

        candidate = find_first_pullback_candidate_v2(
            rows,
            breakout_index=0,
            acceptance_index=1,
            direction="long",
            level=self.level,
            atr=10.0,
            policy=balanced_v2_policy(),
        )

        self.assertEqual(candidate.status, "accepted_with_visual_risk")
        self.assertEqual(candidate.attempt_number, 2)
        self.assertIn("second_pullback_attempt", candidate.visual_risk_flags)

    def test_v2_rejects_close_back_inside_level(self) -> None:
        rows = (
            candle(0, 99, 103, 98, 102),
            candle(1, 102, 106, 101, 105),
            candle(2, 105, 106, 99.8, 100.0),
        )

        candidate = find_first_pullback_candidate_v2(
            rows,
            breakout_index=0,
            acceptance_index=1,
            direction="long",
            level=self.level,
            atr=10.0,
            policy=balanced_v2_policy(),
        )

        self.assertEqual(candidate.status, "rejected")
        self.assertEqual(candidate.semantic_failure_reason, "deep_reentry_inside_range")

    def test_v2_rejects_extension_beyond_hard_cap(self) -> None:
        rows = (
            candle(0, 99, 103, 98, 102),
            candle(1, 102, 106, 101, 105),
            candle(2, 105, 130, 104, 129),
            candle(3, 129, 130, 126, 127),
        )

        candidate = find_first_pullback_candidate_v2(
            rows,
            breakout_index=0,
            acceptance_index=1,
            direction="long",
            level=self.level,
            atr=10.0,
            policy=balanced_v2_policy(),
        )

        self.assertEqual(candidate.status, "rejected")
        self.assertEqual(candidate.semantic_failure_reason, "post_breakout_extension_too_far")

    def test_clean_policy_is_stricter_than_balanced(self) -> None:
        balanced = balanced_v2_policy()
        clean = clean_v2_policy()

        self.assertLess(clean.max_pre_pullback_extension_atr_hard, balanced.max_pre_pullback_extension_atr_hard)
        self.assertLess(clean.max_signal_to_level_atr_hard, balanced.max_signal_to_level_atr_hard)
        self.assertLess(clean.max_pullback_attempt_number, balanced.max_pullback_attempt_number)
        self.assertLess(clean.max_pullback_duration_4h_bars, balanced.max_pullback_duration_4h_bars)


class StrictBpResearchGateTests(unittest.TestCase):
    def test_audit_rejects_non_strict_entry_time(self) -> None:
        audit = audit_event_rows(({
            "event_id": "x",
            "breakout_time": 1,
            "acceptance_time": 2,
            "pullback_time": 3,
            "signal_time": 4,
            "entry_time": 4,
            "feature_cutoff_time": 4,
        },), holdout_accessed=False)

        self.assertEqual(audit["status"], "fail")
        self.assertIn("signal_not_before_entry:x", audit["violations"])

    def test_gate_stops_execution_when_event_count_is_too_low(self) -> None:
        decision = evaluate_signal_gate({
            "unique_event_count": 39,
            "median_4h_return_pct": 0.1,
            "median_12h_return_pct": 0.1,
            "one_r_first_rate": 0.6,
            "invalidation_first_rate": 0.3,
            "subgroup_failure_count": 0,
        }, audit_status="pass", visual_review_status="pass")

        self.assertEqual(decision, "inconclusive_manual_full_development_event_scan")

    def test_runner_never_queries_bars_at_or_after_holdout(self) -> None:
        class RecordingRepository:
            database_path = Path("fake.duckdb")

            def __init__(self) -> None:
                self.calls: list[tuple[str, int]] = []

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.calls.append((timeframe, end_ms))
                return ()

        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            result = run_tc_bp_strict_causal_smoke(repository=repository, output_root=Path(directory))

        holdout_ms = int(__import__("datetime").datetime.fromisoformat(HOLDOUT_START).replace(tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
        self.assertTrue(repository.calls)
        self.assertTrue(all(end_ms < holdout_ms for _, end_ms in repository.calls))
        self.assertEqual(result.decision, "semantic_filter_overfit_sample_collapse")


if __name__ == "__main__":
    unittest.main()
