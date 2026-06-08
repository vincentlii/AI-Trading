from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from trading_system.config.loader import BacktestPresetConfig
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.indicators.regime import average_true_range
from trading_system.timeframe_profiles import get_profile


ANATOMY_FIELDS = (
    "candidate_id",
    "timestamp",
    "timestamp_ms",
    "asset",
    "profile",
    "setup",
    "direction",
    "long_or_short",
    "signal_time",
    "entry_time",
    "structure_time",
    "sweep_time",
    "reclaim_time",
    "bars_structure_to_sweep",
    "bars_sweep_to_reclaim",
    "bars_reclaim_to_signal",
    "bars_signal_to_entry",
    "bars_reclaim_to_entry",
    "bars_sweep_to_entry",
    "candidate_lifecycle_status",
    "candidate_lifecycle_reason",
    "sweep_event_id",
    "candidate_generation_reason",
    "structure_level",
    "structure_level_type",
    "structure_timeframe",
    "structure_level_timestamp",
    "structure_level_age_bars",
    "structure_level_age_hours",
    "structure_level_touch_count",
    "sweep_extreme_price",
    "reclaim_price",
    "signal_close_price",
    "entry_reference_price",
    "actual_entry_price_if_simulated",
    "entry_price",
    "distance_reclaim_to_signal_abs",
    "distance_reclaim_to_signal_atr_entry_tf",
    "distance_reclaim_to_entry_abs",
    "distance_reclaim_to_entry_atr_entry_tf",
    "distance_sweep_extreme_to_entry_atr_entry_tf",
    "distance_stop_to_entry_atr_entry_tf",
    "distance_entry_to_structure_abs",
    "distance_entry_to_structure_pct",
    "distance_entry_to_structure_atr_entry_tf",
    "distance_entry_to_structure_atr_structure_tf",
    "distance_entry_to_reclaim_abs",
    "distance_entry_to_reclaim_pct",
    "distance_entry_to_reclaim_atr_entry_tf",
    "distance_entry_to_reclaim_atr_structure_tf",
    "distance_structure_to_sweep_abs",
    "distance_structure_to_sweep_pct",
    "distance_structure_to_sweep_atr_entry_tf",
    "distance_structure_to_sweep_atr_structure_tf",
    "sweep_atr_multiple",
    "sweep_wick_ratio",
    "atr_entry_tf",
    "atr_structure_tf",
    "atr_used_for_stop",
    "atr_used_for_stop_timeframe",
    "atr_entry_tf_timestamp",
    "atr_structure_tf_timestamp",
    "invalidation_mode",
    "invalidation_mode_config",
    "invalidation_mode_effective",
    "invalidation_buffer_atr",
    "stop_formula_used",
    "stop_formula_fallback_reason",
    "sweep_extreme_low",
    "sweep_extreme_high",
    "sweep_extreme_price_used",
    "stop_price",
    "stop_distance_abs",
    "stop_distance_pct",
    "stop_distance_atr_entry_tf",
    "stop_distance_atr_structure_tf",
    "stop_atr_multiple_entry_tf",
    "stop_atr_multiple_structure_tf",
    "stop_atr_multiple_used",
    "stop_bucket",
    "target_price",
    "target_source",
    "target_distance_abs",
    "target_distance_pct",
    "target_r_entry_tf",
    "target_r_structure_tf",
    "min_target_r",
    "min_target_r_pass",
    "rolling_rvol",
    "tod_dow_rvol",
    "volume_baseline_mode",
    "volume_bucket_sample_count",
    "used_fallback_volume_baseline",
    "reclaim_rvol",
    "reclaim_rvol_tier",
    "reclaim_bars",
    "choch_detected",
    "bos_detected",
    "trend_state",
    "trend_aligned",
    "final_reject_stage",
    "final_reject_reason",
    "formal_approved",
    "shadow_approved_5",
    "shadow_approved_8",
    "risk_reject_reason",
    "structure_reject_reason",
    "volume_reject_reason",
    "compression_box_height",
    "box_height_ATR",
    "box_duration",
    "box_upper",
    "box_lower",
    "box_midpoint",
    "breakout_displacement",
    "breakout_displacement_ATR",
    "breakout_displacement_box_ratio",
    "breakout_score",
    "breakout_close_location",
    "breakout_body_pct",
    "breakout_range_vs_ATR",
    "breakout_range_vs_box_height",
    "close_outside_box_distance_ATR",
    "breakout_RVOL",
    "breakout_volume_z",
    "volume_expansion_vs_compression",
    "range_expansion_vs_compression",
    "body_expansion_vs_compression",
    "acceptance_window_bars",
    "close_back_inside_box",
    "close_back_inside_box_bar_index",
    "close_below_breakout_level",
    "close_above_breakout_level",
    "midpoint_lost_after_breakout",
    "wick_back_inside_but_close_hold",
    "boundary_hold_after_breakout",
    "midpoint_hold_after_breakout",
    "followthrough_bar_count",
    "max_favorable_excursion_before_retest",
    "max_adverse_excursion_before_acceptance",
    "high_volume_no_result_after_breakout",
    "primary_failure_reason",
    "secondary_failure_reasons",
    "ce_subtype",
    "midpoint_hold",
    "boundary_hold",
    "retest_hold",
    "retest_depth_ATR",
    "bars_to_retest",
    "entry_to_stop",
    "stop_distance_ATR",
    "stop_distance_box_ratio",
    "stop_anchor_type",
    "stop_buffer_ATR",
    "stop_inside_box",
    "target_space",
    "gross_RR",
    "cost_adjusted_RR",
    "cost_per_R",
    "net_R",
    "risk_engine_reject_reason",
    "margin_required",
    "notional",
    "position_size",
    "portfolio_heat_after_entry",
    "candidate_quality_tag",
    "breakout_pullback_event_id",
    "breakout_reference_level",
    "breakout_level_type",
    "breakout_close",
    "breakout_displacement_level_ratio",
    "breakout_range_expansion",
    "breakout_body_expansion",
    "acceptance_end_time",
    "close_back_inside_level",
    "close_back_inside_bar_index",
    "wick_back_but_close_hold",
    "immediate_reclaim",
    "high_volume_no_result",
    "acceptance_score",
    "acceptance_status",
    "pullback_start_time",
    "pullback_end_time",
    "pullback_depth_ATR",
    "pullback_depth_vs_breakout",
    "pullback_depth_vs_box",
    "pullback_bars",
    "pullback_volume_ratio_vs_breakout",
    "pullback_volume_contraction",
    "pullback_range_contraction",
    "pullback_body_contraction",
    "pullback_close_location",
    "pullback_zone_type",
    "pullback_zone_distance_ATR",
    "pullback_held_level",
    "pullback_invalidated",
    "pullback_quality_score",
    "relaunch_time",
    "relaunch_close",
    "relaunch_displacement_ATR",
    "relaunch_body_pct",
    "relaunch_close_location",
    "relaunch_volume_recovery",
    "relaunch_breaks_micro_structure",
    "relaunch_score",
    "stop_distance_level_ratio",
    "bp_subtype",
    "stop_distance_too_near_attribution",
    "margin_reject_attribution",
    "near_miss_shadow",
)


