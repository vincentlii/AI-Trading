from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from trading_system.backtest.execution import (
    BacktestExecutionConfig,
    BacktestExitEvent,
    BacktestFillResult,
    EquityPoint,
    SignalOrderAdapter,
    simulate_approved_fill,
)
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
    max_holding_bars: int = 20
    fee_rate: float = 0.0
    spread: float = 0.0
    slippage: float = 0.0
    funding: float = 0.0
    conservative_same_bar: bool = True
    point_value: float = 1.0
    enable_advanced_exits: bool = False
    partial_take_profit_r: float = 1.0
    partial_take_profit_pct: float = 0.5
    move_stop_to_true_breakeven: bool = True
    chandelier_period: int = 22
    chandelier_atr_multiple: float = 4.0


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
    closed_positions: tuple[PositionState, ...]
    closed_trades: tuple[BacktestFillResult, ...]
    exit_events: tuple[BacktestExitEvent, ...]
    equity_curve: tuple[EquityPoint, ...]
    review_log: tuple[ReviewLogEntry, ...]
    account: AccountState


@dataclass(frozen=True)
class _ActivePaperPosition:
    position: PositionState
    close_result: BacktestFillResult
    signal: StrategySignal


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
        active_positions: list[_ActivePaperPosition] = []
        closed_positions: list[PositionState] = []
        closed_trades: list[BacktestFillResult] = []
        exit_events: list[BacktestExitEvent] = []
        equity_curve: list[EquityPoint] = [EquityPoint(timestamp_ms=None, equity=account.equity, drawdown_pct=0.0)]
        review_log: list[ReviewLogEntry] = []

        for item in inputs:
            entry_timestamp = _first_timestamp(item.execution_candles)
            account = _close_due_positions(
                active_positions=active_positions,
                account=account,
                timestamp_ms=entry_timestamp,
                closed_positions=closed_positions,
                closed_trades=closed_trades,
                exit_events=exit_events,
                equity_curve=equity_curve,
                review_log=review_log,
                force_close=False,
            )
            review_log.append(_review_entry(item.signal, "signal_received", "received", timestamp_ms=entry_timestamp))
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
            close_result = simulate_approved_fill(
                risk_decision=risk_decision,
                execution_candles=item.execution_candles,
                config=_to_backtest_config(self.config),
                atr=atr,
            )
            positions.append(position)
            active_positions.append(
                _ActivePaperPosition(
                    position=position,
                    close_result=close_result,
                    signal=item.signal,
                )
            )
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
                open_positions=tuple(active.position for active in active_positions),
            )

        account = _close_due_positions(
            active_positions=active_positions,
            account=account,
            timestamp_ms=None,
            closed_positions=closed_positions,
            closed_trades=closed_trades,
            exit_events=exit_events,
            equity_curve=equity_curve,
            review_log=review_log,
            force_close=True,
        )
        return PaperTradingResult(
            decisions=tuple(decisions),
            fills=tuple(fills),
            positions=tuple(positions),
            closed_positions=tuple(closed_positions),
            closed_trades=tuple(closed_trades),
            exit_events=tuple(exit_events),
            equity_curve=tuple(equity_curve),
            review_log=tuple(review_log),
            account=account,
        )


def _close_due_positions(
    *,
    active_positions: list[_ActivePaperPosition],
    account: AccountState,
    timestamp_ms: int | None,
    closed_positions: list[PositionState],
    closed_trades: list[BacktestFillResult],
    exit_events: list[BacktestExitEvent],
    equity_curve: list[EquityPoint],
    review_log: list[ReviewLogEntry],
    force_close: bool,
) -> AccountState:
    remaining: list[_ActivePaperPosition] = []
    current_account = account
    for active in active_positions:
        close_timestamp = active.close_result.exit_timestamp_ms
        is_due = force_close or (
            timestamp_ms is not None and close_timestamp is not None and close_timestamp < timestamp_ms
        )
        if not is_due:
            remaining.append(active)
            continue

        current_account = _close_position(
            active=active,
            account=current_account,
            closed_positions=closed_positions,
            closed_trades=closed_trades,
            exit_events=exit_events,
            equity_curve=equity_curve,
            review_log=review_log,
        )

    active_positions[:] = remaining
    return AccountState(
        equity=current_account.equity,
        high_water_mark=current_account.high_water_mark,
        current_drawdown_pct=current_account.current_drawdown_pct,
        daily_pnl=current_account.daily_pnl,
        open_positions=tuple(active.position for active in active_positions),
    )


def _close_position(
    *,
    active: _ActivePaperPosition,
    account: AccountState,
    closed_positions: list[PositionState],
    closed_trades: list[BacktestFillResult],
    exit_events: list[BacktestExitEvent],
    equity_curve: list[EquityPoint],
    review_log: list[ReviewLogEntry],
) -> AccountState:
    close_result = active.close_result
    closed_positions.append(active.position)
    closed_trades.append(close_result)
    exit_events.extend(close_result.exit_events)

    equity = account.equity + close_result.net_pnl
    high_water_mark = max(account.high_water_mark, equity)
    drawdown_pct = 0.0 if high_water_mark <= 0 else max(0.0, (high_water_mark - equity) / high_water_mark)
    daily_pnl = account.daily_pnl + close_result.net_pnl
    equity_curve.append(
        EquityPoint(
            timestamp_ms=close_result.exit_timestamp_ms,
            equity=equity,
            drawdown_pct=drawdown_pct,
        )
    )
    for event in close_result.exit_events:
        review_log.append(
            _review_entry(
                active.signal,
                "exit_recorded",
                event.event_type,
                timestamp_ms=event.timestamp_ms,
                payload={
                    "price": event.price,
                    "quantity": event.quantity,
                    "gross_pnl": event.gross_pnl,
                    "net_pnl": event.net_pnl,
                    "cost": event.cost_estimate.total,
                },
            )
        )
    review_log.extend(
        (
            _review_entry(
                active.signal,
                "position_closed",
                close_result.exit_reason,
                timestamp_ms=close_result.exit_timestamp_ms,
                payload={
                    "entry_price": close_result.entry_price,
                    "exit_price": close_result.exit_price,
                    "net_pnl": close_result.net_pnl,
                    "r_multiple": close_result.r_multiple,
                    "holding_bars": close_result.holding_bars,
                },
            ),
            _review_entry(
                active.signal,
                "equity_updated",
                "updated",
                timestamp_ms=close_result.exit_timestamp_ms,
                payload={
                    "equity": equity,
                    "drawdown_pct": drawdown_pct,
                    "daily_pnl": daily_pnl,
                },
            ),
        )
    )
    return AccountState(
        equity=equity,
        high_water_mark=high_water_mark,
        current_drawdown_pct=drawdown_pct,
        daily_pnl=daily_pnl,
        open_positions=(),
    )


def _to_backtest_config(config: PaperBrokerConfig) -> BacktestExecutionConfig:
    return BacktestExecutionConfig(
        initial_equity=config.initial_equity,
        max_holding_bars=config.max_holding_bars,
        fee_rate=config.fee_rate,
        spread=config.spread,
        slippage=config.slippage,
        funding=config.funding,
        conservative_same_bar=config.conservative_same_bar,
        point_value=config.point_value,
        enable_advanced_exits=config.enable_advanced_exits,
        partial_take_profit_r=config.partial_take_profit_r,
        partial_take_profit_pct=config.partial_take_profit_pct,
        move_stop_to_true_breakeven=config.move_stop_to_true_breakeven,
        chandelier_period=config.chandelier_period,
        chandelier_atr_multiple=config.chandelier_atr_multiple,
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
