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


BAR_15M_MS = 15 * 60_000
MAX_CONFIRMATION_BARS = 4
MAX_DIAGNOSTIC_MINUTES = 1200
ALLOWED_LEVEL_FAMILIES = {"previous_day_high_low", "confirmed_swing"}
VPA_FEATURES = (
    "sweep_relative_volume",
    "reclaim_relative_volume",
    "sweep_range_expansion",
    "reclaim_range_expansion",
    "wick_ratio",
    "close_location_value",
    "combined_volume_ratio",
)


@dataclass(frozen=True)
class LREntrySignalV3SmokeResult:
    event_count: int
    confirmation_count: int
    failed_before_confirmation_count: int
    no_confirmation_count: int
    unique_confirmed_physical_event_count: int
    decision: str
    audit_passed: bool
    report_path: str


def run_lr_entry_signal_v3_smoke(
    *,
    repository,
    source_root: Path,
    report_path: Path,
) -> LREntrySignalV3SmokeResult:
    manifest = json.loads((source_root / "run_manifest.json").read_text(encoding="utf-8"))
    events = tuple(
        row
        for row in _load_jsonl(source_root / "event_rows.jsonl")
        if row.get("event_timeframe") == "1H_sweep_reclaim"
        and int(row.get("reclaim_span_bars", 0)) == 1
        and row.get("level_family") in ALLOWED_LEVEL_FAMILIES
    )
    features = {str(row["event_id"]): row for row in _load_jsonl(source_root / "vpa_feature_rows.jsonl")}
    anatomy = {str(row["event_id"]): row for row in _load_jsonl(source_root / "anatomy_rows.jsonl")}
    candles_by_instrument = _load_candles(repository, events)
    candle_times = {
        instrument: tuple(int(getattr(candle, "timestamp_ms")) for candle in candles)
        for instrument, candles in candles_by_instrument.items()
    }

    evaluated: list[dict[str, object]] = []
    for event in events:
        instrument = str(event["instrument"])
        row = evaluate_structural_confirmation(
            event,
            _event_candle_window(
                event,
                candles_by_instrument[instrument],
                candle_times[instrument],
            ),
        )
        source_anatomy = anatomy[str(event["event_id"])]
        evaluated.append(
            {
                **row,
                "year": _year(int(event["signal_time"])),
                "source_forward_240m_R": source_anatomy.get("forward_240m_R"),
                "vpa": features.get(str(event["event_id"]), {}),
            }
        )

    confirmed = tuple(row for row in evaluated if row["confirmation_status"] == "confirmed")
    unique_confirmed = tuple(
        {str(row["physical_event_key"]): row for row in confirmed}.values()
    )
    baseline = _baseline_rows(events, anatomy)
    overall = _metrics(confirmed)
    unique_overall = _metrics(unique_confirmed)
    yearly = _group_comparison(evaluated, baseline, lambda row: str(row["year"]))
    assets = _group_comparison(evaluated, baseline, lambda row: str(row["instrument"]))
    directions = _group_comparison(evaluated, baseline, lambda row: str(row["direction"]))
    levels = _group_comparison(evaluated, baseline, lambda row: str(row["level_family"]))
    yearly_counts = {
        year: len({str(row["physical_event_key"]) for row in confirmed if int(row["year"]) == year})
        for year in (2021, 2022, 2023, 2024)
    }
    yearly_improvements = {
        year: _improved(yearly.get(str(year), {})) for year in yearly_counts
    }
    subgroup_failures = tuple(
        f"{kind}:{name}"
        for kind, groups in (("asset", assets), ("direction", directions))
        for name, comparison in groups.items()
        if _material_subgroup_failure(comparison)
    )
    audit = _audit(
        manifest=manifest,
        events=events,
        evaluated=evaluated,
        features=features,
        source_root=source_root,
    )
    decision = classify_v3_decision(
        invalidation_first_rate=max(
            float(overall["invalidation_first_rate"] or 0.0),
            float(unique_overall["invalidation_first_rate"] or 0.0),
        ),
        one_r_first_rate=min(
            float(overall["one_r_first_rate"] or 0.0),
            float(unique_overall["one_r_first_rate"] or 0.0),
        ),
        event_count=len({str(row["physical_event_key"]) for row in confirmed}),
        yearly_counts=yearly_counts,
        yearly_improvements=yearly_improvements,
        subgroup_failures=subgroup_failures,
        audit_passed=bool(audit["passed"]),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _build_report(
            events=events,
            evaluated=evaluated,
            confirmed=confirmed,
            baseline=baseline,
            overall=overall,
            unique_overall=unique_overall,
            yearly=yearly,
            assets=assets,
            directions=directions,
            levels=levels,
            yearly_counts=yearly_counts,
            yearly_improvements=yearly_improvements,
            subgroup_failures=subgroup_failures,
            audit=audit,
            decision=decision,
        ),
        encoding="utf-8",
    )
    return LREntrySignalV3SmokeResult(
        event_count=len(events),
        confirmation_count=len(confirmed),
        failed_before_confirmation_count=sum(
            row["confirmation_status"] == "failed_before_confirmation" for row in evaluated
        ),
        no_confirmation_count=sum(row["confirmation_status"] == "no_confirmation" for row in evaluated),
        unique_confirmed_physical_event_count=len(
            {str(row["physical_event_key"]) for row in confirmed}
        ),
        decision=decision,
        audit_passed=bool(audit["passed"]),
        report_path=str(report_path),
    )


