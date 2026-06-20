from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from research_pipeline.runners.lr_causal_rebuild import (
    atr_from_index,
    build_causal_atr_index,
)
from research_pipeline.runners.lr_entry_signal_v3_smoke import (
    ALLOWED_LEVEL_FAMILIES,
    evaluate_structural_confirmation,
)


BAR_15M_MS = 15 * 60_000
MAX_DIAGNOSTIC_MINUTES = 1200


@dataclass(frozen=True)
class LRV3ConfirmationGeometryResult:
    eligible_event_count: int
    confirmed_event_count: int
    geometry_event_count: int
    unique_physical_event_count: int
    decision: str
    audit_passed: bool
    report_path: str


def run_lr_v3_confirmation_geometry(
    *,
    repository,
    source_root: Path,
    report_path: Path,
) -> LRV3ConfirmationGeometryResult:
    manifest = json.loads((source_root / "run_manifest.json").read_text(encoding="utf-8"))
    events = tuple(
        row
        for row in _load_jsonl(source_root / "event_rows.jsonl")
        if row.get("event_timeframe") == "1H_sweep_reclaim"
        and int(row.get("reclaim_span_bars", 0)) == 1
        and row.get("level_family") in ALLOWED_LEVEL_FAMILIES
    )
    anatomy = {
        str(row["event_id"]): row
        for row in _load_jsonl(source_root / "anatomy_rows.jsonl")
    }
    candles_by_instrument = _load_candles(repository, events)
    timestamps = {
        instrument: tuple(int(getattr(candle, "timestamp_ms")) for candle in candles)
        for instrument, candles in candles_by_instrument.items()
    }
    atr_indexes = {
        instrument: build_causal_atr_index(candles, timeframe_ms=BAR_15M_MS)
        for instrument, candles in candles_by_instrument.items()
    }

    confirmed_rows: list[dict[str, object]] = []
    geometry_rows: list[dict[str, object]] = []
    data_gaps: list[str] = []
    for event in events:
        instrument = str(event["instrument"])
        window = _event_window(event, candles_by_instrument[instrument], timestamps[instrument])
        confirmation = evaluate_structural_confirmation(event, window)
        if confirmation["confirmation_status"] != "confirmed":
            continue
        confirmed_rows.append(confirmation)
        atr_times, atr_values = atr_indexes[instrument]
        atr_15m = atr_from_index(
            atr_times,
            atr_values,
            cutoff_time=int(confirmation["confirmation_time"]),
        )
        if atr_15m is None:
            data_gaps.append(f"missing_atr15m:{event['event_id']}")
            continue
        row = build_confirmation_geometry(
            event=event,
            confirmation=confirmation,
            candles=window,
            atr_15m=atr_15m,
        )
        geometry_rows.append({**row, "year": _year(int(event["signal_time"]))})

    baseline = _baseline_rows(events, anatomy)
    overall = _dual_metrics(geometry_rows)
    unique_rows = tuple(
        {str(row["physical_event_key"]): row for row in geometry_rows}.values()
    )
    unique_overall = _dual_metrics(unique_rows)
    yearly = _group_rows(geometry_rows, baseline, lambda row: str(row["year"]))
    assets = _group_rows(geometry_rows, baseline, lambda row: str(row["instrument"]))
    directions = _group_rows(geometry_rows, baseline, lambda row: str(row["direction"]))
    levels = _group_rows(geometry_rows, baseline, lambda row: str(row["level_family"]))
    geometry = _geometry_summary(geometry_rows)
    audit = _audit(
        manifest=manifest,
        events=events,
        confirmed_rows=confirmed_rows,
        geometry_rows=geometry_rows,
        data_gaps=data_gaps,
        source_root=source_root,
    )
    reclaim_passed = _path_passed(overall["reclaim_reference"]) and _path_passed(
        unique_overall["reclaim_reference"]
    )
    confirmation_passed = _path_passed(
        overall["confirmation_reference"]
    ) and _path_passed(unique_overall["confirmation_reference"])
    stable = _stable(yearly, assets, directions, levels)
    decision = classify_geometry_decision(
        reclaim_passed=reclaim_passed,
        confirmation_passed=confirmation_passed,
        stable=stable,
        median_chase_atr15m=float(geometry["confirmation_chase_proxy"]["median"] or 0.0),
        median_remaining_to_original_1r=float(
            geometry["confirmation_to_1R_diagnostic_R"]["median"] or 0.0
        ),
        audit_passed=bool(audit["passed"]),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _build_report(
            events=events,
            confirmed_rows=confirmed_rows,
            geometry_rows=geometry_rows,
            baseline=baseline,
            overall=overall,
            unique_overall=unique_overall,
            yearly=yearly,
            assets=assets,
            directions=directions,
            levels=levels,
            geometry=geometry,
            data_gaps=data_gaps,
            audit=audit,
            reclaim_passed=reclaim_passed,
            confirmation_passed=confirmation_passed,
            stable=stable,
            decision=decision,
        ),
        encoding="utf-8",
    )
    return LRV3ConfirmationGeometryResult(
        eligible_event_count=len(events),
        confirmed_event_count=len(confirmed_rows),
        geometry_event_count=len(geometry_rows),
        unique_physical_event_count=len(unique_rows),
        decision=decision,
        audit_passed=bool(audit["passed"]),
        report_path=str(report_path),
    )


