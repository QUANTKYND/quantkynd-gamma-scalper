from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from app.instruments.models import InstrumentDefinition
from app.market_data.provider import HistoricalCloseProvider, InstrumentProvider
from app.services.rv_service import RVResearchSnapshot, build_research_snapshot_from_prices


@dataclass(frozen=True)
class InstrumentRVService:
    instrument: InstrumentDefinition
    snapshot: RVResearchSnapshot


@dataclass(frozen=True)
class CacheEntry:
    service: InstrumentRVService
    expires_at: datetime
    exchange_date: date


class InstrumentRVServiceRegistry:
    def __init__(
        self,
        instruments: InstrumentProvider,
        history: HistoricalCloseProvider,
        *,
        lookback_years: int,
        cache_seconds: int,
        max_entries: int = 50,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._instruments = instruments
        self._history = history
        self._lookback_years = lookback_years
        self._cache_seconds = cache_seconds
        self._max_entries = max_entries
        self._now = now or (lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, instrument_key: str) -> InstrumentRVService:
        now = datetime.now(UTC)
        exchange_date = self.exchange_date()
        entry = self._entries.get(instrument_key)
        if entry is not None and entry.expires_at > now and entry.exchange_date == exchange_date:
            self._entries.move_to_end(instrument_key)
            return entry.service
        lock = self._locks.setdefault(instrument_key, asyncio.Lock())
        async with lock:
            entry = self._entries.get(instrument_key)
            now = datetime.now(UTC)
            if entry is not None and entry.expires_at > now and entry.exchange_date == exchange_date:
                return entry.service
            return await self._refresh(instrument_key)

    async def refresh(self, instrument_key: str) -> InstrumentRVService:
        lock = self._locks.setdefault(instrument_key, asyncio.Lock())
        async with lock:
            return await self._refresh(instrument_key)

    async def _refresh(self, instrument_key: str) -> InstrumentRVService:
        instrument = await self._instruments.resolve(instrument_key)
        to_date = self.exchange_date()
        try:
            from_date = to_date.replace(year=to_date.year - self._lookback_years)
        except ValueError:
            from_date = to_date.replace(year=to_date.year - self._lookback_years, day=28)
        dataset = await self._history.daily_closes(instrument_key, from_date, to_date)
        snapshot = build_research_snapshot_from_prices(
            symbol=instrument.trading_symbol,
            prices=dataset.prices,
            source="upstox_historical",
            dataset_key=instrument.instrument_key,
        )
        service = InstrumentRVService(instrument=instrument, snapshot=snapshot)
        self._entries[instrument_key] = CacheEntry(
            service=service,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._cache_seconds),
            exchange_date=to_date,
        )
        self._entries.move_to_end(instrument_key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return service

    def exchange_date(self) -> date:
        return self._now().astimezone(ZoneInfo("Asia/Kolkata")).date()
