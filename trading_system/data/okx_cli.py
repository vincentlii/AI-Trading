from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Ticker:
    inst_id: str
    last: float
    ask: float
    bid: float
    open_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    timestamp_ms: int


@dataclass(frozen=True)
class Candle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_currency: float
    volume_currency_quote: float
    is_confirmed: bool


@dataclass(frozen=True)
class Instrument:
    inst_id: str
    inst_type: str
    state: str
    list_time_ms: int
    tick_size: str
    lot_size: str
    min_size: str
    base_ccy: str
    quote_ccy: str
    inst_category: str


class OkxCliMarketData:
    def __init__(self, okx_command: str | None = None, runner: Runner | None = None):
        self.okx_command = okx_command if okx_command is not None else _default_okx_command()
        self.runner = runner or subprocess.run

    def get_ticker(self, inst_id: str) -> Ticker:
        data = self._run_json(["market", "ticker", inst_id])
        row = data[0]
        return Ticker(
            inst_id=row["instId"],
            last=float(row["last"]),
            ask=float(row["askPx"]),
            bid=float(row["bidPx"]),
            open_24h=float(row["open24h"]),
            high_24h=float(row["high24h"]),
            low_24h=float(row["low24h"]),
            volume_24h=float(row["vol24h"]),
            timestamp_ms=int(row["ts"]),
        )

    def get_candles(
        self,
        inst_id: str,
        *,
        bar: str,
        limit: int,
        after: int | None = None,
        before: int | None = None,
    ) -> tuple[Candle, ...]:
        args = ["market", "candles", inst_id, "--bar", bar, "--limit", str(limit)]
        if after is not None:
            args.extend(["--after", str(after)])
        if before is not None:
            args.extend(["--before", str(before)])
        data = self._run_json(args)
        return tuple(_parse_candle(row) for row in data)

    def get_instruments(self, *, inst_type: str, inst_id: str | None = None) -> tuple[Instrument, ...]:
        args = ["market", "instruments", "--instType", inst_type]
        if inst_id is not None:
            args.extend(["--instId", inst_id])
        data = self._run_json(args)
        return tuple(_parse_instrument(row) for row in data)

    def _run_json(self, args: Sequence[str]):
        command = [self.okx_command, *args, "--json"]
        try:
            completed = self.runner(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as error:
            raise FileNotFoundError(
                "OKX CLI command not found. "
                "Pass --okx-command, set OKX_CLI_COMMAND, or add okx to PATH. "
                f"resolved_command={self.okx_command}"
            ) from error
        return json.loads(completed.stdout)


def _parse_candle(row: Sequence[str]) -> Candle:
    return Candle(
        timestamp_ms=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        volume_currency=float(row[6]),
        volume_currency_quote=float(row[7]),
        is_confirmed=row[8] == "1",
    )


def _default_okx_command() -> str:
    configured = os.environ.get("OKX_CLI_COMMAND")
    if configured:
        return configured

    discovered = shutil.which("okx")
    if discovered:
        return discovered

    appdata = os.environ.get("APPDATA")
    if appdata:
        npm_command = Path(appdata) / "npm" / "okx.cmd"
        if npm_command.exists():
            return str(npm_command)

    return "okx"


def _parse_instrument(row: Mapping[str, str]) -> Instrument:
    return Instrument(
        inst_id=row["instId"],
        inst_type=row["instType"],
        state=row["state"],
        list_time_ms=int(row["listTime"]),
        tick_size=row["tickSz"],
        lot_size=row["lotSz"],
        min_size=row["minSz"],
        base_ccy=row["baseCcy"],
        quote_ccy=row["quoteCcy"],
        inst_category=row["instCategory"],
    )
