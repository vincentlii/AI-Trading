from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.lr_causal_rebuild import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    atr_from_index,
    build_causal_atr_index,
    level_validity_windows,
    validate_development_window,
)
from research_pipeline.runners.register_research_run import register_research_run
from trading_system.strategies.trend_price_volume_v1.lr_causal_entry import (
    build_all_previous_day_levels,
    build_confirmed_swing_levels,
    build_session_levels,
)
from trading_system.strategies.trend_price_volume_v1.lr_event_anatomy import (
    HORIZONS_MINUTES,
    build_event_anatomy,
)
from trading_system.strategies.trend_price_volume_v1.lr_multitimeframe_event import (
    EVENT_POLICIES,
    LRMultiTimeframeEvent,
    detect_multitimeframe_events,
)
from trading_system.strategies.trend_price_volume_v1.lr_vpa_attribution import (
    build_post_signal_volume_label,
    build_vpa_feature_row,
)


MAX_LABEL_MINUTES = 1200
SCHEMA_VERSION = "lr_multitimeframe_event_research.v1"


@dataclass(frozen=True)
class LRMultiTimeframeResearchResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    dataset_start: str
    dataset_end: str
    event_count: int
    unique_physical_event_count: int
    vpa_feature_count: int
    anatomy_count: int
    audit_status: str
    run_root: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_multitimeframe_event_research(
    *,
    repository,
    preset,
    output_root: Path,
    start_date: str = DEVELOPMENT_START,
    end_date: str = DEVELOPMENT_END,
) -> LRMultiTimeframeResearchResult:
    validate_development_window(start_date, end_date)
    start_ms, end_ms = _date_bounds(start_date, end_date)
    end_exclusive = end_ms + 1
    event_cutoff = end_exclusive - MAX_LABEL_MINUTES * 60_000
    context_start = start_ms - 45 * 24 * 60 * 60_000
    event_objects: list[LRMultiTimeframeEvent] = []
    level_rows: list[dict[str, object]] = []
    candle_cache: dict[tuple[str, str], tuple[object, ...]] = {}

    for target in preset.to_scan_config().targets:
        load_kwargs = {"venue": target.venue, "inst_type": target.inst_type, "confirmed_only": True}
        bars = {
            name: tuple(repository.load_range(target.inst_id, name, context_start, end_ms, **load_kwargs))
            for name in ("15m", "1H", "4H")
        }
        candle_cache.update({(target.inst_id, name): rows for name, rows in bars.items()})
        levels = tuple(
            sorted(
                (
                    *build_session_levels(bars["15m"], cutoff_time=event_cutoff),
                    *build_all_previous_day_levels(bars["15m"], cutoff_time=event_cutoff),
                    *build_confirmed_swing_levels(bars["4H"], cutoff_time=event_cutoff),
                ),
                key=lambda row: (row.confirmed_time, row.family, row.direction, row.level_id),
            )
        )
        level_rows.extend({**level.as_dict(), "instrument": target.inst_id} for level in levels)
        event_objects.extend(
            _scan_target_events(
                instrument=target.inst_id,
                levels=levels,
                candles_by_bar=bars,
                start_ms=start_ms,
                event_cutoff=event_cutoff,
            )
        )

    event_objects.sort(key=_event_sort_key)
    event_rows = [_event_row(event) for event in event_objects]
    feature_rows: list[dict[str, object]] = []
    volume_label_rows: list[dict[str, object]] = []
    anatomy_rows: list[dict[str, object]] = []
    for event in event_objects:
        event_bar = _policy_bar(event.event_timeframe)
        event_candles = candle_cache[(event.instrument, event_bar)]
        feature_rows.append(build_vpa_feature_row(event, event_candles))
        volume_label_rows.append(build_post_signal_volume_label(event, event_candles))
        anatomy_rows.append(build_event_anatomy(event, candle_cache[(event.instrument, "15m")]))

    summary_rows = build_research_summaries(event_rows, feature_rows, anatomy_rows)
    all_label_rows = [*volume_label_rows, *anatomy_rows]
    audit = audit_multitimeframe_research(
        event_rows,
        feature_rows,
        all_label_rows,
        holdout_accessed=False,
    )
    core_rows = {
        "event_rows.jsonl": event_rows,
        "vpa_feature_rows.jsonl": feature_rows,
        "diagnostic_label_rows.jsonl": volume_label_rows,
        "anatomy_rows.jsonl": anatomy_rows,
        "summary_rows.jsonl": summary_rows,
    }
    audit["deterministic_core_hashes"] = {
        name: deterministic_rows_hash(rows) for name, rows in core_rows.items()
    }
    audit["deterministic_reserialization_match"] = all(
        audit["deterministic_core_hashes"][name] == deterministic_rows_hash(tuple(reversed(rows)))
        for name, rows in core_rows.items()
    )
    if not audit["deterministic_reserialization_match"]:
        audit["status"] = "fail"
        audit["violations"].append("artifact_hash_nondeterministic")
        audit["violation_count"] = len(audit["violations"])

    run_root = Path(output_root) / f"multitimeframe_events_development_{start_date}_{end_date}"
    run_root.mkdir(parents=True, exist_ok=True)
    result = LRMultiTimeframeResearchResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        dataset_start=start_date,
        dataset_end=end_date,
        event_count=len(event_rows),
        unique_physical_event_count=len({row["physical_event_key"] for row in event_rows}),
        vpa_feature_count=len(feature_rows),
        anatomy_count=len(anatomy_rows),
        audit_status=str(audit["status"]),
        run_root=str(run_root),
    )
    _write_outputs(
        run_root=run_root,
        result=result,
        preset=preset,
        level_rows=level_rows,
        core_rows=core_rows,
        audit=audit,
    )
    return result


