from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import time
from pathlib import Path
from os import PathLike
from typing import Iterable

from trading_system.data.okx_cli import Candle
from trading_system.data.universe import required_okx_bars_for_profiles


@dataclass(frozen=True)
class CandleKey:
    inst_id: str
    bar: str
    venue: str = "okx"
    inst_type: str = "SPOT"


@dataclass(frozen=True)
class DownloadState:
    venue: str
    inst_type: str
    inst_id: str
    bar: str
    earliest_ts_ms: int | None
    latest_confirmed_ts_ms: int | None
    row_count: int
    last_success_at_ms: int | None
    last_error: str
    cli_version: str


class CandleRepository:
    def __init__(self):
        self._candles_by_key: dict[CandleKey, dict[int, Candle]] = {}

    def save_many(
        self,
        inst_id: str,
        bar: str,
        candles: Iterable[Candle],
        *,
        venue: str = "okx",
        inst_type: str = "SPOT",
        source: str = "okx_cli",
    ) -> None:
        key = CandleKey(inst_id=inst_id, bar=bar, venue=venue, inst_type=inst_type)
        candles_by_timestamp = self._candles_by_key.setdefault(key, {})

        for candle in candles:
            candles_by_timestamp[candle.timestamp_ms] = candle

    def list_candles(self, inst_id: str, bar: str, *, venue: str = "okx", inst_type: str = "SPOT") -> tuple[Candle, ...]:
        key = CandleKey(inst_id=inst_id, bar=bar, venue=venue, inst_type=inst_type)
        candles_by_timestamp = self._candles_by_key.get(key, {})
        return tuple(
            candle
            for _, candle in sorted(candles_by_timestamp.items(), key=lambda item: item[0])
        )

    def latest_timestamp(self, inst_id: str, bar: str, *, venue: str = "okx", inst_type: str = "SPOT") -> int | None:
        candles = self.list_candles(inst_id, bar, venue=venue, inst_type=inst_type)
        if not candles:
            return None
        return candles[-1].timestamp_ms


