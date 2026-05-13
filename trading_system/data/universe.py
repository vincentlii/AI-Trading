from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from trading_system.timeframe_profiles import TimeframeProfile, list_default_profiles


DEFAULT_SYMBOLS = ("BTC-USDT", "ETH-USDT", "XAUT-USDT")
DEFAULT_PRIMARY_VENUE = "okx"
DEFAULT_VALIDATION_VENUES = ("binance",)


@dataclass(frozen=True)
class SymbolMapping:
    canonical_symbol: str
    okx_inst_id: str
    binance_symbol: str


_SYMBOL_MAPPINGS = {
    "BTC/USDT": SymbolMapping("BTC/USDT", "BTC-USDT", "BTCUSDT"),
    "ETH/USDT": SymbolMapping("ETH/USDT", "ETH-USDT", "ETHUSDT"),
    "XAUT/USDT": SymbolMapping("XAUT/USDT", "XAUT-USDT", "XAUTUSDT"),
}


def default_symbols() -> tuple[str, ...]:
    return DEFAULT_SYMBOLS


def get_symbol_mapping(canonical_symbol: str) -> SymbolMapping:
    normalized = canonical_symbol.strip().upper()
    try:
        return _SYMBOL_MAPPINGS[normalized]
    except KeyError as error:
        raise KeyError(f"Unknown canonical symbol: {canonical_symbol}") from error


def timeframe_to_okx_bar(timeframe: str) -> str:
    normalized = timeframe.strip().lower()
    if normalized.endswith("m"):
        return normalized
    if normalized.endswith("h"):
        return f"{normalized[:-1]}H"
    if normalized.endswith("d"):
        return f"{normalized[:-1]}D"
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def required_okx_bars_for_profiles(profiles: Iterable[TimeframeProfile] | None = None) -> tuple[str, ...]:
    source_profiles = list_default_profiles() if profiles is None else profiles
    bars = {timeframe_to_okx_bar(timeframe) for profile in source_profiles for timeframe in profile.timeframes}
    return tuple(sorted(bars, key=_okx_bar_duration_minutes))


def _okx_bar_duration_minutes(bar: str) -> int:
    if bar.endswith("m"):
        return int(bar[:-1])
    if bar.endswith("H"):
        return int(bar[:-1]) * 60
    if bar.endswith("D"):
        return int(bar[:-1]) * 60 * 24
    raise ValueError(f"Unsupported OKX bar: {bar}")