def evaluate_structural_confirmation(
    event: Mapping[str, object],
    candles: Sequence[object],
) -> dict[str, object]:
    signal_time = int(event["signal_time"])
    direction = str(event["direction"])
    signal_close = float(event["signal_close"])
    event_atr = float(event["event_atr"])
    sweep_extreme = float(event["sweep_extreme"])
    invalidation = (
        sweep_extreme - 0.10 * event_atr
        if direction == "long"
        else sweep_extreme + 0.10 * event_atr
    )
    risk = abs(signal_close - invalidation)
    if risk <= 0:
        raise ValueError("v3 smoke requires positive structural diagnostic R")

    confirmed = tuple(
        candle
        for candle in candles
        if bool(getattr(candle, "is_confirmed", False))
    )
    by_open = {int(getattr(candle, "timestamp_ms")): candle for candle in confirmed}
    previous = by_open.get(signal_time - BAR_15M_MS)
    post_signal = tuple(
        candle
        for candle in confirmed
        if signal_time <= int(getattr(candle, "timestamp_ms"))
        and _close_time(candle) <= signal_time + MAX_DIAGNOSTIC_MINUTES * 60_000
    )
    observation_rows: list[object] = []
    for index in range(MAX_CONFIRMATION_BARS):
        candle = by_open.get(signal_time + index * BAR_15M_MS)
        if candle is None:
            break
        observation_rows.append(candle)
    observation = tuple(observation_rows)
    gaps: list[str] = []
    if previous is None:
        gaps.append("missing_previous_confirmed_bar")
    if len(observation) < MAX_CONFIRMATION_BARS:
        gaps.append("missing_confirmed_post_signal_bars")

    base = {
        "row_type": "v3_smoke_diagnostic",
        "row_role": "diagnostic_label",
        "event_id": event["event_id"],
        "physical_event_key": event["physical_event_key"],
        "instrument": event["instrument"],
        "level_family": event["level_family"],
        "direction": direction,
        "signal_time": signal_time,
        "signal_close": signal_close,
        "invalidation_price": invalidation,
        "diagnostic_r_size": risk,
        "confirmation_time": None,
        "time_to_confirmation_minutes": None,
        "time_to_0_5R_minutes": None,
        "time_to_1R_minutes": None,
        "invalidation_time_minutes": None,
        "invalidation_first_status": "unresolved",
        "half_r_first_status": "unresolved",
        "data_gaps": tuple(gaps),
        "eligible_for_performance": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }
    prior = previous
    for candle in observation:
        minutes = int((_close_time(candle) - signal_time) / 60_000)
        if _invalidated(direction, candle, invalidation):
            return {
                **base,
                "confirmation_status": "failed_before_confirmation",
                "invalidation_time_minutes": minutes,
                "invalidation_first_status": "invalidation_first",
                "half_r_first_status": "invalidation_first",
            }
        if prior is not None and _structurally_confirms(direction, candle, prior):
            outcomes = _ordered_outcomes(
                direction=direction,
                signal_time=signal_time,
                signal_close=signal_close,
                invalidation=invalidation,
                risk=risk,
                path=post_signal[post_signal.index(candle) + 1 :],
            )
            return {
                **base,
                **outcomes,
                "confirmation_status": "confirmed",
                "confirmation_time": _close_time(candle),
                "time_to_confirmation_minutes": minutes,
            }
        prior = candle
    return {**base, "confirmation_status": "no_confirmation"}


