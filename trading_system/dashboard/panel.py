from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from trading_system.backtest.batch import BacktestBatchRunner
from trading_system.config.loader import BacktestPresetConfig, load_backtest_preset
from trading_system.config.proposals import load_parameter_proposal
from trading_system.data.quality import check_repository_symbol_bar
from trading_system.data.universe import required_okx_bars_for_profiles
from trading_system.strategies.base import Strategy
from trading_system.timeframe_profiles import get_profile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"
DEFAULT_DB_PATH = PROJECT_ROOT / "storage" / "history.duckdb"
DEFAULT_PROPOSALS_DIR = PROJECT_ROOT / "configs" / "proposals"


@dataclass(frozen=True)
class DashboardSnapshot:
    config_version: str
    config_fingerprint: str
    summary: Mapping[str, object]
    ranking_rows: tuple[dict[str, object], ...]
    quality_rows: tuple[dict[str, object], ...]
    skipped_run_rows: tuple[dict[str, object], ...]
    proposal_rows: tuple[dict[str, object], ...]


def build_default_dashboard_snapshot(
    *,
    preset_path: str | Path = DEFAULT_PRESET_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    proposals_dir: str | Path | None = DEFAULT_PROPOSALS_DIR,
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
    )


def build_dashboard_snapshot(
    *,
    repository,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    proposals_dir: str | Path | None = DEFAULT_PROPOSALS_DIR,
) -> DashboardSnapshot:
    report = BacktestBatchRunner(repository=repository, preset=preset, strategy=strategy).run()
    ranking_rows = report.to_rows()
    quality_rows = _build_quality_rows(repository, preset)
    skipped_run_rows = _build_skipped_run_rows(report.scan_result.profile_runs)
    proposal_rows = _build_proposal_rows(proposals_dir)

    return DashboardSnapshot(
        config_version=report.config_version,
        config_fingerprint=report.config_fingerprint,
        summary=_build_summary(ranking_rows, quality_rows, skipped_run_rows, proposal_rows),
        ranking_rows=ranking_rows,
        quality_rows=quality_rows,
        skipped_run_rows=skipped_run_rows,
        proposal_rows=proposal_rows,
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


def _build_summary(
    ranking_rows: tuple[dict[str, object], ...],
    quality_rows: tuple[dict[str, object], ...],
    skipped_run_rows: tuple[dict[str, object], ...],
    proposal_rows: tuple[dict[str, object], ...],
) -> dict[str, object]:
    return {
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
    }


def _count_status(rows: tuple[dict[str, object], ...], status: str) -> int:
    return sum(1 for row in rows if row.get("status") == status)
