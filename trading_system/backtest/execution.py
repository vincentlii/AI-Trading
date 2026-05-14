from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from trading_system.backtest.risk import (
    AccountState,
    CostEstimate,
    OrderIntent,
    RiskDecision,
    RiskEngine,
    SimulatedOrder,
    TradeLogEntry,
)
from trading_system.strategies.base import StrategySignal


@dataclass(frozen=True)
class BacktestExecutionConfig:
    initial_equity: float = 100_000.0
    max_holding_bars: int = 20
    fee_rate: float = 0.0
    spread: float = 0.0
    slippage: float = 0.0
    funding: float = 0.0
    conservative_same_bar: bool = True
    point_value: float = 1.0


@dataclass(frozen=True)
class BacktestSignalInput:
    signal: StrategySignal
    execution_candles: tuple[object, ...]


@dataclass(frozen=True)
class BacktestSignalDecision:
    signal: StrategySignal
    status: str
    reason_codes: tuple[str, ...]
    intent: OrderIntent | None = None
    risk_decision: RiskDecision | None = None


@dataclass(frozen=True)
class BacktestFillResult:
    order: SimulatedOrder
    decision: RiskDecision
    entry_timestamp_ms: int | None
    exit_timestamp_ms: int | None
    entry_price: float
    exit_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    r_multiple: float
    holding_bars: int
    cost_estimate: CostEstimate
    trade_log: TradeLogEntry


@dataclass(frozen=True)
class EquityPoint:
    timestamp_ms: int | None
    equity: float
    drawdown_pct: float


@dataclass(frozen=True)
class BacktestSummary:
    net_profit: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    profit_factor: float
    average_holding_bars: float
    expectancy_per_trade: float
    cost_to_gross_profit_ratio: float
    trade_count: int
    gross_profit: float
    gross_loss: float
    total_cost: float


@dataclass(frozen=True)
class BacktestRunResult:
    decisions: tuple[BacktestSignalDecision, ...]
    fills: tuple[BacktestFillResult, ...]
    equity_curve: tuple[EquityPoint, ...]
    summary: BacktestSummary


class SignalOrderAdapter:
    def to_order_intent(
        self,
        signal: StrategySignal,
        execution_candles: Sequence[object],
        *,
        point_value: float = 1.0,
    ) -> tuple[OrderIntent | None, float | None, tuple[str, ...]]:
        if not execution_candles:
            return None, None, ("missing_execution_candles",)

        reasons: list[str] = []
        atr = _float_from_mapping(signal.trend_evidence, "atr")
        if atr is None or atr <= 0:
            reasons.append("missing_atr")

        stop_loss = signal.invalidation_level
        if stop_loss is None:
            reasons.append("missing_stop_loss")

        target_price = _target_price(signal.target_hint)
        if target_price is None:
            reasons.append("missing_target_price")

        direction = _normalize_direction(signal.direction)
        if direction is None:
            reasons.append("invalid_direction")

        entry_price = _as_float(getattr(execution_candles[0], "open", None))
        if entry_price is None or entry_price <= 0:
            reasons.append("invalid_entry_price")

        if reasons:
            return None, atr, tuple(dict.fromkeys(reasons))

        return (
            OrderIntent(
                strategy_name=signal.strategy_name,
                strategy_version=signal.strategy_version,
                setup_type=signal.setup_type,
                symbol=signal.symbol,
                venue=signal.venue,
                direction=direction,
                entry_price=entry_price,
                stop_loss=float(stop_loss),
                target_price=target_price,
                point_value=point_value,
            ),
            atr,
            (),
        )


