from __future__ import annotations

from bisect import bisect_left, bisect_right
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping, Sequence

from trading_system.data.quality import bar_duration_ms
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.diagnostics.entry_quality import (
    EntryDiagnostic,
    EntryRecord,
    ProblemDiagnosis,
    SummaryMetric,
    analyze_entry,
    build_problem_diagnoses,
    build_summary_metrics,
)


@dataclass(frozen=True)
class EntryQualityAnalyzerResult:
    report_path: str
    entries: int
    valid_entries: int
    invalid_entries: int
    query_count: int
    holdout_start_ms: int


def load_entry_rows(path: Path) -> tuple[dict[str, object], ...]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"JSONL row {line_number} must be an object")
                rows.append(payload)
        return tuple(rows)
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return tuple(dict(row) for row in csv.DictReader(handle))
    raise ValueError("input path must use .jsonl or .csv")


def normalize_entry_row(
    row: Mapping[str, object],
    *,
    default_venue: str = "okx",
    default_inst_type: str = "auto",
) -> EntryRecord | None:
    strategy_id = _text(_first(row, "strategy_id", "strategy"))
    instrument = _text(_first(row, "instrument", "symbol", "inst_id"))
    direction = _text(row.get("direction")).lower()
    entry_time = parse_timestamp_ms(_first(row, "entry_time", "entry_timestamp_ms", "fill_time"))
    entry_price = _float(_first(row, "entry_price", "fill_price", "actual_entry_price_if_simulated"))
    if not strategy_id or not instrument or direction not in {"long", "short"} or entry_time is None or entry_price is None or entry_price <= 0:
        return None
    venue = _text(row.get("venue")) or default_venue
    inst_type = _text(row.get("inst_type")).upper()
    if not inst_type:
        inst_type = default_inst_type.upper()
    if inst_type == "AUTO":
        inst_type = "SWAP" if instrument.upper().endswith("-SWAP") else "SPOT"
    atr = _float(_first(row, "atr", "atr_at_entry", "atr_at_breakout"))
    if atr is not None and atr <= 0:
        atr = None
    stop = _float(_first(row, "stop_price", "invalidation_price", "initial_stop_price", "stop_loss"))
    level = _float(_first(row, "level_price", "structure_level", "breakout_level"))
    return EntryRecord(
        strategy_id=strategy_id,
        setup_type=_text(_first(row, "setup_type", "setup_id")) or None,
        instrument=instrument,
        direction=direction,
        signal_time_ms=parse_timestamp_ms(_first(row, "signal_time", "signal_timestamp_ms")),
        entry_time_ms=entry_time,
        entry_price=entry_price,
        stop_price=stop if stop is not None and stop > 0 else None,
        level_price=level if level is not None and level > 0 else None,
        atr=atr,
        tags=_tags(row.get("tags")),
        quality_score=_float(row.get("quality_score")),
        venue=venue,
        inst_type=inst_type,
    )


