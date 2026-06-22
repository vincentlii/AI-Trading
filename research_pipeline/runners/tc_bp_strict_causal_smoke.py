from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from trading_system.data.history import DuckDbCandleRepository
from trading_system.reports.trade_charts import build_trade_chart_svg
from trading_system.strategies.trend_price_volume_v1.tc_bp_strict_causal import (
    FIFTEEN_MINUTES_MS,
    FOUR_HOURS_MS,
    StrictBpEvent,
    scan_strict_bp_events,
)


SCHEMA_VERSION = "tc_bp_strict_causal_smoke.v2"
HOLDOUT_START = "2024-12-01"
HORIZONS_HOURS = (1, 4, 8, 12, 24, 48)


@dataclass(frozen=True)
class StrictBpSmokeResult:
    run_root: str
    report_path: str
    decision: str
    event_count: int
    unique_event_count: int


def audit_event_rows(rows: Sequence[Mapping[str, object]], *, holdout_accessed: bool) -> dict[str, object]:
    violations: list[str] = []
    for row in rows:
        event_id = str(row.get("event_id"))
        times = [int(row.get(name) or -1) for name in ("breakout_time", "acceptance_time", "pullback_time", "signal_time")]
        if times != sorted(times):
            violations.append(f"event_time_order:{event_id}")
        if int(row.get("feature_cutoff_time") or -1) > int(row.get("signal_time") or -2):
            violations.append(f"feature_cutoff_after_signal:{event_id}")
        if int(row.get("signal_time") or -1) >= int(row.get("entry_time") or -2):
            violations.append(f"signal_not_before_entry:{event_id}")
    if holdout_accessed:
        violations.append("holdout_accessed")
    return {
        "status": "pass" if not violations else "fail",
        "violations": sorted(violations),
        "violation_count": len(violations),
        "holdout_accessed": holdout_accessed,
        "signal_semantics": "15m BOS confirmed bar close",
        "entry_semantics": "strictly later legal 15m bar",
    }


def evaluate_signal_gate(metrics: Mapping[str, object], *, audit_status: str, visual_review_status: str) -> str:
    count = int(metrics.get("unique_event_count") or 0)
    directional = (
        float(metrics.get("median_4h_return_pct") or 0.0) > 0
        and float(metrics.get("median_12h_return_pct") or 0.0) > 0
        and float(metrics.get("one_r_first_rate") or 0.0) > float(metrics.get("invalidation_first_rate") or 0.0)
        and int(metrics.get("subgroup_failure_count") or 0) == 0
    )
    if not directional:
        return "signal_gate_failed_stop_upstream"
    if audit_status != "pass" or visual_review_status != "pass":
        return "engineering_or_visual_audit_failed"
    if count >= 40 and directional:
        return "signal_gate_passed_execution_allowed"
    if 15 <= count < 40 and directional:
        return "inconclusive_manual_full_development_event_scan"
    return "signal_gate_failed_stop_upstream"


