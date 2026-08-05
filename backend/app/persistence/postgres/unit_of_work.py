from __future__ import annotations

from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.instruments.ports import UnitOfWorkStateError
from app.persistence.postgres.repositories import (
    PostgresCatalogueIngestionRepository,
    PostgresCatalogueRepository,
    PostgresInstrumentRepository,
    PostgresTradingSessionRepository,
)


class PostgresUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        read_only_repeatable_read: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._read_only_repeatable_read = read_only_repeatable_read
        self._session: AsyncSession | None = None
        self._closed = False
        self._finalized = False
        self._instruments: PostgresInstrumentRepository | None = None
        self._catalogues: PostgresCatalogueRepository | None = None
        self._catalogue_ingestions: PostgresCatalogueIngestionRepository | None = None
        self._trading_sessions: PostgresTradingSessionRepository | None = None

    @property
    def instruments(self) -> PostgresInstrumentRepository:
        self._require_active()
        assert self._instruments is not None
        return self._instruments

    @property
    def catalogues(self) -> PostgresCatalogueRepository:
        self._require_active()
        assert self._catalogues is not None
        return self._catalogues

    @property
    def trading_sessions(self) -> PostgresTradingSessionRepository:
        self._require_active()
        assert self._trading_sessions is not None
        return self._trading_sessions

    @property
    def catalogue_ingestions(self) -> PostgresCatalogueIngestionRepository:
        self._require_active()
        assert self._catalogue_ingestions is not None
        return self._catalogue_ingestions

    async def __aenter__(self) -> PostgresUnitOfWork:
        if self._closed or self._session is not None:
            raise UnitOfWorkStateError("unit of work instances cannot be reused")
        self._session = self._session_factory()
        if self._read_only_repeatable_read:
            await self._session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
        self._instruments = PostgresInstrumentRepository(self._session, self._require_active)
        self._catalogues = PostgresCatalogueRepository(self._session, self._require_active)
        self._catalogue_ingestions = PostgresCatalogueIngestionRepository(
            self._session,
            self._require_active,
        )
        self._trading_sessions = PostgresTradingSessionRepository(
            self._session,
            self._require_active,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            raise UnitOfWorkStateError("unit of work is not active")
        session = self._session
        try:
            if not self._finalized:
                await session.rollback()
                self._finalized = True
        finally:
            await session.close()
            self._closed = True
            self._session = None
            self._instruments = None
            self._catalogues = None
            self._catalogue_ingestions = None
            self._trading_sessions = None

    async def commit(self) -> None:
        session = self._require_active()
        try:
            await session.commit()
        except Exception:
            self._finalized = True
            await session.rollback()
            raise
        self._finalized = True

    async def rollback(self) -> None:
        session = self._require_active()
        self._finalized = True
        await session.rollback()

    def _require_active(self) -> AsyncSession:
        if self._session is None or self._finalized:
            raise UnitOfWorkStateError("unit of work is not active")
        return self._session
