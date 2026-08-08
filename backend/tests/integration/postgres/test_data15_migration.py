import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database_config import DatabaseSettings
from app.persistence.postgres.database_safety import (
    DestructiveDatabasePurpose,
    destructive_database_lease,
)
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.migrations import alembic_config
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


DATA14_REVISION = "20260804_04"
DATA15_REVISION = "20260804_05"
RECEIPT_TABLES = (
    "market_data_quality_provider_mapping_receipts",
    "market_data_quality_instrument_version_receipts",
    "market_data_quality_catalogue_version_receipts",
    "market_data_quality_trading_session_receipts",
)
DATA15_TABLES = {
    "market_data_quality_policies",
    "market_data_quality_policy_versions",
    "market_data_quality_policy_source_artifacts",
    "market_data_quality_policy_reason_definitions",
    "market_data_quality_assessment_runs",
    "market_data_quality_assessments",
    "market_data_quality_assessment_reasons",
    "market_data_quality_assessment_dependencies",
    "market_data_quality_dependency_candidates",
    "market_data_quality_run_assessments",
    *RECEIPT_TABLES,
    "market_data_quality_catalogue_membership_receipts",
}


async def _revision(engine) -> str:
    async with engine.connect() as connection:
        return (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()


@pytest.mark.anyio
async def test_data15_upgrade_backfills_one_receipt_per_legacy_temporal_record(
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
            await asyncio.to_thread(command.upgrade, config, DATA14_REVISION)

            fixture = deterministic_fixture()
            await seed_fixture(
                PostgresUnitOfWork(create_session_factory(engine)),
                fixture,
            )

            async with engine.connect() as connection:
                legacy_counts = {
                    table_name: (
                        await connection.execute(
                            text(f"SELECT count(*) FROM {table_name}")
                        )
                    ).scalar_one()
                    for table_name in (
                        "provider_mapping_records",
                        "instrument_version_records",
                        "catalogue_version_records",
                        "trading_session_version_records",
                    )
                }

            await asyncio.to_thread(command.upgrade, config, DATA15_REVISION)
            assert await _revision(engine) == DATA15_REVISION

            async with engine.connect() as connection:
                receipt_counts = {
                    table_name: (
                        await connection.execute(
                            text(f"SELECT count(*) FROM {table_name}")
                        )
                    ).scalar_one()
                    for table_name in RECEIPT_TABLES
                }
                assert receipt_counts == {
                    "market_data_quality_provider_mapping_receipts": legacy_counts[
                        "provider_mapping_records"
                    ],
                    "market_data_quality_instrument_version_receipts": legacy_counts[
                        "instrument_version_records"
                    ],
                    "market_data_quality_catalogue_version_receipts": legacy_counts[
                        "catalogue_version_records"
                    ],
                    "market_data_quality_trading_session_receipts": legacy_counts[
                        "trading_session_version_records"
                    ],
                }
                clocks = (
                    await connection.execute(
                        text(
                            "SELECT count(DISTINCT receipt_at) FROM ("
                            + " UNION ALL ".join(
                                f"SELECT receipt_at FROM {table_name}"
                                for table_name in RECEIPT_TABLES
                            )
                            + ") AS receipts"
                        )
                    )
                ).scalar_one()
                assert clocks == 1
                invalid_basis = (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM ("
                            + " UNION ALL ".join(
                                "SELECT receipt_basis, bootstrap_revision "
                                f"FROM {table_name}"
                                for table_name in RECEIPT_TABLES
                            )
                            + ") AS receipts "
                            "WHERE receipt_basis <> 'legacy_bootstrap' "
                            "OR bootstrap_revision <> '20260804_05'"
                        )
                    )
                ).scalar_one()
                assert invalid_basis == 0

            with pytest.raises(RuntimeError, match="non-empty tables"):
                await asyncio.to_thread(command.downgrade, config, DATA14_REVISION)
            assert await _revision(engine) == DATA15_REVISION
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_data15_deferred_receipt_trigger_rejects_unreceipted_temporal_insert(
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
            await asyncio.to_thread(command.upgrade, config, DATA14_REVISION)
            fixture = deterministic_fixture()
            await seed_fixture(
                PostgresUnitOfWork(create_session_factory(engine)),
                fixture,
            )
            await asyncio.to_thread(command.upgrade, config, DATA15_REVISION)

            new_record_id = "sha256:" + "f" * 64
            with pytest.raises(DBAPIError, match="lacks a receipt"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO instrument_version_records ("
                            "record_id, version_id, scope_id, recorded_at, "
                            "supersedes_record_id, source_provenance_id"
                            ") VALUES ("
                            ":record_id, :version_id, :scope_id, :recorded_at, NULL, NULL)"
                        ),
                        {
                            "record_id": new_record_id,
                            "version_id": fixture.option_version.version_id,
                            "scope_id": "data15-receipt-test",
                            "recorded_at": datetime.now(UTC) + timedelta(seconds=1),
                        },
                    )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_data15_empty_upgrade_check_and_downgrade_cycle(
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
            await asyncio.to_thread(command.upgrade, config, DATA15_REVISION)
            assert await _revision(engine) == DATA15_REVISION

            async with engine.connect() as connection:
                server_major = int(
                    (
                        await connection.execute(text("SHOW server_version_num"))
                    ).scalar_one()
                ) // 10000
                assert server_major == 17
                tables = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT tablename FROM pg_tables "
                                "WHERE schemaname = 'public'"
                            )
                        )
                    ).scalars()
                )
                assert DATA15_TABLES <= tables

            await asyncio.to_thread(command.check, config)
            await asyncio.to_thread(command.downgrade, config, DATA14_REVISION)
            assert await _revision(engine) == DATA14_REVISION
            await asyncio.to_thread(command.upgrade, config, DATA15_REVISION)
            assert await _revision(engine) == DATA15_REVISION
    finally:
        await dispose_database_engine(engine)
