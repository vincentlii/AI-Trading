import unittest

from trading_system.backtest.risk import RiskParameters
from trading_system.config.loader import (
    AssetConfig,
    AssetTargetConfig,
    BacktestPresetConfig,
    CostConfig,
    ExecutionConfig,
    RankingConfig,
    ScanConfig,
    StrategyConfig,
)
from trading_system.data.coverage import CoverageThresholds
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.diagnostics.p6_gate import P6GateConfig, build_failure_attribution_rows, build_p6_gate_report
from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal


def _candle(index: int, interval_ms: int, close: float = 101.0) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * interval_ms,
        open=100.0,
        high=104.0,
        low=99.0,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


class GateSignalStrategy(Strategy):
    metadata = StrategyMetadata(
        name="trend_price_volume",
        version="v1",
        description="P6 gate test strategy.",
        required_timeframe_profile_keys=("B",),
        required_indicators=(),
        documentation_path="",
        supported_symbols=("BTC/USDT",),
        setup_types=("trend_continuation",),
    )

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        entry = context.candles_by_timeframe["15m"]
        if len(entry) < 3:
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
                price_action_evidence={},
                volume_price_evidence={"status": "confirm"},
                risk_profile={},
                explanation_payload={"strategy_family": "breakout_pullback_continuation"},
            ),
        )


def _preset() -> BacktestPresetConfig:
    return BacktestPresetConfig(
        config_version="test",
        config_fingerprint="test",
        assets=AssetConfig(
            universe="btc_eth",
            primary_venue="okx",
            validation_venues=(),
            targets=(AssetTargetConfig("BTC/USDT", "BTC-USDT", "okx", "SPOT"),),
        ),
        risk=RiskParameters(),
        costs=CostConfig("test", fee_rate=0.001, spread=0.0, slippage=0.0, funding=0.0),
        execution=ExecutionConfig(
            initial_equity=100_000.0,
            max_holding_bars=3,
            conservative_same_bar=True,
            point_value=1.0,
            enable_advanced_exits=False,
            partial_take_profit_r=1.0,
            partial_take_profit_pct=0.5,
            move_stop_to_true_breakeven=True,
            chandelier_period=22,
            chandelier_atr_multiple=4.0,
        ),
        scan=ScanConfig(profile_keys=("B",)),
        strategy=StrategyConfig(
            name="trend_price_volume",
            version="v1",
            enabled=True,
            enabled_setups=("trend_continuation",),
        ),
        ranking=RankingConfig(fast_profile_fee_reject_threshold=0.25, min_trades_for_primary=1),
    )


def _repository() -> CandleRepository:
    repository = CandleRepository()
    repository.save_many("BTC-USDT", "15m", tuple(_candle(index, 900_000) for index in range(1, 12)))
    repository.save_many("BTC-USDT", "1H", tuple(_candle(index, 3_600_000) for index in range(-10, 12)))
    repository.save_many("BTC-USDT", "4H", tuple(_candle(index, 14_400_000) for index in range(-10, 12)))
    return repository


class P6GateDiagnosticsTests(unittest.TestCase):
    def test_build_p6_gate_report_combines_coverage_audit_position_aware_and_cost_checks(self):
        report = build_p6_gate_report(
            repository=_repository(),
            preset=_preset(),
            strategy=GateSignalStrategy(),
            config=P6GateConfig(
                coverage_thresholds=CoverageThresholds(runnable=3, diagnostic=3, formal_years=1),
                require_formal_backtest=False,
                max_audit_windows=5,
            ),
        )

        categories = {row.category for row in report.rows}

        self.assertTrue(report.passed)
        self.assertIn("data_coverage", categories)
        self.assertIn("no_lookahead", categories)
        self.assertIn("position_aware", categories)
        self.assertIn("cost_after_r", categories)
        self.assertGreater(report.summary["trade_count"], 0)
        self.assertIsInstance(report.failure_attribution_rows, tuple)

    def test_failure_attribution_classifies_losing_and_cost_drag_trades(self):
        report = build_p6_gate_report(
            repository=_repository(),
            preset=_preset(),
            strategy=GateSignalStrategy(),
            config=P6GateConfig(
                coverage_thresholds=CoverageThresholds(runnable=3, diagnostic=3, formal_years=1),
                require_formal_backtest=False,
                max_audit_windows=5,
            ),
        )

        rows = build_failure_attribution_rows(report.position_aware_report.scan_result)

        self.assertTrue(all("attribution" in row for row in rows))


if __name__ == "__main__":
    unittest.main()
