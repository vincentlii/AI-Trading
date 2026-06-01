from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from trading_system.backtest.execution import (
    BacktestExecutionEngine,
    BacktestRunResult,
    BacktestSignalInput,
)
from trading_system.strategies.base import Strategy, StrategyContext, StrategySignal
from trading_system.timeframe_profiles import get_profile
from trading_system.data.universe import timeframe_to_okx_bar


class CandleStore(Protocol):
    def list_candles(self, inst_id: str, bar: str): ...


@dataclass(frozen=True)
class BacktestScanTarget:
    canonical_symbol: str
    inst_id: str
    venue: str = "okx"
    inst_type: str = "SPOT"


@dataclass(frozen=True)
class BacktestScanConfig:
    targets: tuple[BacktestScanTarget, ...]
    profile_keys: tuple[str, ...] = ("B", "C", "A")
    start_ms: int | None = None
    end_ms: int | None = None
    max_entry_windows: int | None = None
    max_context_bars_by_timeframe: Mapping[str, int] = field(default_factory=dict)
    position_aware: bool = False


@dataclass(frozen=True)
class BacktestProfileScan:
    target: BacktestScanTarget
    profile_key: str
    status: str
    reason_codes: tuple[str, ...]
    candle_counts_by_timeframe: Mapping[str, int]
    signal_count: int
    result: BacktestRunResult
    suppressed_overlap_count: int = 0


@dataclass(frozen=True)
class BacktestScanGroupSummary:
    symbol: str
    venue: str
    timeframe_group: str
    strategy_name: str
    strategy_version: str
    strategy_family: str
    setup_type: str
    signal_count: int
    approved_count: int
    rejected_count: int
    trade_count: int
    net_profit: float
    gross_profit: float
    gross_loss: float
    total_cost: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    profit_factor: float
    expectancy_per_trade: float
    average_holding_bars: float
    fee_to_gross_profit_ratio: float
    direction: str = ""
    inst_type: str = ""
    inst_id: str = ""
    contract_mode: str = "spot"
    allow_short: bool = False
    long_trades: int = 0
    short_trades: int = 0
    long_expectancy_R: float = 0.0
    short_expectancy_R: float = 0.0


@dataclass(frozen=True)
class BacktestScanResult:
    profile_runs: tuple[BacktestProfileScan, ...]
    group_summaries: tuple[BacktestScanGroupSummary, ...]


