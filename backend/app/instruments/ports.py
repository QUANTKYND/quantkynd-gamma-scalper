from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, Self

from app.instruments.catalogue import CatalogueVersion
from app.instruments.identity import (
    ContractVersion,
    FuturesContractIdentity,
    OptionContractIdentity,
    ProviderContractMapping,
    UnderlyingInstrumentIdentity,
)
from app.instruments.sessions import TradingSessionIdentity, TradingSessionVersion


class SemanticCollisionError(ValueError):
    pass


class AmbiguousPointInTimeResultError(ValueError):
    pass


class UnitOfWorkStateError(RuntimeError):
    pass


class PersistenceIntegrityError(ValueError):
    pass


class CatalogueRepository(Protocol):
    async def add(self, catalogue: CatalogueVersion) -> None: ...

    async def get(self, catalogue_version_id: str) -> CatalogueVersion | None: ...

    async def list_for_provider(self, provider: str) -> tuple[CatalogueVersion, ...]: ...

    async def resolve(
        self,
        provider: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> CatalogueVersion | None: ...


class InstrumentRepository(Protocol):
    async def add_underlying(self, instrument: UnderlyingInstrumentIdentity) -> None: ...

    async def add_future(self, contract: FuturesContractIdentity) -> None: ...

    async def add_option(self, contract: OptionContractIdentity) -> None: ...

    async def add_version(self, version: ContractVersion) -> None: ...

    async def add_provider_mapping(self, mapping: ProviderContractMapping) -> None: ...

    async def get_identity(
        self,
        instrument_id: str,
    ) -> UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity | None: ...

    async def get_version(self, version_id: str) -> ContractVersion | None: ...

    async def resolve_provider_key(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderContractMapping | None: ...

    async def list_contract_versions(
        self,
        underlying_instrument_id: str,
        expiry: date,
    ) -> tuple[ContractVersion, ...]: ...


class TradingSessionRepository(Protocol):
    async def add_identity(self, session: TradingSessionIdentity) -> None: ...

    async def add_version(self, version: TradingSessionVersion) -> None: ...

    async def resolve(
        self,
        exchange: str,
        session_date: date,
        session_kind: str,
        known_as_of: datetime | None,
    ) -> TradingSessionVersion | None: ...


class UnitOfWork(Protocol):
    instruments: InstrumentRepository
    catalogues: CatalogueRepository
    trading_sessions: TradingSessionRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc_value, traceback) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
