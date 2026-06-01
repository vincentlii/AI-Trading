from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from trading_system.config.loader import BacktestPresetConfig
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.indicators.regime import average_true_range
from trading_system.strategies.trend_price_volume_v1.features import build_market_regime, confirm_volume_price
from trading_system.timeframe_profiles import get_profile


@dataclass(frozen=True)
class FreshLRScannerResult:
    summary_rows: tuple[dict[str, object], ...]
    event_rows: tuple[dict[str, object], ...]
    candidate_rows: tuple[dict[str, object], ...]
    duplicate_summary: Mapping[str, object]
    report: str


@dataclass(frozen=True)
class StructureLevel:
    source: str
    level_type: str
    direction: str
    price: float
    candle: object
    age_bars: int
    age_hours: float
    distance_abs: float
    distance_atr: float | None
    touch_count: int
    swing_strength: float
    liquidity_score: float
    state: str
    diagnostic_only: bool = False


def scan_fresh_liquidity_reversal(
    *,
    repository,
    preset: BacktestPresetConfig,
    max_entry_windows: int | None,
    reclaim_windows: Sequence[int] = (3, 5, 8),
) -> FreshLRScannerResult:
    max_reclaim = max(reclaim_windows) if reclaim_windows else 3
    event_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    summary_groups: dict[tuple[str, str, str, str, str, str], Counter[str]] = defaultdict(Counter)
    metric_groups: dict[tuple[str, str, str, str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    emitted_ids: set[str] = set()

    for target in preset.to_scan_config().targets:
        asset = target.canonical_symbol.split("/", 1)[0].upper()
        for profile_key in preset.scan.profile_keys:
            profile = get_profile(profile_key)
            entry = _load_timeframe(repository, target, profile.entry_timeframe)
            structure = _load_timeframe(repository, target, profile.structure_timeframe)
            trend = _load_timeframe(repository, target, profile.trend_timeframe)
            if len(entry) < 2 or len(structure) < 3:
                continue
            scan_start_ts = int(getattr(entry[0], "timestamp_ms"))
            if max_entry_windows is not None and max_entry_windows > 0:
                scan_start_ts = int(getattr(entry[max(0, len(entry) - max_entry_windows)], "timestamp_ms"))
            scan_end_ts = int(getattr(entry[-1], "timestamp_ms"))

            for index in range(2, len(structure)):
                sweep = structure[index]
                sweep_ts = int(getattr(sweep, "timestamp_ms"))
                if sweep_ts < scan_start_ts or sweep_ts > scan_end_ts:
                    continue
                prior_start = max(0, index - _level_lookback_bars(profile.key))
                prior = tuple(structure[prior_start:index])
                if not prior:
                    continue
                atr = _atr(structure[: index + 1])
                levels_by_direction = {
                    direction: _active_scanner_levels(_structure_levels(prior=prior, current=sweep, profile_key=profile.key, direction=direction, atr=atr))
                    for direction in ("long", "short")
                }
                for direction in ("long", "short"):
                    all_levels = _structure_levels(prior=prior, current=sweep, profile_key=profile.key, direction=direction, atr=atr)
                    scanner_levels = levels_by_direction[direction]
                    scanner_keys = {(level.source, level.level_type, level.price, int(getattr(level.candle, "timestamp_ms"))) for level in scanner_levels}
                    for structure_level in all_levels:
                        key = (asset, profile.key, direction, structure_level.source, structure_level.level_type, profile.structure_timeframe)
                        _record_structure_level(summary_groups[key], metric_groups[key], structure_level)
                    for structure_level in scanner_levels:
                        key = (asset, profile.key, direction, structure_level.source, structure_level.level_type, profile.structure_timeframe)
                        if (structure_level.source, structure_level.level_type, structure_level.price, int(getattr(structure_level.candle, "timestamp_ms"))) not in scanner_keys:
                            continue
                        level = structure_level.price
                        level_candle = structure_level.candle
                        level_type = structure_level.level_type
                        level_source = structure_level.source
                        summary_groups[key]["structure_levels_scanned_count"] += 1
                        if _near_structure(sweep, level, atr):
                            summary_groups[key]["bars_near_structure_count"] += 1
                        if not _is_sweep(sweep, level, direction):
                            summary_groups[key]["sweep_reject_no_intrabar_cross"] += 1
                            continue
                        summary_groups[key]["bars_cross_structure_intrabar_count"] += 1
                        summary_groups[key]["sweep_events_count"] += 1

                        lifecycle = _resolve_lifecycle(
                            structure=structure,
                            sweep_index=index,
                            level=level,
                            direction=direction,
                            max_reclaim=max_reclaim,
                            reclaim_windows=tuple(reclaim_windows),
                        )
                        for window, reclaimed in lifecycle["reclaimed_within"].items():
                            if reclaimed:
                                summary_groups[key][f"reclaimed_within_{window}_bars"] += 1
                        if lifecycle["invalidated"]:
                            summary_groups[key]["invalidated_events_count"] += 1
                        if lifecycle["reclaim"] is None:
                            summary_groups[key]["expired_events_count"] += 1
                            summary_groups[key]["expired_without_reclaim"] += 1
                        else:
                            summary_groups[key]["bars_close_back_inside_count"] += 1
                            summary_groups[key]["reclaim_events_count"] += 1
                            summary_groups[key]["signal_events_count"] += 1

                        event_id = _event_id(target.inst_id, profile.key, direction, level_source, level_type, level, sweep_ts, lifecycle["reclaim_ts"])
                        entry_candle = _next_entry(entry, lifecycle["signal_ts"]) if lifecycle["signal_ts"] is not None else None
                        event_state = "invalidated" if lifecycle["invalidated"] else "expired"
                        if lifecycle["reclaim"] is not None:
                            event_state = "signaled"
                        if entry_candle is None and lifecycle["reclaim"] is not None:
                            summary_groups[key]["missed_due_to_cache_window_boundary_count"] += 1
                        if entry_candle is not None and int(getattr(entry_candle, "timestamp_ms")) > scan_end_ts:
                            summary_groups[key]["missed_due_to_cache_window_boundary_count"] += 1
                        if entry_candle is not None and lifecycle["reclaim"] is not None and event_id not in emitted_ids and int(getattr(entry_candle, "timestamp_ms")) <= scan_end_ts:
                            emitted_ids.add(event_id)
                            event_state = "emitted"
                            summary_groups[key]["next_entry_bar_found_count"] += 1
                            summary_groups[key]["entry_candidate_emitted_count"] += 1
                            summary_groups[key]["fresh_entry_candidates_count"] += 1
                            candidate = _candidate_row(
                                event_id=event_id,
                                target=target,
                                profile_key=profile.key,
                                direction=direction,
                                structure_level=structure_level,
                                structure=structure,
                                sweep_index=index,
                                sweep=sweep,
                                reclaim=lifecycle["reclaim"],
                                entry_candle=entry_candle,
                                atr=atr,
                                preset=preset,
                                trend_candles=_candles_until(trend, sweep_ts),
                            )
                            candidate_rows.append(candidate)
                        elif event_id in emitted_ids:
                            summary_groups[key]["missed_due_to_duplicate_guard_count"] += 1

                        event_rows.append(
                            {
                                "event_id": event_id,
                                "asset": asset,
                                "profile": profile.key,
                                "direction": direction,
                                "structure_level": level,
                                "structure_level_source": level_source,
                                "structure_level_type": level_type,
                                "structure_timeframe": profile.structure_timeframe,
                                "structure_time": int(getattr(level_candle, "timestamp_ms")),
                                "sweep_time": sweep_ts,
                                "sweep_bar_index": index,
                                "reclaim_time": lifecycle["reclaim_ts"],
                                "signal_time": lifecycle["signal_ts"],
                                "entry_time": None if entry_candle is None else int(getattr(entry_candle, "timestamp_ms")),
                                "expiry_time": lifecycle["expiry_ts"],
                                "event_state": event_state,
                            }
                        )

    summary_rows = _summary_rows(summary_groups, metric_groups, event_rows, candidate_rows)
    duplicate = _duplicate_summary(candidate_rows)
    report = build_fresh_lr_report(summary_rows=summary_rows, candidate_rows=candidate_rows, duplicate_summary=duplicate)
    return FreshLRScannerResult(
        summary_rows=summary_rows,
        event_rows=tuple(event_rows),
        candidate_rows=tuple(candidate_rows),
        duplicate_summary=duplicate,
        report=report,
    )


def write_fresh_lr_artifacts(output_dir: str | Path, result: FreshLRScannerResult) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_csv": output / "fresh_lr_summary.csv",
        "events_jsonl": output / "fresh_lr_events.jsonl",
        "candidates_jsonl": output / "fresh_lr_candidates.jsonl",
        "summary_json": output / "fresh_lr_summary.json",
        "report_md": output / "fresh_lr_report.md",
    }
    _write_csv(paths["summary_csv"], result.summary_rows)
    _write_jsonl(paths["events_jsonl"], result.event_rows)
    _write_jsonl(paths["candidates_jsonl"], result.candidate_rows)
    paths["summary_json"].write_text(
        json.dumps({"summary_rows": result.summary_rows, "duplicate_summary": result.duplicate_summary}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["report_md"].write_text(result.report, encoding="utf-8")
    return paths


def build_fresh_lr_report(
    *,
    summary_rows: Sequence[Mapping[str, object]],
    candidate_rows: Sequence[Mapping[str, object]],
    duplicate_summary: Mapping[str, object],
) -> str:
    total = Counter()
    for row in summary_rows:
        for field in (
            "structure_levels_available_count",
            "active_structure_levels",
            "too_far_structure_levels",
            "sweep_events_count",
            "reclaim_events_count",
            "signal_events_count",
            "fresh_entry_candidates_count",
            "expired_events_count",
            "invalidated_events_count",
        ):
            total[field] += int(row.get(field, 0) or 0)
    stop_buckets = Counter(str(row.get("stop_bucket", "")) for row in candidate_rows)
    source_rows = []
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in summary_rows:
        source = str(row.get("structure_level_source", "unknown"))
        for field in (
            "total_structure_levels",
            "active_structure_levels",
            "structure_levels_scanned_count",
            "too_far_structure_levels",
            "sweep_events_count",
            "reclaim_events_count",
            "fresh_entry_candidates_count",
        ):
            by_source[source][field] += int(row.get(field, 0) or 0)
    for source, counts in sorted(by_source.items()):
        source_rows.append(
            f"- {source}: total={counts['total_structure_levels']} active={counts['active_structure_levels']} "
            f"scanned={counts['structure_levels_scanned_count']} too_far={counts['too_far_structure_levels']} sweep={counts['sweep_events_count']} "
            f"reclaim={counts['reclaim_events_count']} candidates={counts['fresh_entry_candidates_count']}"
        )
    return "\n".join(
        (
            "# Stage 4 Fresh Structure Redesign Report",
            "",
            f"- structure_levels_available_count={total['structure_levels_available_count']}",
            f"- active_structure_levels={total['active_structure_levels']}",
            f"- too_far_structure_levels={total['too_far_structure_levels']}",
            f"- sweep_events_count={total['sweep_events_count']}",
            f"- reclaim_events_count={total['reclaim_events_count']}",
            f"- signal_events_count={total['signal_events_count']}",
            f"- fresh_entry_candidates_count={total['fresh_entry_candidates_count']}",
            f"- expired_events_count={total['expired_events_count']}",
            f"- invalidated_events_count={total['invalidated_events_count']}",
            f"- duplicate_candidate_count={duplicate_summary.get('duplicate_candidate_count', 0)}",
            f"- stop_buckets={dict(stop_buckets)}",
            "",
            "## Source Summary",
            *source_rows,
        )
    ) + "\n"


def _load_timeframe(repository, target, timeframe: str) -> tuple[object, ...]:
    bar = timeframe_to_okx_bar(timeframe)
    if hasattr(repository, "load_range"):
        candles = repository.load_range(target.inst_id, bar, 0, 9_223_372_036_854_775_807, venue=target.venue, inst_type=target.inst_type, confirmed_only=True)
    else:
        candles = repository.list_candles(target.inst_id, bar, venue=target.venue, inst_type=target.inst_type)
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _candles_until(candles: Sequence[object], timestamp_ms: int) -> tuple[object, ...]:
    return tuple(candle for candle in candles if int(getattr(candle, "timestamp_ms")) <= timestamp_ms)


def _context_features(target, profile_key: str, preset: BacktestPresetConfig) -> dict[str, object]:
    profile = get_profile(profile_key)
    return {
        "asset": target.canonical_symbol.split("/", 1)[0].upper(),
        "timeframe_group": profile.key,
        "entry_timeframe": profile.structure_timeframe,
        "structure_timeframe": profile.structure_timeframe,
        "trend_timeframe": profile.trend_timeframe,
        "volume": preset.strategy.volume,
    }


def _volume_evidence(candles: Sequence[object], direction: str, context_features: Mapping[str, object]) -> Mapping[str, object]:
    if len(candles) < 2:
        return {"rolling_rvol": None, "tod_dow_rvol": None, "volume_baseline_mode": "", "volume_bucket_sample_count": 0, "used_fallback_volume_baseline": True}
    return confirm_volume_price(candles, direction, context_features=context_features).evidence


def _rvol_value(evidence: Mapping[str, object]) -> float | None:
    return _as_float(evidence.get("tod_dow_rvol")) or _as_float(evidence.get("rolling_rvol"))


def _detect_choch(structure: Sequence[object], sweep_index: int, reclaim: object, direction: str) -> object | None:
    if sweep_index <= 0:
        return None
    previous = structure[sweep_index - 1]
    reclaim_index = _index_of(structure, int(getattr(reclaim, "timestamp_ms")))
    search = structure[reclaim_index : min(len(structure), reclaim_index + 4)]
    if direction == "long":
        return next((candle for candle in search if float(getattr(candle, "close")) > float(getattr(previous, "high"))), None)
    return next((candle for candle in search if float(getattr(candle, "close")) < float(getattr(previous, "low"))), None)


def _structure_levels(*, prior: Sequence[object], current: object, profile_key: str, direction: str, atr: float) -> tuple[StructureLevel, ...]:
    levels: list[StructureLevel] = []
    levels.extend(_rolling_range_levels(prior=prior, current=current, profile_key=profile_key, direction=direction, atr=atr))
    levels.extend(_recent_swing_levels(prior=prior, current=current, profile_key=profile_key, direction=direction, atr=atr))
    levels.extend(_equal_high_low_levels(prior=prior, current=current, profile_key=profile_key, direction=direction, atr=atr))
    levels.extend(_previous_day_levels(prior=prior, current=current, profile_key=profile_key, direction=direction, atr=atr))
    return tuple(levels)


def _rolling_range_levels(*, prior: Sequence[object], current: object, profile_key: str, direction: str, atr: float) -> tuple[StructureLevel, ...]:
    levels: list[StructureLevel] = []
    for window in _rolling_windows(profile_key):
        if not prior:
            continue
        sample = tuple(prior[-min(window, len(prior)) :])
        if direction == "long":
            candle = min(sample, key=lambda item: float(item.low))
            price = float(candle.low)
            level_type = "rolling_range_low"
        else:
            candle = max(sample, key=lambda item: float(item.high))
            price = float(candle.high)
            level_type = "rolling_range_high"
        levels.append(_make_structure_level("rolling_range", level_type, direction, price, candle, prior, current, profile_key, atr))
    return tuple(_dedupe_levels(levels))


def _recent_swing_levels(*, prior: Sequence[object], current: object, profile_key: str, direction: str, atr: float) -> tuple[StructureLevel, ...]:
    levels: list[StructureLevel] = []
    for lookback in (3, 5, 8):
        swings = _find_swings(prior, direction, lookback)
        for candle, strength in swings[-6:]:
            price = float(candle.low) if direction == "long" else float(candle.high)
            level_type = "recent_swing_low" if direction == "long" else "recent_swing_high"
            level = _make_structure_level("recent_swing", level_type, direction, price, candle, prior, current, profile_key, atr)
            levels.append(
                StructureLevel(
                    source=level.source,
                    level_type=level.level_type,
                    direction=level.direction,
                    price=level.price,
                    candle=level.candle,
                    age_bars=level.age_bars,
                    age_hours=level.age_hours,
                    distance_abs=level.distance_abs,
                    distance_atr=level.distance_atr,
                    touch_count=level.touch_count,
                    swing_strength=strength,
                    liquidity_score=level.liquidity_score + strength,
                    state=level.state,
                    diagnostic_only=level.diagnostic_only,
                )
            )
    return tuple(_dedupe_levels(levels))


def _equal_high_low_levels(*, prior: Sequence[object], current: object, profile_key: str, direction: str, atr: float) -> tuple[StructureLevel, ...]:
    if atr <= 0 or len(prior) < 4:
        return ()
    swings = _find_swings(prior, direction, 3)
    tolerance = 0.25 * atr
    levels: list[StructureLevel] = []
    for index, (candle, _) in enumerate(swings):
        price = float(candle.low) if direction == "long" else float(candle.high)
        has_equal = any(
            abs(price - (float(other.low) if direction == "long" else float(other.high))) <= tolerance
            for other, _ in swings[index + 1 :]
        )
        if has_equal:
            level_type = "equal_low" if direction == "long" else "equal_high"
            level = _make_structure_level("equal_high_low", level_type, direction, price, candle, prior, current, profile_key, atr)
            levels.append(_as_diagnostic(level))
    return tuple(_dedupe_levels(levels))


def _previous_day_levels(*, prior: Sequence[object], current: object, profile_key: str, direction: str, atr: float) -> tuple[StructureLevel, ...]:
    window = 24 if profile_key == "B" else 6
    if len(prior) < window:
        return ()
    sample = tuple(prior[-window:])
    if direction == "long":
        candle = min(sample, key=lambda item: float(item.low))
        price = float(candle.low)
        level_type = "previous_day_low"
    else:
        candle = max(sample, key=lambda item: float(item.high))
        price = float(candle.high)
        level_type = "previous_day_high"
    return (_as_diagnostic(_make_structure_level("previous_day_high_low", level_type, direction, price, candle, prior, current, profile_key, atr)),)


def _level_lookback_bars(profile_key: str) -> int:
    return 240 if profile_key == "B" else 180


def _make_structure_level(source: str, level_type: str, direction: str, price: float, candle: object, prior: Sequence[object], current: object, profile_key: str, atr: float) -> StructureLevel:
    current_ts = int(getattr(current, "timestamp_ms"))
    level_ts = int(getattr(candle, "timestamp_ms"))
    age_bars = max(0, len(prior) - 1 - _index_of(prior, level_ts) + 1)
    age_hours = age_bars * _structure_hours(profile_key)
    close = float(getattr(current, "close"))
    distance_abs = abs(close - price)
    distance_atr = distance_abs / atr if atr > 0 else None
    touch_count = _touch_count(prior, price, atr)
    swing_strength = 0.0
    state = _level_state(age_bars=age_bars, distance_atr=distance_atr, profile_key=profile_key)
    freshness_score = max(0.0, 1.0 - (age_bars / max(1, _max_structure_age_bars(profile_key))))
    proximity_score = max(0.0, 1.0 - ((distance_atr or 99.0) / 3.0))
    touch_count_score = min(float(touch_count), 3.0) / 3.0
    return StructureLevel(
        source=source,
        level_type=level_type,
        direction=direction,
        price=price,
        candle=candle,
        age_bars=age_bars,
        age_hours=age_hours,
        distance_abs=distance_abs,
        distance_atr=distance_atr,
        touch_count=touch_count,
        swing_strength=swing_strength,
        liquidity_score=freshness_score + proximity_score + touch_count_score + swing_strength,
        state=state,
        diagnostic_only=False,
    )


def _active_scanner_levels(levels: Sequence[StructureLevel]) -> tuple[StructureLevel, ...]:
    eligible = [
        level
        for level in levels
        if level.state == "active" and not level.diagnostic_only and level.source in {"recent_swing", "rolling_range"}
    ]
    return tuple(sorted(eligible, key=lambda level: level.liquidity_score, reverse=True)[:3])


def _record_structure_level(counts: Counter[str], metrics: dict[str, list[float]], level: StructureLevel) -> None:
    counts["structure_levels_available_count"] += 1
    counts["total_structure_levels"] += 1
    counts[f"{level.state}_structure_levels"] += 1
    metrics["structure_age_bars"].append(float(level.age_bars))
    metrics["structure_age_hours"].append(float(level.age_hours))
    metrics["distance_to_current_price_abs"].append(float(level.distance_abs))
    if level.distance_atr is not None:
        metrics["nearest_structure_distance_atr"].append(float(level.distance_atr))
        metrics["distance_to_current_price_atr_structure_tf"].append(float(level.distance_atr))


def _find_swings(candles: Sequence[object], direction: str, lookback: int) -> tuple[tuple[object, float], ...]:
    swings: list[tuple[object, float]] = []
    if len(candles) < lookback * 2 + 1:
        return ()
    for index in range(lookback, len(candles) - lookback):
        candle = candles[index]
        left = candles[index - lookback : index]
        right = candles[index + 1 : index + lookback + 1]
        if direction == "long":
            price = float(candle.low)
            if price <= min(float(item.low) for item in left) and price <= min(float(item.low) for item in right):
                strength = (min(float(item.low) for item in left + right) - price) if left and right else 0.0
                swings.append((candle, max(0.0, strength)))
        else:
            price = float(candle.high)
            if price >= max(float(item.high) for item in left) and price >= max(float(item.high) for item in right):
                strength = (price - max(float(item.high) for item in left + right)) if left and right else 0.0
                swings.append((candle, max(0.0, strength)))
    return tuple(swings)


def _dedupe_levels(levels: Sequence[StructureLevel]) -> tuple[StructureLevel, ...]:
    deduped: dict[tuple[str, str, int, str], StructureLevel] = {}
    for level in levels:
        key = (level.source, level.level_type, int(getattr(level.candle, "timestamp_ms")), f"{level.price:.8f}")
        existing = deduped.get(key)
        if existing is None or level.liquidity_score > existing.liquidity_score:
            deduped[key] = level
    return tuple(sorted(deduped.values(), key=lambda item: item.liquidity_score, reverse=True))


def _as_diagnostic(level: StructureLevel) -> StructureLevel:
    return StructureLevel(
        source=level.source,
        level_type=level.level_type,
        direction=level.direction,
        price=level.price,
        candle=level.candle,
        age_bars=level.age_bars,
        age_hours=level.age_hours,
        distance_abs=level.distance_abs,
        distance_atr=level.distance_atr,
        touch_count=level.touch_count,
        swing_strength=level.swing_strength,
        liquidity_score=level.liquidity_score,
        state=level.state,
        diagnostic_only=True,
    )


def _rolling_windows(profile_key: str) -> tuple[int, ...]:
    return (24, 48, 72) if profile_key == "B" else (30, 60, 90)


def _max_structure_age_bars(profile_key: str) -> int:
    return 48 if profile_key == "B" else 60


def _structure_hours(profile_key: str) -> float:
    return 1.0 if profile_key == "B" else 4.0


def _level_state(*, age_bars: int, distance_atr: float | None, profile_key: str) -> str:
    max_age = _max_structure_age_bars(profile_key)
    if age_bars > max_age * 2:
        return "expired"
    if age_bars > max_age:
        return "stale"
    if distance_atr is not None and distance_atr > 3.0:
        return "too_far"
    return "active"


def _touch_count(candles: Sequence[object], price: float, atr: float) -> int:
    if atr <= 0:
        return 0
    tolerance = atr * 0.25
    return sum(1 for candle in candles if float(candle.low) - tolerance <= price <= float(candle.high) + tolerance)


def _resolve_lifecycle(
    *,
    structure: Sequence[object],
    sweep_index: int,
    level: float,
    direction: str,
    max_reclaim: int,
    reclaim_windows: Sequence[int],
) -> dict[str, object]:
    sweep = structure[sweep_index]
    reclaim = None
    invalidated = False
    for offset, candle in enumerate(structure[sweep_index + 1 : sweep_index + max_reclaim + 1], start=1):
        if _invalidates(candle, sweep, direction):
            invalidated = True
            break
        if _is_reclaim(candle, level, direction):
            reclaim = candle
            break
    return {
        "reclaim": reclaim,
        "reclaim_ts": None if reclaim is None else int(getattr(reclaim, "timestamp_ms")),
        "signal_ts": None if reclaim is None else int(getattr(reclaim, "timestamp_ms")),
        "expiry_ts": int(getattr(structure[min(len(structure) - 1, sweep_index + max_reclaim)], "timestamp_ms")),
        "invalidated": invalidated,
        "reclaimed_within": {
            int(window): reclaim is not None and _bar_distance(structure, sweep, reclaim) <= int(window)
            for window in reclaim_windows
        },
    }


def _candidate_row(
    *,
    event_id: str,
    target,
    profile_key: str,
    direction: str,
    structure_level: StructureLevel,
    structure: Sequence[object],
    sweep_index: int,
    sweep,
    reclaim,
    entry_candle,
    atr: float,
    preset: BacktestPresetConfig,
    trend_candles: Sequence[object],
) -> dict[str, object]:
    entry = float(getattr(entry_candle, "open"))
    sweep_extreme = float(getattr(sweep, "low")) if direction == "long" else float(getattr(sweep, "high"))
    buffer = preset.execution.invalidation_buffer_atr
    stop = sweep_extreme - buffer * atr if direction == "long" else sweep_extreme + buffer * atr
    target_price = entry + abs(entry - stop) * 2.0 if direction == "long" else entry - abs(stop - entry) * 2.0
    stop_atr = abs(entry - stop) / atr if atr > 0 else None
    features = _context_features(target, profile_key, preset)
    sweep_volume = _volume_evidence(_candles_until(structure, int(getattr(sweep, "timestamp_ms"))), direction, features)
    reclaim_volume = _volume_evidence(_candles_until(structure, int(getattr(reclaim, "timestamp_ms"))), direction, features)
    choch = _detect_choch(structure, sweep_index, reclaim, direction)
    trend = build_market_regime(trend_candles)
    trend_direction = "" if trend is None or trend.direction is None else trend.direction
    trend_state = "missing" if trend is None else trend.status
    trend_aligned = trend_state == "TREND" and trend_direction == direction
    countertrend = trend_direction in {"long", "short"} and trend_direction != direction
    neutral_trend = not trend_aligned and not countertrend
    sweep_rvol = _rvol_value(sweep_volume)
    reclaim_rvol = _rvol_value(reclaim_volume)
    reclaim_bars = _bar_distance(structure, sweep, reclaim)
    displacement_body_atr = _body_atr(reclaim, atr)
    choch_body_atr = None if choch is None else _body_atr(choch, atr)
    confirmation = _entry_confirmation_tags(
        structure=structure,
        reclaim=reclaim,
        level=structure_level.price,
        direction=direction,
        atr=atr,
    )
    entry_dt = datetime.fromtimestamp(int(getattr(entry_candle, "timestamp_ms")) / 1000, tz=UTC)
    utc_hour = entry_dt.hour
    return {
        "event_id": event_id,
        "asset": target.canonical_symbol.split("/", 1)[0].upper(),
        "symbol": target.canonical_symbol,
        "inst_id": target.inst_id,
        "inst_type": target.inst_type,
        "venue": target.venue,
        "profile": profile_key,
        "direction": direction,
        "structure_level": structure_level.price,
        "structure_level_source": structure_level.source,
        "structure_level_type": structure_level.level_type,
        "structure_time": int(getattr(structure_level.candle, "timestamp_ms")),
        "structure_level_age_bars": structure_level.age_bars,
        "distance_to_current_price_atr_structure_tf": structure_level.distance_atr,
        "liquidity_score": structure_level.liquidity_score,
        "level_touch_count": structure_level.touch_count,
        "level_freshness_score": _freshness_score(structure_level.age_bars),
        "sweep_time": int(getattr(sweep, "timestamp_ms")),
        "reclaim_time": int(getattr(reclaim, "timestamp_ms")),
        "signal_time": int(getattr(reclaim, "timestamp_ms")),
        "entry_time": int(getattr(entry_candle, "timestamp_ms")),
        "event_state": "emitted",
        "reclaim_bars": reclaim_bars,
        "reclaim_within_1": reclaim_bars <= 1,
        "reclaim_within_3": reclaim_bars <= 3,
        "reclaim_within_5": reclaim_bars <= 5,
        "entry_price": entry,
        "reclaim_price": float(getattr(reclaim, "close")),
        "sweep_extreme": sweep_extreme,
        "stop_price": stop,
        "stop_atr_entry_tf": stop_atr,
        "stop_atr_structure_tf": stop_atr,
        "target_price": target_price,
        "target_r": 2.0,
        "wick_ratio": _wick_ratio(sweep, direction),
        "wick_tier": _wick_tier(_wick_ratio(sweep, direction)),
        "displacement_after_reclaim": displacement_body_atr >= 0.8,
        "displacement_body_atr": displacement_body_atr,
        "displacement_body_ge_0_8_atr": displacement_body_atr >= 0.8,
        "displacement_body_ge_1_0_atr": displacement_body_atr >= 1.0,
        "displacement_body_ge_1_2_atr": displacement_body_atr >= 1.2,
        "displacement_close_beyond_structure": _is_reclaim(reclaim, structure_level.price, direction),
        "displacement_direction_valid": _close_direction_valid(reclaim, direction),
        "pullback_retest_after_reclaim": confirmation["pullback_retest_after_reclaim"],
        "second_push_after_reclaim": confirmation["second_push_after_reclaim"],
        "fvg_exists": confirmation["fvg_exists"],
        "fvg_midpoint": confirmation["fvg_midpoint"],
        "fvg_retest_hit": confirmation["fvg_retest_hit"],
        "sweep_rvol": sweep_rvol,
        "reclaim_rvol": reclaim_rvol,
        "rolling_rvol": sweep_volume.get("rolling_rvol"),
        "tod_dow_rvol": sweep_volume.get("tod_dow_rvol"),
        "volume_baseline_mode": sweep_volume.get("volume_baseline_mode"),
        "volume_bucket_sample_count": sweep_volume.get("volume_bucket_sample_count"),
        "used_fallback_volume_baseline": sweep_volume.get("used_fallback_volume_baseline"),
        "sweep_rvol_tier": _sweep_rvol_tier(sweep_rvol),
        "reclaim_rvol_tier": _reclaim_rvol_tier(reclaim_rvol),
        "volume_missing_reason": "" if sweep_rvol is not None and reclaim_rvol is not None else "insufficient_volume_baseline",
        "choch_detected": choch is not None,
        "choch_direction": direction if choch is not None else "",
        "choch_time": None if choch is None else int(getattr(choch, "timestamp_ms")),
        "choch_timeframe": get_profile(profile_key).structure_timeframe,
        "bars_reclaim_to_choch": None if choch is None else max(0, _bar_distance(structure, reclaim, choch)),
        "choch_valid_for_direction": choch is not None,
        "choch_body_atr": choch_body_atr,
        "choch_strength": _choch_strength(choch_body_atr),
        "choch_close_beyond_swing": choch is not None,
        "choch_missing_reason": "" if choch is not None else "no_confirmed_choch_within_reclaim_window",
        "entry_confirmation_missing_reason": _entry_confirmation_missing_reason(confirmation, choch is not None),
        "trend_state": trend_state,
        "trend_timeframe": get_profile(profile_key).trend_timeframe,
        "trend_direction": trend_direction,
        "trend_aligned": trend_aligned,
        "countertrend": countertrend,
        "neutral_trend": neutral_trend,
        "trend_missing_reason": "" if trend is not None else "insufficient_trend_history",
        "liquidity_score_tier": _score_tier(structure_level.liquidity_score),
        "pdh_pdl_tag": structure_level.source == "previous_day_high_low",
        "eqh_eql_tag": structure_level.source == "equal_high_low",
        "session_high_low_tag": structure_level.source == "session_high_low",
        "utc_hour": utc_hour,
        "funding_window_proximity": _funding_window_proximity(utc_hour),
        "london_open_window": 7 <= utc_hour <= 9,
        "ny_open_window": 13 <= utc_hour <= 15,
        "london_ny_overlap": 13 <= utc_hour <= 16,
        "funding_settlement_plus_2h_window": utc_hour in {0, 1, 2, 8, 9, 10, 16, 17, 18},
        "stop_bucket": _stop_bucket(stop_atr),
    }


def _summary_rows(
    groups: Mapping[tuple[str, str, str, str, str, str], Counter[str]],
    metrics: Mapping[tuple[str, str, str, str, str, str], Mapping[str, Sequence[float]]],
    event_rows: Sequence[Mapping[str, object]],
    candidate_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    fields = (
        "structure_levels_available_count",
        "structure_levels_scanned_count",
        "sweep_events_count",
        "reclaim_events_count",
        "signal_events_count",
        "fresh_entry_candidates_count",
        "expired_events_count",
        "invalidated_events_count",
        "total_structure_levels",
        "active_structure_levels",
        "fresh_structure_levels",
        "stale_structure_levels",
        "expired_structure_levels",
        "too_far_structure_levels",
        "bars_near_structure_count",
        "bars_cross_structure_intrabar_count",
        "bars_close_back_inside_count",
        "reclaimed_within_1_bars",
        "reclaimed_within_2_bars",
        "reclaimed_within_3_bars",
        "reclaimed_within_5_bars",
        "reclaimed_within_8_bars",
        "expired_without_reclaim",
        "next_entry_bar_found_count",
        "entry_candidate_emitted_count",
        "missed_due_to_alignment_count",
        "missed_due_to_cache_window_boundary_count",
        "missed_due_to_duplicate_guard_count",
        "sweep_reject_no_intrabar_cross",
    )
    for key, counts in sorted(groups.items()):
        asset, profile, direction, level_source, level_type, timeframe = key
        row: dict[str, object] = {
            "asset": asset,
            "profile": profile,
            "direction": direction,
            "structure_level_source": level_source,
            "structure_level_type": level_type,
            "structure_timeframe": timeframe,
        }
        for field in fields:
            row[field] = counts[field]
        row.update(_metric_fields(metrics.get(key, {})))
        rows.append(row)
    return tuple(rows)


def _duplicate_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    counts = Counter(str(row.get("event_id", "")) for row in rows)
    dupes = [count for count in counts.values() if count > 1]
    return {
        "duplicate_candidate_count": sum(count - 1 for count in dupes),
        "duplicated_sweep_event_count": len(dupes),
        "avg_duplicates_per_sweep_event": sum(dupes) / len(dupes) if dupes else 0.0,
        "max_duplicates_per_sweep_event": max(dupes) if dupes else 0,
    }


def _is_sweep(candle: object, level: float, direction: str) -> bool:
    return float(getattr(candle, "low")) < level if direction == "long" else float(getattr(candle, "high")) > level


def _is_reclaim(candle: object, level: float, direction: str) -> bool:
    return float(getattr(candle, "close")) > level if direction == "long" else float(getattr(candle, "close")) < level


def _invalidates(candle: object, sweep: object, direction: str) -> bool:
    return float(getattr(candle, "low")) < float(getattr(sweep, "low")) if direction == "long" else float(getattr(candle, "high")) > float(getattr(sweep, "high"))


def _next_entry(entry: Sequence[object], signal_ts: int | None) -> object | None:
    if signal_ts is None:
        return None
    return next((candle for candle in entry if int(getattr(candle, "timestamp_ms")) > signal_ts), None)


def _atr(candles: Sequence[object]) -> float:
    recent = tuple(candles[-15:])
    if len(recent) >= 15:
        return average_true_range(
            [float(candle.high) for candle in recent],
            [float(candle.low) for candle in recent],
            [float(candle.close) for candle in recent],
            period=14,
        )
    ranges = [float(candle.high) - float(candle.low) for candle in candles]
    return sum(ranges) / len(ranges) if ranges else 0.0


def _near_structure(candle: object, level: float, atr: float) -> bool:
    distance_atr = _nearest_structure_distance_atr(candle, level, atr)
    return distance_atr is not None and distance_atr <= 1.0


def _nearest_structure_distance_atr(candle: object, level: float, atr: float) -> float | None:
    if atr <= 0:
        return None
    distance = min(abs(float(candle.high) - level), abs(float(candle.low) - level), abs(float(candle.close) - level))
    return distance / atr


def _index_of(candles: Sequence[object], timestamp_ms: int) -> int:
    return next((index for index, candle in enumerate(candles) if int(getattr(candle, "timestamp_ms")) == timestamp_ms), 0)


def _bar_distance(candles: Sequence[object], first: object, second: object) -> int:
    return max(0, _index_of(candles, int(getattr(second, "timestamp_ms"))) - _index_of(candles, int(getattr(first, "timestamp_ms"))))


def _freshness_bucket(age_bars: int) -> str:
    if age_bars <= 20:
        return "fresh_structure_levels"
    if age_bars <= 50:
        return "stale_structure_levels"
    return "expired_structure_levels"


def _wick_ratio(candle: object, direction: str) -> float:
    high = float(getattr(candle, "high"))
    low = float(getattr(candle, "low"))
    width = high - low
    if width <= 0:
        return 0.0
    if direction == "long":
        wick = min(float(getattr(candle, "open")), float(getattr(candle, "close"))) - low
    else:
        wick = high - max(float(getattr(candle, "open")), float(getattr(candle, "close")))
    return max(0.0, wick) / width


def _wick_tier(value: float | None) -> str:
    if value is None:
        return "unknown_wick"
    if value < 0.25:
        return "low_wick"
    if value < 0.50:
        return "medium_wick"
    return "high_wick"


def _sweep_rvol_tier(value: float | None) -> str:
    if value is None:
        return "unknown_sweep_rvol"
    if value < 1.5:
        return "low_sweep_rvol"
    if value < 2.5:
        return "normal_sweep_rvol"
    return "high_sweep_rvol"


def _reclaim_rvol_tier(value: float | None) -> str:
    if value is None:
        return "unknown_reclaim"
    if value <= 1.2:
        return "ideal_reclaim"
    if value <= 1.6:
        return "acceptable_reclaim"
    return "high_reclaim_rvol"


def _score_tier(value: float | None) -> str:
    if value is None:
        return "unknown_score"
    if value < 1.0:
        return "low_score"
    if value < 3.0:
        return "medium_score"
    return "high_score"


def _body_atr(candle, atr: float) -> float:
    if atr <= 0:
        return 0.0
    return abs(float(getattr(candle, "close")) - float(getattr(candle, "open"))) / atr


def _close_direction_valid(candle, direction: str) -> bool:
    if direction == "long":
        return float(getattr(candle, "close")) > float(getattr(candle, "open"))
    return float(getattr(candle, "close")) < float(getattr(candle, "open"))


def _entry_confirmation_tags(
    *,
    structure: Sequence[object],
    reclaim: object,
    level: float,
    direction: str,
    atr: float,
) -> dict[str, object]:
    reclaim_index = _index_of(structure, int(getattr(reclaim, "timestamp_ms")))
    future = tuple(structure[reclaim_index + 1 : reclaim_index + 4])
    fvg = _fvg_after_reclaim(structure, reclaim_index, direction)
    return {
        "pullback_retest_after_reclaim": any(_retests_level(candle, level, direction) for candle in future),
        "second_push_after_reclaim": any(_second_push(candle, reclaim, direction) for candle in future),
        "fvg_exists": fvg["exists"],
        "fvg_midpoint": fvg["midpoint"],
        "fvg_retest_hit": fvg["exists"] and any(_retests_fvg(candle, fvg["midpoint"], direction) for candle in future),
        "diagnostic_window_bars": len(future),
    }


def _retests_level(candle: object, level: float, direction: str) -> bool:
    if direction == "long":
        return float(getattr(candle, "low")) <= level <= float(getattr(candle, "close"))
    return float(getattr(candle, "close")) <= level <= float(getattr(candle, "high"))


def _second_push(candle: object, reclaim: object, direction: str) -> bool:
    if direction == "long":
        return float(getattr(candle, "close")) > float(getattr(reclaim, "high"))
    return float(getattr(candle, "close")) < float(getattr(reclaim, "low"))


def _fvg_after_reclaim(structure: Sequence[object], reclaim_index: int, direction: str) -> dict[str, object]:
    if reclaim_index < 2:
        return {"exists": False, "midpoint": None}
    left = structure[reclaim_index - 2]
    reclaim = structure[reclaim_index]
    if direction == "long" and float(getattr(reclaim, "low")) > float(getattr(left, "high")):
        midpoint = (float(getattr(reclaim, "low")) + float(getattr(left, "high"))) / 2.0
        return {"exists": True, "midpoint": midpoint}
    if direction == "short" and float(getattr(reclaim, "high")) < float(getattr(left, "low")):
        midpoint = (float(getattr(reclaim, "high")) + float(getattr(left, "low"))) / 2.0
        return {"exists": True, "midpoint": midpoint}
    return {"exists": False, "midpoint": None}


def _retests_fvg(candle: object, midpoint: object, direction: str) -> bool:
    if midpoint is None:
        return False
    value = float(midpoint)
    if direction == "long":
        return float(getattr(candle, "low")) <= value <= float(getattr(candle, "high"))
    return float(getattr(candle, "low")) <= value <= float(getattr(candle, "high"))


def _choch_strength(choch_body_atr: float | None) -> str:
    if choch_body_atr is None:
        return "missing_choch"
    if choch_body_atr >= 1.2:
        return "strong_choch"
    if choch_body_atr >= 0.8:
        return "medium_choch"
    return "weak_choch"


def _entry_confirmation_missing_reason(confirmation: Mapping[str, object], has_choch: bool) -> str:
    missing = []
    if not has_choch:
        missing.append("choch_missing")
    if not confirmation.get("pullback_retest_after_reclaim"):
        missing.append("pullback_retest_missing")
    if not confirmation.get("second_push_after_reclaim"):
        missing.append("second_push_missing")
    if not confirmation.get("fvg_exists"):
        missing.append("fvg_missing")
    return ",".join(missing)


def _freshness_score(age_bars: int) -> float:
    return max(0.0, 1.0 - min(age_bars, 100) / 100.0)


def _funding_window_proximity(utc_hour: int) -> str:
    if utc_hour in {0, 8, 16}:
        return "funding_hour"
    if utc_hour in {1, 2, 9, 10, 17, 18}:
        return "funding_plus_2h"
    return "away_from_funding"


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stop_bucket(value: float | None) -> str:
    if value is None:
        return "unknown_stop"
    if value <= 3:
        return "healthy_stop"
    if value <= 8:
        return "borderline_stop"
    return "broken_stop"


def _metric_fields(metrics: Mapping[str, Sequence[float]]) -> dict[str, object]:
    age = _distribution(metrics.get("structure_age_bars", ()))
    distance = _distribution(metrics.get("nearest_structure_distance_atr", ()))
    return {
        "avg_structure_age_bars": age["avg"],
        "p50_structure_age_bars": age["p50"],
        "p75_structure_age_bars": age["p75"],
        "p90_structure_age_bars": age["p90"],
        "p50_nearest_structure_distance_atr": distance["p50"],
        "p75_nearest_structure_distance_atr": distance["p75"],
        "p90_nearest_structure_distance_atr": distance["p90"],
    }


def _distribution(values: Sequence[float]) -> dict[str, object]:
    numbers = sorted(float(value) for value in values)
    if not numbers:
        return {"avg": None, "p50": None, "p75": None, "p90": None}
    return {
        "avg": sum(numbers) / len(numbers),
        "p50": _percentile(numbers, 0.50),
        "p75": _percentile(numbers, 0.75),
        "p90": _percentile(numbers, 0.90),
    }


def _percentile(numbers: Sequence[float], q: float) -> float:
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * q
    low = int(position)
    high = min(low + 1, len(numbers) - 1)
    fraction = position - low
    return numbers[low] * (1.0 - fraction) + numbers[high] * fraction


def _event_id(inst_id: str, profile: str, direction: str, level_source: str, level_type: str, level: float, sweep_ts: int, reclaim_ts: object) -> str:
    raw = f"{inst_id}|{profile}|{direction}|{level_source}|{level_type}|{level:.8f}|{sweep_ts}|{reclaim_ts}"
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text("".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


__all__ = (
    "FreshLRScannerResult",
    "build_fresh_lr_report",
    "scan_fresh_liquidity_reversal",
    "write_fresh_lr_artifacts",
)
