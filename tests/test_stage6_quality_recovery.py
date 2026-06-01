import unittest

from trading_system.diagnostics.stage6_quality import build_stage6_quality_report
from trading_system.diagnostics.stage6c_sizing import build_stage6c_sizing_report, default_setup_sizing_policies
from trading_system.diagnostics.stage6d_edge import build_stage6d_edge_report
from trading_system.diagnostics.stage6e_aggregator import build_stage6e_aggregation
from trading_system.diagnostics.stage7_smoke import build_stage7_smoke_plan


class Stage6QualityRecoveryTests(unittest.TestCase):
    def test_quality_runs_reuse_formal_approved_rows_and_do_not_promote_shadow(self):
        filter_rows = (
            {
                "candidate_id": "a",
                "asset": "ETH",
                "profile": "C",
                "direction": "short",
                "formal_approved": True,
                "shadow_approved_5": True,
                "reject_reason": "",
                "wick_ratio_tier": "high_wick",
                "choch_tag": "choch_false",
                "trend_alignment_tag": "neutral",
                "sweep_rvol_tier": "unknown_sweep_rvol",
                "reclaim_rvol_tier": "unknown_reclaim",
                "liquidity_score_tier": "high_score",
                "structure_level_source": "recent_swing",
                "stop_atr": 1.2,
                "notional": 12000.0,
                "margin_required": 12000.0,
                "leverage": 0.12,
                "stop_distance_abs": 10.0,
                "entry_price": 100.0,
                "portfolio_heat": 0.005,
            },
            {
                "candidate_id": "b",
                "asset": "BTC",
                "profile": "B",
                "direction": "long",
                "formal_approved": False,
                "shadow_approved_5": True,
                "reject_reason": "margin_required_too_high",
                "wick_ratio_tier": "low_wick",
                "choch_tag": "choch_false",
                "trend_alignment_tag": "neutral",
                "sweep_rvol_tier": "unknown_sweep_rvol",
                "reclaim_rvol_tier": "unknown_reclaim",
                "liquidity_score_tier": "high_score",
                "structure_level_source": "recent_swing",
                "stop_atr": 1.0,
                "notional": 50000.0,
                "margin_required": 50000.0,
                "leverage": 0.5,
                "stop_distance_abs": 2.0,
                "entry_price": 100.0,
                "portfolio_heat": 0.005,
            },
        )
        execution_rows = (
            {
                "candidate_id": "a",
                "mae_R": 0.2,
                "mfe_R": 0.6,
                "net_R": 0.1,
                "exit_reason": "time_cut_exit",
                "holding_bars": 8,
                "same_bar_ambiguous": False,
                "liquidation_event": False,
                "funding_paid_or_received": 0.0,
            },
        )

        result = build_stage6_quality_report(filter_rows=filter_rows, execution_rows=execution_rows, equity=100000.0, max_single_notional_pct=0.15)

        baseline = next(row for row in result.run_rows if row["run"] == "Run 0 Baseline")
        wick = next(row for row in result.run_rows if row["run"] == "Run 3 Wick filter")
        choch = next(row for row in result.run_rows if row["run"] == "Run 1 CHoCH filter")
        self.assertEqual(baseline["formal_approved"], 1)
        self.assertEqual(wick["formal_approved"], 1)
        self.assertEqual(choch["formal_approved"], 0)
        self.assertEqual(result.margin_summary["shadow_max_single_notional_2x_pass"], 1)
        self.assertIn("Stage 6 Quality Filter Recovery Report", result.report)


if __name__ == "__main__":
    unittest.main()


