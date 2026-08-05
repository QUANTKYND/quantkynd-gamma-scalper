import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import MetaData, inspect, text

from app.core.database_config import DatabaseSettings
from app.instruments.temporal_records import (
    catalogue_temporal_record,
    instrument_version_temporal_record,
    provider_mapping_temporal_record,
    trading_session_version_temporal_record,
)
from app.persistence.postgres.base import Base
from app.persistence.postgres.database_safety import (
    DestructiveDatabasePurpose,
    destructive_database_lease,
)
from app.persistence.postgres.engine import create_database_engine, dispose_database_engine
from app.persistence.postgres.fixtures import DataFoundationFixture, deterministic_fixture
from app.persistence.postgres.mappings import (
    catalogue_values,
    future_values,
    market_instrument_values,
    option_values,
    provider_mapping_values,
    trading_session_values,
    trading_session_version_values,
    underlying_values,
    version_values,
)
from app.persistence.postgres.migrations import alembic_config


EXPECTED_TABLES = set(Base.metadata.tables)
INITIAL_REVISION = "20260804_01"
DATA_1_1_REVISION = "20260804_02"
EXPECTED_REVISION = "20260804_04"
RECORDED_AT = datetime(2026, 8, 4, 3, 30, tzinfo=UTC)
DATA_1_2_TABLES = {
    "catalogue_source_artifacts",
    "catalogue_ingestion_runs",
    "catalogue_row_outcomes",
    "catalogue_memberships",
}
DATA_1_1_TABLES = EXPECTED_TABLES - DATA_1_2_TABLES


@pytest.mark.anyio
async def test_upgrade_downgrade_reupgrade_and_metadata_drift(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)
    try:
        async with destructive_database_lease(
            engine,
            postgres_url,
            postgres_settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ) as lease:
            await lease.drop_and_recreate_public()
            await asyncio.to_thread(command.upgrade, config, INITIAL_REVISION)
            assert await _revision(engine) == INITIAL_REVISION
            fixture = deterministic_fixture()
            await _insert_legacy_fixture(engine, fixture)
            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION
            await _assert_migrated_records(engine, fixture)
            await asyncio.to_thread(command.check, config)
            await _assert_head_schema(engine)
            await asyncio.to_thread(command.downgrade, config, INITIAL_REVISION)
            assert await _revision(engine) == INITIAL_REVISION
            await asyncio.to_thread(command.downgrade, config, "base")
            await _assert_foundation_tables_absent(engine)
            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION
            await asyncio.to_thread(command.check, config)
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_followup_migration_rejects_legacy_superseded_at(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)
    try:
        async with destructive_database_lease(
            engine,
            postgres_url,
            postgres_settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ) as lease:
            await lease.drop_and_recreate_public()
            await asyncio.to_thread(command.upgrade, config, INITIAL_REVISION)
            await _insert_legacy_superseded_session(engine)
            with pytest.raises(RuntimeError, match="legacy non-null superseded_at"):
                await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == INITIAL_REVISION
            await lease.drop_and_recreate_public()
            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_data_1_2_migration_lifecycle_preserves_data_1_1(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)
    try:
        async with destructive_database_lease(
            engine,
            postgres_url,
            postgres_settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ) as lease:
            await lease.drop_and_recreate_public()
            await asyncio.to_thread(command.upgrade, config, DATA_1_1_REVISION)
            assert await _revision(engine) == DATA_1_1_REVISION
            await _assert_tables(engine, present=DATA_1_1_TABLES, absent=DATA_1_2_TABLES)
            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION
            await _assert_tables(engine, present=EXPECTED_TABLES, absent=set())
            await asyncio.to_thread(command.downgrade, config, DATA_1_1_REVISION)
            assert await _revision(engine) == DATA_1_1_REVISION
            await _assert_tables(engine, present=DATA_1_1_TABLES, absent=DATA_1_2_TABLES)
            await asyncio.to_thread(command.downgrade, config, "base")
            await _assert_foundation_tables_absent(engine)
            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION
            await _assert_tables(engine, present=EXPECTED_TABLES, absent=set())
    finally:
        await dispose_database_engine(engine)


async def _revision(engine) -> str | None:
    async with engine.connect() as connection:
        relation = await connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
        if relation is None:
            return None
        return await connection.scalar(text("SELECT version_num FROM alembic_version"))


async def _insert_legacy_fixture(engine, fixture: DataFoundationFixture) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(_insert_legacy_fixture_sync, fixture)


