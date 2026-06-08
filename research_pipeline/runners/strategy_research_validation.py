from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Mapping, Sequence

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.registry.strategy_registry import default_strategy_registry
from research_pipeline.runners.register_research_run import register_research_run
from trading_system.backtest.layered_cache import read_jsonl, stable_hash, write_json, write_jsonl
from trading_system.backtest.layered_pipeline import run_layered_proposal
from trading_system.config.loader import BacktestPresetConfig
from trading_system.reports.candidate_anatomy import (
    build_candidate_anatomy_rows,
    summarize_candidate_anatomy,
    write_candidate_anatomy_artifacts,
)


@dataclass(frozen=True)
class StrategyResearchValidationResult:
    strategy: str
    run_id: str
    run_root: str
    baseline_dir: str
    expansion_dir: str | None
    max_entry_windows: int | None
    proposal_only: bool
    formal_conclusion_enabled: bool
    baseline_summary: dict[str, Any]
    expansion_triggered: bool
    expansion_reason: str
    final_decision: str
    pipeline_gaps: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_strategy_research_validation(
    *,
    strategy: str,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_root: Path,
    cost_tiers: Sequence[str],
    max_entry_windows: int | None = None,
    allow_expansion: bool = True,
    force: bool = False,
    timestamp: datetime | None = None,
) -> StrategyResearchValidationResult:
    adapter = default_strategy_registry().get(strategy)
    now = timestamp or datetime.now(timezone.utc)
    run_id = _run_id(
        strategy=strategy,
        adapter_version=adapter.adapter_version,
        preset=preset,
        dataset_window=dataset_window,
        timestamp=now,
    )
    run_root = Path(output_root) / run_id
    baseline_dir = run_root / "baseline"
    baseline = _run_one_pass(
        strategy=strategy,
        adapter_version=adapter.adapter_version,
        setup_filter=adapter.setup_filter(),
        repository=repository,
        preset=preset,
        dataset_window=dataset_window,
        pass_name="baseline",
        output_dir=baseline_dir,
        cost_tiers=tuple(cost_tiers),
        max_entry_windows=max_entry_windows,
        force=force,
        strategy_parameters_override=None,
    )
    expansion_reason = _expansion_reason(baseline["summary"])
    expansion_triggered = bool(allow_expansion and expansion_reason)
    expansion_dir: Path | None = None
    if expansion_triggered:
        expansion_dir = run_root / "expansion"
        _run_expansion_grid(
            strategy=strategy,
            adapter_version=adapter.adapter_version,
            setup_filter=adapter.setup_filter(),
            repository=repository,
            preset=preset,
            dataset_window=dataset_window,
            output_dir=expansion_dir,
            cost_tiers=tuple(cost_tiers),
            max_entry_windows=max_entry_windows,
            force=force,
        )

    pipeline_gaps = _pipeline_gaps(baseline["summary"], strategy=strategy)
    final_decision = _final_decision(baseline["summary"], pipeline_gaps)
    result = StrategyResearchValidationResult(
        strategy=strategy,
        run_id=run_id,
        run_root=str(run_root),
        baseline_dir=str(baseline_dir),
        expansion_dir=None if expansion_dir is None else str(expansion_dir),
        max_entry_windows=max_entry_windows,
        proposal_only=True,
        formal_conclusion_enabled=False,
        baseline_summary=baseline["summary"],
        expansion_triggered=expansion_triggered,
        expansion_reason=expansion_reason,
        final_decision=final_decision,
        pipeline_gaps=pipeline_gaps,
    )
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "strategy_research_validation_result.json").write_text(result.as_json(), encoding="utf-8")
    (run_root / "strategy_research_validation_report.md").write_text(_report(result), encoding="utf-8")
    return result


