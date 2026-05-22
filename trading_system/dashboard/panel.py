from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from trading_system.backtest.batch import BacktestBatchRunner
from trading_system.config.loader import BacktestPresetConfig, load_backtest_preset
from trading_system.config.proposals import load_parameter_proposal
from trading_system.data.coverage import build_bar_coverage_rows, build_profile_coverage_rows
from trading_system.data.quality import check_repository_symbol_bar
from trading_system.data.universe import required_okx_bars_for_profiles
from trading_system.diagnostics.rejection_detail import build_rejection_detail_snapshot
from trading_system.diagnostics.signal_funnel import build_signal_funnel_rows
from trading_system.reports.performance import build_performance_report
from trading_system.simulation.review_log import read_review_log
from trading_system.strategies.base import Strategy
from trading_system.timeframe_profiles import get_profile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"
DEFAULT_DB_PATH = PROJECT_ROOT / "storage" / "history.duckdb"
DEFAULT_PROPOSALS_DIR = PROJECT_ROOT / "configs" / "proposals"
DEFAULT_REVIEW_LOG_PATH = PROJECT_ROOT / "storage" / "paper" / "review_log.jsonl"
DASHBOARD_MAX_ENTRY_WINDOWS = 200
DASHBOARD_CONTEXT_BARS = 320
SIGNAL_FUNNEL_STAGE_ORDER = (
    "windows_checked",
    "data_insufficient",
    "regime_not_computable",
    "regime_rejected",
    "price_action_rejected",
    "volume_price_rejected",
    "target_space_insufficient",
    "risk_rejected",
    "approved_signal",
)
VOLUME_REJECTION_REASON_COLUMNS = (
    "volume_ratio_below_reject_threshold",
    "volume_ratio_below_confirm_threshold",
    "volume_ratio_above_anomaly_threshold",
    "price_direction_not_accepted",
)


@dataclass(frozen=True)
class DashboardSnapshot:
    config_version: str
    config_fingerprint: str
    summary: Mapping[str, object]
    ranking_rows: tuple[dict[str, object], ...]
    quality_rows: tuple[dict[str, object], ...]
    skipped_run_rows: tuple[dict[str, object], ...]
    proposal_rows: tuple[dict[str, object], ...]
    performance_metric_rows: tuple[dict[str, object], ...]
    performance_library_rows: tuple[dict[str, object], ...]
    performance_artifact_rows: tuple[dict[str, object], ...]
    data_coverage_rows: tuple[dict[str, object], ...]
    profile_coverage_rows: tuple[dict[str, object], ...]
    signal_funnel_rows: tuple[dict[str, object], ...]
    volume_rejection_rows: tuple[dict[str, object], ...]
    volume_distribution_rows: tuple[dict[str, object], ...]
    risk_rejection_rows: tuple[dict[str, object], ...]
    near_miss_rows: tuple[dict[str, object], ...]
    paper_review_log_rows: tuple[dict[str, object], ...]
    paper_equity_rows: tuple[dict[str, object], ...]
    paper_trade_rows: tuple[dict[str, object], ...]
    paper_failure_rows: tuple[dict[str, object], ...]
    paper_review_log_invalid_rows: tuple[dict[str, object], ...]


def build_default_dashboard_snapshot(
    *,
    preset_path: str | Path = DEFAULT_PRESET_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    proposals_dir: str | Path | None = DEFAULT_PROPOSALS_DIR,
    review_log_path: str | Path | None = DEFAULT_REVIEW_LOG_PATH,
) -> DashboardSnapshot:
    from trading_system.data.history import DuckDbCandleRepository
    from trading_system.strategies.trend_price_volume_v1 import TrendPriceVolumeStrategy

    preset = load_backtest_preset(preset_path)
    repository = DuckDbCandleRepository(db_path)
    return build_dashboard_snapshot(
        repository=repository,
        preset=preset,
        strategy=TrendPriceVolumeStrategy(),
        proposals_dir=proposals_dir,
        review_log_path=review_log_path,
    )


