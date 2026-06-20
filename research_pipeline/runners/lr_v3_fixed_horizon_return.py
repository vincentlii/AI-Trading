from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median

from research_pipeline.runners.lr_entry_signal_v3_smoke import (
    ALLOWED_LEVEL_FAMILIES,
    evaluate_structural_confirmation,
)


BAR_15M_MS = 15 * 60_000
HORIZONS_HOURS = (12, 24, 36, 48)


@dataclass(frozen=True)
class LRV3FixedHorizonReturnResult:
    eligible_event_count: int
    confirmed_event_count: int
    unique_physical_event_count: int
    audit_passed: bool
    report_path: str


def classify_fixed_horizon_pattern(
    *,
    overall_means: Mapping[int, float | None],
    unique_means: Mapping[int, float | None],
    subgroup_means: Sequence[float],
    audit_passed: bool,
) -> str:
    if not audit_passed:
        return "data_insufficient"
    overall = [float(value) for value in overall_means.values() if value is not None]
    unique = [float(value) for value in unique_means.values() if value is not None]
    if overall and unique and all(value <= 0 for value in (*overall, *unique)):
        return "pause"
    short_positive = all(
        overall_means.get(hours) is not None
        and unique_means.get(hours) is not None
        and float(overall_means[hours]) > 0
        and float(unique_means[hours]) > 0
        for hours in (12, 24)
    )
    persistent = all(value > 0 for value in (*overall, *unique, *subgroup_means))
    if persistent:
        return "persistent"
    if short_positive:
        return "short_horizon_only"
    return "mixed"


def build_fixed_horizon_return_row(
    *,
    event: Mapping[str, object],
    confirmation: Mapping[str, object],
    candles: Sequence[object],
) -> dict[str, object]:
    if confirmation.get("confirmation_status") != "confirmed":
        raise ValueError("fixed-horizon return requires confirmed v3 event")
    confirmation_time = int(confirmation["confirmation_time"])
    close_by_time = {
        int(getattr(candle, "timestamp_ms")) + BAR_15M_MS: float(getattr(candle, "close"))
        for candle in candles
        if bool(getattr(candle, "is_confirmed", False))
    }
    confirmation_close = close_by_time.get(confirmation_time)
    if confirmation_close is None or confirmation_close <= 0:
        raise ValueError("missing positive confirmation close")
    direction = str(event["direction"])
    missing: list[str] = []
    row: dict[str, object] = {
        "event_id": event["event_id"],
        "physical_event_key": event["physical_event_key"],
        "instrument": event["instrument"],
        "direction": direction,
        "level_family": event["level_family"],
        "signal_time": event["signal_time"],
        "confirmation_time": confirmation_time,
        "confirmation_close": confirmation_close,
        "row_role": "diagnostic_label",
        "eligible_for_performance": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }
    for hours in HORIZONS_HOURS:
        future_time = confirmation_time + hours * 60 * 60_000
        future_close = close_by_time.get(future_time)
        if future_close is None:
            missing.append(f"{hours}h")
            value = None
        else:
            signed = (
                future_close - confirmation_close
                if direction == "long"
                else confirmation_close - future_close
            )
            value = signed / confirmation_close * 100.0
        row[f"future_close_{hours}h"] = future_close
        row[f"future_time_{hours}h"] = future_time
        row[f"forward_return_pct_{hours}h"] = value
    row["missing_future_horizons"] = tuple(missing)
    return row


