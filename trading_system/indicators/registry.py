from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorMetadata:
    name: str
    category: str
    default_lookback: int | None
    description: str


_INDICATORS = {
    "regime.true_range": IndicatorMetadata(
        name="regime.true_range",
        category="regime",
        default_lookback=None,
        description="Largest intrabar or gap distance for a candle.",
    ),
    "regime.kaufman_efficiency_ratio": IndicatorMetadata(
        name="regime.kaufman_efficiency_ratio",
        category="regime",
        default_lookback=14,
        description="Signal-to-noise ratio between net movement and total path movement.",
    ),
    "regime.choppiness_index": IndicatorMetadata(
        name="regime.choppiness_index",
        category="regime",
        default_lookback=14,
        description="Fractal-style trend versus chop classifier.",
    ),
    "regime.classify_regime": IndicatorMetadata(
        name="regime.classify_regime",
        category="regime",
        default_lookback=14,
        description="Initial ER/CHOP market-regime classifier.",
    ),
    "regime.ema": IndicatorMetadata(
        name="regime.ema",
        category="regime",
        default_lookback=14,
        description="Exponentially weighted moving average of a value sequence.",
    ),
    "regime.atr": IndicatorMetadata(
        name="regime.atr",
        category="regime",
        default_lookback=14,
        description="Average true range over the latest lookback window.",
    ),
    "regime.adx_dmi": IndicatorMetadata(
        name="regime.adx_dmi",
        category="regime",
        default_lookback=14,
        description="Directional movement and ADX trend-strength indicator.",
    ),
    "regime.ttm_squeeze": IndicatorMetadata(
        name="regime.ttm_squeeze",
        category="regime",
        default_lookback=20,
        description="TTM squeeze state using Bollinger bands inside Keltner channels.",
    ),
}


def list_indicators() -> tuple[IndicatorMetadata, ...]:
    return tuple(_INDICATORS[name] for name in sorted(_INDICATORS))


def get_indicator(name: str) -> IndicatorMetadata:
    try:
        return _INDICATORS[name]
    except KeyError as error:
        raise KeyError(f"Unknown indicator: {name}") from error
