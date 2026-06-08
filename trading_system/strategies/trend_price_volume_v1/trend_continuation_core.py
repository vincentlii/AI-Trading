from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from statistics import median
from typing import Any, Mapping, Sequence


CORE_ENGINE_VERSION = "trend_continuation_core.v2"


@dataclass(frozen=True)
class CorePolicy:
    structure_lookback_bars: int = 128
    breakout_seed_lookback_bars: int = 32
    acceptance_window_bars: int = 3
    pullback_observation_bars: int = 12
    relaunch_observation_bars: int = 6
    zone_merge_atr: float = 0.15
    zone_width_atr: float = 0.12
    breakout_watch_distance_atr: float = 0.30
    strong_breakout_distance_atr: float = 0.35
    strong_breakout_strength_min: float = 0.70
    accepted_breakout_strength_min: float = 0.55
    pullback_zone_tolerance_atr: float = 0.35
    min_structural_stop_atr: float = 0.80
    max_structural_stop_atr: float = 3.00
    stop_buffer_atr: float = 0.15
    min_gross_rr: float = 1.20
    max_zones_per_seed: int = 12


@dataclass(frozen=True)
class StructureZone:
    level_id: str
    level_type: str
    zone_upper: float
    zone_lower: float
    zone_mid: float
    zone_width: float
    zone_width_ATR: float
    touch_count: int
    rejection_count: int
    age_bars: int
    last_touch_time: int
    distance_to_price_ATR: float
    reaction_strength: float
    prior_rejection_strength: float
    liquidity_score: float
    structure_score: float
    source_window: str
    is_level_or_zone: str = "zone"
    direction_bias: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BreakoutLifecycleEvent:
    breakout_event_id: str
    lifecycle_event_id: str
    level_id: str
    level_type: str
    direction: str
    breakout_attempt_type: str
    breakout_class: str
    breakout_time: int
    breakout_price: float
    breakout_close: float
    breakout_distance_ATR: float
    breakout_distance_zone_ratio: float
    breakout_body_pct: float
    breakout_close_location: float
    breakout_range_vs_ATR: float
    breakout_volume_z: float
    breakout_RVOL: float
    breakout_volume_vs_prior: float
    breakout_range_expansion_vs_prior: float
    breakout_body_expansion_vs_prior: float
    breakout_high: float
    breakout_low: float
    atr_value: float
    compression_context: bool
    compression_score: float
    compression_range_ratio: float
    compression_body_ratio: float
    compression_volume_ratio: float
    breakout_strength_score: float
    breakout_acceptance_score: float
    breakout_failure_score: float
    acceptance_window_bars: int
    acceptance_end_time: int
    close_back_inside_zone: bool
    close_back_inside_bar_index: int | None
    wick_back_but_close_hold: bool
    immediate_reclaim: bool
    high_volume_no_result: bool
    bars_held_outside_zone: int
    max_adverse_excursion_after_breakout_ATR: float
    max_favorable_excursion_after_breakout_ATR: float
    acceptance_status: str
    pullback_observed: bool
    pullback_start_time: int | None
    pullback_end_time: int | None
    pullback_bars: int
    pullback_delay_bars_after_breakout: int | None
    pullback_depth_ATR: float | None
    pullback_depth_zone_ratio: float | None
    pullback_depth_vs_breakout_move: float | None
    pullback_zone_type: str
    pullback_zone_distance_ATR: float | None
    pullback_touched_zone: bool
    pullback_closed_inside_invalid_zone: bool
    pullback_wick_inside_but_close_hold: bool
    pullback_invalidated_level: bool
    pullback_volume_ratio_vs_breakout: float | None
    pullback_volume_contraction: bool
    pullback_range_contraction: bool
    pullback_body_contraction: bool
    pullback_countertrend_strength: float | None
    pullback_time_decay: float | None
    pullback_health_score: float
    depth_score: float
    volume_contraction_score: float
    range_contraction_score: float
    body_contraction_score: float
    level_hold_score: float
    time_decay_score: float
    no_impulsive_reversal_score: float
    target_space_score: float
    pullback_health_class: str
    relaunch_observed: bool
    relaunch_time: int | None
    relaunch_delay_bars_after_pullback: int | None
    relaunch_type: str
    relaunch_close: float | None
    relaunch_displacement_ATR: float | None
    relaunch_body_pct: float | None
    relaunch_close_location: float | None
    relaunch_volume_recovery: float | None
    relaunch_breaks_micro_structure: bool
    relaunch_score: float
    relaunch_quality_class: str
    stop_anchor_type: str
    stop: float | None
    stop_distance: float | None
    stop_distance_ATR: float | None
    stop_distance_zone_ratio: float | None
    stop_distance_pullback_ratio: float | None
    stop_buffer_ATR: float
    stop_is_structural: bool
    stop_reason: str
    structural_stop_quality: str
    target_source: str
    target: float | None
    target_space: float | None
    target_space_ATR: float | None
    gross_RR: float | None
    nearest_obstacle_distance_ATR: float | None
    target_quality_class: str
    bp_subtype: str
    candidate_rank_score: float
    trade_plan_ready: bool
    primary_failure_reason: str
    secondary_failure_reasons: tuple[str, ...]
    zone: StructureZone

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["secondary_failure_reasons"] = list(self.secondary_failure_reasons)
        return payload

    def with_rank_score(self, value: float) -> "BreakoutLifecycleEvent":
        return replace(self, candidate_rank_score=float(value))


@dataclass(frozen=True)
class TrendContinuationCoreEvaluation:
    core_engine_version: str
    zones: tuple[StructureZone, ...]
    events: tuple[BreakoutLifecycleEvent, ...]
    selected_candidates: tuple[BreakoutLifecycleEvent, ...]


