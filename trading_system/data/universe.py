from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from trading_system.timeframe_profiles import TimeframeProfile, list_default_profiles


DEFAULT_SYMBOLS = ("BTC-USDT", "ETH-USDT", "XAUT-USDT")
DEFAULT_PRIMARY_VENUE = "okx"
DEFAULT_VALIDATION_VENUES = ("binance",)
CRYPTO_SPOT = "CRYPTO_SPOT"
INDEX = "INDEX"


@dataclass(frozen=True)
class SymbolMapping:
    canonical_symbol: str
    okx_inst_id: str
    binance_symbol: str


@dataclass(frozen=True)
class VenueSymbol:
    venue: str
    symbol: str


@dataclass(frozen=True)
class InstrumentSpec:
    canonical_symbol: str
    asset_class: str
    quote_asset: str
    primary_venue: str
    venue_symbols: tuple[VenueSymbol, ...]
    is_default: bool = False


_SYMBOL_MAPPINGS = {
    "BTC/USDT": SymbolMapping("BTC/USDT", "BTC-USDT", "BTCUSDT"),
    "ETH/USDT": SymbolMapping("ETH/USDT", "ETH-USDT", "ETHUSDT"),
    "XAUT/USDT": SymbolMapping("XAUT/USDT", "XAUT-USDT", "XAUTUSDT"),
}

_INSTRUMENTS = {
    "BTC/USDT": InstrumentSpec(
        canonical_symbol="BTC/USDT",
        asset_class=CRYPTO_SPOT,
        quote_asset="USDT",
        primary_venue="okx",
        venue_symbols=(
            VenueSymbol(venue="okx", symbol="BTC-USDT"),
            VenueSymbol(venue="binance", symbol="BTCUSDT"),
        ),
        is_default=True,
    ),
    "ETH/USDT": InstrumentSpec(
        canonical_symbol="ETH/USDT",
        asset_class=CRYPTO_SPOT,
        quote_asset="USDT",
        primary_venue="okx",
        venue_symbols=(
            VenueSymbol(venue="okx", symbol="ETH-USDT"),
            VenueSymbol(venue="binance", symbol="ETHUSDT"),
        ),
        is_default=True,
    ),
    "XAUT/USDT": InstrumentSpec(
        canonical_symbol="XAUT/USDT",
        asset_class=CRYPTO_SPOT,
        quote_asset="USDT",
        primary_venue="okx",
        venue_symbols=(
            VenueSymbol(venue="okx", symbol="XAUT-USDT"),
            VenueSymbol(venue="binance", symbol="XAUTUSDT"),
        ),
        is_default=True,
    ),
    "NASDAQ100/INDEX": InstrumentSpec(
        canonical_symbol="NASDAQ100/INDEX",
        asset_class=INDEX,
        quote_asset="USD",
        primary_venue="external",
        venue_symbols=(
            VenueSymbol(venue="external", symbol="NASDAQ100"),
        ),
        is_default=False,
    ),
}


def default_symbols() -> tuple[str, ...]:
    return DEFAULT_SYMBOLS


def list_instruments(*, default_only: bool = False) -> tuple[InstrumentSpec, ...]:
    instruments = tuple(_INSTRUMENTS.values())
    if default_only:
        return tuple(instrument for instrument in instruments if instrument.is_default)
    return instruments


def get_instrument(canonical_symbol: str) -> InstrumentSpec:
    normalized = canonical_symbol.strip().upper()
    try:
        return _INSTRUMENTS[normalized]
    except KeyError as error:
        raise KeyError(f"Unknown instrument: {canonical_symbol}") from error


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
