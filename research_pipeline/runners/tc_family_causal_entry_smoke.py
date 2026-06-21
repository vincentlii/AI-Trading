from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.artifacts.reader import read_artifact
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.core.sizing.capped_risk import apply_capped_risk_sizing
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.strategy_research_validation import (
    _diagnostic_rows,
    _regression_baseline,
    _review_log_rows,
    _robustness_rows,
    _summary_rows,
)
from research_pipeline.runners.tc_family_trade_count_expansion import (
    _execute_capped_candidates,
    _family_artifact_contract,
    _filter_candidate,
    _variant_summary,
    family_audit_profile,
)
from trading_system.backtest.layered_cache import write_json, write_jsonl
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION
from trading_system.timeframe_profiles import get_profile


FAMILY_VARIANT_ID = "bp_lifecycle_level_zone_v1"


@dataclass(frozen=True)
class TcFamilyCausalEntrySmokeResult:
    run_id: str
    run_root: str
    report_path: str
    decision: str
    variants: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_tc_family_causal_entry_smoke(
    *,
    repository,
    preset: BacktestPresetConfig,
    source_candidate_rows: Path,
    profile_b_source_candidate_rows: Path | None = None,
    output_root: Path,
    dataset_window: str,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
) -> TcFamilyCausalEntrySmokeResult:
    source_candidate_rows = Path(source_candidate_rows).resolve()
    source_rows = _load_candidate_rows(source_candidate_rows)
    normalized = tuple(_normalize_candidate_availability(row) for row in source_rows)
    if not normalized:
        raise ValueError("TC causal entry smoke requires candidate rows")
    if any(str(row.get("profile") or "") != "C" for row in normalized):
        raise ValueError("TC causal entry smoke stage 1 accepts Profile C candidates only")
    profile_b_path = Path(profile_b_source_candidate_rows).resolve() if profile_b_source_candidate_rows else None
    profile_b_rows: tuple[dict[str, object], ...] = ()
    if profile_b_path is not None:
        profile_b_rows = tuple(_normalize_candidate_availability(row) for row in _load_candidate_rows(profile_b_path))
        if any(str(row.get("profile") or "") != "B" for row in profile_b_rows):
            raise ValueError("TC causal entry Profile B source contains another profile")

    run_seed = {
        "source_hash": _sha256_file(source_candidate_rows),
        "dataset_window": dataset_window,
        "config_fingerprint": preset.config_fingerprint,
        "candidate_count": len(normalized),
        "profile_b_source_hash": _sha256_file(profile_b_path) if profile_b_path is not None else None,
        "profile_b_candidate_count": len(profile_b_rows),
    }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + stable_fingerprint(run_seed)[:12]
    run_root = Path(output_root).resolve() / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    variants: dict[str, Any] = {}
    specs = [
        ("c_4h_next_1h_open_control", "1h", preset, normalized, source_candidate_rows),
        (
            "c_4h_next_15m_open",
            "15m",
            _scaled_execution_preset(preset, source_timeframe="1h", target_timeframe="15m"),
            normalized,
            source_candidate_rows,
        ),
    ]
    if profile_b_rows:
        specs.append(
            (
                "b_1h_next_15m_open",
                "15m",
                _scaled_execution_preset(preset, source_timeframe="1h", target_timeframe="15m"),
                profile_b_rows,
                profile_b_path,
            )
        )
    for label, execution_timeframe, variant_preset, source, candidate_source_path in specs:
        candidates = tuple({**row, "variant": label} for row in source)
        summary = _run_execution_variant(
            repository=repository,
            preset=variant_preset,
            candidates=candidates,
            execution_timeframe=execution_timeframe,
            label=label,
            output_dir=run_root / "variants" / label,
            source_candidate_rows=candidate_source_path,
            dataset_window=dataset_window,
            cost_tiers=cost_tiers,
        )
        variants[label] = summary

    control = variants["c_4h_next_1h_open_control"]
    test = variants["c_4h_next_15m_open"]
    test_gate = _gate_metrics(test, improvement=_number(test.get("base_net_R_avg")) - _number(control.get("base_net_R_avg")))
    test["gate_metrics"] = test_gate
    test["gate_passed"] = _smoke_gate_passes(test_gate)
    if test["gate_passed"]:
        decision = "c_4h_15m_passed"
    elif "b_1h_next_15m_open" in variants:
        profile_b = variants["b_1h_next_15m_open"]
        profile_b_gate = _gate_metrics(
            profile_b,
            improvement=_number(profile_b.get("base_net_R_avg")) - _number(control.get("base_net_R_avg")),
        )
        profile_b["gate_metrics"] = profile_b_gate
        profile_b["gate_passed"] = _smoke_gate_passes(profile_b_gate)
        decision = "b_1h_15m_passed" if profile_b["gate_passed"] else "pause_tc_causal_rebuild"
    else:
        decision = "proceed_to_profile_b"
    payload = {
        "decision": decision,
        "source_candidate_rows": str(source_candidate_rows),
        "source_candidate_hash": run_seed["source_hash"],
        "source_candidate_count": len(normalized),
        "profile_b_source_candidate_rows": str(profile_b_path) if profile_b_path is not None else None,
        "profile_b_source_candidate_hash": run_seed["profile_b_source_hash"],
        "profile_b_source_candidate_count": len(profile_b_rows),
        "dataset_window": dataset_window,
        "holdout_accessed": False,
        "variants": variants,
    }
    report_path = run_root / "tc_causal_entry_rescue_smoke_v1.md"
    report_path.write_text(_render_report(payload), encoding="utf-8")
    write_json(run_root / "tc_causal_entry_rescue_smoke_v1.json", payload)
    result = TcFamilyCausalEntrySmokeResult(
        run_id=run_id,
        run_root=str(run_root),
        report_path=str(report_path),
        decision=decision,
        variants=variants,
    )
    write_json(run_root / "tc_causal_entry_rescue_smoke_result.json", result.as_dict())
    return result


