from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.reports.tc_family_trade_count_and_variant_expansion import (
    write_tc_family_trade_count_report,
)
from research_pipeline.runners.tc_family_trade_count_expansion import (
    _portfolio_heat_allows,
    _select_variant_candidates_from_store,
    _unique_structure_context_rows,
    family_audit_profile,
    select_family_decision,
)
from tests.test_trend_continuation_family import _event


class TcFamilyTradeCountExpansionTests(unittest.TestCase):
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
                yield (_event(lifecycle_event_id="low", candidate_rank_score=0.4),)
                yield (_event(lifecycle_event_id="high", candidate_rank_score=0.9),)

        selected = _select_variant_candidates_from_store(
            store=Store(),
            variant_id="bp_shallow_momentum_capped_risk_v3",
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["lifecycle_event_id"], "high")


if __name__ == "__main__":
    unittest.main()