class Stage6CSizingProposalTests(unittest.TestCase):
    def test_setup_specific_policies_keep_liquidity_reversal_separate(self):
        policies = default_setup_sizing_policies()

        self.assertEqual(policies["liquidity_reversal"]["sizing_model"], "notional_capped_risk_based")
        self.assertTrue(policies["liquidity_reversal"]["allow_notional_cap"])
        self.assertIn("trend_continuation", policies)
        self.assertNotEqual(policies["liquidity_reversal"]["exit_model"], policies["trend_continuation"]["exit_model"])

    def test_capped_sizing_is_shadow_and_records_actual_risk(self):
        filter_rows = (
            {
                "candidate_id": "tight-margin",
                "asset": "ETH",
                "profile": "C",
                "direction": "short",
                "setup": "liquidity_reversal",
                "formal_approved": False,
                "reject_reason": "margin_required_too_high",
                "reject_stage": "risk_filter",
                "risk_pct": 0.005,
                "risk_amount": 500.0,
                "entry_price": 100.0,
                "stop_price": 99.0,
                "stop_distance_abs": 1.0,
                "stop_distance_pct": 0.01,
                "stop_atr": 1.0,
                "target_r": 2.0,
                "cost_after_r": 1.8,
                "raw_position_qty_by_risk": 500.0,
                "raw_position_notional_by_risk": 50000.0,
                "max_single_notional": 15000.0,
                "max_single_notional_pct": 0.15,
                "margin_required": 50000.0,
                "margin_required_pct": 0.5,
                "notional_to_equity_pct": 0.5,
                "leverage": 0.5,
                "liquidation_distance_pct": 0.5,
                "portfolio_heat": 0.005,
                "sweep_rvol_tier": "high_sweep_rvol",
                "choch_tag": "choch_true",
                "wick_ratio_tier": "high_wick",
                "structure_level_source": "recent_swing",
            },
            {
                "candidate_id": "too-near",
                "asset": "BTC",
                "profile": "B",
                "direction": "long",
                "setup": "liquidity_reversal",
                "formal_approved": False,
                "reject_reason": "stop_distance_too_near",
                "risk_pct": 0.005,
                "risk_amount": 500.0,
                "entry_price": 100.0,
                "stop_price": 99.5,
                "stop_distance_abs": 0.5,
                "stop_distance_pct": 0.005,
                "stop_atr": 0.5,
                "target_r": 2.0,
                "cost_after_r": 1.7,
                "raw_position_notional_by_risk": 100000.0,
                "max_single_notional": 15000.0,
                "max_single_notional_pct": 0.15,
            },
        )

        result = build_stage6c_sizing_report(filter_rows=filter_rows, execution_rows=(), equity=100000.0, max_single_notional_pct=0.15)

        capped = next(row for row in result.sizing_summary_rows if row["sizing_model"] == "notional_capped_risk_based")
        current = next(row for row in result.sizing_summary_rows if row["sizing_model"] == "current_risk_based_sizing")
        capped_row = next(row for row in result.sizing_rows if row["candidate_id"] == "tight-margin" and row["sizing_model"] == "notional_capped_risk_based")
        near_row = next(row for row in result.sizing_rows if row["candidate_id"] == "too-near" and row["sizing_model"] == "notional_capped_risk_based")

        self.assertEqual(current["formal_approved"], 0)
        self.assertEqual(capped["proposal_approved"], 1)
        self.assertFalse(capped_row["formal_approved"])
        self.assertTrue(capped_row["proposal_approved"])
        self.assertTrue(capped_row["capped_by_notional"])
        self.assertAlmostEqual(capped_row["actual_risk_pct_after_cap"], 0.0015)
        self.assertEqual(capped_row["stop_near_quality_flag"], "required_notional_far_above_cap")
        self.assertFalse(near_row["proposal_approved"])
        self.assertEqual(near_row["stop_near_quality_flag"], "required_notional_far_above_cap")
        self.assertIn("Stage 6C Setup-Specific Sizing Proposal Report", result.report)


