from __future__ import annotations

from typing import Any, Sequence


TIME_FIELD_CHECKS = (
    ("feature_cutoff_time_lte_signal_time", ("feature_cutoff_time", "signal_time")),
    ("structure_confirmed_time_lte_sweep_time", ("structure_confirmed_time", "sweep_time")),
    ("sweep_time_lte_reclaim_time", ("sweep_time", "reclaim_time")),
    ("reclaim_time_lte_signal_time", ("reclaim_time", "signal_time")),
    ("signal_time_lt_entry_time", ("signal_time", "entry_time")),
    ("entry_time_lte_exit_time", ("entry_time", "exit_time")),
)


def build_no_lookahead_rows(
    rows: list[dict[str, Any]],
    *,
    time_field_checks: Sequence[Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    output = []
    for check_name, fields in _normalized_checks(time_field_checks):
        available_rows = [row for row in rows if all(row.get(field) not in (None, "") for field in fields)]
        failed = sum(1 for row in available_rows if not _time_order_ok(row, fields))
        output.append(
            {
                "check_name": check_name,
                "checked_rows": len(available_rows),
                "unverifiable_rows": len(rows) - len(available_rows),
                "failed_rows": failed,
                "passed": len(available_rows) == len(rows) and len(rows) > 0 and failed == 0,
                "blocking": len(available_rows) == 0 or failed > 0,
                "details": _time_details(len(available_rows), failed),
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


def _normalized_checks(checks: Sequence[Sequence[str]] | None) -> tuple[tuple[str, tuple[str, str]], ...]:
    if checks is None:
        return TIME_FIELD_CHECKS
    normalized = []
    for check in checks:
        if len(check) != 3:
            continue
        normalized.append((str(check[0]), (str(check[1]), str(check[2]))))
    return tuple(normalized)


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


def _time_order_ok(row: dict[str, Any], fields: tuple[str, str]) -> bool:
    left = _to_int(row.get(fields[0]))
    right = _to_int(row.get(fields[1]))
    if left is None or right is None:
        return False
    if fields[0] == "signal_time" and fields[1] == "entry_time":
        return left < right
    return left <= right


def _time_details(available: int, failed: int) -> str:
    if available == 0:
        return "required temporal fields are missing"
    if failed:
        return "temporal ordering failed"
    return "temporal ordering verified"


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