def build_candidate_anatomy_rows(
    *,
    repository,
    filter_rows: Sequence[Mapping[str, object]],
    preset: BacktestPresetConfig | None = None,
) -> tuple[dict[str, object], ...]:
    candles_cache: dict[tuple[str, str, str, str], tuple[object, ...]] = {}
    rows: list[dict[str, object]] = []
    for row in filter_rows:
        if str(row.get("setup", "")) == "compression_expansion":
            rows.append(_compression_expansion_anatomy_row(row))
            continue
        if str(row.get("setup", "")) == "breakout_pullback":
            rows.append(_breakout_pullback_anatomy_row(row))
            continue
        if str(row.get("setup", "")) != "liquidity_reversal":
            continue
        profile = get_profile(str(row["profile"]))
        target_key = (str(row["inst_id"]), str(row.get("venue", "okx")), str(row.get("inst_type", "SWAP")))
        entry_candles = _load_cached(candles_cache, repository, *target_key, profile.entry_timeframe)
        structure_candles = _load_cached(candles_cache, repository, *target_key, profile.structure_timeframe)

        timestamp_ms = int(row["timestamp_ms"])
        sweep_timestamp_ms = _optional_int(row.get("sweep_timestamp_ms")) or timestamp_ms
        entry_candle = _infer_entry_candle(entry_candles, row, timestamp_ms)
        structure_info = _structure_level_info(row, structure_candles, sweep_timestamp_ms)
        entry_atr, entry_atr_ts = _atr_at(entry_candles, int(getattr(entry_candle, "timestamp_ms")) if entry_candle is not None else timestamp_ms)
        structure_atr, structure_atr_ts = _atr_at(structure_candles, timestamp_ms)

        entry_price = _float(row.get("entry_price"), _float(row.get("entry_reference_price"), 0.0))
        structure_level = _float(row.get("structure_level"), 0.0)
        reclaim_price = _optional_float(row.get("reclaim_price"))
        signal_close = _float(row.get("signal_close_price"), _float(row.get("entry_reference_price"), 0.0))
        sweep_extreme = _float(row.get("sweep_extreme_price", row.get("sweep_extreme")), 0.0)
        stop_price = _float(row.get("stop_price"), 0.0)
        target_price = _float(row.get("target_price"), 0.0)
        stop_distance = abs(entry_price - stop_price)
        target_distance = abs(target_price - entry_price)
        atr_used = _float(row.get("atr_value"), 0.0)
        min_target_r = _float(row.get("min_liquidity_reversal_target_r"), 1.5)
        target_r = _ratio(target_distance, stop_distance)
        target_r_value = 0.0 if target_r is None else target_r

        anatomy = {
            "candidate_id": row.get("candidate_id", ""),
            "timestamp": _iso(timestamp_ms),
            "timestamp_ms": timestamp_ms,
            "asset": row.get("asset", ""),
            "profile": profile.key,
            "setup": row.get("setup", ""),
            "direction": row.get("direction", ""),
            "long_or_short": row.get("long_or_short", row.get("direction", "")),
            "signal_time": _iso(timestamp_ms),
            "entry_time": _iso(int(getattr(entry_candle, "timestamp_ms"))) if entry_candle is not None else "",
            "structure_time": _iso(_optional_int(row.get("structure_timestamp_ms"))),
            "sweep_time": _iso(_optional_int(row.get("sweep_timestamp_ms"))),
            "reclaim_time": _iso(_optional_int(row.get("reclaim_timestamp_ms"))),
            "bars_structure_to_sweep": row.get("bars_structure_to_sweep", ""),
            "bars_sweep_to_reclaim": row.get("bars_sweep_to_reclaim", ""),
            "bars_reclaim_to_signal": row.get("bars_reclaim_to_signal", ""),
            "bars_signal_to_entry": row.get("bars_signal_to_entry", ""),
            "bars_reclaim_to_entry": row.get("bars_reclaim_to_entry", ""),
            "bars_sweep_to_entry": row.get("bars_sweep_to_entry", ""),
            "candidate_lifecycle_status": row.get("candidate_lifecycle_status", ""),
            "candidate_lifecycle_reason": row.get("candidate_lifecycle_reason", ""),
            "sweep_event_id": row.get("sweep_event_id", ""),
            "candidate_generation_reason": row.get("candidate_generation_reason", ""),
            "structure_level": structure_level,
            "structure_level_type": structure_info["structure_level_type"],
            "structure_timeframe": profile.structure_timeframe,
            "structure_level_timestamp": _iso(structure_info.get("timestamp_ms")),
            "structure_level_age_bars": structure_info.get("age_bars"),
            "structure_level_age_hours": structure_info.get("age_hours"),
            "structure_level_touch_count": structure_info.get("touch_count"),
            "sweep_extreme_price": sweep_extreme,
            "reclaim_price": reclaim_price,
            "signal_close_price": signal_close,
            "entry_reference_price": row.get("entry_reference_price", ""),
            "actual_entry_price_if_simulated": row.get("actual_entry_price_if_simulated", ""),
            "entry_price": entry_price,
            "distance_reclaim_to_signal_abs": None if reclaim_price is None else abs(signal_close - reclaim_price),
            "distance_reclaim_to_signal_atr_entry_tf": None if reclaim_price is None else _ratio(abs(signal_close - reclaim_price), entry_atr),
            "distance_reclaim_to_entry_abs": None if reclaim_price is None else abs(entry_price - reclaim_price),
            "distance_reclaim_to_entry_atr_entry_tf": None if reclaim_price is None else _ratio(abs(entry_price - reclaim_price), entry_atr),
            "distance_sweep_extreme_to_entry_atr_entry_tf": _ratio(abs(entry_price - sweep_extreme), entry_atr),
            "distance_stop_to_entry_atr_entry_tf": _ratio(stop_distance, entry_atr),
            "distance_entry_to_structure_abs": abs(entry_price - structure_level),
            "distance_entry_to_structure_pct": _ratio(abs(entry_price - structure_level), entry_price),
            "distance_entry_to_structure_atr_entry_tf": _ratio(abs(entry_price - structure_level), entry_atr),
            "distance_entry_to_structure_atr_structure_tf": _ratio(abs(entry_price - structure_level), structure_atr),
            "distance_entry_to_reclaim_abs": None if reclaim_price is None else abs(entry_price - reclaim_price),
            "distance_entry_to_reclaim_pct": None if reclaim_price is None else _ratio(abs(entry_price - reclaim_price), entry_price),
            "distance_entry_to_reclaim_atr_entry_tf": None if reclaim_price is None else _ratio(abs(entry_price - reclaim_price), entry_atr),
            "distance_entry_to_reclaim_atr_structure_tf": None if reclaim_price is None else _ratio(abs(entry_price - reclaim_price), structure_atr),
            "distance_structure_to_sweep_abs": abs(structure_level - sweep_extreme),
            "distance_structure_to_sweep_pct": _ratio(abs(structure_level - sweep_extreme), structure_level),
            "distance_structure_to_sweep_atr_entry_tf": _ratio(abs(structure_level - sweep_extreme), entry_atr),
            "distance_structure_to_sweep_atr_structure_tf": _ratio(abs(structure_level - sweep_extreme), structure_atr),
            "sweep_atr_multiple": row.get("sweep_atr_multiple", ""),
            "sweep_wick_ratio": row.get("wick_ratio", ""),
            "atr_entry_tf": entry_atr,
            "atr_structure_tf": structure_atr,
            "atr_used_for_stop": atr_used,
            "atr_used_for_stop_timeframe": profile.trend_timeframe,
            "atr_entry_tf_timestamp": _iso(entry_atr_ts),
            "atr_structure_tf_timestamp": _iso(structure_atr_ts),
            "invalidation_mode": row.get("invalidation_mode", ""),
            "invalidation_mode_config": row.get("invalidation_mode_config", row.get("invalidation_mode", "")),
            "invalidation_mode_effective": row.get("invalidation_mode_effective", row.get("invalidation_mode", "")),
            "invalidation_buffer_atr": row.get("invalidation_buffer_atr", ""),
            "stop_formula_used": _stop_formula_used(row, atr_used),
            "stop_formula_fallback_reason": row.get("stop_formula_fallback_reason", ""),
            "sweep_extreme_low": row.get("sweep_extreme_low", ""),
            "sweep_extreme_high": row.get("sweep_extreme_high", ""),
            "sweep_extreme_price_used": row.get("sweep_extreme_price_used", sweep_extreme),
            "stop_price": stop_price,
            "stop_distance_abs": stop_distance,
            "stop_distance_pct": _ratio(stop_distance, entry_price),
            "stop_distance_atr_entry_tf": _ratio(stop_distance, entry_atr),
            "stop_distance_atr_structure_tf": _ratio(stop_distance, structure_atr),
            "stop_atr_multiple_entry_tf": _ratio(stop_distance, entry_atr),
            "stop_atr_multiple_structure_tf": _ratio(stop_distance, structure_atr),
            "stop_atr_multiple_used": row.get("stop_atr_multiple", _ratio(stop_distance, atr_used)),
            "target_price": target_price,
            "target_source": _target_source(row, stop_distance, target_distance),
            "target_distance_abs": target_distance,
            "target_distance_pct": _ratio(target_distance, entry_price),
            "target_r_entry_tf": target_r_value,
            "target_r_structure_tf": target_r_value,
            "min_target_r": min_target_r,
            "min_target_r_pass": target_r_value >= min_target_r,
            "rolling_rvol": row.get("rolling_rvol", ""),
            "tod_dow_rvol": row.get("tod_dow_rvol", ""),
            "volume_baseline_mode": row.get("volume_baseline_mode", ""),
            "volume_bucket_sample_count": row.get("volume_bucket_sample_count", ""),
            "used_fallback_volume_baseline": row.get("used_fallback_volume_baseline", ""),
            "reclaim_rvol": row.get("reclaim_rvol", ""),
            "reclaim_rvol_tier": row.get("reclaim_quality", _reclaim_quality(_optional_float(row.get("reclaim_rvol")))),
            "reclaim_bars": row.get("reclaim_bars", ""),
            "choch_detected": row.get("choch_detected", ""),
            "bos_detected": row.get("bos_detected", ""),
            "trend_state": row.get("trend_state", ""),
            "trend_aligned": row.get("trend_direction") in ("", row.get("direction")),
            "final_reject_stage": row.get("reject_stage", ""),
            "final_reject_reason": row.get("reject_reason", ""),
            "formal_approved": row.get("formal_approved", False),
            "shadow_approved_5": row.get("shadow_approved_5", False),
            "shadow_approved_8": row.get("shadow_approved_8", False),
            "risk_reject_reason": _risk_reason(row),
            "structure_reject_reason": _reason_if(row, {"wick_ratio_too_low", "sweep_too_far", "reclaim_timeout", "high_reclaim_rvol", "choch_required_missing"}),
            "volume_reject_reason": _reason_if(row, {"low_sweep_rvol"}),
        }
        anatomy["stop_bucket"] = _stop_bucket(anatomy["stop_atr_multiple_entry_tf"])
        rows.append(anatomy)
    return tuple(rows)


