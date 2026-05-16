from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderIntent:
    strategy_name: str
    strategy_version: str
    setup_type: str
    symbol: str
    venue: str
    direction: str
    entry_price: float
    stop_loss: float
    target_price: float | None
    point_value: float = 1.0

    @property
    def stop_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    def reward_distance(self) -> float | None:
        if self.target_price is None:
            return None
        return abs(self.target_price - self.entry_price)


@dataclass(frozen=True)
class RiskParameters:
    risk_pct: float = 0.005
    drawdown_level_1_pct: float = 0.02
    drawdown_level_1_risk_pct: float = 0.0035
    drawdown_level_2_pct: float = 0.04
    drawdown_level_2_risk_pct: float = 0.002
    hard_drawdown_stop_pct: float = 0.05
    daily_loss_limit_pct: float = 0.02
    min_stop_atr_multiple: float = 0.8
    max_stop_atr_multiple: float = 3.0
    max_single_notional_pct: float = 0.15
    max_total_gross_leverage: float = 1.0
    max_portfolio_heat_pct: float = 0.02
    min_liquidity_reversal_target_r: float = 1.5


@dataclass(frozen=True)
class PositionState:
    symbol: str
    venue: str
    direction: str
    quantity: float
    entry_price: float
    stop_loss: float
    initial_risk_amount: float
    notional_value: float


@dataclass(frozen=True)
class AccountState:
    equity: float
    high_water_mark: float
    current_drawdown_pct: float
    daily_pnl: float
    open_positions: tuple[PositionState, ...] = ()


@dataclass(frozen=True)
class CostEstimate:
    fees: float = 0.0
    spread: float = 0.0
    expected_slippage: float = 0.0
    funding: float = 0.0

    @property
    def total(self) -> float:
        return self.fees + self.spread + self.expected_slippage + self.funding

    def true_breakeven_price(self, *, entry_price: float, remaining_quantity: float, direction: str) -> float:
        if remaining_quantity <= 0:
            raise ValueError("remaining_quantity must be greater than 0")
        adjustment = self.total / remaining_quantity
        if direction.upper() == "LONG":
            return entry_price + adjustment
        if direction.upper() == "SHORT":
            return entry_price - adjustment
        raise ValueError(f"Unsupported direction: {direction}")


@dataclass(frozen=True)
class SimulatedOrder:
    intent: OrderIntent
    quantity: float
    notional_value: float
    risk_amount: float
    cost_estimate: CostEstimate


@dataclass(frozen=True)
class RiskDecision:
    status: str
    reason_codes: tuple[str, ...]
    risk_pct: float
    risk_amount: float
    approved_order: SimulatedOrder | None = None


@dataclass(frozen=True)
class TradeLogEntry:
    order: SimulatedOrder
    decision: RiskDecision
    exit_reason: str = ""
    pnl: float = 0.0
    r_multiple: float = 0.0
    exit_events: tuple[object, ...] = ()


class RiskEngine:
    def __init__(self, parameters: RiskParameters):
        self.parameters = parameters

    def evaluate(
        self,
        intent: OrderIntent,
        account: AccountState,
        *,
        atr: float,
        cost_estimate: CostEstimate | None = None,
    ) -> RiskDecision:
        if atr <= 0:
            raise ValueError("atr must be greater than 0")
        if account.equity <= 0:
            raise ValueError("account equity must be greater than 0")

        cost_estimate = cost_estimate or CostEstimate()
        reasons: list[str] = []
        risk_pct = self._effective_risk_pct(account, reasons)
        risk_amount = account.equity * risk_pct

        if intent.stop_distance < self.parameters.min_stop_atr_multiple * atr:
            reasons.append("stop_distance_too_near")
        if intent.stop_distance > self.parameters.max_stop_atr_multiple * atr:
            reasons.append("stop_distance_too_far")
        if intent.stop_distance <= 0:
            reasons.append("invalid_stop_distance")

        quantity = 0.0
        notional_value = 0.0
        if intent.stop_distance > 0:
            quantity = risk_amount / (intent.stop_distance * intent.point_value)
            notional_value = quantity * intent.entry_price * intent.point_value

        if notional_value > account.equity * self.parameters.max_single_notional_pct:
            reasons.append("notional_cap_exceeded")

        current_notional = sum(position.notional_value for position in account.open_positions)
        if current_notional + notional_value > account.equity * self.parameters.max_total_gross_leverage:
            reasons.append("total_gross_leverage_exceeded")

        current_heat = sum(position.initial_risk_amount for position in account.open_positions)
        if current_heat + risk_amount > account.equity * self.parameters.max_portfolio_heat_pct:
            reasons.append("portfolio_heat_exceeded")

        if (
            intent.setup_type == "liquidity_reversal"
            and intent.reward_distance() is not None
            and intent.stop_distance > 0
            and (intent.reward_distance() / intent.stop_distance) < self.parameters.min_liquidity_reversal_target_r
        ):
            reasons.append("target_reward_below_minimum")

        if account.daily_pnl <= -(account.equity * self.parameters.daily_loss_limit_pct):
            reasons.append("daily_loss_limit_reached")

        if reasons:
            return RiskDecision(
                status="rejected",
                reason_codes=tuple(dict.fromkeys(reasons)),
                risk_pct=risk_pct,
                risk_amount=risk_amount,
                approved_order=None,
            )

        return RiskDecision(
            status="approved",
            reason_codes=(),
            risk_pct=risk_pct,
            risk_amount=risk_amount,
            approved_order=SimulatedOrder(
                intent=intent,
                quantity=quantity,
                notional_value=notional_value,
                risk_amount=risk_amount,
                cost_estimate=cost_estimate,
            ),
        )

    def _effective_risk_pct(self, account: AccountState, reasons: list[str]) -> float:
        drawdown = account.current_drawdown_pct
        if drawdown >= self.parameters.hard_drawdown_stop_pct:
            reasons.append("hard_drawdown_stop")
            return 0.0
        if drawdown >= self.parameters.drawdown_level_2_pct:
            return self.parameters.drawdown_level_2_risk_pct
        if drawdown >= self.parameters.drawdown_level_1_pct:
            return self.parameters.drawdown_level_1_risk_pct
        return self.parameters.risk_pct
