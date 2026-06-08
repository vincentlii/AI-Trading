from __future__ import annotations

from collections.abc import Mapping

from trading_system.config.loader import BacktestPresetConfig


SIZE_ONLY_REJECTS = {"margin_required_too_high"}


def apply_capped_risk_sizing(
    row: Mapping[str, object],
    preset: BacktestPresetConfig,
    *,
    min_actual_risk_pct_after_cap: float = 0.001,
) -> dict[str, object]:
    output = dict(row)
    equity = float(preset.execution.initial_equity)
    entry = _float(row.get("entry_price") or row.get("entry_reference_price")) or 0.0
    stop = _float(row.get("stop_price")) or 0.0
    stop_distance = abs(entry - stop)
    point_value = float(preset.execution.point_value)
    theoretical_risk = equity * float(preset.risk.risk_pct)
    theoretical_size = 0.0 if stop_distance <= 0 or point_value <= 0 else theoretical_risk / (stop_distance * point_value)
    theoretical_notional = abs(theoretical_size * entry * point_value)
    max_notional = equity * float(preset.risk.max_single_notional_pct)
    capped_notional = min(theoretical_notional, max_notional)
    capped_size = 0.0 if entry <= 0 or point_value <= 0 else capped_notional / (entry * point_value)
    actual_risk = capped_size * stop_distance * point_value
    actual_risk_pct = 0.0 if equity <= 0 else actual_risk / equity
    margin_before = theoretical_notional / max(float(preset.risk.max_total_gross_leverage), 1e-12)
    margin_after = capped_notional / max(float(preset.risk.max_total_gross_leverage), 1e-12)
    before_reason = str(row.get("reject_reason") or "")
    formal_approved = bool(row.get("formal_approved"))
    structural_valid = str(row.get("structural_stop_quality") or "valid") == "valid"
    eligible_reject = not before_reason or before_reason in SIZE_ONLY_REJECTS
    after_reason = ""
    if not structural_valid:
        after_reason = str(row.get("structural_stop_quality") or before_reason or "structural_stop_invalid")
    elif not eligible_reject:
        after_reason = before_reason
    elif actual_risk_pct < min_actual_risk_pct_after_cap:
        after_reason = "actual_risk_after_cap_below_minimum"
    elif margin_after > equity:
        after_reason = "margin_required_too_high"
    proposal_approved = formal_approved or not after_reason
    output.update(
        {
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "proposal_only": True,
            "formal_approved": formal_approved,
            "approved_before_cap": formal_approved,
            "proposal_approved_after_cap": proposal_approved,
            "approved_after_cap": proposal_approved,
            "theoretical_risk_based_position_size": theoretical_size,
            "capped_position_size": capped_size,
            "theoretical_notional": theoretical_notional,
            "capped_notional": capped_notional,
            "margin_required_before_cap": margin_before,
            "margin_required_after_cap": margin_after,
            "actual_risk_after_cap": actual_risk,
            "actual_risk_after_cap_pct": actual_risk_pct,
            "capped_by_notional": capped_notional + 1e-12 < theoretical_notional,
            "risk_reject_reason_before_cap": before_reason,
            "risk_reject_reason_after_cap": after_reason,
            "approval_basis": "proposal_approved_after_cap" if proposal_approved else "rejected_after_cap",
        }
    )
    return output


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ("SIZE_ONLY_REJECTS", "apply_capped_risk_sizing")
