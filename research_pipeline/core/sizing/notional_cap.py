from __future__ import annotations


def notional_cap_hit_ratio(hit_count: int | None, candidate_count: int | None) -> float | None:
    if hit_count is None or candidate_count in (None, 0):
        return None
    return int(hit_count) / int(candidate_count)


def classify_required_notional_to_cap_ratio(value: float | None) -> str | None:
    if value is None:
        return None
    ratio = float(value)
    if ratio <= 1.5:
        return "near_cap"
    if ratio <= 3.0:
        return "moderate_above_cap"
    if ratio <= 5.0:
        return "far_above_cap"
    return "extreme_above_cap"
