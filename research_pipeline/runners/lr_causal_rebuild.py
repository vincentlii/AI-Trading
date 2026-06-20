from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run
from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import LRCausalEvent
from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import (
    build_all_previous_day_levels,
    build_confirmed_swing_levels,
    build_session_levels,
    detect_causal_events,
)


DEVELOPMENT_START = "2020-12-31"
DEVELOPMENT_END = "2024-11-30"
HOLDOUT_START = "2024-12-01"
HOLDOUT_END = "2026-05-27"
MAX_HOLDING_HOURS = 20
FORWARD_HORIZON_BARS = (1, 2, 4, 8, 16, 32, 80)


@dataclass(frozen=True)
class LRCausalAnatomyResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    dataset_start: str
    dataset_end: str
    raw_level_count: int
    event_count: int
    candidate_count: int
    diagnostic_count: int
    run_root: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def development_candidate_cutoff(holdout_start_ms: int) -> int:
    return int(holdout_start_ms) - MAX_HOLDING_HOURS * 60 * 60 * 1000


def validate_development_window(start_date: str, end_date: str) -> tuple[str, str]:
    start = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end = datetime.fromisoformat(end_date).replace(tzinfo=UTC)
    holdout = datetime.fromisoformat(HOLDOUT_START).replace(tzinfo=UTC)
    if start >= end:
        raise ValueError("development start must be before end")
    if end >= holdout:
        raise ValueError("development window cannot cross sealed holdout")
    return start_date, end_date


def level_validity_windows(
    levels: Sequence[object],
    *,
    end_time: int,
) -> dict[str, int]:
    grouped: dict[tuple[str, str], list[object]] = defaultdict(list)
    for level in levels:
        grouped[(str(getattr(level, "family")), str(getattr(level, "direction")))].append(level)
    windows: dict[str, int] = {}
    for family_levels in grouped.values():
        ordered = sorted(family_levels, key=lambda row: int(getattr(row, "confirmed_time")))
        for index, level in enumerate(ordered):
            next_confirmation = (
                int(getattr(ordered[index + 1], "confirmed_time"))
                if index + 1 < len(ordered)
                else int(end_time)
            )
            windows[str(getattr(level, "level_id"))] = min(next_confirmation, int(end_time))
    return windows


def causal_atr(
    candles: Sequence[object],
    *,
    cutoff_time: int,
    timeframe_ms: int,
    period: int = 14,
) -> float | None:
    close_times, values = build_causal_atr_index(
        candles,
        timeframe_ms=timeframe_ms,
        period=period,
    )
    return atr_from_index(close_times, values, cutoff_time=cutoff_time)


def build_causal_atr_index(
    candles: Sequence[object],
    *,
    timeframe_ms: int,
    period: int = 14,
) -> tuple[list[int], list[float]]:
    confirmed = [candle for candle in candles if bool(getattr(candle, "is_confirmed", False))]
    if len(confirmed) < period:
        return [], []
    true_ranges: list[float] = []
    for index, candle in enumerate(confirmed):
        high = float(getattr(candle, "high"))
        low = float(getattr(candle, "low"))
        if index == 0:
            true_ranges.append(high - low)
            continue
        previous_close = float(getattr(confirmed[index - 1], "close"))
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    rolling_sum = sum(true_ranges[:period])
    close_times = [int(getattr(confirmed[period - 1], "timestamp_ms")) + timeframe_ms]
    values = [rolling_sum / period]
    for index in range(period, len(confirmed)):
        rolling_sum += true_ranges[index] - true_ranges[index - period]
        close_times.append(int(getattr(confirmed[index], "timestamp_ms")) + timeframe_ms)
        values.append(rolling_sum / period)
    return close_times, values


def atr_from_index(
    close_times: Sequence[int],
    values: Sequence[float],
    *,
    cutoff_time: int,
) -> float | None:
    index = bisect_right(close_times, cutoff_time) - 1
    if index < 0:
        return None
    return float(values[index])