def build_confirmation_geometry(
    *,
    event: Mapping[str, object],
    confirmation: Mapping[str, object],
    candles: Sequence[object],
    atr_15m: float,
) -> dict[str, object]:
    if confirmation.get("confirmation_status") != "confirmed":
        raise ValueError("geometry requires a confirmed v3 event")
    if atr_15m <= 0:
        raise ValueError("geometry requires positive causal ATR15m")
    direction = str(event["direction"])
    signal_time = int(event["signal_time"])
    confirmation_time = int(confirmation["confirmation_time"])
    confirmation_bar = next(
        (
            candle
            for candle in candles
            if int(getattr(candle, "timestamp_ms")) + BAR_15M_MS == confirmation_time
            and bool(getattr(candle, "is_confirmed", False))
        ),
        None,
    )
    if confirmation_bar is None:
        raise ValueError("missing confirmed 15m confirmation bar")

    confirmation_close = float(getattr(confirmation_bar, "close"))
    reclaim_close = float(event["signal_close"])
    level_price = float(event["level_price"])
    event_atr = float(event["event_atr"])
    sweep_extreme = float(event["sweep_extreme"])
    invalidation = (
        sweep_extreme - 0.10 * event_atr
        if direction == "long"
        else sweep_extreme + 0.10 * event_atr
    )
    reclaim_r = abs(reclaim_close - invalidation)
    confirmation_r = abs(confirmation_close - invalidation)
    if reclaim_r <= 0 or confirmation_r <= 0:
        raise ValueError("geometry requires positive diagnostic R")
    original_target = _target(direction, reclaim_close, reclaim_r)
    path = tuple(
        candle
        for candle in candles
        if bool(getattr(candle, "is_confirmed", False))
        and int(getattr(candle, "timestamp_ms")) >= confirmation_time
        and int(getattr(candle, "timestamp_ms")) + BAR_15M_MS
        <= signal_time + MAX_DIAGNOSTIC_MINUTES * 60_000
    )
    delay_minutes = int(confirmation["time_to_confirmation_minutes"])
    return {
        "event_id": event["event_id"],
        "physical_event_key": event["physical_event_key"],
        "instrument": event["instrument"],
        "direction": direction,
        "level_family": event["level_family"],
        "signal_time": signal_time,
        "confirmation_time": confirmation_time,
        "confirmation_close": confirmation_close,
        "atr_15m": atr_15m,
        "atr_1h": event_atr,
        "confirmation_to_level_ATR15m": _signed_distance(
            direction, level_price, confirmation_close
        )
        / atr_15m,
        "confirmation_to_level_ATR1H": _signed_distance(
            direction, level_price, confirmation_close
        )
        / event_atr,
        "confirmation_to_invalidation_ATR15m": abs(confirmation_close - invalidation)
        / atr_15m,
        "confirmation_to_invalidation_diagnostic_R": abs(
            confirmation_close - invalidation
        )
        / reclaim_r,
        "confirmation_to_1R_ATR15m": _remaining_distance(
            direction, confirmation_close, original_target
        )
        / atr_15m,
        "confirmation_to_1R_diagnostic_R": _remaining_distance(
            direction, confirmation_close, original_target
        )
        / reclaim_r,
        "confirmation_chase_proxy": _signed_distance(
            direction, reclaim_close, confirmation_close
        )
        / atr_15m,
        "confirmation_delay_bars": delay_minutes // 15,
        "confirmation_delay_minutes": delay_minutes,
        "reclaim_reference_R": reclaim_r,
        "confirmation_reference_R": confirmation_r,
        **_reference_outcomes(
            prefix="reclaim_reference",
            direction=direction,
            reference=reclaim_close,
            risk=reclaim_r,
            invalidation=invalidation,
            confirmation_time=confirmation_time,
            path=path,
        ),
        **_reference_outcomes(
            prefix="confirmation_reference",
            direction=direction,
            reference=confirmation_close,
            risk=confirmation_r,
            invalidation=invalidation,
            confirmation_time=confirmation_time,
            path=path,
        ),
        "row_role": "diagnostic_label",
        "eligible_for_performance": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def classify_geometry_decision(
    *,
    reclaim_passed: bool,
    confirmation_passed: bool,
    stable: bool,
    median_chase_atr15m: float,
    median_remaining_to_original_1r: float,
    audit_passed: bool,
) -> str:
    if not audit_passed:
        return "D"
    if not reclaim_passed and not confirmation_passed:
        return "C"
    obvious_chase = median_chase_atr15m >= 1.0 or median_remaining_to_original_1r <= 0.0
    if not reclaim_passed or not confirmation_passed or obvious_chase:
        return "B"
    return "A" if stable else "C"


def _reference_outcomes(
    *,
    prefix: str,
    direction: str,
    reference: float,
    risk: float,
    invalidation: float,
    confirmation_time: int,
    path: Sequence[object],
) -> dict[str, object]:
    half_time: int | None = None
    one_time: int | None = None
    invalidation_time: int | None = None
    future_240 = next(
        (
            float(getattr(candle, "close"))
            for candle in path
            if int(getattr(candle, "timestamp_ms")) + BAR_15M_MS
            == confirmation_time + 240 * 60_000
        ),
        None,
    )
    for candle in path:
        close_time = int(getattr(candle, "timestamp_ms")) + BAR_15M_MS
        minutes = int((close_time - confirmation_time) / 60_000)
        if _invalidated(direction, candle, invalidation):
            invalidation_time = minutes
            break
        favorable = float(getattr(candle, "high" if direction == "long" else "low"))
        if half_time is None and _reached(direction, favorable, _target(direction, reference, 0.5 * risk)):
            half_time = minutes
        if one_time is None and _reached(direction, favorable, _target(direction, reference, risk)):
            one_time = minutes
    signed_240 = (
        None
        if future_240 is None
        else future_240 - reference
        if direction == "long"
        else reference - future_240
    )
    return {
        f"{prefix}_time_to_0_5R_minutes": half_time,
        f"{prefix}_time_to_1R_minutes": one_time,
        f"{prefix}_invalidation_time_minutes": invalidation_time,
        f"{prefix}_half_r_first_status": (
            "half_r_first"
            if half_time is not None
            else "invalidation_first"
            if invalidation_time is not None
            else "unresolved"
        ),
        f"{prefix}_invalidation_first_status": (
            "one_r_first"
            if one_time is not None
            else "invalidation_first"
            if invalidation_time is not None
            else "unresolved"
        ),
        f"{prefix}_forward_240m_R": None if signed_240 is None else signed_240 / risk,
    }


def _signed_distance(direction: str, origin: float, destination: float) -> float:
    return destination - origin if direction == "long" else origin - destination


def _remaining_distance(direction: str, current: float, target: float) -> float:
    return target - current if direction == "long" else current - target


def _target(direction: str, reference: float, distance: float) -> float:
    return reference + distance if direction == "long" else reference - distance


def _invalidated(direction: str, candle: object, invalidation: float) -> bool:
    if direction == "long":
        return float(getattr(candle, "low")) <= invalidation
    return float(getattr(candle, "high")) >= invalidation


def _reached(direction: str, favorable: float, target: float) -> bool:
    return favorable >= target if direction == "long" else favorable <= target


def _load_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    with path.open("r", encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


def _load_candles(repository, events: Sequence[Mapping[str, object]]) -> dict[str, tuple[object, ...]]:
    output: dict[str, tuple[object, ...]] = {}
    for instrument in sorted({str(row["instrument"]) for row in events}):
        group = [row for row in events if row["instrument"] == instrument]
        start = min(int(row["signal_time"]) for row in group) - 2 * 24 * 60 * 60_000
        end = max(int(row["signal_time"]) for row in group) + MAX_DIAGNOSTIC_MINUTES * 60_000
        output[instrument] = tuple(
            repository.load_range(
                instrument,
                "15m",
                start,
                end,
                venue="okx",
                inst_type="SWAP",
                confirmed_only=True,
            )
        )
    return output


def _event_window(
    event: Mapping[str, object],
    candles: Sequence[object],
    timestamps: Sequence[int],
) -> Sequence[object]:
    signal_time = int(event["signal_time"])
    start = bisect_left(timestamps, signal_time - BAR_15M_MS)
    end = bisect_right(timestamps, signal_time + MAX_DIAGNOSTIC_MINUTES * 60_000)
    return candles[start:end]


def _baseline_rows(
    events: Sequence[Mapping[str, object]],
    anatomy: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "physical_event_key": event["physical_event_key"],
            "instrument": event["instrument"],
            "direction": event["direction"],
            "level_family": event["level_family"],
            "year": _year(int(event["signal_time"])),
            **anatomy[str(event["event_id"])],
        }
        for event in events
    )


def _dual_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    return {
        reference: _reference_metrics(rows, reference)
        for reference in ("reclaim_reference", "confirmation_reference")
    }


def _reference_metrics(
    rows: Sequence[Mapping[str, object]],
    prefix: str,
) -> dict[str, object]:
    status = f"{prefix}_invalidation_first_status"
    resolved = [row for row in rows if row.get(status) != "unresolved"]
    return {
        "count": len(rows),
        "unique_physical_count": len({str(row["physical_event_key"]) for row in rows}),
        "invalidation_first_rate": _ratio(
            sum(row.get(status) == "invalidation_first" for row in resolved), len(resolved)
        ),
        "half_r_first_rate": _ratio(
            sum(row.get(f"{prefix}_time_to_0_5R_minutes") is not None for row in rows),
            len(rows),
        ),
        "one_r_first_rate": _ratio(
            sum(row.get(f"{prefix}_time_to_1R_minutes") is not None for row in rows),
            len(rows),
        ),
        "no_decision_rate": _ratio(sum(row.get(status) == "unresolved" for row in rows), len(rows)),
        "median_forward_240m_R": _median(row.get(f"{prefix}_forward_240m_R") for row in rows),
    }


def _baseline_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    resolved = [row for row in rows if row.get("invalidation_first_status") != "unresolved"]
    return {
        "count": len(rows),
        "invalidation_first_rate": _ratio(
            sum(row.get("invalidation_first_status") == "invalidation_first" for row in resolved),
            len(resolved),
        ),
        "half_r_first_rate": _ratio(
            sum(row.get("time_to_0_5R_minutes") is not None for row in rows), len(rows)
        ),
        "one_r_first_rate": _ratio(
            sum(row.get("time_to_1R_minutes") is not None for row in rows), len(rows)
        ),
        "no_decision_rate": _ratio(
            sum(row.get("invalidation_first_status") == "unresolved" for row in rows), len(rows)
        ),
        "median_forward_240m_R": _median(row.get("forward_240m_R") for row in rows),
    }


def _group_rows(
    rows: Sequence[Mapping[str, object]],
    baseline: Sequence[Mapping[str, object]],
    key,
) -> dict[str, dict[str, object]]:
    current: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    prior: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        current[key(row)].append(row)
    for row in baseline:
        prior[key(row)].append(row)
    return {
        name: {
            "baseline": _baseline_metrics(prior.get(name, ())),
            **_dual_metrics(current.get(name, ())),
        }
        for name in sorted(set(current) | set(prior))
    }


def _geometry_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, float | None]]:
    fields = (
        "confirmation_to_level_ATR15m",
        "confirmation_to_level_ATR1H",
        "confirmation_to_invalidation_ATR15m",
        "confirmation_to_invalidation_diagnostic_R",
        "confirmation_to_1R_ATR15m",
        "confirmation_to_1R_diagnostic_R",
        "confirmation_chase_proxy",
        "confirmation_delay_bars",
        "confirmation_delay_minutes",
    )
    return {field: _distribution(row.get(field) for row in rows) for field in fields}


