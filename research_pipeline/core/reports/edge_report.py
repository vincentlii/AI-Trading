from __future__ import annotations

from typing import Any


def render_edge_report(analysis: Any) -> str:
    payload = analysis.as_dict() if hasattr(analysis, "as_dict") else dict(analysis)
    lines = [
        "# Edge Analysis Report",
        "",
        "Read-only analytics report. It reads existing artifacts and does not run scanner, filter, sizing, or execution logic.",
        "",
        f"- strategy: {payload['strategy']}",
        f"- stage: {payload['stage']}",
        f"- window: {payload['window']}",
        f"- ranking_method: {payload['ranking_method']}",
        "",
        "## Baseline",
    ]
    baseline = payload["baseline_combo"]["edge_metrics"]
    lines.extend(
        [
            f"- closed_trades: {baseline.get('closed_trades')}",
            f"- MFE_R_avg: {baseline.get('MFE_R_avg')}",
            f"- MFE>=0.5: {baseline.get('MFE_ge_0_5_ratio')}",
            f"- MFE>=1.0: {baseline.get('MFE_ge_1_0_ratio')}",
            f"- time_cut_exit_rate: {baseline.get('time_cut_exit_rate')}",
            "",
            "## Ranked Combos",
        ]
    )
    for combo in payload["ranked_combos"]:
        edge = combo["edge_metrics"]
        lines.append(
            "- {name}: closed={closed}, MFE_R_avg={mfe}, MFE>=0.5={mfe05}, "
            "MFE>=1.0={mfe10}, net_R_avg={net}, time_cut={time_cut}, "
            "smoke_ready_hint={ready}".format(
                name=combo["combo_name"],
                closed=edge.get("closed_trades"),
                mfe=edge.get("MFE_R_avg"),
                mfe05=edge.get("MFE_ge_0_5_ratio"),
                mfe10=edge.get("MFE_ge_1_0_ratio"),
                net=edge.get("net_R_avg"),
                time_cut=edge.get("time_cut_exit_rate"),
                ready=combo.get("smoke_ready_hint"),
            )
        )
    return "\n".join(lines) + "\n"
