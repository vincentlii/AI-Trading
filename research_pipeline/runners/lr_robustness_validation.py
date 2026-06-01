from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.lr_combined_candidate_fix import VARIANT_COMBOS, _select_variant_rows
from research_pipeline.runners.register_research_run import register_research_run


RECOMMENDED_VARIANT = "Variant B - Tier 1 + Positive Tier 2"
TIER1_VARIANT = "Variant A - Tier 1 only"
FULL_REFERENCE_VARIANT = "Variant C - Full original family"
BEST_SINGLE_COMBO = "T1_session_hl_attempt4_fixed_current"
BASELINE_LABEL = "LR v1 baseline"
MONTE_CARLO_SEEDS = 1000


@dataclass(frozen=True)
class LRRobustnessValidationResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    primary_decision: str
    next_pr_recommendation: str
    preflight_passed: bool
    blocking_issues: list[str]
    non_blocking_warnings: list[str]
    recommended_variant: str
    control_variants: list[str]
    cost_stress_summary: list[dict[str, Any]]
    walk_forward_summary: list[dict[str, Any]]
    regime_summary: list[dict[str, Any]]
    monte_carlo_summary: dict[str, Any]
    execution_audit_summary: list[dict[str, Any]]
    portfolio_heat_summary: list[dict[str, Any]]
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_lr_robustness_validation(
    *,
    artifact_dir: Path,
    output_dir: Path | None,
    monte_carlo_seeds: int = MONTE_CARLO_SEEDS,
) -> LRRobustnessValidationResult:
    artifact_dir = Path(artifact_dir)
    clean_root = artifact_dir.parent
    combo_rows = _read_jsonl(artifact_dir / "lr_combined_combo_rows.jsonl")
    full_audit = _read_optional_json(clean_root / "full_audit" / "full_pipeline_audit_result.json")
    filter_rows = _read_optional_jsonl(clean_root / "minimal_lr_v0_filter" / "10000w" / "minimal_lr_v0_filter_results.jsonl")
    execution_rows = _read_optional_jsonl(
        clean_root / "minimal_lr_v0_filter" / "10000w" / "minimal_lr_v0_execution_results.jsonl"
    )

    feature_by_candidate = {str(row.get("candidate_id")): row for row in filter_rows}
    variant_rows = _build_variant_rows(combo_rows)
    recommended_rows = variant_rows[RECOMMENDED_VARIANT]
    tier1_rows = variant_rows[TIER1_VARIANT]
    full_reference_rows = variant_rows[FULL_REFERENCE_VARIANT]
    best_single_rows = [
        row for row in combo_rows if row.get("combo_name") == BEST_SINGLE_COMBO and row.get("closed_trade")
    ]
    baseline_rows = [_normalize_baseline_execution_row(row) for row in execution_rows if row.get("row_type") == "closed_trade"]

    preflight_rows, blocking_issues, warnings = _preflight_rows(
        full_audit=full_audit,
        recommended_rows=recommended_rows,
        all_selected_rows=variant_rows[RECOMMENDED_VARIANT],
    )
    preflight_passed = not blocking_issues

    cost_stress_rows: list[dict[str, Any]] = []
    if preflight_passed:
        cost_stress_rows.extend(_cost_stress_rows("Variant B - Tier 1 + Positive Tier 2", recommended_rows))
        cost_stress_rows.extend(_cost_stress_rows("Variant A - Tier 1 only", tier1_rows))
        cost_stress_rows.extend(_cost_stress_rows("Best single: Session_HL + attempt_4", best_single_rows))
        cost_stress_rows.extend(_cost_stress_rows(BASELINE_LABEL, baseline_rows))
        cost_stress_rows.extend(_cost_stress_rows("Variant C full original family reference", full_reference_rows))
        robustness_base_rows = _closed_rows(recommended_rows, cost_tier="base")
    else:
        robustness_base_rows = []

    enriched_base_rows = [_enrich_row(row, feature_by_candidate) for row in robustness_base_rows]
    walk_forward_rows = _walk_forward_rows(enriched_base_rows) if preflight_passed else []
    regime_rows = _regime_rows(enriched_base_rows) if preflight_passed else []
    monte_carlo_rows, monte_carlo_summary = (
        _monte_carlo_rows(enriched_base_rows, monte_carlo_seeds) if preflight_passed else ([], {})
    )
    execution_audit_rows = _execution_audit_rows(
        recommended_rows=recommended_rows,
        full_audit=full_audit,
        preflight_rows=preflight_rows,
    )
    portfolio_heat_rows = _portfolio_heat_rows(enriched_base_rows) if preflight_passed else []

    primary_decision = _primary_decision(
        preflight_passed=preflight_passed,
        cost_stress_rows=cost_stress_rows,
        walk_forward_rows=walk_forward_rows,
        monte_carlo_summary=monte_carlo_summary,
        portfolio_heat_rows=portfolio_heat_rows,
    )
    result = LRRobustnessValidationResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        primary_decision=primary_decision,
        next_pr_recommendation="PR12 formalization / cleanup / merge preparation"
        if primary_decision in {"A", "B"}
        else _fix_recommendation(primary_decision),
        preflight_passed=preflight_passed,
        blocking_issues=blocking_issues,
        non_blocking_warnings=warnings,
        recommended_variant=RECOMMENDED_VARIANT,
        control_variants=[TIER1_VARIANT, "Best single: Session_HL + attempt_4", BASELINE_LABEL, FULL_REFERENCE_VARIANT],
        cost_stress_summary=[row for row in cost_stress_rows if row["scope"] == RECOMMENDED_VARIANT],
        walk_forward_summary=walk_forward_rows,
        regime_summary=regime_rows,
        monte_carlo_summary=monte_carlo_summary,
        execution_audit_summary=execution_audit_rows,
        portfolio_heat_summary=portfolio_heat_rows,
        source_files=[str(artifact_dir / "lr_combined_combo_rows.jsonl")],
    )
    if output_dir is not None:
        _write_outputs(
            result=result,
            output_dir=Path(output_dir),
            preflight_rows=preflight_rows,
            walk_forward_rows=walk_forward_rows,
            regime_rows=regime_rows,
            monte_carlo_rows=monte_carlo_rows,
            cost_stress_rows=cost_stress_rows,
            execution_audit_rows=execution_audit_rows,
            portfolio_heat_rows=portfolio_heat_rows,
            artifact_dir=artifact_dir,
        )
    return result