def evaluate_trend_continuation_core(
    candles: Sequence[object],
    *,
    atr: float,
    policy: CorePolicy | None = None,
) -> TrendContinuationCoreEvaluation:
    policy = policy or CorePolicy()
    confirmed = tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))
    if atr <= 0 or len(confirmed) < 8:
        return TrendContinuationCoreEvaluation(CORE_ENGINE_VERSION, (), (), ())

    events: list[BreakoutLifecycleEvent] = []
    zones_by_id: dict[str, StructureZone] = {}
    seed_start = max(4, len(confirmed) - policy.breakout_seed_lookback_bars)
    for seed_index in range(seed_start, len(confirmed) - 2):
        history = confirmed[max(0, seed_index - policy.structure_lookback_bars) : seed_index]
        if len(history) < 4:
            continue
        zones = discover_structure_zones(history, current_price=float(getattr(confirmed[seed_index], "close")), atr=atr, policy=policy)
        ranked_zones = sorted(
            zones,
            key=lambda zone: (
                zone.distance_to_price_ATR,
                -zone.structure_score,
                -zone.liquidity_score,
                zone.level_id,
            ),
        )[: policy.max_zones_per_seed]
        for zone in ranked_zones:
            zones_by_id.setdefault(zone.level_id, zone)
            event = _evaluate_seed(confirmed, seed_index, zone, atr=atr, policy=policy)
            if event is not None:
                events.append(event)
    unique = _deduplicate_events(events)
    selected = arbitrate_trade_candidates(tuple(event for event in unique if event.trade_plan_ready))
    return TrendContinuationCoreEvaluation(
        core_engine_version=CORE_ENGINE_VERSION,
        zones=tuple(zones_by_id[key] for key in sorted(zones_by_id)),
        events=tuple(unique),
        selected_candidates=selected,
    )


