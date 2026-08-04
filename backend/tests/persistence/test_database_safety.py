import pytest
from sqlalchemy import text

from app.core.database_config import DatabaseSettings
from app.persistence.postgres.database_safety import (
    SENTINEL_SCHEMA,
    SENTINEL_TABLE,
    DestructiveDatabasePurpose,
    DestructiveDatabaseSafetyError,
    destructive_database_lease,
)
from app.persistence.postgres.engine import create_database_engine, dispose_database_engine


@pytest.mark.anyio
async def test_missing_sentinel_is_rejected_and_not_created(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(f"ALTER TABLE {SENTINEL_SCHEMA}.{SENTINEL_TABLE} RENAME TO hidden_sentinel")
            )
        try:
            with pytest.raises(DestructiveDatabaseSafetyError, match="sentinel is missing"):
                async with destructive_database_lease(
                    engine,
                    postgres_url,
                    postgres_settings,
                    DestructiveDatabasePurpose.INTEGRATION,
                ):
                    pass
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(
                        text(
                            "SELECT to_regclass('quantkynd_control.disposable_database_sentinel')"
                        )
                    )
                    is None
                )
        finally:
            async with engine.begin() as connection:
                await connection.execute(
                    text(f"ALTER TABLE {SENTINEL_SCHEMA}.hidden_sentinel RENAME TO {SENTINEL_TABLE}")
                )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("column", "invalid_value"),
    (("purpose", "restore"), ("database_name", "another_database")),
)
async def test_mismatched_sentinel_is_rejected(
    column: str,
    invalid_value: str,
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    expected = (
        DestructiveDatabasePurpose.INTEGRATION.value
        if column == "purpose"
        else postgres_settings.database_expected_integration_test_name
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"UPDATE {SENTINEL_SCHEMA}.{SENTINEL_TABLE} SET {column} = :invalid_value"
                ),
                {"invalid_value": invalid_value},
            )
        try:
            with pytest.raises(DestructiveDatabaseSafetyError, match="does not match"):
                async with destructive_database_lease(
                    engine,
                    postgres_url,
                    postgres_settings,
                    DestructiveDatabasePurpose.INTEGRATION,
                ):
                    pass
        finally:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        f"UPDATE {SENTINEL_SCHEMA}.{SENTINEL_TABLE} SET {column} = :expected"
                    ),
                    {"expected": expected},
                )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_drop_public_preserves_control_schema_sentinel(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    try:
        async with destructive_database_lease(
            engine,
            postgres_url,
            postgres_settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ) as lease:
            await lease.drop_and_recreate_public()
            relation = await lease.connection.scalar(
                text("SELECT to_regclass('quantkynd_control.disposable_database_sentinel')")
            )
            assert relation == f"{SENTINEL_SCHEMA}.{SENTINEL_TABLE}"
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_advisory_lock_rejects_concurrent_destructive_run(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    first_engine = create_database_engine(postgres_settings)
    second_engine = create_database_engine(postgres_settings)
    try:
        async with destructive_database_lease(
            first_engine,
            postgres_url,
            postgres_settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ):
            with pytest.raises(DestructiveDatabaseSafetyError, match="advisory lock"):
                async with destructive_database_lease(
                    second_engine,
                    postgres_url,
                    postgres_settings,
                    DestructiveDatabasePurpose.INTEGRATION,
                ):
                    pass
    finally:
        await dispose_database_engine(first_engine)
        await dispose_database_engine(second_engine)
