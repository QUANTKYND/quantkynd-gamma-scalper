import asyncio

from sqlalchemy import inspect, text

from alembic import command

from app.persistence.postgres.base import Base
from app.core.database_config import DatabaseSettings
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.migrations import (
    alembic_config,
    downgrade_to_base,
    upgrade_to_head,
)
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


EXPECTED_TABLES = set(Base.metadata.tables)
EXPECTED_REVISION = "20260804_01"


def test_upgrade_downgrade_reupgrade_and_metadata_drift(postgres_url: str) -> None:
    downgrade_to_base(postgres_url)
    upgrade_to_head(postgres_url)
    config = alembic_config(postgres_url)
    command.check(config)
    asyncio.run(assert_head_schema(postgres_url))
    asyncio.run(seed_and_read_fixture(postgres_url))
    downgrade_to_base(postgres_url)
    asyncio.run(assert_foundation_tables_absent(postgres_url))
    upgrade_to_head(postgres_url)
    command.check(config)
    asyncio.run(seed_and_read_fixture(postgres_url))


async def assert_head_schema(database_url: str) -> None:
    engine = create_database_engine(DatabaseSettings(database_url=database_url, _env_file=None))
    try:
        async with engine.connect() as connection:
            details = await connection.run_sync(schema_details)
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert EXPECTED_TABLES <= details["tables"]
        assert details["columns"]
        assert details["primary_keys"]
        assert details["checks"]
        assert details["mapping_foreign_keys"]
        assert details["version_foreign_keys"]
        assert details["mapping_indexes"]
        assert revision == EXPECTED_REVISION
    finally:
        await dispose_database_engine(engine)


def schema_details(connection) -> dict[str, object]:
    schema = inspect(connection)
    return {
        "tables": set(schema.get_table_names()),
        "columns": all(schema.get_columns(table) for table in EXPECTED_TABLES),
        "primary_keys": all(
            schema.get_pk_constraint(table)["constrained_columns"] for table in EXPECTED_TABLES
        ),
        "checks": all(schema.get_check_constraints(table) for table in EXPECTED_TABLES),
        "mapping_foreign_keys": schema.get_foreign_keys("provider_contract_mappings"),
        "version_foreign_keys": schema.get_foreign_keys("instrument_versions"),
        "mapping_indexes": schema.get_indexes("provider_contract_mappings"),
    }


async def assert_foundation_tables_absent(database_url: str) -> None:
    engine = create_database_engine(DatabaseSettings(database_url=database_url, _env_file=None))
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda value: set(inspect(value).get_table_names()))
        assert EXPECTED_TABLES.isdisjoint(tables)
    finally:
        await dispose_database_engine(engine)


async def seed_and_read_fixture(database_url: str) -> None:
    engine = create_database_engine(DatabaseSettings(database_url=database_url, _env_file=None))
    fixture = deterministic_fixture()
    try:
        factory = create_session_factory(engine)
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            assert await unit_of_work.instruments.get_identity(fixture.option.contract_id) == fixture.option
    finally:
        await dispose_database_engine(engine)
