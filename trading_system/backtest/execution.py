from __future__ import annotations

import math
import hashlib
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
    spread_slippage_rate: float = 0.0
    funding: float = 0.0
    conservative_same_bar: bool = True
    point_value: float = 1.0
    enable_advanced_exits: bool = False
    partial_take_profit_r: float = 1.0
    partial_take_profit_pct: float = 0.5
    move_stop_to_true_breakeven: bool = True
    breakeven_after_mfe_r: float = 0.0
    chandelier_period: int = 22
    chandelier_atr_multiple: float = 4.0
    reversal_time_cut_bars: int = 0
    reversal_time_cut_min_mfe_r: float = 0.0


@dataclass(frozen=True)
class BacktestSignalInput:
    signal: StrategySignal
    execution_candles: tuple[object, ...]
    candidate_id: str = ""
    event_id: str = ""
    feature_cutoff_time: int | None = None
    structure_confirmed_time: int | None = None
    sweep_time: int | None = None
    reclaim_time: int | None = None
    signal_time: int | None = None
    bar_confirmed: bool = True
    no_lookahead_safe: bool | None = None


@dataclass(frozen=True)
class BacktestSignalDecision:
    signal: StrategySignal
    status: str
    reason_codes: tuple[str, ...]
    intent: OrderIntent | None = None
    risk_decision: RiskDecision | None = None


@dataclass(frozen=True)
class BacktestExitEvent:
    timestamp_ms: int | None
    bar_index: int
    event_type: str
    price: float
    quantity: float
    gross_pnl: float
    cost_estimate: CostEstimate
    net_pnl: float