def _scan_target_events(
    *,
    instrument: str,
    levels: Sequence[object],
    candles_by_bar: Mapping[str, Sequence[object]],
    start_ms: int,
    event_cutoff: int,
) -> list[LRMultiTimeframeEvent]:
    validity = level_validity_windows(levels, end_time=event_cutoff + 1)
    events: list[LRMultiTimeframeEvent] = []
    control_atr_times, control_atr_values = build_causal_atr_index(
        candles_by_bar["4H"],
        timeframe_ms=4 * 60 * 60_000,
    )

    def control_depth_cap_at(timestamp: int) -> float | None:
        return atr_from_index(control_atr_times, control_atr_values, cutoff_time=timestamp)

    for policy in EVENT_POLICIES.values():
        bar = _policy_bar(policy.name)
        candles = candles_by_bar[bar]
        timestamps = [int(getattr(row, "timestamp_ms")) for row in candles]
        atr_times, atr_values = build_causal_atr_index(
            candles,
            timeframe_ms=policy.timeframe_ms,
        )

        def atr_at(timestamp: int) -> float | None:
            return atr_from_index(atr_times, atr_values, cutoff_time=timestamp)

        for level in levels:
            window_start = bisect_left(timestamps, level.confirmed_time)
            window_end = bisect_left(timestamps, validity[level.level_id])
            detected = detect_multitimeframe_events(
                levels=(level,),
                candles=candles[window_start:window_end],
                atr_at=atr_at,
                policy=policy,
                instrument=instrument,
                sweep_depth_cap_at=(
                    control_depth_cap_at if policy.name == "15m_micro" else None
                ),
            )
            events.extend(
                event for event in detected if start_ms <= event.signal_time <= event_cutoff
            )
    return events


