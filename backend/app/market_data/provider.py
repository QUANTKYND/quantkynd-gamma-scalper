from __future__ import annotations

from datetime import date
from typing import Protocol

from app.instruments.models import InstrumentDefinition
from app.market_data.models import HistoricalCloseDataset


class InstrumentProvider(Protocol):
    async def search(self, query: str, exchanges: tuple[str, ...], kinds: tuple[str, ...], limit: int) -> tuple[InstrumentDefinition, ...]: ...

    async def resolve(self, instrument_key: str) -> InstrumentDefinition: ...


class HistoricalCloseProvider(Protocol):
    async def daily_closes(self, instrument_key: str, from_date: date, to_date: date) -> HistoricalCloseDataset: ...


class LiveMarketProvider(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def subscribe(self, instrument_keys: tuple[str, ...]) -> None: ...

    async def unsubscribe(self, instrument_keys: tuple[str, ...]) -> None: ...
