from __future__ import annotations

from collections import Counter
from typing import Sequence

from trading_system.backtest.execution import BacktestSignalInput, SignalOrderAdapter
from trading_system.backtest.risk import AccountState, CostEstimate, RiskEngine
from trading_system.config.loader import BacktestPresetConfig
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.strategies.base import Strategy, StrategyContext
from trading_system.strategies.trend_price_volume_v1.features import (
    build_market_regime,
    confirm_volume_price,
    detect_price_action_setup,
    minimum_reward_to_risk,
    strategy_parameters_from_context,
)
from trading_system.timeframe_profiles import get_profile


FUNNEL_STAGES = (
    "data_insufficient",
    "regime_not_computable",
    "regime_rejected",
    "price_action_rejected",
    "volume_price_rejected",
    "target_space_insufficient",
    "risk_rejected",
    "approved_signal",
)


def build_signal_funnel_rows(
    repository,
    *,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    profile_keys: Sequence[str] | None = None,
    max_windows_per_profile: int = 200,
) -> tuple[dict[str, object], ...]:
    active_profiles = tuple(profile_keys or preset.scan.profile_keys)
    rows: list[dict[str, object]] = []
    for target in preset.assets.targets:
        for profile_key in active_profiles:
            rows.append(
                _diagnose_target_profile(
                    repository,
                    target=target,
                    profile_key=profile_key,
                    preset=preset,
                    strategy=strategy,
                    max_windows=max_windows_per_profile,
                )
            )
    return tuple(rows)


def _diagnose_target_profile(
    repository,
    *,
    target,
    profile_key: str,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    max_windows: int,
) -> dict[str, object]:
    profile = get_profile(profile_key)
    candles_by_timeframe = {
        profile.entry_timeframe: _load_timeframe(repository, target, profile.entry_timeframe, preset),
        profile.structure_timeframe: _load_timeframe(repository, target, profile.structure_timeframe, preset),
        profile.trend_timeframe: _load_timeframe(repository, target, profile.trend_timeframe, preset),
    }
    counts = {timeframe: len(candles) for timeframe, candles in candles_by_timeframe.items()}
    stage_counts: Counter[str] = Counter({stage: 0 for stage in FUNNEL_STAGES})
    reason_codes: Counter[str] = Counter()

    missing = tuple(f"missing_candles:{timeframe}" for timeframe, candles in candles_by_timeframe.items() if not candles)
    if missing:
        stage_counts["data_insufficient"] = 1
        reason_codes.update(missing)
        return _row(target, profile, counts, 0, stage_counts, reason_codes)

    entry_candles = candles_by_timeframe[profile.entry_timeframe]
    max_holding_bars = preset.execution.max_holding_bars
    risk_engine = RiskEngine(preset.to_risk_parameters())
    adapter = SignalOrderAdapter()
    windows_checked = 0

    start_index = max(0, len(entry_candles) - max_windows - 1)
    for index in range(start_index, max(0, len(entry_candles) - 1)):
        if windows_checked >= max_windows:
            break

        signal_timestamp_ms = int(getattr(entry_candles[index], "timestamp_ms"))
        context = StrategyContext(
            symbol=target.canonical_symbol,
            venue=target.venue,
            timeframe_group=profile.key,
            candles_by_timeframe={
                profile.entry_timeframe: entry_candles[: index + 1],
                profile.structure_timeframe: _candles_until(
                    candles_by_timeframe[profile.structure_timeframe],
                    signal_timestamp_ms,
                ),
                profile.trend_timeframe: _candles_until(
                    candles_by_timeframe[profile.trend_timeframe],
                    signal_timestamp_ms,
                ),
            },
        )
        execution_candles = tuple(entry_candles[index + 1 : index + 1 + max_holding_bars])
        windows_checked += 1

        if any(not candles for candles in context.candles_by_timeframe.values()) or not execution_candles:
            stage_counts["data_insufficient"] += 1
            reason_codes["missing_context_or_execution_candles"] += 1
            continue

        regime = build_market_regime(context.candles_by_timeframe[profile.trend_timeframe])
        if regime is None:
            stage_counts["regime_not_computable"] += 1
            reason_codes["regime_not_computable"] += 1
            continue

        if regime.status == "OVERHEATED_TREND_END" or regime.direction is None:
            stage_counts["regime_rejected"] += 1
            reason_codes[f"regime_rejected:{regime.status}"] += 1
            continue

        parameters = strategy_parameters_from_context(context.features)
        setup = detect_price_action_setup(
            context.candles_by_timeframe[profile.structure_timeframe],
            context.candles_by_timeframe[profile.entry_timeframe],
            regime,
            parameters,
        )
        if setup is None:
            stage_counts["price_action_rejected"] += 1
            reason_codes["price_action_rejected"] += 1
            continue

        confirmation = confirm_volume_price(
            context.candles_by_timeframe[profile.entry_timeframe],
            setup.direction,
            context_features=context.features,
        )
        if confirmation.status != "confirm":
            stage_counts["volume_price_rejected"] += 1
            reason_codes[f"volume_price:{confirmation.status}"] += 1
            continue

        reward_to_risk = minimum_reward_to_risk(
            float(context.candles_by_timeframe[profile.entry_timeframe][-1].close),
            setup.invalidation_level,
            setup.target_price,
        )
        if reward_to_risk is None or (setup.setup_type == "liquidity_reversal" and reward_to_risk < 1.5):
            stage_counts["target_space_insufficient"] += 1
            reason_codes["target_space_insufficient"] += 1
            continue

        signals = strategy.generate_signals(context)
        if not signals:
            stage_counts["target_space_insufficient"] += 1
            reason_codes["strategy_returned_no_signal_after_diagnostic_pass"] += 1
            continue

        input_item = BacktestSignalInput(signal=signals[0], execution_candles=execution_candles)
        intent, atr, adapter_reasons = adapter.to_order_intent(
            input_item.signal,
            input_item.execution_candles,
            point_value=preset.execution.point_value,
        )
        if intent is None or atr is None or adapter_reasons:
            stage_counts["risk_rejected"] += 1
            reason_codes.update(adapter_reasons)
            continue

        decision = risk_engine.evaluate(
            intent,
            AccountState(
                equity=preset.execution.initial_equity,
                high_water_mark=preset.execution.initial_equity,
                current_drawdown_pct=0.0,
                daily_pnl=0.0,
                open_positions=(),
            ),
            atr=atr,
            cost_estimate=CostEstimate(),
        )
        if decision.approved_order is None:
            stage_counts["risk_rejected"] += 1
            reason_codes.update(decision.reason_codes)
            continue

        stage_counts["approved_signal"] += 1

    return _row(target, profile, counts, windows_checked, stage_counts, reason_codes)


