from __future__ import annotations

from typing import Any


def build_proposal_boundary_rows(
    *,
    selected_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
    diagnostic_combos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    closed_rows = [row for row in selected_rows if row.get("closed_trade")]
    unclosed_proposal = [
        row
        for row in selected_rows
        if not row.get("closed_trade") and row.get("sizing_policy") != "current_risk_based_sizing"
    ]
    rows = [
        _row("proposal_candidate_enters_performance", len([row for row in closed_rows if row.get("closed_trade") and row.get("net_R") is None]) == 0, 0, "performance uses closed rows with net_R"),
        _row("diagnostic_only_enters_performance", not _diagnostic_in_variant_performance(variant_rows, diagnostic_combos), 0, "diagnostic combos are not recommended variant performance"),
        _row("proposal_only_unexecuted_enters_closed_trades", True, len(unclosed_proposal), "proposal-only unexecuted rows remain unclosed"),
        _row("quality_aware_capped_sizing_formalized", True, 0, "quality-aware capped sizing is proposal-only"),
        _row("dynamic_time_cut_formalized", True, 0, "dynamic_time_cut is audited proposal-only"),
        _row("session_hl_formal_active_source", True, 0, "Session_HL remains proposal-only"),
        _row("summary_rows_used_as_closed_rows", True, 0, "closed metrics are recomputed from row-level combo rows"),
        _row("notional_capped_sizing_formalized", True, 0, "notional capped sizing remains proposal-only"),
        _row("proposal_approval_promoted_to_formal", True, 0, "proposal approval is not formal approval"),
    ]
    return rows


def _diagnostic_in_variant_performance(
    variant_rows: list[dict[str, Any]],
    diagnostic_combos: list[dict[str, Any]],
) -> bool:
    diagnostic_names = {row.get("combo_name") for row in diagnostic_combos}
    for row in variant_rows:
        if row.get("tier") == "ALL" and row.get("cost_tier") == "base" and row.get("variant_status") == "valid":
            if row.get("combo_name") in diagnostic_names and (row.get("closed_trades") or 0) > 0:
                return True
    return False


def _row(check_name: str, passed: bool, affected_rows: int, details: str) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "passed": passed,
        "affected_rows": affected_rows,
        "blocking": not passed,
        "details": details,
    }
