from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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


VOLUME_REASONS = (
    "volume_ratio_below_reject_threshold",
    "volume_ratio_below_confirm_threshold",
    "volume_ratio_above_anomaly_threshold",
    "price_direction_not_accepted",
)


@dataclass(frozen=True)
class RejectionDetailEvent:
    symbol: str
    venue: str
    inst_type: str
    inst_id: str
    profile: str
    entry_timeframe: str
    strategy_family: str
    setup_type: str
    direction: str
    timestamp_ms: int
    terminal_stage: str
    volume_status: str
    volume_reason: str
    volume_ratio: float | None = None
    latest_volume: float | None = None
    average_volume: float | None = None
    price_state: str = ""
    risk_reason_codes: tuple[str, ...] = ()
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
    atr: float | None = None
    stop_distance: float | None = None
    stop_atr_multiple: float | None = None
    reward_to_risk: float | None = None
    estimated_cost_r: float | None = None
    net_reward_to_risk: float | None = None
    max_stop_atr_multiple: float | None = None


@dataclass(frozen=True)
class RejectionDetailSnapshot:
    volume_rejection_rows: tuple[dict[str, object], ...]
    volume_distribution_rows: tuple[dict[str, object], ...]
    risk_rejection_rows: tuple[dict[str, object], ...]
    near_miss_rows: tuple[dict[str, object], ...]


def build_rejection_detail_snapshot(
    repository,
    *,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    profile_keys: Sequence[str] | None = None,
    max_windows_per_profile: int = 500,
) -> RejectionDetailSnapshot:
    events: list[RejectionDetailEvent] = []
    active_profiles = tuple(profile_keys or preset.scan.profile_keys)
    for target in preset.assets.targets:
        for profile_key in active_profiles:
            events.extend(
                _build_target_profile_events(
                    repository,
                    target=target,
                    profile_key=profile_key,
                    preset=preset,
                    strategy=strategy,
                    max_windows=max_windows_per_profile,
                )
            )
    return summarize_rejection_events(events)


def summarize_rejection_events(events: Sequence[RejectionDetailEvent]) -> RejectionDetailSnapshot:
    events = tuple(events)
    return RejectionDetailSnapshot(
        volume_rejection_rows=_build_volume_rejection_rows(events),
        volume_distribution_rows=_build_volume_distribution_rows(events),
        risk_rejection_rows=_build_risk_rejection_rows(events),
        near_miss_rows=_build_near_miss_rows(events),
    )


def classify_volume_rejection(
    *,
    status: str,
    volume_ratio: float | None,
    price_state: str,
    direction: str,
    fallback_reason: str = "",
) -> str:
    normalized_status = status.lower()
    if volume_ratio is not None:
        if volume_ratio >= 6.0:
            return "volume_ratio_above_anomaly_threshold"
        if volume_ratio < 0.8:
            return "volume_ratio_below_reject_threshold"
        if volume_ratio < 1.5:
            return "volume_ratio_below_confirm_threshold"
        if normalized_status != "confirm" and not _price_state_accepts_direction(price_state, direction):
            return "price_direction_not_accepted"
    if fallback_reason:
        return fallback_reason
    if normalized_status == "confirm":
        return "confirmed"
    return f"volume_status:{normalized_status}"


