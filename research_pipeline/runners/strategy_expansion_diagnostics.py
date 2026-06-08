from __future__ import annotations

import json
import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_pipeline.adapters.base import StrategyAdapter
from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.registry.strategy_registry import default_strategy_registry
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.strategy_research_validation import _preset_with_override, _run_one_pass
from research_pipeline.core.reports.trend_continuation_core_rebuild import (
    write_trend_continuation_core_rebuild_report,
)
from trading_system.backtest.layered_cache import read_jsonl, stable_hash, write_jsonl
from trading_system.backtest.layered_pipeline import (
    _candle_timestamps,
    _candles_until_cached,
    _context_features,
    _load_timeframe,
    run_layered_proposal,
)
from trading_system.backtest.scanner import BacktestScanTarget
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.trend_price_volume_v1.features import (
    build_market_regime,
    strategy_parameters_from_context,
)
from trading_system.timeframe_profiles import get_profile


class BaselineReuseError(ValueError):
    pass


@dataclass(frozen=True)
class ExpansionDiagnosticsArtifacts:
    run_id: str
    output_dir: str
    manifest: dict[str, Any]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True)
class StrategyExpansionDiagnosticsResult:
    strategy: str
    run_id: str
    run_root: str
    baseline_summary: dict[str, Any]
    variant_summary: dict[str, Any]
    selected_variants: list[str]
    closed_trade_runs: list[dict[str, Any]]
    full_audit_gate_status: str
    final_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_strategy_expansion_diagnostics(
    *,
    strategy: str,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_root: Path,
    max_entry_windows: int | None = None,
    run_top_variants: bool = False,
    baseline_artifact_dir: Path | None = None,
    reuse_baseline: bool = False,
    variant_only: bool = False,
    variants: Sequence[str] | None = None,
    cost_tiers: Sequence[str] = ("base",),
    force: bool = False,
    timestamp: datetime | None = None,
) -> StrategyExpansionDiagnosticsResult:
    adapter = default_strategy_registry().get(strategy)
    setup_filter = adapter.setup_filter()
    if variant_only and not (reuse_baseline or baseline_artifact_dir is not None):
        raise BaselineReuseError("--variant-only requires --reuse-baseline and --baseline-artifact-dir")
    now = timestamp or datetime.now(timezone.utc)
    run_id = stable_fingerprint(
        {
            "strategy": strategy,
            "adapter_version": adapter.adapter_version,
            "dataset_window": dataset_window,
            "timestamp": now.isoformat(),
            "max_entry_windows": max_entry_windows,
        }
    )[:24]
    run_root = Path(output_root) / run_id
    baseline_dir = run_root / "baseline"
    if reuse_baseline or baseline_artifact_dir is not None:
        if baseline_artifact_dir is None:
            raise BaselineReuseError("--reuse-baseline requires --baseline-artifact-dir")
        reusable = load_reusable_baseline_artifacts(
            baseline_dir=Path(baseline_artifact_dir),
            strategy=strategy,
            adapter=adapter,
            dataset_window=dataset_window,
            max_entry_windows=max_entry_windows,
            config_fingerprint=preset.config_fingerprint,
            setup_filter=setup_filter,
        )
        baseline_summary = _load_summary_row(Path(reusable["artifact_paths"]["diagnostic_summary_rows"]))
        baseline_context_rows = read_jsonl(Path(reusable["artifact_paths"]["context_features"]))
        baseline_source_dir = Path(baseline_artifact_dir)
    else:
        baseline = _run_diagnostic_pass(
            strategy=strategy,
            adapter=adapter,
            repository=repository,
            preset=preset,
            dataset_window=dataset_window,
            output_dir=baseline_dir,
            max_entry_windows=max_entry_windows,
            force=force,
            variant_id="baseline_strict",
            parameter_overrides=None,
            context_rows=None,
            config_fingerprint=preset.config_fingerprint,
            source_command="research_pipeline.cli.research strategy-expansion-diagnostics",
        )
        baseline_summary = baseline.summary
        baseline_context_rows = read_jsonl(baseline_dir / "context_features.jsonl")
        baseline_source_dir = baseline_dir
    selected = _select_variants(adapter, baseline_summary, explicit_variants=tuple(variants or ()))
    if variant_only and not selected:
        raise BaselineReuseError("--variant-only requires at least one selected variant")
    variant_summaries: dict[str, Any] = {}
    closed_trade_runs: list[dict[str, Any]] = []
    for variant in selected:
        variant_dir = run_root / "variants" / variant.variant_id
        variant_artifacts = _run_diagnostic_pass(
            strategy=strategy,
            adapter=adapter,
            repository=repository,
            preset=_preset_with_override(preset, variant.parameter_overrides),
            dataset_window=dataset_window,
            output_dir=variant_dir,
            max_entry_windows=max_entry_windows,
            force=force,
            variant_id=variant.variant_id,
            parameter_overrides=variant.parameter_overrides,
            context_rows=baseline_context_rows,
            config_fingerprint=preset.config_fingerprint,
            source_command="research_pipeline.cli.research strategy-expansion-diagnostics",
        )
        variant_summaries[variant.variant_id] = variant_artifacts.summary
        if (
            run_top_variants
            and bool(getattr(variant, "execution_eligible", True))
            and int(variant_artifacts.summary.get("candidate_ready_windows", 0) or 0) > 0
        ):
            validation_dir = run_root / "variant_research_validation" / variant.variant_id
            validation = _run_one_pass(
                strategy=strategy,
                adapter_version=adapter.adapter_version,
                repository=repository,
                preset=preset,
                dataset_window=dataset_window,
                pass_name=f"proposal_only_{variant.variant_id}",
                output_dir=validation_dir,
                cost_tiers=tuple(cost_tiers),
                force=force,
                max_entry_windows=max_entry_windows,
                strategy_parameters_override=variant.parameter_overrides,
            )
            audit_dir = validation_dir / "full_audit"
            audit = run_full_pipeline_audit(
                strategy=strategy,
                artifact_dir=validation_dir,
                registry=None,
                output_dir=audit_dir,
            )
            closed_trade_runs.append(
                {
                    "variant_id": variant.variant_id,
                    "validation_dir": str(validation_dir),
                    "closed_trades": validation["summary"].get("closed_trades", 0),
                    "raw_candidates": validation["summary"].get("candidate_rows", 0),
                    "formal_approved": validation["summary"].get("formal_approved", 0),
                    "reject_reason_distribution": _reject_distribution(validation["summary"]),
                    "stop_distance_too_near": _reject_count(validation["summary"], "stop_distance_too_near"),
                    "margin_required_too_high": _reject_count(validation["summary"], "margin_required_too_high"),
                    "base_metrics": dict(validation["summary"].get("base_metrics", {})),
                    "cost_tier_summaries": list(validation["summary"].get("cost_tier_summaries", ())),
                    "candidate_anatomy": dict(validation["summary"].get("candidate_anatomy", {})),
                    "audit_passed": audit.audit_passed,
                    "blocking_issues": list(audit.blocking_issues),
                }
            )
    result = StrategyExpansionDiagnosticsResult(
        strategy=strategy,
        run_id=run_id,
        run_root=str(run_root),
        baseline_summary=baseline_summary,
        variant_summary=variant_summaries,
        selected_variants=[variant.variant_id for variant in selected],
        closed_trade_runs=closed_trade_runs,
        full_audit_gate_status=_full_audit_gate_status(closed_trade_runs),
        final_status=_final_status(baseline_summary, variant_summaries, closed_trade_runs),
    )
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "strategy_expansion_diagnostics_result.json").write_text(result.as_json() + "\n", encoding="utf-8")
    (run_root / "strategy_expansion_diagnostics_report.md").write_text(_render_result_report(result), encoding="utf-8")
    if strategy == "breakout_pullback" and str(adapter.adapter_version).startswith("lifecycle_core."):
        core_payload = _core_rebuild_payload(result, baseline_source_dir=baseline_source_dir)
        (run_root / "core_rebuild_result.json").write_text(
            json.dumps(core_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_trend_continuation_core_rebuild_report(
            output_dir=run_root,
            baseline_summary=core_payload["baseline_summary"],
            variant_summaries=core_payload["variant_summaries"],
            metadata=core_payload["metadata"],
        )
    if baseline_source_dir != baseline_dir:
        (run_root / "reused_baseline_ref.json").write_text(
            json.dumps({"baseline_artifact_dir": str(baseline_source_dir)}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def refresh_core_rebuild_report(
    run_root: Path,
    *,
    previous_round_result: Path | None = None,
) -> Path:
    run_root = Path(run_root)
    raw = json.loads((run_root / "strategy_expansion_diagnostics_result.json").read_text(encoding="utf-8"))
    result = StrategyExpansionDiagnosticsResult(**raw)
    reused_ref = run_root / "reused_baseline_ref.json"
    baseline_source_dir = run_root / "baseline"
    if reused_ref.exists():
        baseline_source_dir = Path(
            json.loads(reused_ref.read_text(encoding="utf-8"))["baseline_artifact_dir"]
        )
    core_payload = _core_rebuild_payload(
        result,
        baseline_source_dir=baseline_source_dir,
        previous_round_result=previous_round_result,
    )
    (run_root / "core_rebuild_result.json").write_text(
        json.dumps(core_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return write_trend_continuation_core_rebuild_report(
        output_dir=run_root,
        baseline_summary=core_payload["baseline_summary"],
        variant_summaries=core_payload["variant_summaries"],
        metadata=core_payload["metadata"],
    )


def _core_rebuild_payload(
    result: StrategyExpansionDiagnosticsResult,
    *,
    baseline_source_dir: Path | None = None,
    previous_round_result: Path | None = None,
) -> dict[str, Any]:
    validation_by_variant = {
        str(row.get("variant_id")): dict(row) for row in result.closed_trade_runs
    }
    variants: dict[str, dict[str, Any]] = {}
    for variant_id, diagnostic in result.variant_summary.items():
        validation = validation_by_variant.get(variant_id, {})
        diagnostic_summary = _enrich_lifecycle_summary(
            diagnostic,
            Path(result.run_root) / "variants" / variant_id / "core_event_rows.jsonl",
        )
        tiers = {
            str(row.get("cost_tier")): dict(row)
            for row in validation.get("cost_tier_summaries", ())
            if isinstance(row, Mapping)
        }
        base = tiers.get("base", {})
        stress = tiers.get("stress", {})
        harsh = tiers.get("harsh", {})
        variants[variant_id] = {
            **diagnostic_summary,
            **validation,
            "base_net_R_avg": base.get("net_R_avg"),
            "stress_net_R_avg": stress.get("net_R_avg"),
            "harsh_net_R_avg": harsh.get("net_R_avg"),
            "PF": base.get("profit_factor"),
            "median_R": base.get("median_R"),
            "R_std": base.get("R_std"),
            "win_rate": base.get("win_rate"),
            "avg_win_R": base.get("avg_win_R"),
            "avg_loss_R": base.get("avg_loss_R"),
            "top_1_trade_R_contribution": base.get("top_1_trade_R_contribution"),
            "top_2_trades_R_contribution": base.get("top_2_trades_R_contribution"),
            "net_R_avg_excluding_top_1": base.get("net_R_avg_excluding_top_1"),
            "net_R_avg_excluding_top_2": base.get("net_R_avg_excluding_top_2"),
            "full_audit_gate": "passed" if validation.get("audit_passed") else "failed_or_unverifiable",
        }
        variants[variant_id].update(_validation_artifact_summary(validation))
        failure_taxonomy = diagnostic_summary.get("event_failure_taxonomy")
        if isinstance(failure_taxonomy, Mapping):
            for key in (
                "structural_stop_too_near",
                "structural_stop_too_wide",
                "target_space_insufficient",
                "nearest_obstacle_too_close",
            ):
                variants[variant_id][key] = failure_taxonomy.get(key, 0)
    baseline_summary = _enrich_lifecycle_summary(
        result.baseline_summary,
        (baseline_source_dir or Path(result.run_root) / "baseline") / "core_event_rows.jsonl",
    )
    previous = _previous_round_summary(previous_round_result)
    if previous:
        baseline_summary["previous_round"] = previous
    decision_metadata = _core_decision_metadata(variants)
    closed_variants = [row for row in variants.values() if int(row.get("closed_trades") or 0) > 0]
    full_audit_summary = (
        "passed_for_all_closed_trade_variants"
        if closed_variants and all(row.get("full_audit_gate") == "passed" for row in closed_variants)
        else result.full_audit_gate_status
    )
    return {
        "baseline_summary": baseline_summary,
        "variant_summaries": variants,
        "metadata": {
            "run_id": result.run_id,
            "manifest_summary": "manifest-driven lifecycle core rebuild; proposal-only",
            "cross_run_artifact_reuse": "baseline context and fingerprinted diagnostic artifacts persisted",
            "full_audit_summary": full_audit_summary,
            "artifact_paths": [
                str(Path(result.run_root) / "strategy_expansion_diagnostics_result.json"),
                str(Path(result.run_root) / "core_rebuild_result.json"),
            ],
            "known_limitations": [
                "Diagnostic event rows are broad lifecycle observations and never performance rows.",
                f"This bounded rebuild round covers {baseline_summary.get('total_windows', 'unknown')} context windows; it cannot establish broad regime stability.",
                "No formalization or P6 conclusion is permitted in this round.",
            ],
            **decision_metadata,
        },
    }


def _enrich_lifecycle_summary(summary: Mapping[str, Any], event_path: Path) -> dict[str, Any]:
    payload = dict(summary)
    if event_path.exists():
        payload.update(_lifecycle_event_summary(read_jsonl(event_path)))
    payload.setdefault("breakout_failure_taxonomy", payload.get("event_failure_taxonomy", {}))
    return payload


def _validation_artifact_summary(validation: Mapping[str, Any]) -> dict[str, Any]:
    validation_dir = Path(str(validation.get("validation_dir") or ""))
    if not validation_dir.exists():
        return {}
    robustness_path = validation_dir / "robustness_rows.jsonl"
    robustness = read_jsonl(robustness_path) if robustness_path.exists() else ()
    walk_forward = {
        f"window_{row.get('window_index')}": {
            "closed_trades": row.get("closed_trades"),
            "net_R_avg": row.get("net_R_avg"),
            "median_R": row.get("median_R"),
        }
        for row in robustness
        if row.get("robustness_type") == "walk_forward"
    }
    splits = {
        f"{row.get('split')}:{row.get('bucket')}": {
            "closed_trades": row.get("closed_trades"),
            "net_R_avg": row.get("net_R_avg"),
            "median_R": row.get("median_R"),
        }
        for row in robustness
        if row.get("robustness_type") == "regime_split"
    }
    anatomy = validation.get("candidate_anatomy") if isinstance(validation.get("candidate_anatomy"), Mapping) else {}
    base = validation.get("base_metrics") if isinstance(validation.get("base_metrics"), Mapping) else {}
    output = {
        "walk_forward": walk_forward,
        "asset_profile_direction_split": splits,
        "subtype_split": dict(anatomy.get("bp_subtype_counts", {})),
        "total_R": base.get("total_net_R"),
        "robustness": "available" if robustness else "unverifiable",
    }
    filter_path = validation_dir / "filter_results_research.jsonl"
    filter_rows = read_jsonl(filter_path) if filter_path.exists() else ()
    output["stop_anchor_reject_cross_table"] = dict(
        Counter(
            f"{row.get('stop_anchor_type') or row.get('stop_formula_used') or 'unknown'} x "
            f"{row.get('reject_reason') or 'approved'}"
            for row in filter_rows
        )
    )
    rejects = Counter(str(row.get("reject_reason") or "approved") for row in filter_rows)
    for key in (
        "structural_stop_too_near",
        "structural_stop_too_wide",
        "target_space_insufficient",
        "cost_adjusted_RR_too_low",
        "nearest_obstacle_too_close",
    ):
        output[key] = rejects.get(key, 0)
    audit_dir = validation_dir / "full_audit"
    for key, filename in (
        ("no_lookahead", "audit_no_lookahead_rows.jsonl"),
        ("metric_recompute", "audit_metric_recompute_rows.jsonl"),
        ("regression_baseline", "audit_report_consistency_rows.jsonl"),
    ):
        path = audit_dir / filename
        rows = read_jsonl(path) if path.exists() else ()
        output[key] = "passed" if rows and all(bool(row.get("passed")) for row in rows) else "failed_or_unverifiable"
    audit_result_path = audit_dir / "full_pipeline_audit_result.json"
    if audit_result_path.exists():
        audit_result = json.loads(audit_result_path.read_text(encoding="utf-8"))
        output["full_audit_gate"] = "passed" if audit_result.get("audit_passed") else "failed_or_unverifiable"
        if audit_result.get("audit_passed"):
            output["regression_baseline"] = "passed"
    return output


def _previous_round_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    baseline = payload.get("baseline_summary") if isinstance(payload.get("baseline_summary"), Mapping) else {}
    failed = baseline.get("first_failed_stage_counts") if isinstance(baseline.get("first_failed_stage_counts"), Mapping) else {}
    return {
        "old_total_windows": baseline.get("total_windows"),
        "old_true_breakout_failed": failed.get("true_breakout"),
        "old_candidate_ready_windows": baseline.get("candidate_ready_windows"),
        "old_raw_candidates": baseline.get("raw_candidates"),
        "ce_semantic_decision": "B: pause CE and move to breakout_pullback",
    }


def _core_decision_metadata(variants: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for variant_id, row in variants.items():
        tiers = [_float(row.get(key)) for key in ("base_net_R_avg", "stress_net_R_avg", "harsh_net_R_avg")]
        if (
            int(row.get("closed_trades") or 0) >= 10
            and all(value is not None and value > 0 for value in tiers)
            and row.get("full_audit_gate") == "passed"
        ):
            return {
                "decision": "C. Core rebuild identifies one promising subtype; perform subtype-focused refactor.",
                "decision_reason": (
                    f"{variant_id} is the only subtype path with positive base/stress/harsh results and a "
                    "near-discussion sample, while the mixed family remains too sparse for formalization."
                ),
                "next_actions": [
                    f"Isolate {variant_id} as the only proposal-only path for one bounded validation round.",
                    "Preserve lifecycle, structural-stop, cost, RiskEngine, lineage, and audit boundaries unchanged.",
                    "Stop the trend continuation family if the focused subtype does not retain sample and robustness.",
                ],
            }
    return {}


def summarize_diagnostic_funnel(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    context_rows = [
        row
        for row in rows
        if str(row.get("diagnostic_scope") or "context_window") != "event_lifecycle"
    ]
    event_rows = [
        row for row in rows if str(row.get("diagnostic_scope") or "") == "event_lifecycle"
    ]
    first_failed = Counter(_stage_name(row.get("first_failed_stage")) for row in context_rows)
    first_failed.pop("", None)
    profile_summary: dict[str, dict[str, Any]] = {}
    for row in context_rows:
        profile = str(row.get("profile") or "unknown")
        bucket = profile_summary.setdefault(
            profile,
            {
                "total_windows": 0,
                "candidate_ready_windows": 0,
                "first_failed_stage_counts": {},
            },
        )
        bucket["total_windows"] += 1
        if bool(row.get("candidate_ready")):
            bucket["candidate_ready_windows"] += 1
        stage = _stage_name(row.get("first_failed_stage"))
        if stage:
            bucket_counts = Counter(bucket["first_failed_stage_counts"])
            bucket_counts[stage] += 1
            bucket["first_failed_stage_counts"] = dict(bucket_counts)
    candidate_ready = sum(1 for row in context_rows if bool(row.get("candidate_ready")))
    breakout_classes = Counter(str(row.get("breakout_class") or "unknown") for row in event_rows)
    event_failures = Counter(str(row.get("primary_failure_reason") or "") for row in event_rows)
    event_failures.pop("", None)
    event_summary = _lifecycle_event_summary(event_rows)
    return {
        "row_type": "summary_row",
        "summary_name": "expansion_diagnostics_funnel",
        "total_windows": len(context_rows),
        "candidate_ready_windows": candidate_ready,
        "structure_zones_found": sum(int(row.get("structure_zones_found") or 0) for row in context_rows),
        "breakout_event_seeds": len(event_rows),
        "breakout_class_distribution": dict(breakout_classes),
        "event_failure_taxonomy": dict(event_failures),
        **event_summary,
        "first_failed_stage_counts": dict(first_failed),
        "profile_summary": profile_summary,
        "top_failed_stages": [
            {"stage": stage, "count": count} for stage, count in first_failed.most_common()
        ],
    }


def _lifecycle_event_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    return {
        "structure_zone_type_distribution": dict(Counter(str(row.get("level_type") or "unknown") for row in rows)),
        "pullback_health_distribution": dict(Counter(str(row.get("pullback_health_class") or "unknown") for row in rows)),
        "pullback_type_distribution": dict(Counter(str(row.get("pullback_zone_type") or "unknown") for row in rows)),
        "relaunch_quality_distribution": dict(Counter(str(row.get("relaunch_quality_class") or "unknown") for row in rows)),
        "relaunch_type_distribution": dict(Counter(str(row.get("relaunch_type") or "unknown") for row in rows)),
        "target_source_distribution": dict(Counter(str(row.get("target_source") or "unknown") for row in rows)),
        "target_quality_distribution": dict(Counter(str(row.get("target_quality_class") or "unknown") for row in rows)),
        "structural_stop_quality_distribution": dict(Counter(str(row.get("structural_stop_quality") or "unknown") for row in rows)),
        "subtype_split": dict(Counter(str(row.get("bp_subtype") or "unknown") for row in rows)),
        "pullback_diagnostics": _numeric_distribution_summary(
            rows,
            ("pullback_health_score", "pullback_depth_ATR", "pullback_volume_ratio_vs_breakout", "pullback_time_decay"),
        ),
        "relaunch_diagnostics": _numeric_distribution_summary(
            rows,
            ("relaunch_score", "relaunch_delay_bars_after_pullback", "relaunch_displacement_ATR", "relaunch_volume_recovery"),
        ),
        "target_tradeability_summary": _numeric_distribution_summary(
            rows,
            ("target_space_ATR", "gross_RR", "nearest_obstacle_distance_ATR"),
        ),
        "stop_distance_margin_summary": _numeric_distribution_summary(
            rows,
            ("stop_distance_ATR", "stop_distance_zone_ratio", "stop_distance_pullback_ratio"),
        ),
    }


def _numeric_distribution_summary(
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in fields:
        values = sorted(
            value for row in rows if (value := _float(row.get(field))) is not None
        )
        if not values:
            continue
        output[field] = {
            "count": len(values),
            "avg": sum(values) / len(values),
            "p25": values[round((len(values) - 1) * 0.25)],
            "median": values[round((len(values) - 1) * 0.50)],
            "p75": values[round((len(values) - 1) * 0.75)],
            "p90": values[round((len(values) - 1) * 0.90)],
        }
    return output


def classify_trend_gate_rejection(evidence: Mapping[str, object]) -> dict[str, Any]:
    status = str(evidence.get("status") or "unknown")
    direction = str(evidence.get("direction") or "")
    fast_ema = _float(evidence.get("fast_ema"))
    slow_ema = _float(evidence.get("slow_ema"))
    atr = _float(evidence.get("atr")) or 0.0
    adx = _float(evidence.get("adx"))
    er = _float(evidence.get("efficiency_ratio"))
    chop = _float(evidence.get("choppiness"))
    dmi_plus = _float(evidence.get("dmi_plus"))
    dmi_minus = _float(evidence.get("dmi_minus"))
    squeeze = bool(evidence.get("ttm_squeeze"))
    reasons: list[str] = []
    if status == "TREND" and direction:
        return {"primary_reason": "", "reasons": [], "status": status}
    if not direction:
        reasons.append("no_direction")
    if fast_ema is not None and slow_ema is not None and dmi_plus is not None and dmi_minus is not None:
        ema_direction = "long" if fast_ema > slow_ema else "short" if fast_ema < slow_ema else ""
        dmi_direction = "long" if dmi_plus > dmi_minus else "short" if dmi_minus > dmi_plus else ""
        if ema_direction and dmi_direction and ema_direction != dmi_direction:
            reasons.append("direction_mismatch_ema_dmi")
    if adx is None or adx < 25.0:
        reasons.append("adx_below_25")
    if er is None or er < 0.6:
        reasons.append("er_below_0_60")
    if chop is None or chop > 38.2:
        reasons.append("chop_above_38_2")
    if fast_ema is None or slow_ema is None or abs(fast_ema - slow_ema) < max(atr * 0.1, 0.0):
        reasons.append("ema_gap_below_0_1_atr")
    if status == "OVERHEATED_TREND_END":
        reasons.append("overheated_trend_end")
    if status == "COMPRESSION_PENDING_BREAKOUT" or squeeze:
        reasons.append("compression_pending_breakout")
    if status == "RANGE":
        reasons.append("range_regime")
    if status == "MEAN_REVERTING_TRANSITION":
        reasons.append("mean_reverting_transition")
    if status == "unknown":
        reasons.append("no_regime")
    primary = next((reason for reason in reasons if reason in _TREND_REASON_PRIORITY), reasons[0] if reasons else status.lower())
    return {"primary_reason": primary, "reasons": reasons, "status": status}


def summarize_trend_gate_diagnostics(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    reason_counts = Counter(str(row.get("trend_gate_primary_reason") or "unknown") for row in rows)
    profile_summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        profile = str(row.get("profile") or "unknown")
        bucket = profile_summary.setdefault(profile, {"total_windows": 0, "reason_counts": {}})
        bucket["total_windows"] += 1
        counts = Counter(bucket["reason_counts"])
        counts[str(row.get("trend_gate_primary_reason") or "unknown")] += 1
        bucket["reason_counts"] = dict(counts)
    return {
        "row_type": "summary_row",
        "summary_name": "trend_gate_diagnostics",
        "total_windows": len(rows),
        "reason_counts": dict(reason_counts),
        "top_reasons": [{"reason": reason, "count": count} for reason, count in reason_counts.most_common()],
        "profile_summary": profile_summary,
    }


_TREND_REASON_PRIORITY = (
    "no_regime",
    "no_direction",
    "direction_mismatch_ema_dmi",
    "adx_below_25",
    "er_below_0_60",
    "chop_above_38_2",
    "ema_gap_below_0_1_atr",
    "overheated_trend_end",
    "compression_pending_breakout",
    "range_regime",
    "mean_reverting_transition",
)


def build_baseline_reuse_manifest(
    *,
    baseline_dir: Path,
    strategy: str,
    adapter: StrategyAdapter,
    dataset_window: str,
    max_entry_windows: int | None,
    config_fingerprint: str,
    setup_filter: Sequence[str],
) -> dict[str, Any]:
    baseline_dir = Path(baseline_dir)
    artifact_map = _baseline_reuse_artifact_map(baseline_dir)
    missing = [name for name, path in artifact_map.items() if not path.exists()]
    if missing:
        raise BaselineReuseError(f"missing reusable baseline artifacts: {', '.join(sorted(missing))}")
    artifact_hashes = {name: _sha256(path) for name, path in artifact_map.items()}
    manifest = {
        "schema_version": "baseline_reuse_manifest.v1",
        "strategy": strategy,
        "adapter_version": adapter.adapter_version,
        "dataset_window": dataset_window,
        "max_entry_windows": max_entry_windows,
        "config_fingerprint": config_fingerprint,
        "setup_filter": list(setup_filter),
        "stage_catalog_hash": stable_fingerprint([stage.as_dict() for stage in adapter.diagnostic_stages()]),
        "artifact_paths": {name: str(path) for name, path in artifact_map.items()},
        "artifact_hashes": artifact_hashes,
        "reuse_fingerprint": stable_fingerprint(
            {
                "strategy": strategy,
                "adapter_version": adapter.adapter_version,
                "dataset_window": dataset_window,
                "max_entry_windows": max_entry_windows,
                "config_fingerprint": config_fingerprint,
                "setup_filter": list(setup_filter),
                "artifact_hashes": artifact_hashes,
            }
        ),
    }
    (baseline_dir / "baseline_reuse_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_reusable_baseline_artifacts(
    *,
    baseline_dir: Path,
    strategy: str,
    adapter: StrategyAdapter,
    dataset_window: str,
    max_entry_windows: int | None,
    config_fingerprint: str,
    setup_filter: Sequence[str],
) -> dict[str, Any]:
    baseline_dir = Path(baseline_dir)
    manifest_path = baseline_dir / "baseline_reuse_manifest.json"
    if not manifest_path.exists():
        raise BaselineReuseError("missing baseline_reuse_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "strategy": strategy,
        "adapter_version": adapter.adapter_version,
        "dataset_window": dataset_window,
        "max_entry_windows": max_entry_windows,
        "config_fingerprint": config_fingerprint,
        "setup_filter": list(setup_filter),
        "stage_catalog_hash": stable_fingerprint([stage.as_dict() for stage in adapter.diagnostic_stages()]),
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise BaselineReuseError(f"{key} mismatch")
    artifact_paths = manifest.get("artifact_paths")
    artifact_hashes = manifest.get("artifact_hashes")
    if not isinstance(artifact_paths, Mapping) or not isinstance(artifact_hashes, Mapping):
        raise BaselineReuseError("invalid baseline reuse manifest")
    for name, path_value in artifact_paths.items():
        path = Path(str(path_value))
        if not path.exists():
            raise BaselineReuseError(f"missing artifact: {name}")
        expected_hash = str(artifact_hashes.get(name) or "")
        if _sha256(path) != expected_hash:
            raise BaselineReuseError(f"hash mismatch: {name}")
    return dict(manifest)


def _run_diagnostic_pass(
    *,
    strategy: str,
    adapter: StrategyAdapter,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_dir: Path,
    max_entry_windows: int | None,
    force: bool,
    variant_id: str,
    parameter_overrides: Mapping[str, object] | None,
    context_rows: Sequence[Mapping[str, object]] | None,
    config_fingerprint: str,
    source_command: str,
) -> ExpansionDiagnosticsArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_candidates: int | None = None
    if context_rows is None:
        layered = run_layered_proposal(
            repository=repository,
            preset=preset,
            mode="candidate_only",
            cache_dir=output_dir,
            max_entry_windows=max_entry_windows,
            force_context=force,
            force_candidates=force,
            setup_filter=adapter.setup_filter(),
            progress_path=output_dir / "expansion_diagnostics_progress.json",
        )
        context_rows = read_jsonl(layered.context_path)
        raw_candidates = layered.raw_candidates_count
    else:
        write_jsonl(output_dir / "context_features.jsonl", tuple(dict(row) for row in context_rows))
        layered = run_layered_proposal(
            repository=repository,
            preset=preset,
            mode="candidate_only",
            cache_dir=output_dir,
            max_entry_windows=max_entry_windows,
            force_context=False,
            force_candidates=True,
            setup_filter=adapter.setup_filter(),
            progress_path=output_dir / "expansion_diagnostics_progress.json",
        )
        raw_candidates = layered.raw_candidates_count
    diagnostic_rows = diagnostic_rows_for_adapter(
        adapter=adapter,
        repository=repository,
        preset=preset,
        context_rows=context_rows,
        variant_id=variant_id,
        parameter_overrides=parameter_overrides,
    )
    trend_gate_rows = _trend_gate_rows(diagnostic_rows)
    regime_rows = _regime_rows(diagnostic_rows)
    near_miss_rows = _near_miss_rows(diagnostic_rows)
    core_event_rows = tuple(
        row for row in diagnostic_rows if row.get("diagnostic_scope") == "event_lifecycle"
    )
    summary = summarize_diagnostic_funnel(diagnostic_rows)
    summary.update(
        {
            "variant_id": variant_id,
            "raw_candidates": raw_candidates,
            "parameter_overrides": dict(parameter_overrides or {}),
            "profile_differences": _profile_differences(diagnostic_rows),
            "volume_baseline_summary": _volume_baseline_summary(diagnostic_rows),
            "rvol_failure_counts": _rvol_failure_counts(diagnostic_rows),
            "regime_summary": _regime_summary(diagnostic_rows),
            "trend_gate_summary": summarize_trend_gate_diagnostics(trend_gate_rows),
        }
    )
    variant_rows = [
        {
            "row_type": "diagnostic_only",
            "variant_id": variant_id,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
            "candidate_ready_windows": summary["candidate_ready_windows"],
            "raw_candidates": raw_candidates,
            "parameter_overrides": dict(parameter_overrides or {}),
        }
    ]
    artifacts = write_expansion_diagnostics_artifacts(
        output_dir=output_dir,
        strategy=strategy,
        adapter=adapter,
        dataset_window=dataset_window,
        run_id=stable_hash({"strategy": strategy, "variant": variant_id, "dir": str(output_dir)})[:24],
        max_entry_windows=max_entry_windows,
        diagnostic_rows=diagnostic_rows,
        core_event_rows=core_event_rows,
        trend_gate_rows=trend_gate_rows,
        regime_rows=regime_rows,
        near_miss_rows=near_miss_rows,
        variant_rows=variant_rows,
        summary=summary,
        source_command=source_command,
    )
    if variant_id == "baseline_strict":
        build_baseline_reuse_manifest(
            baseline_dir=output_dir,
            strategy=strategy,
            adapter=adapter,
            dataset_window=dataset_window,
            max_entry_windows=max_entry_windows,
            config_fingerprint=config_fingerprint,
            setup_filter=adapter.setup_filter(),
        )
    return artifacts


def diagnostic_rows_for_adapter(
    *,
    adapter: StrategyAdapter,
    repository,
    preset: BacktestPresetConfig,
    context_rows: Sequence[Mapping[str, object]],
    variant_id: str,
    parameter_overrides: Mapping[str, object] | None,
    runtime_cache: dict[str, Any] | None = None,
) -> tuple[dict[str, object], ...]:
    runtime = runtime_cache if runtime_cache is not None else {}
    candle_cache = runtime.setdefault("candle_cache", {})
    timestamp_cache = runtime.setdefault("timestamp_cache", {})
    regime_cache = runtime.setdefault("regime_cache", {})
    structure_regime_cache = runtime.setdefault("structure_regime_cache", {})
    rows: list[dict[str, object]] = []
    if not context_rows:
        return tuple()
    for row_index, row in enumerate(context_rows):
        target = BacktestScanTarget(
            canonical_symbol=str(row["symbol"]),
            inst_id=str(row["inst_id"]),
            venue=str(row["venue"]),
            inst_type=str(row["inst_type"]),
        )
        profile = get_profile(str(row["profile"]))
        timestamp_ms = int(row["timestamp_ms"])

        def cached_timeframe(timeframe: str) -> tuple[object, ...]:
            key = (target.inst_id, target.venue, target.inst_type, timeframe, str(row["symbol"]))
            if key not in candle_cache:
                candle_cache[key] = _load_timeframe(repository, target, timeframe, preset)
                timestamp_cache[key] = _candle_timestamps(candle_cache[key])
            return candle_cache[key]

        def cached_until(timeframe: str, max_bars: int | None = None) -> tuple[object, ...]:
            key = (target.inst_id, target.venue, target.inst_type, timeframe, str(row["symbol"]))
            candles_for_timeframe = cached_timeframe(timeframe)
            return _candles_until_cached(candles_for_timeframe, timestamp_cache[key], timestamp_ms, max_bars=max_bars)

        entry = cached_until(profile.entry_timeframe, 96)
        structure = cached_until(profile.structure_timeframe, 512)
        trend = cached_until(profile.trend_timeframe, 260)
        features = _context_features(target, profile.key, preset)
        if parameter_overrides:
            features["strategy_parameters"] = _merged_strategy_parameters(
                features.get("strategy_parameters"),
                parameter_overrides,
            )
        trend_ts = int(getattr(trend[-1], "timestamp_ms")) if trend else 0
        regime_key = (target.inst_id, target.inst_type, profile.key, trend_ts)
        if regime_key not in regime_cache:
            regime_cache[regime_key] = build_market_regime(trend)
        features["market_regime"] = regime_cache[regime_key]
        structure_ts = int(getattr(structure[-1], "timestamp_ms")) if structure else 0
        structure_key = (target.inst_id, target.inst_type, profile.key, structure_ts)
        if structure_key not in structure_regime_cache:
            structure_regime_cache[structure_key] = build_market_regime(structure)
        features["structure_regime"] = structure_regime_cache[structure_key]
        diagnostics = adapter.evaluate_diagnostics(
            structure,
            entry,
            regime_cache[regime_key],
            parameters=strategy_parameters_from_context(features),
            context_features=features,
        )
        rows.append(
            _diagnostic_row(
                row_index,
                row,
                diagnostics,
                variant_id,
                parameter_overrides,
                structure_regime_cache[structure_key],
            )
        )
        for event_index, event_row in enumerate(diagnostics.get("event_rows", ())):
            if not isinstance(event_row, Mapping):
                continue
            rows.append(
                _core_event_diagnostic_row(
                    row_index=row_index,
                    event_index=event_index,
                    context_row=row,
                    event_row=event_row,
                    variant_id=variant_id,
                    parameter_overrides=parameter_overrides,
                )
            )
    return tuple(rows)


def _diagnostic_row(
    row_index: int,
    context_row: Mapping[str, object],
    diagnostics: Mapping[str, Any],
    variant_id: str,
    parameter_overrides: Mapping[str, object] | None,
    structure_regime: object | None = None,
) -> dict[str, object]:
    metrics = dict(diagnostics.get("metrics", {}))
    stages = dict(diagnostics.get("stages", {}))
    first_failed_stage = str(diagnostics.get("first_failed_stage") or "")
    failed_payload = stages.get(first_failed_stage, {}) if first_failed_stage else {}
    window_stage = stages.get("window_ready", {})
    trend_stage = stages.get("trend_gate", {})
    trend_rejection = classify_trend_gate_rejection(
        {
            "status": trend_stage.get("regime_status"),
            "direction": trend_stage.get("regime_direction"),
            "fast_ema": trend_stage.get("fast_ema"),
            "slow_ema": trend_stage.get("slow_ema"),
            "atr": trend_stage.get("atr"),
            "efficiency_ratio": trend_stage.get("efficiency_ratio"),
            "choppiness": trend_stage.get("choppiness"),
            "dmi_plus": trend_stage.get("dmi_plus"),
            "dmi_minus": trend_stage.get("dmi_minus"),
            "adx": trend_stage.get("adx"),
            "ttm_squeeze": trend_stage.get("ttm_squeeze"),
        }
    )
    trend_reasons = list(trend_rejection["reasons"])
    structure_direction = getattr(structure_regime, "direction", None)
    structure_status = getattr(structure_regime, "status", None)
    if (
        structure_status == "TREND"
        and structure_direction in {"long", "short"}
        and trend_stage.get("regime_direction") in {"long", "short"}
        and structure_direction != trend_stage.get("regime_direction")
    ):
        trend_reasons.append("structure_trend_mismatch")
    return {
        "row_type": "diagnostic_only",
        "diagnostic_scope": "context_window",
        "variant_id": variant_id,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
        "diagnostic_index": row_index,
        "asset": context_row.get("asset"),
        "symbol": context_row.get("symbol"),
        "inst_id": context_row.get("inst_id"),
        "inst_type": context_row.get("inst_type"),
        "venue": context_row.get("venue"),
        "profile": context_row.get("profile"),
        "timestamp_ms": context_row.get("timestamp_ms"),
        "entry_timeframe": context_row.get("entry_timeframe"),
        "structure_timeframe": context_row.get("structure_timeframe"),
        "trend_timeframe": context_row.get("trend_timeframe"),
        "candidate_ready": bool(diagnostics.get("candidate_ready")),
        "structure_zones_found": metrics.get("structure_zones_found"),
        "breakout_event_seeds": metrics.get("breakout_event_seeds"),
        "candidate_ready_events": metrics.get("candidate_ready_events"),
        "first_failed_stage": first_failed_stage,
        "failed_distance_to_threshold": failed_payload.get("distance_to_threshold"),
        "structure_count": window_stage.get("structure_count"),
        "entry_count": window_stage.get("entry_count"),
        "regime_present": window_stage.get("regime_present"),
        "regime_status": trend_stage.get("regime_status"),
        "regime_direction": trend_stage.get("regime_direction"),
        "regime_fast_ema": trend_stage.get("fast_ema"),
        "regime_slow_ema": trend_stage.get("slow_ema"),
        "regime_atr": trend_stage.get("atr"),
        "regime_efficiency_ratio": trend_stage.get("efficiency_ratio"),
        "regime_choppiness": trend_stage.get("choppiness"),
        "regime_dmi_plus": trend_stage.get("dmi_plus"),
        "regime_dmi_minus": trend_stage.get("dmi_minus"),
        "regime_adx": trend_stage.get("adx"),
        "regime_ttm_squeeze": trend_stage.get("ttm_squeeze"),
        "structure_regime_status": getattr(structure_regime, "status", None),
        "structure_regime_direction": getattr(structure_regime, "direction", None),
        "trend_gate_primary_reason": trend_rejection["primary_reason"],
        "trend_gate_reasons": trend_reasons,
        "direction": metrics.get("direction"),
        "breakout_rvol": metrics.get("breakout_rvol"),
        "compression_start_time": metrics.get("compression_start_time"),
        "compression_end_time": metrics.get("compression_end_time"),
        "breakout_time": metrics.get("breakout_time"),
        "confirmation_time": metrics.get("confirmation_time"),
        "compression_high": metrics.get("compression_high"),
        "compression_low": metrics.get("compression_low"),
        "compression_midpoint": metrics.get("compression_midpoint"),
        "compression_box_height": metrics.get("compression_box_height"),
        "compression_box_atr": metrics.get("compression_box_atr"),
        "compression_avg_range_atr": metrics.get("compression_avg_range_atr"),
        "breakout_buffer_atr": metrics.get("breakout_buffer_atr"),
        "pullback_rvol": metrics.get("pullback_rvol"),
        "restart_rvol": metrics.get("restart_rvol"),
        "breakout_body_ratio": metrics.get("breakout_body_ratio"),
        "breakout_close_location": metrics.get("breakout_close_location"),
        "breakout_score": metrics.get("breakout_score"),
        "breakout_displacement_atr": metrics.get("breakout_displacement_atr"),
        "breakout_displacement_box_ratio": metrics.get("breakout_displacement_box_ratio"),
        "breakout_range_vs_ATR": metrics.get("breakout_range_vs_ATR"),
        "breakout_range_vs_box_height": metrics.get("breakout_range_vs_box_height"),
        "close_outside_box_distance_ATR": metrics.get("close_outside_box_distance_ATR"),
        "breakout_volume_z": metrics.get("breakout_volume_z"),
        "volume_expansion_vs_compression": metrics.get("volume_expansion_vs_compression"),
        "range_expansion_vs_compression": metrics.get("range_expansion_vs_compression"),
        "body_expansion_vs_compression": metrics.get("body_expansion_vs_compression"),
        "acceptance_window_bars": metrics.get("acceptance_window_bars"),
        "close_back_inside_box": metrics.get("close_back_inside_box"),
        "close_back_inside_box_bar_index": metrics.get("close_back_inside_box_bar_index"),
        "midpoint_lost_after_breakout": metrics.get("midpoint_lost_after_breakout"),
        "wick_back_inside_but_close_hold": metrics.get("wick_back_inside_but_close_hold"),
        "boundary_hold_after_breakout": metrics.get("boundary_hold_after_breakout"),
        "midpoint_hold_after_breakout": metrics.get("midpoint_hold_after_breakout"),
        "followthrough_bar_count": metrics.get("followthrough_bar_count"),
        "high_volume_no_result_after_breakout": metrics.get("high_volume_no_result_after_breakout"),
        "primary_failure_reason": metrics.get("primary_failure_reason"),
        "secondary_failure_reasons": metrics.get("secondary_failure_reasons"),
        "ce_subtype": metrics.get("ce_subtype"),
        "setup_id": metrics.get("setup_id"),
        "breakout_reference_level": metrics.get("breakout_reference_level"),
        "breakout_level_type": metrics.get("breakout_level_type"),
        "breakout_close": metrics.get("breakout_close"),
        "breakout_displacement_ATR": metrics.get("breakout_displacement_ATR"),
        "breakout_displacement_level_ratio": metrics.get("breakout_displacement_level_ratio"),
        "breakout_range_expansion": metrics.get("breakout_range_expansion"),
        "breakout_body_expansion": metrics.get("breakout_body_expansion"),
        "breakout_RVOL": metrics.get("breakout_RVOL"),
        "acceptance_score": metrics.get("acceptance_score"),
        "acceptance_status": metrics.get("acceptance_status"),
        "close_back_inside_level": metrics.get("close_back_inside_level"),
        "close_back_inside_bar_index": metrics.get("close_back_inside_bar_index"),
        "wick_back_but_close_hold": metrics.get("wick_back_but_close_hold"),
        "immediate_reclaim": metrics.get("immediate_reclaim"),
        "high_volume_no_result": metrics.get("high_volume_no_result"),
        "pullback_start_time": metrics.get("pullback_start_time"),
        "pullback_end_time": metrics.get("pullback_end_time"),
        "pullback_depth_ATR": metrics.get("pullback_depth_ATR"),
        "pullback_depth_vs_breakout": metrics.get("pullback_depth_vs_breakout"),
        "pullback_depth_vs_box": metrics.get("pullback_depth_vs_box"),
        "pullback_bars": metrics.get("pullback_bars"),
        "pullback_volume_ratio_vs_breakout": metrics.get("pullback_volume_ratio_vs_breakout"),
        "pullback_volume_contraction": metrics.get("pullback_volume_contraction"),
        "pullback_range_contraction": metrics.get("pullback_range_contraction"),
        "pullback_body_contraction": metrics.get("pullback_body_contraction"),
        "pullback_close_location": metrics.get("pullback_close_location"),
        "pullback_zone_type": metrics.get("pullback_zone_type"),
        "pullback_zone_distance_ATR": metrics.get("pullback_zone_distance_ATR"),
        "pullback_held_level": metrics.get("pullback_held_level"),
        "pullback_invalidated": metrics.get("pullback_invalidated"),
        "pullback_quality_score": metrics.get("pullback_quality_score"),
        "relaunch_time": metrics.get("relaunch_time"),
        "relaunch_close": metrics.get("relaunch_close"),
        "relaunch_displacement_ATR": metrics.get("relaunch_displacement_ATR"),
        "relaunch_body_pct": metrics.get("relaunch_body_pct"),
        "relaunch_close_location": metrics.get("relaunch_close_location"),
        "relaunch_volume_recovery": metrics.get("relaunch_volume_recovery"),
        "relaunch_breaks_micro_structure": metrics.get("relaunch_breaks_micro_structure"),
        "relaunch_score": metrics.get("relaunch_score"),
        "bp_subtype": metrics.get("bp_subtype"),
        "gross_RR": metrics.get("gross_RR"),
        "cost_adjusted_RR": metrics.get("cost_adjusted_RR"),
        "cost_per_R": metrics.get("cost_per_R"),
        "target_space": metrics.get("target_space"),
        "stop_anchor_type": metrics.get("stop_anchor_type"),
        "stop_distance_ATR": metrics.get("stop_distance_ATR"),
        "stop_distance_level_ratio": metrics.get("stop_distance_level_ratio"),
        "bos_distance": metrics.get("bos_distance"),
        "pullback_midpoint_distance": metrics.get("pullback_midpoint_distance"),
        "entry_volume_status": metrics.get("entry_volume_status"),
        "entry_volume_ratio": metrics.get("entry_volume_ratio"),
        "volume_baseline_mode": metrics.get("volume_baseline_mode"),
        "volume_bucket_sample_count": metrics.get("volume_bucket_sample_count"),
        "used_fallback_volume_baseline": metrics.get("used_fallback_volume_baseline"),
        "entry_volume_baseline_mode": metrics.get("entry_volume_baseline_mode"),
        "entry_volume_bucket_sample_count": metrics.get("entry_volume_bucket_sample_count"),
        "entry_used_fallback_volume_baseline": metrics.get("entry_used_fallback_volume_baseline"),
        "parameter_overrides": dict(parameter_overrides or {}),
        "stage_results": {
            name: bool(payload.get("passed"))
            for name, payload in stages.items()
            if isinstance(payload, Mapping)
        },
    }


def _core_event_diagnostic_row(
    *,
    row_index: int,
    event_index: int,
    context_row: Mapping[str, object],
    event_row: Mapping[str, object],
    variant_id: str,
    parameter_overrides: Mapping[str, object] | None,
) -> dict[str, object]:
    payload = dict(event_row)
    payload.update(
        {
            "row_type": "diagnostic_only",
            "diagnostic_scope": "event_lifecycle",
            "variant_id": variant_id,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
            "diagnostic_index": row_index,
            "event_index": event_index,
            "asset": context_row.get("asset"),
            "symbol": context_row.get("symbol"),
            "inst_id": context_row.get("inst_id"),
            "inst_type": context_row.get("inst_type"),
            "venue": context_row.get("venue"),
            "profile": context_row.get("profile"),
            "timestamp_ms": context_row.get("timestamp_ms"),
            "entry_timeframe": context_row.get("entry_timeframe"),
            "structure_timeframe": context_row.get("structure_timeframe"),
            "trend_timeframe": context_row.get("trend_timeframe"),
            "parameter_overrides": dict(parameter_overrides or {}),
        }
    )
    return payload


def _near_miss_rows(rows: Sequence[Mapping[str, object]], limit: int = 200) -> tuple[dict[str, object], ...]:
    near: list[dict[str, object]] = []
    for row in rows:
        distance = _float(row.get("failed_distance_to_threshold"))
        stage = str(row.get("first_failed_stage") or "")
        if distance is None or not stage:
            continue
        if -0.25 <= distance < 0:
            near.append(
                {
                    "row_type": "diagnostic_only",
                    "variant_id": row.get("variant_id"),
                    "asset": row.get("asset"),
                    "profile": row.get("profile"),
                    "timestamp_ms": row.get("timestamp_ms"),
                    "near_miss_stage": stage,
                    "distance_to_threshold": distance,
                    "proposal_only": True,
                }
            )
    near.sort(key=lambda item: abs(float(item["distance_to_threshold"])))
    return tuple(near[:limit])


def _trend_gate_rows(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    output: list[dict[str, object]] = []
    for row in rows:
        if str(row.get("first_failed_stage") or "") != "trend_gate":
            continue
        output.append(
            {
                "row_type": "diagnostic_only",
                "variant_id": row.get("variant_id"),
                "asset": row.get("asset"),
                "profile": row.get("profile"),
                "timestamp_ms": row.get("timestamp_ms"),
                "trend_timeframe": row.get("trend_timeframe"),
                "structure_timeframe": row.get("structure_timeframe"),
                "regime_status": row.get("regime_status"),
                "regime_direction": row.get("regime_direction"),
                "structure_regime_status": row.get("structure_regime_status"),
                "structure_regime_direction": row.get("structure_regime_direction"),
                "fast_ema": row.get("regime_fast_ema"),
                "slow_ema": row.get("regime_slow_ema"),
                "atr": row.get("regime_atr"),
                "adx": row.get("regime_adx"),
                "dmi_plus": row.get("regime_dmi_plus"),
                "dmi_minus": row.get("regime_dmi_minus"),
                "efficiency_ratio": row.get("regime_efficiency_ratio"),
                "choppiness": row.get("regime_choppiness"),
                "ttm_squeeze": row.get("regime_ttm_squeeze"),
                "trend_gate_primary_reason": row.get("trend_gate_primary_reason"),
                "trend_gate_reasons": row.get("trend_gate_reasons"),
            }
        )
    return tuple(output)


def _regime_rows(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    output: list[dict[str, object]] = []
    for row in rows:
        output.append(
            {
                "row_type": "diagnostic_only",
                "variant_id": row.get("variant_id"),
                "asset": row.get("asset"),
                "profile": row.get("profile"),
                "timestamp_ms": row.get("timestamp_ms"),
                "trend_timeframe": row.get("trend_timeframe"),
                "structure_timeframe": row.get("structure_timeframe"),
                "regime_status": row.get("regime_status"),
                "regime_direction": row.get("regime_direction"),
                "structure_regime_status": row.get("structure_regime_status"),
                "structure_regime_direction": row.get("structure_regime_direction"),
                "adx": row.get("regime_adx"),
                "efficiency_ratio": row.get("regime_efficiency_ratio"),
                "choppiness": row.get("regime_choppiness"),
                "ttm_squeeze": row.get("regime_ttm_squeeze"),
            }
        )
    return tuple(output)


def _select_variants(
    adapter: StrategyAdapter,
    summary: Mapping[str, Any],
    *,
    explicit_variants: Sequence[str] = (),
) -> list[Any]:
    variants = adapter.proposal_expansion_variants()
    if explicit_variants:
        by_id = {variant.variant_id: variant for variant in variants}
        missing = [variant_id for variant_id in explicit_variants if variant_id not in by_id]
        if missing:
            raise BaselineReuseError(f"unknown expansion variant: {', '.join(missing)}")
        return [by_id[variant_id] for variant_id in explicit_variants]
    counts = {
        str(item.get("stage")): int(item.get("count") or 0)
        for item in summary.get("top_failed_stages", [])
        if isinstance(item, Mapping)
    }
    selected: list[Any] = []
    seen_stages: set[str] = set()
    for stage, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if stage in seen_stages:
            continue
        matches = [variant for variant in variants if variant.trigger_stage == stage][:2]
        if matches:
            selected.extend(matches)
            seen_stages.add(stage)
        if len(selected) >= 4:
            break
    distinct = []
    for variant in selected:
        if all(existing.trigger_stage != variant.trigger_stage for existing in distinct):
            distinct.append(variant)
    if len(distinct) >= 2:
        combined = _combined_variant(distinct[0], distinct[1])
        if combined is not None:
            selected.append(combined)
    return selected


def _combined_variant(first: Any, second: Any) -> Any | None:
    from research_pipeline.adapters.base import ProposalExpansionVariant

    merged = _merge_parameter_overrides(first.parameter_overrides, second.parameter_overrides)
    if not merged:
        return None
    return ProposalExpansionVariant(
        variant_id=f"combined_{first.variant_id}__{second.variant_id}",
        description=f"Diagnostic-only combined variant: {first.variant_id} + {second.variant_id}.",
        parameter_overrides=merged,
        trigger_stage=f"{first.trigger_stage}+{second.trigger_stage}",
    )


def _merge_parameter_overrides(
    first: Mapping[str, object],
    second: Mapping[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = {}
    for overrides in (first, second):
        for namespace, values in overrides.items():
            if isinstance(values, Mapping):
                current = dict(merged.get(namespace, {})) if isinstance(merged.get(namespace), Mapping) else {}
                current.update(dict(values))
                merged[namespace] = current
            else:
                merged[namespace] = values
    return merged


def _profile_differences(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    profile_rows: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        profile_rows.setdefault(str(row.get("profile") or "unknown"), []).append(row)
    output: dict[str, Any] = {}
    for profile, bucket in sorted(profile_rows.items()):
        output[profile] = summarize_diagnostic_funnel(bucket)
    return output


def _volume_baseline_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    rows = tuple(row for row in rows if row.get("diagnostic_scope") != "event_lifecycle")
    modes = Counter(str(row.get("volume_baseline_mode") or "unknown") for row in rows)
    entry_modes = Counter(str(row.get("entry_volume_baseline_mode") or "unknown") for row in rows)
    fallback = sum(1 for row in rows if bool(row.get("used_fallback_volume_baseline")))
    entry_fallback = sum(1 for row in rows if bool(row.get("entry_used_fallback_volume_baseline")))
    return {
        "volume_baseline_modes": dict(modes),
        "entry_volume_baseline_modes": dict(entry_modes),
        "used_fallback_volume_baseline_count": fallback,
        "entry_used_fallback_volume_baseline_count": entry_fallback,
    }


def _rvol_failure_counts(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    rows = tuple(row for row in rows if row.get("diagnostic_scope") != "event_lifecycle")
    stages = ("breakout_rvol", "pullback_rvol", "restart_rvol", "entry_volume_confirmation")
    return {
        stage: sum(1 for row in rows if str(row.get("first_failed_stage") or "") == stage)
        for stage in stages
    }


def _regime_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    rows = tuple(row for row in rows if row.get("diagnostic_scope") != "event_lifecycle")
    return {
        "regime_status_counts": dict(Counter(str(row.get("regime_status") or "unknown") for row in rows)),
        "regime_direction_counts": dict(Counter(str(row.get("regime_direction") or "") for row in rows)),
        "regime_present_count": sum(1 for row in rows if bool(row.get("regime_present"))),
    }


def _merged_strategy_parameters(raw: object, override: Mapping[str, object]) -> dict[str, object]:
    params = dict(raw) if isinstance(raw, Mapping) else {}
    for key, value in override.items():
        if isinstance(value, Mapping):
            current = dict(params.get(key, {})) if isinstance(params.get(key), Mapping) else {}
            current.update(dict(value))
            params[key] = current
        else:
            params[key] = value
    return params


def _final_status(
    baseline_summary: Mapping[str, Any],
    variant_summaries: Mapping[str, Any],
    closed_trade_runs: Sequence[Mapping[str, object]],
) -> str:
    if any(int(row.get("closed_trades") or 0) > 0 for row in closed_trade_runs):
        return "diagnostic_candidate"
    if any(int(summary.get("candidate_ready_windows") or 0) > 0 for summary in variant_summaries.values()):
        return "diagnostic_candidate"
    if int(baseline_summary.get("candidate_ready_windows") or 0) > 0:
        return "diagnostic_candidate"
    return "needs_expansion_or_pipeline_fix"


def _full_audit_gate_status(closed_trade_runs: Sequence[Mapping[str, object]]) -> str:
    if not closed_trade_runs:
        return "not_run_no_closed_trade_unverifiable"
    if all(bool(row.get("audit_passed")) for row in closed_trade_runs):
        return "passed_for_closed_trade_variants"
    return "failed_for_closed_trade_variants"


def _reject_count(summary: Mapping[str, Any], reason: str) -> int:
    total = 0
    for item in summary.get("top_reject_reasons", ()):
        if isinstance(item, Sequence) and len(item) >= 2 and str(item[0]) == reason:
            total += int(item[1] or 0)
    return total


def _reject_distribution(summary: Mapping[str, Any]) -> dict[str, int]:
    output: dict[str, int] = {}
    for item in summary.get("top_reject_reasons", ()):
        if isinstance(item, Sequence) and len(item) >= 2:
            output[str(item[0])] = int(item[1] or 0)
    return output


def _render_result_report(result: StrategyExpansionDiagnosticsResult) -> str:
    lines = [
        f"# {result.strategy} Strategy Expansion Diagnostics",
        "",
        f"- run_id: {result.run_id}",
        f"- final_status: {result.final_status}",
        f"- full_audit_gate_status: {result.full_audit_gate_status}",
        f"- baseline_candidate_ready_windows: {result.baseline_summary.get('candidate_ready_windows', 0)}",
        f"- selected_variants: {', '.join(result.selected_variants) if result.selected_variants else 'none'}",
        "",
        "## Baseline Top Failed Stages",
        "",
    ]
    for item in result.baseline_summary.get("top_failed_stages", []):
        if isinstance(item, Mapping):
            lines.append(f"- {item.get('stage')}: {item.get('count')}")
    if not result.baseline_summary.get("top_failed_stages"):
        lines.append("- none")
    lines.extend(["", "## Variant Summary", ""])
    for variant_id, summary in sorted(result.variant_summary.items()):
        lines.append(f"- {variant_id}: candidate_ready_windows={summary.get('candidate_ready_windows', 0)} raw_candidates={summary.get('raw_candidates', 0)}")
    if not result.variant_summary:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _baseline_reuse_artifact_map(baseline_dir: Path) -> dict[str, Path]:
    candidates = {
        "context_features": baseline_dir / "context_features.jsonl",
        "raw_candidates": baseline_dir / "raw_candidates.jsonl",
        "diagnostic_funnel_rows": baseline_dir / "diagnostic_funnel_rows.jsonl",
        "diagnostic_summary_rows": baseline_dir / "diagnostic_summary_rows.jsonl",
        "near_miss_rows": baseline_dir / "near_miss_rows.jsonl",
        "cache_manifest": baseline_dir / "cache_manifest.json",
        "run_manifest": baseline_dir / "run_manifest.json",
        "artifact_index": baseline_dir / "artifact_index.json",
        "research_run_registry": baseline_dir / "research_run_registry.json",
    }
    optional = {
        "core_event_rows": baseline_dir / "core_event_rows.jsonl",
        "regime_rows": baseline_dir / "regime_rows.jsonl",
        "trend_gate_diagnostic_rows": baseline_dir / "trend_gate_diagnostic_rows.jsonl",
    }
    candidates.update({name: path for name, path in optional.items() if path.exists()})
    return candidates


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_summary_row(path: Path) -> dict[str, Any]:
    rows = read_jsonl(path)
    if not rows:
        raise BaselineReuseError("missing diagnostic summary row")
    return dict(rows[0])


def write_expansion_diagnostics_artifacts(
    *,
    output_dir: Path,
    strategy: str,
    adapter: StrategyAdapter,
    dataset_window: str,
    run_id: str,
    max_entry_windows: int | None,
    diagnostic_rows: Sequence[Mapping[str, object]],
    near_miss_rows: Sequence[Mapping[str, object]],
    variant_rows: Sequence[Mapping[str, object]],
    summary: Mapping[str, Any],
    source_command: str,
    core_event_rows: Sequence[Mapping[str, object]] = (),
    trend_gate_rows: Sequence[Mapping[str, object]] = (),
    regime_rows: Sequence[Mapping[str, object]] = (),
) -> ExpansionDiagnosticsArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_path = output_dir / "diagnostic_funnel_rows.jsonl"
    core_event_path = output_dir / "core_event_rows.jsonl"
    trend_gate_path = output_dir / "trend_gate_diagnostic_rows.jsonl"
    regime_path = output_dir / "regime_rows.jsonl"
    near_miss_path = output_dir / "near_miss_rows.jsonl"
    variant_path = output_dir / "expansion_variant_rows.jsonl"
    summary_path = output_dir / "diagnostic_summary_rows.jsonl"
    result_path = output_dir / "expansion_diagnostics_result.json"
    report_path = output_dir / "expansion_diagnostics_report.md"

    normalized_summary = dict(summary)
    normalized_summary.setdefault("row_type", "summary_row")
    normalized_summary.setdefault("summary_name", "expansion_diagnostics_funnel")

    write_jsonl(diagnostic_path, tuple(dict(row) for row in diagnostic_rows))
    if core_event_rows:
        normalized_core_events = tuple(dict(row) for row in core_event_rows)
    else:
        normalized_core_events = tuple(
            dict(row)
            for row in diagnostic_rows
            if row.get("diagnostic_scope") == "event_lifecycle"
        )
    write_jsonl(core_event_path, normalized_core_events)
    write_jsonl(trend_gate_path, tuple(dict(row) for row in trend_gate_rows))
    write_jsonl(regime_path, tuple(dict(row) for row in regime_rows))
    write_jsonl(near_miss_path, tuple(dict(row) for row in near_miss_rows))
    write_jsonl(variant_path, tuple(dict(row) for row in variant_rows))
    write_jsonl(summary_path, (normalized_summary,))

    artifact_paths = {
        "diagnostic_rows": str(diagnostic_path),
        "core_event_rows": str(core_event_path),
        "trend_gate_diagnostic_rows": str(trend_gate_path),
        "regime_rows": str(regime_path),
        "near_miss_rows": str(near_miss_path),
        "expansion_variant_rows": str(variant_path),
        "summary_rows": str(summary_path),
    }
    manifest = RunManifest(
        run_id=run_id,
        strategy=strategy,
        adapter_version=adapter.adapter_version,
        dataset_window=dataset_window,
        artifact_contract=adapter.artifact_contract().as_dict(),
        audit_profile=adapter.audit_profile().as_dict(),
        artifact_paths=artifact_paths,
        config_snapshot={
            "setup_filter": list(adapter.setup_filter()),
            "max_entry_windows": max_entry_windows,
            "stage_catalog": [stage.as_dict() for stage in adapter.diagnostic_stages()],
            "proposal_expansion_variants": [
                variant.as_dict() for variant in adapter.proposal_expansion_variants()
            ],
            "diagnostic_row_types": ["diagnostic_only", "summary_row"],
        },
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="Strategy expansion diagnostics; proposal-only, no formal config change.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    payload = ExpansionDiagnosticsArtifacts(
        run_id=run_id,
        output_dir=str(output_dir),
        manifest=manifest.as_dict(),
        summary=normalized_summary,
    )
    result_path.write_text(payload.as_json() + "\n", encoding="utf-8")
    report_path.write_text(_render_report(strategy, normalized_summary), encoding="utf-8")

    index = build_index_for_directory(
        output_dir,
        strategy=strategy,
        stage="expansion_diagnostics",
        window=dataset_window,
        source_command=source_command,
        config_hash=run_id,
        notes="Proposal-only expansion diagnostics artifacts.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=strategy,
        stage="expansion_diagnostics",
        window=dataset_window,
        source_command=source_command,
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="Proposal-only expansion diagnostics; no formal config change.",
        tags=["expansion_diagnostics", strategy],
    )
    return payload


def _stage_name(value: object) -> str:
    return str(value or "").strip()


def _render_report(strategy: str, summary: Mapping[str, Any]) -> str:
    lines = [
        f"# {strategy} Expansion Diagnostics",
        "",
        f"- total_windows: {summary.get('total_windows', 0)}",
        f"- candidate_ready_windows: {summary.get('candidate_ready_windows', 0)}",
        "",
        "## Top Failed Stages",
        "",
    ]
    for item in summary.get("top_failed_stages", []):
        if isinstance(item, Mapping):
            lines.append(f"- {item.get('stage')}: {item.get('count')}")
    if not summary.get("top_failed_stages"):
        lines.append("- none")
    return "\n".join(lines) + "\n"