class BacktestExecutionEngine:
    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        config: BacktestExecutionConfig | None = None,
        adapter: SignalOrderAdapter | None = None,
    ):
        self.risk_engine = risk_engine
        self.config = config or BacktestExecutionConfig()
        self.adapter = adapter or SignalOrderAdapter()

    def run(self, inputs: Sequence[BacktestSignalInput]) -> BacktestRunResult:
        equity = self.config.initial_equity
        high_water_mark = equity
        account = _account_state(equity=equity, high_water_mark=high_water_mark)
        decisions: list[BacktestSignalDecision] = []
        fills: list[BacktestFillResult] = []
        equity_curve: list[EquityPoint] = [EquityPoint(timestamp_ms=None, equity=equity, drawdown_pct=0.0)]

        for item in inputs:
            intent, atr, adapter_reasons = self.adapter.to_order_intent(
                item.signal,
                item.execution_candles,
                point_value=self.config.point_value,
            )
            if intent is None or atr is None or adapter_reasons:
                decisions.append(
                    BacktestSignalDecision(
                        signal=item.signal,
                        status="rejected",
                        reason_codes=adapter_reasons,
                        intent=intent,
                        risk_decision=None,
                    )
                )
                continue

            pretrade_cost = _estimate_cost(intent.entry_price, intent.entry_price, 0.0, self.config)
            risk_decision = self.risk_engine.evaluate(intent, account, atr=atr, cost_estimate=pretrade_cost)
            decision = BacktestSignalDecision(
                signal=item.signal,
                status=risk_decision.status,
                reason_codes=risk_decision.reason_codes,
                intent=intent,
                risk_decision=risk_decision,
            )
            decisions.append(decision)
            if risk_decision.approved_order is None:
                continue

            fill = _simulate_fill(
                risk_decision=risk_decision,
                execution_candles=item.execution_candles,
                config=self.config,
            )
            fills.append(fill)
            equity += fill.net_pnl
            high_water_mark = max(high_water_mark, equity)
            drawdown_pct = 0.0 if high_water_mark <= 0 else max(0.0, (high_water_mark - equity) / high_water_mark)
            equity_curve.append(
                EquityPoint(
                    timestamp_ms=fill.exit_timestamp_ms,
                    equity=equity,
                    drawdown_pct=drawdown_pct,
                )
            )
            account = _account_state(
                equity=equity,
                high_water_mark=high_water_mark,
                current_drawdown_pct=drawdown_pct,
                daily_pnl=equity - self.config.initial_equity,
            )

        return BacktestRunResult(
            decisions=tuple(decisions),
            fills=tuple(fills),
            equity_curve=tuple(equity_curve),
            summary=_summarize(fills, equity_curve, self.config.initial_equity),
        )


def _simulate_fill(
    *,
    risk_decision: RiskDecision,
    execution_candles: Sequence[object],
    config: BacktestExecutionConfig,
) -> BacktestFillResult:
    order = risk_decision.approved_order
    if order is None:
        raise ValueError("risk_decision must contain an approved order")

    intent = order.intent
    candles = tuple(execution_candles[: config.max_holding_bars])
    if not candles:
        raise ValueError("execution_candles must not be empty")

    exit_candle = candles[-1]
    exit_price = float(getattr(exit_candle, "close"))
    exit_reason = "time_exit"
    holding_bars = len(candles)

    for index, candle in enumerate(candles, start=1):
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        stop_hit, target_hit = _exit_hits(intent, high=high, low=low)
        if stop_hit and target_hit and config.conservative_same_bar:
            exit_price = intent.stop_loss
            exit_reason = "stop_loss"
        elif stop_hit:
            exit_price = intent.stop_loss
            exit_reason = "stop_loss"
        elif target_hit and intent.target_price is not None:
            exit_price = intent.target_price
            exit_reason = "target"
        else:
            continue
        exit_candle = candle
        holding_bars = index
        break

    gross_pnl = _gross_pnl(intent, exit_price, order.quantity)
    cost_estimate = _estimate_cost(intent.entry_price, exit_price, order.quantity, config)
    net_pnl = gross_pnl - cost_estimate.total
    r_multiple = 0.0 if order.risk_amount <= 0 else net_pnl / order.risk_amount
    trade_log = TradeLogEntry(
        order=order,
        decision=risk_decision,
        exit_reason=exit_reason,
        pnl=net_pnl,
        r_multiple=r_multiple,
    )
    return BacktestFillResult(
        order=order,
        decision=risk_decision,
        entry_timestamp_ms=_optional_timestamp(candles[0]),
        exit_timestamp_ms=_optional_timestamp(exit_candle),
        entry_price=intent.entry_price,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        r_multiple=r_multiple,
        holding_bars=holding_bars,
        cost_estimate=cost_estimate,
        trade_log=trade_log,
    )


def _exit_hits(intent: OrderIntent, *, high: float, low: float) -> tuple[bool, bool]:
    if intent.direction == "LONG":
        return low <= intent.stop_loss, intent.target_price is not None and high >= intent.target_price
    if intent.direction == "SHORT":
        return high >= intent.stop_loss, intent.target_price is not None and low <= intent.target_price
    return False, False