def build_dashboard_snapshot(
    *,
    repository,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    proposals_dir: str | Path | None = DEFAULT_PROPOSALS_DIR,
    review_log_path: str | Path | None = DEFAULT_REVIEW_LOG_PATH,
) -> DashboardSnapshot:
    report = BacktestBatchRunner(
        repository=repository,
        preset=preset,
        strategy=strategy,
        scan_config=_dashboard_scan_config(preset),
    ).run()
    ranking_rows = report.to_rows()
    quality_rows = _build_quality_rows(repository, preset)
    skipped_run_rows = _build_skipped_run_rows(report.scan_result.profile_runs)
    proposal_rows = _build_proposal_rows(proposals_dir)
    performance_report = build_performance_report(report.scan_result)
    target_tuples = _target_tuples(preset)
    bars = tuple(reversed(required_okx_bars_for_profiles(tuple(get_profile(key) for key in preset.scan.profile_keys))))
    data_coverage_rows = build_bar_coverage_rows(repository, targets=target_tuples, bars=bars)
    profile_coverage_rows = build_profile_coverage_rows(
        repository,
        targets=target_tuples,
        profile_keys=preset.scan.profile_keys,
    )
    signal_funnel_rows = build_signal_funnel_rows(
        repository,
        preset=preset,
        strategy=strategy,
    )
    rejection_detail = build_rejection_detail_snapshot(
        repository,
        preset=preset,
        strategy=strategy,
        max_windows_per_profile=200,
    )
    paper_review = _build_paper_review_rows(review_log_path)

    return DashboardSnapshot(
        config_version=report.config_version,
        config_fingerprint=report.config_fingerprint,
        summary=_build_summary(
            ranking_rows,
            quality_rows,
            skipped_run_rows,
            proposal_rows,
            performance_report.summary,
            data_coverage_rows,
            profile_coverage_rows,
            signal_funnel_rows,
            rejection_detail.volume_rejection_rows,
            rejection_detail.risk_rejection_rows,
            rejection_detail.near_miss_rows,
            paper_review["review_log_rows"],
            paper_review["trade_rows"],
            paper_review["failure_rows"],
            DASHBOARD_MAX_ENTRY_WINDOWS,
        ),
        ranking_rows=ranking_rows,
        quality_rows=quality_rows,
        skipped_run_rows=skipped_run_rows,
        proposal_rows=proposal_rows,
        performance_metric_rows=performance_report.metric_rows,
        performance_library_rows=performance_report.library_rows,
        performance_artifact_rows=performance_report.artifact_rows,
        data_coverage_rows=data_coverage_rows,
        profile_coverage_rows=profile_coverage_rows,
        signal_funnel_rows=signal_funnel_rows,
        volume_rejection_rows=rejection_detail.volume_rejection_rows,
        volume_distribution_rows=rejection_detail.volume_distribution_rows,
        risk_rejection_rows=rejection_detail.risk_rejection_rows,
        near_miss_rows=rejection_detail.near_miss_rows,
        paper_review_log_rows=paper_review["review_log_rows"],
        paper_equity_rows=paper_review["equity_rows"],
        paper_trade_rows=paper_review["trade_rows"],
        paper_failure_rows=paper_review["failure_rows"],
        paper_review_log_invalid_rows=paper_review["invalid_rows"],
    )


def _build_quality_rows(repository, preset: BacktestPresetConfig) -> tuple[dict[str, object], ...]:
    profiles = tuple(get_profile(key) for key in preset.scan.profile_keys)
    bars = required_okx_bars_for_profiles(profiles)
    rows: list[dict[str, object]] = []

    for target in preset.assets.targets:
        for bar in bars:
            report = check_repository_symbol_bar(
                repository,
                target.inst_id,
                bar,
                venue=target.venue,
                inst_type=target.inst_type,
            )
            rows.append(
                {
                    "symbol": target.canonical_symbol,
                    "venue": report.venue,
                    "inst_type": report.inst_type,
                    "inst_id": report.inst_id,
                    "bar": report.bar,
                    "status": report.status,
                    "row_count": report.row_count,
                    "earliest_ts_ms": report.earliest_ts_ms,
                    "latest_ts_ms": report.latest_ts_ms,
                    "issue_count": len(report.issues),
                    "issue_codes": tuple(issue.code for issue in report.issues),
                }
            )

    return tuple(rows)


def _build_skipped_run_rows(profile_runs) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "symbol": run.target.canonical_symbol,
            "venue": run.target.venue,
            "inst_type": run.target.inst_type,
            "inst_id": run.target.inst_id,
            "timeframe_group": run.profile_key,
            "status": run.status,
            "reason_codes": run.reason_codes,
            "signal_count": run.signal_count,
            "candle_counts_by_timeframe": dict(run.candle_counts_by_timeframe),
        }
        for run in profile_runs
        if run.status != "completed"
    )


