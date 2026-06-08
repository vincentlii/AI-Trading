from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_pipeline.core.analytics.execution_path import (
    compare_retained_removed_rows,
    enrich_execution_path_rows,
    summarize_execution_path_rows,
)
from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.core.reports.tc_family_final_regime_aware_refinement import (
    write_tc_family_final_regime_aware_refinement_report,
)
from research_pipeline.runners.full_pipeline_audit import run_full_pipeline_audit
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.runners.strategy_research_validation import (
    _diagnostic_rows,
    _regression_baseline,
    _review_log_rows,
    _robustness_rows,
    _summary_rows,
)
from research_pipeline.runners.tc_family_cost_aware_exit_target import (
    CE_SHALLOW_COMPARISON_ID,
    _cost_aware_score,
    _load_source_artifacts,
    _num,
    _single_dimension_concentration,
    _with_path_summary,
)
from research_pipeline.runners.tc_family_cost_aware_refinement_with_trend_state import (
    build_trend_state_lineage_diagnostics,
    _copy_trend_state,
    _source_with_trend_state,
)
from research_pipeline.runners.tc_family_trade_count_expansion import (
    _family_artifact_contract,
    _portfolio_heat_allows,
    _simulate_capped_candidate,
    _tier_preset,
    _variant_summary,
    family_audit_profile,
)
from trading_system.config.loader import BacktestPresetConfig
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION
from trading_system.strategies.trend_price_volume_v1.trend_continuation_family import family_variant_setup
from trading_system.backtest.layered_cache import write_json, write_jsonl


BASELINE_VARIANT_ID = "bp_shallow_cost_aware_admission_v3"

FINAL_REGIME_VARIANT_IDS = (
    "bp_shallow_regime_diagnostic_no_filter_v1",
    "bp_shallow_regime_adaptive_exit_v1",
    "bp_shallow_regime_cost_gate_v1",
)


