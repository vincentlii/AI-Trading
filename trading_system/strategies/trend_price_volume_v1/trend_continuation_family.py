from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256


FAMILY_VARIANT_IDS = (
    "ce_lifecycle_native_light_confirm_v1",
    "ce_lifecycle_shallow_momentum_v1",
    "bp_shallow_momentum_capped_risk_v3",
)

_COMPACT_EVENT_FIELDS = {
    "lifecycle_event_id",
    "breakout_event_id",
    "level_id",
    "asset",
    "symbol",
    "inst_id",
    "inst_type",
    "venue",
    "profile",
    "timestamp_ms",
    "direction",
    "breakout_class",
    "breakout_time",
    "breakout_price",
    "breakout_close",
    "breakout_high",
    "breakout_low",
    "breakout_RVOL",
    "breakout_strength_score",
    "acceptance_end_time",
    "acceptance_status",
    "immediate_reclaim",
    "high_volume_no_result",
    "compression_context",
    "compression_score",
    "compression_range_ratio",
    "compression_body_ratio",
    "compression_volume_ratio",
    "pullback_observed",
    "pullback_start_time",
    "pullback_end_time",
    "pullback_zone_type",
    "pullback_health_class",
    "pullback_health_score",
    "relaunch_time",
    "relaunch_close",
    "relaunch_type",
    "relaunch_quality_class",
    "relaunch_score",
    "stop",
    "stop_anchor_type",
    "stop_distance",
    "stop_distance_ATR",
    "stop_buffer_ATR",
    "stop_is_structural",
    "structural_stop_quality",
    "target",
    "target_source",
    "target_space",
    "target_space_ATR",
    "gross_RR",
    "target_quality_class",
    "bp_subtype",
    "candidate_rank_score",
    "trend_state",
    "trend_direction",
    "atr_value",
    "primary_failure_reason",
    "secondary_failure_reasons",
}

_COMPACT_ZONE_FIELDS = {
    "zone_lower",
    "zone_upper",
    "zone_mid",
    "zone_width",
    "zone_width_ATR",
    "last_touch_time",
    "level_type",
    "structure_score",
}


def family_variant_setup(variant_id: str) -> str:
    if variant_id not in FAMILY_VARIANT_IDS:
        raise ValueError(f"unsupported TC family variant: {variant_id}")
    return "compression_expansion" if variant_id.startswith("ce_") else "breakout_pullback"


def select_family_candidates(
    event_rows: Sequence[Mapping[str, object]],
    variant_id: str,
) -> tuple[dict[str, object], ...]:
    setup = family_variant_setup(variant_id)
    selected_by_lifecycle: dict[str, dict[str, object]] = {}
    for event in event_rows:
        if not _variant_eligible(event, variant_id):
            continue
        lifecycle_id = str(event.get("lifecycle_event_id") or event.get("breakout_event_id") or "")
        if not lifecycle_id:
            continue
        candidate = _candidate_from_event(event, variant_id=variant_id, setup=setup)
        current = selected_by_lifecycle.get(lifecycle_id)
        if current is None or int(candidate["timestamp_ms"]) < int(current["timestamp_ms"]):
            selected_by_lifecycle[lifecycle_id] = candidate
    selected_by_signal: dict[tuple[str, str, str, int], dict[str, object]] = {}
    for candidate in selected_by_lifecycle.values():
        key = (
            str(candidate.get("asset") or ""),
            str(candidate.get("profile") or ""),
            str(candidate.get("direction") or ""),
            int(candidate.get("timestamp_ms") or 0),
        )
        current = selected_by_signal.get(key)
        if current is None or _candidate_rank(candidate) > _candidate_rank(current):
            selected_by_signal[key] = candidate
    return tuple(
        selected_by_signal[key]
        for key in sorted(selected_by_signal, key=lambda item: (item[3], item[0], item[1], item[2]))
    )


def compact_family_event(event: Mapping[str, object]) -> dict[str, object]:
    compact = {key: event.get(key) for key in _COMPACT_EVENT_FIELDS if key in event}
    zone = event.get("zone")
    if isinstance(zone, Mapping):
        compact["zone"] = {key: zone.get(key) for key in _COMPACT_ZONE_FIELDS if key in zone}
    return compact


