from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.database_config import (
    DatabaseSettings,
    database_endpoint_identity,
    database_host,
    database_name,
)


SENTINEL_SCHEMA = "quantkynd_control"
SENTINEL_TABLE = "disposable_database_sentinel"
SENTINEL_SCHEMA_VERSION = "data-1.1-disposable-v1"
SENTINEL_OWNERSHIP_MARKER = "quantkynd-owned-disposable-database"


class DestructiveDatabasePurpose(StrEnum):
    INTEGRATION = "integration"
    RESTORE = "restore"


class DestructiveDatabaseSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseServerIdentity:
    database_name: str
    server_address: str
    server_port: int
    system_identifier: str


@dataclass
class DestructiveDatabaseLease:
    connection: AsyncConnection
    purpose: DestructiveDatabasePurpose
    expected_database_name: str
    server_identity: DatabaseServerIdentity
    lock_key: int

    async def recheck_sentinel(self) -> None:
        await _validate_sentinel(
            self.connection,
            self.expected_database_name,
            self.purpose,
        )

    async def drop_and_recreate_public(self) -> None:
        await self.recheck_sentinel()
        await self.connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await self.connection.execute(text("CREATE SCHEMA public"))
        await self.connection.commit()
        await self.recheck_sentinel()
        await self.connection.commit()

    async def drop_public_for_restore(self) -> None:
        await self.recheck_sentinel()
        await self.connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await self.connection.commit()
        await self.recheck_sentinel()
        await self.connection.commit()


class DestructiveDatabaseLeaseContext:
    def __init__(
        self,
        engine: AsyncEngine,
        database_url: str,
        settings: DatabaseSettings,
        purpose: DestructiveDatabasePurpose,
    ) -> None:
        self._engine = engine
        self._database_url = database_url
        self._settings = settings
        self._purpose = purpose
        self._lease: DestructiveDatabaseLease | None = None

    async def __aenter__(self) -> DestructiveDatabaseLease:
        _validate_destructive_configuration(
            self._database_url,
            self._settings,
            self._purpose,
        )
        expected_name = _expected_database_name(self._settings, self._purpose)
        connection = await self._engine.connect()
        try:
            identity = await _server_identity(connection)
            if identity.database_name != expected_name:
                raise DestructiveDatabaseSafetyError(
                    "connected database name does not match the exact destructive expectation"
                )
            lock_key = await connection.scalar(
                text(
                    "SELECT hashtextextended('quantkynd:data11:destructive:' || current_database(), 0)"
                )
            )
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            if not acquired:
                raise DestructiveDatabaseSafetyError(
                    "another destructive database operation holds the advisory lock"
                )
            await _validate_sentinel(connection, expected_name, self._purpose)
            await connection.commit()
            self._lease = DestructiveDatabaseLease(
                connection,
                self._purpose,
                expected_name,
                identity,
                lock_key,
            )
            return self._lease
        except Exception:
            await connection.close()
            raise

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if self._lease is None:
            return
        try:
            await self._lease.connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": self._lease.lock_key},
            )
            await self._lease.connection.commit()
        finally:
            await self._lease.connection.close()
            self._lease = None


def destructive_database_lease(
    engine: AsyncEngine,
    database_url: str,
    settings: DatabaseSettings,
    purpose: DestructiveDatabasePurpose,
) -> DestructiveDatabaseLeaseContext:
    return DestructiveDatabaseLeaseContext(engine, database_url, settings, purpose)


def assert_distinct_database_servers(
    source: DestructiveDatabaseLease,
    restore: DestructiveDatabaseLease,
) -> None:
    source_identity = source.server_identity
    restore_identity = restore.server_identity
    if (
        source_identity.system_identifier == restore_identity.system_identifier
        and source_identity.database_name == restore_identity.database_name
    ):
        raise DestructiveDatabaseSafetyError(
            "source and restore connections resolve to the same server database"
        )