@dataclass(frozen=True)
class TcFamilyFinalRegimeAwareRefinementResult:
    run_id: str
    run_root: str
    baseline_run_root: str
    decision: str
    baseline_summary: dict[str, Any]
    variant_summaries: dict[str, Any]
    regime_diagnostic_summary: dict[str, Any]
    ce_shallow_comparison: dict[str, Any]
    report_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_tc_family_final_regime_aware_refinement(
    *,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    baseline_run_root: Path,
    output_root: Path,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
    timestamp: datetime | None = None,
) -> TcFamilyFinalRegimeAwareRefinementResult:
    baseline_run_root = Path(baseline_run_root)
    output_root = Path(output_root)
    now = timestamp or datetime.now(timezone.utc)
    fingerprint = stable_fingerprint(
        {
            "round": "tc_family_final_regime_aware_refinement",
            "baseline_run_root": str(baseline_run_root),
            "dataset_window": dataset_window,
            "config_fingerprint": preset.config_fingerprint,
            "core_engine_version": CORE_ENGINE_VERSION,
            "source_variant": BASELINE_VARIANT_ID,
            "variants": FINAL_REGIME_VARIANT_IDS,
            "trend_state_policy": "diagnostic_and_proposal_routing_only",
        }
    )
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{fingerprint[:12]}"
    run_root = output_root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    trend_cache: dict[tuple[str, str, str, str, int], dict[str, object]] = {}
    candle_cache: dict[tuple[str, str, str, str, str], tuple[tuple[int, object], ...]] = {}
    source = _source_with_trend_state(
        _load_source_artifacts(baseline_run_root, BASELINE_VARIANT_ID),
        repository=repository,
        trend_cache=trend_cache,
        candle_cache=candle_cache,
    )
    baseline_summary = _with_path_summary(source)
    baseline_summary["trend_state_split"] = _base_trend_state_split(source["closed_rows"])
    baseline_summary["regime_diagnostic_summary"] = build_regime_diagnostic_summary(source["closed_rows"])
    baseline_summary["trend_state_lineage"] = build_trend_state_lineage_diagnostics(
        candidate_rows=source["candidate_rows"],
        filter_rows=source["filter_rows"],
        closed_rows=source["closed_rows"],
    )
    baseline_summary["trend_state_metrics"] = baseline_summary["regime_diagnostic_summary"]

    ce_shallow = _source_with_trend_state(
        _load_ce_shallow_comparison_source_for_final_round(baseline_run_root),
        repository=repository,
        trend_cache=trend_cache,
        candle_cache=candle_cache,
    )
    ce_shallow_comparison = _with_path_summary(ce_shallow)
    ce_shallow_comparison["trend_state_split"] = _base_trend_state_split(ce_shallow["closed_rows"])

    artifact_paths: list[str] = []
    variant_summaries: dict[str, Any] = {}
    for variant_id in FINAL_REGIME_VARIANT_IDS:
        output_dir = run_root / "variants" / variant_id
        summary = _run_final_regime_variant(
            variant_id=variant_id,
            source=source,
            repository=repository,
            preset=preset,
            dataset_window=dataset_window,
            output_dir=output_dir,
            cost_tiers=tuple(cost_tiers),
        )
        variant_summaries[variant_id] = summary
        artifact_paths.append(str(output_dir))

    decision = select_final_regime_decision(variant_summaries, baseline_summary=baseline_summary)
    payload = {
        "run_id": run_id,
        "baseline_run_root": str(baseline_run_root),
        "decision": decision,
        "decision_reason": _decision_reason(decision, baseline_summary, variant_summaries),
        "executive_summary": _executive_summary(decision, baseline_summary, variant_summaries),
        "constraints": [
            "proposal-only / diagnostic-only; no formalization and no P6",
            "live_trading_enabled=false; no live order path used",
            "RiskEngine, costs, slippage, margin, notional cap, portfolio heat, formal stop, formal target, and formal exit boundaries remain unchanged",
            "performance metrics use row_type=closed_trade only",
            "diagnostic/proposal/summary rows remain excluded from performance",
            "LR final evidence remains read-only and is not included in this round's performance",
            "capped risk sizing remains proposal-only with minimum actual risk after cap of 0.10% equity",
            "trend_state is used for diagnostic split and proposal-only policy routing, not direct formal filtering",
        ],
        "baseline_summary": baseline_summary,
        "variant_summaries": variant_summaries,
        "regime_diagnostic_summary": baseline_summary["regime_diagnostic_summary"],
        "regime_interpretation": _regime_interpretation(baseline_summary["regime_diagnostic_summary"]),
        "ce_shallow_comparison": ce_shallow_comparison,
        "next_actions": _next_actions(decision),
        "artifact_paths": artifact_paths,
        "known_limitations": [
            "Regime-aware policies are proposal-only shadow routes and are not formal filters.",
            "RANGE and TREND may remain small-sample diagnostic groups.",
            "No asset/profile/direction hand-picking was applied.",
        ],
    }
    report_path = write_tc_family_final_regime_aware_refinement_report(output_dir=run_root, payload=payload)
    result = TcFamilyFinalRegimeAwareRefinementResult(
        run_id=run_id,
        run_root=str(run_root),
        baseline_run_root=str(baseline_run_root),
        decision=decision,
        baseline_summary=baseline_summary,
        variant_summaries=variant_summaries,
        regime_diagnostic_summary=baseline_summary["regime_diagnostic_summary"],
        ce_shallow_comparison=ce_shallow_comparison,
        report_path=str(report_path),
    )
    (run_root / "tc_family_final_regime_aware_refinement_result.json").write_text(result.as_json() + "\n", encoding="utf-8")
    return result


def _load_ce_shallow_comparison_source_for_final_round(baseline_run_root: Path) -> dict[str, Any]:
    current = Path(baseline_run_root)
    seen: set[str] = set()
    for _ in range(4):
        key = str(current)
        if key in seen:
            break
        seen.add(key)
        try:
            return _load_source_artifacts(current, CE_SHALLOW_COMPARISON_ID)
        except FileNotFoundError:
            next_root = _read_prior_baseline_root(current)
            if next_root is None:
                raise
            current = next_root
    raise FileNotFoundError(f"missing CE shallow source while walking baselines from {baseline_run_root}")


def _read_prior_baseline_root(run_root: Path) -> Path | None:
    for name in (
        "tc_family_cost_aware_refinement_with_trend_state_result.json",
        "tc_family_cost_aware_exit_target_result.json",
        "tc_family_profit_execution_optimization_result.json",
    ):
        path = run_root / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        prior_root = payload.get("baseline_run_root")
        return Path(prior_root) if prior_root else None
    return None


