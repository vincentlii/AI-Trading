from __future__ import annotations

from typing import Any


def evaluate_smoke_readiness(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, bool]:
    sample_ok = _num(candidate, "closed_trades") >= 40
    mfe_avg_improved = _num(candidate, "MFE_R_avg") > _num(baseline, "MFE_R_avg")
    mfe_0_5_improved = _num(candidate, "MFE_R_ge_0_5_ratio") > _num(
        baseline, "MFE_R_ge_0_5_ratio"
    )
    mfe_1_0_not_worse = _num(candidate, "MFE_R_ge_1_0_ratio") >= _num(
        baseline, "MFE_R_ge_1_0_ratio"
    )
    net_not_worse = (
        _num(candidate, "net_R_avg") >= _num(baseline, "net_R_avg")
        or _num(candidate, "net_return_on_notional_avg")
        >= _num(baseline, "net_return_on_notional_avg")
    )
    time_cut_lower = _num(candidate, "time_cut_exit_rate") < _num(
        baseline, "time_cut_exit_rate"
    )
    smoke_ready = all(
        [
            sample_ok,
            mfe_avg_improved,
            mfe_0_5_improved,
            mfe_1_0_not_worse,
            net_not_worse,
            time_cut_lower,
        ]
    )
    return {
        "sample_ok": sample_ok,
        "mfe_avg_improved": mfe_avg_improved,
        "mfe_0_5_improved": mfe_0_5_improved,
        "mfe_1_0_not_worse": mfe_1_0_not_worse,
        "net_not_worse": net_not_worse,
        "time_cut_lower": time_cut_lower,
        "smoke_ready": smoke_ready,
    }


def _num(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        return 0.0
    return float(value)