def _gross_pnl(intent: OrderIntent, exit_price: float, quantity: float) -> float:
    if intent.direction == "LONG":
        return (exit_price - intent.entry_price) * quantity * intent.point_value
    if intent.direction == "SHORT":
        return (intent.entry_price - exit_price) * quantity * intent.point_value
    raise ValueError(f"Unsupported direction: {intent.direction}")


def _estimate_cost(
    entry_price: float,
    exit_price: float,
    quantity: float,
    config: BacktestExecutionConfig,
) -> CostEstimate:
    point_quantity = quantity * config.point_value
    entry_notional = abs(entry_price * point_quantity)
    exit_notional = abs(exit_price * point_quantity)
    return CostEstimate(
        fees=(entry_notional + exit_notional) * config.fee_rate,
        spread=abs(config.spread * point_quantity),
        expected_slippage=abs(config.slippage * point_quantity * 2.0),
        funding=abs(config.funding * point_quantity),
    )


def _summarize(
    fills: Sequence[BacktestFillResult],
    equity_curve: Sequence[EquityPoint],
    initial_equity: float,
) -> BacktestSummary:
    if not fills:
        return BacktestSummary(
            net_profit=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_loss_ratio=0.0,
            profit_factor=0.0,
            average_holding_bars=0.0,
            expectancy_per_trade=0.0,
            cost_to_gross_profit_ratio=0.0,
            trade_count=0,
            gross_profit=0.0,
            gross_loss=0.0,
            total_cost=0.0,
        )

    net_values = [fill.net_pnl for fill in fills]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    gross_profit = sum(max(fill.gross_pnl, 0.0) for fill in fills)
    gross_loss = sum(min(fill.gross_pnl, 0.0) for fill in fills)
    total_cost = sum(fill.cost_estimate.total for fill in fills)
    average_win = sum(wins) / len(wins) if wins else 0.0
    average_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    return BacktestSummary(
        net_profit=sum(net_values),
        max_drawdown=max((point.drawdown_pct for point in equity_curve), default=0.0),
        win_rate=len(wins) / len(fills),
        profit_loss_ratio=0.0 if average_loss == 0 else average_win / average_loss,
        profit_factor=_profit_factor(gross_profit, gross_loss),
        average_holding_bars=sum(fill.holding_bars for fill in fills) / len(fills),
        expectancy_per_trade=sum(net_values) / len(fills),
        cost_to_gross_profit_ratio=0.0 if gross_profit <= 0 else total_cost / gross_profit,
        trade_count=len(fills),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_cost=total_cost,
    )


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_profit <= 0:
        return 0.0
    if gross_loss == 0:
        return math.inf
    return gross_profit / abs(gross_loss)


def _target_price(target_hint: object | None) -> float | None:
    if not isinstance(target_hint, Mapping):
        return None
    return _as_float(target_hint.get("target_price"))


def _float_from_mapping(source: Mapping[str, object], key: str) -> float | None:
    return _as_float(source.get(key))


def _as_float(value: object | None) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _normalize_direction(direction: str) -> str | None:
    normalized = direction.upper()
    if normalized in {"LONG", "SHORT"}:
        return normalized
    if normalized == "BUY":
        return "LONG"
    if normalized == "SELL":
        return "SHORT"
    return None


def _optional_timestamp(candle: object) -> int | None:
    value = getattr(candle, "timestamp_ms", None)
    if value is None:
        return None
    return int(value)


def _account_state(
    *,
    equity: float,
    high_water_mark: float,
    current_drawdown_pct: float = 0.0,
    daily_pnl: float = 0.0,
) -> AccountState:
    return AccountState(
        equity=equity,
        high_water_mark=high_water_mark,
        current_drawdown_pct=current_drawdown_pct,
        daily_pnl=daily_pnl,
        open_positions=(),
    )


__all__ = (
    "BacktestExecutionConfig",
    "BacktestSignalInput",
    "BacktestSignalDecision",
    "BacktestFillResult",
    "EquityPoint",
    "BacktestSummary",
    "BacktestRunResult",
    "SignalOrderAdapter",
    "BacktestExecutionEngine",
)