def _variant_eligible(event: Mapping[str, object], variant_id: str) -> bool:
    if str(event.get("breakout_class") or "") == "failed_breakout":
        return False
    if bool(event.get("immediate_reclaim")) or bool(event.get("high_volume_no_result")):
        return False
    if variant_id == "ce_lifecycle_native_light_confirm_v1":
        return bool(event.get("compression_context")) and str(event.get("acceptance_status") or "") != "failed"
    shallow = (
        str(event.get("breakout_class") or "") in {"strong_breakout", "accepted_breakout"}
        and str(event.get("pullback_zone_type") or "") == "shallow_pullback"
        and str(event.get("pullback_health_class") or "") in {"healthy", "acceptable"}
        and str(event.get("relaunch_quality_class") or "") in {"strong", "acceptable"}
        and str(event.get("structural_stop_quality") or "") == "valid"
        and str(event.get("target_quality_class") or "") in {"good", "acceptable"}
    )
    if variant_id == "ce_lifecycle_shallow_momentum_v1":
        return bool(event.get("compression_context")) and shallow
    return shallow


def _candidate_from_event(
    event: Mapping[str, object],
    *,
    variant_id: str,
    setup: str,
) -> dict[str, object]:
    zone = event.get("zone") if isinstance(event.get("zone"), Mapping) else {}
    direction = str(event.get("direction") or "")
    atr = _event_atr(event, zone)
    native = variant_id == "ce_lifecycle_native_light_confirm_v1"
    signal_time = _int(event.get("acceptance_end_time") if native else event.get("relaunch_time"))
    if signal_time is None:
        signal_time = _int(event.get("timestamp_ms")) or _int(event.get("breakout_time")) or 0
    entry = _float(event.get("breakout_close") if native else event.get("relaunch_close"))
    if entry is None:
        entry = _float(event.get("breakout_price")) or _float(zone.get("zone_mid")) or 0.0
    stop, stop_anchor = _structural_stop(event, zone, entry=entry, atr=atr, direction=direction, native=native)
    target = _target(event, entry=entry, stop=stop, direction=direction, zone=zone)
    stop_distance = abs(entry - stop)
    target_space = abs(target - entry)
    lifecycle_id = str(event.get("lifecycle_event_id") or event.get("breakout_event_id"))
    candidate_id = sha256(f"{variant_id}|{lifecycle_id}".encode("utf-8")).hexdigest()[:24]
    zone_confirmed = _int(zone.get("last_touch_time")) or _int(event.get("breakout_time")) or signal_time
    breakout_time = _int(event.get("breakout_time")) or signal_time
    pullback_end = _int(event.get("pullback_end_time")) if not native else signal_time
    structural_quality = (
        "valid"
        if atr > 0 and 0.8 <= stop_distance / atr <= 3.0
        else "structural_stop_too_near"
        if atr > 0 and stop_distance / atr < 0.8
        else "structural_stop_too_wide"
    )
    return {
        "candidate_id": candidate_id,
        "event_id": lifecycle_id,
        "sweep_event_id": lifecycle_id,
        "trend_event_id": lifecycle_id,
        "breakout_pullback_event_id": lifecycle_id,
        "compression_event_id": lifecycle_id if setup == "compression_expansion" else "",
        "lifecycle_event_id": lifecycle_id,
        "breakout_event_id": event.get("breakout_event_id"),
        "level_id": event.get("level_id"),
        "row_type": "proposal_candidate",
        "eligible_for_performance": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
        "variant": variant_id,
        "setup": setup,
        "strategy_family": "compression_expansion_breakout" if setup == "compression_expansion" else "breakout_pullback_continuation",
        "asset": event.get("asset"),
        "symbol": event.get("symbol"),
        "inst_id": event.get("inst_id"),
        "inst_type": event.get("inst_type"),
        "venue": event.get("venue"),
        "profile": event.get("profile"),
        "direction": direction,
        "long_or_short": direction,
        "timestamp_ms": signal_time,
        "signal_timestamp_ms": signal_time,
        "entry_timestamp_ms": signal_time,
        "structure_timestamp_ms": zone_confirmed,
        "sweep_timestamp_ms": breakout_time,
        "reclaim_timestamp_ms": pullback_end,
        "feature_cutoff_time": signal_time,
        "structure_confirmed_time": zone_confirmed,
        "zone_confirmed_time": zone_confirmed,
        "breakout_time": breakout_time,
        "acceptance_end_time": _int(event.get("acceptance_end_time")) or signal_time,
        "pullback_start_time": event.get("pullback_start_time") if not native else signal_time,
        "pullback_end_time": pullback_end,
        "pullback_confirmed_time": pullback_end,
        "relaunch_time": _int(event.get("relaunch_time")) if not native else signal_time,
        "signal_time": signal_time,
        "entry_time": signal_time,
        "bar_confirmed": True,
        "no_lookahead_safe": True,
        "entry_policy": "light_confirmation" if native else "shallow_pullback_relaunch",
        "entry_reference_price": entry,
        "actual_entry_price_if_simulated": entry,
        "signal_close_price": entry,
        "stop_price": stop,
        "target_price": target,
        "atr_value": atr,
        "structure_level": _float(zone.get("zone_mid")) or entry,
        "sweep_extreme": _float(event.get("breakout_low" if direction == "short" else "breakout_high")) or entry,
        "sweep_extreme_low": _float(event.get("breakout_low")) or entry,
        "sweep_extreme_high": _float(event.get("breakout_high")) or entry,
        "stop_anchor_type": stop_anchor,
        "stop_formula_used": stop_anchor,
        "stop_is_structural": True,
        "structural_stop_quality": structural_quality,
        "stop_distance": stop_distance,
        "stop_distance_atr": None if atr <= 0 else stop_distance / atr,
        "target_space": target_space,
        "target_space_atr": None if atr <= 0 else target_space / atr,
        "gross_RR": None if stop_distance <= 0 else target_space / stop_distance,
        "breakout_class": event.get("breakout_class"),
        "breakout_RVOL": event.get("breakout_RVOL"),
        "breakout_score": event.get("breakout_strength_score"),
        "compression_context": bool(event.get("compression_context")),
        "compression_score": event.get("compression_score"),
        "pullback_health_class": event.get("pullback_health_class"),
        "pullback_quality_score": event.get("pullback_health_score"),
        "pullback_zone_type": event.get("pullback_zone_type"),
        "relaunch_quality_class": event.get("relaunch_quality_class"),
        "relaunch_score": event.get("relaunch_score"),
        "bp_subtype": event.get("bp_subtype"),
        "candidate_quality_tag": _quality_tag(event, native=native),
        "candidate_rank_score": event.get("candidate_rank_score"),
        "trend_state": event.get("trend_state", "unknown"),
        "trend_direction": event.get("trend_direction", ""),
        "countertrend": False,
        "candidate_generation_reason": f"tc_family_shared_lifecycle:{variant_id}",
        "candidate_lifecycle_status": "proposal_candidate",
        "candidate_lifecycle_reason": "shared_lifecycle_family_selector",
        "primary_failure_reason": "",
        "secondary_failure_reasons": [],
        "setup_evidence": dict(event),
    }