def _compression_expansion_anatomy_row(row: Mapping[str, object]) -> dict[str, object]:
    timestamp_ms = _optional_int(row.get("timestamp_ms"))
    entry = _optional_float(row.get("entry_price")) or _optional_float(row.get("entry_reference_price")) or 0.0
    stop = _optional_float(row.get("stop_price")) or 0.0
    target = _optional_float(row.get("target_price")) or 0.0
    atr = _optional_float(row.get("atr_value")) or 0.0
    stop_distance = abs(entry - stop)
    target_space = _optional_float(row.get("target_space"))
    if target_space is None:
        target_space = abs(target - entry)
    gross_rr = _optional_float(row.get("gross_RR")) or _optional_float(row.get("target_r")) or _ratio(target_space, stop_distance) or 0.0
    cost_per_r = _optional_float(row.get("cost_per_R")) or _optional_float(row.get("estimated_cost_r")) or 0.0
    cost_adjusted_rr = _optional_float(row.get("cost_adjusted_RR"))
    if cost_adjusted_rr is None:
        cost_adjusted_rr = gross_rr - cost_per_r
    risk_reason = _risk_reason(row)
    stop_attr = _ce_stop_near_attribution(row, stop_distance, atr)
    margin_attr = _ce_margin_attribution(row, stop_distance, atr)
    near_miss = _ce_near_miss_shadow(row, risk_reason, stop_attr, margin_attr, gross_rr, cost_adjusted_rr)
    quality = str(row.get("candidate_quality_tag") or "")
    if not quality:
        quality = near_miss if near_miss in {"low_quality_reject", "reasonable_near_miss"} else "medium_quality_candidate"
    return {
        "row_type": "diagnostic_only",
        "candidate_id": row.get("candidate_id", ""),
        "timestamp": _iso(timestamp_ms),
        "timestamp_ms": timestamp_ms,
        "asset": row.get("asset", ""),
        "profile": row.get("profile", ""),
        "setup": "compression_expansion",
        "direction": row.get("direction", ""),
        "long_or_short": row.get("long_or_short", row.get("direction", "")),
        "signal_time": _iso(_optional_int(row.get("signal_time")) or timestamp_ms),
        "entry_time": _iso(_optional_int(row.get("entry_time")) or _optional_int(row.get("entry_timestamp_ms"))),
        "structure_time": _iso(_optional_int(row.get("compression_end_time"))),
        "sweep_time": _iso(_optional_int(row.get("breakout_time"))),
        "reclaim_time": _iso(_optional_int(row.get("confirmation_time"))),
        "candidate_lifecycle_status": row.get("candidate_lifecycle_status", ""),
        "candidate_lifecycle_reason": row.get("candidate_lifecycle_reason", ""),
        "sweep_event_id": row.get("sweep_event_id", row.get("compression_event_id", "")),
        "candidate_generation_reason": row.get("candidate_generation_reason", ""),
        "structure_level": row.get("structure_level", ""),
        "structure_level_type": "compression_box_upper" if row.get("direction") == "long" else "compression_box_lower",
        "entry_price": entry,
        "entry_reference_price": row.get("entry_reference_price", entry),
        "actual_entry_price_if_simulated": row.get("actual_entry_price_if_simulated", entry),
        "stop_price": stop,
        "target_price": target,
        "atr_used_for_stop": atr,
        "atr_used_for_stop_timeframe": row.get("atr_used_for_stop_timeframe", ""),
        "stop_formula_used": row.get("stop_formula_used", ""),
        "stop_price_distance_abs": stop_distance,
        "stop_distance_abs": stop_distance,
        "stop_distance_pct": _ratio(stop_distance, entry),
        "stop_atr_multiple_entry_tf": _optional_float(row.get("stop_distance_atr")) or _ratio(stop_distance, atr),
        "stop_atr_multiple_used": _optional_float(row.get("stop_distance_atr")) or _ratio(stop_distance, atr),
        "stop_bucket": _stop_bucket(_optional_float(row.get("stop_distance_atr")) or _ratio(stop_distance, atr)),
        "target_distance_abs": target_space,
        "target_r_entry_tf": gross_rr,
        "target_r_structure_tf": gross_rr,
        "min_target_r": row.get("min_target_r", ""),
        "min_target_r_pass": gross_rr >= 1.0,
        "rolling_rvol": row.get("breakout_rvol", row.get("rolling_rvol", "")),
        "tod_dow_rvol": row.get("tod_dow_rvol", ""),
        "volume_baseline_mode": row.get("volume_baseline_mode", ""),
        "volume_bucket_sample_count": row.get("volume_bucket_sample_count", ""),
        "used_fallback_volume_baseline": row.get("used_fallback_volume_baseline", ""),
        "bos_detected": row.get("bos_detected", ""),
        "trend_state": row.get("trend_state", ""),
        "trend_aligned": row.get("trend_direction") in ("", row.get("direction")),
        "final_reject_stage": row.get("reject_stage", ""),
        "final_reject_reason": row.get("reject_reason", ""),
        "formal_approved": row.get("formal_approved", False),
        "shadow_approved_5": row.get("shadow_approved_5", False),
        "shadow_approved_8": row.get("shadow_approved_8", False),
        "risk_reject_reason": risk_reason,
        "risk_engine_reject_reason": risk_reason,
        "structure_reject_reason": row.get("reject_reason", "") if row.get("reject_stage") in {"price_action", "compression_quality"} else "",
        "volume_reject_reason": row.get("reject_reason", "") if row.get("reject_stage") == "volume_filter" else "",
        "compression_box_height": row.get("compression_box_height", ""),
        "box_height_ATR": row.get("compression_box_atr", ""),
        "box_duration": _ce_box_duration(row),
        "box_upper": row.get("compression_high", ""),
        "box_lower": row.get("compression_low", ""),
        "box_midpoint": row.get("compression_midpoint", ""),
        "breakout_displacement": row.get("breakout_range", ""),
        "breakout_displacement_ATR": row.get("breakout_displacement_atr", ""),
        "breakout_displacement_box_ratio": row.get("breakout_displacement_box_ratio", ""),
        "breakout_score": row.get("breakout_score", ""),
        "breakout_close_location": row.get("breakout_close_location", ""),
        "breakout_body_pct": row.get("breakout_body_pct", row.get("breakout_body_ratio", "")),
        "breakout_range_vs_ATR": row.get("breakout_range_vs_ATR", ""),
        "breakout_range_vs_box_height": row.get("breakout_range_vs_box_height", ""),
        "close_outside_box_distance_ATR": row.get("close_outside_box_distance_ATR", ""),
        "breakout_RVOL": row.get("breakout_rvol", ""),
        "breakout_volume_z": row.get("breakout_volume_z", ""),
        "volume_expansion_vs_compression": row.get("volume_expansion_vs_compression", ""),
        "range_expansion_vs_compression": row.get("range_expansion_vs_compression", ""),
        "body_expansion_vs_compression": row.get("body_expansion_vs_compression", ""),
        "acceptance_window_bars": row.get("acceptance_window_bars", ""),
        "close_back_inside_box": row.get("close_back_inside_box", ""),
        "close_back_inside_box_bar_index": row.get("close_back_inside_box_bar_index", ""),
        "close_below_breakout_level": row.get("close_below_breakout_level", ""),
        "close_above_breakout_level": row.get("close_above_breakout_level", ""),
        "midpoint_lost_after_breakout": row.get("midpoint_lost_after_breakout", ""),
        "wick_back_inside_but_close_hold": row.get("wick_back_inside_but_close_hold", ""),
        "boundary_hold_after_breakout": row.get("boundary_hold_after_breakout", ""),
        "midpoint_hold_after_breakout": row.get("midpoint_hold_after_breakout", ""),
        "followthrough_bar_count": row.get("followthrough_bar_count", ""),
        "max_favorable_excursion_before_retest": row.get("max_favorable_excursion_before_retest", ""),
        "max_adverse_excursion_before_acceptance": row.get("max_adverse_excursion_before_acceptance", ""),
        "high_volume_no_result_after_breakout": row.get("high_volume_no_result_after_breakout", ""),
        "primary_failure_reason": row.get("primary_failure_reason", ""),
        "secondary_failure_reasons": row.get("secondary_failure_reasons", ""),
        "ce_subtype": row.get("ce_subtype", ""),
        "midpoint_hold": row.get("midpoint_hold", ""),
        "boundary_hold": row.get("boundary_hold", ""),
        "retest_hold": row.get("retest_hold", ""),
        "retest_depth_ATR": row.get("retest_depth_atr", ""),
        "bars_to_retest": row.get("bars_to_retest", ""),
        "entry_to_stop": row.get("entry_to_stop", stop_distance),
        "stop_distance_ATR": row.get("stop_distance_atr", _ratio(stop_distance, atr)),
        "stop_distance_box_ratio": row.get("stop_distance_box_ratio", ""),
        "stop_anchor_type": row.get("stop_anchor_type", ""),
        "stop_buffer_ATR": row.get("stop_buffer_atr", ""),
        "stop_inside_box": row.get("stop_inside_box", ""),
        "target_space": target_space,
        "gross_RR": gross_rr,
        "cost_adjusted_RR": cost_adjusted_rr,
        "cost_per_R": cost_per_r,
        "net_R": row.get("net_R", ""),
        "margin_required": row.get("margin_required", ""),
        "notional": row.get("notional", ""),
        "position_size": row.get("position_size", row.get("quantity", "")),
        "portfolio_heat_after_entry": row.get("portfolio_heat_after_entry", row.get("portfolio_heat", "")),
        "candidate_quality_tag": quality,
        "stop_distance_too_near_attribution": stop_attr,
        "margin_reject_attribution": margin_attr,
        "near_miss_shadow": near_miss,
    }