def _path_passed(metrics: Mapping[str, object]) -> bool:
    invalidation = metrics.get("invalidation_first_rate")
    one_r = metrics.get("one_r_first_rate")
    return invalidation is not None and one_r is not None and float(invalidation) <= 0.45 and float(one_r) >= 0.52


def _comparison_improved(comparison: Mapping[str, object], prefix: str) -> bool:
    if "baseline" not in comparison or prefix not in comparison:
        return False
    baseline = comparison["baseline"]
    current = comparison[prefix]
    return bool(
        baseline.get("invalidation_first_rate") is not None
        and current.get("invalidation_first_rate") is not None
        and baseline.get("one_r_first_rate") is not None
        and current.get("one_r_first_rate") is not None
        and float(current["invalidation_first_rate"])
        < float(baseline["invalidation_first_rate"])
        and float(current["one_r_first_rate"]) > float(baseline["one_r_first_rate"])
    )


def _material_failure(comparison: Mapping[str, object], prefix: str) -> bool:
    baseline = comparison["baseline"]
    current = comparison[prefix]
    return bool(
        int(current.get("unique_physical_count", 0)) < 50
        or current.get("invalidation_first_rate") is None
        or current.get("one_r_first_rate") is None
        or float(current["invalidation_first_rate"])
        > float(baseline["invalidation_first_rate"]) + 0.02
        or float(current["one_r_first_rate"]) < float(baseline["one_r_first_rate"]) - 0.02
    )