def _structural_stop(
    event: Mapping[str, object],
    zone: Mapping[str, object],
    *,
    entry: float,
    atr: float,
    direction: str,
    native: bool,
) -> tuple[float, str]:
    if not native and _float(event.get("stop")) is not None:
        return float(event["stop"]), str(event.get("stop_anchor_type") or "retest_structure_invalidation_stop")
    buffer = atr * 0.15
    if direction == "long":
        return (_float(zone.get("zone_lower")) or entry - atr) - buffer, "compression_zone_opposite_edge_stop"
    return (_float(zone.get("zone_upper")) or entry + atr) + buffer, "compression_zone_opposite_edge_stop"


def _target(
    event: Mapping[str, object],
    *,
    entry: float,
    stop: float,
    direction: str,
    zone: Mapping[str, object],
) -> float:
    existing = _float(event.get("target"))
    if existing is not None and ((direction == "long" and existing > entry) or (direction == "short" and existing < entry)):
        return existing
    distance = max(abs(entry - stop) * 1.2, _float(zone.get("zone_width")) or 0.0)
    return entry + distance if direction == "long" else entry - distance


def _event_atr(event: Mapping[str, object], zone: Mapping[str, object]) -> float:
    direct = _float(event.get("atr_value"))
    if direct is not None and direct > 0:
        return direct
    distance = _float(event.get("stop_distance"))
    multiple = _float(event.get("stop_distance_ATR"))
    if distance is not None and multiple is not None and multiple > 0:
        return distance / multiple
    width = _float(zone.get("zone_width"))
    width_atr = _float(zone.get("zone_width_ATR"))
    if width is not None and width_atr is not None and width_atr > 0:
        return width / width_atr
    return max(abs((_float(event.get("breakout_high")) or 0.0) - (_float(event.get("breakout_low")) or 0.0)), 1e-12)


def _quality_tag(event: Mapping[str, object], *, native: bool) -> str:
    if native:
        return "compression_native_light_confirm"
    health = str(event.get("pullback_health_class") or "")
    relaunch = str(event.get("relaunch_quality_class") or "")
    return "high_quality_candidate" if health == "healthy" and relaunch == "strong" else "reasonable_near_miss"


def _candidate_rank(candidate: Mapping[str, object]) -> tuple[float, float, float, str]:
    return (
        _float(candidate.get("candidate_rank_score")) or 0.0,
        _float(candidate.get("compression_score")) or 0.0,
        _float(candidate.get("breakout_score")) or 0.0,
        str(candidate.get("lifecycle_event_id") or ""),
    )


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


__all__ = (
    "FAMILY_VARIANT_IDS",
    "compact_family_event",
    "family_variant_setup",
    "select_family_candidates",
)