def audit_multitimeframe_research(
    event_rows: Sequence[Mapping[str, object]],
    feature_rows: Sequence[Mapping[str, object]],
    label_rows: Sequence[Mapping[str, object]],
    *,
    holdout_accessed: bool,
) -> dict[str, object]:
    violations: list[str] = []
    if holdout_accessed:
        violations.append("holdout_accessed")
    event_ids = {str(row.get("event_id")) for row in event_rows}
    for row in event_rows:
        event_id = str(row.get("event_id"))
        if not bool(row.get("bar_confirmed")):
            violations.append(f"unconfirmed_event:{event_id}")
        if int(row.get("signal_time", -1)) != int(row.get("reclaim_time", -2)):
            violations.append(f"signal_not_reclaim_close:{event_id}")
        if int(row.get("feature_cutoff_time", -1)) > int(row.get("signal_time", -2)):
            violations.append(f"event_feature_cutoff_after_signal:{event_id}")
    for row in feature_rows:
        event_id = str(row.get("event_id"))
        if event_id not in event_ids:
            violations.append(f"orphan_feature:{event_id}")
        if row.get("row_role") != "tradable_feature":
            violations.append(f"feature_role_contamination:{event_id}")
        if int(row.get("max_source_time", -1)) > int(row.get("signal_time", -2)):
            violations.append(f"feature_lookahead:{event_id}")
        if int(row.get("feature_cutoff_time", -1)) > int(row.get("signal_time", -2)):
            violations.append(f"feature_cutoff_after_signal:{event_id}")
    for row in label_rows:
        event_id = str(row.get("event_id"))
        if event_id not in event_ids:
            violations.append(f"orphan_label:{event_id}")
        if row.get("row_role") != "diagnostic_label":
            violations.append(f"label_role_contamination:{event_id}")
        min_source = row.get("min_source_time", row.get("label_min_source_time"))
        if min_source not in (None, "") and int(min_source) <= int(row.get("signal_time", -1)):
            violations.append(f"label_not_strictly_future:{event_id}")
    return {
        "status": "pass" if not violations else "fail",
        "violation_count": len(violations),
        "violations": sorted(violations),
        "event_count": len(event_rows),
        "unique_physical_event_count": len(
            {str(row.get("physical_event_key")) for row in event_rows}
        ),
        "feature_count": len(feature_rows),
        "label_count": len(label_rows),
        "holdout_accessed": holdout_accessed,
        "bar_close_confirmation_semantics": "event signal equals confirmed reclaim bar close",
        "future_data_role": "diagnostic_label_only",
    }


