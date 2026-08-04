import asyncio

import pytest
from pydantic import ValidationError

from app.core.database_config import (
    DatabaseConfigurationError,
    DatabaseSettings,
    redacted_database_url,
)
from app.persistence.postgres.engine import create_database_engine, dispose_database_engine


URL = "postgresql+asyncpg://user:secret@localhost:5432/quantkynd_test"


def test_database_url_is_optional_until_requested(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = DatabaseSettings(_env_file=None)
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL is required"):
        settings.require_database_url()


@pytest.mark.parametrize(
    "value",
    ["not-a-url", "postgresql://localhost/database", "sqlite:///database.db"],
)
def test_database_url_requires_async_postgres(value: str) -> None:
    with pytest.raises(ValidationError, match=r"malformed|postgresql\+asyncpg"):
        DatabaseSettings(database_url=value, _env_file=None)


def test_pool_settings_are_range_validated() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(database_pool_size=0, _env_file=None)
    with pytest.raises(ValidationError):
        DatabaseSettings(database_statement_timeout_ms=99, _env_file=None)


def test_credentials_are_redacted() -> None:
    settings = DatabaseSettings(database_url=URL, _env_file=None)
    assert "secret" not in repr(settings)
    assert "secret" not in redacted_database_url(URL)
    assert "***" in redacted_database_url(URL)


def test_restore_database_must_be_distinct() -> None:
    settings = DatabaseSettings(
        database_url=URL,
        database_restore_test_url="postgresql+asyncpg://other:different@localhost/quantkynd_test",
        _env_file=None,
    )
    with pytest.raises(DatabaseConfigurationError, match="must be different"):
        settings.require_restore_urls()


def test_restore_database_aliases_cannot_bypass_distinctness() -> None:
    settings = DatabaseSettings(
        database_url=URL,
        database_restore_test_url="postgresql+asyncpg://other:different@127.0.0.1/quantkynd_test",
        _env_file=None,
    )
    with pytest.raises(DatabaseConfigurationError, match="must be different"):
        settings.require_restore_urls()


def test_engine_creation_is_lazy() -> None:
    settings = DatabaseSettings(database_url=URL, _env_file=None)
    engine = create_database_engine(settings)
    asyncio.run(dispose_database_engine(engine))
