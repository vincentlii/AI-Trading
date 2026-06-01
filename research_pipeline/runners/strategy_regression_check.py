from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.metrics.baseline import load_baseline_metrics
from research_pipeline.runners.edge_analysis import build_edge_analysis
from research_pipeline.runners.sizing_diagnostics import build_sizing_diagnostics


FLOAT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class StrategyRegressionCheck:
    strategy: str
    passed: bool
    proposal_only: bool
    formal_conclusion_enabled: bool
    checks: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        lines = [
            f"# Strategy Regression Check: {self.strategy}",
            "",
            f"- passed: {self.passed}",
            f"- proposal_only: {self.proposal_only}",
            f"- formal_conclusion_enabled: {self.formal_conclusion_enabled}",
            "",
            "| Check | Expected | Actual | Passed |",
            "|---|---:|---:|---|",
        ]
        for name, row in self.checks.items():
            lines.append(
                f"| {name} | `{row['expected']}` | `{row['actual']}` | {row['passed']} |"
            )
        return "\n".join(lines) + "\n"


def run_strategy_regression_check(
    strategy: str,
    *,
    baseline_dir: Path,
    summary_dir: Path,
) -> StrategyRegressionCheck:
    if strategy != "liquidity_reversal":
        raise ValueError(f"Unsupported strategy for regression check: {strategy}")
    baseline = load_baseline_metrics(Path(baseline_dir))
    edge = build_edge_analysis(strategy, summary_dir=Path(summary_dir)).as_dict()
    sizing = build_sizing_diagnostics(strategy, summary_dir=Path(summary_dir)).as_dict()
    displacement = _combo(edge, "displacement_after_reclaim")
    capped = sizing["models"]["notional_capped_risk_based"]
    checks = {
        "fresh_candidates": _exact(5652, baseline.counts["fresh_candidates"]),
        "formal_approved": _exact(417, baseline.counts["formal_approved"]),
        "proposal_approved": _exact(3400, baseline.counts["proposal_approved"]),
        "closed_trades": _exact(417, baseline.counts["closed_trades"]),
        "smoke_ready_combos": _exact(
            ["CHOCH true", "displacement_after_reclaim"],
            baseline.selected_smoke_combos,
        ),
        "displacement_closed": _exact(
            137, displacement["edge_metrics"]["closed_trades"]
        ),
        "displacement_MFE_R_avg": _float(
            1.043551147771528, displacement["edge_metrics"]["MFE_R_avg"]
        ),
        "displacement_MFE_ge_0_5": _float(
            0.781021897810219, displacement["edge_metrics"]["MFE_ge_0_5_ratio"]
        ),
        "displacement_MFE_ge_1_0": _float(
            0.44525547445255476, displacement["edge_metrics"]["MFE_ge_1_0_ratio"]
        ),
        "displacement_time_cut": _float(
            0.2116788321167883, displacement["edge_metrics"]["time_cut_exit_rate"]
        ),
        "notional_cap_hit_count": _exact(
            5092, capped["notional_cap"]["notional_cap_hit_count"]
        ),
        "notional_cap_hit_ratio": _float(
            0.9009200283085633, capped["notional_cap"]["notional_cap_hit_ratio"]
        ),
        "actual_risk_pct_after_cap_p50": _float(
            0.0017564422157157668,
            capped["capped_proposal"]["actual_risk_pct_after_cap_p50"],
        ),
        "risk_utilization_p50": _float(
            0.35128844314315333, capped["risk_based"]["risk_utilization_p50"]
        ),
    }
    return StrategyRegressionCheck(
        strategy=strategy,
        passed=all(row["passed"] for row in checks.values()),
        proposal_only=True,
        formal_conclusion_enabled=False,
        checks=checks,
    )


def _combo(edge_payload: dict[str, Any], combo_name: str) -> dict[str, Any]:
    for row in edge_payload["combo_metrics"]:
        if row["combo_name"] == combo_name:
            return row
    raise KeyError(combo_name)


def _exact(expected: Any, actual: Any) -> dict[str, Any]:
    return {"expected": expected, "actual": actual, "passed": expected == actual}


def _float(expected: float, actual: float) -> dict[str, Any]:
    return {
        "expected": expected,
        "actual": actual,
        "passed": abs(float(expected) - float(actual)) <= FLOAT_TOLERANCE,
    }
