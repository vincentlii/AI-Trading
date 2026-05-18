from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping

from trading_system.backtest.risk import RiskParameters
from trading_system.config.loader import (
    BacktestPresetConfig,
    ConfigError,
)


ALLOWED_CHANGE_PATHS = {
    "risk.risk_pct",
    "risk.drawdown_level_1_pct",
    "risk.drawdown_level_1_risk_pct",
    "risk.drawdown_level_2_pct",
    "risk.drawdown_level_2_risk_pct",
    "risk.hard_drawdown_stop_pct",
    "risk.daily_loss_limit_pct",
    "risk.min_stop_atr_multiple",
    "risk.max_stop_atr_multiple",
    "risk.max_single_notional_pct",
    "risk.max_total_gross_leverage",
    "risk.max_portfolio_heat_pct",
    "risk.min_liquidity_reversal_target_r",
    "costs.fee_rate",
    "costs.spread",
    "costs.slippage",
    "costs.funding",
    "execution.initial_equity",
    "execution.max_holding_bars",
    "execution.conservative_same_bar",
    "execution.point_value",
    "execution.enable_advanced_exits",
    "execution.partial_take_profit_r",
    "execution.partial_take_profit_pct",
    "execution.move_stop_to_true_breakeven",
    "execution.chandelier_period",
    "execution.chandelier_atr_multiple",
    "scan.profile_keys",
    "strategy.enabled",
    "strategy.enabled_setups",
    "ranking.fast_profile_fee_reject_threshold",
    "ranking.min_trades_for_primary",
}

FORBIDDEN_TERMS = ("api_key", "secret", "passphrase", "live_order", "real_order", "trade_permission")


class ProposalError(ValueError):
    pass


@dataclass(frozen=True)
class ProposalChange:
    path: str
    before: object
    after: object
    reason: str


@dataclass(frozen=True)
class ParameterProposal:
    proposal_id: str
    title: str
    source: str
    base_preset_path: str
    base_config_version: str
    base_config_fingerprint: str
    changes: tuple[ProposalChange, ...]
    evidence: Mapping[str, object]
    expected_impact: str
    risks: tuple[str, ...]
    validation_plan: tuple[str, ...]
    auto_apply: bool = False


def make_parameter_proposal(
    *,
    proposal_id: str,
    title: str,
    source: str,
    base_preset_path: str,
    base_preset: BacktestPresetConfig,
    changes: tuple[ProposalChange, ...],
    evidence: Mapping[str, object],
    expected_impact: str,
    risks: tuple[str, ...],
    validation_plan: tuple[str, ...],
) -> ParameterProposal:
    proposal = ParameterProposal(
        proposal_id=_required_text(proposal_id, "proposal_id"),
        title=_required_text(title, "title"),
        source=_required_text(source, "source"),
        base_preset_path=_required_text(base_preset_path, "base_preset_path"),
        base_config_version=base_preset.config_version,
        base_config_fingerprint=base_preset.config_fingerprint,
        changes=_non_empty_changes(changes),
        evidence=dict(evidence),
        expected_impact=_required_text(expected_impact, "expected_impact"),
        risks=tuple(_required_text(item, "risk") for item in risks),
        validation_plan=tuple(_required_text(item, "validation_plan") for item in validation_plan),
        auto_apply=False,
    )
    _validate_no_forbidden_terms(asdict(proposal))
    return proposal


