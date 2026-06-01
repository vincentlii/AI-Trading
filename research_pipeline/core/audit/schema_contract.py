from __future__ import annotations

from typing import Any


ALLOWED_ROW_TYPES = {
    "market_bar",
    "context_row",
    "feature_row",
    "structure_level",
    "raw_candidate",
    "proposal_candidate",
    "formal_approved",
    "rejected_candidate",
    "sizing_diagnostic",
    "executed_trade",
    "closed_trade",
    "diagnostic_only",
    "summary_row",
    "report_metric",
}

ROW_TYPE_REQUIRED_FIELDS = {
    "market_bar": {"asset", "timeframe", "timestamp", "bar_confirmed", "data_hash"},
    "context_row": {"asset", "timeframe", "timestamp", "bar_confirmed", "data_hash"},
    "feature_row": {"feature_name", "feature_cutoff_time", "source_timeframe", "no_lookahead_safe"},
    "structure_level": {"structure_source", "structure_confirmed_time", "structure_price", "source_timeframe"},
    "raw_candidate": {"event_id", "candidate_id", "signal_time", "entry_time", "structure_confirmed_time"},
    "proposal_candidate": {"event_id", "candidate_id", "signal_time", "entry_time", "structure_confirmed_time"},
    "formal_approved": {"candidate_id", "formal_approved", "filter_policy"},
    "rejected_candidate": {"candidate_id", "reject_reason", "filter_policy"},
    "sizing_diagnostic": {"candidate_id", "sizing_policy", "proposal_only", "actual_risk_pct", "risk_utilization"},
    "executed_trade": {"trade_id", "execution_id", "candidate_id", "entry_time", "entry_price"},
    "closed_trade": {"trade_id", "execution_id", "exit_time", "exit_reason", "net_R", "MFE_R", "MAE_R", "fee_cost", "slippage_cost", "funding_cost"},
    "diagnostic_only": {"diagnostic_only"},
    "summary_row": {"source_artifact"},
    "report_metric": {"source_artifact", "metric_name", "source_row_type"},
}


def build_schema_contract_rows(
    *,
    artifact_name: str,
    rows: list[dict[str, Any]],
    inferred_row_type: str,
    required_fields: set[str] | None = None,
    blocking_missing_row_type: bool = False,
) -> list[dict[str, Any]]:
    required = set(required_fields or ROW_TYPE_REQUIRED_FIELDS.get(inferred_row_type, set()))
    output = []
    sample = rows[:200]
    for index, row in enumerate(sample):
        explicit = row.get("row_type")
        row_type = str(explicit or inferred_row_type)
        missing = sorted(field for field in required if field not in row or row.get(field) in (None, ""))
        output.append(
            {
                "artifact_name": artifact_name,
                "row_index": index,
                "row_type": row_type,
                "row_type_explicit": explicit is not None,
                "allowed_row_type": row_type in ALLOWED_ROW_TYPES,
                "missing_fields": missing,
                "blocking": bool(missing) or (blocking_missing_row_type and explicit is None),
                "notes": "row_type inferred for legacy artifact" if explicit is None else "",
            }
        )
    if not rows:
        output.append(
            {
                "artifact_name": artifact_name,
                "row_index": None,
                "row_type": inferred_row_type,
                "row_type_explicit": False,
                "allowed_row_type": inferred_row_type in ALLOWED_ROW_TYPES,
                "missing_fields": sorted(required),
                "blocking": False,
                "notes": "empty artifact",
            }
        )
    return output
