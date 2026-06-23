from __future__ import annotations

import unittest
from inspect import signature
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from trading_system.data.okx_cli import Candle
from trading_system.strategies.trend_price_volume_v1.tc_bp_strict_causal import (
    FIFTEEN_MINUTES_MS,
    FOUR_HOURS_MS,
    StrictLevel,
    structural_trend_direction,
)
from research_pipeline.runners.tc_bp_entry_model_quick_compare import (
    MODELS,
    EntryDiagnostic,
    LEVEL_MAX_AGE_MS,
    SOFT_RIGHT_MODEL,
    _model_metrics,
    _extended_model_metrics,
    _structural_trends_for_cutoffs,
    TrueBreakoutEvent,
    build_true_breakout_events,
    build_true_breakout_diagnostic_events,
    evaluate_left_limit,
    evaluate_right_confirmation,
    evaluate_right_confirmation_soft_vpa,
    run_tc_bp_entry_model_quick_compare,
    run_tc_bp_35m_comprehensive_diagnostic,
    run_tc_bp_entry_model_quick_compare_extended,
)


def candle(index: int, open_: float, high: float, low: float, close: float, *, step: int) -> Candle:
    return Candle(
        timestamp_ms=index * step,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


def event(direction: str = "long") -> TrueBreakoutEvent:
    return TrueBreakoutEvent(
        event_id=f"BTC:1:{direction}",
        physical_event_key=f"BTC:1:{direction}",
        instrument="BTC-USDT-SWAP",
        direction=direction,
        level_id="level-1",
        level_family="confirmed_swing",
        level_price=100.0,
        level_lower=99.5,
        level_upper=100.5,
        atr=10.0,
        breakout_time=FOUR_HOURS_MS,
        acceptance_time=2 * FOUR_HOURS_MS,
        breakout_open=99.0,
        breakout_high=106.0,
        breakout_low=98.0,
        breakout_close=104.0,
        acceptance_close=105.0,
        impulse_extreme=106.0,
        trend_state=direction,
    )


class EntryModelUnitTests(unittest.TestCase):
    def test_true_breakout_requires_a_fresh_cross_from_inside_level(self) -> None:
        rows = (
            candle(0, 101.5, 103.0, 101.0, 102.0, step=FOUR_HOURS_MS),
            candle(1, 102.0, 105.0, 101.5, 104.5, step=FOUR_HOURS_MS),
            candle(2, 104.5, 106.0, 104.0, 105.0, step=FOUR_HOURS_MS),
        )
        level = StrictLevel("h1", "confirmed_swing", "long", 100.0, 99.5, 100.5, 0, FOUR_HOURS_MS, 1, 10.0, 0)
        with (
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.causal_atr", return_value=(10.0,) * 3),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.confirmed_swing_levels", return_value=(level,)),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.repeated_boundary_levels", return_value=()),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare._structural_trends_for_cutoffs", return_value={2 * FOUR_HOURS_MS: "long", 3 * FOUR_HOURS_MS: "long"}),
        ):
            events = build_true_breakout_events("BTC-USDT-SWAP", rows, start_ms=0, end_ms=4 * FOUR_HOURS_MS)

        self.assertEqual(events, ())

    def test_first_accepted_breakout_consumes_level_before_report_window(self) -> None:
        rows = (
            candle(0, 99.0, 100.0, 98.0, 100.0, step=FOUR_HOURS_MS),
            candle(1, 100.0, 105.0, 99.5, 104.5, step=FOUR_HOURS_MS),
            candle(2, 104.5, 106.0, 104.0, 105.0, step=FOUR_HOURS_MS),
            candle(3, 105.0, 105.5, 99.0, 100.0, step=FOUR_HOURS_MS),
            candle(4, 100.0, 105.0, 99.5, 104.5, step=FOUR_HOURS_MS),
            candle(5, 104.5, 106.0, 104.0, 105.0, step=FOUR_HOURS_MS),
        )
        level = StrictLevel("h1", "confirmed_swing", "long", 100.0, 99.5, 100.5, 0, FOUR_HOURS_MS, 1, 10.0, 0)
        trends = {index * FOUR_HOURS_MS: "long" for index in range(1, 7)}
        with (
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.causal_atr", return_value=(10.0,) * 6),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.confirmed_swing_levels", return_value=(level,)),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.repeated_boundary_levels", return_value=()),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare._structural_trends_for_cutoffs", return_value=trends),
        ):
            events = build_true_breakout_events(
                "BTC-USDT-SWAP",
                rows,
                start_ms=4 * FOUR_HOURS_MS,
                end_ms=7 * FOUR_HOURS_MS,
            )

        self.assertEqual(events, ())

    def test_stale_level_is_not_reused_outside_bounded_lifecycle(self) -> None:
        rows = (
            candle(0, 99.0, 100.0, 98.0, 100.0, step=FOUR_HOURS_MS),
            candle(1, 100.0, 105.0, 99.5, 104.5, step=FOUR_HOURS_MS),
            candle(2, 104.5, 106.0, 104.0, 105.0, step=FOUR_HOURS_MS),
        )
        old_origin = FOUR_HOURS_MS - LEVEL_MAX_AGE_MS - FOUR_HOURS_MS
        level = StrictLevel("h1", "confirmed_swing", "long", 100.0, 99.5, 100.5, 0, FOUR_HOURS_MS, 1, 10.0, old_origin)
        with (
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.causal_atr", return_value=(10.0,) * 3),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.confirmed_swing_levels", return_value=(level,)),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.repeated_boundary_levels", return_value=()),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare._structural_trends_for_cutoffs", return_value={2 * FOUR_HOURS_MS: "long", 3 * FOUR_HOURS_MS: "long"}),
        ):
            events = build_true_breakout_events("BTC-USDT-SWAP", rows, start_ms=0, end_ms=4 * FOUR_HOURS_MS)

        self.assertEqual(events, ())

    def test_cached_structural_trends_match_reference_semantics(self) -> None:
        levels = (
            StrictLevel("h1", "swing", "long", 100, 99, 101, 0, 10, 1),
            StrictLevel("l1", "swing", "short", 90, 89, 91, 0, 10, 1),
            StrictLevel("h2", "swing", "long", 110, 109, 111, 1, 20, 1),
            StrictLevel("l2", "swing", "short", 95, 94, 96, 1, 20, 1),
            StrictLevel("h3", "swing", "long", 105, 104, 106, 2, 30, 1),
            StrictLevel("l3", "swing", "short", 92, 91, 93, 2, 30, 1),
        )
        cutoffs = (5, 10, 20, 30, 40)

        cached = _structural_trends_for_cutoffs(levels, cutoffs)

        self.assertEqual(
            cached,
            {
                cutoff: structural_trend_direction(levels, cutoff_time=cutoff)
                for cutoff in cutoffs
            },
        )

    def test_left_limit_fills_without_15m_bos(self) -> None:
        rows = (
            candle(32, 103, 104, 101.5, 102, step=FIFTEEN_MINUTES_MS),
            candle(33, 102, 103, 100.8, 102, step=FIFTEEN_MINUTES_MS),
        )

        result = evaluate_left_limit(event(), rows, model="level_edge_limit")

        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.model, "left_level_edge_limit")
        self.assertAlmostEqual(result.entry_price or 0.0, 101.0)

    def test_triggered_result_captures_extended_directional_diagnostics(self) -> None:
        rows = tuple(
            candle(33 + i, 101.0, 107.0, 100.5, 103.0, step=FIFTEEN_MINUTES_MS)
            for i in range(400)
        )

        result = evaluate_left_limit(event(), rows, model="level_edge_limit")

        self.assertEqual(result.status, "triggered")
        self.assertIsNotNone(result.stop_distance_atr)
        self.assertTrue(result.one_point_five_r_first)
        self.assertTrue(result.two_r_first)
        self.assertGreater(result.mfe_pct or 0.0, 0.0)
        self.assertGreater(result.mfe_r or 0.0, 2.0)
        self.assertIsNotNone(result.forward_24h_return_pct)
        self.assertIsNotNone(result.forward_72h_return_pct)

    def test_triggered_result_captures_short_horizon_returns_and_path_windows(self) -> None:
        rows = tuple(
            candle(33 + i, 101.0, 107.0, 100.5, 103.0, step=FIFTEEN_MINUTES_MS)
            for i in range(400)
        )

        result = evaluate_left_limit(
            event(),
            rows,
            model="level_edge_limit",
            path_horizon_hours=96,
        )

        self.assertIsNotNone(result.forward_2h_return_pct)
        self.assertIsNotNone(result.forward_8h_return_pct)
        self.assertIsNotNone(result.forward_16h_return_pct)
        self.assertIsNotNone(result.forward_20h_return_pct)
        self.assertEqual(
            tuple(hours for hours, _ in result.horizon_paths),
            (2, 4, 8, 12, 16, 20, 24, 36, 48, 60, 72, 96),
        )

    def test_incomplete_horizon_does_not_report_partial_mfe_mae(self) -> None:
        rows = tuple(
            candle(33 + i, 101.0, 107.0, 100.5, 103.0, step=FIFTEEN_MINUTES_MS)
            for i in range(20)
        )

        result = evaluate_left_limit(
            event(),
            rows,
            model="level_edge_limit",
            path_horizon_hours=96,
        )
        paths = dict(result.horizon_paths)

        self.assertIsNone(paths[96].mfe_pct)
        self.assertIsNone(paths[96].mae_pct)
        self.assertFalse(paths[96].window_complete)

    def test_incomplete_no_decision_is_excluded_from_path_rate_denominator(self) -> None:
        rows = (
            EntryDiagnostic(
                event_id="a",
                model="left_level_edge_limit",
                status="triggered",
                path_order="one_r_first",
                path_window_complete=False,
            ),
            EntryDiagnostic(
                event_id="b",
                model="left_level_edge_limit",
                status="triggered",
                path_order="no_decision",
                path_window_complete=False,
            ),
        )

        metrics = _model_metrics((event(), event()), rows)["left_level_edge_limit"]

        self.assertEqual(metrics["one_r_first"], 1.0)

    def test_fixed_returns_do_not_reuse_path_order_denominator(self) -> None:
        row = EntryDiagnostic(
            event_id="a",
            model="right_level_retest_confirm",
            status="triggered",
            path_order="no_decision",
            path_window_complete=False,
            forward_4h_return_pct=0.4,
            forward_12h_return_pct=1.2,
        )

        core = _model_metrics((event(),), (row,))["right_level_retest_confirm"]
        extended = _extended_model_metrics((event(),), (row,))["right_level_retest_confirm"]

        self.assertEqual(core["median_4h"], 0.4)
        self.assertEqual(core["median_12h"], 1.2)
        self.assertEqual(extended["median_4h"], 0.4)
        self.assertEqual(extended["median_12h"], 1.2)

    def test_left_limit_expires_when_never_touched(self) -> None:
        rows = tuple(candle(32 + i, 105, 106, 104, 105, step=FIFTEEN_MINUTES_MS) for i in range(32))

        result = evaluate_left_limit(event(), rows, model="level_edge_limit")

        self.assertEqual(result.status, "expired")

    def test_left_buy_limit_fills_when_bar_gaps_below_limit(self) -> None:
        rows = (candle(32, 100.0, 100.5, 99.8, 100.2, step=FIFTEEN_MINUTES_MS),)

        result = evaluate_left_limit(event(), rows, model="level_edge_limit")

        self.assertEqual(result.status, "triggered")
        self.assertAlmostEqual(result.entry_price or 0.0, 101.0)

    def test_left_limit_cancels_after_confirmed_extension_hard_cap(self) -> None:
        rows = (
            candle(32, 105, 130, 104, 129.0, step=FIFTEEN_MINUTES_MS),
            candle(33, 129, 130, 120, 125.0, step=FIFTEEN_MINUTES_MS),
        )

        result = evaluate_left_limit(event(), rows, model="breakout_mid_limit")

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.failure_reason, "pre_fill_extension_too_far")

    def test_left_fill_and_stop_same_bar_is_ambiguous(self) -> None:
        rows = (candle(32, 103, 104, 98.0, 102.0, step=FIFTEEN_MINUTES_MS),)

        result = evaluate_left_limit(event(), rows, model="level_edge_limit")

        self.assertEqual(result.status, "ambiguous_intrabar_path")
        self.assertIsNone(result.path_order)

    def test_right_requires_level_retest_then_15m_bos(self) -> None:
        rows_4h = (
            candle(0, 99, 106, 98, 104, step=FOUR_HOURS_MS),
            candle(1, 104, 107, 103, 105, step=FOUR_HOURS_MS),
            candle(2, 105, 106, 100.2, 102, step=FOUR_HOURS_MS),
        )
        rows_15m = (
            candle(48, 101, 102, 100.8, 101.5, step=FIFTEEN_MINUTES_MS),
            candle(49, 101.5, 102.2, 101.0, 102.0, step=FIFTEEN_MINUTES_MS),
            candle(50, 102.0, 102.5, 101.5, 102.2, step=FIFTEEN_MINUTES_MS),
            candle(51, 102.2, 104.0, 102.0, 103.8, step=FIFTEEN_MINUTES_MS),
            candle(52, 103.8, 104.2, 103.0, 104.0, step=FIFTEEN_MINUTES_MS),
        )

        result = evaluate_right_confirmation(event(), rows_4h, rows_15m)

        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.model, "right_level_retest_confirm")
        self.assertEqual(result.entry_time, rows_15m[4].timestamp_ms + FIFTEEN_MINUTES_MS)
        self.assertEqual(result.entry_price, rows_15m[4].close)

    def test_right_cancels_when_invalidation_occurs_before_next_bar_entry(self) -> None:
        rows_4h = (
            candle(0, 99, 106, 98, 104, step=FOUR_HOURS_MS),
            candle(1, 104, 107, 103, 105, step=FOUR_HOURS_MS),
            candle(2, 105, 106, 100.2, 102, step=FOUR_HOURS_MS),
        )
        rows_15m = (
            candle(48, 101, 102, 100.8, 101.5, step=FIFTEEN_MINUTES_MS),
            candle(49, 101.5, 102.2, 101.0, 102.0, step=FIFTEEN_MINUTES_MS),
            candle(50, 102.0, 102.5, 101.5, 102.2, step=FIFTEEN_MINUTES_MS),
            candle(51, 102.2, 104.0, 102.0, 103.8, step=FIFTEEN_MINUTES_MS),
            candle(52, 103.8, 104.2, 97.0, 104.0, step=FIFTEEN_MINUTES_MS),
        )

        result = evaluate_right_confirmation(event(), rows_4h, rows_15m)

        self.assertEqual(result.status, "not_triggered")
        self.assertEqual(result.failure_reason, "failed_before_entry")

    def test_right_cancels_when_retest_bar_already_invalidates_setup(self) -> None:
        rows_4h = (
            candle(0, 99, 106, 98, 104, step=FOUR_HOURS_MS),
            candle(1, 104, 107, 103, 105, step=FOUR_HOURS_MS),
            candle(2, 105, 106, 97.0, 102, step=FOUR_HOURS_MS),
        )

        result = evaluate_right_confirmation(event(), rows_4h, ())

        self.assertEqual(result.status, "not_triggered")
        self.assertEqual(result.failure_reason, "retest_invalidated_setup")

    def test_diagnostic_events_can_keep_no_trend_gate_and_later_level_attempts(self) -> None:
        rows = (
            candle(0, 99.0, 100.0, 98.0, 100.0, step=FOUR_HOURS_MS),
            candle(1, 100.0, 105.0, 99.5, 104.5, step=FOUR_HOURS_MS),
            candle(2, 104.5, 106.0, 104.0, 105.0, step=FOUR_HOURS_MS),
            candle(3, 105.0, 105.5, 99.0, 100.0, step=FOUR_HOURS_MS),
            candle(4, 100.0, 105.0, 99.5, 104.5, step=FOUR_HOURS_MS),
            candle(5, 104.5, 106.0, 104.0, 105.0, step=FOUR_HOURS_MS),
        )
        level = StrictLevel("h1", "confirmed_swing", "long", 100.0, 99.5, 100.5, 0, FOUR_HOURS_MS, 1, 10.0, 0)
        with (
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.causal_atr", return_value=(10.0,) * 6),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.confirmed_swing_levels", return_value=(level,)),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare.repeated_boundary_levels", return_value=()),
            patch("research_pipeline.runners.tc_bp_entry_model_quick_compare._structural_trends_for_cutoffs", return_value={2 * FOUR_HOURS_MS: "unknown", 3 * FOUR_HOURS_MS: "unknown", 5 * FOUR_HOURS_MS: "unknown", 6 * FOUR_HOURS_MS: "unknown"}),
        ):
            events = build_true_breakout_diagnostic_events(
                "BTC-USDT-SWAP",
                rows,
                start_ms=0,
                end_ms=7 * FOUR_HOURS_MS,
            )

        self.assertEqual(tuple(row.breakout_attempt_number for row in events), (1, 2))
        self.assertTrue(all(row.trend_state == "unknown" for row in events))
        self.assertTrue(all(row.trend_score_label in {"trend_unknown_or_transition", "trend_score_match"} for row in events))

    def test_soft_right_keeps_wick_breach_reclaim_and_records_vpa(self) -> None:
        rows_4h = (
            candle(0, 99, 106, 98, 104, step=FOUR_HOURS_MS),
            candle(1, 104, 107, 103, 105, step=FOUR_HOURS_MS),
            candle(2, 105, 106, 98.0, 102.5, step=FOUR_HOURS_MS),
        )
        rows_15m = (
            candle(48, 102.0, 102.4, 101.6, 102.1, step=FIFTEEN_MINUTES_MS),
            candle(49, 102.1, 102.5, 101.8, 102.2, step=FIFTEEN_MINUTES_MS),
            candle(50, 102.2, 102.6, 101.9, 102.3, step=FIFTEEN_MINUTES_MS),
            candle(51, 102.3, 104.8, 102.1, 104.6, step=FIFTEEN_MINUTES_MS),
            candle(52, 104.6, 105.0, 104.2, 104.7, step=FIFTEEN_MINUTES_MS),
        )

        hard = evaluate_right_confirmation(event(), rows_4h, rows_15m)
        soft = evaluate_right_confirmation_soft_vpa(event(), rows_4h, rows_15m)

        self.assertEqual(hard.status, "not_triggered")
        self.assertEqual(hard.failure_reason, "retest_invalidated_setup")
        self.assertEqual(soft.status, "triggered")
        self.assertEqual(soft.model, SOFT_RIGHT_MODEL)
        self.assertEqual(soft.retest_lifecycle, "wick_breach_reclaimed")
        self.assertIn(soft.confirmation_type, {"micro_bos_confirm", "level_reclaim_confirm", "vpa_relaunch_confirm"})
        self.assertIn(soft.vpa_bucket, {"weak_vpa", "normal_vpa", "strong_vpa"})

    def test_soft_right_rejects_confirmed_pre_entry_failure_after_two_inside_closes(self) -> None:
        rows_4h = (
            candle(0, 99, 106, 98, 104, step=FOUR_HOURS_MS),
            candle(1, 104, 107, 103, 105, step=FOUR_HOURS_MS),
            candle(2, 105, 106, 99.0, 99.8, step=FOUR_HOURS_MS),
            candle(3, 99.8, 100.2, 98.8, 99.7, step=FOUR_HOURS_MS),
        )

        result = evaluate_right_confirmation_soft_vpa(event(), rows_4h, ())

        self.assertEqual(result.status, "not_triggered")
        self.assertEqual(result.failure_reason, "confirmed_pre_entry_failure")

    def test_comprehensive_runner_stays_before_holdout_and_writes_one_markdown(self) -> None:
        class RecordingRepository:
            database_path = Path("fake.duckdb")

            def __init__(self) -> None:
                self.end_times: list[int] = []

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.end_times.append(end_ms)
                return ()

        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            report = output / "TC BP 35M Comprehensive Diagnostic Report.md"
            result = run_tc_bp_35m_comprehensive_diagnostic(repository=repository, report_path=report)
            text = report.read_text(encoding="utf-8")
            self.assertEqual(tuple(path.name for path in output.iterdir()), (report.name,))
            self.assertIn("TC/BP 35个月综合轻量诊断实验", text)
            self.assertIn("Trend diagnostic", text)
            self.assertIn("Right retest lifecycle", text)
            self.assertIn("VPA attribution", text)
            self.assertIn("+1.5R_first", text)
            self.assertIn("+2R_first", text)
            self.assertIn("48H path-order", text)
            self.assertIn("固定持仓时长", text)
            self.assertTrue(repository.end_times)
            self.assertTrue(all(value < result.holdout_start_ms for value in repository.end_times))


