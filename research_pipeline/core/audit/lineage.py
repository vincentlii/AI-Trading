from __future__ import annotations

from typing import Any


def build_lineage_rows(
    *,
    source_artifact: str,
    reported_variant: dict[str, Any],
) -> list[dict[str, Any]]:
    closed = int(reported_variant.get("closed_trades") or 0)
    excluded = int(reported_variant.get("selected_without_closed_count") or 0)
    rows = []
    for metric_name in (
        "net_R_avg",
        "total_net_R",
        "profit_factor",
        "MFE_R",
        "MAE_R",
        "time_cut",
        "bad_time_cut",
        "max_drawdown",
        "PF",
        "closed_trades",
    ):
        rows.append(
            {
                "metric_name": metric_name,
                "source_artifact": source_artifact,
                "source_row_type": "closed_trade",
                "included_row_count": closed,
                "excluded_row_count": excluded,
                "filter_condition": "closed_trade == true",
                "can_enter_performance_metrics": True,
            }
        )
    rows.append(
        {
            "metric_name": "selected_trades",
            "source_artifact": source_artifact,
            "source_row_type": "selected_candidate",
            "included_row_count": int(reported_variant.get("selected_trades") or 0),
            "excluded_row_count": 0,
            "filter_condition": "selected by variant priority; not a performance metric",
            "can_enter_performance_metrics": False,
        }
    )
    return rows