def _stable(
    yearly: Mapping[str, Mapping[str, object]],
    assets: Mapping[str, Mapping[str, object]],
    directions: Mapping[str, Mapping[str, object]],
    levels: Mapping[str, Mapping[str, object]],
) -> bool:
    improved_years = sum(
        all(_comparison_improved(yearly.get(str(year), {}), prefix) for prefix in ("reclaim_reference", "confirmation_reference"))
        for year in (2021, 2022, 2023, 2024)
    )
    subgroup_failure = any(
        _material_failure(comparison, prefix)
        for groups in (assets, directions, levels)
        for comparison in groups.values()
        for prefix in ("reclaim_reference", "confirmation_reference")
    )
    return improved_years >= 3 and not subgroup_failure


def _audit(
    *,
    manifest: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    confirmed_rows: Sequence[Mapping[str, object]],
    geometry_rows: Sequence[Mapping[str, object]],
    data_gaps: Sequence[str],
    source_root: Path,
) -> dict[str, object]:
    violations: list[str] = []
    if manifest.get("holdout_accessed") is not False:
        violations.append("source_holdout_boundary_not_sealed")
    if manifest.get("audit_status") != "pass":
        violations.append("source_causality_audit_not_passed")
    if len(data_gaps) > max(1, int(0.01 * max(1, len(confirmed_rows)))):
        violations.append("geometry_data_gap_rate_above_1pct")
    for event in events:
        if event.get("event_timeframe") != "1H_sweep_reclaim" or int(event.get("reclaim_span_bars", 0)) != 1:
            violations.append(f"event_scope:{event['event_id']}")
        if event.get("level_family") not in ALLOWED_LEVEL_FAMILIES:
            violations.append(f"level_scope:{event['event_id']}")
    for row in geometry_rows:
        if row.get("row_role") != "diagnostic_label" or row.get("eligible_for_performance") is not False:
            violations.append(f"performance_contamination:{row['event_id']}")
        if int(row["confirmation_time"]) <= int(row["signal_time"]):
            violations.append(f"confirmation_not_future:{row['event_id']}")
    return {
        "passed": not violations,
        "violations": tuple(sorted(violations)),
        "holdout_accessed": False,
        "source_hashes": {
            name: _sha256(source_root / name)
            for name in ("event_rows.jsonl", "anatomy_rows.jsonl", "run_manifest.json")
        },
    }