class BacktestRollingScanner:
    def __init__(
        self,
        *,
        repository: CandleStore,
        strategy: Strategy,
        execution_engine: BacktestExecutionEngine,
        config: BacktestScanConfig,
    ):
        self.repository = repository
        self.strategy = strategy
        self.execution_engine = execution_engine
        self.config = config

    def scan(self) -> BacktestScanResult:
        profile_runs: list[BacktestProfileScan] = []

        for target in self.config.targets:
            for profile_key in self.config.profile_keys:
                profile_runs.append(self._scan_target_profile(target, profile_key))

        return BacktestScanResult(
            profile_runs=tuple(profile_runs),
            group_summaries=_build_group_summaries(profile_runs),
        )

    def _scan_target_profile(self, target: BacktestScanTarget, profile_key: str) -> BacktestProfileScan:
        try:
            profile = get_profile(profile_key)
        except KeyError:
            empty_result = self.execution_engine.run(())
            return BacktestProfileScan(
                target=target,
                profile_key=profile_key,
                status="skipped",
                reason_codes=("unknown_profile",),
                candle_counts_by_timeframe={},
                signal_count=0,
                result=empty_result,
            )

        candles_by_timeframe = {
            profile.entry_timeframe: self._load_timeframe(target, profile.entry_timeframe),
            profile.structure_timeframe: self._load_timeframe(target, profile.structure_timeframe),
            profile.trend_timeframe: self._load_timeframe(target, profile.trend_timeframe),
        }
        counts = {timeframe: len(candles) for timeframe, candles in candles_by_timeframe.items()}
        missing = tuple(f"missing_candles:{timeframe}" for timeframe, candles in candles_by_timeframe.items() if not candles)
        if missing:
            return BacktestProfileScan(
                target=target,
                profile_key=profile.key,
                status="skipped",
                reason_codes=missing,
                candle_counts_by_timeframe=counts,
                signal_count=0,
                result=self.execution_engine.run(()),
            )

        entry_candles = candles_by_timeframe[profile.entry_timeframe]
        inputs: list[BacktestSignalInput] = []
        active_until_by_key: dict[tuple[str, str, str, str], int | None] = {}
        suppressed_overlap_count = 0
        max_holding_bars = self.execution_engine.config.max_holding_bars

        start_index = 0
        if self.config.max_entry_windows is not None and self.config.max_entry_windows > 0:
            start_index = max(0, len(entry_candles) - self.config.max_entry_windows - 1)

        for index in range(start_index, max(0, len(entry_candles) - 1)):
            signal_timestamp_ms = int(getattr(entry_candles[index], "timestamp_ms"))
            context = StrategyContext(
                symbol=target.canonical_symbol,
                venue=target.venue,
                timeframe_group=profile.key,
                candles_by_timeframe={
                    profile.entry_timeframe: self._trim_context(
                        profile.entry_timeframe,
                        entry_candles[: index + 1],
                    ),
                    profile.structure_timeframe: self._trim_context(
                        profile.structure_timeframe,
                        _candles_until(candles_by_timeframe[profile.structure_timeframe], signal_timestamp_ms),
                    ),
                    profile.trend_timeframe: self._trim_context(
                        profile.trend_timeframe,
                        _candles_until(candles_by_timeframe[profile.trend_timeframe], signal_timestamp_ms),
                    ),
                },
            )
            if any(not candles for candles in context.candles_by_timeframe.values()):
                continue

            execution_candles = tuple(entry_candles[index + 1 : index + 1 + max_holding_bars])
            if not execution_candles:
                continue

            for signal in self.strategy.generate_signals(context):
                input_item = BacktestSignalInput(signal=signal, execution_candles=execution_candles)
                if self.config.position_aware and _overlaps_active_position(
                    signal,
                    input_item,
                    active_until_by_key,
                ):
                    suppressed_overlap_count += 1
                    continue
                inputs.append(input_item)
                if self.config.position_aware:
                    _record_active_position_until(
                        signal,
                        input_item,
                        self.execution_engine,
                        active_until_by_key,
                    )

        return BacktestProfileScan(
            target=target,
            profile_key=profile.key,
            status="completed",
            reason_codes=(),
            candle_counts_by_timeframe=counts,
            signal_count=len(inputs),
            result=self.execution_engine.run(inputs),
            suppressed_overlap_count=suppressed_overlap_count,
        )

    def _load_timeframe(self, target: BacktestScanTarget, timeframe: str) -> tuple[object, ...]:
        bar = timeframe_to_okx_bar(timeframe)
        if hasattr(self.repository, "load_range"):
            start_ms = 0 if self.config.start_ms is None else self.config.start_ms
            end_ms = 9_223_372_036_854_775_807 if self.config.end_ms is None else self.config.end_ms
            return tuple(
                self.repository.load_range(
                    target.inst_id,
                    bar,
                    start_ms,
                    end_ms,
                    venue=target.venue,
                    inst_type=target.inst_type,
                    confirmed_only=True,
                )
            )

        candles = _list_repository_candles(self.repository, target, bar)
        return tuple(
            candle
            for candle in candles
            if _is_confirmed(candle)
            and (self.config.start_ms is None or int(getattr(candle, "timestamp_ms")) >= self.config.start_ms)
            and (self.config.end_ms is None or int(getattr(candle, "timestamp_ms")) <= self.config.end_ms)
        )

    def _trim_context(self, timeframe: str, candles: Sequence[object]) -> tuple[object, ...]:
        limit = self.config.max_context_bars_by_timeframe.get(timeframe)
        if limit is None or limit <= 0:
            return tuple(candles)
        return tuple(candles[-limit:])


