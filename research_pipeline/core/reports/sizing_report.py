from __future__ import annotations

from typing import Any


def render_sizing_report(result: Any) -> str:
    payload = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    lines = [
        "# Sizing Diagnostics Report",
        "",
        "Read-only sizing diagnostics. It reads existing artifacts and does not run scanner, filter, sizing engine, or execution logic.",
        "",
        f"- strategy: {payload['strategy']}",
        f"- stage: {payload['stage']}",
        f"- window: {payload['window']}",
        f"- proposal_only: {payload['proposal_only']}",
        f"- readonly: {payload['readonly']}",
        "",
        "proposal approval is not formal approval. Low actual risk or low risk utilization is not an automatic reject; it is only a diagnostic signal.",
        "",
        "## Counts",
        f"- fresh_candidates: {payload['fresh_candidates']}",
        f"- formal_approved: {payload['formal_approved']}",
        f"- proposal_approved: {payload['proposal_approved']}",
        f"- closed_trades: {payload['closed_trades']}",
        "",
        "## Models",
    ]
    for name, model in payload["models"].items():
        risk = model["risk_based"]
        cap = model["notional_cap"]
        margin = model["margin"]
        proposal = model["capped_proposal"]
        lines.extend(
            [
                f"### {name}",
                f"- formal_approved: {model['formal_approved']}",
                f"- proposal_approved: {model['proposal_approved']}",
                f"- actual_risk_pct_p50: {risk['actual_risk_pct_p50']}",
                f"- risk_utilization_p50: {risk['risk_utilization_p50']}",
                f"- notional_cap_hit_count: {cap['notional_cap_hit_count']}",
                f"- notional_cap_hit_ratio: {cap['notional_cap_hit_ratio']}",
                f"- margin_required_too_high: {margin['margin_required_too_high_count']}",
                f"- stop_distance_too_near: {margin['stop_distance_too_near_count']}",
                f"- capped_proposal_approved: {proposal['capped_proposal_approved']}",
                f"- missing_fields: {', '.join(model['missing_fields']) if model['missing_fields'] else 'none'}",
                "",
            ]
        )
    return "\n".join(lines)