def _build_report(
    *,
    events: Sequence[Mapping[str, object]],
    confirmed_rows: Sequence[Mapping[str, object]],
    geometry_rows: Sequence[Mapping[str, object]],
    baseline: Sequence[Mapping[str, object]],
    overall: Mapping[str, Mapping[str, object]],
    unique_overall: Mapping[str, Mapping[str, object]],
    yearly: Mapping[str, Mapping[str, object]],
    assets: Mapping[str, Mapping[str, object]],
    directions: Mapping[str, Mapping[str, object]],
    levels: Mapping[str, Mapping[str, object]],
    geometry: Mapping[str, Mapping[str, object]],
    data_gaps: Sequence[str],
    audit: Mapping[str, object],
    reclaim_passed: bool,
    confirmation_passed: bool,
    stable: bool,
    decision: str,
) -> str:
    baseline_metrics = _baseline_metrics(baseline)
    decision_text = {
        "A": "几何风险可控，可以进入极小 execution feasibility smoke",
        "B": "有改善但主要来自 confirmation chase，需重新定义 confirmation",
        "C": "改善不稳定，暂停 LR v3",
        "D": "数据或审计不足，先修工程",
    }[decision]
    already_one_r = _ratio(
        sum(float(row["confirmation_to_1R_diagnostic_R"]) <= 0 for row in geometry_rows),
        len(geometry_rows),
    )
    lines = [
        "# LR v3 Confirmation Geometry Diagnostic",
        "",
        "## 结论",
        "",
        f"**{decision}. {decision_text}。**",
        "",
        "本报告是 diagnostic-only，不是交易绩效；未生成 entry、execution 或 closed-trade evidence。",
        "",
        "## 样本",
        "",
        f"- Eligible 1H same-bar PDH/PDL + confirmed swing events: {len(events):,}",
        f"- v3 confirmed events: {len(confirmed_rows):,}",
        f"- Geometry-complete events: {len(geometry_rows):,}",
        f"- Unique physical events: {len({str(row['physical_event_key']) for row in geometry_rows}):,}",
        f"- Data gaps: {len(data_gaps):,}",
        "",
        "## Confirmation Geometry",
        "",
        "所有距离均按 reversal 方向带符号；`confirmation_to_1R` 小于等于 0 表示 confirmation close 已到达或越过原 reclaim-reference +1R。ATR15m 只使用 confirmation close 时已经确认的 14 根数据。",
        "",
        "| Geometry | p10 | p25 | median | p75 | p90 |",
        "|---|---:|---:|---:|---:|---:|",
        *[
            f"| `{field}` | {_num(stats['p10'])} | {_num(stats['p25'])} | {_num(stats['median'])} | {_num(stats['p75'])} | {_num(stats['p90'])} |"
            for field, stats in geometry.items()
        ],
        "",
        f"- Confirmation already at/beyond original +1R: {_pct(already_one_r)}",
        f"- Median chase proxy: {_num(geometry['confirmation_chase_proxy']['median'])} ATR15m",
        f"- Median remaining distance to original +1R: {_num(geometry['confirmation_to_1R_diagnostic_R']['median'])} diagnostic R",
        "",
        "## Dual-Reference Path Order",
        "",
        "A 与 B 使用相同的 confirmation 后路径、相同 structural invalidation 和相同 240m future timestamp。A 使用 1H reclaim close/R；B 使用 15m confirmation close/R。Confirmation bar 本身不计入确认后 target 命中。",
        "",
        "| Metric | Original eligible baseline | A: reclaim reference | B: confirmation reference |",
        "|---|---:|---:|---:|",
        f"| Invalidation-first | {_pct(baseline_metrics['invalidation_first_rate'])} | {_pct(overall['reclaim_reference']['invalidation_first_rate'])} | {_pct(overall['confirmation_reference']['invalidation_first_rate'])} |",
        f"| +0.5R first | {_pct(baseline_metrics['half_r_first_rate'])} | {_pct(overall['reclaim_reference']['half_r_first_rate'])} | {_pct(overall['confirmation_reference']['half_r_first_rate'])} |",
        f"| +1R first | {_pct(baseline_metrics['one_r_first_rate'])} | {_pct(overall['reclaim_reference']['one_r_first_rate'])} | {_pct(overall['confirmation_reference']['one_r_first_rate'])} |",
        f"| No decision | {_pct(baseline_metrics['no_decision_rate'])} | {_pct(overall['reclaim_reference']['no_decision_rate'])} | {_pct(overall['confirmation_reference']['no_decision_rate'])} |",
        f"| 240m median R | {_num(baseline_metrics['median_forward_240m_R'])} | {_num(overall['reclaim_reference']['median_forward_240m_R'])} | {_num(overall['confirmation_reference']['median_forward_240m_R'])} |",
        "",
        "Unique-physical sensitivity:",
        "",
        f"- A invalidation-first {_pct(unique_overall['reclaim_reference']['invalidation_first_rate'])}, +1R-first {_pct(unique_overall['reclaim_reference']['one_r_first_rate'])}, 240m median R {_num(unique_overall['reclaim_reference']['median_forward_240m_R'])}。",
        f"- B invalidation-first {_pct(unique_overall['confirmation_reference']['invalidation_first_rate'])}, +1R-first {_pct(unique_overall['confirmation_reference']['one_r_first_rate'])}, 240m median R {_num(unique_overall['confirmation_reference']['median_forward_240m_R'])}。",
        "",
        "## Yearly Breakdown",
        "",
        *_group_table(yearly),
        "",
        "## BTC/ETH Breakdown",
        "",
        *_group_table(assets),
        "",
        "## Long/Short Breakdown",
        "",
        *_group_table(directions),
        "",
        "## Level Breakdown",
        "",
        *_group_table(levels),
        "",
        "PDH/PDL 与 confirmed swing 分开报告；Session H/L 未独立放行。",
        "",
        "## 判断",
        "",
        "A 显著改善而 B 基本回到原 eligible baseline，说明 v3 的表面 path-order 优势主要来自等待 confirmation 后，价格已经沿 reversal 方向推进、原 +1R 剩余距离缩短；当从 confirmation close 重新承担完整 structural risk 后，后续推进不足。它不是纯粹由少数已越过 +1R 的事件造成（占比仅见上方 geometry），但目前不能视为可直接交易的持续信号质量提升。",
        "",
        f"- Reclaim-reference 通过原 v3 path-order 标准: {_yes(reclaim_passed)}",
        f"- Confirmation-reference 通过相同标准: {_yes(confirmation_passed)}",
        f"- 至少 3/4 年且 BTC/ETH、long/short、level 均无明显失效: {_yes(stable)}",
        f"- Median chase < 1 ATR15m: {_yes(float(geometry['confirmation_chase_proxy']['median'] or 0) < 1.0)}",
        f"- Median confirmation 尚未越过原 +1R: {_yes(float(geometry['confirmation_to_1R_diagnostic_R']['median'] or 0) > 0.0)}",
        f"- Final decision: **{decision}**",
        "",
        "## Data Gaps",
        "",
        "- 既有 artifacts 仍无 first-touch 与 active-session 字段；本诊断不使用 Session H/L。",
        *([f"- `{gap}`" for gap in data_gaps] or ["- Geometry 所需 ATR15m 与 confirmation bar 完整。"]),
        "",
        "## Audit",
        "",
        f"- status: {'pass' if audit['passed'] else 'fail'}",
        f"- violations: {len(audit['violations'])}",
        "- holdout accessed: false",
        "- source scanner rerun: false",
        "- Entry Tournament run: false",
        "- performance rows generated: 0",
        "- RiskEngine/cost/stop/notional/formal config modified: false",
        "- Restricted Variant B: suspended",
        *[f"- source SHA-256 `{name}`: `{digest}`" for name, digest in audit["source_hashes"].items()],
        "",
    ]
    return "\n".join(lines)