def evaluate_breakout_pullback_core_diagnostics(
    structure_candles: Sequence[object],
    entry_candles: Sequence[object],
    regime: object | None,
    *,
    parameters: object | None = None,
    context_features: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    del entry_candles, context_features
    confirmed = tuple(candle for candle in structure_candles if bool(getattr(candle, "is_confirmed", False)))
    atr = float(getattr(regime, "atr", 0.0) or 0.0)
    if atr <= 0:
        atr = _average([float(getattr(candle, "high")) - float(getattr(candle, "low")) for candle in confirmed[-20:]])
    policy = core_policy_from_parameters(parameters)
    evaluation = evaluate_trend_continuation_core(confirmed, atr=atr, policy=policy)
    selected = _select_variant_events(evaluation.selected_candidates, parameters)
    event_rows = [event.as_dict() for event in evaluation.events]
    best = selected[0] if selected else max(evaluation.events, key=_rank_key, default=None)
    metrics = {} if best is None else best.as_dict()
    metrics.update(
        {
            "setup_id": "breakout_pullback",
            "core_engine_version": CORE_ENGINE_VERSION,
            "structure_zones_found": len(evaluation.zones),
            "breakout_event_seeds": len(evaluation.events),
            "candidate_ready_events": len(selected),
            "candidate_ready": bool(selected),
            "event_rows": event_rows,
        }
    )
    lifecycle_survivors = [event for event in evaluation.events if event.breakout_class != "failed_breakout"]
    pullbacks = [event for event in lifecycle_survivors if event.pullback_observed]
    healthy = [event for event in pullbacks if event.pullback_health_class != "failed"]
    relaunched = [event for event in healthy if event.relaunch_observed]
    structural = [event for event in relaunched if event.structural_stop_quality == "valid"]
    tradeable = [event for event in structural if event.target_quality_class in {"good", "acceptable"}]
    stages = {
        "window_ready": {"passed": bool(confirmed and atr > 0), "count": len(confirmed)},
        "structure_zone_discovery": {"passed": bool(evaluation.zones), "count": len(evaluation.zones)},
        "breakout_event_seed": {"passed": bool(evaluation.events), "count": len(evaluation.events)},
        "breakout_lifecycle": {"passed": bool(lifecycle_survivors), "count": len(lifecycle_survivors), "hard_gate": False},
        "pullback_observation": {"passed": bool(pullbacks), "count": len(pullbacks)},
        "pullback_health": {"passed": bool(healthy), "count": len(healthy)},
        "relaunch_confirmation": {"passed": bool(relaunched), "count": len(relaunched)},
        "structural_stop": {"passed": bool(structural), "count": len(structural)},
        "target_tradeability": {"passed": bool(tradeable), "count": len(tradeable)},
        "risk_engine_approval": {"passed": bool(selected), "count": len(selected)},
    }
    first_failed = next((name for name, payload in stages.items() if not payload["passed"]), "")
    return {
        "candidate_ready": bool(selected),
        "first_failed_stage": first_failed,
        "stages": stages,
        "metrics": metrics,
        "event_rows": event_rows,
    }


def core_policy_from_parameters(parameters: object | None) -> CorePolicy:
    variant = str(getattr(parameters, "bp_variant_policy", "lifecycle_level_zone") or "lifecycle_level_zone")
    if variant == "lifecycle_boundary_midpoint":
        return CorePolicy(pullback_zone_tolerance_atr=0.50, max_structural_stop_atr=3.0)
    if variant == "lifecycle_shallow_momentum":
        return CorePolicy(pullback_observation_bars=8, relaunch_observation_bars=4, pullback_zone_tolerance_atr=0.20)
    if variant == "lifecycle_weak_break_watch":
        return CorePolicy(accepted_breakout_strength_min=0.70, pullback_observation_bars=12, relaunch_observation_bars=6)
    return CorePolicy()


def _select_variant_events(events: Sequence[BreakoutLifecycleEvent], parameters: object | None) -> tuple[BreakoutLifecycleEvent, ...]:
    variant = str(getattr(parameters, "bp_variant_policy", "lifecycle_level_zone") or "lifecycle_level_zone")
    allowed = list(events)
    if variant == "lifecycle_boundary_midpoint":
        allowed = [event for event in allowed if event.bp_subtype in {"boundary_retest_continuation", "midpoint_retest_continuation"}]
    elif variant == "lifecycle_shallow_momentum":
        allowed = [event for event in allowed if event.bp_subtype == "shallow_pullback_momentum" and event.relaunch_quality_class == "strong"]
    elif variant == "lifecycle_weak_break_watch":
        allowed = [
            event
            for event in allowed
            if event.breakout_class == "weak_but_watch"
            and event.pullback_health_class == "healthy"
            and event.relaunch_quality_class == "strong"
        ]
    else:
        allowed = [
            event
            for event in allowed
            if event.bp_subtype in {"level_retest_continuation", "boundary_retest_continuation", "ob_like_retest_continuation"}
        ]
    return arbitrate_trade_candidates(allowed)


def discover_structure_zones(
    history: Sequence[object],
    *,
    current_price: float,
    atr: float,
    policy: CorePolicy | None = None,
) -> tuple[StructureZone, ...]:
    policy = policy or CorePolicy()
    if not history or atr <= 0:
        return ()
    rows = tuple(history[-policy.structure_lookback_bars :])
    width = max(atr * policy.zone_width_atr, 1e-12)
    sources: list[tuple[str, float, str]] = [
        ("range_upper", max(float(getattr(candle, "high")) for candle in rows), "long"),
        ("range_lower", min(float(getattr(candle, "low")) for candle in rows), "short"),
    ]
    for index in range(1, len(rows) - 1):
        previous, candle, following = rows[index - 1], rows[index], rows[index + 1]
        if float(getattr(candle, "high")) >= max(float(getattr(previous, "high")), float(getattr(following, "high"))):
            sources.append(("swing_high", float(getattr(candle, "high")), "long"))
        if float(getattr(candle, "low")) <= min(float(getattr(previous, "low")), float(getattr(following, "low"))):
            sources.append(("swing_low", float(getattr(candle, "low")), "short"))
    last = rows[-1]
    opposite_price = float(getattr(last, "low")) if float(getattr(last, "close")) < float(getattr(last, "open")) else float(getattr(last, "high"))
    sources.append(("last_opposite_candle_zone", opposite_price, ""))

    grouped: list[list[tuple[str, float, str]]] = []
    for source in sorted(sources, key=lambda item: item[1]):
        if grouped and abs(source[1] - median(item[1] for item in grouped[-1])) <= atr * policy.zone_merge_atr:
            grouped[-1].append(source)
        else:
            grouped.append([source])
    zones = []
    for group in grouped:
        mid = median(item[1] for item in group)
        lower, upper = mid - width / 2.0, mid + width / 2.0
        touch_count = sum(1 for candle in rows if float(getattr(candle, "low")) <= upper and float(getattr(candle, "high")) >= lower)
        last_touch_index = max(
            (index for index, candle in enumerate(rows) if float(getattr(candle, "low")) <= upper and float(getattr(candle, "high")) >= lower),
            default=0,
        )
        rejection_count = sum(
            1
            for candle in rows
            if float(getattr(candle, "low")) <= upper <= float(getattr(candle, "high"))
            or float(getattr(candle, "low")) <= lower <= float(getattr(candle, "high"))
        )
        level_types = sorted({item[0] for item in group})
        level_type = "local_pivot_cluster" if len(group) > 1 else level_types[0]
        confirmed_time = int(getattr(rows[last_touch_index], "timestamp_ms"))
        level_id = _stable_id(level_type, round(lower, 8), round(upper, 8), confirmed_time)
        structure_score = min(1.0, 0.25 + touch_count * 0.08 + rejection_count * 0.05)
        zones.append(
            StructureZone(
                level_id=level_id,
                level_type=level_type,
                zone_upper=upper,
                zone_lower=lower,
                zone_mid=mid,
                zone_width=upper - lower,
                zone_width_ATR=(upper - lower) / atr,
                touch_count=touch_count,
                rejection_count=rejection_count,
                age_bars=len(rows) - 1 - last_touch_index,
                last_touch_time=confirmed_time,
                distance_to_price_ATR=abs(current_price - mid) / atr,
                reaction_strength=min(1.0, rejection_count / max(touch_count, 1)),
                prior_rejection_strength=min(1.0, rejection_count * 0.15),
                liquidity_score=min(1.0, touch_count * 0.12),
                structure_score=structure_score,
                source_window=f"{int(getattr(rows[0], 'timestamp_ms'))}:{int(getattr(rows[-1], 'timestamp_ms'))}",
                direction_bias=next((item[2] for item in group if item[2]), ""),
            )
        )
    return tuple(zones)


def arbitrate_trade_candidates(events: Sequence[BreakoutLifecycleEvent]) -> tuple[BreakoutLifecycleEvent, ...]:
    selected: dict[tuple[str, int], BreakoutLifecycleEvent] = {}
    for event in events:
        if event.relaunch_time is None:
            continue
        key = (event.direction, event.relaunch_time)
        current = selected.get(key)
        if current is None or _rank_key(event) > _rank_key(current):
            selected[key] = event
    return tuple(selected[key] for key in sorted(selected, key=lambda item: (item[1], item[0])))


def _evaluate_seed(
    candles: Sequence[object],
    seed_index: int,
    zone: StructureZone,
    *,
    atr: float,
    policy: CorePolicy,
) -> BreakoutLifecycleEvent | None:
    breakout = candles[seed_index]
    close = float(getattr(breakout, "close"))
    high = float(getattr(breakout, "high"))
    low = float(getattr(breakout, "low"))
    direction = ""
    attempt = ""
    distance = 0.0
    if high > zone.zone_upper:
        direction = "long"
        distance = max(0.0, close - zone.zone_upper)
        attempt = "close_break" if close > zone.zone_upper else "wick_break"
    elif low < zone.zone_lower:
        direction = "short"
        distance = max(0.0, zone.zone_lower - close)
        attempt = "close_break" if close < zone.zone_lower else "wick_break"
    if not direction:
        return None
    if abs(close - zone.zone_mid) / atr > max(4.0, policy.breakout_watch_distance_atr * 12.0):
        return None

    breakout_range = max(high - low, 1e-12)
    body = abs(close - float(getattr(breakout, "open")))
    body_pct = body / breakout_range
    close_location = (close - low) / breakout_range if direction == "long" else (high - close) / breakout_range
    prior = candles[max(0, seed_index - 8) : seed_index]
    avg_range = _average([float(getattr(c, "high")) - float(getattr(c, "low")) for c in prior])
    avg_body = _average([abs(float(getattr(c, "close")) - float(getattr(c, "open"))) for c in prior])
    avg_volume = _average([float(getattr(c, "volume", 0.0)) for c in prior])
    volume = float(getattr(breakout, "volume", 0.0))
    breakout_rvol = volume / avg_volume if avg_volume > 0 else 0.0
    compression = _compression_context(prior)
    distance_atr = distance / atr
    strength = _average(
        [
            min(1.0, distance_atr / max(policy.strong_breakout_distance_atr, 1e-12)),
            min(1.0, body_pct / 0.65),
            min(1.0, close_location / 0.80),
            min(1.0, breakout_rvol / 1.50),
        ]
    )
    acceptance = tuple(candles[seed_index + 1 : seed_index + 1 + policy.acceptance_window_bars])
    lifecycle = _classify_lifecycle(
        direction,
        breakout,
        zone,
        acceptance,
        atr=atr,
        strength=strength,
        attempt=attempt,
        policy=policy,
    )
    breakout_event_id = _stable_id(CORE_ENGINE_VERSION, zone.level_id, direction, int(getattr(breakout, "timestamp_ms")))

    pullback = _observe_pullback(
        candles,
        # Acceptance and a normal retest may overlap. Lifecycle classification
        # decides failure; pullback observation must not wait for the full
        # acceptance window to finish.
        start_index=seed_index + 1,
        direction=direction,
        breakout=breakout,
        zone=zone,
        atr=atr,
        policy=policy,
    )
    relaunch = _observe_relaunch(
        candles,
        start_index=pullback["end_index"] + 1 if pullback["end_index"] is not None else len(candles),
        direction=direction,
        pullback=pullback,
        atr=atr,
        policy=policy,
    )
    trade = _build_trade_plan(direction=direction, breakout=breakout, zone=zone, pullback=pullback, relaunch=relaunch, atr=atr, policy=policy)
    primary, secondary = _failure_reason(lifecycle, pullback, relaunch, trade)
    ready = (
        lifecycle["breakout_class"] != "failed_breakout"
        and pullback["health_class"] in {"healthy", "acceptable", "weak_but_watch"}
        and relaunch["quality_class"] in {"strong", "acceptable"}
        and trade["structural_stop_quality"] == "valid"
        and trade["target_quality_class"] in {"good", "acceptable"}
    )
    subtype = _subtype(zone, pullback, lifecycle)
    rank_score = _average(
        [
            lifecycle["strength_score"],
            lifecycle["acceptance_score"],
            pullback["health_score"],
            relaunch["score"],
            min(1.0, float(trade["gross_RR"] or 0.0) / 2.0),
            zone.structure_score,
        ]
    )
    return BreakoutLifecycleEvent(
        breakout_event_id=breakout_event_id,
        lifecycle_event_id=_stable_id(breakout_event_id, pullback["end_time"], relaunch["time"]),
        level_id=zone.level_id,
        level_type=zone.level_type,
        direction=direction,
        breakout_attempt_type=attempt,
        breakout_class=lifecycle["breakout_class"],
        breakout_time=int(getattr(breakout, "timestamp_ms")),
        breakout_price=high if direction == "long" else low,
        breakout_close=close,
        breakout_distance_ATR=distance_atr,
        breakout_distance_zone_ratio=distance / max(zone.zone_width, 1e-12),
        breakout_body_pct=body_pct,
        breakout_close_location=close_location,
        breakout_range_vs_ATR=breakout_range / atr,
        breakout_volume_z=_z_score(volume, [float(getattr(c, "volume", 0.0)) for c in prior]),
        breakout_RVOL=breakout_rvol,
        breakout_volume_vs_prior=breakout_rvol,
        breakout_range_expansion_vs_prior=breakout_range / avg_range if avg_range > 0 else 0.0,
        breakout_body_expansion_vs_prior=body / avg_body if avg_body > 0 else 0.0,
        breakout_high=high,
        breakout_low=low,
        atr_value=atr,
        compression_context=compression["detected"],
        compression_score=compression["score"],
        compression_range_ratio=compression["range_ratio"],
        compression_body_ratio=compression["body_ratio"],
        compression_volume_ratio=compression["volume_ratio"],
        breakout_strength_score=lifecycle["strength_score"],
        breakout_acceptance_score=lifecycle["acceptance_score"],
        breakout_failure_score=lifecycle["failure_score"],
        acceptance_window_bars=len(acceptance),
        acceptance_end_time=(
            int(pullback["start_time"])
            if pullback["start_time"] is not None
            else int(getattr(acceptance[-1], "timestamp_ms"))
            if acceptance
            else int(getattr(breakout, "timestamp_ms"))
        ),
        close_back_inside_zone=lifecycle["close_back_inside"],
        close_back_inside_bar_index=lifecycle["close_back_index"],
        wick_back_but_close_hold=lifecycle["wick_hold"],
        immediate_reclaim=lifecycle["immediate_reclaim"],
        high_volume_no_result=lifecycle["high_volume_no_result"],
        bars_held_outside_zone=lifecycle["bars_held"],
        max_adverse_excursion_after_breakout_ATR=lifecycle["mae_atr"],
        max_favorable_excursion_after_breakout_ATR=lifecycle["mfe_atr"],
        acceptance_status=lifecycle["acceptance_status"],
        pullback_observed=pullback["observed"],
        pullback_start_time=pullback["start_time"],
        pullback_end_time=pullback["end_time"],
        pullback_bars=pullback["bars"],
        pullback_delay_bars_after_breakout=pullback["delay"],
        pullback_depth_ATR=pullback["depth_atr"],
        pullback_depth_zone_ratio=pullback["depth_zone_ratio"],
        pullback_depth_vs_breakout_move=pullback["depth_vs_breakout"],
        pullback_zone_type=pullback["zone_type"],
        pullback_zone_distance_ATR=pullback["zone_distance_atr"],
        pullback_touched_zone=pullback["touched_zone"],
        pullback_closed_inside_invalid_zone=pullback["closed_inside_invalid"],
        pullback_wick_inside_but_close_hold=pullback["wick_inside_close_hold"],
        pullback_invalidated_level=pullback["invalidated"],
        pullback_volume_ratio_vs_breakout=pullback["volume_ratio"],
        pullback_volume_contraction=pullback["volume_contraction"],
        pullback_range_contraction=pullback["range_contraction"],
        pullback_body_contraction=pullback["body_contraction"],
        pullback_countertrend_strength=pullback["countertrend_strength"],
        pullback_time_decay=pullback["time_decay"],
        pullback_health_score=pullback["health_score"],
        depth_score=pullback["depth_score"],
        volume_contraction_score=pullback["volume_score"],
        range_contraction_score=pullback["range_score"],
        body_contraction_score=pullback["body_score"],
        level_hold_score=pullback["level_hold_score"],
        time_decay_score=pullback["time_decay_score"],
        no_impulsive_reversal_score=pullback["no_impulsive_score"],
        target_space_score=pullback["target_space_score"],
        pullback_health_class=pullback["health_class"],
        relaunch_observed=relaunch["observed"],
        relaunch_time=relaunch["time"],
        relaunch_delay_bars_after_pullback=relaunch["delay"],
        relaunch_type=relaunch["type"],
        relaunch_close=relaunch["close"],
        relaunch_displacement_ATR=relaunch["displacement_atr"],
        relaunch_body_pct=relaunch["body_pct"],
        relaunch_close_location=relaunch["close_location"],
        relaunch_volume_recovery=relaunch["volume_recovery"],
        relaunch_breaks_micro_structure=relaunch["micro_break"],
        relaunch_score=relaunch["score"],
        relaunch_quality_class=relaunch["quality_class"],
        stop_anchor_type=trade["stop_anchor_type"],
        stop=trade["stop"],
        stop_distance=trade["stop_distance"],
        stop_distance_ATR=trade["stop_distance_atr"],
        stop_distance_zone_ratio=trade["stop_distance_zone_ratio"],
        stop_distance_pullback_ratio=trade["stop_distance_pullback_ratio"],
        stop_buffer_ATR=policy.stop_buffer_atr,
        stop_is_structural=trade["stop_is_structural"],
        stop_reason=trade["stop_reason"],
        structural_stop_quality=trade["structural_stop_quality"],
        target_source=trade["target_source"],
        target=trade["target"],
        target_space=trade["target_space"],
        target_space_ATR=trade["target_space_atr"],
        gross_RR=trade["gross_RR"],
        nearest_obstacle_distance_ATR=trade["nearest_obstacle_distance_atr"],
        target_quality_class=trade["target_quality_class"],
        bp_subtype=subtype,
        candidate_rank_score=rank_score,
        trade_plan_ready=ready,
        primary_failure_reason="" if ready else primary,
        secondary_failure_reasons=tuple(secondary),
        zone=zone,
    )


def _classify_lifecycle(direction: str, breakout: object, zone: StructureZone, window: Sequence[object], *, atr: float, strength: float, attempt: str, policy: CorePolicy) -> dict[str, Any]:
    close_back_index = None
    wick_hold = False
    held = 0
    favorable: list[float] = []
    adverse: list[float] = []
    breakout_close = float(getattr(breakout, "close"))
    for offset, candle in enumerate(window, start=1):
        close, high, low = float(getattr(candle, "close")), float(getattr(candle, "high")), float(getattr(candle, "low"))
        inside = close <= zone.zone_upper if direction == "long" else close >= zone.zone_lower
        if inside and close_back_index is None:
            close_back_index = offset
        wick_hold = wick_hold or (low <= zone.zone_upper < close if direction == "long" else high >= zone.zone_lower > close)
        held += int(not inside)
        favorable.append(max(0.0, high - breakout_close) if direction == "long" else max(0.0, breakout_close - low))
        adverse.append(max(0.0, breakout_close - low) if direction == "long" else max(0.0, high - breakout_close))
    immediate = close_back_index == 1
    high_volume_no_result = bool(window and held == 0 and float(getattr(breakout, "volume", 0.0)) > _average([float(getattr(c, "volume", 0.0)) for c in window]) * 1.5)
    failed = close_back_index is not None or high_volume_no_result
    acceptance_score = min(1.0, held / max(len(window), 1) + (0.15 if wick_hold else 0.0))
    failure_score = min(1.0, (0.7 if failed else 0.0) + (0.3 if immediate else 0.0))
    if failed:
        breakout_class = "failed_breakout"
    elif strength >= policy.strong_breakout_strength_min:
        breakout_class = "strong_breakout"
    elif strength >= policy.accepted_breakout_strength_min and acceptance_score >= 0.50:
        breakout_class = "accepted_breakout"
    else:
        breakout_class = "weak_but_watch"
    return {
        "breakout_class": breakout_class,
        "strength_score": strength,
        "acceptance_score": acceptance_score,
        "failure_score": failure_score,
        "close_back_inside": close_back_index is not None,
        "close_back_index": close_back_index,
        "wick_hold": wick_hold,
        "immediate_reclaim": immediate,
        "high_volume_no_result": high_volume_no_result,
        "bars_held": held,
        "mae_atr": max(adverse or [0.0]) / atr,
        "mfe_atr": max(favorable or [0.0]) / atr,
        "acceptance_status": "failed" if failed else "accepted" if acceptance_score >= 0.50 else "watch",
    }


def _observe_pullback(candles: Sequence[object], *, start_index: int, direction: str, breakout: object, zone: StructureZone, atr: float, policy: CorePolicy) -> dict[str, Any]:
    end = min(len(candles), start_index + policy.pullback_observation_bars)
    window = tuple(candles[start_index:end])
    if not window:
        return _empty_pullback()
    breakout_close = float(getattr(breakout, "close"))
    breakout_range = max(float(getattr(breakout, "high")) - float(getattr(breakout, "low")), 1e-12)
    breakout_volume = max(float(getattr(breakout, "volume", 0.0)), 1e-12)
    best_index = min(range(len(window)), key=lambda index: float(getattr(window[index], "low")) if direction == "long" else -float(getattr(window[index], "high")))
    observed_window = window[: best_index + 1]
    extreme = min(float(getattr(c, "low")) for c in observed_window) if direction == "long" else max(float(getattr(c, "high")) for c in observed_window)
    closes = [float(getattr(c, "close")) for c in observed_window]
    depth = max(0.0, breakout_close - extreme) if direction == "long" else max(0.0, extreme - breakout_close)
    invalidated = any(close < zone.zone_lower if direction == "long" else close > zone.zone_upper for close in closes)
    touched = extreme <= zone.zone_upper + atr * policy.pullback_zone_tolerance_atr if direction == "long" else extreme >= zone.zone_lower - atr * policy.pullback_zone_tolerance_atr
    close_hold = not invalidated
    ranges = [float(getattr(c, "high")) - float(getattr(c, "low")) for c in observed_window]
    bodies = [abs(float(getattr(c, "close")) - float(getattr(c, "open"))) for c in observed_window]
    volumes = [float(getattr(c, "volume", 0.0)) for c in observed_window]
    volume_ratio = _average(volumes) / breakout_volume
    range_ratio = _average(ranges) / breakout_range
    body_ratio = _average(bodies) / max(abs(float(getattr(breakout, "close")) - float(getattr(breakout, "open"))), 1e-12)
    depth_atr = depth / atr
    depth_score = max(0.0, 1.0 - abs(depth_atr - 0.8) / 1.6)
    volume_score = min(1.0, max(0.0, 1.2 - volume_ratio))
    range_score = min(1.0, max(0.0, 1.2 - range_ratio))
    body_score = min(1.0, max(0.0, 1.2 - body_ratio))
    level_hold_score = 1.0 if touched and close_hold else 0.5 if close_hold else 0.0
    time_decay_score = max(0.0, 1.0 - best_index / max(policy.pullback_observation_bars, 1))
    no_impulsive_score = 1.0 if range_ratio <= 1.2 else 0.0
    target_space_score = min(1.0, max(0.0, depth_atr / 0.8))
    health = _average([depth_score, volume_score, range_score, body_score, level_hold_score, time_decay_score, no_impulsive_score, target_space_score])
    health_class = "healthy" if health >= 0.70 else "acceptable" if health >= 0.50 else "weak_but_watch" if health >= 0.35 and not invalidated else "failed"
    midpoint = zone.zone_mid
    zone_type = "level_retest" if touched else "midpoint_retest" if abs(extreme - midpoint) <= atr * policy.pullback_zone_tolerance_atr else "shallow_pullback"
    return {
        "observed": True,
        "start_time": int(getattr(observed_window[0], "timestamp_ms")),
        "end_time": int(getattr(observed_window[-1], "timestamp_ms")),
        "end_index": start_index + best_index,
        "bars": len(observed_window),
        "delay": 0,
        "depth_atr": depth_atr,
        "depth_zone_ratio": depth / max(zone.zone_width, 1e-12),
        "depth_vs_breakout": depth / breakout_range,
        "zone_type": zone_type,
        "zone_distance_atr": abs(extreme - zone.zone_mid) / atr,
        "touched_zone": touched,
        "closed_inside_invalid": invalidated,
        "wick_inside_close_hold": touched and close_hold,
        "invalidated": invalidated,
        "volume_ratio": volume_ratio,
        "volume_contraction": volume_ratio <= 1.0,
        "range_contraction": range_ratio <= 1.0,
        "body_contraction": body_ratio <= 1.0,
        "countertrend_strength": range_ratio,
        "time_decay": best_index / max(policy.pullback_observation_bars, 1),
        "health_score": health,
        "depth_score": depth_score,
        "volume_score": volume_score,
        "range_score": range_score,
        "body_score": body_score,
        "level_hold_score": level_hold_score,
        "time_decay_score": time_decay_score,
        "no_impulsive_score": no_impulsive_score,
        "target_space_score": target_space_score,
        "health_class": health_class,
        "extreme": extreme,
        "range": max(ranges or [0.0]),
        "last_close": closes[-1],
        "avg_volume": _average(volumes),
    }


def _observe_relaunch(candles: Sequence[object], *, start_index: int, direction: str, pullback: Mapping[str, Any], atr: float, policy: CorePolicy) -> dict[str, Any]:
    if not pullback.get("observed"):
        return _empty_relaunch()
    window = tuple(candles[start_index : min(len(candles), start_index + policy.relaunch_observation_bars)])
    for offset, candle in enumerate(window, start=1):
        close, open_, high, low = (float(getattr(candle, name)) for name in ("close", "open", "high", "low"))
        candle_range = max(high - low, 1e-12)
        body_pct = abs(close - open_) / candle_range
        close_location = (close - low) / candle_range if direction == "long" else (high - close) / candle_range
        micro_break = close > float(pullback["last_close"]) if direction == "long" else close < float(pullback["last_close"])
        directional = close > open_ if direction == "long" else close < open_
        previous = window[offset - 2] if offset >= 2 else None
        two_bar = bool(previous is not None and directional and (float(getattr(previous, "close")) > float(getattr(previous, "open")) if direction == "long" else float(getattr(previous, "close")) < float(getattr(previous, "open"))))
        engulf = bool(previous is not None and high >= float(getattr(previous, "high")) and low <= float(getattr(previous, "low")) and directional)
        volume_recovery = float(getattr(candle, "volume", 0.0)) / max(float(pullback["avg_volume"]), 1e-12)
        relaunch_type = "micro_break_relaunch" if micro_break else "engulf_relaunch" if engulf else "two_bar_relaunch" if two_bar else "volume_recovery_relaunch" if volume_recovery >= 1.0 and directional else ""
        score = _average([1.0 if micro_break else 0.0, 1.0 if directional else 0.0, min(1.0, body_pct / 0.60), min(1.0, close_location / 0.80), min(1.0, volume_recovery / 1.30)])
        if relaunch_type and score >= 0.35:
            quality = "strong" if score >= 0.70 else "acceptable" if score >= 0.50 else "weak"
            return {
                "observed": True,
                "time": int(getattr(candle, "timestamp_ms")),
                "delay": offset,
                "type": relaunch_type,
                "close": close,
                "displacement_atr": abs(close - float(pullback["last_close"])) / atr,
                "body_pct": body_pct,
                "close_location": close_location,
                "volume_recovery": volume_recovery,
                "micro_break": micro_break,
                "score": score,
                "quality_class": quality,
                "low": low,
                "high": high,
            }
    return _empty_relaunch()


def _build_trade_plan(*, direction: str, breakout: object, zone: StructureZone, pullback: Mapping[str, Any], relaunch: Mapping[str, Any], atr: float, policy: CorePolicy) -> dict[str, Any]:
    if not relaunch.get("observed"):
        return _empty_trade()
    entry = float(relaunch["close"])
    buffer = atr * policy.stop_buffer_atr
    pullback_extreme = float(pullback["extreme"])
    if direction == "long":
        stop = min(pullback_extreme, zone.zone_lower) - buffer
        breakout_move = max(float(getattr(breakout, "high")) - zone.zone_mid, atr)
        target = entry + max(breakout_move, abs(entry - stop) * policy.min_gross_rr)
    else:
        stop = max(pullback_extreme, zone.zone_upper) + buffer
        breakout_move = max(zone.zone_mid - float(getattr(breakout, "low")), atr)
        target = entry - max(breakout_move, abs(entry - stop) * policy.min_gross_rr)
    distance = abs(entry - stop)
    distance_atr = distance / atr
    quality = "structural_stop_too_near" if distance_atr < policy.min_structural_stop_atr else "structural_stop_too_wide" if distance_atr > policy.max_structural_stop_atr else "valid"
    target_space = abs(target - entry)
    gross_rr = target_space / max(distance, 1e-12)
    target_quality = "good" if gross_rr >= 1.5 else "acceptable" if gross_rr >= policy.min_gross_rr else "poor"
    return {
        "stop_anchor_type": "retest_structure_invalidation_stop",
        "stop": stop,
        "stop_distance": distance,
        "stop_distance_atr": distance_atr,
        "stop_distance_zone_ratio": distance / max(zone.zone_width, 1e-12),
        "stop_distance_pullback_ratio": distance / max(float(pullback["range"]), 1e-12),
        "stop_is_structural": True,
        "stop_reason": "pullback_extreme_and_zone_invalidation_with_atr_buffer",
        "structural_stop_quality": quality,
        "target_source": "measured_move_or_minimum_rr",
        "target": target,
        "target_space": target_space,
        "target_space_atr": target_space / atr,
        "gross_RR": gross_rr,
        "nearest_obstacle_distance_atr": target_space / atr,
        "target_quality_class": target_quality,
    }


def _failure_reason(lifecycle: Mapping[str, Any], pullback: Mapping[str, Any], relaunch: Mapping[str, Any], trade: Mapping[str, Any]) -> tuple[str, list[str]]:
    reasons = []
    if lifecycle["breakout_class"] == "failed_breakout":
        reasons.append("immediate_reclaim" if lifecycle["immediate_reclaim"] else "close_back_inside_zone" if lifecycle["close_back_inside"] else "failed_breakout")
    if not pullback["observed"]:
        reasons.append("no_pullback_observed")
    elif pullback["health_class"] == "failed":
        reasons.append("pullback_health_failed")
    if not relaunch["observed"]:
        reasons.append("no_relaunch_observed")
    elif relaunch["quality_class"] == "weak":
        reasons.append("relaunch_weak")
    if trade.get("structural_stop_quality") in {"structural_stop_too_near", "structural_stop_too_wide"}:
        reasons.append(str(trade["structural_stop_quality"]))
    if trade.get("target_quality_class") == "poor":
        reasons.append("target_space_insufficient")
    return (reasons[0] if reasons else "ambiguous", reasons[1:])


def _subtype(zone: StructureZone, pullback: Mapping[str, Any], lifecycle: Mapping[str, Any]) -> str:
    if lifecycle["breakout_class"] == "weak_but_watch":
        return "weak_break_accepted_pullback"
    if pullback["zone_type"] == "shallow_pullback":
        return "shallow_pullback_momentum"
    if pullback["zone_type"] == "midpoint_retest":
        return "midpoint_retest_continuation"
    if zone.level_type in {"range_upper", "range_lower", "local_pivot_cluster"}:
        return "boundary_retest_continuation"
    if zone.level_type == "last_opposite_candle_zone":
        return "ob_like_retest_continuation"
    return "level_retest_continuation"


def _deduplicate_events(events: Sequence[BreakoutLifecycleEvent]) -> list[BreakoutLifecycleEvent]:
    output: dict[str, BreakoutLifecycleEvent] = {}
    for event in events:
        current = output.get(event.lifecycle_event_id)
        if current is None or _rank_key(event) > _rank_key(current):
            output[event.lifecycle_event_id] = event
    return [output[key] for key in sorted(output)]


def _rank_key(event: BreakoutLifecycleEvent) -> tuple[float, float, str]:
    return (event.candidate_rank_score, event.zone.structure_score, event.lifecycle_event_id)


def _empty_pullback() -> dict[str, Any]:
    return {
        "observed": False, "start_time": None, "end_time": None, "end_index": None, "bars": 0, "delay": None,
        "depth_atr": None, "depth_zone_ratio": None, "depth_vs_breakout": None, "zone_type": "ambiguous",
        "zone_distance_atr": None, "touched_zone": False, "closed_inside_invalid": False, "wick_inside_close_hold": False,
        "invalidated": False, "volume_ratio": None, "volume_contraction": False, "range_contraction": False,
        "body_contraction": False, "countertrend_strength": None, "time_decay": None, "health_score": 0.0,
        "depth_score": 0.0, "volume_score": 0.0, "range_score": 0.0, "body_score": 0.0, "level_hold_score": 0.0,
        "time_decay_score": 0.0, "no_impulsive_score": 0.0, "target_space_score": 0.0, "health_class": "failed",
        "extreme": 0.0, "range": 0.0, "last_close": 0.0, "avg_volume": 0.0,
    }


def _empty_relaunch() -> dict[str, Any]:
    return {
        "observed": False, "time": None, "delay": None, "type": "", "close": None, "displacement_atr": None,
        "body_pct": None, "close_location": None, "volume_recovery": None, "micro_break": False, "score": 0.0,
        "quality_class": "failed", "low": None, "high": None,
    }


def _empty_trade() -> dict[str, Any]:
    return {
        "stop_anchor_type": "", "stop": None, "stop_distance": None, "stop_distance_atr": None,
        "stop_distance_zone_ratio": None, "stop_distance_pullback_ratio": None, "stop_is_structural": False,
        "stop_reason": "", "structural_stop_quality": "invalid", "target_source": "", "target": None,
        "target_space": None, "target_space_atr": None, "gross_RR": None, "nearest_obstacle_distance_atr": None,
        "target_quality_class": "invalid",
    }


def _stable_id(*values: object) -> str:
    return sha256("|".join(str(value) for value in values).encode("utf-8")).hexdigest()[:24]


def _average(values: Sequence[float]) -> float:
    clean = [float(value) for value in values]
    return 0.0 if not clean else sum(clean) / len(clean)


def _compression_context(prior: Sequence[object]) -> dict[str, Any]:
    if len(prior) < 6:
        return {
            "detected": False,
            "score": 0.0,
            "range_ratio": 1.0,
            "body_ratio": 1.0,
            "volume_ratio": 1.0,
        }
    split = max(3, len(prior) // 2)
    baseline = tuple(prior[:-split]) or tuple(prior[:split])
    recent = tuple(prior[-split:])

    def ratio(values: Sequence[float], reference: Sequence[float]) -> float:
        return _average(values) / max(_average(reference), 1e-12)

    range_ratio = ratio(
        [float(getattr(candle, "high")) - float(getattr(candle, "low")) for candle in recent],
        [float(getattr(candle, "high")) - float(getattr(candle, "low")) for candle in baseline],
    )
    body_ratio = ratio(
        [abs(float(getattr(candle, "close")) - float(getattr(candle, "open"))) for candle in recent],
        [abs(float(getattr(candle, "close")) - float(getattr(candle, "open"))) for candle in baseline],
    )
    volume_ratio = ratio(
        [float(getattr(candle, "volume", 0.0)) for candle in recent],
        [float(getattr(candle, "volume", 0.0)) for candle in baseline],
    )
    score = _average(
        [
            max(0.0, min(1.0, 1.25 - range_ratio)),
            max(0.0, min(1.0, 1.25 - body_ratio)),
            max(0.0, min(1.0, 1.25 - volume_ratio)),
        ]
    )
    return {
        "detected": bool(score >= 0.35 and range_ratio <= 1.05),
        "score": score,
        "range_ratio": max(0.0, range_ratio),
        "body_ratio": max(0.0, body_ratio),
        "volume_ratio": max(0.0, volume_ratio),
    }


def _z_score(value: float, history: Sequence[float]) -> float:
    clean = [float(item) for item in history]
    if len(clean) < 2:
        return 0.0
    mean = _average(clean)
    variance = _average([(item - mean) ** 2 for item in clean])
    return 0.0 if variance <= 0 else (value - mean) / variance**0.5


__all__ = (
    "CORE_ENGINE_VERSION",
    "BreakoutLifecycleEvent",
    "CorePolicy",
    "StructureZone",
    "TrendContinuationCoreEvaluation",
    "arbitrate_trade_candidates",
    "discover_structure_zones",
    "evaluate_breakout_pullback_core_diagnostics",
    "evaluate_trend_continuation_core",
)
