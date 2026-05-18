from __future__ import annotations

from pathlib import Path

from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal
from trading_system.timeframe_profiles import get_profile
from trading_system.strategies.trend_price_volume_v1.features import (
    build_market_regime,
    confirm_volume_price,
    detect_price_action_setup,
    minimum_reward_to_risk,
    strategy_parameters_from_context,
)


class TrendPriceVolumeStrategy(Strategy):
    metadata = StrategyMetadata(
        name="trend_price_volume",
        version="v1",
        description="Initial strategy plugin: trend regime, price action structure, volume-price confirmation, and risk gating.",
        required_timeframe_profile_keys=("A", "B", "C"),
        required_indicators=(
            "regime.trend_state",
            "regime.ema",
            "regime.atr",
            "regime.adx_dmi",
            "regime.ttm_squeeze",
            "price_action.structure",
            "volume_price.confirmation",
        ),
        documentation_path=str(Path(__file__).with_name("strategy.md")),
        supported_symbols=("BTC/USDT", "ETH/USDT", "XAUT/USDT"),
        setup_types=("trend_continuation", "liquidity_reversal"),
    )

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        try:
            profile = get_profile(context.timeframe_group)
        except KeyError:
            return ()

        entry_candles = tuple(context.candles_by_timeframe.get(profile.entry_timeframe, ()))
        structure_candles = tuple(context.candles_by_timeframe.get(profile.structure_timeframe, ()))
        trend_candles = tuple(context.candles_by_timeframe.get(profile.trend_timeframe, ()))
        if not entry_candles or not structure_candles or not trend_candles:
            return ()

        regime = build_market_regime(trend_candles)
        if regime is None:
            return ()

        parameters = strategy_parameters_from_context(context.features)
        setup = detect_price_action_setup(structure_candles, entry_candles, regime, parameters)
        if setup is None:
            return ()

        confirmation = confirm_volume_price(
            entry_candles,
            setup.direction,
            context_features=context.features,
        )
        if confirmation.status != "confirm":
            return ()

        entry_price = float(entry_candles[-1].close)
        reward_to_risk = minimum_reward_to_risk(
            entry_price,
            setup.invalidation_level,
            setup.target_price,
        )
        if reward_to_risk is None:
            return ()
        if setup.setup_type == "liquidity_reversal" and reward_to_risk < 1.5:
            return ()

        strategy_family = str(setup.evidence.get("strategy_family", setup.setup_type))
        trend_gate_role = setup.evidence.get("trend_gate_role")
        signal = StrategySignal(
            strategy_name=self.metadata.name,
            strategy_version=self.metadata.version,
            setup_type=setup.setup_type,
            symbol=context.symbol,
            venue=context.venue,
            timeframe_group=context.timeframe_group,
            direction=setup.direction,
            entry_zone={
                "low": setup.entry_zone_low,
                "high": setup.entry_zone_high,
                "reference_price": entry_price,
            },
            invalidation_level=setup.invalidation_level,
            target_hint={
                "target_price": setup.target_price,
                "reward_to_risk": reward_to_risk,
            },
            trend_evidence=regime.evidence,
            price_action_evidence=setup.evidence,
            volume_price_evidence=confirmation.evidence,
            risk_profile={
                "setup_type": setup.setup_type,
                "strategy_family": strategy_family,
                "invalidation_level": setup.invalidation_level,
                "target_price": setup.target_price,
                "minimum_reward_to_risk": 1.5 if setup.setup_type == "liquidity_reversal" else None,
            },
            explanation_payload={
                "hot_path": (
                    "MarketRegime",
                    "PriceActionSetup",
                    "VolumePriceConfirmation",
                    "StrategySignal",
                ),
                "regime_state": regime.state,
                "setup_type": setup.setup_type,
                "strategy_family": strategy_family,
                "trend_gate_role": trend_gate_role,
                "confirmation_status": confirmation.status,
            },
        )
        return (signal,)
