from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, asdict
from hashlib import sha256

from trading_system.strategies.trend_price_volume_v1.features import (
    build_market_regime,
    confirm_volume_price,
    strategy_parameters_from_context,
)


@dataclass(frozen=True)
class RawCandidate:
    candidate_id: str
    timestamp_ms: int
    structure_timestamp_ms: int | None
    sweep_timestamp_ms: int
    reclaim_timestamp_ms: int | None
    signal_timestamp_ms: int
    entry_timestamp_ms: int
    asset: str
    symbol: str
    venue: str
    inst_id: str
    inst_type: str
    profile: str
    setup: str
    direction: str
    long_or_short: str
    structure_level: float
    sweep_extreme: float
    wick_ratio: float
    sweep_atr_multiple: float
    rolling_rvol: float | None
    tod_dow_rvol: float | None
    reclaim_bars: int
    choch_detected: bool
    bos_detected: bool
    trend_state: str
    trend_direction: str
    signal_close_price: float
    entry_reference_price: float
    actual_entry_price_if_simulated: float
    target_price: float
    stop_price: float
    atr_value: float
    reclaim_rvol: float | None
    countertrend: bool
    raw_volume: float | None
    log_volume: float | None
    volume_baseline_mode: str
    volume_bucket_key: str
    volume_bucket_sample_count: int
    used_fallback_volume_baseline: bool
    sweep_extreme_price: float
    sweep_extreme_low: float
    sweep_extreme_high: float
    sweep_extreme_price_used: float
    reclaim_price: float | None
    invalidation_mode_config: str
    invalidation_mode_effective: str
    invalidation_buffer_atr: float
    stop_formula_used: str
    stop_formula_fallback_reason: str
    atr_used_for_stop: float
    atr_used_for_stop_timeframe: str
    bars_structure_to_sweep: int | None
    bars_sweep_to_reclaim: int | None
    bars_reclaim_to_signal: int | None
    bars_signal_to_entry: int | None
    bars_reclaim_to_entry: int | None
    bars_sweep_to_entry: int | None
    candidate_lifecycle_status: str
    candidate_lifecycle_reason: str
    sweep_event_id: str
    candidate_generation_reason: str

    def to_row(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StopPlan:
    price: float
    mode_config: str
    mode_effective: str
    buffer_atr: float
    formula_used: str
    fallback_reason: str


def generate_raw_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    trend_candles: Sequence[object],
    context_features: Mapping[str, object],
) -> tuple[RawCandidate, ...]:
    structure = tuple(candle for candle in structure_candles if bool(getattr(candle, "is_confirmed", False)))
    entry = tuple(candle for candle in entry_candles if bool(getattr(candle, "is_confirmed", False)))
    trend = tuple(candle for candle in trend_candles if bool(getattr(candle, "is_confirmed", False)))
    if len(structure) < 5 or not entry:
        return ()

    regime = build_market_regime(trend)
    atr = float(regime.atr) if regime is not None and regime.atr > 0 else _average_range(structure)
    if atr <= 0:
        return ()
    trend_state = regime.status if regime is not None else "unknown"
    trend_direction = regime.direction or "" if regime is not None else ""
    params = strategy_parameters_from_context(context_features)
    candidates: list[RawCandidate] = []
    candidates.extend(
        _liquidity_candidates(
            symbol=symbol,
            venue=venue,
            inst_id=inst_id,
            inst_type=inst_type,
            profile=profile,
            structure=structure,
            entry=entry,
            atr=atr,
            trend_state=trend_state,
            trend_direction=trend_direction,
            context_features=context_features,
            invalidation_mode=params.invalidation_mode,
            invalidation_buffer_atr=params.invalidation_buffer_atr,
        )
    )
    candidates.extend(
        _trend_candidates(
            symbol=symbol,
            venue=venue,
            inst_id=inst_id,
            inst_type=inst_type,
            profile=profile,
            structure=structure,
            entry=entry,
            atr=atr,
            trend_state=trend_state,
            trend_direction=trend_direction,
            context_features=context_features,
        )
    )
    return tuple(candidates)


