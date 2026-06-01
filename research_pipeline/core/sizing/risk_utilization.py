from __future__ import annotations


def risk_utilization_ratio(actual_risk_pct: float | None, target_risk_pct: float | None) -> float | None:
    if actual_risk_pct is None or target_risk_pct in (None, 0):
        return None
    return float(actual_risk_pct) / float(target_risk_pct)


def classify_actual_risk_pct(actual_risk_pct: float | None) -> str | None:
    if actual_risk_pct is None:
        return None
    value = float(actual_risk_pct)
    if value < 0.001:
        return "tiny_risk"
    if value < 0.002:
        return "low_risk"
    if value < 0.0035:
        return "medium_risk"
    return "near_target_risk"