def classify_v3_decision(
    *,
    invalidation_first_rate: float,
    one_r_first_rate: float,
    event_count: int,
    yearly_counts: Mapping[int, int],
    yearly_improvements: Mapping[int, bool],
    subgroup_failures: Sequence[str],
    audit_passed: bool,
) -> str:
    if not audit_passed:
        return "D"
    sample_passed = event_count >= 300 and all(
        yearly_counts.get(year, 0) >= 50 for year in (2021, 2022, 2023, 2024)
    )
    stable = sum(bool(yearly_improvements.get(year)) for year in (2021, 2022, 2023, 2024)) >= 3
    threshold_passed = invalidation_first_rate <= 0.45 and one_r_first_rate >= 0.52
    if sample_passed and stable and not subgroup_failures and threshold_passed:
        return "A"
    improved = invalidation_first_rate <= 0.48 or one_r_first_rate >= 0.50
    return "B" if improved else "C"


def _ordered_outcomes(
    *,
    direction: str,
    signal_time: int,
    signal_close: float,
    invalidation: float,
    risk: float,
    path: Sequence[object],
) -> dict[str, object]:
    half_time: int | None = None
    one_time: int | None = None
    invalidation_time: int | None = None
    for candle in path:
        minutes = int((_close_time(candle) - signal_time) / 60_000)
        if _invalidated(direction, candle, invalidation):
            invalidation_time = minutes
            break
        favorable = float(getattr(candle, "high" if direction == "long" else "low"))
        if half_time is None and _target_reached(direction, favorable, signal_close, 0.5 * risk):
            half_time = minutes
        if one_time is None and _target_reached(direction, favorable, signal_close, risk):
            one_time = minutes
    return {
        "time_to_0_5R_minutes": half_time,
        "time_to_1R_minutes": one_time,
        "invalidation_time_minutes": invalidation_time,
        "half_r_first_status": (
            "half_r_first"
            if half_time is not None
            else "invalidation_first"
            if invalidation_time is not None
            else "unresolved"
        ),
        "invalidation_first_status": (
            "one_r_first"
            if one_time is not None
            else "invalidation_first"
            if invalidation_time is not None
            else "unresolved"
        ),
    }


def _structurally_confirms(direction: str, candle: object, previous: object) -> bool:
    high = float(getattr(candle, "high"))
    low = float(getattr(candle, "low"))
    close = float(getattr(candle, "close"))
    if high <= low:
        return False
    midpoint = low + 0.5 * (high - low)
    if direction == "long":
        return close > float(getattr(previous, "high")) and close >= midpoint
    return close < float(getattr(previous, "low")) and close <= midpoint


def _invalidated(direction: str, candle: object, invalidation: float) -> bool:
    if direction == "long":
        return float(getattr(candle, "low")) <= invalidation
    return float(getattr(candle, "high")) >= invalidation


def _target_reached(
    direction: str,
    favorable_extreme: float,
    signal_close: float,
    distance: float,
) -> bool:
    target = signal_close + distance if direction == "long" else signal_close - distance
    return favorable_extreme >= target if direction == "long" else favorable_extreme <= target


def _close_time(candle: object) -> int:
    return int(getattr(candle, "timestamp_ms")) + BAR_15M_MS


def _load_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    with path.open("r", encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


def _load_candles(repository, events: Sequence[Mapping[str, object]]) -> dict[str, tuple[object, ...]]:
    output: dict[str, tuple[object, ...]] = {}
    for instrument in sorted({str(row["instrument"]) for row in events}):
        group = [row for row in events if row["instrument"] == instrument]
        start = min(int(row["signal_time"]) for row in group) - BAR_15M_MS
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


def _event_candle_window(
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
            "event_id": event["event_id"],
            "physical_event_key": event["physical_event_key"],
            "instrument": event["instrument"],
            "direction": event["direction"],
            "level_family": event["level_family"],
            "year": _year(int(event["signal_time"])),
            **anatomy[str(event["event_id"])],
        }
        for event in events
    )


def _metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    resolved = [row for row in rows if row.get("invalidation_first_status") != "unresolved"]
    return {
        "count": len(rows),
        "unique_physical_count": len({str(row["physical_event_key"]) for row in rows}),
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
        "median_time_to_confirmation": _median(
            row.get("time_to_confirmation_minutes") for row in rows
        ),
        "median_time_to_half_r": _median(row.get("time_to_0_5R_minutes") for row in rows),
        "median_time_to_invalidation": _median(
            row.get("invalidation_time_minutes") for row in rows
        ),
        "median_source_forward_240m_R": _median(
            row.get("source_forward_240m_R") for row in rows
        ),
    }