def build_regime_diagnostic_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    enriched_rows = enrich_execution_path_rows(rows)
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in enriched_rows:
        if row.get("row_type") == "closed_trade" and str(row.get("cost_tier") or "base") == "base":
            groups[_state(row)].append(row)
    result: dict[str, dict[str, object]] = {}
    for state, base_rows in sorted(groups.items()):
        all_rows = [row for row in enriched_rows if row.get("row_type") == "closed_trade" and _state(row) == state]
        tier_avg = {
            tier: _avg([_r(row) for row in all_rows if str(row.get("cost_tier") or "base") == tier])
            for tier in ("base", "stress", "harsh")
        }
        net = [_r(row) for row in base_rows]
        wins = [value for value in net if value > 0]
        losses = [value for value in net if value < 0]
        result[state] = {
            "closed": len(base_rows),
            "base_net_R_avg": tier_avg["base"],
            "stress_net_R_avg": tier_avg["stress"],
            "harsh_net_R_avg": tier_avg["harsh"],
            "total_R": sum(net),
            "PF": (sum(wins) / abs(sum(losses))) if losses else None,
            "median_R": _median(net),
            "win_rate": _share(len(wins), len(base_rows)),
            "avg_win_R": _avg(wins),
            "avg_loss_R": _avg(losses),
            "MFE_R_median": _median([_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0 for row in base_rows]),
            "MAE_R_median": _median([_num(row.get("MAE_R")) or _num(row.get("mae_R")) or 0.0 for row in base_rows]),
            "giveback_median": _median([_num(row.get("profit_giveback_R")) or 0.0 for row in base_rows]),
            "cost_per_R_median": _median([_num(row.get("cost_per_R")) or 0.0 for row in base_rows]),
            "target_space_ATR_median": _median([_num(row.get("target_space_ATR")) or _num(row.get("target_space_atr")) or 0.0 for row in base_rows]),
            "nearest_obstacle_distance_ATR_median": _median([_num(row.get("nearest_obstacle_distance_ATR")) or 0.0 for row in base_rows]),
            "positive_MFE_but_final_loss_share": _share(
                sum(1 for row in base_rows if (_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0) > 0 and _r(row) <= 0),
                len(base_rows),
            ),
            "cost_flipped_share": _share(sum(1 for row in base_rows if row.get("cost_flipped_to_loss")), len(base_rows)),
            "MFE_ge_0_5R_share": _share(sum(1 for row in base_rows if (_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0) >= 0.5), len(base_rows)),
            "MFE_ge_1R_share": _share(sum(1 for row in base_rows if (_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0) >= 1.0), len(base_rows)),
            "asset_split": _counts(row.get("asset") or row.get("inst_id") for row in base_rows),
            "profile_split": _counts(row.get("profile") for row in base_rows),
            "direction_split": _counts(row.get("direction") for row in base_rows),
            "harsh_base_degradation": (tier_avg["harsh"] - tier_avg["base"]) if tier_avg["harsh"] is not None and tier_avg["base"] is not None else None,
        }
    return result


def select_final_regime_decision(
    variant_summaries: Mapping[str, Mapping[str, object]],
    *,
    baseline_summary: Mapping[str, object] | None = None,
) -> str:
    best_key, best = max(
        variant_summaries.items(),
        key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0,
        default=("", {}),
    )
    if (
        int(best.get("closed_trades") or 0) >= 350
        and (_num(best.get("base_net_R_avg")) or -999.0) > 0
        and (_num(best.get("stress_net_R_avg")) or -999.0) > 0
        and (_num(best.get("harsh_net_R_avg")) or -999.0) >= 0.015
        and (_num(best.get("median_R")) or -999.0) >= 0
        and (_num(best.get("PF")) or 0.0) > 1.25
        and (_num(best.get("net_R_avg_excluding_top_1")) or -999.0) > 0
        and (_num(best.get("net_R_avg_excluding_top_2")) or -999.0) > 0
        and int(best.get("positive_walk_forward_windows") or 0) >= 4
        and best.get("full_audit_gate") == "passed"
        and best.get("no_lookahead") == "passed"
        and best.get("metric_recompute") == "passed"
        and not best.get("single_dimension_concentration")
        and not best.get("uses_direct_regime_filter")
    ):
        return "A. BP shallow has validation-prep potential; run bounded validation-prep next."
    baseline_harsh = _num((baseline_summary or {}).get("harsh_net_R_avg")) or -999.0
    if best and (_num(best.get("harsh_net_R_avg")) or -999.0) > baseline_harsh and int(best.get("closed_trades") or 0) >= 350:
        return "B. Regime-aware refinement improved edge but still not enough; keep diagnostic only."
    if best_key and (_num(best.get("harsh_net_R_avg")) or -999.0) <= baseline_harsh:
        return "C. Regime-aware rules overfit or overfiltered; revert to v3 baseline."
    if _regime_summary_has_signal((baseline_summary or {}).get("regime_diagnostic_summary")):
        return "D. Trend_state split is informative but not actionable; pause TC refinement."
    return "E. No variant improves enough; pause TC family and move to simple baseline later."