@dataclass(frozen=True)
class BacktestFillResult:
    order: SimulatedOrder
    decision: RiskDecision
    trade_id: str
    execution_id: str
    candidate_id: str
    event_id: str
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
    exit_events: tuple[BacktestExitEvent, ...] = field(default_factory=tuple)
    mae: float = 0.0
    mfe: float = 0.0
    mae_r: float = 0.0
    mfe_r: float = 0.0
    bars_to_mae: int = 0
    bars_to_mfe: int = 0
    r_path_after_entry: tuple[float, ...] = field(default_factory=tuple)
    max_favorable_drawdown_ratio: float = 0.0
    stop_efficiency_ratio: float = 0.0
    trade_excursion_asymmetry: float = 0.0
    exit_bar_index: int = 0
    reached_1r: bool = False
    reached_1_5r: bool = False
    reached_2r: bool = False
    moved_to_breakeven: bool = False
    breakeven_hit: bool = False
    partial_take_profit_hit: bool = False
    same_bar_ambiguous: bool = False
    same_bar_resolution: str = ""
    intrabar_scan_available: bool = False
    intrabar_scan_used: bool = False
    stop_and_target_touched_same_bar: bool = False
    entry_and_exit_same_bar: bool = False
    forced_pessimistic_exit: bool = False


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

        for signal_index, item in enumerate(inputs):
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

            lineage = _signal_lineage(item, signal_index=signal_index)
            fill = _simulate_fill(
                risk_decision=risk_decision,
                execution_candles=item.execution_candles,
                config=self.config,
                atr=atr,
                lineage=lineage,
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


def simulate_approved_fill(
    *,
    risk_decision: RiskDecision,
    execution_candles: Sequence[object],
    config: BacktestExecutionConfig,
    atr: float,
    lineage: Mapping[str, object] | None = None,
) -> BacktestFillResult:
    return _simulate_fill(
        risk_decision=risk_decision,
        execution_candles=execution_candles,
        config=config,
        atr=atr,
        lineage=lineage or {},
    )


def _simulate_fill(
    *,
    risk_decision: RiskDecision,
    execution_candles: Sequence[object],
    config: BacktestExecutionConfig,
    atr: float,
    lineage: Mapping[str, object],
) -> BacktestFillResult:
    order = risk_decision.approved_order
    if order is None:
        raise ValueError("risk_decision must contain an approved order")

    intent = order.intent
    candles = tuple(execution_candles[: config.max_holding_bars])
    if not candles:
        raise ValueError("execution_candles must not be empty")

    if config.enable_advanced_exits:
        return _simulate_advanced_fill(
            risk_decision=risk_decision,
            candles=candles,
            config=config,
            atr=atr,
            lineage=lineage,
        )

    return _simulate_simple_fill(risk_decision=risk_decision, candles=candles, config=config, lineage=lineage)


def _simulate_simple_fill(
    *,
    risk_decision: RiskDecision,
    candles: Sequence[object],
    config: BacktestExecutionConfig,
    lineage: Mapping[str, object],
) -> BacktestFillResult:
    order = risk_decision.approved_order
    if order is None:
        raise ValueError("risk_decision must contain an approved order")

    intent = order.intent
    exit_candle = candles[-1]
    exit_price = float(getattr(exit_candle, "close"))
    exit_reason = "time_exit"
    holding_bars = len(candles)

    for index, candle in enumerate(candles, start=1):
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        stop_hit, target_hit = _exit_hits(intent, high=high, low=low)
        same_bar_ambiguous = stop_hit and target_hit
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
            if _should_time_cut_momentum_failure(
                intent=intent,
                candles=candles[:index],
                bar_index=index,
                config=config,
            ):
                exit_price = float(getattr(candle, "close"))
                exit_reason = "time_cut_exit"
                exit_candle = candle
                holding_bars = index
                same_bar_ambiguous = False
                break
            continue
        exit_candle = candle
        holding_bars = index
        break
    else:
        same_bar_ambiguous = False

    exit_event = _build_exit_event(
        intent=intent,
        candle=exit_candle,
        bar_index=holding_bars,
        event_type=exit_reason,
        price=exit_price,
        quantity=order.quantity,
        config=config,
    )
    gross_pnl = exit_event.gross_pnl
    cost_estimate = exit_event.cost_estimate
    net_pnl = gross_pnl - cost_estimate.total
    r_multiple = 0.0 if order.risk_amount <= 0 else net_pnl / order.risk_amount
    trade_log = TradeLogEntry(
        order=order,
        decision=risk_decision,
        exit_reason=exit_reason,
        pnl=net_pnl,
        r_multiple=r_multiple,
        exit_events=(exit_event,),
    )
    diagnostics = _fill_diagnostics(
        intent=intent,
        candles=candles,
        holding_bars=holding_bars,
        exit_reason=exit_reason,
        exit_events=(exit_event,),
        same_bar_ambiguous=same_bar_ambiguous,
        stop_and_target_touched_same_bar=same_bar_ambiguous,
        entry_and_exit_same_bar=holding_bars == 1,
        forced_pessimistic_exit=same_bar_ambiguous and config.conservative_same_bar,
    )
    entry_timestamp = _optional_timestamp(candles[0])
    exit_timestamp = _optional_timestamp(exit_candle)
    identity = _execution_identity(
        lineage=lineage,
        intent=intent,
        entry_timestamp_ms=entry_timestamp,
        exit_timestamp_ms=exit_timestamp,
        exit_reason=exit_reason,
    )
    return BacktestFillResult(
        order=order,
        decision=risk_decision,
        trade_id=identity["trade_id"],
        execution_id=identity["execution_id"],
        candidate_id=identity["candidate_id"],
        event_id=identity["event_id"],
        entry_timestamp_ms=entry_timestamp,
        exit_timestamp_ms=exit_timestamp,
        entry_price=intent.entry_price,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        r_multiple=r_multiple,
        holding_bars=holding_bars,
        cost_estimate=cost_estimate,
        trade_log=trade_log,
        exit_events=(exit_event,),
        **diagnostics,
    )


def _simulate_advanced_fill(
    *,
    risk_decision: RiskDecision,
    candles: Sequence[object],
    config: BacktestExecutionConfig,
    atr: float,
    lineage: Mapping[str, object],
) -> BacktestFillResult:
    order = risk_decision.approved_order
    if order is None:
        raise ValueError("risk_decision must contain an approved order")

    intent = order.intent
    events: list[BacktestExitEvent] = []
    seen_candles: list[object] = []
    remaining_quantity = order.quantity
    current_stop = intent.stop_loss
    current_stop_reason = "stop_loss"
    partial_done = False
    partial_price = _r_price(intent, config.partial_take_profit_r)
    partial_pct = min(max(config.partial_take_profit_pct, 0.0), 1.0)

    for index, candle in enumerate(candles, start=1):
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        stop_hit = _stop_hit(intent.direction, current_stop, high=high, low=low)
        target_hit = _target_hit(intent, high=high, low=low)
        partial_hit = (
            not partial_done
            and partial_pct > 0.0
            and remaining_quantity > 0.0
            and _price_hit(intent.direction, partial_price, high=high, low=low)
        )

        if stop_hit and (target_hit or partial_hit) and config.conservative_same_bar:
            events.append(
                _build_exit_event(
                    intent=intent,
                    candle=candle,
                    bar_index=index,
                    event_type=current_stop_reason,
                    price=current_stop,
                    quantity=remaining_quantity,
                    config=config,
                )
            )
            remaining_quantity = 0.0
            break
        if stop_hit:
            events.append(
                _build_exit_event(
                    intent=intent,
                    candle=candle,
                    bar_index=index,
                    event_type=current_stop_reason,
                    price=current_stop,
                    quantity=remaining_quantity,
                    config=config,
                )
            )
            remaining_quantity = 0.0
            break

        if partial_hit:
            partial_quantity = min(remaining_quantity, order.quantity * partial_pct)
            events.append(
                _build_exit_event(
                    intent=intent,
                    candle=candle,
                    bar_index=index,
                    event_type="partial_take_profit",
                    price=partial_price,
                    quantity=partial_quantity,
                    config=config,
                )
            )
            remaining_quantity -= partial_quantity
            partial_done = True
            if remaining_quantity <= 0.0:
                break
            if config.move_stop_to_true_breakeven:
                observed_mfe_r = config.partial_take_profit_r
                if observed_mfe_r < config.breakeven_after_mfe_r:
                    seen_candles.append(candle)
                    continue
                current_stop = _true_breakeven_stop(
                    intent=intent,
                    remaining_quantity=remaining_quantity,
                    config=config,
                )
                current_stop_reason = "breakeven_stop"

            target_after_partial = _target_hit(intent, high=high, low=low)
            if target_after_partial and intent.target_price is not None:
                events.append(
                    _build_exit_event(
                        intent=intent,
                        candle=candle,
                        bar_index=index,
                        event_type="target",
                        price=intent.target_price,
                        quantity=remaining_quantity,
                        config=config,
                    )
                )
                remaining_quantity = 0.0
                break
        elif target_hit and intent.target_price is not None:
            events.append(
                _build_exit_event(
                    intent=intent,
                    candle=candle,
                    bar_index=index,
                    event_type="target",
                    price=intent.target_price,
                    quantity=remaining_quantity,
                    config=config,
                )
            )
            remaining_quantity = 0.0
            break

        if _should_time_cut_momentum_failure(
            intent=intent,
            candles=tuple(seen_candles) + (candle,),
            bar_index=index,
            config=config,
        ):
            events.append(
                _build_exit_event(
                    intent=intent,
                    candle=candle,
                    bar_index=index,
                    event_type="time_cut_exit",
                    price=float(getattr(candle, "close")),
                    quantity=remaining_quantity,
                    config=config,
                )
            )
            remaining_quantity = 0.0
            break

        seen_candles.append(candle)
        if partial_done and remaining_quantity > 0.0:
            candidate_stop = _chandelier_stop(intent.direction, seen_candles, atr=atr, config=config)
            tightened_stop = _tighten_stop(intent.direction, current_stop, candidate_stop)
            if tightened_stop != current_stop:
                current_stop = tightened_stop
                current_stop_reason = "chandelier_exit"

    if remaining_quantity > 0.0:
        exit_candle = candles[-1]
        events.append(
            _build_exit_event(
                intent=intent,
                candle=exit_candle,
                bar_index=len(candles),
                event_type="time_exit",
                price=float(getattr(exit_candle, "close")),
                quantity=remaining_quantity,
                config=config,
            )
        )

    return _build_fill_result(
        risk_decision=risk_decision,
        candles=candles,
        events=tuple(events),
        lineage=lineage,
    )


def _build_fill_result(
    *,
    risk_decision: RiskDecision,
    candles: Sequence[object],
    events: tuple[BacktestExitEvent, ...],
    lineage: Mapping[str, object],
) -> BacktestFillResult:
    order = risk_decision.approved_order
    if order is None:
        raise ValueError("risk_decision must contain an approved order")
    if not events:
        raise ValueError("events must not be empty")

    final_event = events[-1]
    gross_pnl = sum(event.gross_pnl for event in events)
    cost_estimate = _sum_cost_estimates(event.cost_estimate for event in events)
    net_pnl = sum(event.net_pnl for event in events)
    r_multiple = 0.0 if order.risk_amount <= 0 else net_pnl / order.risk_amount
    trade_log = TradeLogEntry(
        order=order,
        decision=risk_decision,
        exit_reason=final_event.event_type,
        pnl=net_pnl,
        r_multiple=r_multiple,
        exit_events=events,
    )
    diagnostics = _fill_diagnostics(
        intent=order.intent,
        candles=candles,
        holding_bars=final_event.bar_index,
        exit_reason=final_event.event_type,
        exit_events=events,
    )
    entry_timestamp = _optional_timestamp(candles[0])
    identity = _execution_identity(
        lineage=lineage,
        intent=order.intent,
        entry_timestamp_ms=entry_timestamp,
        exit_timestamp_ms=final_event.timestamp_ms,
        exit_reason=final_event.event_type,
    )
    return BacktestFillResult(
        order=order,
        decision=risk_decision,
        trade_id=identity["trade_id"],
        execution_id=identity["execution_id"],
        candidate_id=identity["candidate_id"],
        event_id=identity["event_id"],
        entry_timestamp_ms=entry_timestamp,
        exit_timestamp_ms=final_event.timestamp_ms,
        entry_price=order.intent.entry_price,
        exit_price=final_event.price,
        exit_reason=final_event.event_type,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        r_multiple=r_multiple,
        holding_bars=final_event.bar_index,
        cost_estimate=cost_estimate,
        trade_log=trade_log,
        exit_events=events,
        **diagnostics,
    )


def _build_exit_event(
    *,
    intent: OrderIntent,
    candle: object,
    bar_index: int,
    event_type: str,
    price: float,
    quantity: float,
    config: BacktestExecutionConfig,
) -> BacktestExitEvent:
    gross_pnl = _gross_pnl(intent, price, quantity)
    cost_estimate = _estimate_cost(intent.entry_price, price, quantity, config)
    net_pnl = gross_pnl - cost_estimate.total
    return BacktestExitEvent(
        timestamp_ms=_optional_timestamp(candle),
        bar_index=bar_index,
        event_type=event_type,
        price=price,
        quantity=quantity,
        gross_pnl=gross_pnl,
        cost_estimate=cost_estimate,
        net_pnl=net_pnl,
    )


def _sum_cost_estimates(costs: Sequence[CostEstimate]) -> CostEstimate:
    costs = tuple(costs)
    return CostEstimate(
        fees=sum(cost.fees for cost in costs),
        spread=sum(cost.spread for cost in costs),
        expected_slippage=sum(cost.expected_slippage for cost in costs),
        funding=sum(cost.funding for cost in costs),
    )


def _exit_hits(intent: OrderIntent, *, high: float, low: float) -> tuple[bool, bool]:
    if intent.direction == "LONG":
        return low <= intent.stop_loss, intent.target_price is not None and high >= intent.target_price
    if intent.direction == "SHORT":
        return high >= intent.stop_loss, intent.target_price is not None and low <= intent.target_price
    return False, False


def _stop_hit(direction: str, stop_price: float, *, high: float, low: float) -> bool:
    if direction == "LONG":
        return low <= stop_price
    if direction == "SHORT":
        return high >= stop_price
    return False


def _target_hit(intent: OrderIntent, *, high: float, low: float) -> bool:
    if intent.target_price is None:
        return False
    return _price_hit(intent.direction, intent.target_price, high=high, low=low)


def _price_hit(direction: str, price: float, *, high: float, low: float) -> bool:
    if direction == "LONG":
        return high >= price
    if direction == "SHORT":
        return low <= price
    return False


def _r_price(intent: OrderIntent, r_multiple: float) -> float:
    if intent.direction == "LONG":
        return intent.entry_price + intent.stop_distance * r_multiple
    if intent.direction == "SHORT":
        return intent.entry_price - intent.stop_distance * r_multiple
    raise ValueError(f"Unsupported direction: {intent.direction}")


def _signal_lineage(item: BacktestSignalInput, *, signal_index: int) -> dict[str, object]:
    signal = item.signal
    candidate_id = _lineage_value(item.candidate_id, signal.explanation_payload, signal.price_action_evidence, "candidate_id")
    event_id = _lineage_value(item.event_id, signal.explanation_payload, signal.price_action_evidence, "event_id")
    fallback_seed = "|".join(
        (
            signal.strategy_name,
            signal.strategy_version,
            signal.symbol,
            signal.venue,
            signal.setup_type,
            signal.direction,
            str(signal_index),
        )
    )
    if not candidate_id:
        candidate_id = "signal_" + _stable_token(fallback_seed)
    if not event_id:
        event_id = str(candidate_id)
    return {
        "candidate_id": str(candidate_id),
        "event_id": str(event_id),
        "feature_cutoff_time": item.feature_cutoff_time,
        "structure_confirmed_time": item.structure_confirmed_time,
        "sweep_time": item.sweep_time,
        "reclaim_time": item.reclaim_time,
        "signal_time": item.signal_time,
        "bar_confirmed": item.bar_confirmed,
        "no_lookahead_safe": item.no_lookahead_safe,
    }


def _execution_identity(
    *,
    lineage: Mapping[str, object],
    intent: OrderIntent,
    entry_timestamp_ms: int | None,
    exit_timestamp_ms: int | None,
    exit_reason: str,
) -> dict[str, str]:
    candidate_id = str(lineage.get("candidate_id") or "")
    event_id = str(lineage.get("event_id") or candidate_id)
    trade_seed = "|".join(
        (
            intent.strategy_name,
            intent.strategy_version,
            intent.symbol,
            intent.venue,
            intent.setup_type,
            intent.direction,
            event_id,
            candidate_id,
            str(entry_timestamp_ms),
        )
    )
    trade_id = f"trade_{candidate_id}_{_stable_token(trade_seed)}"
    execution_seed = "|".join((trade_id, str(exit_timestamp_ms), exit_reason))
    execution_id = f"exec_{_stable_token(execution_seed)}"
    return {
        "candidate_id": candidate_id,
        "event_id": event_id,
        "trade_id": trade_id,
        "execution_id": execution_id,
    }


def _lineage_value(
    direct_value: object,
    explanation_payload: Mapping[str, object],
    price_action_evidence: Mapping[str, object],
    key: str,
) -> object:
    if direct_value not in (None, ""):
        return direct_value
    value = explanation_payload.get(key)
    if value not in (None, ""):
        return value
    return price_action_evidence.get(key)


def _stable_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _should_time_cut_momentum_failure(
    *,
    intent: OrderIntent,
    candles: Sequence[object],
    bar_index: int,
    config: BacktestExecutionConfig,
) -> bool:
    if config.reversal_time_cut_bars <= 0 or bar_index < config.reversal_time_cut_bars:
        return False
    if intent.stop_distance <= 0:
        return False
    return _mfe_r(intent, candles) < config.reversal_time_cut_min_mfe_r


def _mfe_r(intent: OrderIntent, candles: Sequence[object]) -> float:
    favorable = 0.0
    for candle in candles:
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        if intent.direction == "LONG":
            favorable = max(favorable, high - intent.entry_price)
        elif intent.direction == "SHORT":
            favorable = max(favorable, intent.entry_price - low)
    return max(0.0, favorable) / intent.stop_distance


def _true_breakeven_stop(
    *,
    intent: OrderIntent,
    remaining_quantity: float,
    config: BacktestExecutionConfig,
) -> float:
    if remaining_quantity <= 0:
        raise ValueError("remaining_quantity must be greater than 0")

    costs = _estimate_cost(intent.entry_price, intent.entry_price, remaining_quantity, config)
    adjustment = costs.total / (remaining_quantity * intent.point_value)
    if intent.direction == "LONG":
        return intent.entry_price + adjustment
    if intent.direction == "SHORT":
        return intent.entry_price - adjustment
    raise ValueError(f"Unsupported direction: {intent.direction}")


def _chandelier_stop(
    direction: str,
    candles: Sequence[object],
    *,
    atr: float,
    config: BacktestExecutionConfig,
) -> float:
    period = max(1, config.chandelier_period)
    window = tuple(candles[-period:])
    if direction == "LONG":
        highest_high = max(float(getattr(candle, "high")) for candle in window)
        return highest_high - atr * config.chandelier_atr_multiple
    if direction == "SHORT":
        lowest_low = min(float(getattr(candle, "low")) for candle in window)
        return lowest_low + atr * config.chandelier_atr_multiple
    raise ValueError(f"Unsupported direction: {direction}")


def _tighten_stop(direction: str, current_stop: float, candidate_stop: float) -> float:
    if direction == "LONG":
        return max(current_stop, candidate_stop)
    if direction == "SHORT":
        return min(current_stop, candidate_stop)
    raise ValueError(f"Unsupported direction: {direction}")


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
        expected_slippage=abs(config.slippage * point_quantity * 2.0)
        + (entry_notional + exit_notional) * config.spread_slippage_rate,
        funding=abs(config.funding * point_quantity),
    )