def save_parameter_proposal(proposal: ParameterProposal, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{proposal.proposal_id}.json"
    payload = _proposal_to_payload(proposal)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_parameter_proposal(path: str | Path) -> ParameterProposal:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProposalError(f"invalid proposal JSON: {error}") from error
    if not isinstance(payload, Mapping):
        raise ProposalError("proposal payload must be an object")
    return _proposal_from_payload(payload)


def apply_parameter_proposal(
    base_preset: BacktestPresetConfig,
    proposal: ParameterProposal,
) -> BacktestPresetConfig:
    if proposal.auto_apply:
        raise ProposalError("proposal auto_apply must be false")
    if proposal.base_config_fingerprint != base_preset.config_fingerprint:
        raise ProposalError("proposal base_config_fingerprint does not match current preset")
    if proposal.base_config_version != base_preset.config_version:
        raise ProposalError("proposal base_config_version does not match current preset")

    updated = base_preset
    for change in proposal.changes:
        updated = _apply_change(updated, change)

    _validate_preset(updated)
    return replace(updated, config_fingerprint=_fingerprint_preset(updated))


def _apply_change(preset: BacktestPresetConfig, change: ProposalChange) -> BacktestPresetConfig:
    if change.path not in ALLOWED_CHANGE_PATHS:
        raise ProposalError(f"proposal path is not allowed: {change.path}")
    current_value = _get_value(preset, change.path)
    if current_value != change.before:
        raise ProposalError(f"proposal before value mismatch for {change.path}: {change.before!r} != {current_value!r}")
    section, field_name = change.path.split(".", 1)
    section_value = getattr(preset, section)
    updated_section = replace(section_value, **{field_name: _normalize_after_value(current_value, change.after)})
    return replace(preset, **{section: updated_section})


def _get_value(preset: BacktestPresetConfig, path: str) -> object:
    section, field_name = path.split(".", 1)
    return getattr(getattr(preset, section), field_name)


def _normalize_after_value(current_value: object, after: object) -> object:
    if isinstance(current_value, tuple):
        if not isinstance(after, list | tuple):
            raise ProposalError("tuple fields require list or tuple proposed values")
        return tuple(after)
    if isinstance(current_value, bool):
        if not isinstance(after, bool):
            raise ProposalError("boolean fields require boolean proposed values")
        return after
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        if not isinstance(after, int) or isinstance(after, bool):
            raise ProposalError("integer fields require integer proposed values")
        return after
    if isinstance(current_value, float):
        if not isinstance(after, int | float) or isinstance(after, bool):
            raise ProposalError("float fields require numeric proposed values")
        return float(after)
    if isinstance(current_value, str):
        if not isinstance(after, str):
            raise ProposalError("string fields require string proposed values")
        return after
    return after


def _validate_preset(preset: BacktestPresetConfig) -> None:
    _pct("risk.risk_pct", preset.risk.risk_pct)
    _pct("risk.drawdown_level_1_pct", preset.risk.drawdown_level_1_pct)
    _pct("risk.drawdown_level_1_risk_pct", preset.risk.drawdown_level_1_risk_pct)
    _pct("risk.drawdown_level_2_pct", preset.risk.drawdown_level_2_pct)
    _pct("risk.drawdown_level_2_risk_pct", preset.risk.drawdown_level_2_risk_pct)
    _pct("risk.hard_drawdown_stop_pct", preset.risk.hard_drawdown_stop_pct)
    _pct("risk.daily_loss_limit_pct", preset.risk.daily_loss_limit_pct)
    _pct("risk.max_single_notional_pct", preset.risk.max_single_notional_pct)
    _pct("risk.max_portfolio_heat_pct", preset.risk.max_portfolio_heat_pct)
    if not 0 < preset.risk.min_stop_atr_multiple <= preset.risk.max_stop_atr_multiple:
        raise ConfigError("min_stop_atr_multiple must be > 0 and <= max_stop_atr_multiple")
    if preset.risk.max_total_gross_leverage <= 0:
        raise ConfigError("max_total_gross_leverage must be greater than 0")
    if preset.risk.min_liquidity_reversal_target_r <= 0:
        raise ConfigError("min_liquidity_reversal_target_r must be greater than 0")

    _non_negative("costs.fee_rate", preset.costs.fee_rate)
    _non_negative("costs.spread", preset.costs.spread)
    _non_negative("costs.slippage", preset.costs.slippage)
    _non_negative("costs.funding", preset.costs.funding)
    if preset.costs.fee_rate > 0.05:
        raise ConfigError("fee_rate must be <= 0.05")

    if preset.execution.initial_equity <= 0:
        raise ConfigError("initial_equity must be greater than 0")
    if preset.execution.max_holding_bars <= 0:
        raise ConfigError("max_holding_bars must be greater than 0")
    if preset.execution.point_value <= 0:
        raise ConfigError("point_value must be greater than 0")
    if preset.execution.partial_take_profit_r <= 0:
        raise ConfigError("partial_take_profit_r must be greater than 0")
    if not 0 < preset.execution.partial_take_profit_pct <= 1:
        raise ConfigError("partial_take_profit_pct must be > 0 and <= 1")
    if preset.execution.chandelier_period <= 0:
        raise ConfigError("chandelier_period must be greater than 0")
    if preset.execution.chandelier_atr_multiple <= 0:
        raise ConfigError("chandelier_atr_multiple must be greater than 0")

    if not preset.scan.profile_keys or set(preset.scan.profile_keys) - {"A", "B", "C"}:
        raise ConfigError("profile keys must be A/B/C")
    if not preset.strategy.enabled_setups:
        raise ConfigError("enabled_setups must not be empty")
    if preset.strategy.name == "trend_price_volume" and preset.strategy.version == "v1":
        invalid = set(preset.strategy.enabled_setups) - {"trend_continuation", "liquidity_reversal"}
        if invalid:
            raise ConfigError(f"strategy setup is not supported: {', '.join(sorted(invalid))}")
    _pct("ranking.fast_profile_fee_reject_threshold", preset.ranking.fast_profile_fee_reject_threshold)
    if preset.ranking.min_trades_for_primary <= 0:
        raise ConfigError("min_trades_for_primary must be greater than 0")


def _proposal_to_payload(proposal: ParameterProposal) -> dict[str, object]:
    return asdict(proposal)


def _proposal_from_payload(payload: Mapping[str, object]) -> ParameterProposal:
    changes_raw = payload.get("changes")
    if not isinstance(changes_raw, list) or not changes_raw:
        raise ProposalError("changes must be a non-empty list")
    changes = []
    for item in changes_raw:
        if not isinstance(item, Mapping):
            raise ProposalError("changes must contain objects")
        changes.append(
            ProposalChange(
                path=_required_text(item.get("path"), "changes.path"),
                before=item.get("before"),
                after=item.get("after"),
                reason=_required_text(item.get("reason"), "changes.reason"),
            )
        )
    proposal = ParameterProposal(
        proposal_id=_required_text(payload.get("proposal_id"), "proposal_id"),
        title=_required_text(payload.get("title"), "title"),
        source=_required_text(payload.get("source"), "source"),
        base_preset_path=_required_text(payload.get("base_preset_path"), "base_preset_path"),
        base_config_version=_required_text(payload.get("base_config_version"), "base_config_version"),
        base_config_fingerprint=_required_text(payload.get("base_config_fingerprint"), "base_config_fingerprint"),
        changes=tuple(changes),
        evidence=_mapping(payload.get("evidence"), "evidence"),
        expected_impact=_required_text(payload.get("expected_impact"), "expected_impact"),
        risks=_text_tuple(payload.get("risks"), "risks"),
        validation_plan=_text_tuple(payload.get("validation_plan"), "validation_plan"),
        auto_apply=False,
    )
    if payload.get("auto_apply") is not False:
        raise ProposalError("proposal auto_apply must be false")
    _validate_no_forbidden_terms(_proposal_to_payload(proposal))
    return proposal


def _fingerprint_preset(preset: BacktestPresetConfig) -> str:
    normalized = {
        "config_version": preset.config_version,
        "assets": asdict(preset.assets),
        "risk": asdict(preset.risk),
        "costs": asdict(preset.costs),
        "execution": asdict(preset.execution),
        "scan": asdict(preset.scan),
        "strategy": asdict(preset.strategy),
        "ranking": asdict(preset.ranking),
    }
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _non_empty_changes(changes: tuple[ProposalChange, ...]) -> tuple[ProposalChange, ...]:
    if not changes:
        raise ProposalError("changes must not be empty")
    for change in changes:
        _required_text(change.path, "change.path")
        _required_text(change.reason, "change.reason")
    return changes


def _validate_no_forbidden_terms(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False).lower()
    for term in FORBIDDEN_TERMS:
        if term in text:
            raise ProposalError(f"proposal contains forbidden term: {term}")


def _required_text(value: object, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProposalError(f"{key} must be a non-empty string")
    return value


def _mapping(value: object, key: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProposalError(f"{key} must be an object")
    return dict(value)


def _text_tuple(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ProposalError(f"{key} must be a non-empty list")
    return tuple(_required_text(item, key) for item in value)


def _pct(key: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ConfigError(f"{key} must be between 0 and 1")


def _non_negative(key: str, value: float) -> None:
    if value < 0:
        raise ConfigError(f"{key} must be non-negative")


__all__ = (
    "ParameterProposal",
    "ProposalChange",
    "ProposalError",
    "apply_parameter_proposal",
    "load_parameter_proposal",
    "make_parameter_proposal",
    "save_parameter_proposal",
)
