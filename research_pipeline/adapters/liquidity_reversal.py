from __future__ import annotations

from research_pipeline.adapters.base import ArtifactContract, AuditProfile, StrategyAdapter


class LiquidityReversalAdapter(StrategyAdapter):
    name = "liquidity_reversal"
    display_name = "Liquidity Reversal"
    adapter_version = "proposal_only.v1"
    strategy_family = "price_action_volume"
    status = "proposal_only"
    proposal_only = True
    formal_conclusion_enabled = False
    supported_assets = ["BTC", "ETH"]
    supported_markets = ["SWAP"]
    supported_profiles = ["B", "C"]
    smoke_ready_combos = ["CHOCH true", "displacement_after_reclaim"]
    primary_combo = "displacement_after_reclaim"
    sizing_models = [
        "current_risk_based_sizing",
        "notional_capped_risk_based",
    ]
    required_artifact_types = [
        "key_metrics",
        "aggregation_result",
        "edge_analysis_result",
        "sizing_diagnostics_result",
        "smoke_plan",
    ]

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "adapter_version": self.adapter_version,
            "strategy_family": self.strategy_family,
            "status": self.status,
            "proposal_only": self.proposal_only,
            "formal_conclusion_enabled": self.formal_conclusion_enabled,
            "supported_assets": list(self.supported_assets),
            "supported_markets": list(self.supported_markets),
            "supported_profiles": list(self.supported_profiles),
            "baseline_keys": self.baseline_metric_keys(),
            "smoke_ready_combos": list(self.smoke_ready_combos),
            "primary_combo": self.primary_combo,
            "sizing_models": list(self.sizing_models),
            "required_artifact_types": list(self.required_artifact_types),
            "artifact_contract": self.artifact_contract().as_dict(),
            "audit_profile": self.audit_profile().as_dict(),
            "candidate_schema": self.candidate_schema(),
            "lineage_fields": self.lineage_fields(),
        }

    def artifact_contract(self) -> ArtifactContract:
        return ArtifactContract(
            required_inputs=[
                "filter_results",
                "execution_results",
                "sizing_candidates",
                "artifact_index",
                "research_run_registry",
            ],
            required_outputs=[
                "closed_trade_rows",
                "proposal_candidate_rows",
                "diagnostic_rows",
                "summary_rows",
                "robustness_input_rows",
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
                "event_key",
            ],
        )

    def candidate_schema(self) -> dict[str, str]:
        return {
            "candidate_id": "string",
            "event_id": "string",
            "event_key": "string",
            "asset": "string",
            "profile": "string",
            "direction": "string",
            "row_type": "string",
            "sweep_time": "timestamp",
            "reclaim_time": "timestamp",
            "signal_time": "timestamp",
            "entry_time": "timestamp",
        }

    def baseline_metric_keys(self) -> list[str]:
        return [
            "fresh_candidates",
            "formal_approved",
            "proposal_approved",
            "closed_trades",
            "MFE_R",
            "MAE_R",
            "net_R",
            "time_cut_exit_rate",
        ]

    def baseline_combo_keys(self) -> list[str]:
        return [
            "high_sweep_rvol",
            "high_sweep_rvol + CHOCH true + high_wick",
            "CHOCH true",
            "displacement_after_reclaim",
        ]

    def generate_candidates(self, *args, **kwargs):
        raise NotImplementedError("PR10 adapter does not migrate LR scanner.")

    def filter_replay(self, *args, **kwargs):
        raise NotImplementedError("PR10 adapter does not migrate LR filter replay.")

    def run_sizing_engine(self, *args, **kwargs):
        raise NotImplementedError("PR10 adapter does not migrate LR sizing engine.")

    def run_execution(self, *args, **kwargs):
        raise NotImplementedError("PR10 adapter does not migrate LR execution.")

    def filter_policy(self):
        raise NotImplementedError("PR10 adapter does not migrate LR filter policy.")

    def sizing_policy(self):
        raise NotImplementedError("PR10 adapter does not migrate LR sizing policy.")

    def exit_policy(self):
        raise NotImplementedError("PR10 adapter does not migrate LR exit policy.")
