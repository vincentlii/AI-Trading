from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Sequence

from trading_system.backtest.execution import BacktestExecutionEngine
from trading_system.backtest.risk import RiskEngine
from trading_system.backtest.scanner import BacktestRollingScanner, BacktestScanGroupSummary, BacktestScanResult
from trading_system.config.loader import BacktestPresetConfig, RankingConfig
from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal


@dataclass(frozen=True)
class RankedBacktestGroup:
    rank: int
    status: str
    reason_codes: tuple[str, ...]
    score: float
    summary: BacktestScanGroupSummary


@dataclass(frozen=True)
class BacktestBatchReport:
    config_version: str
    config_fingerprint: str
    scan_result: BacktestScanResult
    ranked_groups: tuple[RankedBacktestGroup, ...]

    def to_rows(self) -> tuple[dict[str, object], ...]:
        rows: list[dict[str, object]] = []
        for item in self.ranked_groups:
            row = asdict(item.summary)
            row.update(
                {
                    "rank": item.rank,
                    "status": item.status,
                    "reason_codes": item.reason_codes,
                    "score": item.score,
                    "config_version": self.config_version,
                    "config_fingerprint": self.config_fingerprint,
                }
            )
            rows.append(row)
        return tuple(rows)


class BacktestBatchRunner:
    def __init__(
        self,
        *,
        repository,
        preset: BacktestPresetConfig,
        strategy: Strategy,
    ):
        self.repository = repository
        self.preset = preset
        self.strategy = strategy

    def run(self) -> BacktestBatchReport:
        strategy = _ConfiguredStrategy(self.strategy, self.preset)
        execution_engine = BacktestExecutionEngine(
            risk_engine=RiskEngine(self.preset.to_risk_parameters()),
            config=self.preset.to_execution_config(),
        )
        scanner = BacktestRollingScanner(
            repository=self.repository,
            strategy=strategy,
            execution_engine=execution_engine,
            config=self.preset.to_scan_config(),
        )
        scan_result = scanner.scan()
        ranked_groups = rank_scan_groups(scan_result.group_summaries, self.preset.ranking)
        return BacktestBatchReport(
            config_version=self.preset.config_version,
            config_fingerprint=self.preset.config_fingerprint,
            scan_result=scan_result,
            ranked_groups=ranked_groups,
        )


def rank_scan_groups(
    summaries: Sequence[BacktestScanGroupSummary],
    ranking: RankingConfig,
) -> tuple[RankedBacktestGroup, ...]:
    ranked: list[RankedBacktestGroup] = []
    for summary in summaries:
        status, reason_codes = _evaluate_summary(summary, ranking)
        ranked.append(
            RankedBacktestGroup(
                rank=0,
                status=status,
                reason_codes=reason_codes,
                score=_score_summary(summary),
                summary=summary,
            )
        )

    status_order = {"candidate": 0, "supporting_only": 1, "rejected": 2}
    ranked.sort(
        key=lambda item: (
            status_order[item.status],
            -item.score,
            item.summary.symbol,
            item.summary.timeframe_group,
            item.summary.strategy_family,
            item.summary.setup_type,
        )
    )
    return tuple(
        RankedBacktestGroup(
            rank=index,
            status=item.status,
            reason_codes=item.reason_codes,
            score=item.score,
            summary=item.summary,
        )
        for index, item in enumerate(ranked, start=1)
    )


def _evaluate_summary(summary: BacktestScanGroupSummary, ranking: RankingConfig) -> tuple[str, tuple[str, ...]]:
    if (
        summary.timeframe_group == "A"
        and summary.fee_to_gross_profit_ratio > ranking.fast_profile_fee_reject_threshold
    ):
        return "rejected", ("fast_profile_fee_ratio_above_threshold",)
    if summary.timeframe_group == "C" and summary.trade_count < ranking.min_trades_for_primary:
        return "supporting_only", ("sample_below_minimum",)
    return "candidate", ()


def _score_summary(summary: BacktestScanGroupSummary) -> float:
    drawdown = summary.max_drawdown if summary.max_drawdown > 0 else 0.01
    profit_factor = 0.0 if math.isinf(summary.profit_factor) else max(summary.profit_factor, 0.0)
    expectancy = max(summary.expectancy_per_trade, 0.0)
    return (summary.net_profit / drawdown) + (profit_factor * 100.0) + expectancy


class _ConfiguredStrategy(Strategy):
    def __init__(self, strategy: Strategy, preset: BacktestPresetConfig):
        self.strategy = strategy
        self.preset = preset
        if strategy.metadata.name != preset.strategy.name or strategy.metadata.version != preset.strategy.version:
            raise ValueError(
                "preset strategy does not match runner strategy: "
                f"{preset.strategy.name}@{preset.strategy.version} != "
                f"{strategy.metadata.name}@{strategy.metadata.version}"
            )

    @property
    def metadata(self) -> StrategyMetadata:
        return self.strategy.metadata

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        if not self.preset.strategy.enabled:
            return ()
        enabled_setups = set(self.preset.strategy.enabled_setups)
        return tuple(
            signal
            for signal in self.strategy.generate_signals(context)
            if signal.setup_type in enabled_setups
        )


__all__ = (
    "BacktestBatchReport",
    "BacktestBatchRunner",
    "RankedBacktestGroup",
    "rank_scan_groups",
)
