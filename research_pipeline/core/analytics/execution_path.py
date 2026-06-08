from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from statistics import median


def enrich_execution_path_rows(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    enriched: list[dict[str, object]] = []
    for row in rows:
        if row.get("row_type") != "closed_trade":
            continue
        mfe = _num(_first(row, "mfe_R", "MFE_R")) or 0.0
        mae = abs(_num(_first(row, "mae_R", "MAE_R")) or 0.0)
        final_r = _num(_first(row, "net_R", "r_multiple")) or 0.0
        gross_r = _num(_first(row, "gross_R", "gross_r"))
        if gross_r is None:
            gross_r = final_r + _cost_per_r(row)
        bars_to_mfe = _int(_first(row, "bars_to_mfe", "time_to_MFE_bars")) or 0
        bars_to_mae = _int(_first(row, "bars_to_mae", "time_to_MAE_bars")) or 0
        holding = _int(_first(row, "holding_bars", "bars_in_trade")) or 0
        cost_per_r = _cost_per_r(row)
        exit_efficiency = None if mfe <= 0 else final_r / mfe
        giveback = mfe - final_r
        cost_flipped = gross_r > 0 and final_r <= 0
        positive_mfe_loss = mfe > 0 and final_r <= 0
        early_mae = bars_to_mae > 0 and (bars_to_mfe <= 0 or bars_to_mae <= bars_to_mfe) and mae >= 0.5
        enriched.append(
            {
                **dict(row),
                "final_R": final_r,
                "gross_final_R": gross_r,
                "MAE_R": mae,
                "MFE_R": mfe,
                "MFE_minus_final_R": giveback,
                "MFE_to_MAE_ratio": None if mae <= 0 else mfe / mae,
                "time_to_MFE_bars": bars_to_mfe,
                "time_to_MAE_bars": bars_to_mae,
                "entry_to_MFE_bars": bars_to_mfe,
                "entry_to_MAE_bars": bars_to_mae,
                "bars_in_trade": holding,
                "exit_bar_index": _int(row.get("exit_bar_index")) or holding,
                "exit_efficiency": exit_efficiency,
                "profit_giveback_R": giveback,
                "profit_giveback_pct": None if mfe <= 0 else giveback / mfe,
                "reached_0_5R": mfe >= 0.5,
                "reached_0_75R": mfe >= 0.75,
                "reached_1R": mfe >= 1.0,
                "reached_1_5R": mfe >= 1.5,
                "reached_2R": mfe >= 2.0,
                "hit_stop_after_positive_MFE": positive_mfe_loss and str(row.get("exit_reason") or "") == "stop_loss",
                "positive_MFE_but_final_loss": positive_mfe_loss,
                "positive_MFE_but_small_final": mfe >= 0.5 and 0 < final_r < 0.1,
                "final_loss_after_1R_MFE": mfe >= 1.0 and final_r <= 0,
                "early_MAE_R": mae if early_mae else 0.0,
                "early_adverse_move_flag": early_mae,
                "MAE_before_MFE": bars_to_mae > 0 and (bars_to_mfe <= 0 or bars_to_mae <= bars_to_mfe),
                "MFE_before_MAE": bars_to_mfe > 0 and (bars_to_mae <= 0 or bars_to_mfe < bars_to_mae),
                "cost_per_R": cost_per_r,
                "cost_as_pct_of_MFE": None if mfe <= 0 else cost_per_r / mfe,
                "cost_as_pct_of_final_gross_R": None if gross_r <= 0 else cost_per_r / gross_r,
                "would_be_profitable_before_cost": gross_r > 0,
                "cost_flipped_to_loss": cost_flipped,
                "signal_bad_candidate": mfe < 0.3 and mae >= 0.5,
                "entry_too_early_candidate": early_mae,
                "entry_too_late_candidate": mfe < 0.5 and final_r <= 0 and not early_mae,
                "exit_too_late_candidate": mfe >= 0.75 and giveback >= 0.5,
                "target_too_far_candidate": mfe >= 1.0 and final_r <= 0,
                "stop_too_wide_candidate": mae > 1.2 and str(row.get("exit_reason") or "") != "stop_loss",
                "stop_too_tight_candidate": str(row.get("exit_reason") or "") == "stop_loss" and mfe >= 0.5,
                "cost_too_high_candidate": cost_flipped or (mfe > 0 and cost_per_r / max(mfe, 1e-12) >= 0.25),
                "good_signal_bad_exit_candidate": mfe >= 0.75 and final_r <= 0,
                "good_signal_good_exit_candidate": mfe >= 0.75 and final_r > 0 and (exit_efficiency or 0.0) >= 0.35,
                "no_edge_candidate": mfe < 0.3 and final_r <= 0,
            }
        )
    return tuple(enriched)


def summarize_execution_path_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    closed = [dict(row) for row in rows if row.get("row_type") == "closed_trade"]
    count = len(closed)
    mfe = [_num(row.get("MFE_R")) for row in closed]
    mae = [_num(row.get("MAE_R")) for row in closed]
    efficiency = [_num(row.get("exit_efficiency")) for row in closed]
    giveback = [_num(row.get("profit_giveback_R")) for row in closed]
    final_r = [_num(row.get("final_R")) for row in closed]
    groups = {
        "final_winner": sum(1 for row in closed if (_num(row.get("final_R")) or 0.0) > 0),
        "final_loser": sum(1 for row in closed if (_num(row.get("final_R")) or 0.0) <= 0),
        "positive_MFE_but_final_loss": sum(1 for row in closed if row.get("positive_MFE_but_final_loss")),
        "MFE_ge_0_5_final_le_0": sum(1 for row in closed if (_num(row.get("MFE_R")) or 0.0) >= 0.5 and (_num(row.get("final_R")) or 0.0) <= 0),
        "MFE_ge_1_0_final_le_0": sum(1 for row in closed if (_num(row.get("MFE_R")) or 0.0) >= 1.0 and (_num(row.get("final_R")) or 0.0) <= 0),
        "MAE_ge_0_5_before_MFE": sum(1 for row in closed if row.get("early_adverse_move_flag")),
        "never_reached_0_5R_MFE": sum(1 for row in closed if (_num(row.get("MFE_R")) or 0.0) < 0.5),
        "cost_flipped_winner_to_loser": sum(1 for row in closed if row.get("cost_flipped_to_loss")),
    }
    label_counts = {
        name: sum(1 for row in closed if row.get(name))
        for name in (
            "signal_bad_candidate",
            "good_signal_bad_exit_candidate",
            "entry_too_early_candidate",
            "exit_too_late_candidate",
            "target_too_far_candidate",
            "cost_too_high_candidate",
            "no_edge_candidate",
        )
    }
    return {
        "closed_trades": count,
        "MAE_R_avg": _avg(mae),
        "MAE_R_median": _pct(mae, 50),
        "MAE_R_p25": _pct(mae, 25),
        "MAE_R_p75": _pct(mae, 75),
        "MAE_R_p90": _pct(mae, 90),
        "MFE_R_avg": _avg(mfe),
        "MFE_R_median": _pct(mfe, 50),
        "MFE_R_p25": _pct(mfe, 25),
        "MFE_R_p75": _pct(mfe, 75),
        "MFE_R_p90": _pct(mfe, 90),
        "MFE_to_MAE_ratio_avg": _avg([_num(row.get("MFE_to_MAE_ratio")) for row in closed]),
        "exit_efficiency_avg": _avg(efficiency),
        "exit_efficiency_median": _pct(efficiency, 50),
        "profit_giveback_R_avg": _avg(giveback),
        "profit_giveback_R_median": _pct(giveback, 50),
        "MFE_ge_0_4R": sum(1 for row in closed if (_num(row.get("MFE_R")) or 0.0) >= 0.4),
        "MFE_ge_0_4R_share": _share(sum(1 for row in closed if (_num(row.get("MFE_R")) or 0.0) >= 0.4), count),
        "MFE_ge_0_5R": sum(1 for row in closed if (_num(row.get("MFE_R")) or 0.0) >= 0.5),
        "reached_0_5R_share": _share(sum(1 for row in closed if row.get("reached_0_5R")), count),
        "reached_0_75R_share": _share(sum(1 for row in closed if row.get("reached_0_75R")), count),
        "reached_1R_share": _share(sum(1 for row in closed if row.get("reached_1R")), count),
        "positive_MFE_but_final_loss": groups["positive_MFE_but_final_loss"],
        "positive_MFE_but_final_loss_share": _share(groups["positive_MFE_but_final_loss"], count),
        "MFE_ge_0_5_final_le_0": groups["MFE_ge_0_5_final_le_0"],
        "MFE_ge_0_5_final_le_0_share": _share(groups["MFE_ge_0_5_final_le_0"], count),
        "MFE_ge_1R_final_le_0": groups["MFE_ge_1_0_final_le_0"],
        "MFE_ge_1R_final_le_0_share": _share(groups["MFE_ge_1_0_final_le_0"], count),
        "hit_stop_after_positive_MFE": sum(1 for row in closed if row.get("hit_stop_after_positive_MFE")),
        "cost_flipped_to_loss": groups["cost_flipped_winner_to_loser"],
        "cost_flipped_to_loss_share": _share(groups["cost_flipped_winner_to_loser"], count),
        "never_reached_0_5R_MFE": groups["never_reached_0_5R_MFE"],
        "never_reached_0_5R_MFE_share": _share(groups["never_reached_0_5R_MFE"], count),
        "early_MAE": groups["MAE_ge_0_5_before_MFE"],
        "early_MAE_share": _share(groups["MAE_ge_0_5_before_MFE"], count),
        "path_group_counts": groups,
        "attribution_counts": label_counts,
        "final_R_avg": _avg(final_r),
        "final_R_median": _pct(final_r, 50),
        "exit_reason_distribution": dict(Counter(str(row.get("exit_reason") or "unknown") for row in closed)),
    }


def compare_retained_removed_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    closed = [dict(row) for row in rows if row.get("row_type") == "closed_trade"]
    retained = [row for row in closed if row.get("retained_by_admission")]
    removed = [row for row in closed if row.get("removed_by_admission")]
    return {
        "retained_count": len(retained),
        "removed_count": len(removed),
        "retained_avg_R": _avg([_num(row.get("final_R")) or _num(row.get("net_R")) for row in retained]),
        "removed_avg_R": _avg([_num(row.get("final_R")) or _num(row.get("net_R")) for row in removed]),
        "retained_harsh_R": _avg([_num(row.get("final_R")) or _num(row.get("net_R")) for row in retained if row.get("cost_tier") == "harsh"]),
        "removed_harsh_R": _avg([_num(row.get("final_R")) or _num(row.get("net_R")) for row in removed if row.get("cost_tier") == "harsh"]),
        "retained_median_R": _pct([_num(row.get("final_R")) or _num(row.get("net_R")) for row in retained], 50),
        "removed_median_R": _pct([_num(row.get("final_R")) or _num(row.get("net_R")) for row in removed], 50),
        "retained_cost_per_R": _avg([_num(row.get("cost_per_R")) for row in retained]),
        "removed_cost_per_R": _avg([_num(row.get("cost_per_R")) for row in removed]),
    }


def _cost_per_r(row: Mapping[str, object]) -> float:
    direct = _num(row.get("cost_per_R"))
    if direct is not None:
        return direct
    risk = _num(row.get("actual_risk_after_cap")) or _num(row.get("risk_amount")) or 0.0
    cost = sum(_num(row.get(key)) or 0.0 for key in ("fee_cost", "slippage_cost", "funding_cost", "fee", "spread"))
    if risk <= 0:
        return 0.0
    return cost / risk


def _first(row: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _num(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _avg(values: Sequence[float | None]) -> float | None:
    nums = [float(value) for value in values if value is not None]
    return None if not nums else sum(nums) / len(nums)


def _pct(values: Sequence[float | None], percentile: int) -> float | None:
    nums = sorted(float(value) for value in values if value is not None)
    if not nums:
        return None
    if percentile == 50:
        return float(median(nums))
    index = (len(nums) - 1) * percentile / 100
    lower = int(index)
    upper = min(lower + 1, len(nums) - 1)
    weight = index - lower
    return nums[lower] * (1 - weight) + nums[upper] * weight


def _share(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


__all__ = ("compare_retained_removed_rows", "enrich_execution_path_rows", "summarize_execution_path_rows")