def _build_proposal_rows(proposals_dir: str | Path | None) -> tuple[dict[str, object], ...]:
    if proposals_dir is None:
        return ()

    directory = Path(proposals_dir)
    if not directory.exists():
        return ()

    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            proposal = load_parameter_proposal(path)
        except Exception as error:
            rows.append(
                {
                    "path": str(path),
                    "status": "invalid",
                    "error": str(error),
                }
            )
            continue

        rows.append(
            {
                "path": str(path),
                "status": "loaded",
                "proposal_id": proposal.proposal_id,
                "title": proposal.title,
                "source": proposal.source,
                "base_config_version": proposal.base_config_version,
                "base_config_fingerprint": proposal.base_config_fingerprint,
                "change_count": len(proposal.changes),
                "auto_apply": proposal.auto_apply,
            }
        )

    return tuple(rows)


def _build_paper_review_rows(review_log_path: str | Path | None) -> dict[str, tuple[dict[str, object], ...]]:
    if review_log_path is None:
        return {
            "review_log_rows": (),
            "equity_rows": (),
            "trade_rows": (),
            "failure_rows": (),
            "invalid_rows": (),
        }

    result = read_review_log(review_log_path)
    review_rows = tuple(_review_log_row(entry) for entry in result.entries)
    equity_rows = tuple(row for row in review_rows if row["event_type"] == "equity_updated")
    trade_rows = tuple(row for row in review_rows if row["event_type"] == "position_closed")
    failure_rows = []
    for row in trade_rows:
        failure = _paper_failure_row(row)
        if failure is not None:
            failure_rows.append(failure)
    return {
        "review_log_rows": review_rows,
        "equity_rows": equity_rows,
        "trade_rows": trade_rows,
        "failure_rows": tuple(failure_rows),
        "invalid_rows": result.invalid_rows,
    }


def _review_log_row(entry) -> dict[str, object]:
    row = {
        "event_type": entry.event_type,
        "timestamp_ms": entry.timestamp_ms,
        "symbol": entry.symbol,
        "venue": entry.venue,
        "strategy_name": entry.strategy_name,
        "strategy_version": entry.strategy_version,
        "setup_type": entry.setup_type,
        "status": entry.status,
        "reason_codes": entry.reason_codes,
    }
    row.update({f"payload_{key}": value for key, value in entry.payload.items()})
    return row


def _paper_failure_row(row: Mapping[str, object]) -> dict[str, object] | None:
    net_pnl = _as_float(row.get("payload_net_pnl"))
    cost = _as_float(row.get("payload_cost"))
    r_multiple = _as_float(row.get("payload_r_multiple"))
    exit_reason = str(row.get("status", ""))
    attribution = ""
    if net_pnl < 0:
        attribution = "losing_trade"
    elif exit_reason == "time_exit":
        attribution = "time_exit"
    elif cost > 0 and r_multiple < 0.25:
        attribution = "cost_drag_or_low_net_r"
    if not attribution:
        return None
    return {
        "symbol": row.get("symbol", ""),
        "timestamp_ms": row.get("timestamp_ms"),
        "setup_type": row.get("setup_type", ""),
        "exit_reason": exit_reason,
        "net_pnl": net_pnl,
        "r_multiple": r_multiple,
        "cost": cost,
        "attribution": attribution,
    }


def _build_summary(
    ranking_rows: tuple[dict[str, object], ...],
    quality_rows: tuple[dict[str, object], ...],
    skipped_run_rows: tuple[dict[str, object], ...],
    proposal_rows: tuple[dict[str, object], ...],
    performance_summary: Mapping[str, object],
    data_coverage_rows: tuple[dict[str, object], ...],
    profile_coverage_rows: tuple[dict[str, object], ...],
    signal_funnel_rows: tuple[dict[str, object], ...],
    volume_rejection_rows: tuple[dict[str, object], ...],
    risk_rejection_rows: tuple[dict[str, object], ...],
    near_miss_rows: tuple[dict[str, object], ...],
    paper_review_log_rows: tuple[dict[str, object], ...],
    paper_trade_rows: tuple[dict[str, object], ...],
    paper_failure_rows: tuple[dict[str, object], ...],
    dashboard_max_entry_windows: int,
) -> dict[str, object]:
    summary = {
        "ranked_groups": len(ranking_rows),
        "candidates": _count_status(ranking_rows, "candidate"),
        "supporting_only": _count_status(ranking_rows, "supporting_only"),
        "rejected": _count_status(ranking_rows, "rejected"),
        "net_profit": sum(float(row.get("net_profit", 0.0)) for row in ranking_rows),
        "quality_checks": len(quality_rows),
        "quality_failures": sum(1 for row in quality_rows if row["status"] != "pass"),
        "skipped_runs": len(skipped_run_rows),
        "proposals": len(proposal_rows),
        "invalid_proposals": sum(1 for row in proposal_rows if row["status"] == "invalid"),
        "coverage_bars": len(data_coverage_rows),
        "coverage_bar_ready": sum(1 for row in data_coverage_rows if row["next_action"] == "ready"),
        "profile_can_run": sum(1 for row in profile_coverage_rows if row["can_run"]),
        "signal_funnel_profiles": len(signal_funnel_rows),
        "approved_signals": sum(int(row["approved_signal"]) for row in signal_funnel_rows),
        "volume_rejection_groups": len(volume_rejection_rows),
        "risk_rejection_groups": len(risk_rejection_rows),
        "near_miss_candidates": len(near_miss_rows),
        "paper_review_log_events": len(paper_review_log_rows),
        "paper_trade_events": len(paper_trade_rows),
        "paper_failure_cases": len(paper_failure_rows),
        "dashboard_max_entry_windows": dashboard_max_entry_windows,
    }
    summary.update(performance_summary)
    return summary


