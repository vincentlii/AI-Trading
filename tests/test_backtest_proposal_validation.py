import unittest
from pathlib import Path

from trading_system.backtest.proposal_validation import validate_parameter_proposal
from trading_system.config import load_backtest_preset
from trading_system.config.proposals import ProposalChange, make_parameter_proposal
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


def _repository_with_abc_data() -> CandleRepository:
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


class OneSignalStrategy(Strategy):
    metadata = StrategyMetadata(
        name="trend_price_volume",
        version="v1",
        description="Test proposal validation strategy.",
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


class BacktestProposalValidationTests(unittest.TestCase):
    def test_validate_parameter_proposal_runs_p4_4_with_in_memory_proposed_preset(self):
        preset = load_backtest_preset(PRESET_PATH)
        proposal = make_parameter_proposal(
            proposal_id="p4_5_validate_min_trades",
            title="Validate higher minimum trade count",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.min_trades_for_primary",
                    before=30,
                    after=40,
                    reason="Test validation entry.",
                ),
            ),
            evidence={"window": "synthetic"},
            expected_impact="No formal config changes; only proposed ranking threshold changes in memory.",
            risks=("May demote slow trend groups.",),
            validation_plan=("Run P4.4 batch validator.",),
        )

        validation = validate_parameter_proposal(
            proposal=proposal,
            base_preset=preset,
            repository=_repository_with_abc_data(),
            strategy=OneSignalStrategy(),
        )

        self.assertEqual(validation.proposal_id, proposal.proposal_id)
        self.assertEqual(validation.status, "validated")
        self.assertFalse(validation.auto_apply)
        self.assertEqual(validation.base_config_fingerprint, preset.config_fingerprint)
        self.assertNotEqual(validation.proposed_config_fingerprint, preset.config_fingerprint)
        self.assertEqual(validation.proposed_report.config_fingerprint, validation.proposed_config_fingerprint)
        self.assertGreater(len(validation.proposed_report.to_rows()), 0)


if __name__ == "__main__":
    unittest.main()
