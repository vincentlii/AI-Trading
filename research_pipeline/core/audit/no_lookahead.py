from __future__ import annotations

from typing import Any


TIME_FIELD_CHECKS = (
    ("feature_cutoff_time_lte_signal_time", ("feature_cutoff_time", "signal_time")),
    ("structure_confirmed_time_lte_sweep_time", ("structure_confirmed_time", "sweep_time")),
    ("sweep_time_lte_reclaim_time", ("sweep_time", "reclaim_time")),
    ("reclaim_time_lte_signal_time", ("reclaim_time", "signal_time")),
    ("signal_time_lt_entry_time", ("signal_time", "entry_time")),
    ("entry_time_lte_exit_time", ("entry_time", "exit_time")),
)


def build_no_lookahead_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for check_name, fields in TIME_FIELD_CHECKS:
        available = sum(1 for row in rows if all(row.get(field) not in (None, "") for field in fields))
        output.append(
            {
                "check_name": check_name,
                "checked_rows": available,
                "unverifiable_rows": len(rows) - available,
                "passed": available == len(rows) and len(rows) > 0,
                "blocking": available == 0,
                "details": "required temporal fields are missing" if available == 0 else "temporal fields available",
            }
        )
    output.extend(
        [
            _field_check("bar_confirmed_true", rows, "bar_confirmed"),
            _field_check("same_bar_ambiguity_pessimistic", rows, "same_bar_ambiguous"),
            _field_check("no_lookahead_feature_usage", rows, "no_lookahead_safe"),
        ]
    )
    return output


def _field_check(check_name: str, rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if field in row)
    return {
        "check_name": check_name,
        "checked_rows": available,
        "unverifiable_rows": len(rows) - available,
        "passed": available == len(rows) and len(rows) > 0,
        "blocking": available == 0,
        "details": f"{field} missing from selected rows" if available == 0 else f"{field} available",
    }