def _liquidity_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
    invalidation_mode: str,
    invalidation_buffer_atr: float,
) -> tuple[RawCandidate, ...]:
    rows: list[RawCandidate] = []
    asset = symbol.split("/", 1)[0].upper()
    for index in range(2, len(structure)):
        sweep = structure[index]
        previous = structure[index - 1]
        next_candles = tuple(structure[index + 1 : index + 6])
        prior = tuple(structure[:index])
        if not prior:
            continue
        prior_low = min(float(candle.low) for candle in prior)
        prior_high = max(float(candle.high) for candle in prior)
        prior_low_candle = min(prior, key=lambda candle: float(candle.low))
        prior_high_candle = max(prior, key=lambda candle: float(candle.high))
        downside_deviation = prior_low - float(sweep.low)
        upside_deviation = float(sweep.high) - prior_high
        if downside_deviation > 0:
            reclaim = _find_reclaim(sweep, next_candles, "long", prior_low)
            choch = next((candle for candle in next_candles if float(candle.close) > float(previous.high)), None)
            signal = _signal_candle(reclaim, choch, sweep)
            entry_candle = _entry_after_signal(entry, int(getattr(signal, "timestamp_ms")))
            if entry_candle is None or int(getattr(entry_candle, "timestamp_ms")) != int(getattr(entry[-1], "timestamp_ms")):
                continue
            volume_evidence = confirm_volume_price((*prior, sweep), "long", context_features=context_features).evidence
            stop = _stop("long", sweep, atr, invalidation_mode, invalidation_buffer_atr)
            entry_price = float(entry_candle.open)
            rows.append(
                _candidate(
                    symbol=symbol,
                    venue=venue,
                    inst_id=inst_id,
                    inst_type=inst_type,
                    profile=profile,
                    setup="liquidity_reversal",
                    direction="long",
                    asset=asset,
                    timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    structure_timestamp_ms=int(getattr(prior_low_candle, "timestamp_ms")),
                    sweep_timestamp_ms=int(getattr(sweep, "timestamp_ms")),
                    reclaim_timestamp_ms=None if reclaim is None else int(getattr(reclaim, "timestamp_ms")),
                    signal_timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    entry_timestamp_ms=int(getattr(entry_candle, "timestamp_ms")),
                    structure_level=prior_low,
                    sweep_extreme=float(sweep.low),
                    sweep_extreme_low=float(sweep.low),
                    sweep_extreme_high=float(sweep.high),
                    wick_ratio=_wick_ratio(sweep, "long"),
                    sweep_atr_multiple=downside_deviation / atr,
                    reclaim_bars=_bars_between(sweep, reclaim),
                    choch_detected=choch is not None,
                    bos_detected=False,
                    trend_state=trend_state,
                    trend_direction=trend_direction,
                    signal_close_price=float(signal.close),
                    entry_reference_price=entry_price,
                    actual_entry_price_if_simulated=entry_price,
                    target_price=entry_price + abs(entry_price - stop.price) * 2.0,
                    stop=stop,
                    atr_value=atr,
                    reclaim=reclaim,
                    volume_evidence=volume_evidence,
                    context_features=context_features,
                    countertrend=trend_direction == "short",
                    bars_structure_to_sweep=index - _candle_index(structure, prior_low_candle),
                    bars_sweep_to_reclaim=_bars_between(sweep, reclaim),
                    bars_reclaim_to_signal=_bars_between(reclaim, signal) if reclaim is not None else None,
                    bars_signal_to_entry=_entry_bars_between(entry, signal, entry_candle),
                    bars_reclaim_to_entry=_entry_bars_between(entry, reclaim, entry_candle) if reclaim is not None else None,
                    bars_sweep_to_entry=_entry_bars_between(entry, sweep, entry_candle),
                    candidate_generation_reason="downside_sweep_structure_event",
                )
            )
        if upside_deviation > 0:
            reclaim = _find_reclaim(sweep, next_candles, "short", prior_high)
            choch = next((candle for candle in next_candles if float(candle.close) < float(previous.low)), None)
            signal = _signal_candle(reclaim, choch, sweep)
            entry_candle = _entry_after_signal(entry, int(getattr(signal, "timestamp_ms")))
            if entry_candle is None or int(getattr(entry_candle, "timestamp_ms")) != int(getattr(entry[-1], "timestamp_ms")):
                continue
            volume_evidence = confirm_volume_price((*prior, sweep), "short", context_features=context_features).evidence
            stop = _stop("short", sweep, atr, invalidation_mode, invalidation_buffer_atr)
            entry_price = float(entry_candle.open)
            rows.append(
                _candidate(
                    symbol=symbol,
                    venue=venue,
                    inst_id=inst_id,
                    inst_type=inst_type,
                    profile=profile,
                    setup="liquidity_reversal",
                    direction="short",
                    asset=asset,
                    timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    structure_timestamp_ms=int(getattr(prior_high_candle, "timestamp_ms")),
                    sweep_timestamp_ms=int(getattr(sweep, "timestamp_ms")),
                    reclaim_timestamp_ms=None if reclaim is None else int(getattr(reclaim, "timestamp_ms")),
                    signal_timestamp_ms=int(getattr(signal, "timestamp_ms")),
                    entry_timestamp_ms=int(getattr(entry_candle, "timestamp_ms")),
                    structure_level=prior_high,
                    sweep_extreme=float(sweep.high),
                    sweep_extreme_low=float(sweep.low),
                    sweep_extreme_high=float(sweep.high),
                    wick_ratio=_wick_ratio(sweep, "short"),
                    sweep_atr_multiple=upside_deviation / atr,
                    reclaim_bars=_bars_between(sweep, reclaim),
                    choch_detected=choch is not None,
                    bos_detected=False,
                    trend_state=trend_state,
                    trend_direction=trend_direction,
                    signal_close_price=float(signal.close),
                    entry_reference_price=entry_price,
                    actual_entry_price_if_simulated=entry_price,
                    target_price=entry_price - abs(stop.price - entry_price) * 2.0,
                    stop=stop,
                    atr_value=atr,
                    reclaim=reclaim,
                    volume_evidence=volume_evidence,
                    context_features=context_features,
                    countertrend=trend_direction == "long",
                    bars_structure_to_sweep=index - _candle_index(structure, prior_high_candle),
                    bars_sweep_to_reclaim=_bars_between(sweep, reclaim),
                    bars_reclaim_to_signal=_bars_between(reclaim, signal) if reclaim is not None else None,
                    bars_signal_to_entry=_entry_bars_between(entry, signal, entry_candle),
                    bars_reclaim_to_entry=_entry_bars_between(entry, reclaim, entry_candle) if reclaim is not None else None,
                    bars_sweep_to_entry=_entry_bars_between(entry, sweep, entry_candle),
                    candidate_generation_reason="upside_sweep_structure_event",
                )
            )
    return tuple(rows)