def run_tc_bp_strict_causal_smoke(
    *,
    repository: DuckDbCandleRepository,
    output_root: Path,
    start_date: str = "2024-07-01",
    end_date: str = "2024-11-30",
    visual_review_status: str = "generated_pending_human_review",
) -> StrictBpSmokeResult:
    if end_date >= HOLDOUT_START:
        raise ValueError(f"end_date must be before sealed holdout {HOLDOUT_START}")
    start_ms, end_ms = _date_bounds(start_date, end_date)
    holdout_ms, _ = _date_bounds(HOLDOUT_START, HOLDOUT_START)
    diagnostic_end_ms = min(end_ms + 48 * 60 * 60 * 1000, holdout_ms - FIFTEEN_MINUTES_MS - 1)
    warmup_ms = start_ms - 180 * 24 * 60 * 60 * 1000
    run_id = f"{start_date}_{end_date}_{SCHEMA_VERSION}"
    run_root = Path(output_root).resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    events: list[StrictBpEvent] = []
    candidate_rows: list[dict[str, object]] = []
    candles_4h_by_instrument: dict[str, tuple[object, ...]] = {}
    candles_15m_by_instrument: dict[str, tuple[object, ...]] = {}
    for instrument in ("BTC-USDT-SWAP", "ETH-USDT-SWAP"):
        rows_4h = repository.load_range(instrument, "4H", warmup_ms, end_ms, inst_type="SWAP")
        rows_15m = repository.load_range(instrument, "15m", warmup_ms, diagnostic_end_ms, inst_type="SWAP")
        candles_4h_by_instrument[instrument] = rows_4h
        candles_15m_by_instrument[instrument] = rows_15m
        events.extend(scan_strict_bp_events(
            instrument=instrument,
            candles_4h=rows_4h,
            candles_15m=rows_15m,
            start_ms=start_ms,
            end_ms=end_ms,
            candidate_diagnostics=candidate_rows,
        ))
    level_candidate_count = len(candidate_rows)
    candidate_rows = _deduplicate_candidate_rows(candidate_rows)
    event_rows = [_event_row(event, candles_15m_by_instrument[event.instrument]) for event in events]
    diagnostic_rows = [_diagnostic_row(event, candles_15m_by_instrument[event.instrument]) for event in events]
    geometry_rows = [_visual_geometry_row(event, candles_15m_by_instrument[event.instrument]) for event in events]
    summary_rows = _summary_rows(event_rows, diagnostic_rows)
    audit = audit_event_rows(event_rows, holdout_accessed=False)
    metrics_by_setup = _metrics_by_setup(event_rows, diagnostic_rows, geometry_rows)
    metrics = metrics_by_setup.get("strict_shallow_pullback_v2_balanced", _gate_metrics(event_rows, diagnostic_rows))
    charts_generated = _write_chart_review(
        run_root / "tc_bp_strict_visual_review.html",
        [event for event in events if event.setup == "strict_shallow_pullback_v2_balanced"],
        candles_4h_by_instrument,
        candles_15m_by_instrument,
    )
    if not charts_generated:
        visual_review_status = "not_applicable_no_events"
    if int(metrics.get("unique_event_count") or 0) < 50:
        decision = "semantic_filter_overfit_sample_collapse"
    else:
        decision = evaluate_signal_gate(metrics, audit_status=str(audit["status"]), visual_review_status=visual_review_status)
    if decision == "signal_gate_passed_execution_allowed":
        execution_status = "manual_execution_feasibility_required"
    elif decision == "engineering_or_visual_audit_failed":
        execution_status = "not_run_engineering_or_visual_gate_failed"
    else:
        execution_status = "not_run_signal_gate_failed"
    for name, rows in (
        ("event_rows.jsonl", event_rows),
        ("pullback_candidate_rows.jsonl", candidate_rows),
        ("visual_geometry_rows.jsonl", geometry_rows),
        ("diagnostic_label_rows.jsonl", diagnostic_rows),
        ("summary_rows.jsonl", summary_rows),
        ("execution_rows.jsonl", ()),
        ("closed_trade_rows.jsonl", ()),
    ):
        _write_jsonl(run_root / name, rows)
    _write_json(run_root / "causality_audit.json", audit)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "strategy": "breakout_pullback",
        "stage": "strict_causal_profile_c_signal_smoke",
        "dataset_window": [start_date, end_date],
        "holdout_start": HOLDOUT_START,
        "holdout_accessed": False,
        "raw_ohlcv_only": True,
        "old_event_candidate_cache_reused": False,
        "profile": "C",
        "setups": [
            "strict_level_retest_v1",
            "strict_shallow_pullback_v1",
            "strict_shallow_pullback_v2_balanced",
            "strict_shallow_pullback_v2_clean",
        ],
        "proposal_only": True,
        "formal_conclusion_enabled": False,
        "risk_engine_modified": False,
        "cost_model_modified": False,
        "execution_status": execution_status,
        "decision": decision,
        "metrics": metrics,
        "metrics_by_setup": metrics_by_setup,
        "candidate_failure_counts": dict(sorted(Counter(
            str(row.get("semantic_failure_reason") or row.get("status") or "unknown")
            for row in candidate_rows
        ).items())),
        "level_candidate_count_before_physical_dedup": level_candidate_count,
        "physical_candidate_count": len(candidate_rows),
        "diagnostic_end_ms": diagnostic_end_ms,
        "visual_review_status": visual_review_status,
        "source_database": str(repository.database_path.resolve()),
    }
    _write_json(run_root / "run_manifest.json", manifest)
    report_path = run_root / "tc_bp_strict_causal_smoke_v2_report.md"
    report_path.write_text(_report(manifest, audit, summary_rows), encoding="utf-8")
    _write_json(run_root / "complete_marker.json", {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "event_count": len(event_rows),
        "candidate_count": len(candidate_rows),
        "level_candidate_count_before_physical_dedup": level_candidate_count,
    })
    for stale_index in (run_root / "artifact_index.json", run_root / "artifact_index.md"):
        stale_index.unlink(missing_ok=True)
    index = build_index_for_directory(
        run_root,
        strategy="breakout_pullback",
        stage="strict_causal_profile_c_signal_smoke",
        window=f"{start_date}_{end_date}",
        source_command="scripts/run_tc_bp_strict_causal_smoke.py",
        pipeline_version=SCHEMA_VERSION,
        notes="Raw OHLCV rescan; old event/candidate/execution caches forbidden.",
    )
    write_artifact_index(index, run_root)
    return StrictBpSmokeResult(
        str(run_root),
        str(report_path),
        decision,
        int(metrics.get("event_count") or 0),
        int(metrics.get("unique_event_count") or 0),
    )


