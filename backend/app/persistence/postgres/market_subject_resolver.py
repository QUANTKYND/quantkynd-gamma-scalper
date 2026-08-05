from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.services.catalogue_market_subject_resolver import CatalogueMarketSubjectResolver


def postgres_catalogue_market_subject_resolver(
    session_factory: async_sessionmaker[AsyncSession],
) -> CatalogueMarketSubjectResolver:
    return CatalogueMarketSubjectResolver(
        lambda: PostgresUnitOfWork(session_factory, read_only_repeatable_read=True)
    )