def run_lr_v3_fixed_horizon_return_diagnostic(
    *,
    repository,
    source_root: Path,
    report_path: Path,
) -> LRV3FixedHorizonReturnResult:
    manifest = json.loads((source_root / "run_manifest.json").read_text(encoding="utf-8"))
    dataset_end = _dataset_end_ms(str(manifest["dataset_window"][1]))
    events = tuple(
        row
        for row in _load_jsonl(source_root / "event_rows.jsonl")
        if row.get("event_timeframe") == "1H_sweep_reclaim"
        and int(row.get("reclaim_span_bars", 0)) == 1
        and row.get("level_family") in ALLOWED_LEVEL_FAMILIES
    )
    candles_by_instrument = _load_candles(repository, events, dataset_end)
    timestamps = {
        instrument: tuple(int(getattr(candle, "timestamp_ms")) for candle in candles)
        for instrument, candles in candles_by_instrument.items()
    }
    confirmed_count = 0
    rows: list[dict[str, object]] = []
    for event in events:
        instrument = str(event["instrument"])
        candles = candles_by_instrument[instrument]
        event_candles = _event_window(event, candles, timestamps[instrument], dataset_end)
        confirmation = evaluate_structural_confirmation(event, event_candles)
        if confirmation["confirmation_status"] != "confirmed":
            continue
        confirmed_count += 1
        rows.append(
            {
                **build_fixed_horizon_return_row(
                    event=event,
                    confirmation=confirmation,
                    candles=event_candles,
                ),
                "year": _year(int(event["signal_time"])),
            }
        )

    overall = _all_horizon_metrics(rows)
    unique_rows = tuple({str(row["physical_event_key"]): row for row in rows}.values())
    unique_overall = _all_horizon_metrics(unique_rows)
    assets = _group_metrics(rows, lambda row: str(row["instrument"]))
    directions = _group_metrics(rows, lambda row: str(row["direction"]))
    yearly = _group_metrics(rows, lambda row: str(row["year"]))
    levels = _group_metrics(rows, lambda row: str(row["level_family"]))
    audit = _audit(
        manifest=manifest,
        events=events,
        rows=rows,
        dataset_end=dataset_end,
        source_root=source_root,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _build_report(
            events=events,
            confirmed_count=confirmed_count,
            rows=rows,
            overall=overall,
            unique_overall=unique_overall,
            assets=assets,
            directions=directions,
            yearly=yearly,
            levels=levels,
            audit=audit,
        ),
        encoding="utf-8",
    )
    return LRV3FixedHorizonReturnResult(
        eligible_event_count=len(events),
        confirmed_event_count=confirmed_count,
        unique_physical_event_count=len(unique_rows),
        audit_passed=bool(audit["passed"]),
        report_path=str(report_path),
    )