def _event_row(event: StrictBpEvent, rows: Sequence[object]) -> dict[str, object]:
    confirmed = [row for row in rows if row.timestamp_ms + FIFTEEN_MINUTES_MS <= event.signal_time]
    signal = confirmed[-1] if confirmed else None
    history = confirmed[-21:-1]
    average_volume = sum(row.volume for row in history) / len(history) if history else 0.0
    average_range = sum(row.high - row.low for row in history) / len(history) if history else 0.0
    relative_volume = signal.volume / average_volume if signal is not None and average_volume > 0 else None
    range_expansion = (signal.high - signal.low) / average_range if signal is not None and average_range > 0 else None
    return {
        **asdict(event),
        "row_role": "tradable_feature",
        "feature_cutoff_time": event.signal_time,
        "signal_relative_volume": relative_volume,
        "signal_range_expansion": range_expansion,
        "vpa_role": "attribution_only",
        "proposal_only": True,
    }


def _visual_geometry_row(event: StrictBpEvent, rows: Sequence[object]) -> dict[str, object]:
    entry_bar = next(
        (row for row in rows if row.is_confirmed and row.timestamp_ms + FIFTEEN_MINUTES_MS == event.entry_time),
        None,
    )
    outer = event.level_upper if event.direction == "long" else event.level_lower
    atr = event.atr_at_breakout or event.atr_4h
    entry_distance = None
    if entry_bar is not None and outer is not None and atr > 0:
        entry_distance = (
            (entry_bar.close - outer) / atr
            if event.direction == "long"
            else (outer - entry_bar.close) / atr
        )
    return {
        "event_id": event.event_id,
        "physical_event_key": event.physical_event_key,
        "row_role": "diagnostic_label",
        "label_source_time": event.entry_time,
        "signal_price_to_level_atr": event.signal_price_to_level_atr,
        "entry_price_to_level_atr": entry_distance,
        "entry_chase_risk": entry_distance is not None and entry_distance > 1.25,
        "entry_reference_semantics": "next confirmed 15m close; diagnostic only",
    }


def _deduplicate_candidate_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["physical_event_key"])].append(row)
    status_rank = {"accepted": 0, "accepted_with_visual_risk": 1, "rejected": 2}
    output: list[dict[str, object]] = []
    for physical_key, alternatives in sorted(grouped.items()):
        selected = min(
            alternatives,
            key=lambda row: (
                status_rank.get(str(row.get("status")), 3),
                abs(float(row.get("pre_pullback_extension_atr") or 999.0)),
                str(row.get("level_id") or ""),
            ),
        )
        output.append({**dict(selected), "physical_event_key": physical_key, "level_alternative_count": len(alternatives)})
    return output


