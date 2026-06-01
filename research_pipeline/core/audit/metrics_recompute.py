from __future__ import annotations

from typing import Any, Iterable


PERFORMANCE_METRICS = {
    "net_R_avg",
    "total_net_R",
    "profit_factor",
    "MFE_R_avg",
    "MAE_R_avg",
    "time_cut_exit_rate",
    "bad_time_cut_ratio",
    "max_drawdown",
}


def recompute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [row for row in rows if _is_closed_trade_row(row)]
    net = [_float(row.get("net_R")) for row in closed]
    mfe = [_float(row.get("mfe_R")) for row in closed]
    mae = [_float(row.get("mae_R")) for row in closed]
    time_cut = [row for row in closed if row.get("time_cut_exit")]
    total_net = sum(value for value in net if value is not None)
    return {
        "closed_trades": len(closed),
        "net_R_avg": _avg(net),
        "total_net_R": total_net,
        "profit_factor": _profit_factor([value for value in net if value is not None]),
        "MFE_R_avg": _avg(mfe),
        "MAE_R_avg": _avg(mae),
        "time_cut_exit_rate": _ratio(len(time_cut), len(closed)),
        "bad_time_cut_ratio": _ratio(sum(1 for row in time_cut if row.get("loss_time_cut")), len(time_cut)),
        "duplicate_event_count": duplicate_event_count(rows),
        "selected_without_closed_count": sum(1 for row in rows if not _is_closed_trade_row(row)),
        "max_drawdown": _max_drawdown([value or 0.0 for value in net]),
    }


def comparison_rows(
    *,
    scope: str,
    cost_tier: str,
    reported: dict[str, Any],
    recomputed: dict[str, Any],
    source_artifact: str,
    tolerance: float = 1e-6,
) -> list[dict[str, Any]]:
    rows = []
    for metric_name in (
        "closed_trades",
        "net_R_avg",
        "total_net_R",
        "profit_factor",
        "MFE_R_avg",
        "MAE_R_avg",
        "time_cut_exit_rate",
        "bad_time_cut_ratio",
        "duplicate_event_count",
        "selected_without_closed_count",
    ):
        reported_value = reported.get(metric_name)
        recomputed_value = recomputed.get(metric_name)
        diff = _diff(reported_value, recomputed_value)
        is_count = metric_name in {"closed_trades", "duplicate_event_count", "selected_without_closed_count"}
        passed = reported_value == recomputed_value if is_count else diff is not None and diff <= tolerance
        rows.append(
            {
                "scope": scope,
                "cost_tier": cost_tier,
                "metric_name": metric_name,
                "reported_value": reported_value,
                "recomputed_value": recomputed_value,
                "diff": diff,
                "tolerance": 0 if is_count else tolerance,
                "passed": passed,
                "source_artifact": source_artifact,
            }
        )
    return rows


def duplicate_event_count(rows: list[dict[str, Any]]) -> int:
    base = [row for row in rows if row.get("cost_tier") == "base"]
    keys = [f"{row.get('event_key')}|{row.get('direction')}" for row in base]
    return len(keys) - len(set(keys))


def _is_closed_trade_row(row: dict[str, Any]) -> bool:
    if "row_type" in row:
        return row.get("row_type") == "closed_trade" and bool(row.get("closed_trade"))
    return bool(row.get("closed_trade"))


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else sum(clean) / len(clean)


def _ratio(count: int, total: int) -> float | None:
    return None if total == 0 else count / total


def _profit_factor(values: Iterable[float]) -> float | None:
    clean = list(values)
    wins = sum(value for value in clean if value > 0)
    losses = abs(sum(value for value in clean if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return abs(max_dd)


def _diff(left: Any, right: Any) -> float | None:
    left_float = _float(left)
    right_float = _float(right)
    if left_float is None and right_float is None:
        return 0.0
    if left_float is None or right_float is None:
        return None
    return abs(left_float - right_float)