def run_lr_causal_anatomy(
    *,
    repository,
    preset,
    output_root: Path,
    start_date: str = DEVELOPMENT_START,
    end_date: str = DEVELOPMENT_END,
) -> LRCausalAnatomyResult:
    validate_development_window(start_date, end_date)
    start_ms, end_ms = _date_bounds(start_date, end_date)
    candidate_cutoff = development_candidate_cutoff(end_ms + 1)
    context_start = start_ms - 30 * 24 * 60 * 60 * 1000
    candidate_rows: list[dict[str, object]] = []
    level_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    filter_rows: list[dict[str, object]] = []
    raw_level_count = 0
    event_count = 0

    for target in preset.to_scan_config().targets:
        load_kwargs = {"venue": target.venue, "inst_type": target.inst_type, "confirmed_only": True}
        candles_15m = tuple(
            repository.load_range(target.inst_id, "15m", context_start, end_ms, **load_kwargs)
        )
        candles_4h = tuple(
            repository.load_range(target.inst_id, "4H", context_start, end_ms, **load_kwargs)
        )
        levels, events, candidates, diagnostics, rejections = _scan_target_anatomy(
            instrument=target.inst_id,
            candles_15m=candles_15m,
            candles_4h=candles_4h,
            start_ms=start_ms,
            candidate_cutoff=candidate_cutoff,
        )
        raw_level_count += len(levels)
        level_rows.extend({**level.as_dict(), "instrument": target.inst_id} for level in levels)
        event_count += len(events)
        candidate_rows.extend(candidates)
        diagnostic_rows.extend(diagnostics)
        filter_rows.extend(rejections)
        filter_rows.extend(
            {
                "row_type": "filter_decision",
                "candidate_id": row["candidate_id"],
                "event_id": row["event_id"],
                "market_event_key": row["market_event_key"],
                "decision": "approved_for_anatomy_diagnostics",
                "eligible_for_performance": False,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
            for row in candidates
        )

    run_root = Path(output_root) / f"anatomy_development_{start_date}_{end_date}"
    run_root.mkdir(parents=True, exist_ok=True)
    result = LRCausalAnatomyResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        dataset_start=start_date,
        dataset_end=end_date,
        raw_level_count=raw_level_count,
        event_count=event_count,
        candidate_count=len(candidate_rows),
        diagnostic_count=len(diagnostic_rows),
        run_root=str(run_root),
    )
    _write_anatomy_outputs(
        run_root=run_root,
        result=result,
        preset=preset,
        level_rows=level_rows,
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        diagnostic_rows=diagnostic_rows,
    )
    return result