def _run_final_regime_variant(
    *,
    variant_id: str,
    source: Mapping[str, Any],
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_dir: Path,
    cost_tiers: Sequence[str],
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = tuple(dict(row, variant_id=variant_id, source_variant_id=BASELINE_VARIANT_ID) for row in source["candidate_rows"])
    filter_rows = _prepare_filter_rows(source["filter_rows"], variant_id=variant_id)
    if variant_id == "bp_shallow_regime_cost_gate_v1":
        _apply_regime_cost_gate(filter_rows)
    if variant_id == "bp_shallow_regime_diagnostic_no_filter_v1":
        closed_rows = tuple(_copy_closed_variant(row, variant_id) for row in source["closed_rows"])
    else:
        closed_rows = _execute_final_regime_variant(
            variant_id=variant_id,
            repository=repository,
            preset=preset,
            filter_rows=filter_rows,
            cost_tiers=cost_tiers,
        )
    enriched = enrich_execution_path_rows(closed_rows)
    path_summary = summarize_execution_path_rows(enriched)
    variant_diagnostics = _variant_specific_diagnostics(variant_id, enriched, source, filter_rows)
    robustness_rows = _robustness_rows(closed_rows)
    summary_rows = _summary_rows(candidate_rows, filter_rows, closed_rows)
    trend_lineage = build_trend_state_lineage_diagnostics(
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
    )
    diagnostic_rows = (
        *_diagnostic_rows(filter_rows, candidate_rows, closed_rows),
        {
            "row_type": "diagnostic_only",
            "diagnostic_only": True,
            "eligible_for_performance": False,
            "diagnostic_name": "tc_family_final_regime_aware_refinement",
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "path_summary": path_summary,
            "variant_diagnostics": variant_diagnostics,
            "regime_diagnostic_summary": build_regime_diagnostic_summary(closed_rows),
            "trend_state_lineage": trend_lineage,
        },
    )
    review_log_rows = _review_log_rows(
        strategy=family_variant_setup("bp_shallow_momentum_capped_risk_v3"),
        pass_name=variant_id,
        summary_rows=summary_rows,
        diagnostic_rows=diagnostic_rows,
        anatomy_summary=path_summary,
    )
    regression_baseline = _regression_baseline(summary_rows)
    write_jsonl(output_dir / "candidate_rows.jsonl", candidate_rows)
    write_jsonl(output_dir / "filter_results_research.jsonl", filter_rows)
    write_jsonl(output_dir / "closed_trade_rows.jsonl", closed_rows)
    write_jsonl(output_dir / "execution_path_diagnostics.jsonl", enriched)
    write_json(output_dir / "execution_path_summary.json", path_summary)
    write_json(output_dir / "variant_diagnostics.json", variant_diagnostics)
    write_json(output_dir / "regime_diagnostic_summary.json", build_regime_diagnostic_summary(closed_rows))
    write_json(output_dir / "trend_state_lineage_diagnostics.json", trend_lineage)
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_log_rows)
    write_json(output_dir / "regression_baseline.json", regression_baseline)
    setup = family_variant_setup("bp_shallow_momentum_capped_risk_v3")
    manifest = RunManifest(
        run_id=stable_fingerprint({"variant_id": variant_id, "output_dir": str(output_dir)})[:24],
        strategy=setup,
        adapter_version=f"tc_family_final_regime_aware_refinement.v1+{CORE_ENGINE_VERSION}",
        dataset_window=dataset_window,
        artifact_contract=_family_artifact_contract().as_dict(),
        audit_profile=family_audit_profile("bp_shallow_momentum_capped_risk_v3").as_dict(),
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
            "regime_diagnostic_summary": str(output_dir / "regime_diagnostic_summary.json"),
            "trend_state_lineage_diagnostics": str(output_dir / "trend_state_lineage_diagnostics.json"),
        },
        config_snapshot={
            "config_version": preset.config_version,
            "config_fingerprint": preset.config_fingerprint,
            "setup_filter": [setup],
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "sizing_policy": "capped_risk_sizing_proposal_only",
            "exit_policy": _exit_policy_name(variant_id),
            "trend_state_policy": "diagnostic_and_proposal_routing_only",
        },
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="TC family final regime-aware refinement; proposal-only shadow replay.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=setup,
        stage=f"tc_family_final_regime_aware_refinement_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-final-regime-aware-refinement",
        config_hash=preset.config_fingerprint,
        notes="Proposal-only TC family final regime-aware refinement; LR final evidence untouched.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=setup,
        stage=f"tc_family_final_regime_aware_refinement_{variant_id}",
        window=dataset_window,
        source_command="research_pipeline.cli.research tc-family-final-regime-aware-refinement",
        adapter_version=manifest.adapter_version,
        baseline_ref=str(source["variant_dir"]),
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        config_hash=preset.config_fingerprint,
        notes="Proposal-only final regime-aware refinement.",
        tags=["tc_family", variant_id, "regime"],
    )
    audit = run_full_pipeline_audit(strategy=setup, artifact_dir=output_dir, registry=None, output_dir=output_dir / "full_audit")
    summary = _variant_summary(
        variant_id="bp_shallow_momentum_capped_risk_v3",
        cache_status={"reused": True, "baseline_ref": str(source["variant_dir"])},
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
        robustness_rows=robustness_rows,
        audit=audit,
    )
    summary.update(
        {
            "variant_id": variant_id,
            "source_variant_id": BASELINE_VARIANT_ID,
            "setup_id": setup,
            "path_diagnostics": path_summary,
            "variant_diagnostics": variant_diagnostics,
            "regime_diagnostic_summary": build_regime_diagnostic_summary(closed_rows),
            "retained_removed_comparison": variant_diagnostics.get("retained_removed_comparison", {}),
            "trend_state_lineage": trend_lineage,
            "trend_state_split": _base_trend_state_split(closed_rows),
            "trend_state_metrics": build_regime_diagnostic_summary(closed_rows),
            "interpretation": _interpret_variant(variant_id, summary, path_summary, variant_diagnostics),
            "single_dimension_concentration": _single_dimension_concentration(summary),
            "uses_direct_regime_filter": False,
        }
    )
    write_json(output_dir / "variant_summary.json", summary)
    return summary


