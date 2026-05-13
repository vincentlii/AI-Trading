from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable

from trading_system.data.history import DownloadState
from trading_system.data.okx_cli import Candle


@dataclass(frozen=True)
class DownloadSummary:
    venue: str
    inst_type: str
    inst_id: str
    bar: str
    pages_requested: int
    pages_fetched: int
    received_count: int
    saved_count: int
    skipped_unconfirmed_count: int
    earliest_ts_ms: int | None
    latest_confirmed_ts_ms: int | None
    row_count: int
    last_success_at_ms: int | None
    error: str


class OkxHistoryDownloader:
    venue = "okx"
    inst_type = "SPOT"
    source = "okx_cli"

    def __init__(self, client, repository, cli_version: str = "unknown"):
        self.client = client
        self.repository = repository
        self.cli_version = cli_version

    def download_symbol_bar(
        self,
        inst_id: str,
        bar: str,
        *,
        limit: int = 100,
        max_pages: int = 1,
    ) -> DownloadSummary:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if max_pages <= 0:
            raise ValueError("max_pages must be greater than 0")

        try:
            return self._download_symbol_bar(inst_id, bar, limit=limit, max_pages=max_pages)
        except Exception as error:
            return self._record_error_summary(inst_id, bar, max_pages=max_pages, error=error)

    def download_many(
        self,
        inst_ids: Iterable[str],
        bars: Iterable[str],
        *,
        limit: int = 100,
        max_pages: int = 1,
    ) -> tuple[DownloadSummary, ...]:
        summaries: list[DownloadSummary] = []
        for inst_id in inst_ids:
            for bar in bars:
                summaries.append(self.download_symbol_bar(inst_id, bar, limit=limit, max_pages=max_pages))
        return tuple(summaries)

    def _download_symbol_bar(self, inst_id: str, bar: str, *, limit: int, max_pages: int) -> DownloadSummary:
        after: int | None = None
        previous_oldest_ts: int | None = None
        pages_fetched = 0
        received_count = 0
        saved_count = 0
        skipped_unconfirmed_count = 0

        for _ in range(max_pages):
            page = self.client.get_candles(inst_id, bar=bar, limit=limit, after=after)
            if not page:
                break

            page_oldest_ts = min(candle.timestamp_ms for candle in page)
            if previous_oldest_ts is not None and page_oldest_ts >= previous_oldest_ts:
                break

            pages_fetched += 1
            received_count += len(page)
            confirmed = tuple(candle for candle in page if candle.is_confirmed)
            skipped_unconfirmed_count += len(page) - len(confirmed)

            if confirmed:
                self.repository.save_many(
                    inst_id,
                    bar,
                    confirmed,
                    venue=self.venue,
                    inst_type=self.inst_type,
                    source=self.source,
                )
                saved_count += len(confirmed)

            previous_oldest_ts = page_oldest_ts
            after = page_oldest_ts

        row_count, earliest_ts_ms, latest_confirmed_ts_ms = self._repository_boundaries(inst_id, bar)
        last_success_at_ms = _now_ms() if saved_count > 0 else None

        if saved_count > 0:
            self.repository.update_download_state(
                DownloadState(
                    venue=self.venue,
                    inst_type=self.inst_type,
                    inst_id=inst_id,
                    bar=bar,
                    earliest_ts_ms=earliest_ts_ms,
                    latest_confirmed_ts_ms=latest_confirmed_ts_ms,
                    row_count=row_count,
                    last_success_at_ms=last_success_at_ms,
                    last_error="",
                    cli_version=self.cli_version,
                )
            )

        return DownloadSummary(
            venue=self.venue,
            inst_type=self.inst_type,
            inst_id=inst_id,
            bar=bar,
            pages_requested=max_pages,
            pages_fetched=pages_fetched,
            received_count=received_count,
            saved_count=saved_count,
            skipped_unconfirmed_count=skipped_unconfirmed_count,
            earliest_ts_ms=earliest_ts_ms,
            latest_confirmed_ts_ms=latest_confirmed_ts_ms,
            row_count=row_count,
            last_success_at_ms=last_success_at_ms,
            error="",
        )

    def _record_error_summary(self, inst_id: str, bar: str, *, max_pages: int, error: Exception) -> DownloadSummary:
        row_count, earliest_ts_ms, latest_confirmed_ts_ms = self._repository_boundaries(inst_id, bar)
        existing_state = self.repository.get_download_state(self.venue, inst_id, bar, inst_type=self.inst_type)
        last_success_at_ms = existing_state.last_success_at_ms if existing_state is not None else None
        message = str(error)

        self.repository.update_download_state(
            DownloadState(
                venue=self.venue,
                inst_type=self.inst_type,
                inst_id=inst_id,
                bar=bar,
                earliest_ts_ms=earliest_ts_ms,
                latest_confirmed_ts_ms=latest_confirmed_ts_ms,
                row_count=row_count,
                last_success_at_ms=last_success_at_ms,
                last_error=message,
                cli_version=self.cli_version,
            )
        )

        return DownloadSummary(
            venue=self.venue,
            inst_type=self.inst_type,
            inst_id=inst_id,
            bar=bar,
            pages_requested=max_pages,
            pages_fetched=0,
            received_count=0,
            saved_count=0,
            skipped_unconfirmed_count=0,
            earliest_ts_ms=earliest_ts_ms,
            latest_confirmed_ts_ms=latest_confirmed_ts_ms,
            row_count=row_count,
            last_success_at_ms=last_success_at_ms,
            error=message,
        )

    def _repository_boundaries(self, inst_id: str, bar: str) -> tuple[int, int | None, int | None]:
        candles = self.repository.list_candles(inst_id, bar, venue=self.venue, inst_type=self.inst_type)
        return (
            len(candles),
            self.repository.earliest_timestamp(inst_id, bar, venue=self.venue, inst_type=self.inst_type),
            self.repository.latest_timestamp(inst_id, bar, venue=self.venue, inst_type=self.inst_type),
        )


def _now_ms() -> int:
    return int(time.time() * 1000)
