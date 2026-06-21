from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_pipeline.core.reports.tc_family_trade_count_and_variant_expansion import (
    write_tc_family_trade_count_report,
)
from research_pipeline.cli.research import _candidate_cutoff_ms, _utc_date_bounds, _with_scan_profiles
from research_pipeline.runners.strategy_expansion_diagnostics import _event_rows_for_mode
from research_pipeline.runners.tc_family_trade_count_expansion import (
    _event_is_causal_at_context,
    _filter_context_rows_by_candidate_end,
    _portfolio_heat_allows,
    _select_variant_candidates_from_store,
    _simulate_capped_candidate,
    _unique_structure_context_rows,
    family_audit_profile,
    select_family_decision,
)
from trading_system.backtest.layered_pipeline import _has_candle_at_or_before
from trading_system.config import load_backtest_preset
from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import family_event_eligible
from tests.test_trend_continuation_family import _event


class TcFamilyTradeCountExpansionTests(unittest.TestCase):
    def test_scan_profile_override_is_in_memory_only(self) -> None:
        preset = load_backtest_preset("configs/presets/btc_eth_swap_tc_formal.toml")

        overridden = _with_scan_profiles(preset, ("B",))

        self.assertEqual(preset.scan.profile_keys, ("C",))
        self.assertEqual(overridden.scan.profile_keys, ("B",))

    def test_simulation_passes_explicit_execution_boundary_to_input_builder(self) -> None:
        preset = load_backtest_preset("configs/presets/btc_eth_swap_tc_formal.toml")

        with patch(
            "research_pipeline.runners.tc_family_trade_count_expansion._input_from_filter_row",
            return_value=None,
        ) as builder:
            closed, reason = _simulate_capped_candidate(
                repository=object(),
                candidate={"candidate_id": "candidate-1"},
                tier_preset=preset,
                tier_name="base",
                execution_timeframe="15m",
            )

        self.assertIsNone(closed)
        self.assertEqual(reason, "missing_execution_candles")
        builder.assert_called_once_with(
            unittest.mock.ANY,
            {"candidate_id": "candidate-1"},
            preset,
            execution_timeframe="15m",
        )

    def test_event_replay_only_accepts_the_structure_bar_confirmation_context(self) -> None:
        event = {
            "relaunch_time": 1_000,
            "timestamp_ms": 1_000 + 3 * 60 * 60_000,
            "structure_timeframe": "4h",
        }

        self.assertTrue(_event_is_causal_at_context(event))
        self.assertFalse(
            _event_is_causal_at_context(
                {**event, "timestamp_ms": 1_000 + 7 * 60 * 60_000}
            )
        )

    def test_candidate_replay_predicate_keeps_all_variant_eligible_events(self) -> None:
        diagnostics = {
            "event_rows": (
                {
                    "event": "eligible",
                    "breakout_class": "strong_breakout",
                    "pullback_zone_type": "level_retest",
                    "pullback_health_class": "healthy",
                    "relaunch_quality_class": "strong",
                    "structural_stop_quality": "valid",
                    "target_quality_class": "good",
                },
                {"event": "ineligible", "breakout_class": "failed_breakout"},
            ),
        }

        self.assertEqual(
            _event_rows_for_mode(
                diagnostics,
                event_predicate=lambda row: family_event_eligible(row, "bp_lifecycle_level_zone_v1"),
            ),
            (diagnostics["event_rows"][0],),
        )

    def test_fast_context_history_check_uses_timestamp_presence(self) -> None:
        self.assertFalse(_has_candle_at_or_before((), 100))
        self.assertFalse(_has_candle_at_or_before((101, 102), 100))
        self.assertTrue(_has_candle_at_or_before((99, 101), 100))

    def test_utc_date_bounds_reserve_entry_and_holding_bars(self) -> None:
        start_ms, end_ms, end_exclusive_ms = _utc_date_bounds("2020-12-31", "2024-11-30")

        self.assertEqual(start_ms, 1_609_372_800_000)
        self.assertEqual(end_ms, 1_733_011_199_999)
        self.assertEqual(end_exclusive_ms, 1_733_011_200_000)
        self.assertEqual(
            _candidate_cutoff_ms(
                end_exclusive_ms=end_exclusive_ms,
                entry_timeframes=("1h",),
                max_holding_bars=20,
            ),
            1_732_935_600_000,
        )

    def test_candidate_cutoff_removes_context_without_complete_trade_path(self) -> None:
        rows = (
            {"timestamp_ms": 100, "candidate": "kept"},
            {"timestamp_ms": 101, "candidate": "cut"},
        )

        self.assertEqual(
            _filter_context_rows_by_candidate_end(rows, candidate_end_ms=100),
            ({"timestamp_ms": 100, "candidate": "kept"},),
        )

    def test_native_ce_audit_profile_does_not_require_pullback_or_relaunch(self) -> None:
        profile = family_audit_profile("ce_lifecycle_native_light_confirm_v1")

        self.assertIn("acceptance_end_time", profile.required_time_fields)
        self.assertNotIn("pullback_end_time", profile.required_time_fields)
        self.assertNotIn("relaunch_time", profile.required_time_fields)

    def test_decision_prefers_bp_shallow_when_it_is_robust_and_ce_is_weaker(self) -> None:
        decision = select_family_decision(
            {
                "ce_lifecycle_native_light_confirm_v1": {
                    "closed_trades": 35,
                    "base_net_R_avg": -0.1,
                    "stress_net_R_avg": -0.12,
                    "harsh_net_R_avg": -0.15,
                },
                "ce_lifecycle_shallow_momentum_v1": {"closed_trades": 4},
                "bp_shallow_momentum_capped_risk_v3": {
                    "closed_trades": 32,
                    "base_net_R_avg": 0.2,
                    "stress_net_R_avg": 0.15,
                    "harsh_net_R_avg": 0.08,
                    "net_R_avg_excluding_top_1": 0.1,
                    "net_R_avg_excluding_top_2": 0.07,
                    "margin_required_too_high_after_cap": 0,
                },
            }
        )

        self.assertTrue(decision.startswith("C."))

    def test_report_is_concentrated_and_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_tc_family_trade_count_report(
                output_dir=Path(temp_dir),
                payload={
                    "run_id": "fixture-run",
                    "decision": "E. Results remain too narrow or weak; pause TC family expansion.",
                    "cache_status": {"complete": True, "event_rows": 10},
                    "variant_summaries": {
                        "ce_lifecycle_native_light_confirm_v1": {"raw_candidates": 3, "closed_trades": 1},
                        "ce_lifecycle_shallow_momentum_v1": {"raw_candidates": 1, "closed_trades": 0},
                        "bp_shallow_momentum_capped_risk_v3": {"raw_candidates": 1, "closed_trades": 1},
                    },
                    "constraints": ["proposal-only"],
                    "artifact_paths": [],
                    "known_limitations": ["fixture"],
                },
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn("# TC Family Trade Count and Variant Expansion Report", text)
        self.assertIn("## 4. Capped Risk Sizing Methodology", text)
        self.assertIn("## 13. Decision", text)
        self.assertIn("bp_shallow_momentum_capped_risk_v3", text)

    def test_decision_does_not_treat_missing_cost_tiers_as_near_positive(self) -> None:
        decision = select_family_decision(
            {
                "ce_lifecycle_native_light_confirm_v1": {"closed_trades": 30, "base_net_R_avg": -0.1},
                "ce_lifecycle_shallow_momentum_v1": {"closed_trades": 20, "base_net_R_avg": 0.01},
                "bp_shallow_momentum_capped_risk_v3": {"closed_trades": 20, "base_net_R_avg": 0.02},
            }
        )

        self.assertFalse(decision.startswith("A."))

    def test_portfolio_heat_check_rejects_overlapping_candidate_above_existing_limit(self) -> None:
        existing = [(100, 200, 0.015)]

        self.assertFalse(
            _portfolio_heat_allows(
                existing,
                entry_time=150,
                exit_time=250,
                risk_pct=0.006,
                max_heat_pct=0.02,
            )
        )
        self.assertTrue(
            _portfolio_heat_allows(
                existing,
                entry_time=201,
                exit_time=250,
                risk_pct=0.006,
                max_heat_pct=0.02,
            )
        )

    def test_unique_structure_context_rows_avoids_recomputing_same_structure_bar(self) -> None:
        rows = (
            {"inst_id": "BTC", "profile": "B", "structure_timeframe": "1h", "timestamp_ms": 3_600_000},
            {"inst_id": "BTC", "profile": "B", "structure_timeframe": "1h", "timestamp_ms": 4_500_000},
            {"inst_id": "BTC", "profile": "B", "structure_timeframe": "1h", "timestamp_ms": 7_200_000},
        )

        unique = _unique_structure_context_rows(rows)

        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]["timestamp_ms"], 4_500_000)

    def test_variant_candidate_selection_arbitrates_signals_across_cache_batches(self) -> None:
        class Store:
            def iter_event_batches(self):
                yield (_event(lifecycle_event_id="low", candidate_rank_score=0.4, pullback_zone_type="shallow_pullback"),)
                yield (_event(lifecycle_event_id="high", candidate_rank_score=0.9, pullback_zone_type="shallow_pullback"),)

        selected = _select_variant_candidates_from_store(
            store=Store(),
            variant_id="bp_shallow_momentum_capped_risk_v3",
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["lifecycle_event_id"], "high")


if __name__ == "__main__":
    unittest.main()