def _build_target_profile_events(
    repository,
    *,
    target,
    profile_key: str,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    max_windows: int,
) -> list[RejectionDetailEvent]:
    profile = get_profile(profile_key)
    candles_by_timeframe = {
        profile.entry_timeframe: _load_timeframe(repository, target, profile.entry_timeframe, preset),
        profile.structure_timeframe: _load_timeframe(repository, target, profile.structure_timeframe, preset),
        profile.trend_timeframe: _load_timeframe(repository, target, profile.trend_timeframe, preset),
    }
    if any(not candles for candles in candles_by_timeframe.values()):
        return []

    entry_candles = candles_by_timeframe[profile.entry_timeframe]
    max_holding_bars = preset.execution.max_holding_bars
    risk_engine = RiskEngine(preset.to_risk_parameters())
    adapter = SignalOrderAdapter()
    events: list[RejectionDetailEvent] = []

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
            continue

        regime = build_market_regime(context.candles_by_timeframe[profile.trend_timeframe])
        if regime is None or regime.status == "OVERHEATED_TREND_END" or regime.direction is None:
            continue

        parameters = strategy_parameters_from_context(context.features)
        setup = detect_price_action_setup(
            context.candles_by_timeframe[profile.structure_timeframe],
            context.candles_by_timeframe[profile.entry_timeframe],
            regime,
            parameters,
        )
        if setup is None:
            continue

        confirmation = confirm_volume_price(
            context.candles_by_timeframe[profile.entry_timeframe],
            setup.direction,
            context_features=context.features,
        )
        terminal_stage = "volume_price_rejected" if confirmation.status != "confirm" else "volume_price_confirmed"
        base_event = _build_base_event(
            target=target,
            profile=profile,
            setup=setup,
            confirmation=confirmation,
            timestamp_ms=signal_timestamp_ms,
            terminal_stage=terminal_stage,
        )
        if confirmation.status != "confirm":
            events.append(base_event)
            continue

        entry_price = float(context.candles_by_timeframe[profile.entry_timeframe][-1].close)
        reward_to_risk = minimum_reward_to_risk(
            entry_price,
            setup.invalidation_level,
            setup.target_price,
        )
        if reward_to_risk is None or (setup.setup_type == "liquidity_reversal" and reward_to_risk < 1.5):
            events.append(_replace_event(base_event, terminal_stage="target_space_insufficient", reward_to_risk=reward_to_risk))
            continue

        signals = strategy.generate_signals(context)
        if not signals:
            events.append(
                _replace_event(
                    base_event,
                    terminal_stage="target_space_insufficient",
                    reward_to_risk=reward_to_risk,
                    risk_reason_codes=("strategy_returned_no_signal_after_diagnostic_pass",),
                )
            )
            continue

        input_item = BacktestSignalInput(signal=signals[0], execution_candles=execution_candles)
        intent, atr, adapter_reasons = adapter.to_order_intent(
            input_item.signal,
            input_item.execution_candles,
            point_value=preset.execution.point_value,
        )
        risk_metrics = _risk_metrics(intent, atr, preset)
        if intent is None or atr is None or adapter_reasons:
            events.append(
                _replace_event(
                    base_event,
                    terminal_stage="risk_rejected",
                    risk_reason_codes=adapter_reasons,
                    **risk_metrics,
                )
            )
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
        final_stage = "approved_signal" if decision.approved_order is not None else "risk_rejected"
        events.append(
            _replace_event(
                base_event,
                terminal_stage=final_stage,
                risk_reason_codes=decision.reason_codes,
                **risk_metrics,
            )
        )

    return events


def _build_base_event(
    *,
    target,
    profile,
    setup,
    confirmation,
    timestamp_ms: int,
    terminal_stage: str,
) -> RejectionDetailEvent:
    evidence = confirmation.evidence
    volume_ratio = _as_float(evidence.get("volume_ratio"))
    price_state = str(evidence.get("price_state", ""))
    fallback_reason = str(evidence.get("reason", ""))
    direction = str(setup.direction)
    return RejectionDetailEvent(
        symbol=target.canonical_symbol,
        venue=target.venue,
        inst_type=target.inst_type,
        inst_id=target.inst_id,
        profile=profile.key,
        entry_timeframe=profile.entry_timeframe,
        strategy_family=str(setup.evidence.get("strategy_family", setup.setup_type)),
        setup_type=setup.setup_type,
        direction=direction,
        timestamp_ms=timestamp_ms,
        terminal_stage=terminal_stage,
        volume_status=confirmation.status,
        volume_reason=classify_volume_rejection(
            status=confirmation.status,
            volume_ratio=volume_ratio,
            price_state=price_state,
            direction=direction,
            fallback_reason=fallback_reason,
        ),
        volume_ratio=volume_ratio,
        latest_volume=_as_float(evidence.get("latest_volume")),
        average_volume=_as_float(evidence.get("average_volume")),
        price_state=price_state,
        entry_price=None,
        stop_loss=setup.invalidation_level,
        target_price=setup.target_price,
        max_stop_atr_multiple=None,
    )


def _replace_event(event: RejectionDetailEvent, **overrides) -> RejectionDetailEvent:
    values = event.__dict__.copy()
    values.update(overrides)
    return RejectionDetailEvent(**values)


def _risk_metrics(intent, atr: float | None, preset: BacktestPresetConfig) -> dict[str, float | None]:
    max_stop = preset.risk.max_stop_atr_multiple
    if intent is None:
        return {
            "entry_price": None,
            "stop_loss": None,
            "target_price": None,
            "atr": atr,
            "stop_distance": None,
            "stop_atr_multiple": None,
            "reward_to_risk": None,
            "estimated_cost_r": None,
            "net_reward_to_risk": None,
            "max_stop_atr_multiple": max_stop,
        }

    stop_distance = intent.stop_distance
    reward_distance = intent.reward_distance()
    reward_to_risk = None if reward_distance is None or stop_distance <= 0 else reward_distance / stop_distance
    estimated_cost_r = _estimated_cost_r(intent, preset) if stop_distance > 0 else None
    net_reward_to_risk = (
        None if reward_to_risk is None or estimated_cost_r is None else reward_to_risk - estimated_cost_r
    )
    return {
        "entry_price": intent.entry_price,
        "stop_loss": intent.stop_loss,
        "target_price": intent.target_price,
        "atr": atr,
        "stop_distance": stop_distance,
        "stop_atr_multiple": None if atr is None or atr <= 0 else stop_distance / atr,
        "reward_to_risk": reward_to_risk,
        "estimated_cost_r": estimated_cost_r,
        "net_reward_to_risk": net_reward_to_risk,
        "max_stop_atr_multiple": max_stop,
    }


