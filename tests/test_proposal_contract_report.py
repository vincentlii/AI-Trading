import unittest
from pathlib import Path

from trading_system.backtest.batch import BacktestBatchRunner
from trading_system.config import load_backtest_preset
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.reports.proposal import build_cost_tier_rows
from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal
from trading_system.timeframe_profiles import get_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SWAP_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_swap_proposal.toml"


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


class LongShortStrategy(Strategy):
    metadata = StrategyMetadata(
        name="trend_price_volume",
        version="v1",
        description="Contract proposal report test strategy.",
        required_timeframe_profile_keys=("B", "C"),
        required_indicators=(),
        documentation_path="",
        supported_symbols=("BTC/USDT", "ETH/USDT"),
        setup_types=("liquidity_reversal",),
    )

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        profile = get_profile(context.timeframe_group)
        entry = tuple(context.candles_by_timeframe[profile.entry_timeframe])
        if len(entry) != 3:
            return ()
        direction = "short" if context.symbol == "ETH/USDT" else "long"
        invalidation = 105.0 if direction == "short" else 95.0
        target = 90.0 if direction == "short" else 110.0
        return (
            StrategySignal(
                strategy_name=self.metadata.name,
                strategy_version=self.metadata.version,
                setup_type="liquidity_reversal",
                symbol=context.symbol,
                venue=context.venue,
                timeframe_group=context.timeframe_group,
                direction=direction,
                entry_zone={"low": 99.0, "high": 101.0},
                invalidation_level=invalidation,
                target_hint={"target_price": target},
                trend_evidence={"atr": 3.0},
                price_action_evidence={},
                volume_price_evidence={"status": "confirm"},
                risk_profile={},
                explanation_payload={"strategy_family": "liquidity_sweep_reclaim"},
            ),
        )


def _repository() -> CandleRepository:
    repository = CandleRepository()
    candles = (
        _candle(1, 100.0, 104.0, 99.0, 102.0),
        _candle(2, 102.0, 105.0, 100.0, 104.0),
        _candle(3, 104.0, 106.0, 101.0, 105.0),
        _candle(4, 100.0, 112.0, 89.0, 101.0),
    )
    for inst_id in ("BTC-USDT-SWAP", "ETH-USDT-SWAP"):
        for bar in ("15m", "1H", "4H", "1D"):
            repository.save_many(inst_id, bar, candles, inst_type="SWAP")
    return repository


class ProposalContractReportTests(unittest.TestCase):
    def test_cost_tier_rows_include_base_stress_harsh_and_direction_breakout(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        rows = build_cost_tier_rows(repository=_repository(), preset=preset, strategy=LongShortStrategy())

        self.assertEqual({row["cost_tier"] for row in rows}, {"base", "stress", "harsh"})
        self.assertTrue(all(row["fee_rate"] == 0.001 for row in rows))
        self.assertTrue(all(row["inst_type"] == "SWAP" for row in rows))
        self.assertTrue(all(row["contract_mode"] == "usdt_swap" for row in rows))
        self.assertTrue(all(row["allow_short"] is True for row in rows))
        self.assertTrue(all(row["funding_mode"] == "static_config_only" for row in rows))
        self.assertTrue(all("expectancy_R" in row for row in rows))
        self.assertTrue(any(row["long_trades"] > 0 for row in rows))
        self.assertTrue(any(row["short_trades"] > 0 for row in rows))

    def test_cost_tier_rows_do_not_lower_fee_rate_below_formal_cost(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        rows = build_cost_tier_rows(repository=_repository(), preset=preset, strategy=LongShortStrategy())

        self.assertGreaterEqual(min(row["fee_rate"] for row in rows), preset.costs.fee_rate)

    def test_cost_tier_rows_can_filter_tiers_and_limit_entry_windows(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        rows = build_cost_tier_rows(
            repository=_repository(),
            preset=preset,
            strategy=LongShortStrategy(),
            cost_tiers=("base",),
            max_entry_windows=1,
        )

        self.assertEqual({row["cost_tier"] for row in rows}, {"base"})
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