def _trend_candidates(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    structure: Sequence[object],
    entry: Sequence[object],
    atr: float,
    trend_state: str,
    trend_direction: str,
    context_features: Mapping[str, object],
) -> tuple[RawCandidate, ...]:
    if len(structure) < 4:
        return ()
    prior = tuple(structure[:-1])
    latest = structure[-1]
    asset = symbol.split("/", 1)[0].upper()
    rows: list[RawCandidate] = []
    prior_high = max(float(candle.high) for candle in prior)
    prior_low = min(float(candle.low) for candle in prior)
    if float(latest.close) > prior_high:
        volume_evidence = confirm_volume_price((*prior, latest), "long", context_features=context_features).evidence
        rows.append(
            _candidate(
                symbol=symbol,
                venue=venue,
                inst_id=inst_id,
                inst_type=inst_type,
                profile=profile,
                setup="trend_continuation",
                direction="long",
                asset=asset,
                timestamp_ms=int(getattr(latest, "timestamp_ms")),
                structure_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                sweep_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                reclaim_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                signal_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                entry_timestamp_ms=int(getattr(entry[-1], "timestamp_ms")),
                structure_level=prior_high,
                sweep_extreme=float(latest.high),
                sweep_extreme_low=float(latest.low),
                sweep_extreme_high=float(latest.high),
                wick_ratio=_wick_ratio(latest, "long"),
                sweep_atr_multiple=(float(latest.close) - prior_high) / atr,
                reclaim_bars=0,
                choch_detected=False,
                bos_detected=True,
                trend_state=trend_state,
                trend_direction=trend_direction,
                signal_close_price=float(latest.close),
                entry_reference_price=float(entry[-1].close),
                actual_entry_price_if_simulated=float(entry[-1].close),
                target_price=float(entry[-1].close) + atr * 2.0,
                stop=_manual_stop("long", float(entry[-1].close) - atr, "trend_continuation_atr_buffer_long"),
                atr_value=atr,
                reclaim=latest,
                volume_evidence=volume_evidence,
                context_features=context_features,
                countertrend=trend_direction == "short",
                bars_structure_to_sweep=0,
                bars_sweep_to_reclaim=0,
                bars_reclaim_to_signal=0,
                bars_signal_to_entry=0,
                bars_reclaim_to_entry=0,
                bars_sweep_to_entry=0,
                candidate_generation_reason="bullish_breakout_structure_event",
            )
        )
    if float(latest.close) < prior_low:
        volume_evidence = confirm_volume_price((*prior, latest), "short", context_features=context_features).evidence
        rows.append(
            _candidate(
                symbol=symbol,
                venue=venue,
                inst_id=inst_id,
                inst_type=inst_type,
                profile=profile,
                setup="trend_continuation",
                direction="short",
                asset=asset,
                timestamp_ms=int(getattr(latest, "timestamp_ms")),
                structure_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                sweep_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                reclaim_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                signal_timestamp_ms=int(getattr(latest, "timestamp_ms")),
                entry_timestamp_ms=int(getattr(entry[-1], "timestamp_ms")),
                structure_level=prior_low,
                sweep_extreme=float(latest.low),
                sweep_extreme_low=float(latest.low),
                sweep_extreme_high=float(latest.high),
                wick_ratio=_wick_ratio(latest, "short"),
                sweep_atr_multiple=(prior_low - float(latest.close)) / atr,
                reclaim_bars=0,
                choch_detected=False,
                bos_detected=True,
                trend_state=trend_state,
                trend_direction=trend_direction,
                signal_close_price=float(latest.close),
                entry_reference_price=float(entry[-1].close),
                actual_entry_price_if_simulated=float(entry[-1].close),
                target_price=float(entry[-1].close) - atr * 2.0,
                stop=_manual_stop("short", float(entry[-1].close) + atr, "trend_continuation_atr_buffer_short"),
                atr_value=atr,
                reclaim=latest,
                volume_evidence=volume_evidence,
                context_features=context_features,
                countertrend=trend_direction == "long",
                bars_structure_to_sweep=0,
                bars_sweep_to_reclaim=0,
                bars_reclaim_to_signal=0,
                bars_signal_to_entry=0,
                bars_reclaim_to_entry=0,
                bars_sweep_to_entry=0,
                candidate_generation_reason="bearish_breakout_structure_event",
            )
        )
    return tuple(rows)