def infer_strategy_family(signal: StrategySignal) -> str:
    value = signal.explanation_payload.get("strategy_family")
    if isinstance(value, str) and value:
        return value

    fallback = {
        "liquidity_reversal": "liquidity_sweep_reclaim",
        "trend_continuation": "breakout_pullback_continuation",
    }
    return fallback.get(signal.setup_type, signal.setup_type)


def _list_repository_candles(repository: CandleStore, target: BacktestScanTarget, bar: str) -> tuple[object, ...]:
    try:
        return tuple(repository.list_candles(target.inst_id, bar, venue=target.venue, inst_type=target.inst_type))
    except TypeError:
        return tuple(repository.list_candles(target.inst_id, bar))


def _candles_until(candles: Sequence[object], timestamp_ms: int) -> tuple[object, ...]:
    return tuple(candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms)


def _is_confirmed(candle: object) -> bool:
    return bool(getattr(candle, "is_confirmed", False))


def _build_group_summaries(profile_runs: Sequence[BacktestProfileScan]) -> tuple[BacktestScanGroupSummary, ...]:
    signal_counts: dict[tuple[str, ...], int] = defaultdict(int)
    approved_counts: dict[tuple[str, ...], int] = defaultdict(int)
    rejected_counts: dict[tuple[str, ...], int] = defaultdict(int)
    fills_by_key: dict[tuple[str, ...], list[object]] = defaultdict(list)
    initial_equity_by_key: dict[tuple[str, ...], float] = {}

    for run in profile_runs:
        approved_decisions = []
        for decision in run.result.decisions:
            key = _group_key(decision.signal, run)
            signal_counts[key] += 1
            if decision.status == "approved":
                approved_counts[key] += 1
                approved_decisions.append(decision)
            else:
                rejected_counts[key] += 1

        for decision, fill in zip(approved_decisions, run.result.fills):
            key = _group_key(decision.signal, run)
            fills_by_key[key].append(fill)
            if key not in initial_equity_by_key and run.result.equity_curve:
                initial_equity_by_key[key] = float(run.result.equity_curve[0].equity)

    summaries: list[BacktestScanGroupSummary] = []
    for key in sorted(signal_counts):
        fills = tuple(fills_by_key.get(key, ()))
        stats = _group_fill_stats(fills, initial_equity_by_key.get(key, 0.0))
        summaries.append(
            BacktestScanGroupSummary(
                symbol=key[0],
                venue=key[1],
                timeframe_group=key[2],
                strategy_name=key[3],
                strategy_version=key[4],
                strategy_family=key[5],
                setup_type=key[6],
                direction=key[7],
                inst_type=key[8],
                inst_id=key[9],
                contract_mode="usdt_swap" if key[8] == "SWAP" else "spot",
                allow_short=key[8] == "SWAP",
                signal_count=signal_counts[key],
                approved_count=approved_counts[key],
                rejected_count=rejected_counts[key],
                trade_count=len(fills),
                **stats,
            )
        )
    return tuple(summaries)


def _group_key(signal: StrategySignal, run: BacktestProfileScan) -> tuple[str, ...]:
    return (
        signal.symbol,
        signal.venue,
        signal.timeframe_group,
        signal.strategy_name,
        signal.strategy_version,
        infer_strategy_family(signal),
        signal.setup_type,
        signal.direction,
        run.target.inst_type,
        run.target.inst_id,
    )


def _position_key(signal: StrategySignal) -> tuple[str, str, str, str]:
    return (
        signal.symbol,
        signal.strategy_name,
        signal.strategy_version,
        signal.setup_type,
    )


