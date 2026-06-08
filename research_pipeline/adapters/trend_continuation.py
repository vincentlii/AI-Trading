from __future__ import annotations

from research_pipeline.adapters.base import (
    ArtifactContract,
    AuditProfile,
    DiagnosticStage,
    ProposalExpansionVariant,
    StrategyAdapter,
)
from trading_system.strategies.trend_price_volume_v1.features import evaluate_trend_continuation_diagnostics


class TrendContinuationAdapter(StrategyAdapter):
    name = "trend_continuation"
    display_name = "Trend Continuation"
    adapter_version = "research_validation.v1"
    strategy_family = "price_action_volume"
    status = "research_validation"
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
                "implementation_setup": "trend_continuation",
            }
        )
        return payload

    def required_features(self) -> list[str]:
        return [
            "trend_regime",
            "breakout_structure",
            "pullback_retest",
            "volume_confirmation",
        ]

    def structure_sources(self) -> list[str]:
        return ["breakout_level", "pullback_zone", "higher_timeframe_trend"]

    def setup_filter(self) -> tuple[str, ...]:
        return ("trend_continuation",)

    def parameter_namespace(self) -> str:
        return "trend_continuation"

    def artifact_contract(self) -> ArtifactContract:
        return ArtifactContract(
            required_inputs=[
                "candidate_rows",
                "filter_results",
                "execution_rows",
                "timeseries_rows",
                "run_manifest",
            ],
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
                "trend_event_id",
            ],
            required_time_fields=[
                "feature_cutoff_time",
                "trend_confirmed_time",
                "breakout_time",
                "pullback_confirmed_time",
                "signal_time",
                "entry_time",
                "exit_time",
            ],
            time_order_checks=[
                ("feature_cutoff_time_lte_signal_time", "feature_cutoff_time", "signal_time"),
                ("trend_confirmed_time_lte_signal_time", "trend_confirmed_time", "signal_time"),
                ("breakout_time_lte_pullback_confirmed_time", "breakout_time", "pullback_confirmed_time"),
                ("pullback_confirmed_time_lte_signal_time", "pullback_confirmed_time", "signal_time"),
                ("signal_time_lt_entry_time", "signal_time", "entry_time"),
                ("entry_time_lte_exit_time", "entry_time", "exit_time"),
            ],
        )

    def candidate_schema(self) -> dict[str, str]:
        return {
            "candidate_id": "string",
            "event_id": "string",
            "trend_event_id": "string",
            "asset": "string",
            "direction": "string",
            "row_type": "string",
            "trend_confirmed_time": "timestamp",
            "breakout_time": "timestamp",
            "pullback_confirmed_time": "timestamp",
            "signal_time": "timestamp",
            "entry_time": "timestamp",
        }

    def diagnostic_stages(self) -> list[DiagnosticStage]:
        return [
            DiagnosticStage("window_ready", "Required entry, structure, and trend windows are available."),
            DiagnosticStage("trend_gate", "Higher timeframe trend regime is TREND with long/short direction."),
            DiagnosticStage("volume_baseline_available", "Breakout volume baseline is positive and usable."),
            DiagnosticStage("breakout_rvol", "Breakout relative volume meets the strict TC threshold."),
            DiagnosticStage("pullback_rvol", "Pullback relative volume stays below the strict TC threshold."),
            DiagnosticStage("displacement_range", "Breakout candle range is positive."),
            DiagnosticStage("displacement_body", "Breakout body ratio meets displacement threshold."),
            DiagnosticStage("BOS", "Breakout close clears prior structure by ATR buffer."),
            DiagnosticStage("close_location", "Breakout close location is near the impulse extreme."),
            DiagnosticStage("pullback_direction", "Pullback moves against the breakout impulse."),
            DiagnosticStage("pullback_midpoint", "Pullback holds breakout midpoint and prior structure."),
            DiagnosticStage("restart_price", "Entry window restarts in trend direction."),
            DiagnosticStage("restart_rvol", "Restart candle relative volume meets threshold."),
            DiagnosticStage("entry_volume_confirmation", "Entry timeframe volume confirmation is confirm."),
        ]

    def proposal_expansion_variants(self) -> list[ProposalExpansionVariant]:
        return [
            ProposalExpansionVariant(
                variant_id="bos_buffer_atr_0_35",
                description="Diagnostic-only BOS buffer relaxation.",
                parameter_overrides={"trend_continuation": {"breakout_buffer_atr": 0.35}},
                trigger_stage="BOS",
            ),
            ProposalExpansionVariant(
                variant_id="bos_buffer_atr_0_25",
                description="Diagnostic-only stronger BOS buffer relaxation.",
                parameter_overrides={"trend_continuation": {"breakout_buffer_atr": 0.25}},
                trigger_stage="BOS",
            ),
            ProposalExpansionVariant(
                variant_id="breakout_body_ratio_min_0_60",
                description="Diagnostic-only displacement body relaxation.",
                parameter_overrides={"trend_continuation": {"breakout_body_ratio_min": 0.60}},
                trigger_stage="displacement_body",
            ),
            ProposalExpansionVariant(
                variant_id="breakout_close_location_max_0_30",
                description="Diagnostic-only close location relaxation.",
                parameter_overrides={"trend_continuation": {"breakout_close_location_max": 0.30}},
                trigger_stage="close_location",
            ),
            ProposalExpansionVariant(
                variant_id="breakout_rvol_min_1_80",
                description="Diagnostic-only breakout RVOL relaxation.",
                parameter_overrides={"trend_continuation": {"breakout_rvol_min": 1.8}},
                trigger_stage="breakout_rvol",
            ),
            ProposalExpansionVariant(
                variant_id="breakout_rvol_min_1_60",
                description="Diagnostic-only stronger breakout RVOL relaxation.",
                parameter_overrides={"trend_continuation": {"breakout_rvol_min": 1.6}},
                trigger_stage="breakout_rvol",
            ),
            ProposalExpansionVariant(
                variant_id="pullback_rvol_max_0_90",
                description="Diagnostic-only pullback RVOL relaxation.",
                parameter_overrides={"trend_continuation": {"pullback_rvol_max": 0.9}},
                trigger_stage="pullback_rvol",
            ),
            ProposalExpansionVariant(
                variant_id="restart_rvol_min_1_30",
                description="Diagnostic-only restart RVOL relaxation.",
                parameter_overrides={"trend_continuation": {"restart_rvol_min": 1.3}},
                trigger_stage="restart_rvol",
            ),
            ProposalExpansionVariant(
                variant_id="fresh_trend_b_v1",
                description="Proposal-only B profile fresh trend gate diagnostic.",
                parameter_overrides={"trend_continuation": {"trend_gate_policy": "fresh_trend_b_v1"}},
                trigger_stage="trend_gate",
            ),
            ProposalExpansionVariant(
                variant_id="transition_trend_b_v1",
                description="Proposal-only B profile transition trend gate diagnostic.",
                parameter_overrides={"trend_continuation": {"trend_gate_policy": "transition_trend_b_v1"}},
                trigger_stage="trend_gate",
            ),
            ProposalExpansionVariant(
                variant_id="compression_expansion_watchlist_v1",
                description="Diagnostic-only compression expansion watchlist.",
                parameter_overrides={"trend_continuation": {"trend_gate_policy": "compression_expansion_watchlist_v1"}},
                trigger_stage="trend_gate",
                execution_eligible=False,
            ),
            ProposalExpansionVariant(
                variant_id="profile_c_structure_proxy_v1",
                description="Diagnostic-only C profile structure-trend proxy.",
                parameter_overrides={"trend_continuation": {"trend_gate_policy": "profile_c_structure_proxy_v1"}},
                trigger_stage="trend_gate",
                execution_eligible=False,
            ),
            ProposalExpansionVariant(
                variant_id="near_threshold_mature_trend_v1",
                description="Proposal-only strict mature trend near-threshold diagnostic.",
                parameter_overrides={"trend_continuation": {"trend_gate_policy": "near_threshold_mature_trend_v1"}},
                trigger_stage="trend_gate",
            ),
        ]

    def evaluate_diagnostics(self, *args, **kwargs):
        return evaluate_trend_continuation_diagnostics(*args, **kwargs)

    def generate_candidates(self, *args, **kwargs):
        raise NotImplementedError("trend_continuation research validation runs through strategy-research-validation.")

    def filter_policy(self):
        return {
            "mode": "proposal_only_research_validation",
            "setup_filter": "trend_continuation",
            "formal_config_changes": False,
        }

    def sizing_policy(self):
        return {
            "baseline": "RiskEngine current risk-based sizing",
            "proposal_only": True,
        }

    def exit_policy(self):
        return {
            "baseline": "existing BacktestExecutionEngine advanced exits",
            "proposal_only": True,
        }