def _candidate(
    *,
    symbol: str,
    venue: str,
    inst_id: str,
    inst_type: str,
    profile: str,
    setup: str,
    direction: str,
    asset: str,
    timestamp_ms: int,
    structure_timestamp_ms: int | None,
    sweep_timestamp_ms: int,
    reclaim_timestamp_ms: int | None,
    signal_timestamp_ms: int,
    entry_timestamp_ms: int,
    structure_level: float,
    sweep_extreme: float,
    sweep_extreme_low: float,
    sweep_extreme_high: float,
    wick_ratio: float,
    sweep_atr_multiple: float,
    reclaim_bars: int,
    choch_detected: bool,
    bos_detected: bool,
    trend_state: str,
    trend_direction: str,
    signal_close_price: float,
    entry_reference_price: float,
    actual_entry_price_if_simulated: float,
    target_price: float,
    stop: StopPlan,
    atr_value: float,
    reclaim: object | None,
    volume_evidence: Mapping[str, object],
    context_features: Mapping[str, object],
    countertrend: bool,
    bars_structure_to_sweep: int | None,
    bars_sweep_to_reclaim: int | None,
    bars_reclaim_to_signal: int | None,
    bars_signal_to_entry: int | None,
    bars_reclaim_to_entry: int | None,
    bars_sweep_to_entry: int | None,
    candidate_generation_reason: str,
) -> RawCandidate:
    volume = volume_evidence
    reclaim_rvol = _as_float(volume.get("tod_dow_rvol") or volume.get("rolling_rvol"))
    sweep_event_id = f"{symbol}|{profile}|{setup}|{direction}|{structure_timestamp_ms}|{sweep_timestamp_ms}|{reclaim_timestamp_ms}|{structure_level:.8f}|{sweep_extreme:.8f}"
    lifecycle_status, lifecycle_reason = _lifecycle_status(
        reclaim_timestamp_ms=reclaim_timestamp_ms,
        bars_reclaim_to_signal=bars_reclaim_to_signal,
        bars_signal_to_entry=bars_signal_to_entry,
        bars_reclaim_to_entry=bars_reclaim_to_entry,
        entry_reference_price=entry_reference_price,
        reclaim_price=None if reclaim is None else float(getattr(reclaim, "close")),
        atr=atr_value,
    )
    return RawCandidate(
        candidate_id=sha256(sweep_event_id.encode("utf-8")).hexdigest()[:24],
        timestamp_ms=timestamp_ms,
        structure_timestamp_ms=structure_timestamp_ms,
        sweep_timestamp_ms=sweep_timestamp_ms,
        reclaim_timestamp_ms=reclaim_timestamp_ms,
        signal_timestamp_ms=signal_timestamp_ms,
        entry_timestamp_ms=entry_timestamp_ms,
        asset=asset,
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        inst_type=inst_type,
        profile=profile,
        setup=setup,
        direction=direction,
        long_or_short=direction,
        structure_level=structure_level,
        sweep_extreme=sweep_extreme,
        wick_ratio=wick_ratio,
        sweep_atr_multiple=sweep_atr_multiple,
        rolling_rvol=_as_float(volume.get("rolling_rvol")),
        tod_dow_rvol=_as_float(volume.get("tod_dow_rvol")),
        reclaim_bars=reclaim_bars,
        choch_detected=choch_detected,
        bos_detected=bos_detected,
        trend_state=trend_state,
        trend_direction=trend_direction,
        signal_close_price=signal_close_price,
        entry_reference_price=entry_reference_price,
        actual_entry_price_if_simulated=actual_entry_price_if_simulated,
        target_price=target_price,
        stop_price=stop.price,
        atr_value=atr_value,
        reclaim_rvol=reclaim_rvol,
        countertrend=countertrend,
        raw_volume=_as_float(volume.get("raw_volume")),
        log_volume=_as_float(volume.get("log_volume")),
        volume_baseline_mode=str(volume.get("volume_baseline_mode", "")),
        volume_bucket_key=str(volume.get("volume_bucket_key", "")),
        volume_bucket_sample_count=int(volume.get("volume_bucket_sample_count", 0) or 0),
        used_fallback_volume_baseline=bool(volume.get("used_fallback_volume_baseline", False)),
        sweep_extreme_price=sweep_extreme,
        sweep_extreme_low=sweep_extreme_low,
        sweep_extreme_high=sweep_extreme_high,
        sweep_extreme_price_used=sweep_extreme,
        reclaim_price=None if reclaim is None else float(getattr(reclaim, "close")),
        invalidation_mode_config=stop.mode_config,
        invalidation_mode_effective=stop.mode_effective,
        invalidation_buffer_atr=stop.buffer_atr,
        stop_formula_used=stop.formula_used,
        stop_formula_fallback_reason=stop.fallback_reason,
        atr_used_for_stop=atr_value,
        atr_used_for_stop_timeframe=str(context_features.get("trend_timeframe", "")),
        bars_structure_to_sweep=bars_structure_to_sweep,
        bars_sweep_to_reclaim=bars_sweep_to_reclaim,
        bars_reclaim_to_signal=bars_reclaim_to_signal,
        bars_signal_to_entry=bars_signal_to_entry,
        bars_reclaim_to_entry=bars_reclaim_to_entry,
        bars_sweep_to_entry=bars_sweep_to_entry,
        candidate_lifecycle_status=lifecycle_status,
        candidate_lifecycle_reason=lifecycle_reason,
        sweep_event_id=sha256(sweep_event_id.encode("utf-8")).hexdigest()[:24],
        candidate_generation_reason=candidate_generation_reason,
    )


