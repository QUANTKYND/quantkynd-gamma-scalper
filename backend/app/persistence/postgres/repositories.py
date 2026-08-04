from __future__ import annotations

from datetime import date, datetime
from typing import Any, TypeVar

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.instruments.catalogue import CatalogueVersion
from app.instruments.identity import (
    ContractVersion,
    FuturesContractIdentity,
    OptionContractIdentity,
    ProviderContractMapping,
    UnderlyingInstrumentIdentity,
)
from app.instruments.ports import (
    AmbiguousPointInTimeResultError,
    PersistenceIntegrityError,
    SemanticCollisionError,
)
from app.instruments.sessions import TradingSessionIdentity, TradingSessionVersion
from app.persistence.postgres.mappings import (
    catalogue_from_row,
    catalogue_values,
    future_from_rows,
    future_values,
    market_instrument_values,
    option_from_rows,
    option_values,
    provider_mapping_from_row,
    provider_mapping_values,
    trading_session_values,
    trading_session_version_from_row,
    trading_session_version_values,
    underlying_from_rows,
    underlying_values,
    version_from_row,
    version_values,
)
from app.persistence.postgres.models import (
    CatalogueVersionRow,
    FuturesContractRow,
    InstrumentVersionRow,
    MarketInstrumentRow,
    OptionContractRow,
    ProviderContractMappingRow,
    TradingSessionRow,
    TradingSessionVersionRow,
    UnderlyingInstrumentRow,
)


class PostgresCatalogueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, catalogue: CatalogueVersion) -> None:
        await _insert_immutable(
            self._session,
            CatalogueVersionRow,
            "catalogue_version_id",
            catalogue_values(catalogue),
            "catalogue version",
        )

    async def get(self, catalogue_version_id: str) -> CatalogueVersion | None:
        row = await self._session.get(CatalogueVersionRow, catalogue_version_id)
        return catalogue_from_row(row) if row is not None else None

    async def list_for_provider(self, provider: str) -> tuple[CatalogueVersion, ...]:
        rows = (
            await self._session.scalars(
                select(CatalogueVersionRow)
                .where(CatalogueVersionRow.provider == provider)
                .order_by(
                    CatalogueVersionRow.effective_from,
                    CatalogueVersionRow.catalogue_version_id,
                )
            )
        ).all()
        return tuple(catalogue_from_row(row) for row in rows)

    async def resolve(
        self,
        provider: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> CatalogueVersion | None:
        conditions = [
            CatalogueVersionRow.provider == provider,
            CatalogueVersionRow.effective_from <= market_as_of,
            or_(
                CatalogueVersionRow.effective_until.is_(None),
                CatalogueVersionRow.effective_until > market_as_of,
            ),
        ]
        if known_as_of is not None:
            conditions.append(CatalogueVersionRow.recorded_at <= known_as_of)
        rows = (
            await self._session.scalars(
                select(CatalogueVersionRow)
                .where(*conditions)
                .order_by(CatalogueVersionRow.catalogue_version_id)
                .limit(2)
            )
        ).all()
        if len(rows) > 1:
            raise AmbiguousPointInTimeResultError(
                "multiple catalogue versions are visible at the requested cutoffs"
            )
        return catalogue_from_row(rows[0]) if rows else None


class PostgresInstrumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_underlying(self, instrument: UnderlyingInstrumentIdentity) -> None:
        await self._add_registry(instrument)
        await _insert_immutable(
            self._session,
            UnderlyingInstrumentRow,
            "instrument_id",
            underlying_values(instrument),
            "underlying instrument",
        )

    async def add_future(self, contract: FuturesContractIdentity) -> None:
        await self._add_registry(contract)
        await _insert_immutable(
            self._session,
            FuturesContractRow,
            "contract_id",
            future_values(contract),
            "futures contract",
        )

    async def add_option(self, contract: OptionContractIdentity) -> None:
        await self._add_registry(contract)
        await _insert_immutable(
            self._session,
            OptionContractRow,
            "contract_id",
            option_values(contract),
            "option contract",
        )

    async def add_version(self, version: ContractVersion) -> None:
        await _insert_immutable(
            self._session,
            InstrumentVersionRow,
            "version_id",
            version_values(version),
            "instrument version",
        )

    async def add_provider_mapping(self, mapping: ProviderContractMapping) -> None:
        await _insert_immutable(
            self._session,
            ProviderContractMappingRow,
            "mapping_id",
            provider_mapping_values(mapping),
            "provider mapping",
        )

    async def get_identity(
        self,
        instrument_id: str,
    ) -> UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity | None:
        registry = await self._session.get(MarketInstrumentRow, instrument_id)
        if registry is None:
            return None
        if registry.instrument_kind == "underlying":
            row = await self._session.get(UnderlyingInstrumentRow, instrument_id)
            return underlying_from_rows(registry, _required_subtype(row))
        if registry.instrument_kind == "future":
            row = await self._session.get(FuturesContractRow, instrument_id)
            return future_from_rows(registry, _required_subtype(row))
        if registry.instrument_kind == "option":
            row = await self._session.get(OptionContractRow, instrument_id)
            return option_from_rows(registry, _required_subtype(row))
        raise PersistenceIntegrityError("durable instrument registry has an unsupported kind")

    async def get_version(self, version_id: str) -> ContractVersion | None:
        result = await self._session.execute(
            select(InstrumentVersionRow, MarketInstrumentRow.instrument_kind)
            .join(
                MarketInstrumentRow,
                MarketInstrumentRow.instrument_id == InstrumentVersionRow.instrument_id,
            )
            .where(InstrumentVersionRow.version_id == version_id)
        )
        item = result.one_or_none()
        return version_from_row(item[0], item[1]) if item is not None else None

    async def resolve_provider_key(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderContractMapping | None:
        conditions = [
            ProviderContractMappingRow.provider == provider,
            ProviderContractMappingRow.provider_contract_key == provider_contract_key,
            ProviderContractMappingRow.effective_from <= market_as_of,
            or_(
                ProviderContractMappingRow.effective_until.is_(None),
                ProviderContractMappingRow.effective_until > market_as_of,
            ),
            InstrumentVersionRow.valid_from <= market_as_of,
            or_(
                InstrumentVersionRow.valid_until.is_(None),
                InstrumentVersionRow.valid_until > market_as_of,
            ),
        ]
        if known_as_of is not None:
            conditions.extend(
                [
                    ProviderContractMappingRow.recorded_at <= known_as_of,
                    or_(
                        ProviderContractMappingRow.superseded_at.is_(None),
                        ProviderContractMappingRow.superseded_at > known_as_of,
                    ),
                    InstrumentVersionRow.recorded_at <= known_as_of,
                    or_(
                        InstrumentVersionRow.superseded_at.is_(None),
                        InstrumentVersionRow.superseded_at > known_as_of,
                    ),
                ]
            )
        rows = (
            await self._session.scalars(
                select(ProviderContractMappingRow)
                .join(
                    InstrumentVersionRow,
                    InstrumentVersionRow.version_id
                    == ProviderContractMappingRow.contract_version_id,
                )
                .where(*conditions)
                .order_by(ProviderContractMappingRow.mapping_id)
                .limit(2)
            )
        ).all()
        if len(rows) > 1:
            raise AmbiguousPointInTimeResultError(
                "multiple provider mappings are visible at the requested cutoffs"
            )
        return provider_mapping_from_row(rows[0]) if rows else None

    async def list_contract_versions(
        self,
        underlying_instrument_id: str,
        expiry: date,
    ) -> tuple[ContractVersion, ...]:
        result = await self._session.execute(
            select(InstrumentVersionRow, MarketInstrumentRow.instrument_kind)
            .join(
                MarketInstrumentRow,
                MarketInstrumentRow.instrument_id == InstrumentVersionRow.instrument_id,
            )
            .outerjoin(
                FuturesContractRow,
                FuturesContractRow.contract_id == MarketInstrumentRow.instrument_id,
            )
            .outerjoin(
                OptionContractRow,
                OptionContractRow.contract_id == MarketInstrumentRow.instrument_id,
            )
            .where(
                or_(
                    and_(
                        FuturesContractRow.underlying_instrument_id == underlying_instrument_id,
                        FuturesContractRow.expiry == expiry,
                    ),
                    and_(
                        OptionContractRow.underlying_instrument_id == underlying_instrument_id,
                        OptionContractRow.expiry == expiry,
                    ),
                )
            )
            .order_by(InstrumentVersionRow.version_id)
        )
        return tuple(version_from_row(row, kind) for row, kind in result.all())

    async def _add_registry(
        self,
        instrument: UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity,
    ) -> None:
        await _insert_immutable(
            self._session,
            MarketInstrumentRow,
            "instrument_id",
            market_instrument_values(instrument),
            "market instrument",
        )


class PostgresTradingSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_identity(self, session: TradingSessionIdentity) -> None:
        await _insert_immutable(
            self._session,
            TradingSessionRow,
            "session_id",
            trading_session_values(session),
            "trading session",
        )

    async def add_version(self, version: TradingSessionVersion) -> None:
        await _insert_immutable(
            self._session,
            TradingSessionVersionRow,
            "session_version_id",
            trading_session_version_values(version),
            "trading session version",
        )

    async def resolve(
        self,
        exchange: str,
        session_date: date,
        session_kind: str,
        known_as_of: datetime | None,
    ) -> TradingSessionVersion | None:
        conditions = [
            TradingSessionRow.exchange == exchange,
            TradingSessionRow.session_date == session_date,
            TradingSessionRow.session_kind == session_kind,
        ]
        if known_as_of is not None:
            conditions.extend(
                [
                    TradingSessionVersionRow.recorded_at <= known_as_of,
                    or_(
                        TradingSessionVersionRow.superseded_at.is_(None),
                        TradingSessionVersionRow.superseded_at > known_as_of,
                    ),
                ]
            )
        rows = (
            await self._session.scalars(
                select(TradingSessionVersionRow)
                .join(
                    TradingSessionRow,
                    TradingSessionRow.session_id == TradingSessionVersionRow.session_id,
                )
                .where(*conditions)
                .order_by(TradingSessionVersionRow.session_version_id)
                .limit(2)
            )
        ).all()
        if len(rows) > 1:
            raise AmbiguousPointInTimeResultError(
                "multiple trading-session versions are visible at the knowledge cutoff"
            )
        return trading_session_version_from_row(rows[0]) if rows else None


RowType = TypeVar("RowType")


async def _insert_immutable(
    session: AsyncSession,
    model: type[RowType],
    primary_key_name: str,
    values: dict[str, Any],
    label: str,
) -> None:
    primary_key = getattr(model, primary_key_name)
    statement = (
        insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[primary_key])
        .returning(primary_key)
    )
    try:
        inserted = (await session.execute(statement)).scalar_one_or_none()
        if inserted is not None:
            return
        existing = await session.get(model, values[primary_key_name])
    except IntegrityError:
        raise PersistenceIntegrityError(
            f"persistence integrity constraint rejected {label}"
        ) from None
    if existing is None:
        raise PersistenceIntegrityError(f"conflicting {label} row was not readable")
    differences = [
        field_name
        for field_name, expected in values.items()
        if getattr(existing, field_name) != expected
    ]
    if differences:
        raise SemanticCollisionError(
            f"{label} identity collision with different immutable content"
        )


def _required_subtype(row: RowType | None) -> RowType:
    if row is None:
        raise PersistenceIntegrityError("durable instrument subtype row is missing")
    return row
