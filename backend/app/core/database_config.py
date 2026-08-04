from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class DatabaseConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseUrls:
    source: str
    restore: str


class DatabaseSettings(BaseSettings):
    database_url: SecretStr | None = None
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    database_pool_recycle_seconds: int = Field(default=1800, ge=30, le=86400)
    database_connect_timeout_seconds: int = Field(default=10, ge=1, le=120)
    database_statement_timeout_ms: int = Field(default=30000, ge=100, le=3600000)
    database_application_name: str = Field(default="quantkynd", min_length=1, max_length=63)
    database_echo: bool = False
    database_restore_test_url: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", "database_restore_test_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            _validated_url(value.get_secret_value())
        return value

    @field_validator("database_application_name")
    @classmethod
    def validate_application_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_APPLICATION_NAME must not be blank")
        return value

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise DatabaseConfigurationError(
                "DATABASE_URL is required for database-backed functionality"
            )
        return self.database_url.get_secret_value()

    def require_restore_urls(self) -> DatabaseUrls:
        source = self.require_database_url()
        if self.database_restore_test_url is None:
            raise DatabaseConfigurationError(
                "DATABASE_RESTORE_TEST_URL is required for restore verification"
            )
        restore = self.database_restore_test_url.get_secret_value()
        source_url = _validated_url(source)
        restore_url = _validated_url(restore)
        if _database_identity(source_url) == _database_identity(restore_url):
            raise DatabaseConfigurationError(
                "source and restore-test databases must be different"
            )
        return DatabaseUrls(source, restore)


def redacted_database_url(value: str) -> str:
    return _validated_url(value).render_as_string(hide_password=True)


def database_name(value: str) -> str:
    return _validated_url(value).database or ""


def _validated_url(value: str) -> URL:
    try:
        url = make_url(value)
    except Exception as exc:
        raise ValueError("database URL is malformed") from exc
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("database URL must use postgresql+asyncpg")
    if not url.database:
        raise ValueError("database URL must name a database")
    return url


def _database_identity(url: URL) -> tuple[str, int, str]:
    return (
        _normalized_host(url.host),
        url.port or 5432,
        url.database or "",
    )


def _normalized_host(host: str | None) -> str:
    value = (host or "localhost").lower()
    if value in {"localhost", "127.0.0.1", "::1"}:
        return "localhost"
    return value
