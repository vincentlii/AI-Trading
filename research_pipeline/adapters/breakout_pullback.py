from __future__ import annotations

from research_pipeline.adapters.base import (
    ArtifactContract,
    AuditProfile,
    DiagnosticStage,
    ProposalExpansionVariant,
    StrategyAdapter,
)
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import (
    CORE_ENGINE_VERSION,
    evaluate_breakout_pullback_core_diagnostics,
)


class BreakoutPullbackAdapter(StrategyAdapter):
    name = "breakout_pullback"
    display_name = "Breakout Pullback"
    adapter_version = "lifecycle_core.v2"
    strategy_family = "breakout_pullback_continuation"
    status = "diagnostic_candidate"
    proposal_only = True
    formal_conclusion_enabled = False
    supported_assets = ["BTC", "ETH"]
    supported_markets = ["SWAP"]

    def metadata(self) -> dict[str, object]:
        payload = super().metadata()
        payload.update(
            {
                "strategy_family": self.strategy_family,
                "status": self.status,
                "supported_assets": list(self.supported_assets),
                "supported_markets": list(self.supported_markets),
                "dry_run_only": False,
                "implementation_strategy": "trend_price_volume",
                "implementation_version": "v1",
                "implementation_setup": "breakout_pullback",
                "core_engine_version": CORE_ENGINE_VERSION,
            }
        )
        return payload

    def setup_filter(self) -> tuple[str, ...]:
        return ("breakout_pullback",)

    def parameter_namespace(self) -> str:
        return "breakout_pullback"

    def required_features(self) -> list[str]:
        return [
            "structure_zone",
            "breakout_event_seed",
            "breakout_lifecycle",
            "pullback_health",
            "relaunch_confirmation",
            "structural_trade_plan",
        ]

    def structure_sources(self) -> list[str]:
        return [
            "swing_high_low",
            "equal_high_low",
            "range_boundary",
            "compression_box_boundary",
            "local_pivot_cluster",
            "last_opposite_candle_zone",
            "recent_impulse_origin",
        ]

    def artifact_contract(self) -> ArtifactContract:
        return ArtifactContract(
            required_inputs=["candidate_rows", "filter_results", "execution_rows", "timeseries_rows", "run_manifest"],
            required_outputs=[
                "closed_trade_rows",
                "proposal_candidate_rows",
                "diagnostic_rows",
                "summary_rows",
                "audit_report",
                "robustness_rows",
                "regression_baseline",
            ],
        )

    def audit_profile(self) -> AuditProfile:
        return AuditProfile(
            required_lineage_fields=[
                "trade_id",
                "execution_id",
                "candidate_id",
                "event_id",
                "breakout_pullback_event_id",
                "level_id",
                "breakout_event_id",
                "lifecycle_event_id",
            ],
            required_time_fields=[
                "feature_cutoff_time",
                "zone_confirmed_time",
                "breakout_time",
                "acceptance_end_time",
                "pullback_start_time",
                "pullback_end_time",
                "relaunch_time",
                "signal_time",
                "entry_time",
                "exit_time",
            ],
            time_order_checks=[
                ("feature_cutoff_time_lte_signal_time", "feature_cutoff_time", "signal_time"),
                ("zone_confirmed_time_lte_breakout_time", "zone_confirmed_time", "breakout_time"),
                ("breakout_time_lte_acceptance_end_time", "breakout_time", "acceptance_end_time"),
                ("acceptance_end_time_lte_pullback_start_time", "acceptance_end_time", "pullback_start_time"),
                ("pullback_start_time_lte_pullback_end_time", "pullback_start_time", "pullback_end_time"),
                ("pullback_end_time_lte_relaunch_time", "pullback_end_time", "relaunch_time"),
                ("relaunch_time_lte_signal_time", "relaunch_time", "signal_time"),
                ("signal_time_lt_entry_time", "signal_time", "entry_time"),
                ("entry_time_lte_exit_time", "entry_time", "exit_time"),
            ],
        )

    def candidate_schema(self) -> dict[str, str]:
        return {
            "candidate_id": "string",
            "event_id": "string",
            "breakout_pullback_event_id": "string",
            "asset": "string",
            "direction": "string",
            "row_type": "string",
            "zone_confirmed_time": "timestamp",
            "breakout_time": "timestamp",
            "acceptance_end_time": "timestamp",
            "pullback_start_time": "timestamp",
            "pullback_end_time": "timestamp",
            "relaunch_time": "timestamp",
            "signal_time": "timestamp",
            "entry_time": "timestamp",
            "core_engine_version": "string",
            "level_id": "string",
            "breakout_event_id": "string",
            "lifecycle_event_id": "string",
            "breakout_class": "string",
            "pullback_health_class": "string",
            "relaunch_type": "string",
        }

    def diagnostic_stages(self) -> list[DiagnosticStage]:
        return [
            DiagnosticStage("window_ready", "Required candles and context exist."),
            DiagnosticStage("structure_zone_discovery", "Discover scored structure levels and zones."),
            DiagnosticStage("breakout_event_seed", "Generate broad breakout lifecycle event seeds."),
            DiagnosticStage("breakout_lifecycle", "Classify breakout lifecycle; only failed breakouts are eliminated.", hard_gate=False),
            DiagnosticStage("pullback_observation", "Observe delayed, shallow, zone, and midpoint pullbacks."),
            DiagnosticStage("pullback_health", "Score pullback health and structural hold."),
            DiagnosticStage("relaunch_confirmation", "Observe multi-pattern relaunch confirmation."),
            DiagnosticStage("structural_stop", "Build and validate structural stop geometry."),
            DiagnosticStage("target_tradeability", "Check target and cost-adjusted tradeability."),
            DiagnosticStage("risk_engine_approval", "Pass eligible candidate to the unchanged RiskEngine."),
        ]

    def proposal_expansion_variants(self) -> list[ProposalExpansionVariant]:
        return [
            ProposalExpansionVariant(
                variant_id="bp_lifecycle_level_zone_retest_v2",
                description="Proposal-only lifecycle level/zone retest.",
                parameter_overrides={
                    "breakout_pullback": {
                        "bp_variant_policy": "lifecycle_level_zone",
                    }
                },
                trigger_stage="risk_engine_approval",
            ),
            ProposalExpansionVariant(
                variant_id="bp_lifecycle_boundary_midpoint_v2",
                description="Proposal-only lifecycle boundary/midpoint retest.",
                parameter_overrides={
                    "breakout_pullback": {
                        "bp_variant_policy": "lifecycle_boundary_midpoint",
                    }
                },
                trigger_stage="risk_engine_approval",
            ),
            ProposalExpansionVariant(
                variant_id="bp_lifecycle_shallow_momentum_v2",
                description="Proposal-only lifecycle shallow pullback momentum.",
                parameter_overrides={
                    "breakout_pullback": {
                        "bp_variant_policy": "lifecycle_shallow_momentum",
                    }
                },
                trigger_stage="risk_engine_approval",
            ),
            ProposalExpansionVariant(
                variant_id="bp_lifecycle_weak_break_watch_v2",
                description="Proposal-only weak breakout watch converted by healthy pullback and strong relaunch.",
                parameter_overrides={
                    "breakout_pullback": {
                        "bp_variant_policy": "lifecycle_weak_break_watch",
                    }
                },
                trigger_stage="risk_engine_approval",
            ),
        ]

    def evaluate_diagnostics(self, *args, **kwargs):
        return evaluate_breakout_pullback_core_diagnostics(*args, **kwargs)

    def generate_candidates(self, *args, **kwargs):
        raise NotImplementedError("breakout_pullback research validation runs through Research Pipeline.")

    def filter_policy(self):
        return {
            "mode": "proposal_only_lifecycle_core_rebuild",
            "setup_filter": "breakout_pullback",
            "formal_config_changes": False,
        }

    def sizing_policy(self):
        return {"baseline": "RiskEngine current risk-based sizing", "proposal_only": True}

    def exit_policy(self):
        return {"baseline": "existing BacktestExecutionEngine advanced exits", "proposal_only": True}