def _diagnostic_row(event: StrictBpEvent, rows: Sequence[object]) -> dict[str, object]:
    result: dict[str, object] = {"event_id": event.event_id, "row_role": "diagnostic_label", "signal_time": event.signal_time}
    after = [row for row in rows if row.timestamp_ms >= event.signal_time]
    sign = 1.0 if event.direction == "long" else -1.0
    for hours in HORIZONS_HOURS:
        target = event.signal_time + hours * 60 * 60 * 1000
        future = next((row for row in after if row.timestamp_ms + FIFTEEN_MINUTES_MS >= target), None)
        result[f"forward_{hours}h_return_pct"] = None if future is None else sign * (future.close - event.signal_price) / event.signal_price * 100.0
    risk = abs(event.signal_price - event.invalidation)
    one_r = event.signal_price + sign * risk
    one_r_time = None
    invalid_time = None
    for row in after:
        if row.timestamp_ms > event.signal_time + 48 * 60 * 60 * 1000:
            break
        if invalid_time is None and ((event.direction == "long" and row.low <= event.invalidation) or (event.direction == "short" and row.high >= event.invalidation)):
            invalid_time = row.timestamp_ms
        if one_r_time is None and ((event.direction == "long" and row.high >= one_r) or (event.direction == "short" and row.low <= one_r)):
            one_r_time = row.timestamp_ms
    result["path_order"] = "one_r_first" if one_r_time is not None and (invalid_time is None or one_r_time < invalid_time) else "invalidation_first" if invalid_time is not None else "no_decision"
    result["label_min_source_time"] = event.signal_time + FIFTEEN_MINUTES_MS
    return result


def _gate_metrics(events: Sequence[Mapping[str, object]], labels: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_id = {str(row["event_id"]): row for row in events}
    paths = [str(row.get("path_order")) for row in labels]
    subgroups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in labels:
        event = by_id[str(row["event_id"])]
        value = row.get("forward_12h_return_pct")
        if value is None:
            continue
        for name, key in (("asset", str(event["instrument"])), ("direction", str(event["direction"])), ("setup", str(event["setup"]))):
            subgroups[(name, key)].append(float(value))
    failures = sum(1 for values in subgroups.values() if len(values) >= 5 and median(values) <= 0)
    return {
        "event_count": len(events),
        "unique_event_count": len({str(row["physical_event_key"]) for row in events}),
        "median_4h_return_pct": _median_field(labels, "forward_4h_return_pct"),
        "median_12h_return_pct": _median_field(labels, "forward_12h_return_pct"),
        "one_r_first_rate": paths.count("one_r_first") / len(paths) if paths else 0.0,
        "invalidation_first_rate": paths.count("invalidation_first") / len(paths) if paths else 0.0,
        "subgroup_failure_count": failures,
    }


def _metrics_by_setup(
    events: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]],
    geometry: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    labels_by_id = {str(row["event_id"]): row for row in labels}
    geometry_by_id = {str(row["event_id"]): row for row in geometry}
    setups = sorted({str(row["setup"]) for row in events})
    output: dict[str, dict[str, object]] = {}
    for setup in setups:
        setup_events = [row for row in events if str(row["setup"]) == setup]
        setup_labels = [labels_by_id[str(row["event_id"])] for row in setup_events if str(row["event_id"]) in labels_by_id]
        base = _gate_metrics(setup_events, setup_labels)
        signal_distances = [float(row["signal_price_to_level_atr"]) for row in setup_events if row.get("signal_price_to_level_atr") is not None]
        entry_distances = [
            float(geometry_by_id[str(row["event_id"])]["entry_price_to_level_atr"])
            for row in setup_events
            if str(row["event_id"]) in geometry_by_id and geometry_by_id[str(row["event_id"])].get("entry_price_to_level_atr") is not None
        ]
        base.update({
            "median_signal_price_to_level_atr": median(signal_distances) if signal_distances else None,
            "p90_signal_price_to_level_atr": _percentile(signal_distances, 0.90),
            "median_entry_price_to_level_atr": median(entry_distances) if entry_distances else None,
            "confirmation_chase_rate": sum(value > 1.25 for value in signal_distances) / len(signal_distances) if signal_distances else 0.0,
            "late_or_second_pullback_rate": sum(int(row.get("pullback_attempt_number") or 0) == 2 for row in setup_events) / len(setup_events) if setup_events else 0.0,
            "pre_pullback_extension_too_far_rate": sum(float(row.get("pre_pullback_extension_atr") or 0.0) > 1.25 for row in setup_events) / len(setup_events) if setup_events else 0.0,
            "close_reentry_rate": 0.0,
            "missing_48h_future_bar_count": sum(row.get("forward_48h_return_pct") is None for row in setup_labels),
        })
        output[setup] = base
    return output


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * quantile + 0.5)))
    return ordered[index]