def _load_timeframe(repository, target, timeframe: str, preset: BacktestPresetConfig) -> tuple[object, ...]:
    bar = timeframe_to_okx_bar(timeframe)
    start_ms = 0 if preset.scan.start_ms is None else preset.scan.start_ms
    end_ms = 9_223_372_036_854_775_807 if preset.scan.end_ms is None else preset.scan.end_ms
    if hasattr(repository, "load_range"):
        return tuple(
            repository.load_range(
                target.inst_id,
                bar,
                start_ms,
                end_ms,
                venue=target.venue,
                inst_type=target.inst_type,
                confirmed_only=True,
            )
        )
    try:
        candles = repository.list_candles(target.inst_id, bar, venue=target.venue, inst_type=target.inst_type)
    except TypeError:
        candles = repository.list_candles(target.inst_id, bar)
    return tuple(
        candle
        for candle in candles
        if getattr(candle, "is_confirmed", False)
        and start_ms <= int(getattr(candle, "timestamp_ms")) <= end_ms
    )


def _candles_until(candles: Sequence[object], timestamp_ms: int) -> tuple[object, ...]:
    return tuple(candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms)


def _row(target, profile, counts, windows_checked, stage_counts, reason_codes) -> dict[str, object]:
    return {
        "symbol": target.canonical_symbol,
        "venue": target.venue,
        "inst_type": target.inst_type,
        "inst_id": target.inst_id,
        "profile": profile.key,
        "entry_timeframe": profile.entry_timeframe,
        "structure_timeframe": profile.structure_timeframe,
        "trend_timeframe": profile.trend_timeframe,
        "candle_counts_by_timeframe": dict(counts),
        "windows_checked": windows_checked,
        **{stage: stage_counts[stage] for stage in FUNNEL_STAGES},
        "reason_codes": tuple(sorted(reason_codes)),
        "next_action": _next_action(stage_counts),
    }


def _next_action(stage_counts) -> str:
    if stage_counts["data_insufficient"]:
        return "backfill_data"
    if stage_counts["regime_not_computable"]:
        return "backfill_trend_timeframe"
    if stage_counts["approved_signal"]:
        return "run_p4_4_backtest"
    if stage_counts["risk_rejected"]:
        return "inspect_risk_rejections"
    return "inspect_strategy_conditions"


__all__ = ("FUNNEL_STAGES", "build_signal_funnel_rows")