class Stage6DEdgeValidationTests(unittest.TestCase):
    def test_risk_tiers_do_not_mechanically_reject_low_risk_profitable_rows(self):
        sizing_rows = (
            {
                "candidate_id": "low-risk-edge",
                "sizing_model": "notional_capped_risk_based",
                "proposal_approved": True,
                "formal_approved": False,
                "actual_risk_pct_after_cap": 0.0015,
                "risk_utilization_ratio": 0.30,
                "required_notional_to_cap_ratio": 2.5,
                "sweep_rvol_tier": "high_sweep_rvol",
                "choch_tag": "choch_true",
                "wick_ratio_tier": "high_wick",
                "asset": "ETH",
                "profile": "C",
                "direction": "short",
                "structure_level_source": "recent_swing",
                "reclaim_within_3": True,
                "displacement_after_reclaim": True,
                "pdh_pdl_tag": False,
                "eqh_eql_tag": False,
                "london_open_window": True,
            },
            {
                "candidate_id": "high-risk-no-push",
                "sizing_model": "notional_capped_risk_based",
                "proposal_approved": True,
                "formal_approved": True,
                "actual_risk_pct_after_cap": 0.004,
                "risk_utilization_ratio": 0.80,
                "required_notional_to_cap_ratio": 1.2,
                "sweep_rvol_tier": "low_sweep_rvol",
                "choch_tag": "choch_false",
                "wick_ratio_tier": "low_wick",
                "asset": "BTC",
                "profile": "B",
                "direction": "long",
                "structure_level_source": "recent_swing",
            },
        )
        execution_rows = (
            {"candidate_id": "low-risk-edge", "mfe_R": 1.2, "mae_R": 0.2, "net_R": 0.4, "exit_reason": "target_exit"},
            {"candidate_id": "high-risk-no-push", "mfe_R": 0.1, "mae_R": 0.3, "net_R": -0.2, "exit_reason": "time_cut_exit"},
        )

        result = build_stage6d_edge_report(sizing_rows=sizing_rows, execution_rows=execution_rows)

        low_risk = next(row for row in result.tier_rows if row["tier_type"] == "actual_risk_pct" and row["tier"] == "low_risk")
        strong = next(row for row in result.mfe_push_rows if row["mfe_push_class"] == "strong_push")
        gate_c = next(row for row in result.gate_rows if row["gate"] == "Gate C quality-first")
        self.assertEqual(low_risk["proposal_approved"], 1)
        self.assertEqual(low_risk["MFE_R_ge_1_0_ratio"], 1.0)
        self.assertEqual(low_risk["displacement_after_reclaim_ratio"], 1.0)
        self.assertEqual(low_risk["reclaim_within_3_ratio"], 1.0)
        self.assertEqual(strong["high_sweep_rvol_count"], 1)
        self.assertEqual(gate_c["approved_after_gate"], 1)
        self.assertIn("Stage 6D Capped Sizing Edge & MFE Quality Report", result.report)