class DuckDbCandleRepository:
    def __init__(self, database_path: str | PathLike[str]):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def save_many(
        self,
        inst_id: str,
        bar: str,
        candles: Iterable[Candle],
        *,
        venue: str = "okx",
        inst_type: str = "SPOT",
        source: str = "okx_cli",
        ingested_at_ms: int | None = None,
    ) -> None:
        candles_by_timestamp: dict[int, Candle] = {}
        for item in candles:
            candles_by_timestamp[item.timestamp_ms] = item

        if not candles_by_timestamp:
            return

        ingested_at_ms = ingested_at_ms if ingested_at_ms is not None else _now_ms()
        rows = [
            (
                venue,
                inst_id,
                inst_type,
                bar,
                item.timestamp_ms,
                item.open,
                item.high,
                item.low,
                item.close,
                item.volume,
                item.volume_currency,
                item.volume_currency_quote,
                item.is_confirmed,
                source,
                ingested_at_ms,
            )
            for item in candles_by_timestamp.values()
        ]

        with self._connection() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                for item in candles_by_timestamp.values():
                    connection.execute(
                        """
                        DELETE FROM candles
                        WHERE venue = ?
                          AND inst_id = ?
                          AND inst_type = ?
                          AND bar = ?
                          AND ts_ms = ?
                        """,
                        (venue, inst_id, inst_type, bar, item.timestamp_ms),
                    )
                connection.executemany(
                    """
                    INSERT INTO candles (
                        venue,
                        inst_id,
                        inst_type,
                        bar,
                        ts_ms,
                        "open",
                        high,
                        low,
                        "close",
                        volume,
                        volume_currency,
                        volume_currency_quote,
                        is_confirmed,
                        source,
                        ingested_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def list_candles(
        self,
        inst_id: str,
        bar: str,
        *,
        venue: str = "okx",
        inst_type: str = "SPOT",
    ) -> tuple[Candle, ...]:
        return self.load_range(
            inst_id,
            bar,
            0,
            9_223_372_036_854_775_807,
            venue=venue,
            inst_type=inst_type,
            confirmed_only=False,
        )

    def load_range(
        self,
        inst_id: str,
        bar: str,
        start_ms: int,
        end_ms: int,
        *,
        venue: str = "okx",
        inst_type: str = "SPOT",
        confirmed_only: bool = True,
    ) -> tuple[Candle, ...]:
        filters = """
            venue = ?
            AND inst_id = ?
            AND inst_type = ?
            AND bar = ?
            AND ts_ms >= ?
            AND ts_ms <= ?
        """
        parameters: list[object] = [venue, inst_id, inst_type, bar, start_ms, end_ms]
        if confirmed_only:
            filters += " AND is_confirmed = TRUE"

        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    ts_ms,
                    "open",
                    high,
                    low,
                    "close",
                    volume,
                    volume_currency,
                    volume_currency_quote,
                    is_confirmed
                FROM candles
                WHERE {filters}
                ORDER BY ts_ms ASC
                """,
                parameters,
            ).fetchall()

        return tuple(
            Candle(
                timestamp_ms=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                volume_currency=float(row[6]),
                volume_currency_quote=float(row[7]),
                is_confirmed=bool(row[8]),
            )
            for row in rows
        )

    def latest_timestamp(
        self,
        inst_id: str,
        bar: str,
        *,
        venue: str = "okx",
        inst_type: str = "SPOT",
    ) -> int | None:
        return self._timestamp_boundary(
            "MAX",
            inst_id,
            bar,
            venue=venue,
            inst_type=inst_type,
        )

    def earliest_timestamp(
        self,
        inst_id: str,
        bar: str,
        *,
        venue: str = "okx",
        inst_type: str = "SPOT",
    ) -> int | None:
        return self._timestamp_boundary(
            "MIN",
            inst_id,
            bar,
            venue=venue,
            inst_type=inst_type,
        )

    def get_download_state(
        self,
        venue: str,
        inst_id: str,
        bar: str,
        *,
        inst_type: str = "SPOT",
    ) -> DownloadState | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    venue,
                    inst_type,
                    inst_id,
                    bar,
                    earliest_ts_ms,
                    latest_confirmed_ts_ms,
                    row_count,
                    last_success_at_ms,
                    last_error,
                    cli_version
                FROM download_state
                WHERE venue = ? AND inst_type = ? AND inst_id = ? AND bar = ?
                """,
                (venue, inst_type, inst_id, bar),
            ).fetchone()

        if row is None:
            return None

        return DownloadState(
            venue=str(row[0]),
            inst_type=str(row[1]),
            inst_id=str(row[2]),
            bar=str(row[3]),
            earliest_ts_ms=_optional_int(row[4]),
            latest_confirmed_ts_ms=_optional_int(row[5]),
            row_count=int(row[6]),
            last_success_at_ms=_optional_int(row[7]),
            last_error=str(row[8]),
            cli_version=str(row[9]),
        )

    def update_download_state(self, state: DownloadState) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(
                    """
                    DELETE FROM download_state
                    WHERE venue = ? AND inst_type = ? AND inst_id = ? AND bar = ?
                    """,
                    (state.venue, state.inst_type, state.inst_id, state.bar),
                )
                connection.execute(
                    """
                    INSERT INTO download_state (
                        venue,
                        inst_type,
                        inst_id,
                        bar,
                        earliest_ts_ms,
                        latest_confirmed_ts_ms,
                        row_count,
                        last_success_at_ms,
                        last_error,
                        cli_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.venue,
                        state.inst_type,
                        state.inst_id,
                        state.bar,
                        state.earliest_ts_ms,
                        state.latest_confirmed_ts_ms,
                        state.row_count,
                        state.last_success_at_ms,
                        state.last_error,
                        state.cli_version,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _timestamp_boundary(
        self,
        aggregate: str,
        inst_id: str,
        bar: str,
        *,
        venue: str,
        inst_type: str,
    ) -> int | None:
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT {aggregate}(ts_ms)
                FROM candles
                WHERE venue = ?
                  AND inst_id = ?
                  AND inst_type = ?
                  AND bar = ?
                """,
                (venue, inst_id, inst_type, bar),
            ).fetchone()

        if row is None:
            return None
        return _optional_int(row[0])

    def _initialize_schema(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    venue TEXT NOT NULL,
                    inst_id TEXT NOT NULL,
                    inst_type TEXT NOT NULL,
                    bar TEXT NOT NULL,
                    ts_ms BIGINT NOT NULL,
                    "open" DOUBLE NOT NULL,
                    high DOUBLE NOT NULL,
                    low DOUBLE NOT NULL,
                    "close" DOUBLE NOT NULL,
                    volume DOUBLE NOT NULL,
                    volume_currency DOUBLE NOT NULL,
                    volume_currency_quote DOUBLE NOT NULL,
                    is_confirmed BOOLEAN NOT NULL,
                    source TEXT NOT NULL,
                    ingested_at_ms BIGINT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS download_state (
                    venue TEXT NOT NULL,
                    inst_type TEXT NOT NULL,
                    inst_id TEXT NOT NULL,
                    bar TEXT NOT NULL,
                    earliest_ts_ms BIGINT,
                    latest_confirmed_ts_ms BIGINT,
                    row_count BIGINT NOT NULL,
                    last_success_at_ms BIGINT,
                    last_error TEXT NOT NULL,
                    cli_version TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _connect(self):
        return _connect_duckdb(self.database_path, read_only=False)


class ReadOnlyDuckDbCandleRepository(DuckDbCandleRepository):
    """DuckDB candle reader that never initializes or mutates the database."""

    def __init__(self, database_path: str | PathLike[str]):
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(f"Candle database not found: {self.database_path}")

    def _connect(self):
        return _connect_duckdb(self.database_path, read_only=True)

    def save_many(self, *args, **kwargs) -> None:
        raise PermissionError("ReadOnlyDuckDbCandleRepository does not allow writes")

    def update_download_state(self, *args, **kwargs) -> None:
        raise PermissionError("ReadOnlyDuckDbCandleRepository does not allow writes")


def _connect_duckdb(database_path: Path, *, read_only: bool):
    try:
        import duckdb
    except ImportError as error:
        raise ImportError(
            "DuckDbCandleRepository requires the 'duckdb' package. "
            "Install project dependencies from requirements.txt."
        ) from error
    return duckdb.connect(str(database_path), read_only=read_only)


def required_bars_for_profiles(profiles) -> tuple[str, ...]:
    return required_okx_bars_for_profiles(profiles)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)