def _estimated_cost_r(intent, preset: BacktestPresetConfig) -> float | None:
    risk_amount = preset.execution.initial_equity * preset.risk.risk_pct
    if risk_amount <= 0 or intent.stop_distance <= 0:
        return None
    quantity = risk_amount / (intent.stop_distance * intent.point_value)
    point_quantity = quantity * intent.point_value
    exit_price = intent.target_price if intent.target_price is not None else intent.entry_price
    entry_notional = abs(intent.entry_price * point_quantity)
    exit_notional = abs(exit_price * point_quantity)
    total_cost = (
        (entry_notional + exit_notional) * preset.costs.fee_rate
        + abs(preset.costs.spread * point_quantity)
        + abs(preset.costs.slippage * point_quantity * 2.0)
        + abs(preset.costs.funding * point_quantity)
    )
    return total_cost / risk_amount


def _build_volume_rejection_rows(events: Sequence[RejectionDetailEvent]) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[object, ...], list[RejectionDetailEvent]] = defaultdict(list)
    for event in events:
        grouped[_volume_group_key(event)].append(event)

    rows = []
    for key, group in grouped.items():
        statuses = Counter(event.volume_status for event in group)
        reasons = Counter(event.volume_reason for event in group)
        row = _group_row(key)
        row.update(
            {
                "candidate_count": len(group),
                "confirm": statuses["confirm"],
                "reject": statuses["reject"],
                "cooldown": statuses["cooldown"],
                "anomaly": statuses["anomaly"],
            }
        )
        for reason in VOLUME_REASONS:
            row[reason] = reasons[reason]
        row["other_reasons"] = tuple(sorted(reason for reason in reasons if reason not in VOLUME_REASONS))
        rows.append(row)
    return tuple(sorted(rows, key=_sort_row))


def _build_volume_distribution_rows(events: Sequence[RejectionDetailEvent]) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[object, ...], list[float]] = defaultdict(list)
    for event in events:
        if event.volume_ratio is not None:
            grouped[_volume_group_key(event)].append(event.volume_ratio)

    rows = []
    for key, values in grouped.items():
        summary = _percentile_summary(values, prefix="volume_ratio")
        row = _group_row(key)
        row.update(summary)
        rows.append(row)
    return tuple(sorted(rows, key=_sort_row))


def _build_risk_rejection_rows(events: Sequence[RejectionDetailEvent]) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[object, ...], list[RejectionDetailEvent]] = defaultdict(list)
    for event in events:
        if event.terminal_stage != "risk_rejected":
            continue
        reasons = event.risk_reason_codes or ("unknown_risk_rejection",)
        for reason in reasons:
            grouped[(*_volume_group_key(event), reason)].append(event)

    rows = []
    for key, group in grouped.items():
        reason = str(key[-1])
        row = _group_row(key[:-1])
        row.update(
            {
                "reason_code": reason,
                "candidate_count": len(group),
                "max_stop_atr_multiple": _first_float(group, "max_stop_atr_multiple"),
            }
        )
        row.update(_percentile_summary(_values(group, "stop_distance"), prefix="stop_distance"))
        row.update(_percentile_summary(_values(group, "atr"), prefix="atr"))
        row.update(_percentile_summary(_values(group, "stop_atr_multiple"), prefix="stop_atr"))
        row.update(_percentile_summary(_values(group, "reward_to_risk"), prefix="reward_to_risk"))
        row.update(_percentile_summary(_values(group, "estimated_cost_r"), prefix="estimated_cost_r"))
        row.update(_percentile_summary(_values(group, "net_reward_to_risk"), prefix="net_reward_to_risk"))
        rows.append(row)
    return tuple(sorted(rows, key=_sort_row))