def _insert_legacy_fixture_sync(connection, fixture: DataFoundationFixture) -> None:
    metadata = MetaData()
    metadata.reflect(connection)

    def insert(table_name: str, values: dict[str, object]) -> None:
        connection.execute(metadata.tables[table_name].insert().values(**values))

    insert(
        "catalogue_versions",
        {**catalogue_values(fixture.catalogue), "recorded_at": fixture.catalogue.recorded_at},
    )
    for identity in (fixture.underlying, fixture.future, fixture.option):
        insert("market_instruments", market_instrument_values(identity))
    insert("underlying_instruments", underlying_values(fixture.underlying))
    insert("futures_contracts", future_values(fixture.future))
    insert("option_contracts", option_values(fixture.option))
    for version in (
        fixture.underlying_version,
        fixture.future_version,
        fixture.option_version,
    ):
        insert(
            "instrument_versions",
            {
                **version_values(version),
                "recorded_at": version.recorded_at,
                "superseded_at": None,
            },
        )
    insert(
        "provider_contract_mappings",
        {
            **provider_mapping_values(fixture.provider_mapping),
            "recorded_at": fixture.provider_mapping.recorded_at,
            "superseded_at": None,
        },
    )
    insert("trading_sessions", trading_session_values(fixture.session))
    insert(
        "trading_session_versions",
        {
            **trading_session_version_values(fixture.session_version),
            "recorded_at": fixture.session_version.recorded_at,
            "superseded_at": None,
        },
    )


async def _assert_migrated_records(engine, fixture: DataFoundationFixture) -> None:
    expected = {
        "catalogue_version_records": {catalogue_temporal_record(fixture.catalogue).record_id},
        "instrument_version_records": {
            instrument_version_temporal_record(value).record_id
            for value in (
                fixture.underlying_version,
                fixture.future_version,
                fixture.option_version,
            )
        },
        "provider_mapping_records": {
            provider_mapping_temporal_record(fixture.provider_mapping).record_id
        },
        "trading_session_version_records": {
            trading_session_version_temporal_record(fixture.session_version).record_id
        },
    }
    async with engine.connect() as connection:
        for table_name, record_ids in expected.items():
            migrated = set(
                (await connection.execute(text(f"SELECT record_id FROM {table_name}"))).scalars()
            )
            assert migrated == record_ids


async def _insert_legacy_superseded_session(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO trading_sessions (session_id, exchange, session_date, session_kind) VALUES (:id, 'NSE', :session_date, 'regular')"
            ),
            {"id": "sha256:" + "3" * 64, "session_date": date(2026, 8, 4)},
        )
        await connection.execute(
            text(
                "INSERT INTO trading_session_versions (session_version_id, session_id, pre_open_at, open_at, close_at, post_close_at, timezone, status, recorded_at, superseded_at) VALUES (:version_id, :session_id, NULL, :open_at, :close_at, NULL, 'Asia/Kolkata', 'closed', :recorded_at, :superseded_at)"
            ),
            {
                "version_id": "sha256:" + "4" * 64,
                "session_id": "sha256:" + "3" * 64,
                "open_at": RECORDED_AT,
                "close_at": RECORDED_AT + timedelta(hours=6),
                "recorded_at": RECORDED_AT,
                "superseded_at": RECORDED_AT + timedelta(hours=1),
            },
        )


async def _assert_head_schema(engine) -> None:
    async with engine.connect() as connection:
        details = await connection.run_sync(_schema_details)
    assert EXPECTED_TABLES <= details["tables"]
    assert details["columns"]
    assert details["primary_keys"]
    assert details["checks"]
    assert details["record_foreign_keys"]
    assert details["record_indexes"]


def _schema_details(connection) -> dict[str, object]:
    schema = inspect(connection)
    return {
        "tables": set(schema.get_table_names()),
        "columns": all(schema.get_columns(table) for table in EXPECTED_TABLES),
        "primary_keys": all(
            schema.get_pk_constraint(table)["constrained_columns"] for table in EXPECTED_TABLES
        ),
        "checks": all(schema.get_check_constraints(table) for table in EXPECTED_TABLES),
        "record_foreign_keys": all(
            len(schema.get_foreign_keys(table)) == 2
            for table in (
                "catalogue_version_records",
                "instrument_version_records",
                "provider_mapping_records",
                "trading_session_version_records",
            )
        ),
        "record_indexes": all(
            any(index["unique"] for index in schema.get_indexes(table))
            for table in (
                "catalogue_version_records",
                "instrument_version_records",
                "provider_mapping_records",
                "trading_session_version_records",
            )
        ),
    }


async def _assert_foundation_tables_absent(engine) -> None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda value: set(inspect(value).get_table_names()))
    assert EXPECTED_TABLES.isdisjoint(tables)


async def _assert_tables(engine, *, present: set[str], absent: set[str]) -> None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda value: set(inspect(value).get_table_names()))
    assert present <= tables
    assert absent.isdisjoint(tables)
