from __future__ import annotations

import unittest
from dataclasses import dataclass

from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import (
    CorePolicy,
    arbitrate_trade_candidates,
    evaluate_trend_continuation_core,
)


@dataclass(frozen=True)
class CandleStub:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_confirmed: bool = True


def _candle(index: int, open_: float, high: float, low: float, close: float, volume: float = 100.0) -> CandleStub:
    return CandleStub(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _weak_break_accepted_pullback() -> tuple[CandleStub, ...]:
    context = tuple(
        _candle(index, 99.4, 100.0 + (0.02 if index % 2 else 0.0), 98.9, 99.5, 100.0)
        for index in range(1, 13)
    )
    return (
        *context,
        _candle(13, 99.6, 100.35, 99.5, 100.12, 112.0),
        _candle(14, 100.10, 100.30, 99.98, 100.16, 90.0),
        _candle(15, 100.15, 100.24, 99.92, 100.08, 72.0),
        _candle(16, 100.08, 100.52, 100.02, 100.45, 108.0),
        _candle(17, 100.44, 100.70, 100.35, 100.62, 116.0),
    )


class TrendContinuationCoreTests(unittest.TestCase):
    def test_weak_break_watch_reaches_pullback_and_relaunch_observation(self) -> None:
        evaluation = evaluate_trend_continuation_core(
            _weak_break_accepted_pullback(),
            atr=1.0,
            policy=CorePolicy(
                structure_lookback_bars=12,
                breakout_seed_lookback_bars=5,
                pullback_observation_bars=4,
                relaunch_observation_bars=3,
                accepted_breakout_strength_min=0.70,
            ),
        )

        weak_events = [event for event in evaluation.events if event.breakout_class == "weak_but_watch"]

        self.assertTrue(weak_events)
        self.assertTrue(any(event.pullback_observed for event in weak_events))
        self.assertTrue(any(event.relaunch_observed for event in weak_events))
        self.assertFalse(any(event.primary_failure_reason == "no_real_breakout" for event in weak_events))
        self.assertTrue(
            all(
                event.breakout_time <= event.acceptance_end_time
                and (event.pullback_start_time is None or event.acceptance_end_time <= event.pullback_start_time)
                for event in weak_events
            )
        )

    def test_failed_breakout_is_the_only_breakout_class_eliminated_before_pullback(self) -> None:
        candles = list(_weak_break_accepted_pullback())
        candles[13] = _candle(14, 100.10, 100.20, 98.8, 99.20, 180.0)

        evaluation = evaluate_trend_continuation_core(candles, atr=1.0)
        failed = [event for event in evaluation.events if event.breakout_class == "failed_breakout"]

        self.assertTrue(failed)
        self.assertTrue(all(not event.trade_plan_ready for event in failed))
        self.assertTrue(all(event.primary_failure_reason in {"failed_breakout", "immediate_reclaim", "close_back_inside_zone"} for event in failed))

    def test_structural_stop_quality_is_classified_before_risk_engine(self) -> None:
        evaluation = evaluate_trend_continuation_core(_weak_break_accepted_pullback(), atr=1.0)
        planned = [event for event in evaluation.events if event.stop_anchor_type]

        self.assertTrue(planned)
        self.assertTrue(all(event.structural_stop_quality in {"valid", "structural_stop_too_near", "structural_stop_too_wide"} for event in planned))
        self.assertTrue(all(event.stop_is_structural for event in planned))

    def test_events_expose_shared_compression_context_diagnostics(self) -> None:
        evaluation = evaluate_trend_continuation_core(_weak_break_accepted_pullback(), atr=1.0)

        self.assertTrue(evaluation.events)
        for event in evaluation.events:
            self.assertIsInstance(event.compression_context, bool)
            self.assertGreaterEqual(event.compression_score, 0.0)
            self.assertLessEqual(event.compression_score, 1.0)
            self.assertGreaterEqual(event.compression_range_ratio, 0.0)

    def test_arbitration_keeps_all_diagnostics_but_selects_one_candidate_per_signal(self) -> None:
        evaluation = evaluate_trend_continuation_core(_weak_break_accepted_pullback(), atr=1.0)
        tradeable = [event for event in evaluation.events if event.trade_plan_ready]
        if not tradeable:
            self.skipTest("fixture did not produce tradeable lifecycle events")
        strongest = tradeable[0]
        duplicate = strongest.with_rank_score(strongest.candidate_rank_score - 0.1)

        selected = arbitrate_trade_candidates((strongest, duplicate))

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].candidate_rank_score, strongest.candidate_rank_score)

    def test_appending_future_candle_does_not_change_existing_event_identity(self) -> None:
        candles = _weak_break_accepted_pullback()
        before = evaluate_trend_continuation_core(candles, atr=1.0)
        after = evaluate_trend_continuation_core((*candles, _candle(18, 100.6, 101.0, 100.4, 100.9, 130.0)), atr=1.0)
        before_ids = {event.breakout_event_id for event in before.events}
        after_ids = {event.breakout_event_id for event in after.events}

        self.assertTrue(before_ids)
        self.assertTrue(before_ids.issubset(after_ids))


if __name__ == "__main__":
    unittest.main()
