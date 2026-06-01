from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from research_pipeline.core.analytics.aggregation import AggregationResult
from research_pipeline.core.cache.keys import stable_fingerprint


@dataclass(frozen=True)
class SmokePlan:
    selected_combos: list[str]
    proposal_only: bool
    formal_conclusion_enabled: bool
    sizing_models: list[str]
    cost_tiers: list[str]
    required_outputs: list[str]
    forbidden_actions: list[str]
    source_aggregation_hash: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        lines = [
            "# Smoke Plan",
            "",
            f"- selected_combos: {', '.join(self.selected_combos)}",
            f"- proposal_only: {str(self.proposal_only).lower()}",
            f"- formal_conclusion_enabled: {str(self.formal_conclusion_enabled).lower()}",
            f"- cost_tiers: {', '.join(self.cost_tiers)}",
            "",
            "## Required Outputs",
        ]
        lines.extend(f"- {item}" for item in self.required_outputs)
        lines.extend(["", "## Forbidden Actions"])
        lines.extend(f"- {item}" for item in self.forbidden_actions)
        return "\n".join(lines)


def build_smoke_plan(result: AggregationResult) -> SmokePlan:
    return SmokePlan(
        selected_combos=list(result.smoke_ready_combos),
        proposal_only=True,
        formal_conclusion_enabled=False,
        sizing_models=["current_risk_based_sizing", "notional_capped_risk_based"],
        cost_tiers=["base", "stress", "harsh"],
        required_outputs=[
            "cost_tier",
            "fee",
            "spread",
            "slippage",
            "funding_paid_or_received",
            "MAE_R",
            "MFE_R",
            "exit_reason",
            "max_drawdown",
            "same_bar_ambiguous_count",
            "direction",
            "asset",
            "profile",
        ],
        forbidden_actions=[
            "Do not run formal Stage 7 conclusion",
            "Do not formalize capped sizing",
            "Do not lower fee",
            "Do not bypass RiskEngine",
            "Do not migrate scanner/filter/sizing/execution logic in PR5",
        ],
        source_aggregation_hash=stable_fingerprint(result.as_dict()),
    )
