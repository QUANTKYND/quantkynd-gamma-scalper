import asyncio
import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import (
    BigInteger,
    Boolean,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import DBAPIError, IntegrityError

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
from app.persistence.postgres.engine import (
    create_database_engine,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import (
    DataFoundationFixture,
    deterministic_fixture,
)
from app.persistence.postgres.mappings import (
    catalogue_values,
    future_values,
    market_instrument_values,
    option_values,
    provider_mapping_values,
    trading_session_values,
    temporal_record_values,
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

DATA_1_1_TABLES = {
    "catalogue_versions",
    "market_instruments",
    "trading_sessions",
    "instrument_versions",
    "trading_session_versions",
    "underlying_instruments",
    "futures_contracts",
    "option_contracts",
    "provider_contract_mappings",
    "catalogue_version_records",
    "instrument_version_records",
    "provider_mapping_records",
    "trading_session_version_records",
}

RAW_MARKET_FRAME_COLUMNS = {
    "raw_event_id",
    "provider",
    "provider_schema_id",
    "provider_schema_sha256",
    "connection_session_id",
    "source_order_scope_id",
    "source_order",
    "frame_bytes",
    "frame_content_hash",
    "received_at",
    "available_at",
    "recorded_at",
    "capture_basis",
    "source_file_id",
    "source_record_id",
    "persistence_recorded_at",
}

RAW_MARKET_FRAME_CAPTURE_IDENTITY = (
    "provider",
    "provider_schema_id",
    "connection_session_id",
    "source_order_scope_id",
    "source_order",
)

RAW_MARKET_FRAME_INDEXES = {
    "ix_raw_market_frames_capture_order": (
        "provider",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        "raw_event_id",
    ),
    "ix_raw_market_frames_content_hash": (
        "frame_content_hash",
    ),
    "ix_raw_market_frames_persistence_order": (
        "persistence_recorded_at",
        "raw_event_id",
    ),
}


MARKET_NORMALIZATION_RESULT_COLUMNS = {
    "result_id",
    "raw_event_id",
    "normalization_schema_version",
    "normalizer_implementation_version",
    "response_type",
    "status",
    "decoded_entry_count",
    "accepted_entry_count",
    "failed_entry_count",
    "frame_failure_present",
    "unadopted_schema_paths",
    "present_unadopted_message_paths",
    "secondary_payload_paths_present",
    "full_result_hash",
    "adopted_semantics_hash",
    "metadata_payload",
    "persistence_recorded_at",
}

MARKET_NORMALIZATION_RESULT_INDEXES = {
    "ix_market_normalization_results_schema_raw": (
        "normalization_schema_version",
        "raw_event_id",
    ),
    "ix_market_normalization_results_persistence": (
        "normalization_schema_version",
        "persistence_recorded_at",
        "result_id",
    ),
    "ix_market_normalization_results_status": (
        "normalization_schema_version",
        "status",
        "result_id",
    ),
}


MARKET_OBSERVATION_COLUMNS = {
    "event_id",
    "raw_event_id",
    "event_type",
    "subject_id",
    "provider",
    "provider_contract_key",
    "economic_subject_id",
    "provider_mapping_id",
    "contract_version_id",
    "catalogue_version_id",
    "provider_mapping_record_id",
    "contract_version_record_id",
    "catalogue_version_record_id",
    "resolution_market_as_of",
    "resolution_known_as_of",
    "provider_timestamp",
    "exchange_timestamp",
    "received_at",
    "available_at",
    "recorded_at",
    "availability_basis",
    "source_order_scope_id",
    "source_order",
    "normalization_schema_version",
    "normalizer_implementation_version",
    "provider_sequence",
    "supersedes_event_id",
    "payload",
}

MARKET_OBSERVATION_INDEXES = {
    "ix_market_observations_subject_provider_time": (
        "normalization_schema_version",
        "economic_subject_id",
        "event_type",
        "provider_timestamp",
        "available_at",
        "event_id",
    ),
    "ix_market_observations_subject_availability": (
        "normalization_schema_version",
        "economic_subject_id",
        "availability_basis",
        "available_at",
        "event_id",
    ),
    "ix_market_observations_raw": (
        "raw_event_id",
        "event_id",
    ),
    "ix_market_observations_mapping_provenance": (
        "provider_mapping_id",
        "contract_version_id",
        "catalogue_version_id",
        "event_id",
    ),
    "ix_market_observations_temporal_provenance": (
        "provider_mapping_record_id",
        "contract_version_record_id",
        "catalogue_version_record_id",
        "event_id",
    ),
}

MARKET_RESULT_EVENT_COLUMNS = {
    "result_id",
    "raw_event_id",
    "event_ordinal",
    "event_id",
}

MARKET_FAILURE_COLUMNS = {
    "failure_id",
    "result_id",
    "raw_event_id",
    "scope",
    "reason_code",
    "provider_contract_key",
    "segment",
    "safe_detail_code",
    "selected_feed_union",
    "provider_depth_levels_present",
    "field_paths",
    "unadopted_schema_paths",
    "present_unadopted_message_paths",
    "payload",
}

MARKET_FAILURE_INDEXES = {
    "ix_market_normalization_failures_result_scope": (
        "result_id",
        "scope",
        "failure_id",
    ),
    "ix_market_normalization_failures_reason": (
        "reason_code",
        "failure_id",
    ),
}

MARKET_RESULT_FAILURE_COLUMNS = {
    "result_id",
    "raw_event_id",
    "failure_role",
    "failure_ordinal",
    "failure_id",
}


QUOTE_SUBTYPE_COLUMNS = {
    "event_id",
    "event_type",
    "subject_id",
    "feed_response_type",
    "request_mode",
    "feed_union",
    "is_snapshot",
    "presence_semantics",
    "numeric_basis",
    "quantity_basis",
    "bid_price",
    "bid_size",
    "ask_price",
    "ask_size",
    "last_price",
    "last_size",
    "last_trade_at",
    "previous_close_price",
    "reported_volume",
    "open_interest",
    "provider_depth_levels_present",
    "normalized_depth_levels",
    "unadopted_depth_level_count",
    "unadopted_schema_paths",
    "present_unadopted_message_paths",
    "secondary_payload_paths_present",
}

QUOTE_SUBTYPE_TABLES = (
    "underlying_quote_observations",
    "futures_quote_observations",
    "option_quote_observations",
)

STATUS_SUBTYPE_COLUMNS = {
    "event_id",
    "event_type",
    "subject_id",
    "segment",
    "provider_status_name",
    "provider_status_numeric",
    "status_is_known",
}


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

            await asyncio.to_thread(
                command.upgrade,
                config,
                INITIAL_REVISION,
            )
            assert await _revision(engine) == INITIAL_REVISION

            fixture = deterministic_fixture()
            await _insert_legacy_fixture(engine, fixture)

            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION

            await _assert_migrated_records(engine, fixture)
            await asyncio.to_thread(command.check, config)
            await _assert_head_schema(engine)

            await asyncio.to_thread(
                command.downgrade,
                config,
                INITIAL_REVISION,
            )
            assert await _revision(engine) == INITIAL_REVISION

            await asyncio.to_thread(
                command.downgrade,
                config,
                "base",
            )
            await _assert_foundation_tables_absent(engine)

            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION

            await asyncio.to_thread(command.check, config)
            await _assert_head_schema(engine)
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

            await asyncio.to_thread(
                command.upgrade,
                config,
                INITIAL_REVISION,
            )
            await _insert_legacy_superseded_session(engine)

            with pytest.raises(
                RuntimeError,
                match="legacy non-null superseded_at",
            ):
                await asyncio.to_thread(
                    command.upgrade,
                    config,
                    "head",
                )

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

            await asyncio.to_thread(
                command.upgrade,
                config,
                DATA_1_1_REVISION,
            )
            assert await _revision(engine) == DATA_1_1_REVISION

            await _assert_tables(
                engine,
                present=DATA_1_1_TABLES,
                absent=DATA_1_2_TABLES,
            )

            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION

            await _assert_tables(
                engine,
                present=EXPECTED_TABLES,
                absent=set(),
            )
            await _assert_head_schema(engine)

            await asyncio.to_thread(
                command.downgrade,
                config,
                DATA_1_1_REVISION,
            )
            assert await _revision(engine) == DATA_1_1_REVISION

            await _assert_tables(
                engine,
                present=DATA_1_1_TABLES,
                absent=DATA_1_2_TABLES,
            )

            await asyncio.to_thread(
                command.downgrade,
                config,
                "base",
            )
            await _assert_foundation_tables_absent(engine)

            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION

            await _assert_tables(
                engine,
                present=EXPECTED_TABLES,
                absent=set(),
            )
            await _assert_head_schema(engine)
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_temporal_provenance_foreign_keys_reject_cross_links(
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
            await asyncio.to_thread(command.upgrade, config, "head")

            fixture = deterministic_fixture()
            async with engine.begin() as connection:
                records = await _insert_head_provenance_fixture(
                    connection,
                    fixture,
                )
                raw_event_id = "sha256:" + "8" * 64
                result_id = "sha256:" + "9" * 64
                event_id = "sha256:" + "a" * 64
                now = RECORDED_AT + timedelta(hours=1)

                await connection.execute(
                    Base.metadata.tables[
                        "raw_market_frames"
                    ].insert().values(
                        raw_event_id=raw_event_id,
                        provider="upstox",
                        provider_schema_id="fixture-schema",
                        provider_schema_sha256="b" * 64,
                        connection_session_id="fixture-session",
                        source_order_scope_id="fixture-scope",
                        source_order=0,
                        frame_bytes=b"x",
                        frame_content_hash=(
                            "sha256:" + "c" * 64
                        ),
                        received_at=None,
                        available_at=now,
                        recorded_at=now,
                        capture_basis="historical_import",
                        source_file_id=None,
                        source_record_id=None,
                        persistence_recorded_at=now,
                    )
                )
                await connection.execute(
                    Base.metadata.tables[
                        "market_normalization_results"
                    ].insert().values(
                        result_id=result_id,
                        raw_event_id=raw_event_id,
                        normalization_schema_version=1,
                        normalizer_implementation_version=(
                            "upstox-v3-normalizer-1"
                        ),
                        response_type="live_feed",
                        status="complete",
                        decoded_entry_count=1,
                        accepted_entry_count=1,
                        failed_entry_count=0,
                        frame_failure_present=False,
                        unadopted_schema_paths=[],
                        present_unadopted_message_paths=[],
                        secondary_payload_paths_present=[],
                        full_result_hash=(
                            "sha256:" + "d" * 64
                        ),
                        adopted_semantics_hash=(
                            "sha256:" + "e" * 64
                        ),
                        metadata_payload={},
                        persistence_recorded_at=now,
                    )
                )

                observation_values = {
                    "event_id": event_id,
                    "raw_event_id": raw_event_id,
                    "event_type": "option_quote_observation",
                    "subject_id": fixture.option.contract_id,
                    "provider": "upstox",
                    "provider_contract_key": (
                        fixture.provider_mapping
                        .provider_contract_key
                    ),
                    "economic_subject_id": (
                        fixture.option.contract_id
                    ),
                    "provider_mapping_id": (
                        fixture.provider_mapping.mapping_id
                    ),
                    "contract_version_id": (
                        fixture.option_version.version_id
                    ),
                    "catalogue_version_id": (
                        fixture.catalogue.catalogue_version_id
                    ),
                    "provider_mapping_record_id": (
                        records["mapping"]
                    ),
                    "contract_version_record_id": (
                        records["option_version"]
                    ),
                    "catalogue_version_record_id": (
                        records["catalogue"]
                    ),
                    "resolution_market_as_of": now,
                    "resolution_known_as_of": now,
                    "provider_timestamp": now,
                    "exchange_timestamp": None,
                    "received_at": None,
                    "available_at": now,
                    "recorded_at": now,
                    "availability_basis": "historical_import",
                    "source_order_scope_id": "fixture-scope",
                    "source_order": 0,
                    "normalization_schema_version": 1,
                    "normalizer_implementation_version": (
                        "upstox-v3-normalizer-1"
                    ),
                    "provider_sequence": None,
                    "supersedes_event_id": None,
                    "payload": {},
                }
                await connection.execute(
                    Base.metadata.tables[
                        "market_observations"
                    ].insert().values(**observation_values)
                )

                invalid = {
                    **observation_values,
                    "event_id": "sha256:" + "f" * 64,
                    "contract_version_record_id": (
                        records["underlying_version"]
                    ),
                }
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(
                            Base.metadata.tables[
                                "market_observations"
                            ].insert().values(**invalid)
                        )
    finally:
        await dispose_database_engine(engine)


async def _insert_head_provenance_fixture(
    connection,
    fixture: DataFoundationFixture,
) -> dict[str, str]:
    tables = Base.metadata.tables

    await connection.execute(
        tables["catalogue_versions"].insert().values(
            **catalogue_values(fixture.catalogue)
        )
    )
    catalogue_record = catalogue_temporal_record(
        fixture.catalogue
    )
    await connection.execute(
        tables["catalogue_version_records"].insert().values(
            **temporal_record_values(
                catalogue_record,
                "catalogue_version_id",
            )
        )
    )

    for identity in (
        fixture.underlying,
        fixture.option,
    ):
        await connection.execute(
            tables["market_instruments"].insert().values(
                **market_instrument_values(identity)
            )
        )
    await connection.execute(
        tables["underlying_instruments"].insert().values(
            **underlying_values(fixture.underlying)
        )
    )
    await connection.execute(
        tables["option_contracts"].insert().values(
            **option_values(fixture.option)
        )
    )

    version_records = {}
    for label, version in (
        ("underlying_version", fixture.underlying_version),
        ("option_version", fixture.option_version),
    ):
        await connection.execute(
            tables["instrument_versions"].insert().values(
                **version_values(version)
            )
        )
        record = instrument_version_temporal_record(version)
        await connection.execute(
            tables["instrument_version_records"].insert().values(
                **temporal_record_values(
                    record,
                    "version_id",
                )
            )
        )
        version_records[label] = record.record_id

    await connection.execute(
        tables["provider_contract_mappings"].insert().values(
            **provider_mapping_values(
                fixture.provider_mapping
            )
        )
    )
    mapping_record = provider_mapping_temporal_record(
        fixture.provider_mapping
    )
    await connection.execute(
        tables["provider_mapping_records"].insert().values(
            **temporal_record_values(
                mapping_record,
                "mapping_id",
            )
        )
    )

    return {
        "catalogue": catalogue_record.record_id,
        "mapping": mapping_record.record_id,
        **version_records,
    }


async def _revision(engine) -> str | None:
    async with engine.connect() as connection:
        relation = await connection.scalar(
            text(
                "SELECT to_regclass("
                "'public.alembic_version'"
                ")"
            )
        )

        if relation is None:
            return None

        return await connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )


async def _insert_legacy_fixture(
    engine,
    fixture: DataFoundationFixture,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            _insert_legacy_fixture_sync,
            fixture,
        )


def _insert_legacy_fixture_sync(
    connection,
    fixture: DataFoundationFixture,
) -> None:
    metadata = MetaData()
    metadata.reflect(connection)

    def insert(
        table_name: str,
        values: dict[str, object],
    ) -> None:
        connection.execute(
            metadata.tables[table_name]
            .insert()
            .values(**values)
        )

    insert(
        "catalogue_versions",
        {
            **catalogue_values(fixture.catalogue),
            "recorded_at": fixture.catalogue.recorded_at,
        },
    )

    for identity in (
        fixture.underlying,
        fixture.future,
        fixture.option,
    ):
        insert(
            "market_instruments",
            market_instrument_values(identity),
        )

    insert(
        "underlying_instruments",
        underlying_values(fixture.underlying),
    )
    insert(
        "futures_contracts",
        future_values(fixture.future),
    )
    insert(
        "option_contracts",
        option_values(fixture.option),
    )

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
            **provider_mapping_values(
                fixture.provider_mapping
            ),
            "recorded_at": (
                fixture.provider_mapping.recorded_at
            ),
            "superseded_at": None,
        },
    )

    insert(
        "trading_sessions",
        trading_session_values(fixture.session),
    )
    insert(
        "trading_session_versions",
        {
            **trading_session_version_values(
                fixture.session_version
            ),
            "recorded_at": (
                fixture.session_version.recorded_at
            ),
            "superseded_at": None,
        },
    )


async def _assert_migrated_records(
    engine,
    fixture: DataFoundationFixture,
) -> None:
    expected = {
        "catalogue_version_records": {
            catalogue_temporal_record(
                fixture.catalogue
            ).record_id
        },
        "instrument_version_records": {
            instrument_version_temporal_record(value).record_id
            for value in (
                fixture.underlying_version,
                fixture.future_version,
                fixture.option_version,
            )
        },
        "provider_mapping_records": {
            provider_mapping_temporal_record(
                fixture.provider_mapping
            ).record_id
        },
        "trading_session_version_records": {
            trading_session_version_temporal_record(
                fixture.session_version
            ).record_id
        },
    }

    async with engine.connect() as connection:
        for table_name, record_ids in expected.items():
            migrated = set(
                (
                    await connection.execute(
                        text(
                            f"SELECT record_id "
                            f"FROM {table_name}"
                        )
                    )
                ).scalars()
            )
            assert migrated == record_ids


async def _insert_legacy_superseded_session(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO trading_sessions ("
                "session_id, "
                "exchange, "
                "session_date, "
                "session_kind"
                ") VALUES ("
                ":id, "
                "'NSE', "
                ":session_date, "
                "'regular'"
                ")"
            ),
            {
                "id": "sha256:" + "3" * 64,
                "session_date": date(2026, 8, 4),
            },
        )

        await connection.execute(
            text(
                "INSERT INTO trading_session_versions ("
                "session_version_id, "
                "session_id, "
                "pre_open_at, "
                "open_at, "
                "close_at, "
                "post_close_at, "
                "timezone, "
                "status, "
                "recorded_at, "
                "superseded_at"
                ") VALUES ("
                ":version_id, "
                ":session_id, "
                "NULL, "
                ":open_at, "
                ":close_at, "
                "NULL, "
                "'Asia/Kolkata', "
                "'closed', "
                ":recorded_at, "
                ":superseded_at"
                ")"
            ),
            {
                "version_id": "sha256:" + "4" * 64,
                "session_id": "sha256:" + "3" * 64,
                "open_at": RECORDED_AT,
                "close_at": (
                    RECORDED_AT + timedelta(hours=6)
                ),
                "recorded_at": RECORDED_AT,
                "superseded_at": (
                    RECORDED_AT + timedelta(hours=1)
                ),
            },
        )


async def _assert_head_schema(engine) -> None:
    async with engine.connect() as connection:
        details = await connection.run_sync(
            _schema_details
        )

    assert EXPECTED_TABLES <= details["tables"]
    assert details["columns"]
    assert details["primary_keys"]
    assert details["checks"]
    assert details["record_foreign_keys"]
    assert details["record_indexes"]

    raw = details["raw_market_frames"]
    assert set(raw["columns"]) == RAW_MARKET_FRAME_COLUMNS
    assert raw["primary_key"] == ("raw_event_id",)
    assert isinstance(
        raw["columns"]["source_order"]["type"],
        BigInteger,
    )
    assert isinstance(
        raw["columns"]["frame_bytes"]["type"],
        LargeBinary,
    )
    assert (
        RAW_MARKET_FRAME_CAPTURE_IDENTITY
        in raw["unique_constraints"]
    )
    for index_name, expected_columns in (
        RAW_MARKET_FRAME_INDEXES.items()
    ):
        assert (
            raw["indexes"][index_name]["columns"]
            == expected_columns
        )

    result = details[
        "market_normalization_results"
    ]
    assert (
        set(result["columns"])
        == MARKET_NORMALIZATION_RESULT_COLUMNS
    )
    assert result["primary_key"] == ("result_id",)
    assert isinstance(
        result["columns"][
            "frame_failure_present"
        ]["type"],
        Boolean,
    )
    assert isinstance(
        result["columns"][
            "unadopted_schema_paths"
        ]["type"],
        ARRAY,
    )
    assert isinstance(
        result["columns"][
            "present_unadopted_message_paths"
        ]["type"],
        ARRAY,
    )
    assert isinstance(
        result["columns"][
            "secondary_payload_paths_present"
        ]["type"],
        ARRAY,
    )
    assert isinstance(
        result["columns"][
            "metadata_payload"
        ]["type"],
        JSONB,
    )
    assert (
        (
            "raw_event_id",
            "normalization_schema_version",
        )
        in result["unique_constraints"]
    )
    assert (
        (
            "result_id",
            "raw_event_id",
        )
        in result["unique_constraints"]
    )
    _assert_foreign_key(
        result,
        ("raw_event_id",),
        "raw_market_frames",
        ("raw_event_id",),
    )
    for index_name, expected_columns in (
        MARKET_NORMALIZATION_RESULT_INDEXES.items()
    ):
        assert (
            result["indexes"][index_name]["columns"]
            == expected_columns
        )

    assert (
        "record_id",
        "mapping_id",
    ) in details[
        "provider_mapping_records"
    ]["unique_constraints"]
    assert (
        "record_id",
        "version_id",
    ) in details[
        "instrument_version_records"
    ]["unique_constraints"]
    assert (
        "record_id",
        "catalogue_version_id",
    ) in details[
        "catalogue_version_records"
    ]["unique_constraints"]

    observations = details["market_observations"]
    assert (
        set(observations["columns"])
        == MARKET_OBSERVATION_COLUMNS
    )
    assert observations["primary_key"] == ("event_id",)
    assert isinstance(
        observations["columns"]["source_order"]["type"],
        BigInteger,
    )
    assert isinstance(
        observations["columns"]["payload"]["type"],
        JSONB,
    )
    assert (
        ("event_id", "raw_event_id")
        in observations["unique_constraints"]
    )
    assert (
        ("event_id", "event_type", "subject_id")
        in observations["unique_constraints"]
    )
    _assert_foreign_key(
        observations,
        ("raw_event_id",),
        "raw_market_frames",
        ("raw_event_id",),
    )
    _assert_foreign_key(
        observations,
        (
            "provider_mapping_record_id",
            "provider_mapping_id",
        ),
        "provider_mapping_records",
        ("record_id", "mapping_id"),
    )
    _assert_foreign_key(
        observations,
        (
            "contract_version_record_id",
            "contract_version_id",
        ),
        "instrument_version_records",
        ("record_id", "version_id"),
    )
    _assert_foreign_key(
        observations,
        (
            "catalogue_version_record_id",
            "catalogue_version_id",
        ),
        "catalogue_version_records",
        ("record_id", "catalogue_version_id"),
    )
    for index_name, expected_columns in (
        MARKET_OBSERVATION_INDEXES.items()
    ):
        assert (
            observations["indexes"][index_name]["columns"]
            == expected_columns
        )

    for table_name in QUOTE_SUBTYPE_TABLES:
        quote = details[table_name]
        assert set(quote["columns"]) == QUOTE_SUBTYPE_COLUMNS
        assert quote["primary_key"] == ("event_id",)
        assert isinstance(
            quote["columns"]["bid_price"]["type"],
            Numeric,
        )
        assert isinstance(
            quote["columns"]["bid_size"]["type"],
            BigInteger,
        )
        assert isinstance(
            quote["columns"]["is_snapshot"]["type"],
            Boolean,
        )
        assert isinstance(
            quote["columns"][
                "unadopted_schema_paths"
            ]["type"],
            ARRAY,
        )
        _assert_foreign_key(
            quote,
            (
                "event_id",
                "event_type",
                "subject_id",
            ),
            "market_observations",
            (
                "event_id",
                "event_type",
                "subject_id",
            ),
        )
        assert quote["indexes"][
            f"ix_{table_name}_mode_union"
        ]["columns"] == (
            "request_mode",
            "feed_union",
            "event_id",
        )

    status = details[
        "market_segment_status_observations"
    ]
    assert set(status["columns"]) == STATUS_SUBTYPE_COLUMNS
    assert status["primary_key"] == ("event_id",)
    assert isinstance(
        status["columns"][
            "provider_status_numeric"
        ]["type"],
        Integer,
    )
    assert isinstance(
        status["columns"]["status_is_known"]["type"],
        Boolean,
    )
    _assert_foreign_key(
        status,
        (
            "event_id",
            "event_type",
            "subject_id",
        ),
        "market_observations",
        (
            "event_id",
            "event_type",
            "subject_id",
        ),
    )
    assert status["indexes"][
        "ix_market_segment_status_segment_code"
    ]["columns"] == (
        "segment",
        "provider_status_numeric",
        "event_id",
    )

    result_events = details[
        "market_normalization_result_events"
    ]
    assert (
        set(result_events["columns"])
        == MARKET_RESULT_EVENT_COLUMNS
    )
    assert result_events["primary_key"] == (
        "result_id",
        "event_ordinal",
    )
    assert (
        ("result_id", "event_id")
        in result_events["unique_constraints"]
    )
    _assert_foreign_key(
        result_events,
        ("result_id", "raw_event_id"),
        "market_normalization_results",
        ("result_id", "raw_event_id"),
    )
    _assert_foreign_key(
        result_events,
        ("event_id", "raw_event_id"),
        "market_observations",
        ("event_id", "raw_event_id"),
    )
    assert (
        result_events["indexes"][
            "ix_market_normalization_result_events_event"
        ]["columns"]
        == ("event_id", "result_id")
    )

    failures = details[
        "market_normalization_failures"
    ]
    assert (
        set(failures["columns"])
        == MARKET_FAILURE_COLUMNS
    )
    assert failures["primary_key"] == ("failure_id",)
    assert isinstance(
        failures["columns"]["field_paths"]["type"],
        ARRAY,
    )
    assert isinstance(
        failures["columns"]["payload"]["type"],
        JSONB,
    )
    assert (
        (
            "failure_id",
            "result_id",
            "raw_event_id",
        )
        in failures["unique_constraints"]
    )
    _assert_foreign_key(
        failures,
        ("result_id", "raw_event_id"),
        "market_normalization_results",
        ("result_id", "raw_event_id"),
    )
    for index_name, expected_columns in (
        MARKET_FAILURE_INDEXES.items()
    ):
        assert (
            failures["indexes"][index_name]["columns"]
            == expected_columns
        )

    result_failures = details[
        "market_normalization_result_failures"
    ]
    assert (
        set(result_failures["columns"])
        == MARKET_RESULT_FAILURE_COLUMNS
    )
    assert result_failures["primary_key"] == (
        "result_id",
        "failure_role",
        "failure_ordinal",
    )
    assert (
        (
            "result_id",
            "raw_event_id",
            "failure_role",
            "failure_ordinal",
        )
        in result_failures["unique_constraints"]
    )
    _assert_foreign_key(
        result_failures,
        ("result_id", "raw_event_id"),
        "market_normalization_results",
        ("result_id", "raw_event_id"),
    )
    _assert_foreign_key(
        result_failures,
        (
            "failure_id",
            "result_id",
            "raw_event_id",
        ),
        "market_normalization_failures",
        (
            "failure_id",
            "result_id",
            "raw_event_id",
        ),
    )
    frame_index = result_failures["indexes"][
        "uq_market_normalization_result_failures_one_frame"
    ]
    assert frame_index["columns"] == ("result_id",)
    assert frame_index["unique"] is True
    assert (
        result_failures["indexes"][
            "ix_market_normalization_result_failures_failure"
        ]["columns"]
        == ("failure_id", "result_id")
    )


def _assert_foreign_key(
    details: dict[str, object],
    constrained_columns: tuple[str, ...],
    referred_table: str,
    referred_columns: tuple[str, ...],
) -> None:
    assert any(
        actual_constrained == constrained_columns
        and actual_table == referred_table
        and actual_referred == referred_columns
        and ondelete in (None, "NO ACTION")
        for (
            actual_constrained,
            actual_table,
            actual_referred,
            ondelete,
        ) in details["foreign_keys"]
    )


def _table_details(schema, table_name: str) -> dict[str, object]:
    return {
        "columns": {
            column["name"]: column
            for column in schema.get_columns(table_name)
        },
        "primary_key": tuple(
            schema.get_pk_constraint(table_name)[
                "constrained_columns"
            ]
        ),
        "unique_constraints": {
            tuple(constraint["column_names"])
            for constraint in schema.get_unique_constraints(
                table_name
            )
        },
        "indexes": {
            index["name"]: {
                "columns": tuple(index["column_names"]),
                "unique": bool(index["unique"]),
            }
            for index in schema.get_indexes(table_name)
        },
        "foreign_keys": {
            (
                tuple(
                    foreign_key["constrained_columns"]
                ),
                foreign_key["referred_table"],
                tuple(
                    foreign_key["referred_columns"]
                ),
                foreign_key.get(
                    "options",
                    {},
                ).get("ondelete"),
            )
            for foreign_key in schema.get_foreign_keys(
                table_name
            )
        },
    }


def _schema_details(connection) -> dict[str, object]:
    schema = inspect(connection)

    return {
        "tables": set(schema.get_table_names()),
        "columns": all(
            schema.get_columns(table)
            for table in EXPECTED_TABLES
        ),
        "primary_keys": all(
            schema.get_pk_constraint(table)[
                "constrained_columns"
            ]
            for table in EXPECTED_TABLES
        ),
        "checks": all(
            schema.get_check_constraints(table)
            for table in EXPECTED_TABLES
        ),
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
            any(
                index["unique"]
                for index in schema.get_indexes(table)
            )
            for table in (
                "catalogue_version_records",
                "instrument_version_records",
                "provider_mapping_records",
                "trading_session_version_records",
            )
        ),
        "raw_market_frames": _table_details(
            schema,
            "raw_market_frames",
        ),
        "market_normalization_results": _table_details(
            schema,
            "market_normalization_results",
        ),
        "provider_mapping_records": _table_details(
            schema,
            "provider_mapping_records",
        ),
        "instrument_version_records": _table_details(
            schema,
            "instrument_version_records",
        ),
        "catalogue_version_records": _table_details(
            schema,
            "catalogue_version_records",
        ),
        "market_observations": _table_details(
            schema,
            "market_observations",
        ),
        "market_normalization_result_events": (
            _table_details(
                schema,
                "market_normalization_result_events",
            )
        ),
        "underlying_quote_observations": _table_details(
            schema,
            "underlying_quote_observations",
        ),
        "futures_quote_observations": _table_details(
            schema,
            "futures_quote_observations",
        ),
        "option_quote_observations": _table_details(
            schema,
            "option_quote_observations",
        ),
        "market_segment_status_observations": _table_details(
            schema,
            "market_segment_status_observations",
        ),
        "market_normalization_failures": _table_details(
            schema,
            "market_normalization_failures",
        ),
        "market_normalization_result_failures": (
            _table_details(
                schema,
                "market_normalization_result_failures",
            )
        ),
    }