def _run_one_pass(
    *,
    strategy: str,
    adapter_version: str,
    setup_filter: Sequence[str] | None = None,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    pass_name: str,
    output_dir: Path,
    cost_tiers: Sequence[str],
    force: bool,
    max_entry_windows: int | None,
    strategy_parameters_override: Mapping[str, object] | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_preset = _preset_with_override(preset, strategy_parameters_override)
    layered = run_layered_proposal(
        repository=repository,
        preset=run_preset,
        mode="full_backtest",
        cache_dir=output_dir,
        max_entry_windows=max_entry_windows,
        cost_tiers=tuple(cost_tiers),
        force_context=force,
        force_candidates=force,
        force_filter=force,
        force_execution=force,
        setup_filter=tuple(setup_filter or (strategy,)),
        progress_path=output_dir / "research_validation_progress.json",
    )
    candidate_rows = read_jsonl(layered.raw_candidates_path)
    filter_rows = read_jsonl(layered.filter_results_path)
    execution_rows = read_jsonl(layered.execution_results_path)
    closed_rows = tuple(row for row in execution_rows if row.get("row_type") == "closed_trade")
    diagnostic_rows = _diagnostic_rows(filter_rows, candidate_rows, closed_rows)
    summary_rows = _summary_rows(candidate_rows, filter_rows, closed_rows)
    robustness_rows = _robustness_rows(closed_rows)
    regression_baseline = _regression_baseline(summary_rows)
    anatomy_rows = build_candidate_anatomy_rows(repository=repository, filter_rows=filter_rows)
    anatomy_summary = summarize_candidate_anatomy(anatomy_rows)
    anatomy_paths = write_candidate_anatomy_artifacts(
        output_dir=output_dir / "candidate_anatomy",
        rows=anatomy_rows,
        summary=anatomy_summary,
    )
    review_log_rows = _review_log_rows(
        strategy=strategy,
        pass_name=pass_name,
        summary_rows=summary_rows,
        diagnostic_rows=diagnostic_rows,
        anatomy_summary=anatomy_summary,
    )

    write_jsonl(output_dir / "candidate_rows.jsonl", candidate_rows)
    write_jsonl(output_dir / "filter_results_research.jsonl", filter_rows)
    write_jsonl(output_dir / "closed_trade_rows.jsonl", closed_rows)
    write_jsonl(output_dir / "diagnostic_rows.jsonl", diagnostic_rows)
    write_jsonl(output_dir / "summary_rows.jsonl", summary_rows)
    write_jsonl(output_dir / "robustness_rows.jsonl", robustness_rows)
    write_jsonl(output_dir / "review_log_rows.jsonl", review_log_rows)
    write_json(output_dir / "regression_baseline.json", regression_baseline)
    manifest = RunManifest(
        run_id=stable_hash({"strategy": strategy, "pass": pass_name, "dir": str(output_dir)})[:24],
        strategy=strategy,
        adapter_version=adapter_version,
        dataset_window=dataset_window,
        artifact_contract=default_strategy_registry().get(strategy).artifact_contract().as_dict(),
        audit_profile=default_strategy_registry().get(strategy).audit_profile().as_dict(),
        artifact_paths={
            "candidate_rows": str(output_dir / "candidate_rows.jsonl"),
            "filter_results": str(output_dir / "filter_results_research.jsonl"),
            "execution_rows": str(layered.execution_results_path),
            "closed_trade_rows": str(output_dir / "closed_trade_rows.jsonl"),
            "diagnostic_rows": str(output_dir / "diagnostic_rows.jsonl"),
            "summary_rows": str(output_dir / "summary_rows.jsonl"),
            "robustness_rows": str(output_dir / "robustness_rows.jsonl"),
            "regression_baseline": str(output_dir / "regression_baseline.json"),
            "candidate_anatomy_rows": str(anatomy_paths["candidate_anatomy_jsonl"]),
            "candidate_anatomy_summary": str(anatomy_paths["candidate_anatomy_summary_json"]),
            "near_miss_shadow_rows": str(anatomy_paths["candidate_anatomy_jsonl"]),
            "review_log_rows": str(output_dir / "review_log_rows.jsonl"),
        },
        config_snapshot={
            "config_version": run_preset.config_version,
            "config_fingerprint": run_preset.config_fingerprint,
            "setup_filter": list(setup_filter or (strategy,)),
            "pass_name": pass_name,
            "max_entry_windows": max_entry_windows,
            "strategy_parameters_override": dict(strategy_parameters_override or {}),
        },
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes=f"{strategy} research validation; proposal-only, no formal config change.",
    )
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
    index = build_index_for_directory(
        output_dir,
        strategy=strategy,
        stage=f"research_validation_{pass_name}",
        window=dataset_window,
        source_command="research_pipeline.cli.research strategy-research-validation",
        config_hash=run_preset.config_fingerprint,
        notes=f"{strategy} research validation artifacts.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy=strategy,
        stage=f"research_validation_{pass_name}",
        window=dataset_window,
        source_command="research_pipeline.cli.research strategy-research-validation",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="Proposal-only research validation; no formal config change.",
        tags=["research_validation", pass_name, strategy],
    )
    summary = _pass_summary(
        candidate_rows=candidate_rows,
        filter_rows=filter_rows,
        closed_rows=closed_rows,
        summary_rows=summary_rows,
        robustness_rows=robustness_rows,
        anatomy_summary=anatomy_summary,
    )
    (output_dir / "research_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "research_validation_report.md").write_text(_pass_report(pass_name, summary), encoding="utf-8")
    return {"summary": summary}


def _run_expansion_grid(
    *,
    strategy: str,
    adapter_version: str,
    repository,
    preset: BacktestPresetConfig,
    dataset_window: str,
    output_dir: Path,
    cost_tiers: Sequence[str],
    force: bool,
    max_entry_windows: int | None,
) -> None:
    namespace = default_strategy_registry().get(strategy).parameter_namespace()
    grid = preset.strategy.parameter_grid.get(namespace, {})
    breakout_values = tuple(grid.get("breakout_rvol_min", ())) if isinstance(grid, Mapping) else ()
    pullback_values = tuple(grid.get("pullback_rvol_max", ())) if isinstance(grid, Mapping) else ()
    restart_values = tuple(grid.get("restart_rvol_min", ())) if isinstance(grid, Mapping) else ()
    for breakout in breakout_values or (None,):
        for pullback in pullback_values or (None,):
            for restart in restart_values or (None,):
                override = {
                    key: value
                    for key, value in {
                        "breakout_rvol_min": breakout,
                        "pullback_rvol_max": pullback,
                        "restart_rvol_min": restart,
                    }.items()
                    if value is not None
                }
                name = "b{0}_p{1}_r{2}".format(
                    str(breakout).replace(".", "_"),
                    str(pullback).replace(".", "_"),
                    str(restart).replace(".", "_"),
                )
                _run_one_pass(
                    strategy=strategy,
                    adapter_version=adapter_version,
                    setup_filter=default_strategy_registry().get(strategy).setup_filter(),
                    repository=repository,
                    preset=preset,
                    dataset_window=dataset_window,
                    pass_name=f"expansion_{name}",
                    output_dir=output_dir / name,
                    cost_tiers=cost_tiers,
                    force=force,
                    max_entry_windows=max_entry_windows,
                    strategy_parameters_override={namespace: override},
                )


def _preset_with_override(preset: BacktestPresetConfig, override: Mapping[str, object] | None) -> BacktestPresetConfig:
    if not override:
        return preset
    from dataclasses import replace
    from trading_system.config.loader import StrategyConfig

    params = dict(preset.strategy.parameters)
    for namespace, values in override.items():
        if isinstance(values, Mapping):
            current = dict(params.get(namespace, {})) if isinstance(params.get(namespace), Mapping) else {}
            current.update(dict(values))
            params[namespace] = current
        else:
            params[namespace] = values
    return replace(
        preset,
        strategy=StrategyConfig(
            name=preset.strategy.name,
            version=preset.strategy.version,
            enabled=preset.strategy.enabled,
            enabled_setups=preset.strategy.enabled_setups,
            parameters=params,
            parameter_grid=preset.strategy.parameter_grid,
            profile_status=preset.strategy.profile_status,
            volume=preset.strategy.volume,
        ),
    )


def _diagnostic_rows(
    filter_rows: Sequence[Mapping[str, object]],
    candidate_rows: Sequence[Mapping[str, object]],
    closed_rows: Sequence[Mapping[str, object]] = (),
) -> tuple[dict[str, object], ...]:
    reasons = Counter(str(row.get("reject_reason") or "approved") for row in filter_rows)
    stages = Counter(str(row.get("reject_stage") or "approved") for row in filter_rows)
    return (
        {
            "row_type": "diagnostic_only",
            "diagnostic_name": "reject_reason_distribution",
            "candidate_rows": len(candidate_rows),
            "filter_rows": len(filter_rows),
            "approved_without_closed_count": max(0, sum(1 for row in filter_rows if row.get("formal_approved")) - len(closed_rows)),
            "reject_reasons": dict(reasons),
            "reject_stages": dict(stages),
        },
    )


def _review_log_rows(
    *,
    strategy: str,
    pass_name: str,
    summary_rows: Sequence[Mapping[str, object]],
    diagnostic_rows: Sequence[Mapping[str, object]],
    anatomy_summary: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    base = next((row for row in summary_rows if row.get("cost_tier") == "base"), {})
    diagnostic = diagnostic_rows[0] if diagnostic_rows else {}
    return (
        {
            "row_type": "diagnostic_only",
            "review_log_type": "research_validation_input",
            "strategy": strategy,
            "pass_name": pass_name,
            "proposal_only": True,
            "formal_conclusion_enabled": False,
            "candidate_rows": base.get("candidate_rows", 0),
            "formal_approved": base.get("formal_approved", 0),
            "closed_trades": base.get("closed_trades", 0),
            "approved_without_closed_count": diagnostic.get("approved_without_closed_count", 0),
            "near_miss_shadow_counts": dict(anatomy_summary.get("near_miss_shadow_counts", {})),
            "risk_reject_reason_counts": dict(anatomy_summary.get("risk_reject_reason_counts", {})),
        },
    )


def _summary_rows(
    candidate_rows: Sequence[Mapping[str, object]],
    filter_rows: Sequence[Mapping[str, object]],
    closed_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    rows = []
    for cost_tier in sorted({str(row.get("cost_tier", "base")) for row in closed_rows} | {"base"}):
        tier_closed = [row for row in closed_rows if str(row.get("cost_tier")) == cost_tier]
        rows.append(
            {
                "row_type": "summary_row",
                "scope": "strategy_research_validation",
                "cost_tier": cost_tier,
                "candidate_rows": len(candidate_rows),
                "filter_rows": len(filter_rows),
                "formal_approved": sum(1 for row in filter_rows if row.get("formal_approved")),
                "closed_trades": len(tier_closed),
                **_metrics(tier_closed),
                "selected_without_closed_count": 0,
                "duplicate_event_count": _duplicate_event_count(tier_closed),
            }
        )
    return tuple(rows)


def _robustness_rows(closed_rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    base = [row for row in closed_rows if str(row.get("cost_tier")) == "base"]
    rows: list[dict[str, object]] = []
    rows.extend(_walk_forward_rows(base))
    rows.extend(_regime_rows(base))
    rows.extend(_exposure_rows(base))
    if not base:
        rows.extend(
            [
                {
                    "row_type": "robustness_diagnostic",
                    "robustness_type": "walk_forward",
                    "closed_trades": 0,
                    "diagnostic_status": "no_closed_trades",
                },
                {
                    "row_type": "robustness_diagnostic",
                    "robustness_type": "regime_split",
                    "closed_trades": 0,
                    "diagnostic_status": "no_closed_trades",
                },
            ]
        )
    return tuple(rows)


def _walk_forward_rows(rows: Sequence[Mapping[str, object]], windows: int = 5) -> list[dict[str, object]]:
    ordered = sorted(rows, key=lambda row: (_float(row.get("entry_time")) or 0.0, str(row.get("trade_id"))))
    output: list[dict[str, object]] = []
    if not ordered:
        return output
    for index in range(windows):
        start = round(index * len(ordered) / windows)
        end = round((index + 1) * len(ordered) / windows)
        chunk = ordered[start:end]
        output.append(
            {
                "row_type": "robustness_diagnostic",
                "robustness_type": "walk_forward",
                "window_index": index + 1,
                "closed_trades": len(chunk),
                **_metrics(chunk),
            }
        )
    return output


def _regime_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for split in ("asset", "profile", "direction", "trend_state"):
        buckets: dict[str, list[Mapping[str, object]]] = {}
        for row in rows:
            buckets.setdefault(str(row.get(split) or "unknown"), []).append(row)
        for bucket, chunk in sorted(buckets.items()):
            output.append(
                {
                    "row_type": "robustness_diagnostic",
                    "robustness_type": "regime_split",
                    "split": split,
                    "bucket": bucket,
                    "closed_trades": len(chunk),
                    **_metrics(chunk),
                }
            )
    return output


def _exposure_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "row_type": "robustness_diagnostic",
            "robustness_type": "exposure",
            "closed_trades": len(rows),
            "max_concurrent_positions": _max_concurrent_positions(rows),
            "same_direction_overlap_count": _same_direction_overlaps(rows),
            "portfolio_heat_max": _max_concurrent_heat(rows),
            "top_trade_net_R_share": _top_trade_share(rows),
            "asset_distribution": dict(Counter(str(row.get("asset")) for row in rows)),
            "profile_distribution": dict(Counter(str(row.get("profile")) for row in rows)),
            "direction_distribution": dict(Counter(str(row.get("direction")) for row in rows)),
        }
    ]


def _pass_summary(
    *,
    candidate_rows: Sequence[Mapping[str, object]],
    filter_rows: Sequence[Mapping[str, object]],
    closed_rows: Sequence[Mapping[str, object]],
    summary_rows: Sequence[Mapping[str, object]],
    robustness_rows: Sequence[Mapping[str, object]],
    anatomy_summary: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    base_summary = next((row for row in summary_rows if row.get("cost_tier") == "base"), {})
    exposure = next((row for row in robustness_rows if row.get("robustness_type") == "exposure"), {})
    return {
        "candidate_rows": len(candidate_rows),
        "filter_rows": len(filter_rows),
        "formal_approved": sum(1 for row in filter_rows if row.get("formal_approved")),
        "closed_trades": len([row for row in closed_rows if row.get("cost_tier") == "base"]),
        "cost_tier_summaries": [dict(row) for row in summary_rows],
        "top_reject_reasons": Counter(str(row.get("reject_reason") or "approved") for row in filter_rows).most_common(10),
        "base_metrics": dict(base_summary),
        "exposure": dict(exposure),
        "candidate_anatomy": dict(anatomy_summary or {}),
    }


def _metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    values = [_float(row.get("net_R")) for row in rows if _float(row.get("net_R")) is not None]
    mfe = [_float(row.get("mfe_R")) for row in rows if _float(row.get("mfe_R")) is not None]
    mae = [_float(row.get("mae_R")) for row in rows if _float(row.get("mae_R")) is not None]
    wins = [value for value in values if value > 0]
    losses = [abs(value) for value in values if value < 0]
    ranked = sorted(values, reverse=True)
    total = sum(values)
    excluding_top_1 = ranked[1:] if ranked else []
    excluding_top_2 = ranked[2:] if len(ranked) > 1 else []
    return {
        "net_R_avg": _avg(values),
        "total_net_R": total,
        "median_R": median(values) if values else None,
        "R_std": pstdev(values) if len(values) > 1 else 0.0 if values else None,
        "profit_factor": None if not losses else sum(wins) / sum(losses),
        "win_rate": None if not values else len(wins) / len(values),
        "avg_win_R": _avg(wins),
        "avg_loss_R": None if not losses else -_avg(losses),
        "top_1_trade_R_contribution": None if not values or total == 0 else ranked[0] / total,
        "top_2_trades_R_contribution": None if not values or total == 0 else sum(ranked[:2]) / total,
        "net_R_avg_excluding_top_1": _avg(excluding_top_1),
        "net_R_avg_excluding_top_2": _avg(excluding_top_2),
        "MFE_R_avg": _avg(mfe),
        "MAE_R_avg": _avg(mae),
        "time_cut_exit_rate": _ratio(sum(1 for row in rows if row.get("time_cut_exit")), len(rows)),
        "bad_time_cut_ratio": _ratio(sum(1 for row in rows if row.get("loss_time_cut")), sum(1 for row in rows if row.get("time_cut_exit"))),
        "max_drawdown": _max_drawdown(values),
    }


def _regression_baseline(summary_rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    return {
        "row_type": "regression_baseline",
        "summary_rows": [dict(row) for row in summary_rows],
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _expansion_reason(summary: Mapping[str, Any]) -> str:
    if int(summary.get("candidate_rows") or 0) == 0:
        return "raw_candidates_zero"
    if int(summary.get("closed_trades") or 0) < 30:
        return "closed_trades_below_minimum_discussion_threshold"
    exposure = summary.get("exposure") or {}
    if (_float(exposure.get("top_trade_net_R_share")) or 0.0) >= 0.4:
        return "top_trade_dominates_returns"
    return ""


def _pipeline_gaps(summary: Mapping[str, Any], strategy: str = "strategy") -> list[str]:
    gaps = []
    if int(summary.get("candidate_rows") or 0) == 0:
        gaps.append(f"{strategy} generated zero candidates")
    if int(summary.get("filter_rows") or 0) and int(summary.get("formal_approved") or 0) == 0:
        gaps.append("filter/RiskEngine approved zero candidates")
    if int(summary.get("formal_approved") or 0) and int(summary.get("closed_trades") or 0) == 0:
        gaps.append("approved candidates produced zero closed trades")
    return gaps


def _final_decision(summary: Mapping[str, Any], pipeline_gaps: Sequence[str]) -> str:
    if pipeline_gaps:
        return "needs_expansion_or_pipeline_fix"
    closed = int(summary.get("closed_trades") or 0)
    if closed < 30:
        return "diagnostic_candidate"
    base = summary.get("base_metrics") or {}
    exposure = summary.get("exposure") or {}
    if (_float(base.get("net_R_avg")) or 0.0) > 0 and (_float(exposure.get("top_trade_net_R_share")) or 0.0) < 0.4:
        return "research_candidate_recommended"
    return "diagnostic_candidate"


def _run_id(*, strategy: str, adapter_version: str, preset: BacktestPresetConfig, dataset_window: str, timestamp: datetime) -> str:
    return stable_fingerprint(
        {
            "strategy": strategy,
            "adapter_version": adapter_version,
            "config_fingerprint": preset.config_fingerprint,
            "dataset_window": dataset_window,
            "timestamp": timestamp.isoformat(),
        }
    )[:24]


def _duplicate_event_count(rows: Sequence[Mapping[str, object]]) -> int:
    keys = [f"{row.get('event_id')}|{row.get('direction')}" for row in rows]
    return len(keys) - len(set(keys))


def _max_concurrent_positions(rows: Sequence[Mapping[str, object]]) -> int:
    points = _interval_points(rows, value=1.0)
    current = 0
    max_seen = 0
    for _, delta in points:
        current += int(delta)
        max_seen = max(max_seen, current)
    return max_seen


def _same_direction_overlaps(rows: Sequence[Mapping[str, object]]) -> int:
    pairs = 0
    intervals = [
        (str(row.get("direction")), _float(row.get("entry_time")), _float(row.get("exit_time")))
        for row in rows
        if _float(row.get("entry_time")) is not None and _float(row.get("exit_time")) is not None
    ]
    for index, (direction, start, end) in enumerate(intervals):
        for other_direction, other_start, other_end in intervals[index + 1 :]:
            if direction == other_direction and start <= other_end and other_start <= end:
                pairs += 1
    return pairs


def _max_concurrent_heat(rows: Sequence[Mapping[str, object]]) -> float | None:
    points = _interval_points(rows, value=None)
    if not points:
        return None
    current = 0.0
    max_seen = 0.0
    for _, delta in points:
        current += float(delta)
        max_seen = max(max_seen, current)
    return max_seen


def _interval_points(rows: Sequence[Mapping[str, object]], *, value: float | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for row in rows:
        entry = _float(row.get("entry_time"))
        exit_time = _float(row.get("exit_time"))
        if entry is None or exit_time is None:
            continue
        heat = value if value is not None else (_float(row.get("portfolio_heat")) or 0.0)
        points.append((entry, heat))
        points.append((exit_time, -heat))
    return sorted(points)


def _top_trade_share(rows: Sequence[Mapping[str, object]]) -> float | None:
    values = [_float(row.get("net_R")) or 0.0 for row in rows]
    total = sum(values)
    if not values or total <= 0:
        return None
    return max(values) / total


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _avg(values: Sequence[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _ratio(count: int, total: int) -> float | None:
    return None if total == 0 else count / total


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pass_report(pass_name: str, summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"# Trend Continuation Research Validation: {pass_name}",
            "",
            "- proposal_only = true",
            "- formal_conclusion_enabled = false",
            f"- candidate_rows = {summary.get('candidate_rows')}",
            f"- formal_approved = {summary.get('formal_approved')}",
            f"- closed_trades = {summary.get('closed_trades')}",
            f"- final_signal = {_final_decision(summary, _pipeline_gaps(summary))}",
            "",
        ]
    )


def _report(result: StrategyResearchValidationResult) -> str:
    return "\n".join(
        [
            "# Trend Continuation Strategy Research Validation",
            "",
            "- proposal_only = true",
            "- formal_conclusion_enabled = false",
            f"- run_id = {result.run_id}",
            f"- baseline_dir = {result.baseline_dir}",
            f"- max_entry_windows = {result.max_entry_windows if result.max_entry_windows is not None else 'all'}",
            f"- expansion_triggered = {str(result.expansion_triggered).lower()}",
            f"- expansion_reason = {result.expansion_reason}",
            f"- final_decision = {result.final_decision}",
            "",
            "## Pipeline Gaps",
            *([f"- {gap}" for gap in result.pipeline_gaps] or ["- None"]),
            "",
        ]
    )


__all__ = ("StrategyResearchValidationResult", "run_strategy_research_validation")
