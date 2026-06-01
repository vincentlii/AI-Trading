from __future__ import annotations

from research_pipeline.core.analytics.aggregation import AggregationResult


def render_aggregation_report(result: AggregationResult) -> str:
    lines = [
        f"# Aggregation Report: {result.strategy}",
        "",
        f"- windows: {', '.join(result.windows)}",
        f"- smoke_ready_combos: {', '.join(result.smoke_ready_combos)}",
        "",
        "## Combo Summary",
    ]
    for combo in result.smoke_ready_combos:
        row = result.combo_metrics[combo].get("10000w") or next(iter(result.combo_metrics[combo].values()))
        lines.append(
            f"- {combo}: closed={row.get('closed_trades')} "
            f"MFE_R_avg={row.get('MFE_R_avg')} "
            f"time_cut={row.get('time_cut_exit_rate')}"
        )
    return "\n".join(lines)