def _scan_target_anatomy(
    *,
    instrument: str,
    candles_15m: Sequence[object],
    candles_4h: Sequence[object],
    start_ms: int,
    candidate_cutoff: int,
) -> tuple[
    tuple[object, ...],
    tuple[LRCausalEvent, ...],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    levels = tuple(
        sorted(
            (
                *build_session_levels(candles_15m, cutoff_time=candidate_cutoff),
                *build_all_previous_day_levels(candles_15m, cutoff_time=candidate_cutoff),
                *build_confirmed_swing_levels(candles_4h, cutoff_time=candidate_cutoff),
            ),
            key=lambda row: (row.confirmed_time, row.family, row.direction),
        )
    )
    validity = level_validity_windows(levels, end_time=candidate_cutoff + 1)
    timestamps = [int(getattr(candle, "timestamp_ms")) for candle in candles_15m]
    atr_15m_times, atr_15m_values = build_causal_atr_index(
        candles_15m,
        timeframe_ms=15 * 60 * 1000,
    )
    atr_4h_times, atr_4h_values = build_causal_atr_index(
        candles_4h,
        timeframe_ms=4 * 60 * 60 * 1000,
    )
    atr_15m_at = lambda timestamp: atr_from_index(
        atr_15m_times,
        atr_15m_values,
        cutoff_time=timestamp,
    )
    atr_4h_at = lambda timestamp: atr_from_index(
        atr_4h_times,
        atr_4h_values,
        cutoff_time=timestamp,
    )
    events: list[LRCausalEvent] = []
    for level in levels:
        window_start = bisect_left(timestamps, level.confirmed_time)
        window_end = bisect_left(timestamps, validity[level.level_id])
        detected = detect_causal_events(
            levels=(level,),
            candles_15m=candles_15m[window_start:window_end],
            atr_15m=atr_15m_at,
            atr_4h=atr_4h_at,
            instrument=instrument,
        )
        events.extend(
            event
            for event in detected
            if start_ms <= event.reclaim_time <= candidate_cutoff
        )

    candidates: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for event in events:
        try:
            candidate, event_diagnostics = build_anatomy_rows(
                event,
                candles_15m,
                timestamps=timestamps,
            )
        except ValueError as error:
            rejections.append(anatomy_rejection_row(event, str(error)))
            continue
        candidates.append(candidate)
        diagnostics.extend(event_diagnostics)
    return levels, tuple(events), candidates, diagnostics, rejections


def anatomy_rejection_row(event: LRCausalEvent, reason: str) -> dict[str, object]:
    return {
        "row_type": "filter_decision",
        "event_id": event.event_id,
        "market_event_key": event.market_event_key,
        "level_id": event.level_id,
        "level_family": event.level_family,
        "direction": event.direction,
        "decision": "rejected",
        "reject_reason": reason,
        "eligible_for_performance": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _write_anatomy_outputs(
    *,
    run_root: Path,
    result: LRCausalAnatomyResult,
    preset,
    level_rows: Sequence[Mapping[str, object]],
    candidate_rows: Sequence[Mapping[str, object]],
    filter_rows: Sequence[Mapping[str, object]],
    diagnostic_rows: Sequence[Mapping[str, object]],
) -> None:
    summary_rows = _diagnostic_summaries(diagnostic_rows)
    artifact_rows: dict[str, Sequence[Mapping[str, object]]] = {
        "level_rows.jsonl": level_rows,
        "candidate_rows.jsonl": candidate_rows,
        "filter_results.jsonl": filter_rows,
        "execution_rows.jsonl": (),
        "closed_trade_rows.jsonl": (),
        "variant_closed_trade_rows.jsonl": (),
        "diagnostic_rows.jsonl": diagnostic_rows,
        "summary_rows.jsonl": summary_rows,
        "variant_summary_rows.jsonl": (),
        "robustness_rows.jsonl": (),
    }
    for name, rows in artifact_rows.items():
        _write_jsonl(run_root / name, rows)
    (run_root / "lr_causal_anatomy_result.json").write_text(result.as_json() + "\n", encoding="utf-8")
    (run_root / "lr_causal_anatomy_report.md").write_text(_anatomy_report(result), encoding="utf-8")
    manifest = {
        "strategy": "liquidity_reversal",
        "stage": "lr_causal_rebuild_anatomy",
        "schema_version": "causal_anatomy.v4",
        "atr_reference_time": "sweep_bar_close",
        "dataset_window": [result.dataset_start, result.dataset_end],
        "proposal_only": True,
        "formal_conclusion_enabled": False,
        "audit_status": "not_run_no_closed_trade_unverifiable",
        "holdout_accessed": False,
        "config_fingerprint": preset.config_fingerprint,
        "entry_model": "reclaim_market_next_15m_open",
        "diagnostics_are_performance": False,
        "artifact_paths": {name.removesuffix(".jsonl"): name for name in artifact_rows},
        "audit_profile": {
            "required_time_fields": [
                "sweep_time",
                "reclaim_time",
                "signal_time",
                "entry_time",
            ],
            "time_order_checks": [
                ["sweep_before_reclaim", "sweep_time", "reclaim_time"],
                ["reclaim_before_entry", "reclaim_time", "entry_time"],
            ],
        },
    }
    (run_root / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index = build_index_for_directory(
        run_root,
        strategy="liquidity_reversal",
        stage="lr_causal_rebuild_anatomy",
        window=f"{result.dataset_start}_{result.dataset_end}",
        source_command="research_pipeline.cli.research lr-causal-rebuild --stage anatomy --mode development",
        config_hash=preset.config_fingerprint,
        pipeline_version="lr_causal_rebuild.v4",
        notes="Causal event anatomy only; no closed-trade performance conclusion.",
    )
    index_paths = write_artifact_index(index, run_root)
    register_research_run(
        registry_path=run_root / "research_run_registry.json",
        artifact_index_path=index_paths["json"],
        strategy="liquidity_reversal",
        stage="lr_causal_rebuild_anatomy",
        window=f"{result.dataset_start}_{result.dataset_end}",
        source_command="research_pipeline.cli.research lr-causal-rebuild --stage anatomy --mode development",
        adapter_version="lr_causal_rebuild.v4",
        notes="Causal LR level/event anatomy; holdout sealed.",
        tags=["lr", "causal_rebuild", "anatomy", "development"],
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=True,
        config_hash=preset.config_fingerprint,
    )


def _diagnostic_summaries(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["level_family"]), str(row["direction"]), int(row["horizon_minutes"]))].append(row)
    summaries: list[dict[str, object]] = []
    for (family, direction, horizon), group in sorted(grouped.items()):
        forward = [float(row["forward_R"]) for row in group]
        mfe = [float(row["MFE_R"]) for row in group]
        mae = [float(row["MAE_R"]) for row in group]
        forward_atr = [float(row["forward_ATR"]) for row in group]
        mfe_atr = [float(row["MFE_ATR"]) for row in group]
        mae_atr = [float(row["MAE_ATR"]) for row in group]
        summaries.append(
            {
                "row_type": "diagnostic_summary",
                "level_family": family,
                "direction": direction,
                "horizon_minutes": horizon,
                "event_count": len(group),
                "mean_forward_R": mean(forward),
                "median_forward_R": median(forward),
                "mean_MFE_R": mean(mfe),
                "mean_MAE_R": mean(mae),
                "mean_forward_ATR": mean(forward_atr),
                "median_forward_ATR": median(forward_atr),
                "mean_MFE_ATR": mean(mfe_atr),
                "mean_MAE_ATR": mean(mae_atr),
                "positive_forward_share": sum(value > 0 for value in forward) / len(forward),
                "eligible_for_performance": False,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return summaries


def _date_bounds(start_date: str, end_date: str) -> tuple[int, int]:
    start = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end = datetime.fromisoformat(end_date).replace(tzinfo=UTC) + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _anatomy_report(result: LRCausalAnatomyResult) -> str:
    return "\n".join(
        (
            "# LR Causal Rebuild Anatomy",
            "",
            "## 结论",
            "",
            "- 本阶段只分析因果 level/event 与 forward path，不形成收益结论。",
            "- holdout 未访问；closed_trade_rows 为空；Full Audit 尚不可执行。",
            f"- levels: {result.raw_level_count}",
            f"- events: {result.event_count}",
            f"- candidates: {result.candidate_count}",
            f"- diagnostics: {result.diagnostic_count}",
            "",
        )
    )


def build_anatomy_rows(
    event: LRCausalEvent,
    candles_15m: Sequence[object],
    *,
    timestamps: Sequence[int] | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    timestamp_index = timestamps
    if timestamp_index is None:
        timestamp_index = [int(getattr(candle, "timestamp_ms")) for candle in candles_15m]
    if len(timestamp_index) != len(candles_15m):
        raise ValueError("timestamp index must align with candles")
    entry_index = bisect_right(timestamp_index, event.reclaim_time)
    if entry_index >= len(candles_15m):
        raise ValueError("missing post-reclaim execution candle")
    entry_candle = candles_15m[entry_index]
    entry_time = int(getattr(entry_candle, "timestamp_ms"))
    entry_price = float(getattr(entry_candle, "open"))
    buffer = 0.10 * event.atr_15m
    stop_price = event.sweep_extreme - buffer if event.direction == "long" else event.sweep_extreme + buffer
    if event.direction == "long" and stop_price >= entry_price:
        raise ValueError("invalid long stop geometry")
    if event.direction == "short" and stop_price <= entry_price:
        raise ValueError("invalid short stop geometry")
    risk = entry_price - stop_price if event.direction == "long" else stop_price - entry_price
    if risk <= 0:
        raise ValueError("anatomy candidate requires positive stop distance")
    if event.atr_15m <= 0:
        raise ValueError("anatomy candidate requires positive 15m ATR")
    target_price = entry_price + 2.0 * risk if event.direction == "long" else entry_price - 2.0 * risk
    candidate_id = _stable_id(event.event_id, "reclaim_market_next_15m_open", entry_time)
    candidate = {
        **event.as_dict(),
        "row_type": "proposal_candidate",
        "candidate_id": candidate_id,
        "entry_model": "reclaim_market_next_15m_open",
        "order_type": "market",
        "feature_cutoff_time": event.reclaim_time,
        "signal_time": event.reclaim_time,
        "entry_time": entry_time,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "stop_atr_15m": risk / event.atr_15m if event.atr_15m > 0 else None,
        "bar_confirmed": True,
        "no_lookahead_safe": True,
        "eligible_for_performance": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }
    execution_path = candles_15m[entry_index : entry_index + FORWARD_HORIZON_BARS[-1]]
    diagnostics: list[dict[str, object]] = []
    for horizon in FORWARD_HORIZON_BARS:
        if horizon > len(execution_path):
            continue
        path = execution_path[:horizon]
        close = float(getattr(path[-1], "close"))
        if event.direction == "long":
            forward_r = (close - entry_price) / risk
            mfe_r = (max(float(getattr(row, "high")) for row in path) - entry_price) / risk
            mae_r = (entry_price - min(float(getattr(row, "low")) for row in path)) / risk
            forward_atr = (close - entry_price) / event.atr_15m
            mfe_atr = (max(float(getattr(row, "high")) for row in path) - entry_price) / event.atr_15m
            mae_atr = (entry_price - min(float(getattr(row, "low")) for row in path)) / event.atr_15m
        else:
            forward_r = (entry_price - close) / risk
            mfe_r = (entry_price - min(float(getattr(row, "low")) for row in path)) / risk
            mae_r = (max(float(getattr(row, "high")) for row in path) - entry_price) / risk
            forward_atr = (entry_price - close) / event.atr_15m
            mfe_atr = (entry_price - min(float(getattr(row, "low")) for row in path)) / event.atr_15m
            mae_atr = (max(float(getattr(row, "high")) for row in path) - entry_price) / event.atr_15m
        diagnostics.append(
            {
                "row_type": "diagnostic",
                "candidate_id": candidate_id,
                "event_id": event.event_id,
                "market_event_key": event.market_event_key,
                "level_family": event.level_family,
                "direction": event.direction,
                "horizon_bars": horizon,
                "horizon_minutes": horizon * 15,
                "forward_R": forward_r,
                "MFE_R": mfe_r,
                "MAE_R": mae_r,
                "forward_ATR": forward_atr,
                "MFE_ATR": mfe_atr,
                "MAE_ATR": mae_atr,
                "eligible_for_performance": False,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return candidate, diagnostics


def _stable_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]


__all__ = (
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "FORWARD_HORIZON_BARS",
    "HOLDOUT_END",
    "HOLDOUT_START",
    "LRCausalAnatomyResult",
    "MAX_HOLDING_HOURS",
    "atr_from_index",
    "anatomy_rejection_row",
    "build_anatomy_rows",
    "build_causal_atr_index",
    "causal_atr",
    "development_candidate_cutoff",
    "level_validity_windows",
    "run_lr_causal_anatomy",
    "validate_development_window",
)
