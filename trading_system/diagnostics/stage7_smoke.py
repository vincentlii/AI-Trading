from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Stage7SmokePlan:
    selected_candidates: int
    grouped_rows: tuple[dict[str, object], ...]
    required_fields: tuple[str, ...]
    formal_conclusion_enabled: bool
    report: str


REQUIRED_FIELDS = (
    "cost_tier",
    "fee",
    "spread",
    "slippage",
    "funding_paid_or_received",
    "mae_R",
    "mfe_R",
    "exit_reason",
    "max_drawdown",
    "same_bar_ambiguous_count",
    "direction",
    "asset",
    "profile",
)


def build_stage7_smoke_plan(
    *,
    filter_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
    combo: str,
    cost_tiers: Sequence[str] = ("base", "stress", "harsh"),
) -> Stage7SmokePlan:
    selected = tuple(row for row in filter_rows if _matches_combo(row, combo) and _truthy(row.get("formal_approved")))
    execution_by_id = {str(row.get("candidate_id", "")): row for row in execution_rows}
    grouped = _grouped_rows(selected, execution_by_id, cost_tiers)
    report = _report(combo=combo, selected=len(selected), grouped=grouped, cost_tiers=cost_tiers)
    return Stage7SmokePlan(
        selected_candidates=len(selected),
        grouped_rows=grouped,
        required_fields=REQUIRED_FIELDS,
        formal_conclusion_enabled=False,
        report=report,
    )


def _grouped_rows(
    candidates: Sequence[Mapping[str, object]],
    execution_by_id: Mapping[str, Mapping[str, object]],
    cost_tiers: Sequence[str],
) -> tuple[dict[str, object], ...]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        for tier in cost_tiers:
            groups[
                (
                    str(tier),
                    str(candidate.get("asset", "")),
                    str(candidate.get("profile", "")),
                    str(candidate.get("direction", "")),
                )
            ].append(candidate)

    rows: list[dict[str, object]] = []
    for key, group in sorted(groups.items()):
        executions = [execution_by_id[str(row.get("candidate_id", ""))] for row in group if str(row.get("candidate_id", "")) in execution_by_id]
        exits = Counter(str(row.get("exit_reason", "")) for row in executions if row.get("exit_reason"))
        rows.append(
            {
                "cost_tier": key[0],
                "asset": key[1],
                "profile": key[2],
                "direction": key[3],
                "selected_candidates": len(group),
                "closed_trades": len(executions),
                "MAE_R_avg": _avg(_values(executions, "mae_R")),
                "MFE_R_avg": _avg(_values(executions, "mfe_R")),
                "net_R_avg": _avg(_values(executions, "net_R")),
                "fee": sum(_float(row.get("fee")) or _float(row.get("fees")) or 0.0 for row in executions),
                "spread": sum(_float(row.get("spread")) or 0.0 for row in executions),
                "slippage": sum(_float(row.get("slippage")) or 0.0 for row in executions),
                "exit_reason_top": exits.most_common(1)[0][0] if exits else "",
                "same_bar_ambiguous_count": sum(1 for row in executions if _truthy(row.get("same_bar_ambiguous"))),
                "funding_paid_or_received": sum(_float(row.get("funding_paid_or_received")) or 0.0 for row in executions),
                "max_drawdown": _max_drawdown(_values(executions, "net_R")),
                "proposal_only": True,
            }
        )
    return tuple(rows)


def _matches_combo(row: Mapping[str, object], combo: str) -> bool:
    name = combo.strip()
    if name in {"displacement_after_reclaim", "displacement"}:
        return _truthy(row.get("displacement_after_reclaim"))
    if name == "displacement_after_reclaim + high_wick":
        return _truthy(row.get("displacement_after_reclaim")) and _is_high_wick(row)
    if name == "high_sweep_rvol + CHOCH true + high_wick":
        return _is_high_sweep(row) and _is_choch(row) and _is_high_wick(row)
    if name == "high_sweep_rvol + CHOCH true":
        return _is_high_sweep(row) and _is_choch(row)
    if name == "high_sweep_rvol + high_wick":
        return _is_high_sweep(row) and _is_high_wick(row)
    if name == "high_sweep_rvol":
        return _is_high_sweep(row)
    if name in {"CHOCH true", "CHOCH true only"}:
        return _is_choch(row)
    if name in {"high_wick", "high_wick only"}:
        return _is_high_wick(row)
    if name == "ETH C short":
        return row.get("asset") == "ETH" and row.get("profile") == "C" and row.get("direction") == "short"
    return False


def _report(*, combo: str, selected: int, grouped: Sequence[Mapping[str, object]], cost_tiers: Sequence[str]) -> str:
    lines = [
        "# Stage 7 Smoke Full Backtest Framework",
        "",
        f"- combo={combo}",
        f"- selected_candidates={selected}",
        f"- cost_tiers={','.join(cost_tiers)}",
        "- status=framework_only",
        "- proposal_only=true",
        "- formal_conclusion_enabled=false",
        "",
        "## Required Outputs",
        *[f"- {field}" for field in REQUIRED_FIELDS],
        "",
        "## Grouped Preview",
    ]
    for row in grouped:
        lines.append(
            f"- {row['cost_tier']} {row['asset']} {row['profile']} {row['direction']}: "
            f"selected={row['selected_candidates']} closed={row['closed_trades']} MFE={row['MFE_R_avg']} "
            f"net_R={row['net_R_avg']} exit={row['exit_reason_top']} same_bar={row['same_bar_ambiguous_count']}"
        )
    lines.append("")
    lines.append("This framework does not run Stage 7 conclusions and does not formalize capped sizing.")
    return "\n".join(lines) + "\n"


def _is_high_sweep(row: Mapping[str, object]) -> bool:
    return row.get("sweep_rvol_tier") == "high_sweep_rvol"


def _is_choch(row: Mapping[str, object]) -> bool:
    return row.get("choch_tag") == "choch_true" or row.get("choch_detected") is True


def _is_high_wick(row: Mapping[str, object]) -> bool:
    return row.get("wick_ratio_tier") == "high_wick" or row.get("wick_tier") == "high_wick"


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _values(rows: Sequence[Mapping[str, object]], field: str) -> list[float]:
    return [value for row in rows if (value := _float(row.get(field))) is not None]


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: Sequence[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    high = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        high = max(high, equity)
        drawdown = max(drawdown, high - equity)
    return drawdown


__all__ = ("Stage7SmokePlan", "build_stage7_smoke_plan")