def _overlaps_active_position(
    signal: StrategySignal,
    input_item: BacktestSignalInput,
    active_until_by_key: Mapping[tuple[str, str, str, str], int | None],
) -> bool:
    active_until = active_until_by_key.get(_position_key(signal))
    entry_timestamp = _first_timestamp(input_item.execution_candles)
    if active_until is None or entry_timestamp is None:
        return False
    return entry_timestamp <= active_until


def _record_active_position_until(
    signal: StrategySignal,
    input_item: BacktestSignalInput,
    execution_engine: BacktestExecutionEngine,
    active_until_by_key: dict[tuple[str, str, str, str], int | None],
) -> None:
    result = execution_engine.run((input_item,))
    if not result.fills:
        return
    active_until_by_key[_position_key(signal)] = result.fills[0].exit_timestamp_ms


def _first_timestamp(candles: Sequence[object]) -> int | None:
    if not candles:
        return None
    return int(getattr(candles[0], "timestamp_ms"))


def _group_fill_stats(fills: Sequence[object], initial_equity: float) -> dict[str, float]:
    if not fills:
        return {
            "net_profit": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "total_cost": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "profit_factor": 0.0,
            "expectancy_per_trade": 0.0,
            "average_holding_bars": 0.0,
            "fee_to_gross_profit_ratio": 0.0,
            "long_trades": 0,
            "short_trades": 0,
            "long_expectancy_R": 0.0,
            "short_expectancy_R": 0.0,
        }

    net_values = [float(fill.net_pnl) for fill in fills]
    gross_values = [float(fill.gross_pnl) for fill in fills]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    gross_profit = sum(max(value, 0.0) for value in gross_values)
    gross_loss = sum(min(value, 0.0) for value in gross_values)
    total_cost = sum(float(fill.cost_estimate.total) for fill in fills)
    average_win = sum(wins) / len(wins) if wins else 0.0
    average_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    long_fills = [fill for fill in fills if fill.order.intent.direction == "LONG"]
    short_fills = [fill for fill in fills if fill.order.intent.direction == "SHORT"]
    return {
        "net_profit": sum(net_values),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_cost": total_cost,
        "max_drawdown": _max_drawdown(fills, initial_equity),
        "win_rate": len(wins) / len(fills),
        "profit_loss_ratio": 0.0 if average_loss == 0 else average_win / average_loss,
        "profit_factor": _profit_factor(gross_profit, gross_loss),
        "expectancy_per_trade": sum(net_values) / len(fills),
        "average_holding_bars": sum(int(fill.holding_bars) for fill in fills) / len(fills),
        "fee_to_gross_profit_ratio": 0.0 if gross_profit <= 0 else total_cost / gross_profit,
        "long_trades": len(long_fills),
        "short_trades": len(short_fills),
        "long_expectancy_R": _average_r(long_fills),
        "short_expectancy_R": _average_r(short_fills),
    }


def _max_drawdown(fills: Sequence[object], initial_equity: float) -> float:
    if initial_equity <= 0:
        return 0.0
    equity = initial_equity
    high_water_mark = initial_equity
    max_drawdown = 0.0
    for fill in fills:
        equity += float(fill.net_pnl)
        high_water_mark = max(high_water_mark, equity)
        if high_water_mark > 0:
            max_drawdown = max(max_drawdown, (high_water_mark - equity) / high_water_mark)
    return max_drawdown


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_profit <= 0:
        return 0.0
    if gross_loss == 0:
        return math.inf
    return gross_profit / abs(gross_loss)


def _average_r(fills: Sequence[object]) -> float:
    if not fills:
        return 0.0
    return sum(float(fill.r_multiple) for fill in fills) / len(fills)


__all__ = (
    "BacktestRollingScanner",
    "BacktestScanConfig",
    "BacktestScanGroupSummary",
    "BacktestScanResult",
    "BacktestScanTarget",
    "BacktestProfileScan",
    "infer_strategy_family",
)