def _baseline_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    resolved = [row for row in rows if row.get("invalidation_first_status") != "unresolved"]
    return {
        "count": len(rows),
        "invalidation_first_rate": _ratio(
            sum(row.get("invalidation_first_status") == "invalidation_first" for row in resolved),
            len(resolved),
        ),
        "one_r_first_rate": _ratio(
            sum(row.get("time_to_1R_minutes") is not None for row in rows), len(rows)
        ),
        "median_forward_240m_R": _median(row.get("forward_240m_R") for row in rows),
    }


def _group_comparison(
    evaluated: Sequence[Mapping[str, object]],
    baseline: Sequence[Mapping[str, object]],
    key,
) -> dict[str, dict[str, object]]:
    v3_groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    baseline_groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in evaluated:
        if row.get("confirmation_status") == "confirmed":
            v3_groups[key(row)].append(row)
    for row in baseline:
        baseline_groups[key(row)].append(row)
    return {
        name: {
            "v3": _metrics(v3_groups.get(name, ())),
            "baseline": _baseline_metrics(baseline_groups.get(name, ())),
        }
        for name in sorted(set(v3_groups) | set(baseline_groups))
    }


def _improved(comparison: Mapping[str, object]) -> bool:
    if not comparison:
        return False
    v3 = comparison["v3"]
    baseline = comparison["baseline"]
    left = v3.get("invalidation_first_rate")
    right = baseline.get("invalidation_first_rate")
    return left is not None and right is not None and float(left) < float(right)


def _material_subgroup_failure(comparison: Mapping[str, object]) -> bool:
    v3 = comparison["v3"]
    baseline = comparison["baseline"]
    if int(v3.get("unique_physical_count", 0)) < 50:
        return True
    v3_inv = v3.get("invalidation_first_rate")
    base_inv = baseline.get("invalidation_first_rate")
    v3_one = v3.get("one_r_first_rate")
    base_one = baseline.get("one_r_first_rate")
    return bool(
        v3_inv is None
        or base_inv is None
        or v3_one is None
        or base_one is None
        or float(v3_inv) > float(base_inv) + 0.02
        or float(v3_one) < float(base_one) - 0.02
    )


def _audit(
    *,
    manifest: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    evaluated: Sequence[Mapping[str, object]],
    features: Mapping[str, Mapping[str, object]],
    source_root: Path,
) -> dict[str, object]:
    violations: list[str] = []
    if manifest.get("holdout_accessed") is not False:
        violations.append("source_holdout_boundary_not_sealed")
    if manifest.get("audit_status") != "pass":
        violations.append("source_causality_audit_not_passed")
    for event in events:
        event_id = str(event["event_id"])
        if event.get("event_timeframe") != "1H_sweep_reclaim" or int(event.get("reclaim_span_bars", 0)) != 1:
            violations.append(f"invalid_event_scope:{event_id}")
        if event.get("level_family") not in ALLOWED_LEVEL_FAMILIES:
            violations.append(f"invalid_level_family:{event_id}")
        if int(event.get("feature_cutoff_time", -1)) > int(event["signal_time"]):
            violations.append(f"event_lookahead:{event_id}")
        feature = features.get(event_id)
        if feature is None or int(feature.get("max_source_time", -1)) > int(event["signal_time"]):
            violations.append(f"vpa_lookahead_or_missing:{event_id}")
    for row in evaluated:
        if row.get("eligible_for_performance") is not False or row.get("row_role") != "diagnostic_label":
            violations.append(f"performance_contamination:{row['event_id']}")
        confirmation = row.get("confirmation_time")
        if confirmation is not None and not (
            int(row["signal_time"]) < int(confirmation) <= int(row["signal_time"]) + 60 * 60_000
        ):
            violations.append(f"confirmation_time_violation:{row['event_id']}")
    return {
        "passed": not violations,
        "violations": tuple(sorted(violations)),
        "holdout_accessed": False,
        "source_hashes": {
            name: _sha256(source_root / name)
            for name in (
                "event_rows.jsonl",
                "vpa_feature_rows.jsonl",
                "anatomy_rows.jsonl",
                "run_manifest.json",
            )
        },
    }