def _execute_final_regime_variant(
    *,
    variant_id: str,
    repository,
    preset: BacktestPresetConfig,
    filter_rows: list[dict[str, object]],
    cost_tiers: Sequence[str],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    scheduling_tier = "base" if "base" in cost_tiers else str(cost_tiers[0])
    accepted_ids: set[str] = set()
    open_intervals: list[tuple[int, int, float]] = []
    ordered = sorted(filter_rows, key=lambda row: (int(row.get("timestamp_ms") or 0), str(row.get("candidate_id") or "")))
    for candidate in ordered:
        if not candidate.get("proposal_approved_after_cap"):
            candidate["proposal_execution_status"] = "not_approved_after_cap"
            continue
        closed, reject = _simulate_final_candidate(
            repository=repository,
            candidate=candidate,
            tier_preset=_cost_tier_preset_final(preset, scheduling_tier, variant_id, candidate),
            tier_name=scheduling_tier,
            variant_id=variant_id,
        )
        if closed is None:
            candidate["proposal_execution_status"] = "not_executed"
            candidate["proposal_execution_reject_reason"] = reject
            continue
        if not _portfolio_heat_allows(
            open_intervals,
            entry_time=int(closed["entry_time"]),
            exit_time=int(closed["exit_time"]),
            risk_pct=float(closed["actual_risk_after_cap_pct"]),
            max_heat_pct=preset.risk.max_portfolio_heat_pct,
        ):
            candidate["proposal_approved_after_cap"] = False
            candidate["approved_after_cap"] = False
            candidate["risk_reject_reason_after_cap"] = "portfolio_heat_exceeded_after_cap"
            candidate["proposal_execution_status"] = "not_executed"
            candidate["proposal_execution_reject_reason"] = "portfolio_heat_exceeded_after_cap"
            continue
        accepted_ids.add(str(candidate.get("candidate_id") or ""))
        open_intervals.append((int(closed["entry_time"]), int(closed["exit_time"]), float(closed["actual_risk_after_cap_pct"])))
        candidate["proposal_execution_status"] = "closed"
        candidate["proposal_execution_reject_reason"] = ""
        rows.append(closed)
    for tier_name in cost_tiers:
        if tier_name == scheduling_tier:
            continue
        for candidate in ordered:
            if str(candidate.get("candidate_id") or "") not in accepted_ids:
                continue
            closed, _ = _simulate_final_candidate(
                repository=repository,
                candidate=candidate,
                tier_preset=_cost_tier_preset_final(preset, tier_name, variant_id, candidate),
                tier_name=tier_name,
                variant_id=variant_id,
            )
            if closed is not None:
                rows.append(closed)
    return tuple(rows)


def _simulate_final_candidate(
    *,
    repository,
    candidate: Mapping[str, object],
    tier_preset: BacktestPresetConfig,
    tier_name: str,
    variant_id: str,
) -> tuple[dict[str, object] | None, str]:
    closed, reject = _simulate_capped_candidate(repository=repository, candidate=candidate, tier_preset=tier_preset, tier_name=tier_name)
    if closed is not None:
        closed["variant_id"] = variant_id
        closed["source_variant_id"] = BASELINE_VARIANT_ID
        closed["exit_policy"] = _exit_policy_name(variant_id)
        closed["regime_policy"] = _regime_policy_name(variant_id, _state(candidate))
        _copy_trend_state(candidate, closed)
    return closed, reject


def _cost_tier_preset_final(
    preset: BacktestPresetConfig,
    tier_name: str,
    variant_id: str,
    candidate: Mapping[str, object],
) -> BacktestPresetConfig:
    tier = _tier_preset(preset, tier_name)
    if variant_id != "bp_shallow_regime_adaptive_exit_v1":
        return tier
    state = _state(candidate)
    if state != "MEAN_REVERTING_TRANSITION":
        return tier
    execution = replace(
        tier.execution,
        enable_advanced_exits=True,
        partial_take_profit_r=0.5,
        partial_take_profit_pct=0.35,
        move_stop_to_true_breakeven=True,
        breakeven_after_mfe_r=0.5,
        chandelier_period=5,
        chandelier_atr_multiple=2.5,
    )
    return replace(tier, execution=execution)


def _prepare_filter_rows(rows: Sequence[Mapping[str, object]], *, variant_id: str) -> list[dict[str, object]]:
    prepared = []
    for row in rows:
        payload = dict(row)
        payload["source_variant_id"] = payload.get("variant_id")
        payload["variant_id"] = variant_id
        payload["optimization_variant"] = variant_id
        payload["proposal_only"] = True
        payload["formal_conclusion_enabled"] = False
        prepared.append(payload)
    return prepared


def _apply_regime_cost_gate(filter_rows: list[dict[str, object]]) -> None:
    eligible = [
        row
        for row in filter_rows
        if row.get("proposal_approved_after_cap") and _state(row) == "MEAN_REVERTING_TRANSITION"
    ]
    scores = []
    for row in eligible:
        score = _regime_cost_score(row)
        row["regime_cost_gate_score"] = score
        scores.append(score)
    if not scores:
        return
    threshold = sorted(scores)[max(0, int(len(scores) * 0.14) - 1)]
    for row in eligible:
        if float(row.get("regime_cost_gate_score") or 0.0) <= threshold:
            row["proposal_approved_after_cap"] = False
            row["approved_after_cap"] = False
            row["removed_by_regime_cost_gate"] = True
            row["risk_reject_reason_after_cap"] = "regime_cost_gate_mean_reverting_transition_low_edge"
            row["reject_reason"] = "regime_cost_gate_mean_reverting_transition_low_edge"
        else:
            row["retained_by_regime_cost_gate"] = True


def _regime_cost_score(row: Mapping[str, object]) -> float:
    base = _cost_aware_score(row)
    cost = _num(row.get("cost_per_R")) or 0.0
    target = _num(row.get("target_space_ATR")) or _num(row.get("target_space_atr")) or 0.0
    obstacle = _num(row.get("nearest_obstacle_distance_ATR")) or target
    cost_adjusted = _num(row.get("cost_adjusted_RR")) or 0.0
    return base + min(target / 3.0, 0.25) + min(obstacle / 2.0, 0.20) + min(cost_adjusted / 2.0, 0.20) - min(cost / 0.30, 0.20)


def _variant_specific_diagnostics(
    variant_id: str,
    enriched: Sequence[Mapping[str, object]],
    source: Mapping[str, Any],
    filter_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    closed = [row for row in enriched if row.get("row_type") == "closed_trade"]
    if variant_id == "bp_shallow_regime_diagnostic_no_filter_v1":
        return {
            "diagnostic_policy": "no trade changes; v3 replay with regime diagnostics",
            "regime_diagnostic_summary": build_regime_diagnostic_summary(closed),
        }
    if variant_id == "bp_shallow_regime_adaptive_exit_v1":
        triggered = [row for row in closed if row.get("partial_take_profit_hit")]
        return {
            "exit_policy": "MEAN_REVERTING_TRANSITION uses 0.50R partial 35% + breakeven + loose trailing; other regimes keep v3 exits",
            "capture_trigger_count_by_regime": _counts(_state(row) for row in triggered),
            "final_loss_after_capture_by_regime": _counts(_state(row) for row in triggered if _r(row) <= 0),
            "MFE_ge_1R_capture_count": sum(1 for row in triggered if (_num(row.get("MFE_R")) or _num(row.get("mfe_R")) or 0.0) >= 1.0),
        }
    if variant_id == "bp_shallow_regime_cost_gate_v1":
        retained_ids = {str(row.get("candidate_id") or "") for row in filter_rows if row.get("proposal_approved_after_cap")}
        baseline = []
        for row in source["closed_rows"]:
            payload = dict(row)
            if _state(payload) == "MEAN_REVERTING_TRANSITION" and str(payload.get("candidate_id") or "") not in retained_ids:
                payload["removed_by_admission"] = True
            else:
                payload["retained_by_admission"] = True
            baseline.append(payload)
        comparison = compare_retained_removed_rows(enrich_execution_path_rows(baseline))
        comparison.update(_target_space_comparison(baseline))
        return {
            "cost_gate_policy": "tighten cost/space score only for MEAN_REVERTING_TRANSITION; no direct regime deletion",
            "retained_removed_comparison": comparison,
            "retained_removed_by_regime": {
                "retained": _counts(_state(row) for row in filter_rows if row.get("proposal_approved_after_cap")),
                "removed": _counts(_state(row) for row in filter_rows if row.get("removed_by_regime_cost_gate")),
            },
        }
    return {}


def _target_space_comparison(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    retained = [row for row in rows if row.get("retained_by_admission")]
    removed = [row for row in rows if row.get("removed_by_admission")]
    return {
        "retained_target_space_ATR": _median([_num(row.get("target_space_ATR")) or _num(row.get("target_space_atr")) or 0.0 for row in retained]),
        "removed_target_space_ATR": _median([_num(row.get("target_space_ATR")) or _num(row.get("target_space_atr")) or 0.0 for row in removed]),
    }


def _copy_closed_variant(row: Mapping[str, object], variant_id: str) -> dict[str, object]:
    payload = dict(row)
    payload["variant_id"] = variant_id
    payload["source_variant_id"] = BASELINE_VARIANT_ID
    payload["exit_policy"] = _exit_policy_name(variant_id)
    payload["regime_policy"] = _regime_policy_name(variant_id, _state(payload))
    return payload


def _base_trend_state_split(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return dict(
        Counter(
            _state(row)
            for row in rows
            if row.get("row_type") == "closed_trade" and str(row.get("cost_tier") or "base") == "base"
        )
    )


def _exit_policy_name(variant_id: str) -> str:
    if variant_id == "bp_shallow_regime_adaptive_exit_v1":
        return "proposal_regime_adaptive_exit_mrt_0_50r_partial"
    if variant_id == "bp_shallow_regime_cost_gate_v1":
        return "proposal_v3_exit_with_regime_cost_gate"
    return "proposal_v3_exit_no_filter_regime_diagnostic"


def _regime_policy_name(variant_id: str, state: str) -> str:
    if variant_id == "bp_shallow_regime_adaptive_exit_v1" and state == "MEAN_REVERTING_TRANSITION":
        return "mrt_partial_capture_0_50r_35pct"
    if variant_id == "bp_shallow_regime_cost_gate_v1" and state == "MEAN_REVERTING_TRANSITION":
        return "mrt_cost_gate_tightened"
    return "v3_default_policy"


def _interpret_variant(
    variant_id: str,
    summary: Mapping[str, object],
    path: Mapping[str, object],
    diagnostics: Mapping[str, object],
) -> str:
    return (
        f"{variant_id}: closed={summary.get('closed_trades')}, "
        f"base/stress/harsh={summary.get('base_net_R_avg')}/{summary.get('stress_net_R_avg')}/{summary.get('harsh_net_R_avg')}, "
        f"median_R={summary.get('median_R')}, MFE_median={path.get('MFE_R_median')}, diagnostics={diagnostics}."
    )


def _regime_interpretation(regimes: Mapping[str, Mapping[str, object]]) -> str:
    strong = [
        state
        for state, row in regimes.items()
        if int(row.get("closed") or 0) >= 20 and (_num(row.get("harsh_net_R_avg")) or -999.0) > 0
    ]
    weak = [
        state
        for state, row in regimes.items()
        if int(row.get("closed") or 0) >= 20 and (_num(row.get("harsh_net_R_avg")) or -999.0) <= 0
    ]
    return f"Diagnostic only: stronger harsh regimes={strong}; thin/drag regimes={weak}. No regime was directly removed."


def _decision_reason(decision: str, baseline: Mapping[str, object], variants: Mapping[str, object]) -> str:
    best_key, best = max(variants.items(), key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0, default=("", {}))
    return (
        f"Baseline v3 harsh={baseline.get('harsh_net_R_avg')}; best regime-aware variant is {best_key} "
        f"with harsh={best.get('harsh_net_R_avg')}. Decision follows fixed thresholds."
    )


def _executive_summary(decision: str, baseline: Mapping[str, object], variants: Mapping[str, object]) -> str:
    best_key, best = max(variants.items(), key=lambda item: _num(item[1].get("harsh_net_R_avg")) or -999.0, default=("", {}))
    return (
        f"best={best_key}, harsh={best.get('harsh_net_R_avg')}, baseline_v3_harsh={baseline.get('harsh_net_R_avg')}; {decision}"
    )


def _next_actions(decision: str) -> tuple[str, ...]:
    if decision.startswith("A."):
        return ("Run bounded validation-prep on BP shallow regime-aware path only.", "Add read-only LR complementarity comparison.")
    if decision.startswith("B."):
        return ("Keep BP shallow diagnostic-only; document the regime-aware mechanism as promising but not validation-ready.",)
    if decision.startswith("C."):
        return ("Revert to v3 as the current diagnostic best; stop regime-aware refinement.",)
    if decision.startswith("D."):
        return ("Pause TC refinement; retain trend_state split as diagnostic evidence only.",)
    return ("Pause TC family and consider a simple support/resistance fixed-RR baseline later.",)


def _regime_summary_has_signal(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return any(
        isinstance(row, Mapping) and int(row.get("closed") or 0) >= 20 and (_num(row.get("harsh_net_R_avg")) or -999.0) > 0
        for row in value.values()
    )


def _state(row: Mapping[str, object]) -> str:
    value = row.get("trend_state_at_entry") or row.get("trend_state")
    return "unknown" if value in (None, "", "unknown", "UNKNOWN") else str(value)


def _r(row: Mapping[str, object]) -> float:
    return _num(row.get("net_R")) or _num(row.get("final_R")) or 0.0


def _counts(values) -> dict[str, int]:
    return dict(Counter(str(value) for value in values if value not in (None, "")))


def _avg(values: Sequence[float | None]) -> float | None:
    nums = [float(value) for value in values if value is not None]
    return None if not nums else sum(nums) / len(nums)


def _median(values: Sequence[float | None]) -> float | None:
    nums = sorted(float(value) for value in values if value is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    return nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2


def _share(count: int, total: int) -> float:
    return 0.0 if total <= 0 else count / total


__all__ = (
    "BASELINE_VARIANT_ID",
    "FINAL_REGIME_VARIANT_IDS",
    "TcFamilyFinalRegimeAwareRefinementResult",
    "build_regime_diagnostic_summary",
    "run_tc_family_final_regime_aware_refinement",
    "select_final_regime_decision",
)