async def _assert_foundation_tables_absent(engine) -> None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(
            lambda value: set(
                inspect(value).get_table_names()
            )
        )

    assert EXPECTED_TABLES.isdisjoint(tables)


async def _assert_tables(
    engine,
    *,
    present: set[str],
    absent: set[str],
) -> None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(
            lambda value: set(
                inspect(value).get_table_names()
            )
        )

    assert present <= tables
    assert absent.isdisjoint(tables)

DATA_1_4_TABLES = (
    "raw_market_frames",
    "market_normalization_results",
    "market_observations",
    "underlying_quote_observations",
    "futures_quote_observations",
    "option_quote_observations",
    "market_segment_status_observations",
    "market_normalization_result_events",
    "market_normalization_failures",
    "market_normalization_result_failures",
    "provider_subscription_instrument_sets",
    "provider_subscription_instrument_set_keys",
    "provider_lifecycle_batches",
    "raw_provider_lifecycle_events",
    "provider_lifecycle_batch_events",
    "provider_lifecycle_observations",
    "provider_connection_lifecycle_observations",
    "provider_subscription_lifecycle_observations",
    "provider_lifecycle_batch_observations",
)


def _raw_frame_values(
    *,
    marker: str,
    source_order: int,
    frame_bytes: bytes = b"x",
    available_at: datetime | None = None,
) -> dict[str, object]:
    when = available_at or (
        RECORDED_AT + timedelta(hours=1)
    )
    return {
        "raw_event_id": "sha256:" + marker * 64,
        "provider": "upstox",
        "provider_schema_id": "fixture-schema",
        "provider_schema_sha256": "a" * 64,
        "connection_session_id": "fixture-session",
        "source_order_scope_id": "fixture-scope",
        "source_order": source_order,
        "frame_bytes": frame_bytes,
        "frame_content_hash": (
            "sha256:"
            + hashlib.sha256(frame_bytes).hexdigest()
        ),
        "received_at": None,
        "available_at": when,
        "recorded_at": when,
        "capture_basis": "historical_import",
        "source_file_id": None,
        "source_record_id": None,
        "persistence_recorded_at": when,
    }


