from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from trading_system.data.okx_cli import OkxCliMarketData


@dataclass(frozen=True)
class MarketEvent:
    timestamp_ms: int
    symbol: str
    venue: str
    inst_id: str
    bar: str
    candle: object

    @property
    def is_confirmed(self) -> bool:
        return bool(getattr(self.candle, "is_confirmed", False))


class HistoricalReplayMarketEventSource:
    def __init__(
        self,
        *,
        symbol: str,
        inst_id: str,
        bar: str,
        candles: Sequence[object],
        venue: str = "okx",
        confirmed_only: bool = True,
    ):
        self.symbol = symbol
        self.inst_id = inst_id
        self.bar = bar
        self.candles = tuple(candles)
        self.venue = venue
        self.confirmed_only = confirmed_only

    def events(self) -> tuple[MarketEvent, ...]:
        rows = []
        for candle in sorted(self.candles, key=_timestamp):
            event = _event_from_candle(
                candle,
                symbol=self.symbol,
                venue=self.venue,
                inst_id=self.inst_id,
                bar=self.bar,
            )
            if self.confirmed_only and not event.is_confirmed:
                continue
            rows.append(event)
        return tuple(rows)


class OkxCandlePollingSource:
    def __init__(
        self,
        *,
        symbol: str,
        inst_id: str,
        bar: str,
        market_data: OkxCliMarketData | None = None,
        venue: str = "okx",
        limit: int = 100,
        confirmed_only: bool = True,
    ):
        self.symbol = symbol
        self.inst_id = inst_id
        self.bar = bar
        self.market_data = market_data or OkxCliMarketData()
        self.venue = venue
        self.limit = limit
        self.confirmed_only = confirmed_only
        self._seen_timestamps: set[int] = set()

    def poll_once(self) -> tuple[MarketEvent, ...]:
        candles = self.market_data.get_candles(self.inst_id, bar=self.bar, limit=self.limit)
        events: list[MarketEvent] = []
        for candle in sorted(candles, key=_timestamp):
            event = _event_from_candle(
                candle,
                symbol=self.symbol,
                venue=self.venue,
                inst_id=self.inst_id,
                bar=self.bar,
            )
            if self.confirmed_only and not event.is_confirmed:
                continue
            if event.timestamp_ms in self._seen_timestamps:
                continue
            self._seen_timestamps.add(event.timestamp_ms)
            events.append(event)
        return tuple(events)


def paper_inputs_from_market_events(events, signal_provider: Callable[[MarketEvent], Sequence[object]]):
    from trading_system.simulation.paper import PaperSignalInput

    inputs = []
    for event in events:
        if not event.is_confirmed:
            continue
        for signal in signal_provider(event):
            inputs.append(PaperSignalInput(signal=signal, execution_candles=(event.candle,)))
    return tuple(inputs)


def _event_from_candle(candle: object, *, symbol: str, venue: str, inst_id: str, bar: str) -> MarketEvent:
    return MarketEvent(
        timestamp_ms=_timestamp(candle),
        symbol=symbol,
        venue=venue,
        inst_id=inst_id,
        bar=bar,
        candle=candle,
    )


def _timestamp(candle: object) -> int:
    return int(getattr(candle, "timestamp_ms"))


__all__ = (
    "HistoricalReplayMarketEventSource",
    "MarketEvent",
    "OkxCandlePollingSource",
    "paper_inputs_from_market_events",
)