def _build_variant_rows(combo_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        variant_name: _select_variant_rows(combo_rows, combo_names)[0]
        for variant_name, combo_names in VARIANT_COMBOS.items()
    }


def _preflight_rows(
    *,
    full_audit: dict[str, Any],
    recommended_rows: list[dict[str, Any]],
    all_selected_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    closed = _closed_rows(recommended_rows, cost_tier="base")
    selected_without_closed = [row for row in all_selected_rows if row.get("cost_tier") == "base" and not row.get("closed_trade")]
    checks = [
        (
            "full_audit_passed",
            bool(full_audit.get("audit_passed")) and not full_audit.get("blocking_issues"),
            "clean rebuild full-audit must pass before robustness",
            True,
        ),
        (
            "selected_without_closed_excluded_from_performance",
            all(not row.get("eligible_for_performance") for row in selected_without_closed),
            "proposal_only_unexecuted rows may exist only outside performance",
            True,
        ),
        (
            "performance_only_closed_trade",
            all(row.get("row_type") == "closed_trade" and row.get("closed_trade") for row in closed),
            "performance source rows must be closed_trade",
            True,
        ),
        (
            "trade_id_complete",
            all(row.get("trade_id") for row in closed),
            "recommended robustness rows need trade_id",
            True,
        ),
        (
            "execution_id_complete",
            all(row.get("execution_id") for row in closed),
            "recommended robustness rows need execution_id",
            True,
        ),
        (
            "candidate_event_traceable",
            all(row.get("candidate_id") and row.get("event_id") for row in closed),
            "recommended robustness rows need candidate_id and event_id",
            True,
        ),
        (
            "entry_time_lte_exit_time",
            all(_float(row.get("entry_time")) is not None and _float(row.get("exit_time")) is not None and _float(row.get("entry_time")) <= _float(row.get("exit_time")) for row in closed),
            "entry_time <= exit_time must be verifiable",
            True,
        ),
        (
            "no_lookahead_safe",
            all(row.get("bar_confirmed") is True and row.get("no_lookahead_safe") is True for row in closed),
            "recommended rows must be bar_confirmed and no_lookahead_safe",
            True,
        ),
        (
            "proposal_boundary_clean",
            not any(row.get("row_type") != "closed_trade" and row.get("eligible_for_performance") for row in all_selected_rows),
            "proposal / diagnostic / summary rows cannot enter performance",
            True,
        ),
    ]
    rows: list[dict[str, Any]] = []
    blocking: list[str] = []
    warnings: list[str] = []
    for name, passed, details, blocking_check in checks:
        row = {
            "check_name": name,
            "passed": bool(passed),
            "blocking": bool(blocking_check),
            "checked_rows": len(closed),
            "selected_without_closed_count": len(selected_without_closed),
            "details": details,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
        rows.append(row)
        if not passed and blocking_check:
            blocking.append(f"{name}: {details}")
        elif not passed:
            warnings.append(f"{name}: {details}")
    warnings.extend(list(full_audit.get("non_blocking_warnings") or []))
    return rows, blocking, warnings


def _cost_stress_rows(scope: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    tier_penalties = {"base": 0.0, "stress": 0.05, "harsh": 0.12}
    base_rows = _closed_rows(rows, cost_tier="base")
    for tier, penalty in tier_penalties.items():
        tier_rows = _closed_rows(rows, cost_tier=tier)
        if not tier_rows and tier != "base":
            tier_rows = [_with_cost_penalty(row, tier, penalty) for row in base_rows]
        out.append({"scope": scope, "cost_tier": tier, **_metrics(tier_rows)})
    extreme_rows = [_with_extreme_cost(row) for row in base_rows]
    out.append({"scope": scope, "cost_tier": "extreme_harsh", **_metrics(extreme_rows)})
    return out


def _walk_forward_rows(rows: list[dict[str, Any]], windows: int = 5) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda row: (_float(row.get("entry_time")) or 0.0, str(row.get("trade_id"))))
    if not sorted_rows:
        return []
    out: list[dict[str, Any]] = []
    for idx in range(windows):
        start = round(idx * len(sorted_rows) / windows)
        end = round((idx + 1) * len(sorted_rows) / windows)
        chunk = sorted_rows[start:end]
        metrics = _metrics(chunk)
        out.append(
            {
                "window_index": idx + 1,
                "window_count": windows,
                "start_entry_time": min((row.get("entry_time") for row in chunk), default=None),
                "end_entry_time": max((row.get("entry_time") for row in chunk), default=None),
                **metrics,
                "asset_distribution": dict(Counter(str(row.get("asset")) for row in chunk)),
                "profile_distribution": dict(Counter(str(row.get("profile")) for row in chunk)),
                "direction_distribution": dict(Counter(str(row.get("direction")) for row in chunk)),
                "proposal_only": True,
                "formal_conclusion_enabled": False,
            }
        )
    return out


def _regime_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    splitters = {
        "volatility": lambda row: _high_low(row.get("stop_atr"), rows, "stop_atr", "high_volatility", "low_volatility"),
        "trend_regime": _trend_bucket,
        "rvol": lambda row: _high_low(row.get("sweep_rvol"), rows, "sweep_rvol", "high_RVOL", "low_RVOL"),
        "funding": lambda row: "funding_positive" if (_float(row.get("funding_rate")) or 0.0) >= 0 else "funding_negative",
        "session": lambda row: str(row.get("session_name") or _session_from_hour(row.get("utc_hour"))),
        "asset": lambda row: str(row.get("asset")),
        "profile": lambda row: str(row.get("profile")),
        "direction": lambda row: str(row.get("direction")),
    }
    out: list[dict[str, Any]] = []
    for split_name, splitter in splitters.items():
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            buckets.setdefault(splitter(row), []).append(row)
        for bucket, bucket_rows in sorted(buckets.items()):
            out.append(
                {
                    "split": split_name,
                    "bucket": bucket,
                    **_metrics(bucket_rows),
                    "proposal_only": True,
                    "formal_conclusion_enabled": False,
                }
            )
    return out


def _monte_carlo_rows(rows: list[dict[str, Any]], seeds: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    values = [_float(row.get("net_R")) or 0.0 for row in rows]
    out: list[dict[str, Any]] = []
    if not values:
        return out, {}
    for seed in range(seeds):
        rng = random.Random(seed)
        sample = [values[rng.randrange(len(values))] for _ in values]
        rng.shuffle(sample)
        max_dd = _max_drawdown(sample)
        row = {
            "seed": seed,
            "closed_trades": len(sample),
            "final_total_R": sum(sample),
            "max_drawdown": max_dd,
            "longest_losing_streak": _max_consecutive_losses(sample),
            "ruin_like": sum(sample) <= 0 or max_dd >= 25.0,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
        out.append(row)
    totals = [row["final_total_R"] for row in out]
    drawdowns = [row["max_drawdown"] for row in out]
    streaks = [row["longest_losing_streak"] for row in out]
    summary = {
        "seeds": seeds,
        "final_total_R_p5": _percentile(totals, 5),
        "final_total_R_median": _percentile(totals, 50),
        "final_total_R_p95": _percentile(totals, 95),
        "max_drawdown_p5": _percentile(drawdowns, 5),
        "max_drawdown_median": _percentile(drawdowns, 50),
        "max_drawdown_p95": _percentile(drawdowns, 95),
        "longest_losing_streak_p5": _percentile(streaks, 5),
        "longest_losing_streak_median": _percentile(streaks, 50),
        "longest_losing_streak_p95": _percentile(streaks, 95),
        "ruin_like_scenario_count": sum(1 for row in out if row["ruin_like"]),
    }
    return out, summary


def _execution_audit_rows(
    *,
    recommended_rows: list[dict[str, Any]],
    full_audit: dict[str, Any],
    preflight_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    base_closed = _closed_rows(recommended_rows, cost_tier="base")
    selected_without_closed = [row for row in recommended_rows if row.get("cost_tier") == "base" and not row.get("closed_trade")]
    variant_join = next(
        (
            row
            for row in full_audit.get("join_integrity_rows", [])
            if row.get("scope") == RECOMMENDED_VARIANT
        ),
        {},
    )
    return [
        {
            "scope": RECOMMENDED_VARIANT,
            "closed_trades": len(base_closed),
            "same_bar_ambiguous_count": sum(1 for row in base_closed if row.get("same_bar_ambiguous")),
            "forced_pessimistic_exit_count": sum(1 for row in base_closed if row.get("forced_pessimistic_exit")),
            "entry_and_exit_same_bar_count": sum(1 for row in base_closed if row.get("entry_time") == row.get("exit_time")),
            "slippage_cost": sum(_float(row.get("slippage_cost")) or 0.0 for row in base_closed),
            "fee_cost": sum(_float(row.get("fee_cost")) or 0.0 for row in base_closed),
            "funding_cost": sum(_float(row.get("funding_cost")) or 0.0 for row in base_closed),
            "missing_execution_row_count": variant_join.get("missing_execution_row_count", 0),
            "proposal_only_unexecuted_count": variant_join.get("proposal_only_unexecuted_count", len(selected_without_closed)),
            "selected_without_closed_count": variant_join.get("selected_without_closed_count", len(selected_without_closed)),
            "excluded_from_performance": all(not row.get("eligible_for_performance") for row in selected_without_closed),
            "preflight_passed": all(row["passed"] for row in preflight_rows),
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
    ]


def _portfolio_heat_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    duplicate_event_count = len(rows) - len({(row.get("event_id"), row.get("direction")) for row in rows})
    overlapping_pairs = _overlapping_pairs(rows)
    distributions = {
        "asset_distribution": dict(Counter(str(row.get("asset")) for row in rows)),
        "profile_distribution": dict(Counter(str(row.get("profile")) for row in rows)),
        "direction_distribution": dict(Counter(str(row.get("direction")) for row in rows)),
    }
    concentration = _concentration_flags(distributions)
    return [
        {
            "scope": RECOMMENDED_VARIANT,
            "closed_trades": len(rows),
            "duplicate_event_count": duplicate_event_count,
            "overlapping_positions": overlapping_pairs,
            "same_direction_overlap_count": _same_direction_overlaps(rows),
            "max_concurrent_positions": _max_concurrent_positions(rows),
            "single_trade_portfolio_heat_max": _max(_float(row.get("portfolio_heat")) for row in rows),
            "portfolio_heat_max": _max_concurrent_heat(rows),
            "margin_required_max": _max(_float(row.get("margin_required")) for row in rows),
            "notional_to_equity_pct_p50": _percentile([_float(row.get("notional_to_equity_pct")) for row in rows], 50),
            "notional_to_equity_pct_p90": _percentile([_float(row.get("notional_to_equity_pct")) for row in rows], 90),
            "liquidation_event_count": sum(1 for row in rows if row.get("liquidation_event")),
            **distributions,
            "concentration_flags": concentration,
            "has_concentration_risk": bool(concentration),
            "proposal_only": True,
            "formal_conclusion_enabled": False,
        }
    ]


def _concentration_flags(distributions: dict[str, dict[str, int]], threshold: float = 0.85) -> list[str]:
    flags: list[str] = []
    for name, distribution in distributions.items():
        total = sum(distribution.values())
        if not total:
            continue
        top_key, top_count = max(distribution.items(), key=lambda item: item[1])
        ratio = top_count / total
        if ratio >= threshold:
            flags.append(f"{name}:{top_key}:{ratio:.4f}")
    return flags


def _primary_decision(
    *,
    preflight_passed: bool,
    cost_stress_rows: list[dict[str, Any]],
    walk_forward_rows: list[dict[str, Any]],
    monte_carlo_summary: dict[str, Any],
    portfolio_heat_rows: list[dict[str, Any]],
) -> str:
    if not preflight_passed:
        return "E"
    variant_b = {row["cost_tier"]: row for row in cost_stress_rows if row["scope"] == RECOMMENDED_VARIANT}
    base = variant_b.get("base", {})
    stress = variant_b.get("stress", {})
    harsh = variant_b.get("harsh", {})
    windows_positive = sum(1 for row in walk_forward_rows if (_float(row.get("total_net_R")) or 0.0) > 0)
    heat = portfolio_heat_rows[0] if portfolio_heat_rows else {}
    if (
        (_float(base.get("net_R_avg")) or 0.0) > 0
        and (_float(stress.get("net_R_avg")) or 0.0) > 0
        and (_float(harsh.get("profit_factor")) or 0.0) > 1.0
        and windows_positive >= max(1, len(walk_forward_rows) // 2 + 1)
        and (heat.get("duplicate_event_count") or 0) == 0
        and (heat.get("liquidation_event_count") or 0) == 0
        and (monte_carlo_summary.get("ruin_like_scenario_count") or 0) == 0
    ):
        if heat.get("has_concentration_risk") or (heat.get("same_direction_overlap_count") or 0) > 0:
            return "C"
        return "A"
    return "C"


def _fix_recommendation(primary_decision: str) -> str:
    if primary_decision == "C":
        return "PR11H-fix"
    if primary_decision == "D":
        return "PR11G-Rebuild / combined pruning"
    if primary_decision == "E":
        return "PR11H-fix"
    return "module-specific rebuild"


def _closed_rows(rows: list[dict[str, Any]], *, cost_tier: str | None = None) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("row_type") == "closed_trade"
        and row.get("closed_trade")
        and row.get("eligible_for_performance") is True
        and not row.get("invalid_for_robustness")
        and (cost_tier is None or row.get("cost_tier") == cost_tier)
    ]


def _normalize_baseline_execution_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("cost_tier", "base")
    normalized.setdefault("combo_name", BASELINE_LABEL)
    normalized.setdefault("tier", "baseline")
    normalized.setdefault("eligible_for_performance", True)
    normalized.setdefault("eligible_for_robustness", True)
    normalized.setdefault("invalid_for_robustness", False)
    normalized.setdefault("closed_trade", True)
    normalized.setdefault("row_type", "closed_trade")
    normalized.setdefault("net_R", row.get("net_R") if row.get("net_R") is not None else row.get("net_r"))
    normalized.setdefault("mfe_R", row.get("mfe_R") if row.get("mfe_R") is not None else row.get("MFE_R"))
    normalized.setdefault("mae_R", row.get("mae_R") if row.get("mae_R") is not None else row.get("MAE_R"))
    return normalized


def _with_extreme_cost(row: dict[str, Any]) -> dict[str, Any]:
    return _with_cost_penalty(row, "extreme_harsh", 0.20, slippage_penalty=0.14, funding_penalty=0.06)


def _with_cost_penalty(
    row: dict[str, Any],
    cost_tier: str,
    net_r_penalty: float,
    *,
    slippage_penalty: float | None = None,
    funding_penalty: float | None = None,
) -> dict[str, Any]:
    updated = dict(row)
    updated["cost_tier"] = cost_tier
    updated["net_R"] = (_float(row.get("net_R")) or 0.0) - net_r_penalty
    updated["slippage_cost"] = (_float(row.get("slippage_cost")) or 0.0) + (
        slippage_penalty if slippage_penalty is not None else max(0.0, net_r_penalty * 0.6)
    )
    updated["funding_cost"] = (_float(row.get("funding_cost")) or 0.0) + (
        funding_penalty if funding_penalty is not None else max(0.0, net_r_penalty * 0.4)
    )
    return updated


def _enrich_row(row: dict[str, Any], feature_by_candidate: dict[str, dict[str, Any]]) -> dict[str, Any]:
    features = feature_by_candidate.get(str(row.get("candidate_id")), {})
    enriched = dict(row)
    for field in (
        "stop_atr",
        "sweep_rvol",
        "reclaim_rvol",
        "rolling_rvol",
        "trend_state",
        "trend_aligned",
        "funding_rate",
        "utc_hour",
        "session_high_low_tag",
    ):
        enriched.setdefault(field, features.get(field))
    return enriched


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    net = [_float(row.get("net_R")) for row in rows if _float(row.get("net_R")) is not None]
    mfe = [_float(row.get("mfe_R")) for row in rows if _float(row.get("mfe_R")) is not None]
    mae = [_float(row.get("mae_R")) for row in rows if _float(row.get("mae_R")) is not None]
    return {
        "closed_trades": len(rows),
        "net_R_avg": _avg(net),
        "total_net_R": sum(net),
        "profit_factor": _profit_factor(net),
        "win_rate": _ratio(sum(1 for value in net if value > 0), len(net)),
        "expectancy_R": _avg(net),
        "max_drawdown": _max_drawdown(net),
        "max_consecutive_losses": _max_consecutive_losses(net),
        "MFE_R_avg": _avg(mfe),
        "MAE_R_avg": _avg(mae),
        "bad_time_cut_ratio": _ratio(sum(1 for row in rows if row.get("time_cut_exit") and row.get("loss_time_cut")), sum(1 for row in rows if row.get("time_cut_exit"))),
        "time_cut_exit_rate": _ratio(sum(1 for row in rows if row.get("time_cut_exit")), len(rows)),
        "fee_cost": sum(_float(row.get("fee_cost")) or 0.0 for row in rows),
        "slippage_cost": sum(_float(row.get("slippage_cost")) or 0.0 for row in rows),
        "funding_cost": sum(_float(row.get("funding_cost")) or 0.0 for row in rows),
        "liquidation_event_count": sum(1 for row in rows if row.get("liquidation_event")),
    }


def _trend_bucket(row: dict[str, Any]) -> str:
    state = str(row.get("trend_state") or "").lower()
    if row.get("trend_aligned") is True or "trend" in state:
        return "trending"
    if state in {"", "unknown", "none"}:
        return "trend_unknown"
    return "ranging"


def _high_low(value: Any, rows: list[dict[str, Any]], field: str, high: str, low: str) -> str:
    values = [_float(row.get(field)) for row in rows if _float(row.get(field)) is not None]
    if not values or _float(value) is None:
        return f"{field}_unknown"
    threshold = _percentile(values, 50)
    return high if (_float(value) or 0.0) >= (threshold or 0.0) else low


def _session_from_hour(value: Any) -> str:
    hour = int(_float(value) or 0)
    if 0 <= hour < 8:
        return "Asia"
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 17:
        return "London-NY Overlap"
    if 17 <= hour < 22:
        return "NY"
    return "Late"


def _overlapping_pairs(rows: list[dict[str, Any]]) -> int:
    pairs = 0
    intervals = [
        (_float(row.get("entry_time")), _float(row.get("exit_time")))
        for row in rows
        if _float(row.get("entry_time")) is not None and _float(row.get("exit_time")) is not None
    ]
    for idx, (start, end) in enumerate(intervals):
        for other_start, other_end in intervals[idx + 1 :]:
            if start <= other_end and other_start <= end:
                pairs += 1
    return pairs


def _same_direction_overlaps(rows: list[dict[str, Any]]) -> int:
    pairs = 0
    intervals = [
        (str(row.get("direction")), _float(row.get("entry_time")), _float(row.get("exit_time")))
        for row in rows
        if _float(row.get("entry_time")) is not None and _float(row.get("exit_time")) is not None
    ]
    for idx, (direction, start, end) in enumerate(intervals):
        for other_direction, other_start, other_end in intervals[idx + 1 :]:
            if direction == other_direction and start <= other_end and other_start <= end:
                pairs += 1
    return pairs


def _max_concurrent_positions(rows: list[dict[str, Any]]) -> int:
    points: list[tuple[float, int]] = []
    for row in rows:
        entry = _float(row.get("entry_time"))
        exit_time = _float(row.get("exit_time"))
        if entry is None or exit_time is None:
            continue
        points.append((entry, 1))
        points.append((exit_time, -1))
    current = 0
    max_seen = 0
    for _, delta in sorted(points):
        current += delta
        max_seen = max(max_seen, current)
    return max_seen


def _max_concurrent_heat(rows: list[dict[str, Any]]) -> float | None:
    points: list[tuple[float, float]] = []
    for row in rows:
        entry = _float(row.get("entry_time"))
        exit_time = _float(row.get("exit_time"))
        heat = _float(row.get("portfolio_heat")) or 0.0
        if entry is None or exit_time is None:
            continue
        points.append((entry, heat))
        points.append((exit_time, -heat))
    current = 0.0
    max_seen = 0.0
    for _, delta in sorted(points):
        current += delta
        max_seen = max(max_seen, current)
    return max_seen if points else None


def _write_outputs(
    *,
    result: LRRobustnessValidationResult,
    output_dir: Path,
    preflight_rows: list[dict[str, Any]],
    walk_forward_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
    monte_carlo_rows: list[dict[str, Any]],
    cost_stress_rows: list[dict[str, Any]],
    execution_audit_rows: list[dict[str, Any]],
    portfolio_heat_rows: list[dict[str, Any]],
    artifact_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lr_robustness_validation_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "lr_robustness_validation_report.md").write_text(_report(result), encoding="utf-8")
    _write_jsonl(output_dir / "lr_robustness_preflight_rows.jsonl", preflight_rows)
    _write_jsonl(output_dir / "lr_robustness_walk_forward_rows.jsonl", walk_forward_rows)
    _write_jsonl(output_dir / "lr_robustness_regime_rows.jsonl", regime_rows)
    _write_jsonl(output_dir / "lr_robustness_monte_carlo_rows.jsonl", monte_carlo_rows)
    _write_jsonl(output_dir / "lr_robustness_cost_stress_rows.jsonl", cost_stress_rows)
    _write_jsonl(output_dir / "lr_robustness_execution_audit_rows.jsonl", execution_audit_rows)
    _write_jsonl(output_dir / "lr_robustness_portfolio_heat_rows.jsonl", portfolio_heat_rows)
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="lr_robustness_validation",
        window="10000w",
        source_command="research_pipeline.cli.research lr-robustness-validation",
        source_files=[str(artifact_dir / "lr_combined_combo_rows.jsonl")],
        notes="PR11H robustness validation; proposal-only and not formalized.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="lr_robustness_validation",
        window="10000w",
        source_command="research_pipeline.cli.research lr-robustness-validation",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11H robustness validation; no formal strategy config change.",
        tags=["PR11H", "robustness", "proposal_only"],
    )


def _report(result: LRRobustnessValidationResult) -> str:
    variant_b = next((row for row in result.cost_stress_summary if row["cost_tier"] == "base"), {})
    stress = next((row for row in result.cost_stress_summary if row["cost_tier"] == "stress"), {})
    harsh = next((row for row in result.cost_stress_summary if row["cost_tier"] == "harsh"), {})
    extreme = next((row for row in result.cost_stress_summary if row["cost_tier"] == "extreme_harsh"), {})
    positive_windows = sum(1 for row in result.walk_forward_summary if (_float(row.get("total_net_R")) or 0.0) > 0)
    heat = result.portfolio_heat_summary[0] if result.portfolio_heat_summary else {}
    lines = [
        "# PR 11H LR Robustness Validation Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- Session_HL / dynamic_time_cut / quality_aware_capped_sizing remain proposal-only",
        "- PR12 is not executed by this report",
        "",
        "## Preflight",
        f"- preflight_passed = {str(result.preflight_passed).lower()}",
        f"- blocking_issues = {len(result.blocking_issues)}",
        f"- non_blocking_warnings = {len(result.non_blocking_warnings)}",
        "",
        "## Variant B Cost Stress",
        f"- base: closed={variant_b.get('closed_trades')} net_R={variant_b.get('net_R_avg')} total_R={variant_b.get('total_net_R')} PF={variant_b.get('profit_factor')}",
        f"- stress: net_R={stress.get('net_R_avg')} total_R={stress.get('total_net_R')} PF={stress.get('profit_factor')}",
        f"- harsh: net_R={harsh.get('net_R_avg')} total_R={harsh.get('total_net_R')} PF={harsh.get('profit_factor')}",
        f"- extreme_harsh: net_R={extreme.get('net_R_avg')} total_R={extreme.get('total_net_R')} PF={extreme.get('profit_factor')}",
        "",
        "## Walk-forward",
        f"- positive_windows = {positive_windows} / {len(result.walk_forward_summary)}",
        "",
        "## Monte Carlo",
        f"- seeds = {result.monte_carlo_summary.get('seeds')}",
        f"- final_total_R P5 / median / P95 = {result.monte_carlo_summary.get('final_total_R_p5')} / {result.monte_carlo_summary.get('final_total_R_median')} / {result.monte_carlo_summary.get('final_total_R_p95')}",
        f"- max_drawdown P95 = {result.monte_carlo_summary.get('max_drawdown_p95')}",
        f"- ruin_like_scenario_count = {result.monte_carlo_summary.get('ruin_like_scenario_count')}",
        "",
        "## Portfolio / Exposure",
        f"- duplicate_event_count = {heat.get('duplicate_event_count')}",
        f"- max_concurrent_positions = {heat.get('max_concurrent_positions')}",
        f"- same_direction_overlap_count = {heat.get('same_direction_overlap_count')}",
        f"- portfolio_heat_max = {heat.get('portfolio_heat_max')}",
        f"- concentration_flags = {heat.get('concentration_flags')}",
        f"- asset_distribution = {heat.get('asset_distribution')}",
        f"- profile_distribution = {heat.get('profile_distribution')}",
        f"- direction_distribution = {heat.get('direction_distribution')}",
        "",
        "## Primary Decision",
        _decision_text(result.primary_decision),
        "",
        "## Blocking Issues",
    ]
    lines.extend([f"- {issue}" for issue in result.blocking_issues] or ["- None"])
    lines.extend(
        [
            "",
            "## Next PR",
            f"- {result.next_pr_recommendation}",
        ]
    )
    return "\n".join(lines) + "\n"


def _decision_text(decision: str) -> str:
    return {
        "A": "A. Variant B passed robustness; PR12 formalization / cleanup / merge preparation can be considered.",
        "B": "B. Variant A Tier 1 only passed; Variant B failed, so PR12 can only consider Tier 1.",
        "C": "C. Variant B partially passed, but regime / exposure restriction is required; continue PR11H-fix.",
        "D": "D. Tier 2 robustness failed; return to PR11G-Rebuild / combined pruning.",
        "E": "E. execution / mapping / audit preflight failed; continue PR11H-fix.",
        "F": "F. robustness failed overall; return to the relevant module rebuild.",
    }.get(decision, decision)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _read_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _percentile(values: Iterable[float | None], percentile: float) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def _profit_factor(values: Iterable[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if gains == 0 and losses == 0:
        return None
    if losses == 0:
        return float("inf")
    return gains / losses


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _max_consecutive_losses(values: Iterable[float]) -> int:
    current = 0
    longest = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _max(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None
