from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.metrics.baseline import load_baseline_metrics
from research_pipeline.registry.strategy_registry import default_strategy_registry
from research_pipeline.runners.edge_analysis import build_edge_analysis
from research_pipeline.runners.sizing_diagnostics import build_sizing_diagnostics


@dataclass(frozen=True)
class StrategySummary:
    strategy: str
    adapter_metadata: dict[str, Any]
    baseline_metrics: dict[str, Any]
    smoke_ready_combos: list[str]
    primary_combo: str
    edge_summary: dict[str, Any]
    sizing_summary: dict[str, Any]
    proposal_only: bool
    formal_conclusion_enabled: bool
    missing_artifacts: list[str]
    next_step_hint: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        lines = [
            f"# Strategy Summary: {self.strategy}",
            "",
            f"- proposal_only: {self.proposal_only}",
            f"- formal_conclusion_enabled: {self.formal_conclusion_enabled}",
            f"- primary_combo: {self.primary_combo}",
            f"- smoke_ready_combos: {', '.join(self.smoke_ready_combos)}",
            f"- missing_artifacts: {', '.join(self.missing_artifacts) if self.missing_artifacts else 'none'}",
            f"- next_step_hint: {self.next_step_hint}",
            "",
            "## Baseline",
            f"- fresh_candidates: {self.baseline_metrics.get('fresh_candidates')}",
            f"- formal_approved: {self.baseline_metrics.get('formal_approved')}",
            f"- proposal_approved: {self.baseline_metrics.get('proposal_approved')}",
            f"- closed_trades: {self.baseline_metrics.get('closed_trades')}",
            "",
            "## Edge",
            f"- top_combo: {self.edge_summary.get('top_combo')}",
            f"- top_combo_MFE_R_avg: {self.edge_summary.get('top_combo_MFE_R_avg')}",
            "",
            "## Sizing",
        ]
        for model, row in self.sizing_summary.items():
            lines.append(f"- {model}: {row}")
        return "\n".join(lines) + "\n"


def build_strategy_summary(strategy: str, *, summary_dir: Path) -> StrategySummary:
    adapter = default_strategy_registry().get(strategy)
    metadata = adapter.metadata()
    summary_dir = Path(summary_dir)
    missing = _missing_artifacts(summary_dir)
    baseline_metrics: dict[str, Any] = {}
    smoke_ready = list(metadata["smoke_ready_combos"])
    edge_summary: dict[str, Any] = {}
    sizing_summary: dict[str, Any] = {}

    if "key_metrics.json" not in missing:
        baseline = load_baseline_metrics(summary_dir)
        baseline_metrics = dict(baseline.counts)
        smoke_ready = list(baseline.selected_smoke_combos)

    if "stage6e_aggregated_comparison_snapshot.csv" not in missing:
        edge = build_edge_analysis(strategy, summary_dir=summary_dir)
        top = edge.ranked_combos[0] if edge.ranked_combos else {}
        top_edge = top.get("edge_metrics", {})
        edge_summary = {
            "top_combo": top.get("combo_name"),
            "top_combo_MFE_R_avg": top_edge.get("MFE_R_avg"),
            "top_combo_closed_trades": top_edge.get("closed_trades"),
        }

    if "key_metrics.json" not in missing:
        sizing = build_sizing_diagnostics(strategy, summary_dir=summary_dir)
        sizing_payload = sizing.as_dict()["models"]
        sizing_summary = {
            name: {
                "formal_approved": model["formal_approved"],
                "proposal_approved": model["proposal_approved"],
                "notional_cap_hit_count": model["notional_cap"]["notional_cap_hit_count"],
                "risk_utilization_p50": model["risk_based"]["risk_utilization_p50"],
            }
            for name, model in sizing_payload.items()
        }

    return StrategySummary(
        strategy=strategy,
        adapter_metadata=metadata,
        baseline_metrics=baseline_metrics,
        smoke_ready_combos=smoke_ready,
        primary_combo=str(metadata["primary_combo"]),
        edge_summary=edge_summary,
        sizing_summary=sizing_summary,
        proposal_only=bool(metadata["proposal_only"]),
        formal_conclusion_enabled=bool(metadata["formal_conclusion_enabled"]),
        missing_artifacts=missing,
        next_step_hint="PR11: continue LR proposal validation; do not formalize in PR10.",
    )


def _missing_artifacts(summary_dir: Path) -> list[str]:
    expected = [
        "key_metrics.json",
        "baseline_manifest.json",
        "stage6e_aggregated_comparison_snapshot.csv",
        "stage7_smoke_plan_snapshot.md",
    ]
    return [name for name in expected if not (summary_dir / name).exists()]