def _run_execution_variant(
    *,
    repository,
    preset: BacktestPresetConfig,
    candidates: Sequence[Mapping[str, object]],
    execution_timeframe: str,
    label: str,
    output_dir: Path,
    source_candidate_rows: Path,
    dataset_window: str,
    cost_tiers: Sequence[str],
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    filter_rows_list: list[dict[str, object]] = []
    for candidate in candidates:
        filtered = _filter_candidate(candidate, preset)
        filtered["row_type"] = "formal_approved" if filtered.get("formal_approved") else "rejected_candidate"
        filtered["eligible_for_performance"] = False
        filtered["proposal_only"] = True
        filter_rows_list.append(apply_capped_risk_sizing(filtered, preset))
    closed_rows = _execute_capped_candidates(
        repository=repository,
        preset=preset,
        filter_rows=filter_rows_list,
        cost_tiers=cost_tiers,
        execution_timeframe=execution_timeframe,
    )
    candidate_rows = tuple(dict(row) for row in candidates)
    filter_rows = tuple(filter_rows_list)
    summary_rows = tuple(
        {
            **row,
            "proposal_approved_after_cap": sum(1 for item in filter_rows if item.get("proposal_approved_after_cap")),
        }
        for row in _summary_rows(candidate_rows, filter_rows, closed_rows)
    )
    robustness_rows = _robustness_rows(closed_rows)
    diagnostic_rows = _diagnostic_rows(filter_rows, candidate_rows, closed_rows)
    review_rows = _review_log_rows(
        strategy="breakout_pullback",
        pass_name=label,
        summary_rows=summary_rows,
        diagnostic_rows=diagnostic_rows,
        anatomy_summary={},
    )
    write_jsonl(output_dir / "candidate_rows.jsonl", candidate_rows)
    write_jsonl(output_dir / "filter_results_research.jsonl", filter_rows)
    write_jsonl(output_dir / "closed_trade_rows.jsonl", closed_rows)
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_rows)
    write_json(output_dir / "regression_baseline.json", _regression_baseline(summary_rows))
    manifest = RunManifest(
        run_id=stable_fingerprint({"label": label, "source": str(source_candidate_rows)})[:24],
        strategy="breakout_pullback",
        adapter_version=f"tc_causal_entry_smoke.v1+{CORE_ENGINE_VERSION}",
        dataset_window=dataset_window,
        artifact_contract=_family_artifact_contract().as_dict(),
        audit_profile=family_audit_profile(FAMILY_VARIANT_ID).as_dict(),
        artifact_paths={
            "candidate_rows": str(output_dir / "candidate_rows.jsonl"),
            "filter_results": str(output_dir / "filter_results_research.jsonl"),
            "execution_rows": str(output_dir / "closed_trade_rows.jsonl"),
            "closed_trade_rows": str(output_dir / "closed_trade_rows.jsonl"),
            "diagnostic_rows": str(output_dir / "diagnostic_rows.jsonl"),
            "summary_rows": str(output_dir / "summary_rows.jsonl"),
            "robustness_rows": str(output_dir / "robustness_rows.jsonl"),
            "regression_baseline": str(output_dir / "regression_baseline.json"),
            "review_log_rows": str(output_dir / "review_log_rows.jsonl"),
        },
        config_snapshot={
            "config_version": preset.config_version,
            "config_fingerprint": preset.config_fingerprint,
            "family_variant_id": FAMILY_VARIANT_ID,
            "research_variant_id": label,
            "execution_timeframe": execution_timeframe,
            "event_available_time_semantics": "event_bar_open_plus_event_timeframe",
            "max_holding_bars": preset.execution.max_holding_bars,
            "reversal_time_cut_bars": preset.execution.reversal_time_cut_bars,
            "chandelier_period": preset.execution.chandelier_period,
            "holdout_accessed": False,
        },
        baseline_ref=str(source_candidate_rows),
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="TC causal entry execution-only smoke; no scanner, exit, sizing, risk, or cost optimization.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy="breakout_pullback",
        stage=f"tc_causal_entry_{label}",
        window=dataset_window,
        source_command="research_pipeline tc-family-causal-entry-smoke",
        config_hash=preset.config_fingerprint,
        notes="Proposal-only causal entry smoke.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="breakout_pullback",
        stage=f"tc_causal_entry_{label}",
        window=dataset_window,
        source_command="research_pipeline tc-family-causal-entry-smoke",
        adapter_version=manifest.adapter_version,
        baseline_ref=str(source_candidate_rows),
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        config_hash=preset.config_fingerprint,
        notes="TC causal entry smoke.",
        tags=["tc_family", "causal_entry_smoke", label],
    )
    audit = run_full_pipeline_audit(
        strategy="breakout_pullback",
        artifact_dir=output_dir,
        registry=None,
        output_dir=output_dir / "full_audit",
    )
    summary = _variant_summary(
        variant_id=FAMILY_VARIANT_ID,
        cache_status={"candidate_source": str(source_candidate_rows), "event_rows": len(candidate_rows)},
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
        robustness_rows=robustness_rows,
        audit=audit,
    )
    summary = _research_variant_summary(summary, label)
    summary["execution_timeframe"] = execution_timeframe
    summary["event_available_time_semantics"] = "event_bar_open_plus_event_timeframe"
    summary["subgroup_harsh_avg_r"] = _subgroup_harsh_avg_r(closed_rows)
    write_json(output_dir / "variant_summary.json", summary)
    return summary