class QuickCompareRunnerTests(unittest.TestCase):
    def test_extended_compare_uses_only_requested_models_and_long_window(self) -> None:
        self.assertEqual(
            MODELS,
            ("left_level_edge_limit", "right_level_retest_confirm"),
        )
        parameters = signature(run_tc_bp_entry_model_quick_compare_extended).parameters
        self.assertEqual(parameters["start_date"].default, "2022-01-01")
        self.assertEqual(parameters["end_date"].default, "2024-11-30")

    def test_extended_runner_can_scope_to_btc_only(self) -> None:
        class RecordingRepository:
            database_path = Path("fake.duckdb")

            def __init__(self) -> None:
                self.instruments: list[str] = []

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.instruments.append(instrument)
                return ()

        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            run_tc_bp_entry_model_quick_compare_extended(
                repository=repository,
                report_path=report,
                instruments=("BTC-USDT-SWAP",),
            )
            text = report.read_text(encoding="utf-8")

        self.assertEqual(set(repository.instruments), {"BTC-USDT-SWAP"})
        self.assertIn("BTC-USDT-SWAP", text)
        self.assertNotIn("ETH-USDT-SWAP", text)

    def test_empty_runner_stays_before_holdout_and_writes_main_report(self) -> None:
        class RecordingRepository:
            database_path = Path("fake.duckdb")

            def __init__(self) -> None:
                self.end_times: list[int] = []

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.end_times.append(end_ms)
                return ()

        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            report = Path(directory) / "TC BP Entry Model Quick Compare.md"
            result = run_tc_bp_entry_model_quick_compare(repository=repository, report_path=report)
            text = report.read_text(encoding="utf-8")

        self.assertEqual(result.decision, "inconclusive_need_more_development_scan")
        self.assertIn("TC BP Entry Model Quick Compare", text)
        self.assertTrue(repository.end_times)
        self.assertTrue(all(value < result.holdout_start_ms for value in repository.end_times))

    def test_extended_runner_stays_before_holdout_and_writes_only_markdown(self) -> None:
        class RecordingRepository:
            database_path = Path("fake.duckdb")

            def __init__(self) -> None:
                self.end_times: list[int] = []

            def load_range(self, instrument, timeframe, start_ms, end_ms, **kwargs):
                self.end_times.append(end_ms)
                return ()

        repository = RecordingRepository()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            report = output / "TC BP Entry Model Quick Compare Extended.md"
            result = run_tc_bp_entry_model_quick_compare_extended(repository=repository, report_path=report)
            text = report.read_text(encoding="utf-8")
            generated = tuple(path.name for path in output.iterdir())

        self.assertEqual(generated, (report.name,))
        self.assertIn("双模型核心表", text)
        self.assertIn("风险距离", text)
        self.assertIn("固定时间方向收益", text)
        self.assertIn("MFE / MAE", text)
        self.assertIn("fresh cross", text)
        self.assertIn("acceptance-reference 4H / 12H / 24H", text)
        self.assertIn("| model | 2H | 4H | 8H | 12H | 16H | 20H |", text)
        self.assertIn("| model | horizon | median_MFE_pct | median_MAE_pct |", text)
        self.assertNotIn("left_breakout_mid_limit", text)
        self.assertNotIn("left_impulse_382_limit", text)
        self.assertIn("Paired Subset 拓展", text)
        self.assertTrue(repository.end_times)
        self.assertTrue(all(value < result.holdout_start_ms for value in repository.end_times))


if __name__ == "__main__":
    unittest.main()
