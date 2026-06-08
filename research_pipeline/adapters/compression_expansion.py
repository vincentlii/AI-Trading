from __future__ import annotations

from research_pipeline.adapters.base import (
    ArtifactContract,
    AuditProfile,
    DiagnosticStage,
    ProposalExpansionVariant,
    StrategyAdapter,
)
from trading_system.strategies.trend_price_volume_v1.features import evaluate_compression_expansion_diagnostics


class CompressionExpansionAdapter(StrategyAdapter):
    name = "compression_expansion"
    display_name = "Compression Expansion"
    adapter_version = "research_validation.v1"
    strategy_family = "compression_expansion_breakout"
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
                "implementation_setup": "compression_expansion",
                "semantic_name": "compression_expansion_breakout",
            }
        )
        return payload

    def setup_filter(self) -> tuple[str, ...]:
        return ("compression_expansion",)

    def parameter_namespace(self) -> str:
        return "compression_expansion"

    def required_features(self) -> list[str]:
        return [
            "compression_box",
            "volatility_contraction",
            "breakout_displacement",
            "breakout_volume_expansion",
            "midpoint_or_boundary_hold",
        ]

    def structure_sources(self) -> list[str]:
        return ["compression_box_high_low", "breakout_candle", "confirmation_candle"]

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
                "compression_event_id",
            ],
            required_time_fields=[
                "feature_cutoff_time",
                "compression_start_time",
                "compression_end_time",
                "breakout_time",
                "confirmation_time",
                "signal_time",
                "entry_time",
                "exit_time",
            ],
            time_order_checks=[
                ("feature_cutoff_time_lte_signal_time", "feature_cutoff_time", "signal_time"),
                ("compression_start_time_lte_compression_end_time", "compression_start_time", "compression_end_time"),
                ("compression_end_time_lte_breakout_time", "compression_end_time", "breakout_time"),
                ("breakout_time_lte_confirmation_time", "breakout_time", "confirmation_time"),
                ("confirmation_time_lte_signal_time", "confirmation_time", "signal_time"),
                ("signal_time_lt_entry_time", "signal_time", "entry_time"),
                ("entry_time_lte_exit_time", "entry_time", "exit_time"),
            ],
        )

    def candidate_schema(self) -> dict[str, str]:
        return {
            "candidate_id": "string",
            "event_id": "string",
            "compression_event_id": "string",
            "asset": "string",
            "direction": "string",
            "row_type": "string",
            "compression_start_time": "timestamp",
            "compression_end_time": "timestamp",
            "breakout_time": "timestamp",
            "confirmation_time": "timestamp",
            "signal_time": "timestamp",
            "entry_time": "timestamp",
        }

    def diagnostic_stages(self) -> list[DiagnosticStage]:
        return [
            DiagnosticStage("window_ready", "Required structure, entry, and volatility context exists."),
            DiagnosticStage("compression_detected", "Recent structure forms a bounded low-volatility compression box."),
            DiagnosticStage("compression_quality_valid", "Compression range and average range are below configured ATR thresholds."),
            DiagnosticStage("breakout_detected", "Breakout candle closes outside the compression box."),
            DiagnosticStage("breakout_displacement_valid", "Breakout candle has sufficient body/range displacement."),
            DiagnosticStage("breakout_volume_valid", "Breakout volume expands versus compression baseline."),
            DiagnosticStage("failed_breakout_absent", "Confirmation candle does not quickly close back inside the box."),
            DiagnosticStage("midpoint_hold", "Confirmation holds the breakout midpoint."),
            DiagnosticStage("retest_hold", "Confirmation/retest holds the box boundary within tolerance."),
            DiagnosticStage("continuation_ready", "Continuation direction remains intact after breakout confirmation."),
            DiagnosticStage("subtype_selected", "CE subtype matches the proposal-only variant focus."),
            DiagnosticStage("risk_precheck_pass", "Box-based stop and target provide a positive pre-risk geometry."),
        ]

    def proposal_expansion_variants(self) -> list[ProposalExpansionVariant]:
        return [
            ProposalExpansionVariant(
                variant_id="ce_semantic_acceptance_opposite_stop_v2",
                description="Proposal-only CE semantic acceptance with opposite-edge structural stop; tests true expansion semantics without relaxing RiskEngine.",
                parameter_overrides={
                    "compression_expansion": {
                        "compression_breakout_semantic_policy": "semantic_v2",
                        "compression_acceptance_window_bars": 3,
                        "compression_stop_policy": "opposite_edge_structural_stop",
                        "compression_stop_buffer_atr": 0.10,
                        "compression_min_breakout_score": 0.50,
                        "compression_min_close_outside_box_atr": 0.02,
                    }
                },
                trigger_stage="risk_precheck_pass",
            ),
            ProposalExpansionVariant(
                variant_id="ce_semantic_acceptance_breakout_extreme_stop_v2",
                description="Proposal-only CE semantic acceptance with breakout-candle extreme structural stop; tests impulse breakout subtype quality.",
                parameter_overrides={
                    "compression_expansion": {
                        "compression_breakout_semantic_policy": "semantic_v2",
                        "compression_acceptance_window_bars": 3,
                        "compression_stop_policy": "breakout_extreme_structural_stop",
                        "compression_stop_buffer_atr": 0.10,
                        "compression_min_breakout_score": 0.58,
                        "compression_min_close_outside_box_atr": 0.02,
                        "compression_subtype_focus": "impulse_breakout",
                    }
                },
                trigger_stage="risk_precheck_pass",
            ),
            ProposalExpansionVariant(
                variant_id="ce_acceptance_then_retest_entry_v2",
                description="Proposal-only CE acceptance-then-retest entry with acceptance-retest structural stop; tests breakout_pullback bridge semantics.",
                parameter_overrides={
                    "compression_expansion": {
                        "compression_breakout_semantic_policy": "semantic_v2",
                        "compression_acceptance_window_bars": 3,
                        "compression_entry_policy": "acceptance_retest_close",
                        "compression_stop_policy": "acceptance_retest_structural_stop",
                        "compression_stop_buffer_atr": 0.10,
                        "compression_hold_policy": "midpoint_or_boundary",
                        "compression_min_breakout_score": 0.45,
                        "compression_subtype_focus": "acceptance_retest",
                    }
                },
                trigger_stage="risk_precheck_pass",
            ),
        ]

    def evaluate_diagnostics(self, *args, **kwargs):
        return evaluate_compression_expansion_diagnostics(*args, **kwargs)

    def generate_candidates(self, *args, **kwargs):
        raise NotImplementedError("compression_expansion research validation runs through Research Pipeline.")

    def filter_policy(self):
        return {
            "mode": "proposal_only_research_validation",
            "setup_filter": "compression_expansion",
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
