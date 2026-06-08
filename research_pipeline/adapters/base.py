from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArtifactContract:
    required_inputs: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    performance_row_type: str = "closed_trade"
    excluded_performance_row_types: list[str] = field(
        default_factory=lambda: ["proposal_candidate", "sizing_diagnostic", "diagnostic_only", "summary_row"]
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditProfile:
    performance_row_type: str = "closed_trade"
    excluded_performance_row_types: list[str] = field(
        default_factory=lambda: ["proposal_candidate", "sizing_diagnostic", "diagnostic_only", "summary_row"]
    )
    required_lineage_fields: list[str] = field(
        default_factory=lambda: ["trade_id", "execution_id", "candidate_id", "event_id"]
    )
    required_time_fields: list[str] = field(
        default_factory=lambda: [
            "feature_cutoff_time",
            "structure_confirmed_time",
            "sweep_time",
            "reclaim_time",
            "signal_time",
            "entry_time",
            "exit_time",
        ]
    )
    time_order_checks: list[tuple[str, str, str]] = field(
        default_factory=lambda: [
            ("feature_cutoff_time_lte_signal_time", "feature_cutoff_time", "signal_time"),
            ("structure_confirmed_time_lte_sweep_time", "structure_confirmed_time", "sweep_time"),
            ("sweep_time_lte_reclaim_time", "sweep_time", "reclaim_time"),
            ("reclaim_time_lte_signal_time", "reclaim_time", "signal_time"),
            ("signal_time_lt_entry_time", "signal_time", "entry_time"),
            ("entry_time_lte_exit_time", "entry_time", "exit_time"),
        ]
    )
    requires_metric_recompute: bool = True
    requires_no_lookahead: bool = True
    requires_robustness: bool = True
    requires_exposure_restriction: bool = True
    requires_regression_baseline: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiagnosticStage:
    name: str
    description: str = ""
    hard_gate: bool = True
    threshold_fields: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProposalExpansionVariant:
    variant_id: str
    description: str
    parameter_overrides: dict[str, Any] = field(default_factory=dict)
    trigger_stage: str = ""
    proposal_only: bool = True
    execution_eligible: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyAdapter(ABC):
    name: str
    display_name: str = ""
    adapter_version: str = "adapter.v1"
    proposal_only: bool = True
    formal_conclusion_enabled: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "adapter_version": self.adapter_version,
            "proposal_only": self.proposal_only,
            "formal_conclusion_enabled": self.formal_conclusion_enabled,
            "artifact_contract": self.artifact_contract().as_dict(),
            "audit_profile": self.audit_profile().as_dict(),
            "candidate_schema": self.candidate_schema(),
            "lineage_fields": self.lineage_fields(),
            "diagnostic_stages": [stage.as_dict() for stage in self.diagnostic_stages()],
            "proposal_expansion_variants": [
                variant.as_dict() for variant in self.proposal_expansion_variants()
            ],
        }

    def required_features(self) -> list[str]:
        return []

    def structure_sources(self) -> list[str]:
        return []

    def setup_filter(self) -> tuple[str, ...]:
        return (self.name,)

    def parameter_namespace(self) -> str:
        return self.name

    def artifact_contract(self) -> ArtifactContract:
        return ArtifactContract()

    def audit_profile(self) -> AuditProfile:
        return AuditProfile()

    def candidate_schema(self) -> dict[str, str]:
        return {
            "candidate_id": "string",
            "event_id": "string",
            "row_type": "string",
        }

    def lineage_fields(self) -> list[str]:
        return list(self.audit_profile().required_lineage_fields)

    def diagnostic_stages(self) -> list[DiagnosticStage]:
        return []

    def proposal_expansion_variants(self) -> list[ProposalExpansionVariant]:
        return []

    def evaluate_diagnostics(self, *args, **kwargs) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not provide expansion diagnostics evaluator.")

    def audit_input_manifest(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "adapter_version": self.adapter_version,
            "artifact_contract": self.artifact_contract().as_dict(),
            "audit_profile": self.audit_profile().as_dict(),
            "candidate_schema": self.candidate_schema(),
            "lineage_fields": self.lineage_fields(),
            "proposal_only": self.proposal_only,
            "formal_conclusion_enabled": self.formal_conclusion_enabled,
        }

    @abstractmethod
    def generate_candidates(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def filter_policy(self):
        raise NotImplementedError

    @abstractmethod
    def sizing_policy(self):
        raise NotImplementedError

    @abstractmethod
    def exit_policy(self):
        raise NotImplementedError
