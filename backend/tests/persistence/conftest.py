import os

import pytest

from app.core.database_config import DatabaseSettings, database_name


TEST_DATABASE_MARKERS = ("test", "dev", "local")


@pytest.fixture
def postgres_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if value is None:
        pytest.skip("DATABASE_URL is not configured for PostgreSQL integration tests")
    url = DatabaseSettings(database_url=value, _env_file=None).require_database_url()
    if not any(marker in database_name(url).lower() for marker in TEST_DATABASE_MARKERS):
        pytest.skip("DATABASE_URL does not identify a test-safe database")
    return url


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