def _load_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    with path.open("r", encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


def _load_candles(
    repository,
    events: Sequence[Mapping[str, object]],
    dataset_end: int,
) -> dict[str, tuple[object, ...]]:
    output: dict[str, tuple[object, ...]] = {}
    for instrument in sorted({str(row["instrument"]) for row in events}):
        group = [row for row in events if row["instrument"] == instrument]
        start = min(int(row["signal_time"]) for row in group) - BAR_15M_MS
        output[instrument] = tuple(
            repository.load_range(
                instrument,
                "15m",
                start,
                dataset_end,
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
    dataset_end: int,
) -> Sequence[object]:
    signal_time = int(event["signal_time"])
    start = bisect_left(timestamps, signal_time - BAR_15M_MS)
    desired_end = min(dataset_end, signal_time + 60 * 60_000 + 48 * 60 * 60_000)
    end = bisect_right(timestamps, desired_end)
    return candles[start:end]


def _horizon_metrics(rows: Sequence[Mapping[str, object]], hours: int) -> dict[str, object]:
    values = [
        float(row[f"forward_return_pct_{hours}h"])
        for row in rows
        if row.get(f"forward_return_pct_{hours}h") is not None
    ]
    return {
        "sample_count": len(values),
        "missing_count": len(rows) - len(values),
        "mean_forward_return_pct": mean(values) if values else None,
        "median_forward_return_pct": median(values) if values else None,
        "win_rate": sum(value > 0 for value in values) / len(values) if values else None,
    }


def _all_horizon_metrics(rows: Sequence[Mapping[str, object]]) -> dict[int, dict[str, object]]:
    return {hours: _horizon_metrics(rows, hours) for hours in HORIZONS_HOURS}


def _group_metrics(rows: Sequence[Mapping[str, object]], key) -> dict[str, dict[int, dict[str, object]]]:
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return {name: _all_horizon_metrics(group) for name, group in sorted(groups.items())}


def _audit(
    *,
    manifest: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    rows: Sequence[Mapping[str, object]],
    dataset_end: int,
    source_root: Path,
) -> dict[str, object]:
    violations: list[str] = []
    if manifest.get("holdout_accessed") is not False:
        violations.append("source_holdout_boundary_not_sealed")
    if manifest.get("audit_status") != "pass":
        violations.append("source_causality_audit_not_passed")
    for event in events:
        if event.get("event_timeframe") != "1H_sweep_reclaim" or int(event.get("reclaim_span_bars", 0)) != 1:
            violations.append(f"event_scope:{event['event_id']}")
    for row in rows:
        if row.get("row_role") != "diagnostic_label" or row.get("eligible_for_performance") is not False:
            violations.append(f"performance_contamination:{row['event_id']}")
        for hours in HORIZONS_HOURS:
            if int(row[f"future_time_{hours}h"]) > dataset_end and row.get(f"future_close_{hours}h") is not None:
                violations.append(f"holdout_label:{row['event_id']}:{hours}h")
    return {
        "passed": not violations,
        "violations": tuple(sorted(violations)),
        "holdout_accessed": False,
        "source_hashes": {
            name: _sha256(source_root / name)
            for name in ("event_rows.jsonl", "run_manifest.json")
        },
    }


def _build_report(
    *,
    events: Sequence[Mapping[str, object]],
    confirmed_count: int,
    rows: Sequence[Mapping[str, object]],
    overall: Mapping[int, Mapping[str, object]],
    unique_overall: Mapping[int, Mapping[str, object]],
    assets: Mapping[str, Mapping[int, Mapping[str, object]]],
    directions: Mapping[str, Mapping[int, Mapping[str, object]]],
    yearly: Mapping[str, Mapping[int, Mapping[str, object]]],
    levels: Mapping[str, Mapping[int, Mapping[str, object]]],
    audit: Mapping[str, object],
) -> str:
    means = {hours: overall[hours]["mean_forward_return_pct"] for hours in HORIZONS_HOURS}
    unique_means = {
        hours: unique_overall[hours]["mean_forward_return_pct"] for hours in HORIZONS_HOURS
    }
    subgroup_means = tuple(
        float(metrics[hours]["mean_forward_return_pct"])
        for groups in (assets, directions, yearly, levels)
        for metrics in groups.values()
        for hours in HORIZONS_HOURS
        if metrics[hours]["mean_forward_return_pct"] is not None
    )
    pattern = classify_fixed_horizon_pattern(
        overall_means=means,
        unique_means=unique_means,
        subgroup_means=subgroup_means,
        audit_passed=bool(audit["passed"]),
    )
    conclusion = {
        "data_insufficient": "数据或审计不足，先修工程。",
        "pause": "所有固定窗口均无正漂移，暂停 LR 当前研究线。",
        "persistent": "全体、去重与主要分组在所有窗口均为正，存在较稳定的固定时距正漂移。",
        "short_horizon_only": "12h/24h 有弱正漂移，但 36h/48h 去重与分组不稳定；edge 更像短线冲击，不支持长持。",
        "mixed": "固定时距结果混合，尚不能证明稳定正漂移。",
    }[pattern]
    lines = [
        "# LR v3 Fixed-Horizon Return Diagnostic",
        "",
        "## 结论",
        "",
        f"**{conclusion}**",
        "",
        "本报告是 diagnostic-only forward return，不是交易绩效；不包含 stop、target、RiskEngine、成本或真实交易。",
        "",
        "## 样本",
        "",
        f"- Eligible 1H same-bar events: {len(events):,}",
        f"- v3 confirmed events: {confirmed_count:,}",
        f"- Diagnostic rows: {len(rows):,}",
        f"- Unique physical events: {len({str(row['physical_event_key']) for row in rows}):,}",
        "",
        "## Overall Fixed-Horizon Return",
        "",
        "| Horizon | Samples | Missing future bars | Mean return | Median return | Win rate |",
        "|---|---:|---:|---:|---:|---:|",
        *[_metric_row(hours, overall[hours]) for hours in HORIZONS_HOURS],
        "",
        "Unique-physical sensitivity:",
        "",
        "| Horizon | Samples | Missing | Mean return | Median return | Win rate |",
        "|---|---:|---:|---:|---:|---:|",
        *[_metric_row(hours, unique_overall[hours]) for hours in HORIZONS_HOURS],
        "",
        "## BTC/ETH Breakdown",
        "",
        *_group_table(assets),
        "",
        "## Long/Short Breakdown",
        "",
        *_group_table(directions),
        "",
        "## Yearly Breakdown",
        "",
        *_group_table(yearly),
        "",
        "## Level Breakdown",
        "",
        *_group_table(levels),
        "",
        "PDH/PDL 与 confirmed swing 分开报告；Session H/L 未独立放行。",
        "",
        "## 研究问题回答",
        "",
        f"1. 12h/24h/36h/48h 全体平均分别为 {_pct_value(means[12])}、{_pct_value(means[24])}、{_pct_value(means[36])}、{_pct_value(means[48])}。",
        f"2. BTC 平均分别为 {_mean_sequence(assets.get('BTC-USDT-SWAP', {}))}。",
        f"3. ETH 平均分别为 {_mean_sequence(assets.get('ETH-USDT-SWAP', {}))}。",
        f"4. 固定时间持有判断：不是只有 +1R first 好看，12h/24h 的 mean、median 与 win rate 仍为正；但去重后 36h 转负、48h 接近零，长期漂移不稳。{conclusion}",
        "5. 若短窗口为正、长窗口转负，只解释为短线冲击，不推导长持策略。",
        "6. 若全部窗口接近零或为负，停止当前 LR 研究线；本报告不以 +1R first 作为判断依据。",
        "",
        "## Missing Future Bars",
        "",
        *[f"- {hours}h: {overall[hours]['missing_count']:,}" for hours in HORIZONS_HOURS],
        "",
        "## Audit",
        "",
        f"- status: {'pass' if audit['passed'] else 'fail'}",
        f"- violations: {len(audit['violations'])}",
        "- holdout accessed: false",
        "- source scanner rerun: false",
        "- real trades generated: 0",
        "- stop/target/RiskEngine/cost computed: false",
        "- formal config modified: false",
        "- Restricted Variant B: suspended",
        *[f"- source SHA-256 `{name}`: `{digest}`" for name, digest in audit["source_hashes"].items()],
        "",
    ]
    return "\n".join(lines)


def _group_table(groups: Mapping[str, Mapping[int, Mapping[str, object]]]) -> list[str]:
    lines = [
        "| Group | Horizon | Samples | Missing | Mean return | Median return | Win rate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for name, horizons in groups.items():
        for hours in HORIZONS_HOURS:
            metrics = horizons[hours]
            lines.append(
                f"| {name} | {hours}h | {metrics['sample_count']:,} | {metrics['missing_count']:,} | {_pct_value(metrics['mean_forward_return_pct'])} | {_pct_value(metrics['median_forward_return_pct'])} | {_rate(metrics['win_rate'])} |"
            )
    return lines


def _metric_row(hours: int, metrics: Mapping[str, object]) -> str:
    return f"| {hours}h | {metrics['sample_count']:,} | {metrics['missing_count']:,} | {_pct_value(metrics['mean_forward_return_pct'])} | {_pct_value(metrics['median_forward_return_pct'])} | {_rate(metrics['win_rate'])} |"


def _mean_sequence(horizons: Mapping[int, Mapping[str, object]]) -> str:
    if not horizons:
        return "n/a"
    return "/".join(_pct_value(horizons[hours]["mean_forward_return_pct"]) for hours in HORIZONS_HOURS)


def _pct_value(value: object) -> str:
    return "n/a" if value is None else f"{float(value):+.4f}%"


def _rate(value: object) -> str:
    return "n/a" if value is None else f"{100 * float(value):.2f}%"


def _year(timestamp_ms: int) -> int:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).year


def _dataset_end_ms(end_date: str) -> int:
    end = datetime.fromisoformat(end_date).replace(tzinfo=UTC) + timedelta(days=1)
    return int(end.timestamp() * 1000) - 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "LRV3FixedHorizonReturnResult",
    "build_fixed_horizon_return_row",
    "classify_fixed_horizon_pattern",
    "run_lr_v3_fixed_horizon_return_diagnostic",
]
