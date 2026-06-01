from __future__ import annotations

from dataclasses import dataclass

from trading_system.backtest.risk import OrderIntent
from trading_system.config.loader import BacktestPresetConfig


@dataclass(frozen=True)
class ContractRiskDiagnostics:
    fee: float
    spread: float
    slippage: float
    funding_rate: float
    funding_paid_or_received: float
    leverage: float
    margin_required: float
    notional: float
    liquidation_price: float
    liquidation_distance_pct: float
    maintenance_margin_ratio: float
    gross_exposure: float
    net_exposure: float
    portfolio_heat: float
    reject_reason: str


def estimate_contract_risk(
    *,
    intent: OrderIntent,
    quantity: float,
    risk_amount: float,
    preset: BacktestPresetConfig,
    equity: float | None = None,
    adverse_funding_multiplier: float = 1.0,
) -> ContractRiskDiagnostics:
    account_equity = float(equity or preset.execution.initial_equity)
    notional = abs(intent.entry_price * quantity * intent.point_value)
    leverage = 0.0 if account_equity <= 0 else notional / account_equity
    margin_required = notional / max(preset.risk.max_total_gross_leverage, 1e-12)
    maintenance_margin_ratio = 0.005
    maintenance_margin = notional * maintenance_margin_ratio
    funding_rate = float(preset.costs.funding) * adverse_funding_multiplier
    funding = abs(funding_rate * quantity * intent.point_value)
    fee = notional * 2.0 * float(preset.costs.fee_rate)
    spread = abs(float(preset.costs.spread) * quantity * intent.point_value)
    slippage = notional * 2.0 * float(preset.costs.spread_slippage_rate) + abs(float(preset.costs.slippage) * quantity * intent.point_value * 2.0)
    liquidation_price = _liquidation_price(intent, margin_required, maintenance_margin, quantity)
    liquidation_distance_pct = abs(intent.entry_price - liquidation_price) / intent.entry_price if intent.entry_price > 0 else 0.0
    portfolio_heat = 0.0 if account_equity <= 0 else risk_amount / account_equity

    reject_reason = ""
    if margin_required > account_equity:
        reject_reason = "margin_required_too_high"
    elif liquidation_distance_pct < 0.01:
        reject_reason = "liquidation_distance_too_close"
    elif portfolio_heat > preset.risk.max_portfolio_heat_pct:
        reject_reason = "portfolio_heat_exceeded"

    signed_notional = notional if intent.direction == "LONG" else -notional
    return ContractRiskDiagnostics(
        fee=fee,
        spread=spread,
        slippage=slippage,
        funding_rate=funding_rate,
        funding_paid_or_received=funding,
        leverage=leverage,
        margin_required=margin_required,
        notional=notional,
        liquidation_price=liquidation_price,
        liquidation_distance_pct=liquidation_distance_pct,
        maintenance_margin_ratio=maintenance_margin_ratio,
        gross_exposure=notional,
        net_exposure=signed_notional,
        portfolio_heat=portfolio_heat,
        reject_reason=reject_reason,
    )


def _liquidation_price(intent: OrderIntent, margin_required: float, maintenance_margin: float, quantity: float) -> float:
    if quantity <= 0 or intent.point_value <= 0:
        return intent.entry_price
    buffer = max(margin_required - maintenance_margin, 0.0) / (quantity * intent.point_value)
    if intent.direction == "LONG":
        return max(0.0, intent.entry_price - buffer)
    return intent.entry_price + buffer


__all__ = ("ContractRiskDiagnostics", "estimate_contract_risk")
