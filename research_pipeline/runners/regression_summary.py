from __future__ import annotations

from pathlib import Path

from research_pipeline.adapters.liquidity_reversal import LiquidityReversalAdapter
from research_pipeline.core.metrics.baseline import load_baseline_metrics
from research_pipeline.core.reports.regression import RegressionSummary


def build_regression_summary(strategy: str, baseline_dir: Path) -> RegressionSummary:
    if strategy != LiquidityReversalAdapter.name:
        raise ValueError(f"Unsupported strategy for PR2 skeleton: {strategy}")
    baseline = load_baseline_metrics(Path(baseline_dir))
    displacement = baseline.tracked_combos["displacement_after_reclaim"]
    return RegressionSummary(
        strategy=baseline.strategy,
        window=baseline.window,
        counts=baseline.counts,
        selected_smoke_combos=baseline.selected_smoke_combos,
        displacement_after_reclaim=displacement,
    )