def run_entry_quality_analyzer(
    *,
    input_path: Path,
    output_path: Path,
    repository,
    timeframe: str = "15m",
    max_horizon_hours: int = 96,
    holdout_start_ms: int,
    default_venue: str = "okx",
    default_inst_type: str = "auto",
) -> EntryQualityAnalyzerResult:
    if holdout_start_ms <= 0:
        raise ValueError("holdout_start_ms must be positive")
    if not 1 <= max_horizon_hours <= 96:
        raise ValueError("max_horizon_hours must be between 1 and 96")
    bar = timeframe_to_okx_bar(timeframe)
    timeframe_ms = bar_duration_ms(bar)
    raw_rows = load_entry_rows(input_path)
    records = tuple(
        record
        for row in raw_rows
        if (record := normalize_entry_row(row, default_venue=default_venue, default_inst_type=default_inst_type)) is not None
    )
    if any(record.entry_time_ms >= holdout_start_ms for record in records):
        raise ValueError("entry_time must be strictly before holdout_start")
    grouped: dict[tuple[str, str, str], list[EntryRecord]] = {}
    for record in records:
        grouped.setdefault((record.venue, record.inst_type, record.instrument), []).append(record)

    diagnostics: list[EntryDiagnostic] = []
    query_count = 0
    for (venue, inst_type, instrument), group in sorted(grouped.items()):
        start_ms = min(_ceil_to_timeframe(row.entry_time_ms, timeframe_ms) for row in group)
        requested_end = max(
            _ceil_to_timeframe(row.entry_time_ms + max_horizon_hours * 3_600_000, timeframe_ms) - timeframe_ms
            for row in group
        )
        holdout_end = holdout_start_ms - timeframe_ms - 1
        end_ms = min(requested_end, holdout_end)
        candles = tuple(
            repository.load_range(
                instrument,
                bar,
                start_ms,
                end_ms,
                venue=venue,
                inst_type=inst_type,
                confirmed_only=True,
            )
        ) if end_ms >= start_ms else ()
        query_count += 1
        timestamps = tuple(int(row.timestamp_ms) for row in candles)
        for record in group:
            first = _ceil_to_timeframe(record.entry_time_ms, timeframe_ms)
            last = record.entry_time_ms + max_horizon_hours * 3_600_000
            left = bisect_left(timestamps, first)
            right = bisect_right(timestamps, last)
            diagnostics.append(
                analyze_entry(
                    record,
                    candles[left:right],
                    timeframe_ms=timeframe_ms,
                    max_horizon_hours=max_horizon_hours,
                )
            )

    summary = build_summary_metrics(total_entries=len(raw_rows), diagnostics=diagnostics, max_horizon_hours=max_horizon_hours)
    problems = build_problem_diagnoses(diagnostics)
    report = render_entry_quality_report(
        input_path=input_path,
        timeframe=timeframe,
        max_horizon_hours=max_horizon_hours,
        holdout_start_ms=holdout_start_ms,
        summary=summary,
        problems=problems,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return EntryQualityAnalyzerResult(
        report_path=str(output_path.resolve()),
        entries=len(raw_rows),
        valid_entries=len(records),
        invalid_entries=len(raw_rows) - len(records),
        query_count=query_count,
        holdout_start_ms=holdout_start_ms,
    )


def render_entry_quality_report(
    *,
    input_path: Path,
    timeframe: str,
    max_horizon_hours: int,
    holdout_start_ms: int,
    summary: Sequence[SummaryMetric],
    problems: Sequence[ProblemDiagnosis],
) -> str:
    lines = [
        "# Universal Entry Quality Analyzer Report",
        "",
        f"Input: `{input_path}`；analysis timeframe: `{timeframe}`；max horizon: `{max_horizon_hours}H`。",
        f"Holdout boundary: `{_iso(holdout_start_ms)}`；future return、MFE、MAE 与 path-order 均为 diagnostic labels。",
        "该报告不代表真实交易绩效、Full Audit、formal candidate 或 live readiness。",
        "",
        "## Entry Quality Summary",
        "",
        "| metric | value | note |",
        "|---|---:|---|",
    ]
    lines.extend(f"| {row.metric} | {_format_metric(row)} | {_escape(row.note)} |" for row in summary)
    lines.extend((
        "",
        "## Problem Diagnosis",
        "",
        "| problem | count | rate | meaning | suggested_action |",
        "|---|---:|---:|---|---|",
    ))
    lines.extend(
        f"| {row.problem} | {row.count} | {_format_rate(row.rate)} | {_escape(row.meaning)} (eligible={row.eligible_count}) | {_escape(row.suggested_action)} |"
        for row in problems
    )
    return "\n".join(lines) + "\n"


def _format_metric(row: SummaryMetric) -> str:
    value = row.value
    if value is None:
        return "n/a"
    if row.metric in {"entries", "valid_entries"}:
        return str(int(value))
    if row.metric.endswith("_rate") or row.metric.startswith("win_rate_") or row.metric in {"+0.5R_first", "+1R_first", "+2R_first", "invalidation_first"}:
        return _format_rate(float(value))
    if "return_" in row.metric or row.metric.endswith("_pct"):
        return f"{float(value):+.4f}%"
    if row.metric.startswith("median_time_") or row.metric == "entry_after_signal_delay_median":
        return f"{float(value):.0f} min"
    return f"{float(value):.4f}"


def _format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _first(row: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp_ms(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)


def _tags(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, Mapping):
        return tuple(sorted(str(key) for key, enabled in value.items() if enabled))
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed)
    return tuple(item.strip() for item in text.split(",") if item.strip())


def _ceil_to_timeframe(timestamp_ms: int, timeframe_ms: int) -> int:
    return ((timestamp_ms + timeframe_ms - 1) // timeframe_ms) * timeframe_ms


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


__all__ = (
    "EntryQualityAnalyzerResult",
    "load_entry_rows",
    "normalize_entry_row",
    "parse_timestamp_ms",
    "render_entry_quality_report",
    "run_entry_quality_analyzer",
)
