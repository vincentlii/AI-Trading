from __future__ import annotations

from research_pipeline.runners.smoke_plan import SmokePlan


def render_smoke_plan_report(plan: SmokePlan) -> str:
    return plan.as_markdown()