def build_dashboard_presentation_data(snapshot, *, top_n: int = 10, near_miss_limit: int = 20) -> dict[str, object]:
    return {
        "signal_funnel": _build_signal_funnel_plot_data(_snapshot_rows(snapshot, "signal_funnel_rows")),
        "rejection_reason_top": _build_rejection_reason_top(
            signal_funnel_rows=_snapshot_rows(snapshot, "signal_funnel_rows"),
            volume_rejection_rows=_snapshot_rows(snapshot, "volume_rejection_rows"),
            risk_rejection_rows=_snapshot_rows(snapshot, "risk_rejection_rows"),
            top_n=top_n,
        ),
        "rvol_distribution": _build_rvol_distribution(_snapshot_rows(snapshot, "volume_distribution_rows")),
        "risk_distribution": _build_risk_distribution(_snapshot_rows(snapshot, "risk_rejection_rows")),
        "rejection_heatmap": _build_rejection_heatmap(
            signal_funnel_rows=_snapshot_rows(snapshot, "signal_funnel_rows"),
            volume_rejection_rows=_snapshot_rows(snapshot, "volume_rejection_rows"),
            risk_rejection_rows=_snapshot_rows(snapshot, "risk_rejection_rows"),
        ),
        "near_miss_summary": _build_near_miss_summary(
            _snapshot_rows(snapshot, "near_miss_rows"),
            limit=near_miss_limit,
        ),
        "full_backtest_summary": _build_full_backtest_summary(
            ranking_rows=_snapshot_rows(snapshot, "ranking_rows"),
            performance_metric_rows=_snapshot_rows(snapshot, "performance_metric_rows"),
        ),
    }


def _snapshot_rows(snapshot, attribute: str) -> tuple[dict[str, object], ...]:
    return tuple(getattr(snapshot, attribute, ()))


def _build_signal_funnel_plot_data(rows: tuple[dict[str, object], ...]) -> dict[str, object]:
    return {
        "stages": SIGNAL_FUNNEL_STAGE_ORDER,
        "values": tuple(sum(_as_int(row.get(stage)) for row in rows) for stage in SIGNAL_FUNNEL_STAGE_ORDER),
    }


def _build_rejection_reason_top(
    *,
    signal_funnel_rows: tuple[dict[str, object], ...],
    volume_rejection_rows: tuple[dict[str, object], ...],
    risk_rejection_rows: tuple[dict[str, object], ...],
    top_n: int,
) -> tuple[dict[str, object], ...]:
    counts: Counter[str] = Counter()
    for row in volume_rejection_rows:
        for column in VOLUME_REJECTION_REASON_COLUMNS:
            counts[column] += _as_int(row.get(column))
    for row in risk_rejection_rows:
        reason = str(row.get("reason_code", "")).strip()
        if reason:
            counts[reason] += _as_int(row.get("candidate_count"))
    for row in signal_funnel_rows:
        for reason in row.get("reason_codes", ()) or ():
            reason_text = str(reason).strip()
            if reason_text:
                counts[reason_text] += 1

    ranked = sorted(
        ({"reason_code": reason, "count": count} for reason, count in counts.items() if count > 0),
        key=lambda row: (-int(row["count"]), str(row["reason_code"])),
    )
    return tuple(ranked[: max(0, top_n)])


def _build_rvol_distribution(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "symbol": row.get("symbol", ""),
            "profile": row.get("profile", row.get("timeframe_group", "")),
            "candidate_count": _as_int(row.get("candidate_count")),
            "min": row.get("volume_ratio_min"),
            "p25": row.get("volume_ratio_p25"),
            "median": row.get("volume_ratio_median"),
            "p75": row.get("volume_ratio_p75"),
            "max": row.get("volume_ratio_max"),
        }
        for row in rows
    )


