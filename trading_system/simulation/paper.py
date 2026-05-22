from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from trading_system.backtest.execution import SignalOrderAdapter
from trading_system.backtest.risk import (
    AccountState,
    CostEstimate,
    PositionState,
    RiskDecision,
    RiskEngine,
    SimulatedOrder,
)
from trading_system.strategies.base import StrategySignal


@dataclass(frozen=True)
class PaperBrokerConfig:
    initial_equity: float = 100_000.0
    fee_rate: float = 0.0
    spread: float = 0.0
    slippage: float = 0.0
    funding: float = 0.0
    point_value: float = 1.0


@dataclass(frozen=True)
class PaperSignalInput:
    signal: StrategySignal
    execution_candles: tuple[object, ...]


@dataclass(frozen=True)
class ReviewLogEntry:
    event_type: str
    timestamp_ms: int | None
    symbol: str
    venue: str
    strategy_name: str
    strategy_version: str
    setup_type: str
    status: str
    reason_codes: tuple[str, ...] = ()
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperSignalDecision:
    signal: StrategySignal
    status: str
    reason_codes: tuple[str, ...]
    risk_decision: RiskDecision | None = None
    order: SimulatedOrder | None = None


@dataclass(frozen=True)
class PaperFill:
    order: SimulatedOrder
    timestamp_ms: int | None
    fill_price: float
    quantity: float
    cost_estimate: CostEstimate


@dataclass(frozen=True)
class PaperTradingResult:
    decisions: tuple[PaperSignalDecision, ...]
    fills: tuple[PaperFill, ...]
    positions: tuple[PositionState, ...]
    review_log: tuple[ReviewLogEntry, ...]
    account: AccountState


class PaperBroker:
    def __init__(self, config: PaperBrokerConfig | None = None):
        self.config = config or PaperBrokerConfig()

    def submit_order(self, order: SimulatedOrder, execution_candle: object) -> tuple[PaperFill, PositionState]:
        fill_price = float(getattr(execution_candle, "open"))
        fill = PaperFill(
            order=order,
            timestamp_ms=_optional_timestamp(execution_candle),
            fill_price=fill_price,
            quantity=order.quantity,
            cost_estimate=_estimate_entry_cost(
                fill_price=fill_price,
                quantity=order.quantity,
                point_value=order.intent.point_value,
                config=self.config,
            ),
        )
        position = PositionState(
            symbol=order.intent.symbol,
            venue=order.intent.venue,
            direction=order.intent.direction,
            quantity=order.quantity,
            entry_price=fill_price,
            stop_loss=order.intent.stop_loss,
            initial_risk_amount=order.risk_amount,
            notional_value=abs(fill_price * order.quantity * order.intent.point_value),
        )
        return fill, position