def _summary_rows(events: Sequence[Mapping[str, object]], labels: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    by_id = {str(row["event_id"]): row for row in events}
    groups: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in labels:
        event = by_id[str(row["event_id"])]
        for dimension, value in (("overall", "all"), ("asset", event["instrument"]), ("direction", event["direction"]), ("setup", event["setup"])):
            groups[(str(dimension), str(value))].append(row)
    output = []
    for (dimension, value), rows in sorted(groups.items()):
        output.append({"dimension": dimension, "value": value, "event_count": len(rows), **{f"median_{h}h_return_pct": _median_field(rows, f"forward_{h}h_return_pct") for h in HORIZONS_HOURS}})
    return output


def _write_chart_review(
    path: Path,
    events: Sequence[StrictBpEvent],
    candles_4h: Mapping[str, Sequence[object]],
    candles_15m: Mapping[str, Sequence[object]],
) -> bool:
    sampled = sorted(events, key=lambda row: hashlib.sha256(row.event_id.encode()).hexdigest())[:20]
    if not sampled:
        path.write_text("<html><body><h1>No events</h1></body></html>", encoding="utf-8")
        return False
    blocks = []
    chart_dir = path.parent / "visual_review_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    for stale_chart in chart_dir.glob("*.svg"):
        stale_chart.unlink()
    for event in sampled:
        rows_4h = [row for row in candles_4h[event.instrument] if event.breakout_time - 12*FOUR_HOURS_MS <= row.timestamp_ms <= event.signal_time + 4*FOUR_HOURS_MS]
        rows_15m = [row for row in candles_15m[event.instrument] if event.pullback_time - 8*60*60*1000 <= row.timestamp_ms <= event.signal_time + 4*60*60*1000]
        if not rows_4h or not rows_15m:
            continue
        risk = abs(event.signal_price - event.invalidation)
        target = event.signal_price + (risk if event.direction == "long" else -risk)
        stem = f"{len(blocks)+1:02d}_{hashlib.sha256(event.event_id.encode()).hexdigest()[:12]}"
        chart_payload = {
            **asdict(event),
            "strategy_chart_style": "breakout_pullback",
            "trend_confirmed_time": event.acceptance_time,
            "pullback_confirmed_time": event.pullback_time,
            "confirmation_time": event.signal_time,
            "entry_zone_low": event.level_lower,
            "entry_zone_high": event.level_upper,
            "entry_price": event.signal_price,
            "stop": event.invalidation,
            "target": target,
            "candidate_id": event.event_id,
        }
        four_h_filename = f"{stem}_4h.svg"
        fifteen_m_filename = f"{stem}_15m.svg"
        (chart_dir / four_h_filename).write_text(build_trade_chart_svg(rows_4h, chart_payload, title=f"4H lifecycle | {event.event_id}"), encoding="utf-8")
        (chart_dir / fifteen_m_filename).write_text(build_trade_chart_svg(rows_15m, chart_payload, title=f"15m BOS | {event.event_id}"), encoding="utf-8")
        flags = ", ".join(event.visual_risk_flags) or "none"
        blocks.append(
            f"<section><h2>{event.instrument} {event.direction} {event.setup}</h2>"
            f"<p>{event.event_id}</p><p>score={event.visual_geometry_score}; attempt={event.pullback_attempt_number}; "
            f"extension={event.pre_pullback_extension_atr}; signal_to_level={event.signal_price_to_level_atr}; flags={flags}</p>"
            f"<div class='charts'><img src='visual_review_charts/{four_h_filename}'><img src='visual_review_charts/{fifteen_m_filename}'></div></section>"
        )
    path.write_text("<html><head><meta charset='utf-8'><style>body{font-family:Arial;margin:24px}section{margin:0 0 44px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px}img{width:100%;border:1px solid #bbb}p{font-size:12px}@media(max-width:900px){.charts{grid-template-columns:1fr}}</style></head><body><h1>TC BP First Pullback v2 Visual Review</h1>"+"".join(blocks)+"</body></html>", encoding="utf-8")
    return bool(blocks)


def _report(manifest: Mapping[str, object], audit: Mapping[str, object], summaries: Sequence[Mapping[str, object]]) -> str:
    metrics = manifest["metrics"]
    lines = ["# TC BP First Pullback Geometry v2 Smoke", "", "## 结论", "", f"Decision: `{manifest['decision']}`。", "", "## 数据与语义", "", "- 从 raw OHLCV 重扫；未复用旧 event/candidate/filter/execution 缓存。", f"- Development smoke: `{manifest['dataset_window'][0]}` 至 `{manifest['dataset_window'][1]}`；所有查询和 diagnostic label 均截止于封存 holdout 前。", "- 4H strict causal breakout/acceptance/first-pullback lifecycle + 15m BOS。", "- 本轮只有 semantic diagnostic 和视觉门；execution/closed trade 为空。", "", "## Balanced 主信号", "", f"- events / unique: {metrics['event_count']} / {metrics['unique_event_count']}", f"- 4h / 12h median signed return: {metrics['median_4h_return_pct']:.4f}% / {metrics['median_12h_return_pct']:.4f}%", f"- +1R-first / invalidation-first: {metrics['one_r_first_rate']:.2%} / {metrics['invalidation_first_rate']:.2%}", f"- median / p90 signal-to-level ATR: {metrics.get('median_signal_price_to_level_atr')} / {metrics.get('p90_signal_price_to_level_atr')}", f"- confirmation chase / second pullback / late extension: {float(metrics.get('confirmation_chase_rate') or 0):.2%} / {float(metrics.get('late_or_second_pullback_rate') or 0):.2%} / {float(metrics.get('pre_pullback_extension_too_far_rate') or 0):.2%}", f"- causality audit: `{audit['status']}`", f"- execution: `{manifest['execution_status']}`", "", "## Setup 对照", "", "| setup | rows | unique | 4h median | 12h median | +1R first | invalidation first |", "|---|---:|---:|---:|---:|---:|---:|"]
    for setup, row in sorted(dict(manifest.get("metrics_by_setup") or {}).items()):
        lines.append(f"| {setup} | {row['event_count']} | {row['unique_event_count']} | {row['median_4h_return_pct']:.4f}% | {row['median_12h_return_pct']:.4f}% | {row['one_r_first_rate']:.2%} | {row['invalidation_first_rate']:.2%} |")
    lines.extend(["", "## Physical Candidate Funnel", "", f"- level alternatives before dedup: {manifest.get('level_candidate_count_before_physical_dedup')}", f"- physical candidates: {manifest.get('physical_candidate_count')}"])
    for reason, count in sorted(dict(manifest.get("candidate_failure_counts") or {}).items()):
        lines.append(f"- `{reason}`: {count}")
    lines.extend(["", "## 分组", "", "| dimension | value | n | 4h median | 12h median |", "|---|---|---:|---:|---:|"])
    for row in summaries:
        lines.append(f"| {row['dimension']} | {row['value']} | {row['event_count']} | {row['median_4h_return_pct']} | {row['median_12h_return_pct']} |")
    lines.extend(["", "## 限制", "", "本轮不是交易绩效；visual score 仅用于诊断和图审，不参与过滤。未优化 confirmation、exit、sizing、quality gate、RiskEngine 或成本参数。", ""])
    return "\n".join(lines)


def _median_field(rows: Sequence[Mapping[str, object]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return median(values) if values else 0.0


def _date_bounds(start: str, end: str) -> tuple[int, int]:
    left = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    right = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return int(left.timestamp() * 1000), int(right.timestamp() * 1000) - 1


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text("".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