def _build_near_miss_rows(events: Sequence[RejectionDetailEvent], limit: int = 20) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for event in events:
        if event.volume_status in {"reject", "cooldown"} and event.volume_ratio is not None:
            distance = max(0.0, 1.5 - event.volume_ratio)
            rows.append(
                {
                    **_event_row(event),
                    "near_miss_type": "volume_confirm_threshold",
                    "distance_to_pass": distance,
                }
            )
        if (
            event.terminal_stage == "risk_rejected"
            and "stop_distance_too_far" in event.risk_reason_codes
            and event.stop_atr_multiple is not None
            and event.max_stop_atr_multiple is not None
        ):
            rows.append(
                {
                    **_event_row(event),
                    "near_miss_type": "risk_stop_atr_limit",
                    "distance_to_pass": max(0.0, event.stop_atr_multiple - event.max_stop_atr_multiple),
                }
            )

    return tuple(
        sorted(
            rows,
            key=lambda row: (
                float(row["distance_to_pass"]),
                str(row["symbol"]),
                str(row["profile"]),
                int(row["timestamp_ms"]),
            ),
        )[:limit]
    )


def _event_row(event: RejectionDetailEvent) -> dict[str, object]:
    return {
        "symbol": event.symbol,
        "venue": event.venue,
        "inst_type": event.inst_type,
        "inst_id": event.inst_id,
        "profile": event.profile,
        "entry_timeframe": event.entry_timeframe,
        "strategy_family": event.strategy_family,
        "setup_type": event.setup_type,
        "direction": event.direction,
        "timestamp_ms": event.timestamp_ms,
        "terminal_stage": event.terminal_stage,
        "volume_status": event.volume_status,
        "volume_reason": event.volume_reason,
        "volume_ratio": event.volume_ratio,
        "risk_reason_codes": event.risk_reason_codes,
        "stop_distance": event.stop_distance,
        "atr": event.atr,
        "stop_atr_multiple": event.stop_atr_multiple,
        "max_stop_atr_multiple": event.max_stop_atr_multiple,
        "reward_to_risk": event.reward_to_risk,
        "estimated_cost_r": event.estimated_cost_r,
        "net_reward_to_risk": event.net_reward_to_risk,
    }


def _percentile_summary(values: Sequence[float], *, prefix: str) -> dict[str, object]:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return {
            f"{prefix}_count": 0,
            f"{prefix}_min": None,
            f"{prefix}_p25": None,
            f"{prefix}_median": None,
            f"{prefix}_p75": None,
            f"{prefix}_max": None,
        }
    return {
        "candidate_count" if prefix == "volume_ratio" else f"{prefix}_count": len(clean),
        f"{prefix}_min": clean[0],
        f"{prefix}_p25": _percentile(clean, 0.25),
        f"{prefix}_median": _percentile(clean, 0.5),
        f"{prefix}_p75": _percentile(clean, 0.75),
        f"{prefix}_max": clean[-1],
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return values[lower_index]
    lower = values[lower_index]
    upper = values[upper_index]
    return lower + (upper - lower) * (position - lower_index)


def _volume_group_key(event: RejectionDetailEvent) -> tuple[object, ...]:
    return (
        event.symbol,
        event.venue,
        event.inst_type,
        event.inst_id,
        event.profile,
        event.entry_timeframe,
        event.strategy_family,
        event.setup_type,
        event.direction,
    )


def _group_row(key: Sequence[object]) -> dict[str, object]:
    return {
        "symbol": key[0],
        "venue": key[1],
        "inst_type": key[2],
        "inst_id": key[3],
        "profile": key[4],
        "entry_timeframe": key[5],
        "strategy_family": key[6],
        "setup_type": key[7],
        "direction": key[8],
    }


def _sort_row(row: Mapping[str, object]) -> tuple[object, ...]:
    return (
        row.get("symbol", ""),
        row.get("profile", ""),
        row.get("entry_timeframe", ""),
        row.get("strategy_family", ""),
        row.get("setup_type", ""),
        row.get("direction", ""),
        row.get("reason_code", ""),
    )


def _values(events: Sequence[RejectionDetailEvent], attr: str) -> tuple[float, ...]:
    values = []
    for event in events:
        value = getattr(event, attr)
        if value is not None and math.isfinite(float(value)):
            values.append(float(value))
    return tuple(values)


def _first_float(events: Sequence[RejectionDetailEvent], attr: str) -> float | None:
    for event in events:
        value = getattr(event, attr)
        if value is not None:
            return float(value)
    return None


def _price_state_accepts_direction(price_state: str, direction: str) -> bool:
    normalized = direction.lower()
    if normalized == "long":
        return price_state == "up_close"
    if normalized == "short":
        return price_state == "down_close"
    return False


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


__all__ = (
    "RejectionDetailEvent",
    "RejectionDetailSnapshot",
    "build_rejection_detail_snapshot",
    "classify_volume_rejection",
    "summarize_rejection_events",
)