def _breakout_pullback_anatomy_row(row: Mapping[str, object]) -> dict[str, object]:
    anatomy = _compression_expansion_anatomy_row(row)
    anatomy.update(
        {
            "setup": "breakout_pullback",
            "structure_time": _iso(_optional_int(row.get("breakout_time"))),
            "sweep_time": _iso(_optional_int(row.get("breakout_time"))),
            "reclaim_time": _iso(_optional_int(row.get("pullback_end_time"))),
            "structure_level": row.get("breakout_reference_level", row.get("structure_level", "")),
            "structure_level_type": row.get("breakout_level_type", ""),
            "sweep_event_id": row.get("sweep_event_id", row.get("breakout_pullback_event_id", "")),
            "breakout_pullback_event_id": row.get("breakout_pullback_event_id", ""),
            "breakout_reference_level": row.get("breakout_reference_level", ""),
            "breakout_level_type": row.get("breakout_level_type", ""),
            "breakout_close": row.get("breakout_close", ""),
            "breakout_displacement_ATR": row.get("breakout_displacement_ATR", row.get("breakout_displacement_atr", "")),
            "breakout_displacement_level_ratio": row.get("breakout_displacement_level_ratio", ""),
            "breakout_range_expansion": row.get("breakout_range_expansion", ""),
            "breakout_body_expansion": row.get("breakout_body_expansion", ""),
            "breakout_RVOL": row.get("breakout_RVOL", row.get("breakout_rvol", "")),
            "acceptance_end_time": row.get("acceptance_end_time", ""),
            "close_back_inside_level": row.get("close_back_inside_level", ""),
            "close_back_inside_bar_index": row.get("close_back_inside_bar_index", ""),
            "wick_back_but_close_hold": row.get("wick_back_but_close_hold", ""),
            "immediate_reclaim": row.get("immediate_reclaim", ""),
            "high_volume_no_result": row.get("high_volume_no_result", ""),
            "acceptance_score": row.get("acceptance_score", ""),
            "acceptance_status": row.get("acceptance_status", ""),
            "pullback_start_time": row.get("pullback_start_time", ""),
            "pullback_end_time": row.get("pullback_end_time", ""),
            "pullback_depth_ATR": row.get("pullback_depth_ATR", ""),
            "pullback_depth_vs_breakout": row.get("pullback_depth_vs_breakout", ""),
            "pullback_depth_vs_box": row.get("pullback_depth_vs_box", ""),
            "pullback_bars": row.get("pullback_bars", ""),
            "pullback_volume_ratio_vs_breakout": row.get("pullback_volume_ratio_vs_breakout", ""),
            "pullback_volume_contraction": row.get("pullback_volume_contraction", ""),
            "pullback_range_contraction": row.get("pullback_range_contraction", ""),
            "pullback_body_contraction": row.get("pullback_body_contraction", ""),
            "pullback_close_location": row.get("pullback_close_location", ""),
            "pullback_zone_type": row.get("pullback_zone_type", ""),
            "pullback_zone_distance_ATR": row.get("pullback_zone_distance_ATR", ""),
            "pullback_held_level": row.get("pullback_held_level", ""),
            "pullback_invalidated": row.get("pullback_invalidated", ""),
            "pullback_quality_score": row.get("pullback_quality_score", ""),
            "relaunch_time": row.get("relaunch_time", ""),
            "relaunch_close": row.get("relaunch_close", ""),
            "relaunch_displacement_ATR": row.get("relaunch_displacement_ATR", ""),
            "relaunch_body_pct": row.get("relaunch_body_pct", ""),
            "relaunch_close_location": row.get("relaunch_close_location", ""),
            "relaunch_volume_recovery": row.get("relaunch_volume_recovery", ""),
            "relaunch_breaks_micro_structure": row.get("relaunch_breaks_micro_structure", ""),
            "relaunch_score": row.get("relaunch_score", ""),
            "stop_distance_ATR": row.get("stop_distance_ATR", row.get("stop_distance_atr", "")),
            "stop_distance_level_ratio": row.get("stop_distance_level_ratio", ""),
            "bp_subtype": row.get("bp_subtype", ""),
            "ce_subtype": "",
        }
    )
    return anatomy


