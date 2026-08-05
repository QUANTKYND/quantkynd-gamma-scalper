from __future__ import annotations

from dataclasses import dataclass
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
from app.instruments.temporal_records import AmbiguousPointInTimeResultError
from app.instruments.provider_catalogue import (
    CatalogueIngestionRun,
    CatalogueMembership,
    CatalogueRowOutcome,
    CatalogueSourceArtifact,
)


class SemanticCollisionError(ValueError):
    pass


class UnitOfWorkStateError(RuntimeError):
    pass


class PersistenceIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogueVersionState:
    value: CatalogueVersion
    record_id: str


@dataclass(frozen=True)
class InstrumentVersionState:
    value: ContractVersion
    record_id: str


@dataclass(frozen=True)
class ProviderMappingState:
    value: ProviderContractMapping
    record_id: str
    instrument_id: str


class CatalogueRepository(Protocol):
    async def add(
        self,
        catalogue: CatalogueVersion,
        supersedes_record_id: str | None = None,
    ) -> str: ...

    async def get(self, catalogue_version_id: str) -> CatalogueVersion | None: ...

    async def list_for_provider(self, provider: str) -> tuple[CatalogueVersion, ...]: ...

    async def resolve(
        self,
        provider: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> CatalogueVersion | None: ...

    async def resolve_state(
        self,
        provider: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> CatalogueVersionState | None: ...

    async def resolve_knowledge_leaf(
        self,
        provider: str,
        known_as_of: datetime | None = None,
    ) -> CatalogueVersionState | None: ...


class InstrumentRepository(Protocol):
    async def add_underlying(self, instrument: UnderlyingInstrumentIdentity) -> None: ...

    async def add_future(self, contract: FuturesContractIdentity) -> None: ...

    async def add_option(self, contract: OptionContractIdentity) -> None: ...

    async def add_version(
        self,
        version: ContractVersion,
        supersedes_record_id: str | None = None,
    ) -> str: ...

    async def add_provider_mapping(
        self,
        mapping: ProviderContractMapping,
        supersedes_record_id: str | None = None,
    ) -> str: ...

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

    async def resolve_version_state(
        self,
        instrument_id: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> InstrumentVersionState | None: ...

    async def resolve_version_knowledge_leaf(
        self,
        instrument_id: str,
        known_as_of: datetime | None = None,
    ) -> InstrumentVersionState | None: ...

    async def resolve_provider_key_state(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderMappingState | None: ...

    async def resolve_provider_key_mapping_state(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderMappingState | None: ...

    async def resolve_provider_key_knowledge_leaf(
        self,
        provider: str,
        provider_contract_key: str,
        known_as_of: datetime | None = None,
    ) -> ProviderMappingState | None: ...

    async def resolve_provider_key_instrument_id(
        self,
        provider: str,
        provider_contract_key: str,
    ) -> str | None: ...

    async def list_contract_versions(
        self,
        underlying_instrument_id: str,
        expiry: date,
    ) -> tuple[ContractVersion, ...]: ...


class TradingSessionRepository(Protocol):
    async def add_identity(self, session: TradingSessionIdentity) -> None: ...

    async def add_version(
        self,
        version: TradingSessionVersion,
        supersedes_record_id: str | None = None,
    ) -> str: ...

    async def resolve(
        self,
        exchange: str,
        session_date: date,
        session_kind: str,
        known_as_of: datetime | None,
    ) -> TradingSessionVersion | None: ...


class CatalogueIngestionRepository(Protocol):
    async def lock_provider_profile(self, provider: str, profile_version: str) -> None: ...

    async def add_source_artifact(self, artifact: CatalogueSourceArtifact) -> None: ...

    async def add_ingestion_run(self, run: CatalogueIngestionRun) -> None: ...

    async def add_row_outcomes(self, outcomes: tuple[CatalogueRowOutcome, ...]) -> None: ...

    async def add_memberships(self, memberships: tuple[CatalogueMembership, ...]) -> None: ...

    async def list_memberships_for_catalogue(
        self,
        catalogue_version_id: str,
    ) -> tuple[CatalogueMembership, ...]: ...

    async def get_ingestion_run_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> CatalogueIngestionRun | None: ...


class UnitOfWork(Protocol):
    instruments: InstrumentRepository
    catalogues: CatalogueRepository
    trading_sessions: TradingSessionRepository
    catalogue_ingestions: CatalogueIngestionRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc_value, traceback) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
