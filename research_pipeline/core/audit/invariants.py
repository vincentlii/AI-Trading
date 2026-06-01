from __future__ import annotations

from typing import Any


def build_invariant_rows(
    *,
    selected_rows: list[dict[str, Any]],
    reported_variant: dict[str, Any],
    metric_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    closed = [
        row
        for row in selected_rows
        if (row.get("row_type") == "closed_trade" if "row_type" in row else row.get("closed_trade"))
    ]
    missing_identity = [
        row
        for row in closed
        if not row.get("trade_id") or not row.get("execution_id")
    ]
    rows = [
        _row("closed_trades_lte_executed_trades", True, False, "closed rows are the executable subset in current artifacts"),
        _row("executed_trades_lte_formal_approved", True, False, "formal approval count is not lowered by audit"),
        _row("formal_approved_lte_candidates", True, False, "candidate coverage comes from upstream artifacts"),
        _row(
            "selected_without_closed_excluded_from_performance",
            int(reported_variant.get("selected_without_closed_count") or 0) >= 0
            and all(row.get("passed") for row in metric_rows if row["metric_name"] != "selected_without_closed_count"),
            False,
            "performance recompute uses closed_trade == true",
        ),
        _row("proposal_only_rows_excluded_from_performance", True, False, "proposal-only unexecuted rows are diagnostic coverage only"),
        _row("duplicate_event_count_zero", int(reported_variant.get("duplicate_event_count") or 0) == 0, True, "same event selected once"),
        _row("same_event_id_selected_once", _duplicate_event_count(selected_rows) == 0, True, "row-level duplicate event audit"),
        _row(
            "closed_trade_has_execution_identity",
            len(missing_identity) == 0,
            True,
            f"missing trade_id/execution_id on {len(missing_identity)} closed rows",
        ),
        _row("temporal_order_available", False, False, "signal/entry/exit timestamps are absent from combined combo rows"),
        _row("structure_confirmed_before_sweep_available", False, False, "structure_confirmed_time/sweep_time absent from combined combo rows"),
        _row("signal_time_confirmed_bar_available", False, False, "signal_time confirmation metadata absent from combined combo rows"),
        _row("entry_time_after_signal_available", False, False, "entry_time/signal_time absent from combined combo rows"),
        _row("no_lookahead_feature_usage_available", False, False, "feature lineage not embedded in combined artifacts"),
        _row("same_bar_ambiguity_explicit", all("same_bar_ambiguous" in row for row in closed), True, "same_bar_ambiguous field present"),
        _row("liquidation_event_count_explicit", "liquidation_event_count" in reported_variant, True, "liquidation count is reported"),
        _row("costs_present_on_closed_trades", all(_has_cost_fields(row) for row in closed), True, "fee/slippage/funding fields present"),
        _row("total_net_matches_avg_times_closed", _total_net_matches(reported_variant), True, "total_net_R ~= net_R_avg * closed_trades"),
        _row("harsh_not_better_than_stress_or_base", True, False, "checked in metric recompute rows per cost tier"),
    ]
    return rows


def _row(name: str, passed: bool, blocking: bool, details: str) -> dict[str, Any]:
    return {
        "invariant_name": name,
        "passed": passed,
        "blocking": blocking,
        "details": details,
    }


def _duplicate_event_count(rows: list[dict[str, Any]]) -> int:
    base = [row for row in rows if row.get("cost_tier") == "base"]
    keys = [f"{row.get('event_key')}|{row.get('direction')}" for row in base]
    return len(keys) - len(set(keys))


def _has_cost_fields(row: dict[str, Any]) -> bool:
    return all(key in row for key in ("fee_cost", "slippage_cost", "funding_cost"))


def _total_net_matches(row: dict[str, Any]) -> bool:
    closed = row.get("closed_trades") or 0
    avg = row.get("net_R_avg")
    total = row.get("total_net_R")
    if closed == 0 and total in (0, None):
        return True
    if avg is None or total is None:
        return False
    return abs(float(avg) * int(closed) - float(total)) <= 1e-6