class Stage6EAggregatorTests(unittest.TestCase):
    def test_aggregates_windows_and_requires_sample_and_mfe_for_stage7_smoke(self):
        window_results = {
            "3000w": {
                "combo_rows": (
                    {
                        "combo": "displacement_after_reclaim + high_wick",
                        "sizing_model": "notional_capped_risk_based",
                        "closed_trades": 43,
                        "MFE_R_avg": 0.95,
                        "MFE_R_p50": 0.8,
                        "MFE_R_p75": 1.2,
                        "MFE_R_p90": 1.8,
                        "MFE_R_ge_0_5_ratio": 0.67,
                        "MFE_R_ge_1_0_ratio": 0.32,
                        "net_R_avg": 0.32,
                        "net_return_on_notional_avg": 0.013,
                        "time_cut_exit_rate": 0.32,
                    }
                ),
                "gate_rows": (
                    {
                        "gate": "Gate A risk-aware",
                        "closed_trades": 224,
                        "MFE_R_avg": 0.65,
                        "MFE_R_ge_0_5_ratio": 0.40,
                        "MFE_R_ge_1_0_ratio": 0.21,
                        "net_R_avg": 0.14,
                        "net_return_on_notional_avg": 0.006,
                        "time_cut_exit_rate": 0.59,
                    },
                ),
            },
            "5000w": {
                "combo_rows": (
                    {
                        "combo": "displacement_after_reclaim + high_wick",
                        "sizing_model": "notional_capped_risk_based",
                        "closed_trades": 45,
                        "MFE_R_avg": 0.92,
                        "MFE_R_p50": 0.7,
                        "MFE_R_p75": 1.1,
                        "MFE_R_p90": 1.7,
                        "MFE_R_ge_0_5_ratio": 0.70,
                        "MFE_R_ge_1_0_ratio": 0.35,
                        "net_R_avg": 0.35,
                        "net_return_on_notional_avg": 0.014,
                        "time_cut_exit_rate": 0.30,
                    }
                ),
                "gate_rows": (
                    {
                        "gate": "Gate A risk-aware",
                        "closed_trades": 250,
                        "MFE_R_avg": 0.66,
                        "MFE_R_ge_0_5_ratio": 0.41,
                        "MFE_R_ge_1_0_ratio": 0.22,
                        "net_R_avg": 0.15,
                        "net_return_on_notional_avg": 0.007,
                        "time_cut_exit_rate": 0.58,
                    },
                ),
            },
            "10000w": {
                "combo_rows": (
                    {
                        "combo": "displacement_after_reclaim + high_wick",
                        "sizing_model": "notional_capped_risk_based",
                        "closed_trades": 60,
                        "MFE_R_avg": 0.91,
                        "MFE_R_p50": 0.69,
                        "MFE_R_p75": 1.05,
                        "MFE_R_p90": 1.65,
                        "MFE_R_ge_0_5_ratio": 0.68,
                        "MFE_R_ge_1_0_ratio": 0.33,
                        "net_R_avg": 0.31,
                        "net_return_on_notional_avg": 0.012,
                        "time_cut_exit_rate": 0.35,
                    }
                ),
                "gate_rows": (
                    {
                        "gate": "Gate A risk-aware",
                        "closed_trades": 300,
                        "MFE_R_avg": 0.64,
                        "MFE_R_p50": 0.4,
                        "MFE_R_p75": 0.8,
                        "MFE_R_p90": 1.3,
                        "MFE_R_ge_0_5_ratio": 0.40,
                        "MFE_R_ge_1_0_ratio": 0.22,
                        "net_R_avg": 0.14,
                        "net_return_on_notional_avg": 0.006,
                        "time_cut_exit_rate": 0.58,
                    },
                ),
            },
        }

        result = build_stage6e_aggregation(window_results=window_results)

        combo = next(row for row in result.comparison_rows if row["label"] == "displacement_after_reclaim + high_wick" and row["window"] == "5000w")
        self.assertEqual(combo["sample_size_warning"], "")
        self.assertEqual(combo["MFE_R_p90"], 1.7)
        self.assertTrue(combo["stage7_smoke_ready"])
        self.assertEqual(result.decision, "stage7_smoke_candidate_ready")
        self.assertIn("Stage 6E Aggregator Final Report", result.report)


class Stage7SmokeFrameworkTests(unittest.TestCase):
    def test_smoke_plan_is_framework_only_and_keeps_capped_sizing_proposal(self):
        filter_rows = (
            {
                "candidate_id": "candidate-a",
                "asset": "ETH",
                "profile": "C",
                "direction": "short",
                "formal_approved": True,
                "sweep_rvol_tier": "high_sweep_rvol",
                "choch_tag": "choch_true",
                "wick_ratio_tier": "high_wick",
            },
            {
                "candidate_id": "candidate-b",
                "asset": "BTC",
                "profile": "B",
                "direction": "long",
                "formal_approved": True,
                "sweep_rvol_tier": "low_sweep_rvol",
                "choch_tag": "choch_true",
                "wick_ratio_tier": "high_wick",
            },
        )

        result = build_stage7_smoke_plan(
            filter_rows=filter_rows,
            execution_rows=(),
            combo="high_sweep_rvol + CHOCH true + high_wick",
            cost_tiers=("base", "stress", "harsh"),
        )

        self.assertEqual(result.selected_candidates, 1)
        self.assertFalse(result.formal_conclusion_enabled)
        self.assertIn("proposal_only", result.report)
        self.assertIn("same_bar_ambiguous_count", result.required_fields)