@pytest.mark.anyio
async def test_data14_downgrade_refuses_non_empty_history_before_ddl(
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
            await asyncio.to_thread(command.upgrade, config, "head")

            raw_values = _raw_frame_values(
                marker="1",
                source_order=0,
            )
            async with engine.begin() as connection:
                await connection.execute(
                    Base.metadata.tables[
                        "raw_market_frames"
                    ].insert().values(**raw_values)
                )

            with pytest.raises(
                RuntimeError,
                match=(
                    "DATA-1.4 downgrade refused.*"
                    "raw_market_frames"
                ),
            ):
                await asyncio.to_thread(
                    command.downgrade,
                    config,
                    "20260804_03",
                )

            assert await _revision(engine) == EXPECTED_REVISION

            async with engine.connect() as connection:
                row_count = await connection.scalar(
                    text(
                        "SELECT count(*) "
                        "FROM raw_market_frames"
                    )
                )
                trigger_names = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT tgname "
                                "FROM pg_trigger "
                                "WHERE tgrelid = "
                                "'raw_market_frames'::regclass "
                                "AND NOT tgisinternal"
                            )
                        )
                    ).scalars()
                )
                constraint_names = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT conname "
                                "FROM pg_constraint "
                                "WHERE conname = ANY("
                                "CAST(:names AS text[]))"
                            ),
                            {
                                "names": [
                                    "uq_catalogue_version_records_record_semantic",
                                    "uq_instrument_version_records_record_semantic",
                                    "uq_provider_mapping_records_record_semantic",
                                ]
                            },
                        )
                    ).scalars()
                )

            assert row_count == 1
            assert trigger_names == {
                "data14_raw_market_frames_immutable",
                "data14_raw_market_frames_no_truncate",
            }
            assert constraint_names == {
                "uq_catalogue_version_records_record_semantic",
                "uq_instrument_version_records_record_semantic",
                "uq_provider_mapping_records_record_semantic",
            }
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_raw_frame_one_byte_roundtrip_and_zero_byte_rejection(
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
            await asyncio.to_thread(command.upgrade, config, "head")

            async with engine.begin() as connection:
                one_byte = _raw_frame_values(
                    marker="2",
                    source_order=0,
                    frame_bytes=b"x",
                )
                await connection.execute(
                    Base.metadata.tables[
                        "raw_market_frames"
                    ].insert().values(**one_byte)
                )
                stored = await connection.scalar(
                    text(
                        "SELECT frame_bytes "
                        "FROM raw_market_frames "
                        "WHERE raw_event_id = :raw_event_id"
                    ),
                    {"raw_event_id": one_byte["raw_event_id"]},
                )
                assert bytes(stored) == b"x"

                zero_byte = _raw_frame_values(
                    marker="3",
                    source_order=1,
                    frame_bytes=b"",
                )
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(
                            Base.metadata.tables[
                                "raw_market_frames"
                            ].insert().values(**zero_byte)
                        )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_raw_frame_append_only_trigger_rejects_mutations(
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
            await asyncio.to_thread(command.upgrade, config, "head")

            raw_values = _raw_frame_values(
                marker="4",
                source_order=0,
            )
            async with engine.begin() as connection:
                await connection.execute(
                    Base.metadata.tables[
                        "raw_market_frames"
                    ].insert().values(**raw_values)
                )

            statements = (
                "UPDATE raw_market_frames "
                "SET provider_schema_id = 'changed'",
                "DELETE FROM raw_market_frames",
                "TRUNCATE raw_market_frames",
            )
            for statement in statements:
                async with engine.begin() as connection:
                    with pytest.raises(DBAPIError):
                        async with connection.begin_nested():
                            await connection.execute(text(statement))

            async with engine.connect() as connection:
                assert await connection.scalar(
                    text(
                        "SELECT count(*) "
                        "FROM raw_market_frames"
                    )
                ) == 1
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_raw_frame_rejects_infinite_semantic_timestamp(
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
            await asyncio.to_thread(command.upgrade, config, "head")

            for marker, literal, source_order in (
                ("5", "infinity", 0),
                ("6", "-infinity", 1),
            ):
                values = _raw_frame_values(
                    marker=marker,
                    source_order=source_order,
                )
                async with engine.begin() as connection:
                    with pytest.raises(IntegrityError):
                        async with connection.begin_nested():
                            await connection.execute(
                                text(
                                    "INSERT INTO raw_market_frames ("
                                    "raw_event_id, provider, "
                                    "provider_schema_id, "
                                    "provider_schema_sha256, "
                                    "connection_session_id, "
                                    "source_order_scope_id, "
                                    "source_order, frame_bytes, "
                                    "frame_content_hash, received_at, "
                                    "available_at, recorded_at, "
                                    "capture_basis, source_file_id, "
                                    "source_record_id, "
                                    "persistence_recorded_at"
                                    ") VALUES ("
                                    ":raw_event_id, :provider, "
                                    ":provider_schema_id, "
                                    ":provider_schema_sha256, "
                                    ":connection_session_id, "
                                    ":source_order_scope_id, "
                                    ":source_order, :frame_bytes, "
                                    ":frame_content_hash, NULL, "
                                    f"'{literal}'::timestamptz, "
                                    ":recorded_at, :capture_basis, "
                                    "NULL, NULL, :persistence_recorded_at"
                                    ")"
                                ),
                                values,
                            )
    finally:
        await dispose_database_engine(engine)


def test_all_data14_foreign_keys_are_no_action() -> None:
    for table_name in DATA_1_4_TABLES:
        table = Base.metadata.tables[table_name]
        for constraint in table.foreign_key_constraints:
            assert constraint.elements
            assert all(
                element.ondelete == "NO ACTION"
                for element in constraint.elements
            )