def summarize_candidate_anatomy(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    total = len(rows)
    buckets = Counter(str(row.get("stop_bucket", "unknown_stop")) for row in rows)
    near_miss = Counter(str(row.get("near_miss_shadow", "")) for row in rows if row.get("near_miss_shadow"))
    risk_reasons = Counter(str(row.get("risk_reject_reason", "")) for row in rows if row.get("risk_reject_reason"))
    subtype_counts = Counter(str(row.get("ce_subtype", "")) for row in rows if row.get("ce_subtype"))
    bp_subtype_counts = Counter(str(row.get("bp_subtype", "")) for row in rows if row.get("bp_subtype"))
    failure_counts = Counter(str(row.get("primary_failure_reason", "")) for row in rows if row.get("primary_failure_reason"))
    return {
        "total_candidates": total,
        "stop_buckets": {
            bucket: {"count": buckets[bucket], "ratio": buckets[bucket] / total if total else 0.0}
            for bucket in ("healthy_stop", "borderline_stop", "broken_stop", "unknown_stop")
        },
        "entry_tf_stop_atr": _distribution(row.get("stop_atr_multiple_entry_tf") for row in rows),
        "structure_tf_stop_atr": _distribution(row.get("stop_atr_multiple_structure_tf") for row in rows),
        "used_stop_atr": _distribution(row.get("stop_atr_multiple_used") for row in rows),
        "structure_level_age_bars": _distribution(row.get("structure_level_age_bars") for row in rows),
        "structure_level_age_hours": _distribution(row.get("structure_level_age_hours") for row in rows),
        "entry_to_reclaim_atr_entry_tf": _distribution(row.get("distance_entry_to_reclaim_atr_entry_tf") for row in rows),
        "reclaim_to_signal_atr_entry_tf": _distribution(row.get("distance_reclaim_to_signal_atr_entry_tf") for row in rows),
        "reclaim_to_entry_atr_entry_tf": _distribution(row.get("distance_reclaim_to_entry_atr_entry_tf") for row in rows),
        "entry_to_structure_atr_entry_tf": _distribution(row.get("distance_entry_to_structure_atr_entry_tf") for row in rows),
        "bars_reclaim_to_signal": _distribution(row.get("bars_reclaim_to_signal") for row in rows),
        "bars_signal_to_entry": _distribution(row.get("bars_signal_to_entry") for row in rows),
        "bars_reclaim_to_entry": _distribution(row.get("bars_reclaim_to_entry") for row in rows),
        "bars_sweep_to_entry": _distribution(row.get("bars_sweep_to_entry") for row in rows),
        "target_r_entry_tf": _distribution(row.get("target_r_entry_tf") for row in rows),
        "target_r_structure_tf": _distribution(row.get("target_r_structure_tf") for row in rows),
        "structure_freshness": _freshness_summary(rows),
        "stop_formula_used": dict(Counter(str(row.get("stop_formula_used", "")) for row in rows)),
        "invalidation_mode": dict(Counter(str(row.get("invalidation_mode", "")) for row in rows)),
        "invalidation_mode_config": dict(Counter(str(row.get("invalidation_mode_config", "")) for row in rows)),
        "invalidation_mode_effective": dict(Counter(str(row.get("invalidation_mode_effective", "")) for row in rows)),
        "invalidation_buffer_atr": dict(Counter(str(row.get("invalidation_buffer_atr", "")) for row in rows)),
        "stop_formula_fallback_reason": dict(Counter(str(row.get("stop_formula_fallback_reason", "")) for row in rows)),
        "candidate_lifecycle_status": dict(Counter(str(row.get("candidate_lifecycle_status", "")) for row in rows)),
        "candidate_lifecycle_reason": dict(Counter(str(row.get("candidate_lifecycle_reason", "")) for row in rows)),
        "deduplication": _deduplication_summary(rows),
        "target_source": dict(Counter(str(row.get("target_source", "")) for row in rows)),
        "min_target_r_pass_count": sum(1 for row in rows if row.get("min_target_r_pass")),
        "target_r_too_low_count": sum(1 for row in rows if row.get("final_reject_reason") == "target_r_too_low"),
        "formal_approved_count": sum(1 for row in rows if row.get("formal_approved")),
        "shadow_approved_5_count": sum(1 for row in rows if row.get("shadow_approved_5")),
        "shadow_approved_8_count": sum(1 for row in rows if row.get("shadow_approved_8")),
        "near_miss_shadow_counts": dict(near_miss),
        "risk_reject_reason_counts": dict(risk_reasons),
        "ce_subtype_counts": dict(subtype_counts),
        "bp_subtype_counts": dict(bp_subtype_counts),
        "breakout_failure_taxonomy_counts": dict(failure_counts),
        "stop_distance_too_near_attribution_counts": dict(Counter(str(row.get("stop_distance_too_near_attribution", "")) for row in rows if row.get("stop_distance_too_near_attribution"))),
        "margin_reject_attribution_counts": dict(Counter(str(row.get("margin_reject_attribution", "")) for row in rows if row.get("margin_reject_attribution"))),
    }


def write_candidate_anatomy_artifacts(
    *,
    output_dir: str | Path,
    rows: Sequence[Mapping[str, object]],
    summary: Mapping[str, object],
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    anatomy_jsonl = output / "candidate_anatomy.jsonl"
    anatomy_csv = output / "candidate_anatomy.csv"
    bucket_summary = output / "stop_bucket_summary.csv"
    broken_top20 = output / "broken_stop_top20.csv"
    summary_json = output / "candidate_anatomy_summary.json"
    report_md = output / "candidate_anatomy_report.md"

    _write_jsonl(anatomy_jsonl, rows)
    _write_csv(anatomy_csv, rows, ANATOMY_FIELDS)
    _write_csv(bucket_summary, _bucket_summary_rows(rows), ("group_by", "group_value", "stop_bucket", "count", "ratio"))
    _write_csv(broken_top20, _broken_top20(rows), _BROKEN_TOP_FIELDS)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_md.write_text(build_candidate_anatomy_report(rows=rows, summary=summary), encoding="utf-8")
    return {
        "candidate_anatomy_jsonl": anatomy_jsonl,
        "candidate_anatomy_csv": anatomy_csv,
        "stop_bucket_summary_csv": bucket_summary,
        "broken_stop_top20_csv": broken_top20,
        "candidate_anatomy_summary_json": summary_json,
        "candidate_anatomy_report_md": report_md,
    }


def build_candidate_anatomy_report(*, rows: Sequence[Mapping[str, object]], summary: Mapping[str, object]) -> str:
    buckets = summary["stop_buckets"]
    entry = summary["entry_tf_stop_atr"]
    structure = summary["structure_tf_stop_atr"]
    used = summary["used_stop_atr"]
    freshness = summary["structure_freshness"]
    broken = [row for row in rows if row.get("stop_bucket") == "broken_stop"]
    broken_reasons = Counter(str(row.get("final_reject_reason", "")) for row in broken if row.get("final_reject_reason"))
    severe_groups = _top_group(rows, ("asset", "profile", "direction"), bucket="broken_stop", limit=5)
    entry_gap = summary["entry_to_structure_atr_entry_tf"]
    reclaim_gap = summary["entry_to_reclaim_atr_entry_tf"]
    reclaim_to_entry = summary["reclaim_to_entry_atr_entry_tf"]
    formulas = summary["stop_formula_used"]
    target_sources = summary["target_source"]
    dedup = summary["deduplication"]

    lines = [
        "# Candidate Anatomy Audit Report",
        "",
        f"total_candidates={summary['total_candidates']}",
        "",
        "## Stop Buckets",
        _bucket_line("healthy_stop", buckets["healthy_stop"]),
        _bucket_line("borderline_stop", buckets["borderline_stop"]),
        _bucket_line("broken_stop", buckets["broken_stop"]),
        "",
        "## ATR Comparison",
        f"- entry_tf stop/ATR: P50={_fmt(entry['p50'])}, P75={_fmt(entry['p75'])}, P90={_fmt(entry['p90'])}, P95={_fmt(entry['p95'])}, max={_fmt(entry['max'])}",
        f"- structure_tf stop/ATR: P50={_fmt(structure['p50'])}, P75={_fmt(structure['p75'])}, P90={_fmt(structure['p90'])}, P95={_fmt(structure['p95'])}, max={_fmt(structure['max'])}",
        f"- logged used stop/ATR: P50={_fmt(used['p50'])}, P75={_fmt(used['p75'])}, P90={_fmt(used['p90'])}, P95={_fmt(used['p95'])}, max={_fmt(used['max'])}",
        "",
        "## Structure Freshness",
        f"- fresh={freshness['fresh_structure']['count']}, stale={freshness['stale_structure']['count']}, expired={freshness['expired_structure']['count']}, unknown={freshness['unknown_structure']['count']}",
        f"- age bars: P50={_fmt(summary['structure_level_age_bars']['p50'])}, P75={_fmt(summary['structure_level_age_bars']['p75'])}, P90={_fmt(summary['structure_level_age_bars']['p90'])}, P95={_fmt(summary['structure_level_age_bars']['p95'])}, max={_fmt(summary['structure_level_age_bars']['max'])}",
        "",
        "## Entry Distance",
        f"- entry->structure ATR(entry_tf): P50={_fmt(entry_gap['p50'])}, P75={_fmt(entry_gap['p75'])}, P90={_fmt(entry_gap['p90'])}, P95={_fmt(entry_gap['p95'])}, max={_fmt(entry_gap['max'])}",
        f"- entry->reclaim ATR(entry_tf): P50={_fmt(reclaim_gap['p50'])}, P75={_fmt(reclaim_gap['p75'])}, P90={_fmt(reclaim_gap['p90'])}, P95={_fmt(reclaim_gap['p95'])}, max={_fmt(reclaim_gap['max'])}",
        f"- reclaim->entry ATR(entry_tf): P50={_fmt(reclaim_to_entry['p50'])}, P75={_fmt(reclaim_to_entry['p75'])}, P90={_fmt(reclaim_to_entry['p90'])}, P95={_fmt(reclaim_to_entry['p95'])}, max={_fmt(reclaim_to_entry['max'])}",
        "",
        "## Lifecycle",
        f"- lifecycle_status={summary['candidate_lifecycle_status']}",
        f"- lifecycle_reason={summary['candidate_lifecycle_reason']}",
        f"- duplicate_candidate_count={dedup['duplicate_candidate_count']}, duplicated_sweep_event_count={dedup['duplicated_sweep_event_count']}, max_duplicates_per_sweep_event={dedup['max_duplicates_per_sweep_event']}",
        "",
        "## Stop Formula",
        f"- formula distribution={formulas}",
        f"- invalidation_mode={summary['invalidation_mode']}",
        f"- invalidation_buffer_atr={summary['invalidation_buffer_atr']}",
        "",
        "## Target",
        f"- target R: P50={_fmt(summary['target_r_entry_tf']['p50'])}, P75={_fmt(summary['target_r_entry_tf']['p75'])}, P90={_fmt(summary['target_r_entry_tf']['p90'])}, max={_fmt(summary['target_r_entry_tf']['max'])}",
        f"- target_source={target_sources}",
        f"- min_target_r_pass={summary['min_target_r_pass_count']}, target_r_too_low={summary['target_r_too_low_count']}",
        "",
        "## Worst Groups",
    ]
    lines.extend(f"- {label}: broken={count}" for label, count in severe_groups)
    lines.extend(
        [
            "",
            "## Conclusion",
            _diagnostic_conclusion(summary, rows),
            "",
            "## Stage 2 Priority",
            _stage2_priority(summary, rows),
            "",
            "## Broken Stop Top Rejects",
            f"- {dict(broken_reasons.most_common(8))}",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_cached(cache: dict[tuple[str, str, str, str], tuple[object, ...]], repository, inst_id: str, venue: str, inst_type: str, timeframe: str) -> tuple[object, ...]:
    key = (inst_id, venue, inst_type, timeframe)
    if key not in cache:
        cache[key] = _load_candles(repository, inst_id, timeframe, venue=venue, inst_type=inst_type)
    return cache[key]


def _load_candles(repository, inst_id: str, timeframe: str, *, venue: str, inst_type: str) -> tuple[object, ...]:
    bar = timeframe_to_okx_bar(timeframe)
    if hasattr(repository, "load_range"):
        return tuple(repository.load_range(inst_id, bar, 0, 9_223_372_036_854_775_807, venue=venue, inst_type=inst_type, confirmed_only=True))
    try:
        candles = repository.list_candles(inst_id, bar, venue=venue, inst_type=inst_type)
    except TypeError:
        candles = repository.list_candles(inst_id, bar)
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _candle_at_or_before(candles: Sequence[object], timestamp_ms: int) -> object | None:
    eligible = [candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms]
    return eligible[-1] if eligible else None


def _infer_entry_candle(entry_candles: Sequence[object], row: Mapping[str, object], signal_timestamp_ms: int) -> object | None:
    entry_timestamp = _optional_int(row.get("entry_timestamp_ms"))
    if entry_timestamp is not None:
        match = next((candle for candle in entry_candles if int(getattr(candle, "timestamp_ms")) == entry_timestamp), None)
        if match is not None:
            return match
    entry_price = _optional_float(row.get("entry_reference_price")) or _optional_float(row.get("entry_price"))
    if entry_price is not None:
        matches = [
            candle
            for candle in entry_candles
            if int(getattr(candle, "timestamp_ms")) >= signal_timestamp_ms
            and (
                abs(float(getattr(candle, "open")) - entry_price) <= max(1e-8, abs(entry_price) * 1e-8)
                or abs(float(getattr(candle, "close")) - entry_price) <= max(1e-8, abs(entry_price) * 1e-8)
            )
        ]
        if matches:
            return matches[0]
    return _candle_at_or_before(entry_candles, signal_timestamp_ms)


def _structure_level_info(row: Mapping[str, object], structure_candles: Sequence[object], timestamp_ms: int) -> dict[str, object]:
    direction = str(row.get("direction", ""))
    level = _float(row.get("structure_level"), 0.0)
    candles = [candle for candle in structure_candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms]
    sweep_index = next((index for index, candle in enumerate(candles) if int(getattr(candle, "timestamp_ms")) == timestamp_ms), len(candles) - 1)
    prior = candles[:sweep_index]
    side = "low" if direction == "long" else "high"
    level_index = None
    for index, candle in enumerate(prior):
        value = float(getattr(candle, side))
        if abs(value - level) <= max(1e-8, abs(level) * 1e-8):
            level_index = index
    if level_index is None:
        return {
            "structure_level_type": "range_low" if direction == "long" else "range_high",
            "timestamp_ms": None,
            "age_bars": None,
            "age_hours": None,
            "touch_count": 0,
        }
    level_ts = int(getattr(candles[level_index], "timestamp_ms"))
    return {
        "structure_level_type": "range_low" if direction == "long" else "range_high",
        "timestamp_ms": level_ts,
        "age_bars": sweep_index - level_index,
        "age_hours": (timestamp_ms - level_ts) / 3_600_000,
        "touch_count": sum(1 for candle in prior if abs(float(getattr(candle, side)) - level) <= max(1e-8, abs(level) * 1e-8)),
    }


def _atr_at(candles: Sequence[object], timestamp_ms: int) -> tuple[float | None, int | None]:
    eligible = [candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms]
    if len(eligible) < 15:
        return None, int(getattr(eligible[-1], "timestamp_ms")) if eligible else None
    recent = eligible[-15:]
    highs = [float(candle.high) for candle in recent]
    lows = [float(candle.low) for candle in recent]
    closes = [float(candle.close) for candle in recent]
    return average_true_range(highs, lows, closes, period=14), int(getattr(recent[-1], "timestamp_ms"))


def _stop_formula_used(row: Mapping[str, object], atr_used: float) -> str:
    recorded = str(row.get("stop_formula_used", ""))
    if recorded:
        return recorded
    mode = str(row.get("invalidation_mode", ""))
    direction = str(row.get("direction", ""))
    buffer_atr = _float(row.get("invalidation_buffer_atr"), 0.0)
    sweep = _float(row.get("sweep_extreme_price", row.get("sweep_extreme")), 0.0)
    stop = _float(row.get("stop_price"), 0.0)
    if direction == "long":
        expected = sweep - buffer_atr * atr_used
    else:
        expected = sweep + buffer_atr * atr_used
    if abs(stop - expected) <= max(1e-8, abs(stop) * 1e-8):
        return f"{mode}_{direction}" if mode else f"unknown_mode_{direction}"
    legacy = sweep - atr_used if direction == "long" else sweep + atr_used
    if abs(stop - legacy) <= max(1e-8, abs(stop) * 1e-8):
        return f"legacy_atr_buffer_{direction}"
    return f"unknown_{direction}"


def _target_source(row: Mapping[str, object], stop_distance: float, target_distance: float) -> str:
    if abs(target_distance - 2.0 * stop_distance) <= max(1e-8, abs(target_distance) * 1e-8):
        return "fixed_2r_from_entry_stop"
    return "unknown"


def _risk_reason(row: Mapping[str, object]) -> str:
    if row.get("reject_stage") == "risk_filter":
        return str(row.get("reject_reason", ""))
    if row.get("reject_stage") == "contract_risk_filter":
        return str(row.get("contract_risk_reject_reason") or row.get("reject_reason", ""))
    codes = row.get("risk_reason_codes", ())
    if isinstance(codes, str):
        return codes
    if isinstance(codes, Sequence):
        return ",".join(str(code) for code in codes)
    return ""


def _ce_box_duration(row: Mapping[str, object]) -> int | None:
    start = _optional_int(row.get("compression_start_time"))
    end = _optional_int(row.get("compression_end_time"))
    if start is None or end is None:
        return None
    return max(0, end - start)


def _ce_stop_near_attribution(row: Mapping[str, object], stop_distance: float, atr: float) -> str:
    reason = str(row.get("reject_reason", ""))
    codes = row.get("risk_reason_codes", ())
    code_text = ",".join(str(code) for code in codes) if isinstance(codes, Sequence) and not isinstance(codes, str) else str(codes)
    if "stop_distance_too_near" not in reason and "stop_distance_too_near" not in code_text:
        return ""
    box_atr = _optional_float(row.get("compression_box_atr")) or 0.0
    stop_atr = _optional_float(row.get("stop_distance_atr")) or _ratio(stop_distance, atr) or 0.0
    anchor = str(row.get("stop_anchor_type", ""))
    min_stop = _optional_float(row.get("min_stop_atr_multiple")) or 0.8
    if anchor in {"breakout_midpoint_or_box_edge", "box_upper", "box_lower"}:
        return "stop_anchor_too_close"
    if box_atr > 0 and box_atr < min_stop:
        return "box_too_narrow"
    if stop_atr < min_stop:
        return "atr_floor_or_min_stop_conflict"
    return "entry_too_early"


def _ce_margin_attribution(row: Mapping[str, object], stop_distance: float, atr: float) -> str:
    reason = str(row.get("reject_reason", ""))
    contract_reason = str(row.get("contract_risk_reject_reason", ""))
    margin = _optional_float(row.get("margin_required")) or 0.0
    notional = _optional_float(row.get("notional")) or 0.0
    has_margin_reject = "margin_required_too_high" in reason or "margin_required_too_high" in contract_reason
    has_stop_reject = "stop_distance_too_near" in reason or "stop_distance_too_near" in str(row.get("risk_reason_codes", ""))
    if not has_margin_reject and not has_stop_reject:
        return ""
    stop_atr = _optional_float(row.get("stop_distance_atr")) or _ratio(stop_distance, atr) or 0.0
    if stop_atr < (_optional_float(row.get("min_stop_atr_multiple")) or 0.8) or (has_margin_reject and (margin > 0 or notional > 0)):
        return "stop_distance_position_size_coupling"
    return "independent_margin_constraint"


def _ce_near_miss_shadow(
    row: Mapping[str, object],
    risk_reason: str,
    stop_attr: str,
    margin_attr: str,
    gross_rr: float,
    cost_adjusted_rr: float,
) -> str:
    if bool(row.get("formal_approved")):
        return "approved"
    reject_reason = str(row.get("reject_reason", ""))
    box_atr = _optional_float(row.get("compression_box_atr")) or 0.0
    rvol = _optional_float(row.get("breakout_rvol")) or 0.0
    if gross_rr < 1.0 or cost_adjusted_rr <= 0 or box_atr <= 0 or rvol < 1.0:
        return "low_quality_reject"
    if stop_attr or margin_attr or risk_reason in {"stop_distance_too_near", "margin_required_too_high"}:
        anchor = str(row.get("stop_anchor_type", ""))
        if anchor == "breakout_midpoint_or_box_edge" and stop_attr == "stop_anchor_too_close":
            return "reasonable_near_miss"
        return "definition_conflict"
    if reject_reason:
        return "low_quality_reject"
    return "reasonable_near_miss"


def _reason_if(row: Mapping[str, object], reasons: set[str]) -> str:
    reason = str(row.get("reject_reason", ""))
    return reason if reason in reasons else ""


def _freshness_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[_freshness_bucket(row.get("structure_level_age_bars"))].append(row)
    result: dict[str, dict[str, object]] = {}
    for bucket in ("fresh_structure", "stale_structure", "expired_structure", "unknown_structure"):
        bucket_rows = grouped.get(bucket, [])
        result[bucket] = {
            "count": len(bucket_rows),
            "stop_atr_entry_tf": _distribution(row.get("stop_atr_multiple_entry_tf") for row in bucket_rows),
        }
    return result


def _freshness_bucket(age_bars: object) -> str:
    age = _optional_float(age_bars)
    if age is None:
        return "unknown_structure"
    if age <= 20:
        return "fresh_structure"
    if age <= 50:
        return "stale_structure"
    return "expired_structure"


def _deduplication_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    counts = Counter(str(row.get("sweep_event_id", row.get("candidate_id", ""))) for row in rows)
    duplicate_groups = [count for key, count in counts.items() if key and count > 1]
    duplicate_candidate_count = sum(count - 1 for count in duplicate_groups)
    return {
        "duplicate_candidate_count": duplicate_candidate_count,
        "duplicated_sweep_event_count": len(duplicate_groups),
        "avg_duplicates_per_sweep_event": sum(duplicate_groups) / len(duplicate_groups) if duplicate_groups else 0.0,
        "max_duplicates_per_sweep_event": max(duplicate_groups) if duplicate_groups else 0,
    }


def _bucket_summary_rows(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    fields = (
        "asset",
        "profile",
        "direction",
        "setup",
        "structure_level_type",
        "structure_timeframe",
        "invalidation_mode",
        "atr_used_for_stop_timeframe",
        "final_reject_reason",
    )
    out: list[dict[str, object]] = []
    for field in fields:
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        totals: Counter[str] = Counter()
        for row in rows:
            group_value = str(row.get(field, ""))
            bucket = str(row.get("stop_bucket", "unknown_stop"))
            grouped[group_value][bucket] += 1
            totals[group_value] += 1
        for group_value, buckets in sorted(grouped.items()):
            for bucket, count in sorted(buckets.items()):
                out.append({"group_by": field, "group_value": group_value, "stop_bucket": bucket, "count": count, "ratio": count / totals[group_value]})
    return tuple(out)


def _broken_top20(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    broken = [row for row in rows if row.get("stop_bucket") == "broken_stop"]
    broken.sort(key=lambda row: _optional_float(row.get("stop_atr_multiple_entry_tf")) or 0.0, reverse=True)
    return tuple({field: row.get(field, "") for field in _BROKEN_TOP_FIELDS} for row in broken[:20])


def _top_group(rows: Sequence[Mapping[str, object]], fields: Sequence[str], *, bucket: str, limit: int) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row.get("stop_bucket") == bucket:
            counts["/".join(str(row.get(field, "")) for field in fields)] += 1
    return counts.most_common(limit)


def _diagnostic_conclusion(summary: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> str:
    broken_count = summary["stop_buckets"]["broken_stop"]["count"]
    total = summary["total_candidates"]
    formulas = summary["stop_formula_used"]
    used_formula_ok = sum(count for formula, count in formulas.items() if str(formula).startswith("structure_extreme_buffer"))
    entry_p90 = summary["entry_tf_stop_atr"]["p90"]
    structure_p90 = summary["structure_tf_stop_atr"]["p90"]
    expired = summary["structure_freshness"]["expired_structure"]["count"]
    if used_formula_ok == total and broken_count:
        return (
            "structure_extreme_buffer is logged as active, but many candidates are still broken_stop. "
            f"broken={broken_count}/{total}. Prioritize entry/reference timing, then ATR normalization. "
            f"entry_tf P90={_fmt(entry_p90)}, structure_tf P90={_fmt(structure_p90)}, expired_structure={expired}."
        )
    return (
        "invalidation_mode is logged as structure_extreme_buffer, but stop_formula_used matches legacy ATR expansion. "
        "The primary issue is that raw candidate stop/invalidation parameter plumbing is not taking effect; "
        "entry/reference timing also appears far from historical structure events. "
        f"entry_tf P90={_fmt(entry_p90)}, structure_tf P90={_fmt(structure_p90)}, expired_structure={expired}."
    )


def _stage2_priority(summary: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> str:
    formulas = summary["stop_formula_used"]
    has_legacy = any(str(formula).startswith("legacy_atr_buffer") for formula in formulas)
    if has_legacy:
        return "Stage 2 can start. First priority: fix stop formula / invalidation logic. Re-run candidate anatomy after that, then address entry reference / signal timing."
    return "Stage 2 can start. First priority: fix entry reference / signal timing."


def _distribution(values: Sequence[object] | object) -> dict[str, float | int | None]:
    if not isinstance(values, Sequence) or isinstance(values, str):
        values = tuple(values)  # type: ignore[arg-type]
    numbers = sorted(value for value in (_optional_float(item) for item in values) if value is not None)
    if not numbers:
        return {"count": 0, "p50": None, "p75": None, "p90": None, "p95": None, "max": None, "median": None}
    return {
        "count": len(numbers),
        "p50": _percentile(numbers, 0.50),
        "p75": _percentile(numbers, 0.75),
        "p90": _percentile(numbers, 0.90),
        "p95": _percentile(numbers, 0.95),
        "max": numbers[-1],
        "median": median(numbers),
    }


def _percentile(numbers: Sequence[float], q: float) -> float:
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * q
    low = int(position)
    high = min(low + 1, len(numbers) - 1)
    fraction = position - low
    return numbers[low] * (1.0 - fraction) + numbers[high] * fraction


def _stop_bucket(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "unknown_stop"
    if number <= 3.0:
        return "healthy_stop"
    if number <= 8.0:
        return "borderline_stop"
    return "broken_stop"


def _reclaim_quality(value: float | None) -> str:
    if value is None:
        return "unknown_reclaim"
    if value <= 1.2:
        return "ideal_reclaim"
    if value <= 1.6:
        return "acceptable_reclaim"
    return "high_reclaim_rvol"


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _float(value: object, default: float) -> float:
    number = _optional_float(value)
    return default if number is None else number


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(timestamp_ms: object) -> str:
    if timestamp_ms in (None, ""):
        return ""
    return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC).isoformat()


def _fmt(value: object) -> str:
    number = _optional_float(value)
    return "n/a" if number is None else f"{number:.2f}"


def _bucket_line(name: str, payload: Mapping[str, object]) -> str:
    return f"- {name}: count={payload['count']}, ratio={float(payload['ratio']):.2%}"


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


_BROKEN_TOP_FIELDS = (
    "candidate_id",
    "timestamp",
    "asset",
    "profile",
    "direction",
    "structure_level",
    "structure_level_type",
    "structure_level_age_bars",
    "entry_price",
    "sweep_extreme_price",
    "reclaim_price",
    "stop_price",
    "atr_entry_tf",
    "atr_structure_tf",
    "stop_atr_multiple_entry_tf",
    "stop_atr_multiple_structure_tf",
    "distance_entry_to_structure_atr_entry_tf",
    "distance_entry_to_reclaim_atr_entry_tf",
    "stop_formula_used",
    "final_reject_reason",
)


__all__ = (
    "ANATOMY_FIELDS",
    "build_candidate_anatomy_report",
    "build_candidate_anatomy_rows",
    "summarize_candidate_anatomy",
    "write_candidate_anatomy_artifacts",
)