def _build_report(
    *,
    events: Sequence[Mapping[str, object]],
    evaluated: Sequence[Mapping[str, object]],
    confirmed: Sequence[Mapping[str, object]],
    baseline: Sequence[Mapping[str, object]],
    overall: Mapping[str, object],
    unique_overall: Mapping[str, object],
    yearly: Mapping[str, Mapping[str, object]],
    assets: Mapping[str, Mapping[str, object]],
    directions: Mapping[str, Mapping[str, object]],
    levels: Mapping[str, Mapping[str, object]],
    yearly_counts: Mapping[int, int],
    yearly_improvements: Mapping[int, bool],
    subgroup_failures: Sequence[str],
    audit: Mapping[str, object],
    decision: str,
) -> str:
    failed = sum(row["confirmation_status"] == "failed_before_confirmation" for row in evaluated)
    no_confirmation = sum(row["confirmation_status"] == "no_confirmation" for row in evaluated)
    baseline_overall = _baseline_metrics(baseline)
    gaps = defaultdict(int)
    for row in evaluated:
        for gap in row.get("data_gaps", ()):
            gaps[str(gap)] += 1
    vpa_rows = _vpa_attribution(confirmed)
    decision_text = {
        "A": "明显改善：可以进入一个很小的真实 execution feasibility smoke。",
        "B": "有改善但不稳定：继续只读诊断，不扩展网格。",
        "C": "无明显改善：暂停 LR causal rebuild。",
        "D": "审计或数据缺口导致无法判断：先修工程。",
    }[decision]
    lines = [
        "# LR Entry Signal v3 Smoke Report",
        "",
        "## 结论",
        "",
        f"**Decision {decision}：{decision_text}**",
        "",
        "本报告是 diagnostic-only 机制验证，不是交易绩效；未生成 entry、execution 或 closed-trade evidence。",
        "",
        "## 样本漏斗",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Eligible 1H same-bar events | {len(events):,} |",
        f"| Structural confirmations | {len(confirmed):,} |",
        f"| Unique confirmed physical events | {len({str(row['physical_event_key']) for row in confirmed}):,} |",
        f"| Failed before confirmation | {failed:,} |",
        f"| No confirmation within 4 bars | {no_confirmation:,} |",
        "",
        "## 主结果",
        "",
        "| Metric | Supplied baseline | Matched eligible baseline | v3 confirmed | Pass threshold |",
        "|---|---:|---:|---:|---:|",
        f"| Invalidation-first | 50.02% | {_pct(baseline_overall['invalidation_first_rate'])} | {_pct(overall['invalidation_first_rate'])} | <=45% |",
        f"| +1R first | 48.00% | {_pct(baseline_overall['one_r_first_rate'])} | {_pct(overall['one_r_first_rate'])} | >=52% |",
        f"| 240m median structural R | 0.142 | {_num(baseline_overall['median_forward_240m_R'])} | {_num(overall['median_source_forward_240m_R'])} | diagnostic |",
        f"| +0.5R first | - | - | {_pct(overall['half_r_first_rate'])} | diagnostic |",
        f"| No decision | - | - | {_pct(overall['no_decision_rate'])} | diagnostic |",
        "",
        f"Median time-to-confirmation: {_minutes(overall['median_time_to_confirmation'])}; median time-to-0.5R: {_minutes(overall['median_time_to_half_r'])}; median time-to-invalidation: {_minutes(overall['median_time_to_invalidation'])}。",
        "Path outcomes 从确认后的下一根 15m bar 开始；confirmation bar 不同时计为确认后的目标命中。Invalidation-first 分母为 +1R/invalidation 已决样本，其余 first/no-decision 指标分母为全部 confirmed events。",
        f"Unique-physical sensitivity：invalidation-first {_pct(unique_overall['invalidation_first_rate'])}，+1R-first {_pct(unique_overall['one_r_first_rate'])}，+0.5R-first {_pct(unique_overall['half_r_first_rate'])}，no-decision {_pct(unique_overall['no_decision_rate'])}；最终 gate 使用 event-level 与 unique-physical 两者中更保守的数值。",
        "",
        "## Yearly Breakdown",
        "",
        *_comparison_table(yearly),
        "",
        f"改善年份：{sum(yearly_improvements.values())}/4；各年 unique confirmed physical events：" + ", ".join(f"{year}={yearly_counts[year]}" for year in yearly_counts) + "。",
        "",
        "## BTC/ETH Breakdown",
        "",
        *_comparison_table(assets),
        "",
        "## Long/Short Breakdown",
        "",
        *_comparison_table(directions),
        "",
        f"Material subgroup failures: {', '.join(subgroup_failures) if subgroup_failures else 'none'}。定义为 unique confirmed <50、invalidation-first 比 matched baseline 恶化 >2pp，或 +1R-first 恶化 >2pp。",
        "",
        "## Level Breakdown",
        "",
        *_comparison_table(levels),
        "",
        "PDH/PDL 与 confirmed swing 分开报告；Session H/L 未独立放行。",
        "",
        "## VPA Attribution",
        "",
        "Fixed bins 只作 attribution，不过滤、不打分、不调阈值。",
        "",
        "| Feature | Bucket | Confirmed | Inv-first | +1R first | No decision |",
        "|---|---|---:|---:|---:|---:|",
        *[
            f"| `{row['feature']}` | `{row['bucket']}` | {row['count']:,} | {_pct(row['invalidation_first_rate'])} | {_pct(row['one_r_first_rate'])} | {_pct(row['no_decision_rate'])} |"
            for row in vpa_rows
        ],
        "",
        "## Data Gaps",
        "",
        "- 既有 artifacts 没有 first-touch 与 active-session 字段；Session H/L 只能作为未使用的背景缺口记录。",
        "- v3 不生成 Session H/L confluence 结论，避免用缺失字段做事后代理。",
        *([f"- `{name}`: {count:,} events。" for name, count in sorted(gaps.items())] or ["- 15m confirmation window 无缺失。"]),
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
        "## Gate Decision",
        "",
        f"- Event-level and unique-physical invalidation-first <=45%: {_yes(max(float(overall['invalidation_first_rate'] or 1), float(unique_overall['invalidation_first_rate'] or 1)) <= 0.45)}",
        f"- Event-level and unique-physical +1R-first >=52%: {_yes(min(float(overall['one_r_first_rate'] or 0), float(unique_overall['one_r_first_rate'] or 0)) >= 0.52)}",
        f"- At least 3/4 years improved: {_yes(sum(yearly_improvements.values()) >= 3)}",
        f"- BTC/ETH and long/short no material unilateral failure: {_yes(not subgroup_failures)}",
        f"- Unique confirmed events >=300 and every year >=50: {_yes(len({str(row['physical_event_key']) for row in confirmed}) >= 300 and all(count >= 50 for count in yearly_counts.values()))}",
        f"- Final decision: **{decision}**",
        "",
    ]
    return "\n".join(lines)