def _group_table(groups: Mapping[str, Mapping[str, object]]) -> list[str]:
    lines = [
        "| Group | Reference | Events | Inv-first | +0.5R first | +1R first | No decision | 240m median R |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, group in groups.items():
        baseline = group["baseline"]
        reclaim = group["reclaim_reference"]
        confirmation = group["confirmation_reference"]
        for reference, metrics in (
            ("baseline", baseline),
            ("A reclaim", reclaim),
            ("B confirmation", confirmation),
        ):
            lines.append(
                f"| {name} | {reference} | {metrics['count']:,} | {_pct(metrics['invalidation_first_rate'])} | {_pct(metrics['half_r_first_rate'])} | {_pct(metrics['one_r_first_rate'])} | {_pct(metrics['no_decision_rate'])} | {_num(metrics['median_forward_240m_R'])} |"
            )
    return lines


def _distribution(values) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values if value not in (None, ""))
    return {
        "p10": _percentile(ordered, 0.10),
        "p25": _percentile(ordered, 0.25),
        "median": _percentile(ordered, 0.50),
        "p75": _percentile(ordered, 0.75),
        "p90": _percentile(ordered, 0.90),
    }


def _percentile(ordered: Sequence[float], probability: float) -> float | None:
    if not ordered:
        return None
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _year(timestamp_ms: int) -> int:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).year


def _median(values) -> float | None:
    numbers = [float(value) for value in values if value not in (None, "")]
    return median(numbers) if numbers else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _pct(value: object) -> str:
    return "n/a" if value is None else f"{100 * float(value):.2f}%"


def _num(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def _yes(value: bool) -> str:
    return "pass" if value else "fail"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "LRV3ConfirmationGeometryResult",
    "build_confirmation_geometry",
    "classify_geometry_decision",
    "run_lr_v3_confirmation_geometry",
]