class PaperTradingEngine:
    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        config: PaperBrokerConfig | None = None,
        adapter: SignalOrderAdapter | None = None,
        broker: PaperBroker | None = None,
    ):
        self.risk_engine = risk_engine
        self.config = config or PaperBrokerConfig()
        self.adapter = adapter or SignalOrderAdapter()
        self.broker = broker or PaperBroker(self.config)

    def run(self, inputs: Sequence[PaperSignalInput]) -> PaperTradingResult:
        account = AccountState(
            equity=self.config.initial_equity,
            high_water_mark=self.config.initial_equity,
            current_drawdown_pct=0.0,
            daily_pnl=0.0,
            open_positions=(),
        )
        decisions: list[PaperSignalDecision] = []
        fills: list[PaperFill] = []
        positions: list[PositionState] = []
        review_log: list[ReviewLogEntry] = []

        for item in inputs:
            review_log.append(_review_entry(item.signal, "signal_received", "received", timestamp_ms=None))
            intent, atr, adapter_reasons = self.adapter.to_order_intent(
                item.signal,
                item.execution_candles,
                point_value=self.config.point_value,
            )
            if intent is None or atr is None or adapter_reasons:
                decisions.append(
                    PaperSignalDecision(
                        signal=item.signal,
                        status="rejected",
                        reason_codes=adapter_reasons,
                    )
                )
                review_log.append(
                    _review_entry(
                        item.signal,
                        "adapter_rejected",
                        "rejected",
                        reason_codes=adapter_reasons,
                        timestamp_ms=_first_timestamp(item.execution_candles),
                    )
                )
                continue

            risk_decision = self.risk_engine.evaluate(intent, account, atr=atr)
            if risk_decision.approved_order is None:
                decisions.append(
                    PaperSignalDecision(
                        signal=item.signal,
                        status=risk_decision.status,
                        reason_codes=risk_decision.reason_codes,
                        risk_decision=risk_decision,
                    )
                )
                review_log.append(
                    _review_entry(
                        item.signal,
                        "risk_rejected",
                        risk_decision.status,
                        reason_codes=risk_decision.reason_codes,
                        timestamp_ms=_first_timestamp(item.execution_candles),
                        payload={"risk_pct": risk_decision.risk_pct, "risk_amount": risk_decision.risk_amount},
                    )
                )
                continue

            order = risk_decision.approved_order
            fill, position = self.broker.submit_order(order, item.execution_candles[0])
            positions.append(position)
            fills.append(fill)
            decisions.append(
                PaperSignalDecision(
                    signal=item.signal,
                    status=risk_decision.status,
                    reason_codes=(),
                    risk_decision=risk_decision,
                    order=order,
                )
            )
            review_log.extend(
                (
                    _review_entry(
                        item.signal,
                        "order_created",
                        "approved",
                        timestamp_ms=fill.timestamp_ms,
                        payload={"quantity": order.quantity, "notional_value": order.notional_value},
                    ),
                    _review_entry(
                        item.signal,
                        "fill_recorded",
                        "filled",
                        timestamp_ms=fill.timestamp_ms,
                        payload={"fill_price": fill.fill_price, "cost": fill.cost_estimate.total},
                    ),
                    _review_entry(
                        item.signal,
                        "position_opened",
                        "open",
                        timestamp_ms=fill.timestamp_ms,
                        payload={"entry_price": position.entry_price, "stop_loss": position.stop_loss},
                    ),
                )
            )
            account = AccountState(
                equity=account.equity,
                high_water_mark=account.high_water_mark,
                current_drawdown_pct=account.current_drawdown_pct,
                daily_pnl=account.daily_pnl,
                open_positions=tuple(positions),
            )

        return PaperTradingResult(
            decisions=tuple(decisions),
            fills=tuple(fills),
            positions=tuple(positions),
            review_log=tuple(review_log),
            account=account,
        )


def _estimate_entry_cost(
    *,
    fill_price: float,
    quantity: float,
    point_value: float,
    config: PaperBrokerConfig,
) -> CostEstimate:
    point_quantity = quantity * point_value
    notional = abs(fill_price * point_quantity)
    return CostEstimate(
        fees=notional * config.fee_rate,
        spread=abs(config.spread * point_quantity),
        expected_slippage=abs(config.slippage * point_quantity),
        funding=abs(config.funding * point_quantity),
    )


def _review_entry(
    signal: StrategySignal,
    event_type: str,
    status: str,
    *,
    reason_codes: tuple[str, ...] = (),
    timestamp_ms: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> ReviewLogEntry:
    return ReviewLogEntry(
        event_type=event_type,
        timestamp_ms=timestamp_ms,
        symbol=signal.symbol,
        venue=signal.venue,
        strategy_name=signal.strategy_name,
        strategy_version=signal.strategy_version,
        setup_type=signal.setup_type,
        status=status,
        reason_codes=reason_codes,
        payload=payload or {},
    )


def _first_timestamp(candles: Sequence[object]) -> int | None:
    if not candles:
        return None
    return _optional_timestamp(candles[0])


def _optional_timestamp(candle: object) -> int | None:
    value = getattr(candle, "timestamp_ms", None)
    if value is None:
        return None
    return int(value)


__all__ = (
    "PaperBroker",
    "PaperBrokerConfig",
    "PaperFill",
    "PaperSignalDecision",
    "PaperSignalInput",
    "PaperTradingEngine",
    "PaperTradingResult",
    "ReviewLogEntry",
)