def _comparison_table(groups: Mapping[str, Mapping[str, object]]) -> list[str]:
    lines = [
        "| Group | Baseline events | Confirmed unique | Baseline inv-first | v3 inv-first | Baseline +1R | v3 +1R | Improved |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, comparison in groups.items():
        base = comparison["baseline"]
        v3 = comparison["v3"]
        lines.append(
            f"| {name} | {base['count']:,} | {v3['unique_physical_count']:,} | {_pct(base['invalidation_first_rate'])} | {_pct(v3['invalidation_first_rate'])} | {_pct(base['one_r_first_rate'])} | {_pct(v3['one_r_first_rate'])} | {'yes' if _improved(comparison) else 'no'} |"
        )
    return lines


def _vpa_attribution(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        feature_row = row.get("vpa", {})
        for feature in VPA_FEATURES:
            bucket = _fixed_vpa_bucket(feature, feature_row.get(feature))
            if bucket is not None:
                groups[(feature, bucket)].append(row)
    return [
        {"feature": feature, "bucket": bucket, **_metrics(group)}
        for (feature, bucket), group in sorted(groups.items())
    ]


def _fixed_vpa_bucket(feature: str, value: object) -> str | None:
    if value in (None, ""):
        return None
    number = float(value)
    if feature in {"wick_ratio", "close_location_value"}:
        if number < 0.25:
            return "q1"
        if number < 0.50:
            return "q2"
        if number < 0.75:
            return "q3"
        return "q4"
    if number < 0.8:
        return "low_lt_0.8"
    if number < 1.2:
        return "normal_0.8_1.2"
    if number < 1.5:
        return "elevated_1.2_1.5"
    return "high_ge_1.5"


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


def _minutes(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.0f}m"


def _yes(value: bool) -> str:
    return "pass" if value else "fail"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "LREntrySignalV3SmokeResult",
    "classify_v3_decision",
    "evaluate_structural_confirmation",
    "run_lr_entry_signal_v3_smoke",
]
