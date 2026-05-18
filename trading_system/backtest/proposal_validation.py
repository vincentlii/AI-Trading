from __future__ import annotations

from dataclasses import dataclass

from trading_system.backtest.batch import BacktestBatchReport, BacktestBatchRunner
from trading_system.config.proposals import ParameterProposal, apply_parameter_proposal
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.base import Strategy


@dataclass(frozen=True)
class ProposalValidationResult:
    proposal_id: str
    status: str
    auto_apply: bool
    base_config_version: str
    base_config_fingerprint: str
    proposed_config_fingerprint: str
    base_report: BacktestBatchReport
    proposed_report: BacktestBatchReport


def validate_parameter_proposal(
    *,
    proposal: ParameterProposal,
    base_preset: BacktestPresetConfig,
    repository,
    strategy: Strategy,
) -> ProposalValidationResult:
    proposed_preset = apply_parameter_proposal(base_preset, proposal)
    base_report = BacktestBatchRunner(
        repository=repository,
        preset=base_preset,
        strategy=strategy,
    ).run()
    proposed_report = BacktestBatchRunner(
        repository=repository,
        preset=proposed_preset,
        strategy=strategy,
    ).run()
    return ProposalValidationResult(
        proposal_id=proposal.proposal_id,
        status="validated",
        auto_apply=False,
        base_config_version=base_preset.config_version,
        base_config_fingerprint=base_preset.config_fingerprint,
        proposed_config_fingerprint=proposed_preset.config_fingerprint,
        base_report=base_report,
        proposed_report=proposed_report,
    )


__all__ = (
    "ProposalValidationResult",
    "validate_parameter_proposal",
)