def _fill_diagnostics(
    *,
    intent: OrderIntent,
    candles: Sequence[object],
    holding_bars: int,
    exit_reason: str,
    exit_events: tuple[BacktestExitEvent, ...],
    same_bar_ambiguous: bool = False,
    stop_and_target_touched_same_bar: bool = False,
    entry_and_exit_same_bar: bool = False,
    forced_pessimistic_exit: bool = False,
) -> dict[str, object]:
    window = tuple(candles[:holding_bars])
    if not window or intent.stop_distance <= 0:
        return {}

    adverse: list[float] = []
    favorable: list[float] = []
    r_path: list[float] = []
    for candle in window:
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        close = float(getattr(candle, "close"))
        if intent.direction == "LONG":
            adverse.append(max(0.0, intent.entry_price - low))
            favorable.append(max(0.0, high - intent.entry_price))
            r_path.append((close - intent.entry_price) / intent.stop_distance)
        else:
            adverse.append(max(0.0, high - intent.entry_price))
            favorable.append(max(0.0, intent.entry_price - low))
            r_path.append((intent.entry_price - close) / intent.stop_distance)

    mae = max(adverse, default=0.0)
    mfe = max(favorable, default=0.0)
    bars_to_mae = adverse.index(mae) + 1 if adverse else 0
    bars_to_mfe = favorable.index(mfe) + 1 if favorable else 0
    mae_r = mae / intent.stop_distance
    mfe_r = mfe / intent.stop_distance
    partial_hit = any(event.event_type == "partial_take_profit" for event in exit_events)
    breakeven_hit = any(event.event_type == "breakeven_stop" for event in exit_events)
    moved_to_breakeven = partial_hit or breakeven_hit
    return {
        "mae": mae,
        "mfe": mfe,
        "mae_r": mae_r,
        "mfe_r": mfe_r,
        "bars_to_mae": bars_to_mae,
        "bars_to_mfe": bars_to_mfe,
        "r_path_after_entry": tuple(r_path),
        "max_favorable_drawdown_ratio": 0.0 if mfe <= 0 else max(0.0, mfe - max(r_path, default=0.0) * intent.stop_distance) / mfe,
        "stop_efficiency_ratio": 0.0 if mae <= 0 else min(mae / intent.stop_distance, 1.0),
        "trade_excursion_asymmetry": 0.0 if mae <= 0 else mfe / mae,
        "exit_bar_index": holding_bars,
        "reached_1r": mfe_r >= 1.0,
        "reached_1_5r": mfe_r >= 1.5,
        "reached_2r": mfe_r >= 2.0,
        "moved_to_breakeven": moved_to_breakeven,
        "breakeven_hit": breakeven_hit,
        "partial_take_profit_hit": partial_hit,
        "same_bar_ambiguous": same_bar_ambiguous,
        "same_bar_resolution": "stop_first" if same_bar_ambiguous else "",
        "intrabar_scan_available": False,
        "intrabar_scan_used": False,
        "stop_and_target_touched_same_bar": stop_and_target_touched_same_bar,
        "entry_and_exit_same_bar": entry_and_exit_same_bar,
        "forced_pessimistic_exit": forced_pessimistic_exit,
    }


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
    "BacktestExitEvent",
    "BacktestFillResult",
    "EquityPoint",
    "BacktestSummary",
    "BacktestRunResult",
    "SignalOrderAdapter",
    "BacktestExecutionEngine",
    "simulate_approved_fill",
)
