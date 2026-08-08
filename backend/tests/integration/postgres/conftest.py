import asyncio

import pytest

from app.core.database_config import DatabaseSettings
from app.persistence.postgres.database_safety import (
    DestructiveDatabasePurpose,
    destructive_database_lease,
)
from app.persistence.postgres.engine import create_database_engine, dispose_database_engine
from app.persistence.postgres.migrations import upgrade_to_head


@pytest.fixture
def postgres_settings() -> DatabaseSettings:
    settings = DatabaseSettings(_env_file=None)
    missing = []
    if settings.database_url is None:
        missing.append("DATABASE_URL")
    if not settings.database_allow_destructive_test_operations:
        missing.append("DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true")
    if settings.database_expected_integration_test_name is None:
        missing.append("DATABASE_EXPECTED_INTEGRATION_TEST_NAME")
    if missing:
        pytest.skip(
            "PostgreSQL destructive test contract is incomplete: " + ", ".join(missing)
        )
    return settings


@pytest.fixture
def postgres_url(postgres_settings: DatabaseSettings) -> str:
    return postgres_settings.require_database_url()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def reset_postgres_url(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> str:
    asyncio.run(_reset_database(postgres_url, postgres_settings))
    return postgres_url


async def _reset_database(database_url: str, settings: DatabaseSettings) -> None:
    engine = create_database_engine(settings)
    try:
        async with destructive_database_lease(
            engine,
            database_url,
            settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ) as lease:
            await lease.drop_and_recreate_public()
            await asyncio.to_thread(upgrade_to_head, database_url)
    finally:
        await dispose_database_engine(engine)