async def bootstrap_disposable_database_sentinel(
    engine: AsyncEngine,
    database_url: str,
    settings: DatabaseSettings,
    purpose: DestructiveDatabasePurpose,
) -> None:
    _validate_destructive_configuration(database_url, settings, purpose)
    expected_name = _expected_database_name(settings, purpose)
    async with engine.begin() as connection:
        identity = await _server_identity(connection)
        if identity.database_name != expected_name:
            raise DestructiveDatabaseSafetyError(
                "connected database name does not match the exact bootstrap expectation"
            )
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SENTINEL_SCHEMA}"))
        await connection.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {SENTINEL_SCHEMA}.{SENTINEL_TABLE} (database_name text PRIMARY KEY, purpose text NOT NULL, schema_version text NOT NULL, created_at timestamptz NOT NULL, ownership_marker text NOT NULL)"
            )
        )
        existing = (
            await connection.execute(
                text(
                    f"SELECT database_name, purpose, schema_version, created_at, ownership_marker FROM {SENTINEL_SCHEMA}.{SENTINEL_TABLE}"
                )
            )
        ).mappings().all()
        if existing:
            await _validate_sentinel(connection, expected_name, purpose)
            return
        await connection.execute(
            text(
                f"INSERT INTO {SENTINEL_SCHEMA}.{SENTINEL_TABLE} (database_name, purpose, schema_version, created_at, ownership_marker) VALUES (:database_name, :purpose, :schema_version, CURRENT_TIMESTAMP, :ownership_marker)"
            ),
            {
                "database_name": expected_name,
                "purpose": purpose.value,
                "schema_version": SENTINEL_SCHEMA_VERSION,
                "ownership_marker": SENTINEL_OWNERSHIP_MARKER,
            },
        )


def _validate_destructive_configuration(
    database_url: str,
    settings: DatabaseSettings,
    purpose: DestructiveDatabasePurpose,
) -> None:
    if not settings.database_allow_destructive_test_operations:
        raise DestructiveDatabaseSafetyError(
            "destructive database operations require explicit opt-in"
        )
    expected_name = _expected_database_name(settings, purpose)
    if database_name(database_url) != expected_name:
        raise DestructiveDatabaseSafetyError(
            "database URL name does not match the exact destructive expectation"
        )
    if (
        database_host(database_url) != "localhost"
        and not settings.database_allow_nonlocal_destructive_operations
    ):
        raise DestructiveDatabaseSafetyError(
            "destructive database operations require a loopback host"
        )


def _expected_database_name(
    settings: DatabaseSettings,
    purpose: DestructiveDatabasePurpose,
) -> str:
    value = (
        settings.database_expected_integration_test_name
        if purpose == DestructiveDatabasePurpose.INTEGRATION
        else settings.database_expected_restore_test_name
    )
    if value is None:
        raise DestructiveDatabaseSafetyError(
            f"exact expected {purpose.value} database name is required"
        )
    return value


async def _server_identity(connection: AsyncConnection) -> DatabaseServerIdentity:
    row = (
        await connection.execute(
            text(
                "SELECT current_database() AS database_name, COALESCE(inet_server_addr()::text, 'local') AS server_address, inet_server_port() AS server_port, (pg_control_system()).system_identifier::text AS system_identifier"
            )
        )
    ).mappings().one()
    return DatabaseServerIdentity(
        row["database_name"],
        row["server_address"],
        row["server_port"],
        row["system_identifier"],
    )


async def _validate_sentinel(
    connection: AsyncConnection,
    expected_database_name: str,
    purpose: DestructiveDatabasePurpose,
) -> None:
    relation = await connection.scalar(
        text("SELECT to_regclass(:relation_name)"),
        {"relation_name": f"{SENTINEL_SCHEMA}.{SENTINEL_TABLE}"},
    )
    if relation is None:
        raise DestructiveDatabaseSafetyError(
            "disposable database sentinel is missing"
        )
    rows = (
        await connection.execute(
            text(
                f"SELECT database_name, purpose, schema_version, created_at, ownership_marker FROM {SENTINEL_SCHEMA}.{SENTINEL_TABLE}"
            )
        )
    ).mappings().all()
    if len(rows) != 1:
        raise DestructiveDatabaseSafetyError(
            "disposable database sentinel is malformed"
        )
    row = rows[0]
    if (
        row["database_name"] != expected_database_name
        or row["purpose"] != purpose.value
        or row["schema_version"] != SENTINEL_SCHEMA_VERSION
        or row["ownership_marker"] != SENTINEL_OWNERSHIP_MARKER
        or not isinstance(row["created_at"], datetime)
    ):
        raise DestructiveDatabaseSafetyError(
            "disposable database sentinel does not match the destructive contract"
        )


def configured_database_endpoints(settings: DatabaseSettings) -> tuple[tuple[str, int, str], tuple[str, int, str]]:
    urls = settings.require_restore_urls()
    return database_endpoint_identity(urls.source), database_endpoint_identity(urls.restore)