def _build_risk_distribution(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "symbol": row.get("symbol", ""),
            "profile": row.get("profile", row.get("timeframe_group", "")),
            "reason_code": row.get("reason_code", ""),
            "candidate_count": _as_int(row.get("candidate_count")),
            "stop_atr_median": row.get("stop_atr_median"),
            "reward_to_risk_median": row.get("reward_to_risk_median"),
            "estimated_cost_r_median": row.get("estimated_cost_r_median"),
            "net_reward_to_risk_median": row.get("net_reward_to_risk_median"),
        }
        for row in rows
    )


def _build_rejection_heatmap(
    *,
    signal_funnel_rows: tuple[dict[str, object], ...],
    volume_rejection_rows: tuple[dict[str, object], ...],
    risk_rejection_rows: tuple[dict[str, object], ...],
) -> dict[str, object]:
    counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for row in signal_funnel_rows:
        key = _symbol_profile_key(row)
        counts[key] += sum(
            _as_int(row.get(stage))
            for stage in SIGNAL_FUNNEL_STAGE_ORDER
            if stage not in {"windows_checked", "approved_signal"}
        )
    for row in volume_rejection_rows:
        counts[_symbol_profile_key(row)] += _as_int(row.get("candidate_count"))
    for row in risk_rejection_rows:
        counts[_symbol_profile_key(row)] += _as_int(row.get("candidate_count"))

    symbols = tuple(sorted({symbol for symbol, _profile in counts}))
    profiles = tuple(sorted({profile for _symbol, profile in counts}))
    matrix = tuple(tuple(counts[(symbol, profile)] for profile in profiles) for symbol in symbols)
    return {"x": profiles, "y": symbols, "z": matrix}


def _build_near_miss_summary(
    rows: tuple[dict[str, object], ...],
    *,
    limit: int,
) -> tuple[dict[str, object], ...]:
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                _as_float(row.get("distance_to_pass")),
                str(row.get("symbol", "")),
                str(row.get("profile", row.get("timeframe_group", ""))),
                _as_int(row.get("timestamp_ms")),
            ),
        )[: max(0, limit)]
    )


def _build_full_backtest_summary(
    *,
    ranking_rows: tuple[dict[str, object], ...],
    performance_metric_rows: tuple[dict[str, object], ...],
) -> dict[str, object]:
    best_ranked = min(ranking_rows, key=lambda row: _as_int(row.get("rank"), default=10**9), default={})
    best_performance = max(performance_metric_rows, key=lambda row: _as_float(row.get("net_profit")), default={})
    return {
        "ranked_groups": len(ranking_rows),
        "candidates": _count_status(ranking_rows, "candidate"),
        "supporting_only": _count_status(ranking_rows, "supporting_only"),
        "rejected": _count_status(ranking_rows, "rejected"),
        "ranking_net_profit": sum(_as_float(row.get("net_profit")) for row in ranking_rows),
        "ranking_trade_count": sum(_as_int(row.get("trade_count")) for row in ranking_rows),
        "performance_runs": len(performance_metric_rows),
        "performance_trade_count": sum(_as_int(row.get("trade_count")) for row in performance_metric_rows),
        "performance_net_profit": sum(_as_float(row.get("net_profit")) for row in performance_metric_rows),
        "best_ranked_symbol": best_ranked.get("symbol", ""),
        "best_ranked_profile": best_ranked.get("timeframe_group", best_ranked.get("profile", "")),
        "best_performance_symbol": best_performance.get("symbol", ""),
        "best_performance_profile": best_performance.get(
            "timeframe_group",
            best_performance.get("profile", ""),
        ),
    }


def _count_status(rows: tuple[dict[str, object], ...], status: str) -> int:
    return sum(1 for row in rows if row.get("status") == status)


def _symbol_profile_key(row: Mapping[str, object]) -> tuple[str, str]:
    return str(row.get("symbol", "")), str(row.get("profile", row.get("timeframe_group", "")))


def _as_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _target_tuples(preset: BacktestPresetConfig) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (target.canonical_symbol, target.inst_id, target.venue, target.inst_type)
        for target in preset.assets.targets
    )


def _dashboard_scan_config(preset: BacktestPresetConfig):
    base = preset.to_scan_config()
    context_limits = dict(base.max_context_bars_by_timeframe)
    for timeframe in ("5m", "15m", "1h", "4h", "1d"):
        context_limits.setdefault(timeframe, DASHBOARD_CONTEXT_BARS)
    return replace(
        base,
        max_entry_windows=DASHBOARD_MAX_ENTRY_WINDOWS,
        max_context_bars_by_timeframe=context_limits,
    )