def _event_available_time_ms(candidate: Mapping[str, object]) -> int:
    profile = get_profile(str(candidate.get("profile") or ""))
    event_time = candidate.get("relaunch_time") or candidate.get("acceptance_end_time")
    if event_time in (None, ""):
        raise ValueError("TC candidate is missing causal event time")
    return int(event_time) + _timeframe_ms(profile.structure_timeframe)


def _load_candidate_rows(path: Path) -> tuple[dict[str, object], ...]:
    artifact = read_artifact(Path(path))
    if artifact.kind != "jsonl" or not isinstance(artifact.data, list):
        raise ValueError("TC causal entry source must be a JSONL row artifact")
    return tuple(dict(row) for row in artifact.data if isinstance(row, Mapping))


def _normalize_candidate_availability(candidate: Mapping[str, object]) -> dict[str, object]:
    available_time = _event_available_time_ms(candidate)
    normalized = dict(candidate)
    normalized.update(
        {
            "event_available_time_ms": available_time,
            "timestamp_ms": available_time,
            "signal_timestamp_ms": available_time,
            "feature_cutoff_time": available_time,
            "signal_time": available_time,
        }
    )
    return normalized


def _execution_bar_count(count: int, *, source_timeframe: str, target_timeframe: str) -> int:
    source_ms = _timeframe_ms(source_timeframe)
    target_ms = _timeframe_ms(target_timeframe)
    if count <= 0:
        return 0
    if source_ms % target_ms != 0:
        raise ValueError("execution timeframe must divide the source timeframe")
    return int(count) * (source_ms // target_ms)


def _scaled_execution_preset(
    preset: BacktestPresetConfig,
    *,
    source_timeframe: str,
    target_timeframe: str,
) -> BacktestPresetConfig:
    execution = replace(
        preset.execution,
        max_holding_bars=_execution_bar_count(
            preset.execution.max_holding_bars,
            source_timeframe=source_timeframe,
            target_timeframe=target_timeframe,
        ),
        reversal_time_cut_bars=_execution_bar_count(
            preset.execution.reversal_time_cut_bars,
            source_timeframe=source_timeframe,
            target_timeframe=target_timeframe,
        ),
        chandelier_period=_execution_bar_count(
            preset.execution.chandelier_period,
            source_timeframe=source_timeframe,
            target_timeframe=target_timeframe,
        ),
    )
    return replace(preset, execution=execution)


def _smoke_gate_passes(metrics: Mapping[str, object]) -> bool:
    subgroup = metrics.get("subgroup_harsh_avg_r")
    return (
        int(metrics.get("closed_trades") or 0) >= 80
        and _number(metrics.get("base_avg_r")) > 0.0
        and _number(metrics.get("harsh_avg_r")) >= 0.0
        and _number(metrics.get("base_median_r")) > 0.0
        and _number(metrics.get("base_pf")) > 1.0
        and int(metrics.get("positive_walk_forward_windows") or 0) >= 3
        and int(metrics.get("walk_forward_windows") or 0) >= 5
        and _number(metrics.get("improvement_vs_control_r")) >= 0.05
        and isinstance(subgroup, Mapping)
        and all(_number(subgroup.get(key)) >= -0.05 for key in ("BTC", "ETH", "long", "short"))
    )


def _gate_metrics(summary: Mapping[str, object], *, improvement: float) -> dict[str, object]:
    return {
        "closed_trades": int(summary.get("closed_trades") or 0),
        "base_avg_r": _number(summary.get("base_net_R_avg")),
        "harsh_avg_r": _number(summary.get("harsh_net_R_avg")),
        "base_median_r": _number(summary.get("median_R")),
        "base_pf": _number(summary.get("PF")),
        "positive_walk_forward_windows": int(summary.get("positive_walk_forward_windows") or 0),
        "walk_forward_windows": int(summary.get("walk_forward_windows") or 0),
        "improvement_vs_control_r": improvement,
        "subgroup_harsh_avg_r": dict(summary.get("subgroup_harsh_avg_r") or {}),
    }


def _subgroup_harsh_avg_r(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    harsh = [row for row in rows if str(row.get("cost_tier") or "") == "harsh"]
    output: dict[str, float] = {}
    for key in ("BTC", "ETH"):
        values = [_number(row.get("net_R")) for row in harsh if str(row.get("asset") or "") == key]
        output[key] = mean(values) if values else 0.0
    for key in ("long", "short"):
        values = [_number(row.get("net_R")) for row in harsh if str(row.get("direction") or "") == key]
        output[key] = mean(values) if values else 0.0
    return output


def _research_variant_summary(summary: Mapping[str, object], label: str) -> dict[str, object]:
    labeled = dict(summary)
    labeled["family_variant_id"] = str(summary.get("variant_id") or FAMILY_VARIANT_ID)
    labeled["variant_id"] = label
    return labeled


def _render_report(payload: Mapping[str, object]) -> str:
    variants = payload.get("variants") if isinstance(payload.get("variants"), Mapping) else {}
    lines = [
        "# TC Causal Entry Rescue Smoke v1",
        "",
        "## 结论",
        "",
        f"Decision: `{payload.get('decision')}`。本轮仅验证 causal entry timing，不修改正式配置。",
        "",
        "## 结果",
        "",
        "| Variant | Closed | Base avg R | Harsh avg R | Base PF | Median R | WF + / total | Audit |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label, raw in variants.items():
        summary = raw if isinstance(raw, Mapping) else {}
        lines.append(
            f"| `{label}` | {int(summary.get('closed_trades') or 0)} | "
            f"{_number(summary.get('base_net_R_avg', summary.get('base_avg_r'))):.4f} | "
            f"{_number(summary.get('harsh_net_R_avg', summary.get('harsh_avg_r'))):.4f} | "
            f"{_number(summary.get('PF')):.4f} | "
            f"{_number(summary.get('median_R')):.4f} | "
            f"{int(summary.get('positive_walk_forward_windows') or 0)} / "
            f"{int(summary.get('walk_forward_windows') or 0)} | "
            f"{summary.get('full_audit_gate', 'n/a')} |"
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            f"- Source candidates: {payload.get('source_candidate_count', 'unknown')}。",
            "- `event_available_time = event bar open + event timeframe`。",
            "- Entry 必须严格晚于 event available time。",
            "- RiskEngine、成本、stop、target、notional cap 与正式配置未放宽。",
            "- `holdout_accessed=false`。",
            "",
            "## Stop Rule",
            "",
            (
                "- C 4H+15m 与 B 1H+15m 均未通过预注册门槛，暂停 TC causal rebuild；"
                "不进入 exit、sizing、quality gate 或参数网格优化。"
                if payload.get("decision") == "pause_tc_causal_rebuild"
                else "- 仅当某个 causal variant 通过全部门槛，才允许进入跨年 development validation。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timeframe_ms(timeframe: str) -> int:
    normalized = timeframe.strip().lower()
    if len(normalized) < 2 or not normalized[:-1].isdigit():
        raise ValueError(f"unsupported timeframe: {timeframe}")
    multiplier = {"m": 60_000, "h": 60 * 60_000, "d": 24 * 60 * 60_000}.get(normalized[-1])
    if multiplier is None:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return int(normalized[:-1]) * multiplier


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = ()
