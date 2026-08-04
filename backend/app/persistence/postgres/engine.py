from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database_config import DatabaseSettings


class DatabaseConnectionError(ConnectionError):
    pass


def create_database_engine(settings: DatabaseSettings) -> AsyncEngine:
    server_settings = {
        "application_name": settings.database_application_name,
        "statement_timeout": str(settings.database_statement_timeout_ms),
    }
    return create_async_engine(
        settings.require_database_url(),
        isolation_level="REPEATABLE READ",
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.database_connect_timeout_seconds,
            "server_settings": server_settings,
        },
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def probe_database(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        raise DatabaseConnectionError("database health probe failed") from None


async def dispose_database_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
