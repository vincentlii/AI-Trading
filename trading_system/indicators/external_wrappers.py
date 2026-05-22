from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from dataclasses import dataclass

from trading_system.indicators.regime import average_true_range, exponential_moving_average


@dataclass(frozen=True)
class ExternalIndicatorCheck:
    name: str
    status: str
    source: str
    internal_value: float
    external_value: float | None
    delta: float | None
    tolerance: float
    reason_codes: tuple[str, ...]


def external_ema_check(
    values: Sequence[float],
    *,
    period: int,
    tolerance: float = 1e-9,
) -> ExternalIndicatorCheck:
    internal_value = exponential_moving_average(values, period)
    external_value, source = _talib_ema(values, period)
    return _check_result(
        name="external.ema",
        internal_value=internal_value,
        external_value=external_value,
        source=source,
        tolerance=tolerance,
    )


def external_atr_check(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int,
    tolerance: float = 1e-9,
) -> ExternalIndicatorCheck:
    internal_value = average_true_range(highs, lows, closes, period)
    external_value, source = _talib_atr(highs, lows, closes, period)
    return _check_result(
        name="external.atr",
        internal_value=internal_value,
        external_value=external_value,
        source=source,
        tolerance=tolerance,
    )


def _check_result(
    *,
    name: str,
    internal_value: float,
    external_value: float | None,
    source: str,
    tolerance: float,
) -> ExternalIndicatorCheck:
    if external_value is None:
        return ExternalIndicatorCheck(
            name=name,
            status="external_missing",
            source="internal_reference",
            internal_value=internal_value,
            external_value=None,
            delta=None,
            tolerance=tolerance,
            reason_codes=("optional_indicator_library_missing",),
        )

    delta = abs(internal_value - external_value)
    return ExternalIndicatorCheck(
        name=name,
        status="matched" if delta <= tolerance else "mismatch",
        source=source,
        internal_value=internal_value,
        external_value=external_value,
        delta=delta,
        tolerance=tolerance,
        reason_codes=() if delta <= tolerance else ("external_indicator_delta_above_tolerance",),
    )


def _talib_ema(values: Sequence[float], period: int) -> tuple[float | None, str]:
    if importlib.util.find_spec("talib") is None:
        return None, "talib_missing"
    try:
        import talib

        result = talib.EMA(tuple(float(value) for value in values), timeperiod=period)
        return float(result[-1]), "talib"
    except Exception:
        return None, "talib_error"


def _talib_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> tuple[float | None, str]:
    if importlib.util.find_spec("talib") is None:
        return None, "talib_missing"
    try:
        import talib

        result = talib.ATR(
            tuple(float(value) for value in highs),
            tuple(float(value) for value in lows),
            tuple(float(value) for value in closes),
            timeperiod=period,
        )
        return float(result[-1]), "talib"
    except Exception:
        return None, "talib_error"


__all__ = (
    "ExternalIndicatorCheck",
    "external_atr_check",
    "external_ema_check",
)
