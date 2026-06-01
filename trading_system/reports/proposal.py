from __future__ import annotations

from dataclasses import replace
from statistics import median
from typing import Sequence

from trading_system.backtest.batch import BacktestBatchRunner
from trading_system.backtest.scanner import BacktestScanConfig
from trading_system.config.loader import BacktestPresetConfig, CostConfig
from trading_system.strategies.base import Strategy


def build_cost_tier_rows(
    *,
    repository,
    preset: BacktestPresetConfig,
    strategy: Strategy,
    cost_tiers: Sequence[str] | None = None,
    max_entry_windows: int | None = None,
    progress=None,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    tiers = preset.costs.cost_model_tiers
    if cost_tiers is not None:
        wanted = {name.strip().lower() for name in cost_tiers}
        tiers = tuple(tier for tier in tiers if tier.name.lower() in wanted)
    if not tiers:
        return ()

    scan_config = None
    if max_entry_windows is not None:
        base_scan = preset.to_scan_config()
        scan_config = BacktestScanConfig(
            targets=base_scan.targets,
            profile_keys=base_scan.profile_keys,
            start_ms=base_scan.start_ms,
            end_ms=base_scan.end_ms,
            max_entry_windows=max_entry_windows,
            max_context_bars_by_timeframe=base_scan.max_context_bars_by_timeframe,
            position_aware=base_scan.position_aware,
        )

    for tier in tiers:
        if progress is not None:
            progress(f"running cost_tier={tier.name}")
        fee_rate = max(float(tier.fee_rate), preset.costs.fee_rate)
        tier_costs = replace(
            preset.costs,
            fee_rate=fee_rate,
            spread_slippage_rate=float(tier.spread_slippage_rate),
        )
        tier_preset = replace(preset, costs=tier_costs)
        report = BacktestBatchRunner(
            repository=repository,
            preset=tier_preset,
            strategy=strategy,
            scan_config=scan_config,
        ).run()
        tier_rows = report.to_rows()
        for row in tier_rows:
            row.update(
                {
                    "cost_tier": tier.name,
                    "fee_rate": fee_rate,
                    "spread_slippage_rate": tier.spread_slippage_rate,
                    "funding_mode": preset.costs.funding_mode,
                    "expectancy_R": _direction_expectancy_r(row),
                    "median_R": _median_r_for_group(report.scan_result.profile_runs, row),
                }
            )
            rows.append(row)
    return tuple(rows)


def _direction_expectancy_r(row: dict[str, object]) -> float:
    direction = str(row.get("direction", "")).lower()
    if direction == "long":
        return float(row.get("long_expectancy_R", 0.0))
    if direction == "short":
        return float(row.get("short_expectancy_R", 0.0))
    return 0.0


def _median_r_for_group(profile_runs: Sequence[object], row: dict[str, object]) -> float:
    values: list[float] = []
    for run in profile_runs:
        if run.target.canonical_symbol != row.get("symbol"):
            continue
        if run.profile_key != row.get("timeframe_group"):
            continue
        for fill in run.result.fills:
            if fill.order.intent.direction.lower() == str(row.get("direction", "")).lower():
                values.append(float(fill.r_multiple))
    if not values:
        return 0.0
    return float(median(values))


__all__ = ("build_cost_tier_rows",)
