import unittest
from dataclasses import replace
from pathlib import Path

from trading_system.backtest.batch import BacktestBatchRunner, rank_scan_groups
from trading_system.backtest.scanner import BacktestScanGroupSummary
from trading_system.config import RankingConfig, StrategyConfig, load_backtest_preset
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal
from trading_system.timeframe_profiles import get_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"


def _candle(index: int, open_price: float, high: float, low: float, close: float) -> Candle:
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


def _repository_with_btc_eth_abc_data() -> CandleRepository:
    repository = CandleRepository()
    candles = (
        _candle(1, 100.0, 104.0, 99.0, 102.0),
        _candle(2, 102.0, 105.0, 100.0, 104.0),
        _candle(3, 104.0, 106.0, 101.0, 105.0),
        _candle(4, 100.0, 112.0, 99.0, 111.0),
    )
    for inst_id in ("BTC-USDT", "ETH-USDT"):
        for bar in ("5m", "15m", "1H", "4H", "1D"):
            repository.save_many(inst_id, bar, candles)
    return repository


class OneSignalPerProfileStrategy(Strategy):
    metadata = StrategyMetadata(
        name="trend_price_volume",
        version="v1",
        description="Test P4.4 batch strategy.",
        required_timeframe_profile_keys=("A", "B", "C"),
        required_indicators=(),
        documentation_path="",
        supported_symbols=("BTC/USDT", "ETH/USDT"),
        setup_types=("trend_continuation",),
    )

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        profile = get_profile(context.timeframe_group)
        entry = tuple(context.candles_by_timeframe[profile.entry_timeframe])
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
                price_action_evidence={},
                volume_price_evidence={"status": "confirm"},
                risk_profile={},
                explanation_payload={"strategy_family": "breakout_pullback_continuation"},
            ),
        )


class BacktestBatchTests(unittest.TestCase):
    def test_runner_uses_preset_to_scan_btc_eth_abc_and_output_p4_4_rows(self):
        preset = load_backtest_preset(PRESET_PATH)
        runner = BacktestBatchRunner(
            repository=_repository_with_btc_eth_abc_data(),
            preset=preset,
            strategy=OneSignalPerProfileStrategy(),
        )

        report = runner.run()

        self.assertEqual(report.config_version, preset.config_version)
        self.assertEqual(report.config_fingerprint, preset.config_fingerprint)
        self.assertEqual(len(report.scan_result.profile_runs), 6)
        self.assertEqual({run.target.canonical_symbol for run in report.scan_result.profile_runs}, {"BTC/USDT", "ETH/USDT"})
        self.assertEqual({run.profile_key for run in report.scan_result.profile_runs}, {"A", "B", "C"})

        rows = report.to_rows()
        self.assertEqual(len(rows), 6)
        self.assertEqual({row["symbol"] for row in rows}, {"BTC/USDT", "ETH/USDT"})
        self.assertEqual({row["timeframe_group"] for row in rows}, {"A", "B", "C"})
        self.assertTrue(all(row["config_version"] == preset.config_version for row in rows))
        self.assertTrue(all(row["config_fingerprint"] == preset.config_fingerprint for row in rows))

        b_row = next(row for row in rows if row["symbol"] == "BTC/USDT" and row["timeframe_group"] == "B")
        self.assertEqual(b_row["strategy_family"], "breakout_pullback_continuation")
        self.assertEqual(b_row["setup_type"], "trend_continuation")
        self.assertEqual(b_row["status"], "candidate")
        self.assertGreater(b_row["net_profit"], 0.0)
        self.assertGreaterEqual(b_row["max_drawdown"], 0.0)
        self.assertGreater(b_row["win_rate"], 0.0)
        self.assertGreaterEqual(b_row["profit_loss_ratio"], 0.0)
        self.assertGreater(b_row["profit_factor"], 0.0)
        self.assertGreater(b_row["average_holding_bars"], 0.0)
        self.assertGreater(b_row["expectancy_per_trade"], 0.0)
        self.assertGreaterEqual(b_row["fee_to_gross_profit_ratio"], 0.0)

    def test_ranking_marks_fast_profile_fee_rejection_and_low_sample_supporting_only(self):
        ranking = RankingConfig(fast_profile_fee_reject_threshold=0.25, min_trades_for_primary=30)
        ranked = rank_scan_groups(
            (
                _summary(timeframe_group="A", trade_count=40, fee_to_gross_profit_ratio=0.31, net_profit=500.0),
                _summary(timeframe_group="B", trade_count=40, fee_to_gross_profit_ratio=0.05, net_profit=700.0),
                _summary(timeframe_group="C", trade_count=10, fee_to_gross_profit_ratio=0.05, net_profit=900.0),
            ),
            ranking,
        )

        by_profile = {item.summary.timeframe_group: item for item in ranked}

        self.assertEqual(by_profile["B"].rank, 1)
        self.assertEqual(by_profile["B"].status, "candidate")
        self.assertEqual(by_profile["A"].status, "rejected")
        self.assertIn("fast_profile_fee_ratio_above_threshold", by_profile["A"].reason_codes)
        self.assertEqual(by_profile["C"].status, "supporting_only")
        self.assertIn("sample_below_minimum", by_profile["C"].reason_codes)

    def test_runner_respects_enabled_setup_filter_from_preset(self):
        preset = load_backtest_preset(PRESET_PATH)
        preset = replace(
            preset,
            strategy=StrategyConfig(
                name="trend_price_volume",
                version="v1",
                enabled=True,
                enabled_setups=("liquidity_reversal",),
            ),
        )
        runner = BacktestBatchRunner(
            repository=_repository_with_btc_eth_abc_data(),
            preset=preset,
            strategy=OneSignalPerProfileStrategy(),
        )

        report = runner.run()

        self.assertEqual(report.to_rows(), ())


def _summary(
    *,
    timeframe_group: str,
    trade_count: int,
    fee_to_gross_profit_ratio: float,
    net_profit: float,
) -> BacktestScanGroupSummary:
    return BacktestScanGroupSummary(
        symbol="BTC/USDT",
        venue="okx",
        timeframe_group=timeframe_group,
        strategy_name="trend_price_volume",
        strategy_version="v1",
        strategy_family="breakout_pullback_continuation",
        setup_type="trend_continuation",
        signal_count=trade_count,
        approved_count=trade_count,
        rejected_count=0,
        trade_count=trade_count,
        net_profit=net_profit,
        gross_profit=1000.0,
        gross_loss=-300.0,
        total_cost=1000.0 * fee_to_gross_profit_ratio,
        max_drawdown=0.02,
        win_rate=0.6,
        profit_loss_ratio=1.5,
        profit_factor=3.0,
        expectancy_per_trade=net_profit / trade_count,
        average_holding_bars=5.0,
        fee_to_gross_profit_ratio=fee_to_gross_profit_ratio,
    )


if __name__ == "__main__":
    unittest.main()