def deterministic_rows_hash(rows: Sequence[Mapping[str, object]]) -> str:
    canonical = sorted(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    payload = "".join(row + "\n" for row in canonical).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_research_summaries(
    event_rows: Sequence[Mapping[str, object]],
    feature_rows: Sequence[Mapping[str, object]],
    anatomy_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    feature_by_event = {str(row["event_id"]): row for row in feature_rows}
    anatomy_by_event = {str(row["event_id"]): row for row in anatomy_rows}
    grouped: dict[tuple[object, ...], list[Mapping[str, object]]] = defaultdict(list)
    for event in event_rows:
        signal = datetime.fromtimestamp(int(event["signal_time"]) / 1000, tz=UTC)
        key = (
            event["event_timeframe"],
            event["instrument"],
            event["direction"],
            signal.year,
            _utc_session(signal.hour),
            event["level_family"],
        )
        grouped[key].append(event)
    output: list[dict[str, object]] = []
    for key, group in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        timeframe, instrument, direction, year, session, family = key
        anatomy = [anatomy_by_event[str(row["event_id"])] for row in group]
        summary: dict[str, object] = {
            "row_type": "event_timeframe_anatomy_summary",
            "event_timeframe": timeframe,
            "instrument": instrument,
            "direction": direction,
            "year": year,
            "utc_session": session,
            "level_family": family,
            "event_count": len(group),
            "unique_physical_event_count": len({row["physical_event_key"] for row in group}),
            "MFE_R_median": _median([row.get("MFE_R") for row in anatomy]),
            "MAE_R_median": _median([row.get("MAE_R") for row in anatomy]),
            "follow_through_rate": _share(anatomy, "follow_through_status", "follow_through"),
            "invalidation_first_rate": _share(
                anatomy, "invalidation_first_status", "invalidation_first"
            ),
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
        for horizon in HORIZONS_MINUTES:
            summary[f"forward_{horizon}m_R_median"] = _median(
                [row.get(f"forward_{horizon}m_R") for row in anatomy]
            )
            summary[f"forward_{horizon}m_ATR_median"] = _median(
                [row.get(f"forward_{horizon}m_ATR") for row in anatomy]
            )
        output.append(summary)

    stability_groups: dict[tuple[str, str, str, str], dict[int, list[Mapping[str, object]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for event in event_rows:
        anatomy = anatomy_by_event.get(str(event["event_id"]))
        if anatomy is None:
            continue
        year = datetime.fromtimestamp(int(event["signal_time"]) / 1000, tz=UTC).year
        key = (
            str(event["event_timeframe"]),
            str(event["instrument"]),
            str(event["direction"]),
            str(event["level_family"]),
        )
        stability_groups[key][year].append(anatomy)
    for (timeframe, instrument, direction, family), years in sorted(stability_groups.items()):
        yearly_r = {
            year: _median([row.get("forward_240m_R") for row in rows])
            for year, rows in sorted(years.items())
        }
        yearly_follow = {
            year: _share(rows, "follow_through_status", "follow_through")
            for year, rows in sorted(years.items())
        }
        resolved_r = [value for value in yearly_r.values() if value is not None]
        resolved_follow = [value for value in yearly_follow.values() if value is not None]
        output.append(
            {
                "row_type": "cross_year_stability_summary",
                "event_timeframe": timeframe,
                "instrument": instrument,
                "direction": direction,
                "level_family": family,
                "year_count": len(years),
                "yearly_forward_240m_R_medians": yearly_r,
                "positive_forward_240m_R_year_count": sum(value > 0 for value in resolved_r),
                "forward_240m_R_year_min": min(resolved_r) if resolved_r else None,
                "forward_240m_R_year_max": max(resolved_r) if resolved_r else None,
                "yearly_follow_through_rates": yearly_follow,
                "follow_through_year_min": min(resolved_follow) if resolved_follow else None,
                "follow_through_year_max": max(resolved_follow) if resolved_follow else None,
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )

    bucket_groups: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    vpa_features = (
        "sweep_volume_bucket",
        "reclaim_volume_bucket",
        "sweep_relative_volume",
        "reclaim_relative_volume",
        "sweep_range_expansion",
        "reclaim_range_expansion",
        "wick_ratio",
        "close_location_value",
        "combined_volume_ratio",
    )
    for event in event_rows:
        feature = feature_by_event.get(str(event["event_id"]))
        anatomy = anatomy_by_event.get(str(event["event_id"]))
        if feature is None or anatomy is None:
            continue
        for feature_name in vpa_features:
            value = feature.get(feature_name)
            bucket = value if feature_name.endswith("_bucket") else _fixed_vpa_bucket(feature_name, value)
            if bucket is None:
                continue
            bucket_groups[(str(event["event_timeframe"]), str(event["level_family"]), feature_name, str(bucket))].append(anatomy)
    for (timeframe, family, feature_name, bucket), group in sorted(bucket_groups.items()):
        output.append(
            {
                "row_type": "vpa_bucket_summary",
                "event_timeframe": timeframe,
                "level_family": family,
                "feature_name": feature_name,
                "bucket": bucket,
                "event_count": len(group),
                "MFE_R_median": _median([row.get("MFE_R") for row in group]),
                "MAE_R_median": _median([row.get("MAE_R") for row in group]),
                "follow_through_rate": _share(group, "follow_through_status", "follow_through"),
                "invalidation_first_rate": _share(
                    group, "invalidation_first_status", "invalidation_first"
                ),
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return output


def _write_outputs(
    *,
    run_root: Path,
    result: LRMultiTimeframeResearchResult,
    preset,
    level_rows: Sequence[Mapping[str, object]],
    core_rows: Mapping[str, Sequence[Mapping[str, object]]],
    audit: Mapping[str, object],
) -> None:
    all_rows = {
        "level_rows.jsonl": level_rows,
        **core_rows,
        "execution_rows.jsonl": (),
        "closed_trade_rows.jsonl": (),
        "filter_results.jsonl": (),
        "variant_closed_trade_rows.jsonl": (),
        "variant_summary_rows.jsonl": (),
        "robustness_rows.jsonl": (),
    }
    for name, rows in all_rows.items():
        _write_jsonl(run_root / name, rows)
    (run_root / "causality_audit.json").write_text(
        json.dumps(dict(audit), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_root / "lr_multitimeframe_event_result.json").write_text(
        result.as_json() + "\n", encoding="utf-8"
    )
    (run_root / "lr_multitimeframe_vpa_causal_event_report.md").write_text(
        _report(result, audit), encoding="utf-8"
    )
    manifest = {
        "strategy": "liquidity_reversal",
        "stage": "lr_multitimeframe_vpa_causal_event_research",
        "schema_version": SCHEMA_VERSION,
        "dataset_window": [result.dataset_start, result.dataset_end],
        "event_timeframes": list(EVENT_POLICIES),
        "proposal_only": True,
        "formal_conclusion_enabled": False,
        "selected_variant": None,
        "holdout_accessed": False,
        "audit_status": result.audit_status,
        "full_audit_status": "not_run_no_closed_trade_unverifiable",
        "risk_engine_invoked": False,
        "risk_and_cost_configuration_modified": False,
        "restricted_variant_b_status": "suspended",
        "entry_tournament_v2_role": "failed_diagnostic_only",
        "config_fingerprint": preset.config_fingerprint,
        "diagnostic_r_is_performance": False,
        "artifact_paths": {name.removesuffix(".jsonl"): name for name in all_rows},
    }
    (run_root / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index = build_index_for_directory(
        run_root,
        strategy="liquidity_reversal",
        stage="lr_multitimeframe_vpa_causal_event_research",
        window=f"{result.dataset_start}_{result.dataset_end}",
        source_command="research_pipeline.cli.research lr-causal-rebuild --stage multitimeframe-events --mode development",
        config_hash=preset.config_fingerprint,
        pipeline_version=SCHEMA_VERSION,
        notes="Causal event and VPA attribution only; no entry, exit, sizing, or performance conclusion.",
    )
    index_paths = write_artifact_index(index, run_root)
    register_research_run(
        registry_path=run_root / "research_run_registry.json",
        artifact_index_path=index_paths["json"],
        strategy="liquidity_reversal",
        stage="lr_multitimeframe_vpa_causal_event_research",
        window=f"{result.dataset_start}_{result.dataset_end}",
        source_command="research_pipeline.cli.research lr-causal-rebuild --stage multitimeframe-events --mode development",
        adapter_version=SCHEMA_VERSION,
        notes="15m/1H/4H event anatomy and VPA attribution; holdout sealed.",
        tags=["lr", "causal", "multitimeframe", "vpa", "development"],
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=True,
        config_hash=preset.config_fingerprint,
    )


def _report(result: LRMultiTimeframeResearchResult, audit: Mapping[str, object]) -> str:
    return "\n".join(
        (
            "# LR Multi-Timeframe + VPA Causal Event Research",
            "",
            "## lr_multitimeframe_event_scanner_report",
            "",
            f"- event-level count: {result.event_count}",
            f"- unique physical event count: {result.unique_physical_event_count}",
            "- event pools: 15m control, 1H sweep/reclaim, 4H wick-reclaim.",
            "",
            "## lr_vpa_attribution_report",
            "",
            f"- causal VPA feature rows: {result.vpa_feature_count}",
            "- post-signal volume fields remain diagnostic labels and cannot enter quality gates.",
            "",
            "## lr_event_timeframe_anatomy_report",
            "",
            f"- diagnostic anatomy rows: {result.anatomy_count}",
            "- diagnostic R is an event-comparison label, not trading performance.",
            "",
            "## lr_event_causality_audit_report",
            "",
            f"- status: {audit.get('status')}",
            f"- violations: {audit.get('violation_count')}",
            "- holdout accessed: false",
            "",
            "## lr_research_direction_recommendation",
            "",
            "### 研究问题 1：15m / 1H / 4H 哪个事件周期更像真实 LR？",
            "",
            "以 summary_rows 的跨年 forward diagnostic R、follow-through、invalidation-first 和 unique physical event count 联合判断；本阶段不按单一收益指标选 winner。",
            "",
            "### 研究问题 2：15m 失败来自周期过低、信号过宽，还是缺少量价确认？",
            "",
            "对比 15m control 与 1H/4H anatomy，再检查同周期 VPA buckets 的组间差异；两类证据分别对应 timeframe/event definition 与 VPA attribution。",
            "",
            "### 研究问题 3：VPA 能否区分高低质量事件？",
            "",
            "使用固定分桶比较 diagnostic R、MFE/MAE、follow-through 与 invalidation-first；post-signal volume 仅为 diagnostic label，不得进入门控。",
            "",
            "### 研究问题 4：哪些 level family 值得继续研究？",
            "",
            "按 timeframe、asset、direction、year 与 level family 检查样本量和跨年稳定性，不按 pooled median 单独排序。",
            "",
            "### 研究问题 5：下一步优先方向是什么？",
            "",
            "仅在完整 development 证据支持时，比较 1H event + 15m execution、4H wick event + 15m execution、VPA quality gate、structural MSS 或暂停 LR causal rebuild。",
            "",
            "### 研究问题 6：推荐方向与依据",
            "",
            "本 artifact 提供可复算证据，不自动生成正式策略或下游 entry 选择。Restricted Variant B 继续 suspended，Entry Tournament v2 只保留失败诊断角色。",
            "",
        )
    )


def _event_row(event: LRMultiTimeframeEvent) -> dict[str, object]:
    return {
        **event.as_dict(),
        "row_type": "causal_event",
        "row_role": "tradable_event",
        "eligible_for_performance": False,
    }


def _event_sort_key(event: LRMultiTimeframeEvent) -> tuple[object, ...]:
    return (
        event.signal_time,
        event.instrument,
        event.event_timeframe,
        event.direction,
        event.level_family,
        event.level_id,
    )


def _policy_bar(policy_name: str) -> str:
    return {
        "15m_micro": "15m",
        "1H_sweep_reclaim": "1H",
        "4H_wick_reclaim": "4H",
    }[policy_name]


def _utc_session(hour: int) -> str:
    if hour < 8:
        return "00-08"
    if hour < 16:
        return "08-16"
    return "16-24"


def _median(values: Sequence[object]) -> float | None:
    numbers = [float(value) for value in values if value not in (None, "")]
    return median(numbers) if numbers else None


def _share(rows: Sequence[Mapping[str, object]], field: str, value: str) -> float | None:
    resolved = [row for row in rows if row.get(field) != "unresolved"]
    if not resolved:
        return None
    return sum(row.get(field) == value for row in resolved) / len(resolved)


def _fixed_vpa_bucket(feature_name: str, value: object) -> str | None:
    if value in (None, ""):
        return None
    number = float(value)
    if feature_name in {"wick_ratio", "close_location_value"}:
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


def _date_bounds(start_date: str, end_date: str) -> tuple[int, int]:
    start = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end = datetime.fromisoformat(end_date).replace(tzinfo=UTC) + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    canonical = sorted(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    path.write_text("".join(row + "\n" for row in canonical), encoding="utf-8")


__all__ = [
    "LRMultiTimeframeResearchResult",
    "audit_multitimeframe_research",
    "build_research_summaries",
    "deterministic_rows_hash",
    "run_lr_multitimeframe_event_research",
]