def _average_range(candles: Sequence[object]) -> float:
    if not candles:
        return 0.0
    return sum(float(candle.high) - float(candle.low) for candle in candles) / len(candles)


def _find_reclaim(sweep: object, next_candles: Sequence[object], direction: str, level: float) -> object | None:
    candidates = (sweep, *next_candles)
    if direction == "long":
        return next((candle for candle in candidates if float(candle.close) > level), None)
    return next((candle for candle in candidates if float(candle.close) < level), None)


def _signal_candle(reclaim: object | None, choch: object | None, sweep: object) -> object:
    if reclaim is None and choch is None:
        return sweep
    if reclaim is None:
        return choch
    if choch is None:
        return reclaim
    return choch if int(getattr(choch, "timestamp_ms")) >= int(getattr(reclaim, "timestamp_ms")) else reclaim


def _entry_after_signal(entry: Sequence[object], signal_timestamp_ms: int) -> object | None:
    return next((candle for candle in entry if int(getattr(candle, "timestamp_ms")) > signal_timestamp_ms), None)


def _bars_between(first: object, second: object | None) -> int:
    if second is None:
        return 999
    first_ts = int(getattr(first, "timestamp_ms"))
    second_ts = int(getattr(second, "timestamp_ms"))
    return 0 if first_ts == second_ts else 1


