from __future__ import annotations

from typing import Any


def build_join_rows(
    *,
    mapping_diagnostics: dict[str, Any],
    variant_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [
        {
            "scope": str(mapping_diagnostics.get("combo_name")),
            "selected_count": mapping_diagnostics.get("selected_without_closed_count"),
            "closed_count": 0,
            "selected_without_closed_count": mapping_diagnostics.get("selected_without_closed_count"),
            "missing_trade_id_count": mapping_diagnostics.get("missing_trade_id_count"),
            "missing_execution_row_count": mapping_diagnostics.get("missing_execution_row_count"),
            "join_key_mismatch_count": mapping_diagnostics.get("join_key_mismatch_count"),
            "proposal_only_unexecuted_count": mapping_diagnostics.get("proposal_only_unexecuted_count"),
            "diagnostic_only_count": mapping_diagnostics.get("selected_without_closed_count"),
            "performance_includes_unclosed_rows": False,
            "fix_required": False,
            "reason": mapping_diagnostics.get("fix_applied"),
        }
    ]
    for row in variant_rows:
        if row.get("tier") != "ALL" or row.get("cost_tier") != "base":
            continue
        selected_without_closed = int(row.get("selected_without_closed_count") or 0)
        proposal_only_unexecuted = int(row.get("proposal_only_unexecuted_count") or 0)
        rows.append(
            {
                "scope": row.get("variant_name"),
                "selected_count": int(row.get("selected_trades") or 0) + selected_without_closed,
                "closed_count": row.get("closed_trades"),
                "selected_without_closed_count": selected_without_closed,
                "missing_trade_id_count": 0,
                "missing_execution_row_count": int(row.get("missing_execution_row_count") or 0),
                "join_key_mismatch_count": 0,
                "proposal_only_unexecuted_count": proposal_only_unexecuted,
                "diagnostic_only_count": proposal_only_unexecuted,
                "performance_includes_unclosed_rows": False,
                "fix_required": int(row.get("missing_execution_row_count") or 0) > 0,
                "reason": "unclosed proposal rows excluded from performance",
            }
        )
    return rows
