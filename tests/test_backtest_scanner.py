import unittest

from trading_system.backtest.execution import BacktestExecutionConfig, BacktestExecutionEngine
from trading_system.backtest.risk import RiskEngine, RiskParameters
from trading_system.backtest.scanner import (
    BacktestRollingScanner,
    BacktestScanConfig,
    BacktestScanTarget,
    infer_strategy_family,
)
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal


def candle(index: int, open_price: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


class OneSignalStrategy(Strategy):
    metadata = StrategyMetadata(
        name="test_strategy",
        version="v1",
        description="Test scanner strategy.",
        required_timeframe_profile_keys=("B",),
        required_indicators=(),
        documentation_path="",
        supported_symbols=("BTC/USDT",),
        setup_types=("trend_continuation",),
    )

    def __init__(self):
        self.contexts: list[StrategyContext] = []

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        self.contexts.append(context)
        entry = context.candles_by_timeframe["15m"]
        structure = context.candles_by_timeframe["1h"]
        trend = context.candles_by_timeframe["4h"]
        latest_ts = entry[-1].timestamp_ms
        assert max(candle.timestamp_ms for candle in structure) <= latest_ts
        assert max(candle.timestamp_ms for candle in trend) <= latest_ts
        if len(entry) != 3:
            return ()
        return (
            StrategySignal(
                strategy_name=self.metadata.name,
                strategy_version=self.metadata.version,
                setup_type="trend_continuation",
                symbol=context.symbol,
                venue=context.venue,
                timeframe_group=context.timeframe_group,
                direction="long",
                entry_zone={"low": 99.0, "high": 101.0},
                invalidation_level=95.0,
                target_hint={"target_price": 110.0},
                trend_evidence={"atr": 3.0},
                explanation_payload={"strategy_family": "breakout_pullback_continuation"},
            ),
        )


def repository_with_profile_b_data() -> CandleRepository:
    repository = CandleRepository()
    repository.save_many(
        "BTC-USDT",
        "15m",
        (
            candle(1, 100.0, 104.0, 99.0, 102.0),
            candle(2, 102.0, 105.0, 100.0, 104.0),
            candle(3, 104.0, 106.0, 101.0, 105.0),
            candle(4, 100.0, 111.0, 99.0, 110.0),
        ),
    )
    repository.save_many("BTC-USDT", "1H", tuple(candle(index, 100.0, 103.0, 98.0, 101.0) for index in (1, 2, 3)))
    repository.save_many("BTC-USDT", "4H", tuple(candle(index, 100.0, 103.0, 98.0, 101.0) for index in (1, 2, 3)))
    return repository


class BacktestRollingScannerTests(unittest.TestCase):
    def scanner(self, repository: CandleRepository, strategy: Strategy):
        execution_engine = BacktestExecutionEngine(
            risk_engine=RiskEngine(RiskParameters()),
            config=BacktestExecutionConfig(max_holding_bars=2),
        )
        return BacktestRollingScanner(
            repository=repository,
            strategy=strategy,
            execution_engine=execution_engine,
            config=BacktestScanConfig(
                targets=(BacktestScanTarget(canonical_symbol="BTC/USDT", inst_id="BTC-USDT"),),
                profile_keys=("B",),
            ),
        )

    def test_scans_rolling_contexts_and_executes_signal_on_next_entry_candle(self):
        strategy = OneSignalStrategy()
        result = self.scanner(repository_with_profile_b_data(), strategy).scan()

        self.assertEqual(len(result.profile_runs), 1)
        run = result.profile_runs[0]
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.signal_count, 1)
        self.assertEqual(run.result.summary.trade_count, 1)
        self.assertEqual(run.result.fills[0].entry_timestamp_ms, candle(4, 0.0, 0.0, 0.0, 0.0).timestamp_ms)
        self.assertEqual(run.result.fills[0].entry_price, 100.0)
        self.assertEqual(run.result.fills[0].exit_reason, "target")
        self.assertGreaterEqual(len(strategy.contexts), 3)

    def test_scan_can_limit_recent_entry_windows_without_changing_default_behavior(self):
        repository = repository_with_profile_b_data()
        strategy = OneSignalStrategy()
        execution_engine = BacktestExecutionEngine(
            risk_engine=RiskEngine(RiskParameters()),
            config=BacktestExecutionConfig(max_holding_bars=2),
        )
        scanner = BacktestRollingScanner(
            repository=repository,
            strategy=strategy,
            execution_engine=execution_engine,
            config=BacktestScanConfig(
                targets=(BacktestScanTarget(canonical_symbol="BTC/USDT", inst_id="BTC-USDT"),),
                profile_keys=("B",),
                max_entry_windows=1,
            ),
        )

        result = scanner.scan()

        self.assertEqual(len(strategy.contexts), 1)
        self.assertEqual(result.profile_runs[0].signal_count, 1)

    def test_group_summaries_are_split_by_symbol_profile_strategy_family_and_setup(self):
        result = self.scanner(repository_with_profile_b_data(), OneSignalStrategy()).scan()

        self.assertEqual(len(result.group_summaries), 1)
        summary = result.group_summaries[0]
        self.assertEqual(summary.symbol, "BTC/USDT")
        self.assertEqual(summary.venue, "okx")
        self.assertEqual(summary.timeframe_group, "B")
        self.assertEqual(summary.strategy_family, "breakout_pullback_continuation")
        self.assertEqual(summary.setup_type, "trend_continuation")
        self.assertEqual(summary.signal_count, 1)
        self.assertEqual(summary.trade_count, 1)
        self.assertGreater(summary.net_profit, 0.0)

    def test_missing_profile_timeframe_is_skipped_without_error(self):
        repository = CandleRepository()
        repository.save_many("BTC-USDT", "15m", (candle(1, 100.0, 101.0, 99.0, 100.0),))

        result = self.scanner(repository, OneSignalStrategy()).scan()

        self.assertEqual(result.profile_runs[0].status, "skipped")
        self.assertIn("missing_candles:1h", result.profile_runs[0].reason_codes)
        self.assertEqual(result.group_summaries, ())

    def test_strategy_family_falls_back_from_setup_type_when_payload_is_missing(self):
        signal = StrategySignal(
            strategy_name="trend_price_volume",
            strategy_version="v1",
            setup_type="liquidity_reversal",
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            direction="long",
        )

        self.assertEqual(infer_strategy_family(signal), "liquidity_sweep_reclaim")


if __name__ == "__main__":
    unittest.main()