def _entry_bars_between(entry: Sequence[object], first: object | None, second: object | None) -> int | None:
    if first is None or second is None:
        return None
    first_ts = int(getattr(first, "timestamp_ms"))
    second_ts = int(getattr(second, "timestamp_ms"))
    first_index = next((index for index, candle in enumerate(entry) if int(getattr(candle, "timestamp_ms")) >= first_ts), None)
    second_index = next((index for index, candle in enumerate(entry) if int(getattr(candle, "timestamp_ms")) >= second_ts), None)
    if first_index is None or second_index is None:
        return None
    return max(0, second_index - first_index)


def _candle_index(candles: Sequence[object], target: object) -> int:
    target_ts = int(getattr(target, "timestamp_ms"))
    return next((index for index, candle in enumerate(candles) if int(getattr(candle, "timestamp_ms")) == target_ts), 0)


def _lifecycle_status(
    *,
    reclaim_timestamp_ms: int | None,
    bars_reclaim_to_signal: int | None,
    bars_signal_to_entry: int | None,
    bars_reclaim_to_entry: int | None,
    entry_reference_price: float,
    reclaim_price: float | None,
    atr: float,
) -> tuple[str, str]:
    if reclaim_timestamp_ms is None:
        return "expired_candidate", "missing_reclaim"
    if bars_reclaim_to_signal is not None and bars_reclaim_to_signal > 3:
        return "expired_candidate", "reclaim_to_signal_delay"
    if bars_reclaim_to_entry is not None and bars_reclaim_to_entry > 3:
        return "expired_candidate", "reclaim_to_entry_delay"
    if reclaim_price is not None and atr > 0 and abs(entry_reference_price - reclaim_price) / atr > 1.5:
        return "expired_candidate", "entry_too_far_from_reclaim"
    if bars_reclaim_to_signal is not None and bars_reclaim_to_signal > 1:
        return "stale_candidate", "reclaim_to_signal_delay"
    if bars_signal_to_entry is not None and bars_signal_to_entry > 1:
        return "stale_candidate", "signal_to_entry_delay"
    return "active_candidate", ""


def _wick_ratio(candle: object, direction: str) -> float:
    candle_range = float(candle.high) - float(candle.low)
    if candle_range <= 0:
        return 0.0
    if direction == "long":
        wick = min(float(candle.open), float(candle.close)) - float(candle.low)
    else:
        wick = float(candle.high) - max(float(candle.open), float(candle.close))
    return max(0.0, wick) / candle_range


def _stop(direction: str, candle: object, atr: float, mode: str, buffer_atr: float) -> StopPlan:
    high = float(candle.high)
    low = float(candle.low)
    if mode == "structure_extreme_buffer" and atr > 0 and math.isfinite(atr):
        if direction == "long":
            price = low - buffer_atr * atr
        else:
            price = high + buffer_atr * atr
        return StopPlan(
            price=price,
            mode_config=mode,
            mode_effective="structure_extreme_buffer",
            buffer_atr=buffer_atr,
            formula_used=f"structure_extreme_buffer_{direction}",
            fallback_reason="",
        )
    return _legacy_stop(
        direction,
        high,
        low,
        atr,
        mode_config=mode,
        fallback_reason="" if mode != "structure_extreme_buffer" else "invalid_atr_for_structure_extreme_buffer",
    )


def _legacy_stop(
    direction: str,
    high: float,
    low: float,
    atr: float,
    *,
    mode_config: str = "atr_buffer",
    fallback_reason: str = "",
) -> StopPlan:
    if direction == "long":
        price = low - atr
    else:
        price = high + atr
    return StopPlan(
        price=price,
        mode_config=mode_config,
        mode_effective="atr_buffer",
        buffer_atr=1.0,
        formula_used=f"legacy_atr_buffer_{direction}",
        fallback_reason=fallback_reason,
    )


def _manual_stop(direction: str, price: float, formula_used: str) -> StopPlan:
    return StopPlan(
        price=price,
        mode_config="atr_buffer",
        mode_effective="atr_buffer",
        buffer_atr=1.0,
        formula_used=formula_used,
        fallback_reason="",
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = ("RawCandidate", "generate_raw_candidates")
