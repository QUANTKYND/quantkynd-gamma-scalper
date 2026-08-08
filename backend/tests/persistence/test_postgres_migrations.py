import asyncio
import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from alembic.script import ScriptDirectory
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
from app.core.hashing import stable_hash
from app.instruments.temporal_records import (
    catalogue_temporal_record,
    instrument_version_temporal_record,
    provider_mapping_temporal_record,
    trading_session_version_temporal_record,
)
from app.persistence.postgres.base import Base
from app.persistence.postgres import models as _postgres_models
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
DATA_1_3_REVISION = "20260804_03"
DATA_1_4_REVISION = "20260804_04"
EXPECTED_REVISION = "20260804_05"
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

INSTRUMENT_SET_COLUMNS = {
    "instrument_keys_digest",
    "instrument_key_count",
    "provider_contract_keys",
    "canonical_payload_hash",
}

INSTRUMENT_SET_KEY_COLUMNS = {
    "instrument_keys_digest",
    "key_ordinal",
    "provider_contract_key",
}

PROVIDER_LIFECYCLE_BATCH_COLUMNS = {
    "lifecycle_batch_id",
    "lifecycle_kind",
    "provider",
    "normalization_schema_version",
    "normalizer_implementation_version",
    "input_count",
    "unique_count",
    "normalized_count",
    "duplicate_count",
    "batch_hash",
    "normalized_sequence_hash",
    "metadata_payload",
    "persistence_recorded_at",
}

PROVIDER_LIFECYCLE_BATCH_INDEXES = {
    "ix_provider_lifecycle_batches_acceptance": (
        "normalization_schema_version",
        "provider",
        "lifecycle_kind",
        "persistence_recorded_at",
        "lifecycle_batch_id",
    ),
}

RAW_PROVIDER_LIFECYCLE_EVENT_COLUMNS = {
    "raw_event_id",
    "lifecycle_kind",
    "provider",
    "connection_session_id",
    "subscription_scope_id",
    "previous_state",
    "state",
    "source_order_scope_id",
    "source_order",
    "occurred_at",
    "available_at",
    "recorded_at",
    "request_mode",
    "instrument_keys_digest",
    "instrument_key_count",
    "redacted_reason_code",
    "provider_sequence",
    "payload",
}

RAW_PROVIDER_LIFECYCLE_EVENT_INDEXES = {
    "ix_raw_provider_lifecycle_events_scope_order": (
        "provider",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        "raw_event_id",
    ),
    "ix_raw_provider_lifecycle_events_subscription_scope": (
        "provider",
        "connection_session_id",
        "subscription_scope_id",
        "source_order",
        "raw_event_id",
    ),
}

PROVIDER_LIFECYCLE_BATCH_EVENT_COLUMNS = {
    "lifecycle_batch_id",
    "lifecycle_kind",
    "input_ordinal",
    "raw_event_id",
    "is_exact_duplicate",
    "first_occurrence_ordinal",
}

PROVIDER_LIFECYCLE_BATCH_EVENT_INDEXES = {
    "ix_lifecycle_batch_events_raw": (
        "raw_event_id",
        "lifecycle_batch_id",
        "input_ordinal",
    ),
    "ix_lifecycle_batch_events_first_occurrence": (
        "lifecycle_batch_id",
        "raw_event_id",
        "first_occurrence_ordinal",
    ),
}


PROVIDER_LIFECYCLE_OBSERVATION_COLUMNS = {
    "event_id",
    "raw_event_id",
    "event_type",
    "subject_id",
    "lifecycle_kind",
    "provider",
    "connection_session_id",
    "source_order_scope_id",
    "source_order",
    "occurred_at",
    "available_at",
    "recorded_at",
    "normalization_schema_version",
    "normalizer_implementation_version",
    "provider_sequence",
    "payload",
}

PROVIDER_LIFECYCLE_OBSERVATION_INDEXES = {
    "ix_provider_lifecycle_observations_scope_order": (
        "normalization_schema_version",
        "provider",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        "event_id",
    ),
    "ix_provider_lifecycle_observations_subject_time": (
        "normalization_schema_version",
        "subject_id",
        "lifecycle_kind",
        "available_at",
        "event_id",
    ),
    "ix_provider_lifecycle_observations_raw": (
        "raw_event_id",
        "event_id",
    ),
}

PROVIDER_CONNECTION_LIFECYCLE_OBSERVATION_COLUMNS = {
    "event_id",
    "event_type",
    "subject_id",
    "lifecycle_kind",
    "connection_session_id",
    "previous_state",
    "state",
    "redacted_reason_code",
}

PROVIDER_CONNECTION_LIFECYCLE_OBSERVATION_INDEXES = {
    "ix_provider_connection_lifecycle_state": (
        "connection_session_id",
        "state",
        "event_id",
    ),
}

PROVIDER_SUBSCRIPTION_LIFECYCLE_OBSERVATION_COLUMNS = {
    "event_id",
    "event_type",
    "subject_id",
    "lifecycle_kind",
    "connection_session_id",
    "subscription_scope_id",
    "previous_state",
    "state",
    "request_mode",
    "instrument_keys_digest",
    "instrument_key_count",
    "redacted_reason_code",
}

PROVIDER_SUBSCRIPTION_LIFECYCLE_OBSERVATION_INDEXES = {
    "ix_provider_subscription_lifecycle_scope_state": (
        "connection_session_id",
        "subscription_scope_id",
        "state",
        "event_id",
    ),
    "ix_provider_subscription_lifecycle_instrument_set": (
        "instrument_keys_digest",
        "event_id",
    ),
}

PROVIDER_LIFECYCLE_BATCH_OBSERVATION_COLUMNS = {
    "lifecycle_batch_id",
    "lifecycle_kind",
    "event_ordinal",
    "event_id",
}

PROVIDER_LIFECYCLE_BATCH_OBSERVATION_INDEXES = {
    "ix_lifecycle_batch_observations_event": (
        "event_id",
        "lifecycle_batch_id",
        "event_ordinal",
    ),
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


async def _public_trigger_exists(
    engine,
    *,
    table_name: str,
    trigger_name: str,
) -> bool:
    async with engine.connect() as connection:
        return bool(
            await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_trigger AS trigger
                        JOIN pg_class AS relation
                          ON relation.oid = trigger.tgrelid
                        JOIN pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = 'public'
                          AND relation.relname = :table_name
                          AND trigger.tgname = :trigger_name
                          AND NOT trigger.tgisinternal
                    )
                    """
                ),
                {
                    "table_name": table_name,
                    "trigger_name": trigger_name,
                },
            )
        )


async def _public_function_exists(
    engine,
    function_name: str,
) -> bool:
    async with engine.connect() as connection:
        return bool(
            await connection.scalar(
                text(
                    """
                    SELECT to_regprocedure(:signature)
                           IS NOT NULL
                    """
                ),
                {
                    "signature": (
                        f"public.{function_name}()"
                    )
                },
            )
        )


async def _public_table_names(
    engine,
    table_names: tuple[str, ...],
) -> set[str]:
    existing: set[str] = set()

    async with engine.connect() as connection:
        for table_name in table_names:
            relation = await connection.scalar(
                text(
                    "SELECT to_regclass(:relation_name)"
                ),
                {
                    "relation_name": (
                        f"public.{table_name}"
                    )
                },
            )
            if relation is not None:
                existing.add(table_name)

    return existing


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

            with pytest.raises(
                RuntimeError,
                match=(
                    "DATA-1.5 downgrade refused.*"
                    "market_data_quality_.*_receipts"
                ),
            ):
                await asyncio.to_thread(
                    command.downgrade,
                    config,
                    INITIAL_REVISION,
                )
            assert await _revision(engine) == EXPECTED_REVISION

            # DATA-1.5 receipts are durable history. Exercise the
            # empty downgrade path only after a guarded destructive reset.
            await lease.drop_and_recreate_public()
            await asyncio.to_thread(command.upgrade, config, "head")
            assert await _revision(engine) == EXPECTED_REVISION

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


def _data15_temporal_receipt_values(
    *,
    target_kind: str,
    record_id: str,
    receipt_at: datetime,
) -> dict[str, object]:
    payload = {
        "target_kind": target_kind,
        "record_id": record_id,
        "receipt_at": receipt_at,
        "receipt_basis": "repository_insert",
        "bootstrap_revision": None,
    }
    return {
        "record_id": record_id,
        "receipt_at": receipt_at,
        "receipt_basis": "repository_insert",
        "bootstrap_revision": None,
        "canonical_payload_hash": stable_hash(payload),
    }


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
    receipt_at = RECORDED_AT + timedelta(microseconds=1)
    await connection.execute(
        tables[
            "market_data_quality_catalogue_version_receipts"
        ].insert().values(
            **_data15_temporal_receipt_values(
                target_kind="catalogue_version_record",
                record_id=catalogue_record.record_id,
                receipt_at=receipt_at,
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
        await connection.execute(
            tables[
                "market_data_quality_instrument_version_receipts"
            ].insert().values(
                **_data15_temporal_receipt_values(
                    target_kind="instrument_version_record",
                    record_id=record.record_id,
                    receipt_at=receipt_at,
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
    await connection.execute(
        tables[
            "market_data_quality_provider_mapping_receipts"
        ].insert().values(
            **_data15_temporal_receipt_values(
                target_kind="provider_mapping_record",
                record_id=mapping_record.record_id,
                receipt_at=receipt_at,
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
    instrument_sets = details[
        "provider_subscription_instrument_sets"
    ]
    assert (
        set(instrument_sets["columns"])
        == INSTRUMENT_SET_COLUMNS
    )
    assert instrument_sets["primary_key"] == (
        "instrument_keys_digest",
    )
    assert isinstance(
        instrument_sets["columns"][
            "instrument_key_count"
        ]["type"],
        Integer,
    )
    assert isinstance(
        instrument_sets["columns"][
            "provider_contract_keys"
        ]["type"],
        JSONB,
    )

    instrument_set_keys = details[
        "provider_subscription_instrument_set_keys"
    ]
    assert (
        set(instrument_set_keys["columns"])
        == INSTRUMENT_SET_KEY_COLUMNS
    )
    assert instrument_set_keys["primary_key"] == (
        "instrument_keys_digest",
        "key_ordinal",
    )
    assert (
        (
            "instrument_keys_digest",
            "provider_contract_key",
        )
        in instrument_set_keys["unique_constraints"]
    )
    lifecycle_batches = details[
        "provider_lifecycle_batches"
    ]

    assert (
        set(lifecycle_batches["columns"])
        == PROVIDER_LIFECYCLE_BATCH_COLUMNS
    )
    assert lifecycle_batches["primary_key"] == (
        "lifecycle_batch_id",
    )

    for column_name in (
        "normalization_schema_version",
        "input_count",
        "unique_count",
        "normalized_count",
        "duplicate_count",
    ):
        assert isinstance(
            lifecycle_batches["columns"][
                column_name
            ]["type"],
            Integer,
        )

    assert isinstance(
        lifecycle_batches["columns"][
            "metadata_payload"
        ]["type"],
        JSONB,
    )

    assert (
        "lifecycle_batch_id",
        "lifecycle_kind",
    ) in lifecycle_batches["unique_constraints"]

    for index_name, expected_columns in (
        PROVIDER_LIFECYCLE_BATCH_INDEXES.items()
    ):
        assert (
            lifecycle_batches["indexes"][
                index_name
            ]["columns"]
            == expected_columns
        )

    raw_lifecycle = details[
        "raw_provider_lifecycle_events"
    ]

    assert (
        set(raw_lifecycle["columns"])
        == RAW_PROVIDER_LIFECYCLE_EVENT_COLUMNS
    )
    assert raw_lifecycle["primary_key"] == (
        "raw_event_id",
    )
    assert isinstance(
        raw_lifecycle["columns"]["source_order"]["type"],
        BigInteger,
    )
    assert isinstance(
        raw_lifecycle["columns"][
            "provider_sequence"
        ]["type"],
        BigInteger,
    )
    assert isinstance(
        raw_lifecycle["columns"][
            "instrument_key_count"
        ]["type"],
        Integer,
    )
    assert isinstance(
        raw_lifecycle["columns"]["payload"]["type"],
        JSONB,
    )

    assert (
        "raw_event_id",
        "lifecycle_kind",
    ) in raw_lifecycle["unique_constraints"]

    _assert_foreign_key(
        raw_lifecycle,
        ("instrument_keys_digest",),
        "provider_subscription_instrument_sets",
        ("instrument_keys_digest",),
    )

    for index_name, expected_columns in (
        RAW_PROVIDER_LIFECYCLE_EVENT_INDEXES.items()
    ):
        assert (
            raw_lifecycle["indexes"][index_name]["columns"]
            == expected_columns
        )

    batch_events = details[
        "provider_lifecycle_batch_events"
    ]

    assert (
        set(batch_events["columns"])
        == PROVIDER_LIFECYCLE_BATCH_EVENT_COLUMNS
    )
    assert batch_events["primary_key"] == (
        "lifecycle_batch_id",
        "input_ordinal",
    )

    assert isinstance(
        batch_events["columns"][
            "input_ordinal"
        ]["type"],
        Integer,
    )
    assert isinstance(
        batch_events["columns"][
            "first_occurrence_ordinal"
        ]["type"],
        Integer,
    )
    assert isinstance(
        batch_events["columns"][
            "is_exact_duplicate"
        ]["type"],
        Boolean,
    )

    assert (
        "lifecycle_batch_id",
        "raw_event_id",
        "input_ordinal",
    ) in batch_events["unique_constraints"]

    _assert_foreign_key(
        batch_events,
        (
            "lifecycle_batch_id",
            "lifecycle_kind",
        ),
        "provider_lifecycle_batches",
        (
            "lifecycle_batch_id",
            "lifecycle_kind",
        ),
    )

    _assert_foreign_key(
        batch_events,
        (
            "raw_event_id",
            "lifecycle_kind",
        ),
        "raw_provider_lifecycle_events",
        (
            "raw_event_id",
            "lifecycle_kind",
        ),
    )

    _assert_foreign_key(
        batch_events,
        (
            "lifecycle_batch_id",
            "raw_event_id",
            "first_occurrence_ordinal",
        ),
        "provider_lifecycle_batch_events",
        (
            "lifecycle_batch_id",
            "raw_event_id",
            "input_ordinal",
        ),
    )

    for index_name, expected_columns in (
        PROVIDER_LIFECYCLE_BATCH_EVENT_INDEXES.items()
    ):
        assert (
            batch_events["indexes"][
                index_name
            ]["columns"]
            == expected_columns
        )

    lifecycle_observations = details[
        "provider_lifecycle_observations"
    ]

    assert (
        set(lifecycle_observations["columns"])
        == PROVIDER_LIFECYCLE_OBSERVATION_COLUMNS
    )
    assert lifecycle_observations["primary_key"] == (
        "event_id",
    )
    assert isinstance(
        lifecycle_observations["columns"][
            "source_order"
        ]["type"],
        BigInteger,
    )
    assert isinstance(
        lifecycle_observations["columns"][
            "provider_sequence"
        ]["type"],
        BigInteger,
    )
    assert isinstance(
        lifecycle_observations["columns"][
            "normalization_schema_version"
        ]["type"],
        Integer,
    )
    assert isinstance(
        lifecycle_observations["columns"][
            "payload"
        ]["type"],
        JSONB,
    )

    assert (
        "event_id",
        "lifecycle_kind",
    ) in lifecycle_observations["unique_constraints"]
    assert (
        "event_id",
        "raw_event_id",
        "lifecycle_kind",
    ) in lifecycle_observations["unique_constraints"]
    assert (
        "raw_event_id",
        "normalization_schema_version",
    ) in lifecycle_observations["unique_constraints"]
    assert (
        "event_id",
        "event_type",
        "subject_id",
        "lifecycle_kind",
        "connection_session_id",
    ) in lifecycle_observations["unique_constraints"]

    _assert_foreign_key(
        lifecycle_observations,
        (
            "raw_event_id",
            "lifecycle_kind",
        ),
        "raw_provider_lifecycle_events",
        (
            "raw_event_id",
            "lifecycle_kind",
        ),
    )

    for index_name, expected_columns in (
        PROVIDER_LIFECYCLE_OBSERVATION_INDEXES.items()
    ):
        assert (
            lifecycle_observations["indexes"][
                index_name
            ]["columns"]
            == expected_columns
        )

    connection_observations = details[
        "provider_connection_lifecycle_observations"
    ]

    assert (
        set(connection_observations["columns"])
        == PROVIDER_CONNECTION_LIFECYCLE_OBSERVATION_COLUMNS
    )
    assert connection_observations["primary_key"] == (
        "event_id",
    )

    _assert_foreign_key(
        connection_observations,
        (
            "event_id",
            "event_type",
            "subject_id",
            "lifecycle_kind",
            "connection_session_id",
        ),
        "provider_lifecycle_observations",
        (
            "event_id",
            "event_type",
            "subject_id",
            "lifecycle_kind",
            "connection_session_id",
        ),
    )

    for index_name, expected_columns in (
        PROVIDER_CONNECTION_LIFECYCLE_OBSERVATION_INDEXES.items()
    ):
        assert (
            connection_observations["indexes"][
                index_name
            ]["columns"]
            == expected_columns
        )

    subscription_observations = details[
        "provider_subscription_lifecycle_observations"
    ]

    assert (
        set(subscription_observations["columns"])
        == PROVIDER_SUBSCRIPTION_LIFECYCLE_OBSERVATION_COLUMNS
    )
    assert subscription_observations["primary_key"] == (
        "event_id",
    )
    assert isinstance(
        subscription_observations["columns"][
            "instrument_key_count"
        ]["type"],
        Integer,
    )

    _assert_foreign_key(
        subscription_observations,
        (
            "event_id",
            "event_type",
            "subject_id",
            "lifecycle_kind",
            "connection_session_id",
        ),
        "provider_lifecycle_observations",
        (
            "event_id",
            "event_type",
            "subject_id",
            "lifecycle_kind",
            "connection_session_id",
        ),
    )
    _assert_foreign_key(
        subscription_observations,
        ("instrument_keys_digest",),
        "provider_subscription_instrument_sets",
        ("instrument_keys_digest",),
    )

    for index_name, expected_columns in (
        PROVIDER_SUBSCRIPTION_LIFECYCLE_OBSERVATION_INDEXES.items()
    ):
        assert (
            subscription_observations["indexes"][
                index_name
            ]["columns"]
            == expected_columns
        )

    batch_observations = details[
        "provider_lifecycle_batch_observations"
    ]

    assert (
        set(batch_observations["columns"])
        == PROVIDER_LIFECYCLE_BATCH_OBSERVATION_COLUMNS
    )
    assert batch_observations["primary_key"] == (
        "lifecycle_batch_id",
        "event_ordinal",
    )
    assert isinstance(
        batch_observations["columns"][
            "event_ordinal"
        ]["type"],
        Integer,
    )
    assert (
        "lifecycle_batch_id",
        "event_id",
        "lifecycle_kind",
    ) in batch_observations["unique_constraints"]

    _assert_foreign_key(
        batch_observations,
        (
            "lifecycle_batch_id",
            "lifecycle_kind",
        ),
        "provider_lifecycle_batches",
        (
            "lifecycle_batch_id",
            "lifecycle_kind",
        ),
    )
    _assert_foreign_key(
        batch_observations,
        (
            "event_id",
            "lifecycle_kind",
        ),
        "provider_lifecycle_observations",
        (
            "event_id",
            "lifecycle_kind",
        ),
    )

    for index_name, expected_columns in (
        PROVIDER_LIFECYCLE_BATCH_OBSERVATION_INDEXES.items()
    ):
        assert (
            batch_observations["indexes"][
                index_name
            ]["columns"]
            == expected_columns
        )

    _assert_foreign_key(
        instrument_set_keys,
        ("instrument_keys_digest",),
        "provider_subscription_instrument_sets",
        ("instrument_keys_digest",),
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
        "provider_subscription_instrument_sets": _table_details(
            schema,
            "provider_subscription_instrument_sets",
        ),
        "provider_subscription_instrument_set_keys": _table_details(
            schema,
            "provider_subscription_instrument_set_keys",
        ),
        "provider_lifecycle_batches": _table_details(
            schema,
            "provider_lifecycle_batches",
        ),
        "raw_provider_lifecycle_events": _table_details(
            schema,
            "raw_provider_lifecycle_events",
        ),
        "provider_lifecycle_batch_events": _table_details(
            schema,
            "provider_lifecycle_batch_events",
        ),
        "provider_lifecycle_observations": _table_details(
            schema,
            "provider_lifecycle_observations",
        ),
        "provider_connection_lifecycle_observations": (
            _table_details(
                schema,
                "provider_connection_lifecycle_observations",
            )
        ),
        "provider_subscription_lifecycle_observations": (
            _table_details(
                schema,
                "provider_subscription_lifecycle_observations",
            )
        ),
        "provider_lifecycle_batch_observations": (
            _table_details(
                schema,
                "provider_lifecycle_batch_observations",
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


def _lifecycle_batch_values(
    *,
    marker: str,
    **overrides,
) -> dict[str, object]:
    values = {
        "lifecycle_batch_id": (
            "sha256:" + marker * 64
        ),
        "lifecycle_kind": "connection",
        "provider": "upstox",
        "normalization_schema_version": 1,
        "normalizer_implementation_version": (
            "upstox-v3-normalizer-1"
        ),
        "input_count": 3,
        "unique_count": 2,
        "normalized_count": 2,
        "duplicate_count": 1,
        "batch_hash": "sha256:" + "a" * 64,
        "normalized_sequence_hash": (
            "sha256:" + "b" * 64
        ),
        "metadata_payload": {
            "fixture": "provider_lifecycle_batch",
        },
        "persistence_recorded_at": (
            RECORDED_AT + timedelta(hours=1)
        ),
    }
    values.update(overrides)
    return values


@pytest.mark.anyio
async def test_provider_lifecycle_batch_checks_reject_invalid_roots(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)
    table = Base.metadata.tables[
        "provider_lifecycle_batches"
    ]

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
                "head",
            )

            # Prove that the valid immediate row shape is accepted.
            # Roll back rather than committing an incomplete lifecycle
            # aggregate because deferred event and observation
            # membership checks require the complete batch.
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    valid = _lifecycle_batch_values(
                        marker="1",
                    )
                    await connection.execute(
                        table.insert().values(**valid)
                    )

                    stored = (
                        await connection.execute(
                            text(
                                "SELECT "
                                "input_count, "
                                "unique_count, "
                                "normalized_count, "
                                "duplicate_count "
                                "FROM provider_lifecycle_batches "
                                "WHERE lifecycle_batch_id = "
                                ":lifecycle_batch_id"
                            ),
                            {
                                "lifecycle_batch_id": (
                                    valid[
                                        "lifecycle_batch_id"
                                    ]
                                )
                            },
                        )
                    ).mappings().one()

                    assert dict(stored) == {
                        "input_count": 3,
                        "unique_count": 2,
                        "normalized_count": 2,
                        "duplicate_count": 1,
                    }
                finally:
                    await transaction.rollback()

            invalid_rows = (
                _lifecycle_batch_values(
                    marker="2",
                    lifecycle_batch_id="not-a-hash",
                ),
                _lifecycle_batch_values(
                    marker="3",
                    lifecycle_kind="other",
                ),
                _lifecycle_batch_values(
                    marker="4",
                    normalized_count=1,
                ),
                _lifecycle_batch_values(
                    marker="5",
                    normalizer_implementation_version=(
                        "other-normalizer"
                    ),
                ),
                _lifecycle_batch_values(
                    marker="6",
                    metadata_payload=[],
                ),
                _lifecycle_batch_values(
                    marker="7",
                    input_count=1,
                    unique_count=0,
                    normalized_count=0,
                    duplicate_count=1,
                ),
            )

            for invalid in invalid_rows:
                with pytest.raises(IntegrityError):
                    async with engine.begin() as connection:
                        await connection.execute(
                            table.insert().values(
                                **invalid
                            )
                        )
    finally:
        await dispose_database_engine(engine)


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
async def test_data14_downgrade_fails_when_owned_lifecycle_function_is_missing(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(DATA_1_4_REVISION)
    assert revision is not None

    data14_tables = tuple(revision.module.TABLES)

    damaged_trigger = (
        "data14_provider_lifecycle_"
        "observation_subtype_integrity"
    )
    damaged_function = (
        "data14_validate_provider_"
        "lifecycle_observation_subtype"
    )

    restored_function = (
        "data14_validate_subscription_"
        "instrument_key_ordinal"
    )

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
                EXPECTED_REVISION,
            )

            assert (
                await _revision(engine)
                == EXPECTED_REVISION
            )

            # The validation function has a dependent
            # constraint trigger, so remove both as committed
            # deliberate schema damage.
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        f"DROP TRIGGER {damaged_trigger} "
                        "ON provider_lifecycle_observations"
                    )
                )
                await connection.execute(
                    text(
                        f"DROP FUNCTION {damaged_function}()"
                    )
                )

            assert not await _public_trigger_exists(
                engine,
                table_name=(
                    "provider_lifecycle_observations"
                ),
                trigger_name=damaged_trigger,
            )
            assert not await _public_function_exists(
                engine,
                damaged_function,
            )

            with pytest.raises(DBAPIError):
                await asyncio.to_thread(
                    command.downgrade,
                    config,
                    DATA_1_3_REVISION,
                )

            assert (
                await _revision(engine)
                == EXPECTED_REVISION
            )

            # The failed downgrade had already removed generic
            # triggers, the generic mutation function, all
            # tables and earlier lifecycle functions. All of
            # those operations must have rolled back.
            assert (
                await _public_table_names(
                    engine,
                    data14_tables,
                )
                == set(data14_tables)
            )

            assert await _public_trigger_exists(
                engine,
                table_name="raw_market_frames",
                trigger_name=(
                    "data14_raw_market_frames_immutable"
                ),
            )

            assert await _public_function_exists(
                engine,
                "data14_reject_mutation",
            )

            assert await _public_function_exists(
                engine,
                restored_function,
            )

            # The deliberately damaged function remains absent;
            # the downgrade transaction must not manufacture it.
            assert not await _public_function_exists(
                engine,
                damaged_function,
            )

            await lease.drop_and_recreate_public()

            await asyncio.to_thread(
                command.upgrade,
                config,
                EXPECTED_REVISION,
            )

            assert (
                await _revision(engine)
                == EXPECTED_REVISION
            )

            assert await _public_function_exists(
                engine,
                damaged_function,
            )

            await asyncio.to_thread(
                command.check,
                config,
            )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_data14_downgrade_fails_when_owned_trigger_is_missing(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(DATA_1_4_REVISION)
    assert revision is not None

    data14_tables = tuple(revision.module.TABLES)

    damaged_table = (
        "provider_lifecycle_batch_observations"
    )
    damaged_trigger = (
        "data14_provider_lifecycle_batch_"
        "observations_no_truncate"
    )

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
                EXPECTED_REVISION,
            )

            assert (
                await _revision(engine)
                == EXPECTED_REVISION
            )

            # Commit deliberate schema damage before attempting
            # the downgrade.
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        f"DROP TRIGGER {damaged_trigger} "
                        f"ON {damaged_table}"
                    )
                )

            assert not await _public_trigger_exists(
                engine,
                table_name=damaged_table,
                trigger_name=damaged_trigger,
            )

            # Exact DROP TRIGGER must expose the damaged
            # revision instead of silently continuing.
            with pytest.raises(DBAPIError):
                await asyncio.to_thread(
                    command.downgrade,
                    config,
                    DATA_1_3_REVISION,
                )

            # Alembic must not claim that downgrade completed.
            assert (
                await _revision(engine)
                == EXPECTED_REVISION
            )

            # Earlier trigger removals performed inside the
            # failed downgrade transaction must be rolled back.
            assert await _public_trigger_exists(
                engine,
                table_name="raw_market_frames",
                trigger_name=(
                    "data14_raw_market_frames_immutable"
                ),
            )
            assert await _public_trigger_exists(
                engine,
                table_name="raw_market_frames",
                trigger_name=(
                    "data14_raw_market_frames_no_truncate"
                ),
            )

            assert await _public_function_exists(
                engine,
                "data14_reject_mutation",
            )

            assert (
                await _public_table_names(
                    engine,
                    data14_tables,
                )
                == set(data14_tables)
            )

            # Restore a healthy database for following tests.
            await lease.drop_and_recreate_public()

            await asyncio.to_thread(
                command.upgrade,
                config,
                EXPECTED_REVISION,
            )

            assert (
                await _revision(engine)
                == EXPECTED_REVISION
            )
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


@pytest.mark.anyio
async def test_subscription_instrument_set_integrity_is_deferred_and_exact(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    set_table = Base.metadata.tables[
        "provider_subscription_instrument_sets"
    ]
    key_table = Base.metadata.tables[
        "provider_subscription_instrument_set_keys"
    ]

    def digest_for(keys: tuple[str, ...]) -> str:
        return stable_hash(
            {
                "entity": (
                    "provider_subscription_instrument_keys_v1"
                ),
                "provider_contract_keys": tuple(sorted(keys)),
            }
        )

    async def insert_set(
        connection,
        *,
        declared_keys: tuple[str, ...],
        inserted_rows: tuple[tuple[int, str], ...],
        digest_override: str | None = None,
    ) -> None:
        canonical_keys = tuple(sorted(declared_keys))
        digest = digest_override or digest_for(canonical_keys)

        await connection.execute(
            set_table.insert().values(
                instrument_keys_digest=digest,
                instrument_key_count=len(canonical_keys),
                provider_contract_keys=list(canonical_keys),
                canonical_payload_hash=digest,
            )
        )

        await connection.execute(
            key_table.insert(),
            [
                {
                    "instrument_keys_digest": digest,
                    "key_ordinal": ordinal,
                    "provider_contract_key": key,
                }
                for ordinal, key in inserted_rows
            ],
        )

        await connection.execute(
            text("SET CONSTRAINTS ALL IMMEDIATE")
        )

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
                "head",
            )

            valid_keys = (
                "NSE_FO|VALID_A",
                "NSE_FO|VALID_B",
            )
            async with engine.begin() as connection:
                await insert_set(
                    connection,
                    declared_keys=valid_keys,
                    inserted_rows=(
                        (0, valid_keys[0]),
                        (1, valid_keys[1]),
                    ),
                )

            count_mismatch_keys = (
                "NSE_FO|COUNT_A",
                "NSE_FO|COUNT_B",
            )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await insert_set(
                        connection,
                        declared_keys=count_mismatch_keys,
                        inserted_rows=(
                            (0, count_mismatch_keys[0]),
                        ),
                    )

            gap_keys = (
                "NSE_FO|GAP_A",
                "NSE_FO|GAP_B",
            )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await insert_set(
                        connection,
                        declared_keys=gap_keys,
                        inserted_rows=(
                            (0, gap_keys[0]),
                            (2, gap_keys[1]),
                        ),
                    )

            sorted_keys = (
                "NSE_FO|SORT_A",
                "NSE_FO|SORT_B",
            )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await insert_set(
                        connection,
                        declared_keys=sorted_keys,
                        inserted_rows=(
                            (0, sorted_keys[1]),
                            (1, sorted_keys[0]),
                        ),
                    )

            digest_keys = (
                "NSE_FO|DIGEST_A",
                "NSE_FO|DIGEST_B",
            )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await insert_set(
                        connection,
                        declared_keys=digest_keys,
                        inserted_rows=(
                            (0, digest_keys[0]),
                            (1, digest_keys[1]),
                        ),
                        digest_override=(
                            "sha256:" + "f" * 64
                        ),
                    )

            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        key_table.insert().values(
                            instrument_keys_digest=(
                                "sha256:" + "e" * 64
                            ),
                            key_ordinal=0,
                            provider_contract_key=(
                                "NSE_FO|ORPHAN"
                            ),
                        )
                    )
    finally:
        await dispose_database_engine(engine)


def _raw_connection_lifecycle_values(
    *,
    marker: str,
    **overrides,
) -> dict[str, object]:
    occurred_at = RECORDED_AT + timedelta(hours=1)

    values = {
        "raw_event_id": "sha256:" + marker * 64,
        "lifecycle_kind": "connection",
        "provider": "upstox",
        "connection_session_id": "connection-session-1",
        "subscription_scope_id": None,
        "previous_state": None,
        "state": "connecting",
        "source_order_scope_id": "connection-source-scope-1",
        "source_order": 0,
        "occurred_at": occurred_at,
        "available_at": occurred_at,
        "recorded_at": occurred_at,
        "request_mode": None,
        "instrument_keys_digest": None,
        "instrument_key_count": None,
        "redacted_reason_code": None,
        "provider_sequence": None,
        "payload": {
            "fixture": "raw_connection_lifecycle",
        },
    }
    values.update(overrides)
    return values


def _raw_subscription_lifecycle_values(
    *,
    marker: str,
    instrument_keys_digest: str,
    instrument_key_count: int,
    **overrides,
) -> dict[str, object]:
    occurred_at = RECORDED_AT + timedelta(hours=1)

    values = {
        "raw_event_id": "sha256:" + marker * 64,
        "lifecycle_kind": "subscription",
        "provider": "upstox",
        "connection_session_id": "connection-session-1",
        "subscription_scope_id": "subscription-scope-1",
        "previous_state": None,
        "state": "subscribe_requested",
        "source_order_scope_id": "connection-source-scope-1",
        "source_order": 1,
        "occurred_at": occurred_at,
        "available_at": occurred_at,
        "recorded_at": occurred_at,
        "request_mode": "ltpc",
        "instrument_keys_digest": instrument_keys_digest,
        "instrument_key_count": instrument_key_count,
        "redacted_reason_code": None,
        "provider_sequence": None,
        "payload": {
            "fixture": "raw_subscription_lifecycle",
        },
    }
    values.update(overrides)
    return values


async def _insert_subscription_instrument_set(
    connection,
    *,
    prefix: str,
    count: int,
) -> str:
    keys = tuple(
        f"NSE_FO|{prefix}_{index:04d}"
        for index in range(count)
    )
    digest = stable_hash(
        {
            "entity": (
                "provider_subscription_instrument_keys_v1"
            ),
            "provider_contract_keys": keys,
        }
    )

    await connection.execute(
        Base.metadata.tables[
            "provider_subscription_instrument_sets"
        ].insert().values(
            instrument_keys_digest=digest,
            instrument_key_count=count,
            provider_contract_keys=list(keys),
            canonical_payload_hash=digest,
        )
    )

    await connection.execute(
        Base.metadata.tables[
            "provider_subscription_instrument_set_keys"
        ].insert(),
        [
            {
                "instrument_keys_digest": digest,
                "key_ordinal": ordinal,
                "provider_contract_key": key,
            }
            for ordinal, key in enumerate(keys)
        ],
    )

    return digest


@pytest.mark.anyio
async def test_raw_provider_lifecycle_event_checks_and_set_binding(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)
    table = Base.metadata.tables[
        "raw_provider_lifecycle_events"
    ]

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
                "head",
            )

            async with engine.begin() as connection:
                one_key_digest = (
                    await _insert_subscription_instrument_set(
                        connection,
                        prefix="RAW_ONE",
                        count=1,
                    )
                )
                fifty_one_key_digest = (
                    await _insert_subscription_instrument_set(
                        connection,
                        prefix="RAW_FIFTY_ONE",
                        count=51,
                    )
                )

            # Valid typed rows are accepted. Roll them back because
            # ordered batch membership is implemented in the next slice.
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(
                        table.insert(),
                        [
                            _raw_connection_lifecycle_values(
                                marker="1",
                            ),
                            _raw_subscription_lifecycle_values(
                                marker="2",
                                instrument_keys_digest=(
                                    one_key_digest
                                ),
                                instrument_key_count=1,
                            ),
                        ],
                    )

                    stored_count = await connection.scalar(
                        text(
                            "SELECT count(*) "
                            "FROM raw_provider_lifecycle_events"
                        )
                    )
                    assert stored_count == 2
                finally:
                    await transaction.rollback()

            invalid_rows = (
                _raw_connection_lifecycle_values(
                    marker="3",
                    state="connected",
                ),
                _raw_connection_lifecycle_values(
                    marker="4",
                    previous_state="connecting",
                    state="failed",
                    redacted_reason_code=None,
                ),
                _raw_connection_lifecycle_values(
                    marker="5",
                    request_mode="ltpc",
                ),
                _raw_connection_lifecycle_values(
                    marker="6",
                    available_at=RECORDED_AT,
                ),
                _raw_connection_lifecycle_values(
                    marker="7",
                    provider_sequence=1,
                ),
                _raw_connection_lifecycle_values(
                    marker="8",
                    payload=[],
                ),
                _raw_subscription_lifecycle_values(
                    marker="9",
                    instrument_keys_digest=one_key_digest,
                    instrument_key_count=1,
                    request_mode=None,
                ),
                _raw_subscription_lifecycle_values(
                    marker="a",
                    instrument_keys_digest=(
                        fifty_one_key_digest
                    ),
                    instrument_key_count=51,
                    request_mode="full_d30",
                ),
            )

            for invalid in invalid_rows:
                with pytest.raises(
                    IntegrityError,
                    match="check constraint",
                ):
                    async with engine.begin() as connection:
                        await connection.execute(
                            table.insert().values(**invalid)
                        )

            with pytest.raises(
                DBAPIError,
                match="instrument count mismatch",
            ):
                async with engine.begin() as connection:
                    await connection.execute(
                        table.insert().values(
                            **_raw_subscription_lifecycle_values(
                                marker="b",
                                instrument_keys_digest=(
                                    one_key_digest
                                ),
                                instrument_key_count=2,
                            )
                        )
                    )

            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        table.insert().values(
                            **_raw_subscription_lifecycle_values(
                                marker="c",
                                instrument_keys_digest=(
                                    "sha256:" + "f" * 64
                                ),
                                instrument_key_count=1,
                            )
                        )
                    )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_lifecycle_batch_event_order_and_duplicate_integrity(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    batch_table = Base.metadata.tables[
        "provider_lifecycle_batches"
    ]
    raw_table = Base.metadata.tables[
        "raw_provider_lifecycle_events"
    ]
    membership_table = Base.metadata.tables[
        "provider_lifecycle_batch_events"
    ]
    observation_table = Base.metadata.tables[
        "provider_lifecycle_observations"
    ]
    connection_table = Base.metadata.tables[
        "provider_connection_lifecycle_observations"
    ]
    batch_observation_table = Base.metadata.tables[
        "provider_lifecycle_batch_observations"
    ]

    async def insert_batch(
        connection,
        *,
        marker: str,
        memberships: list[dict[str, object]],
        observation_memberships: (
            list[dict[str, object]] | None
        ) = None,
        **batch_overrides,
    ) -> None:
        batch = _lifecycle_batch_values(
            marker=marker,
            **batch_overrides,
        )

        await connection.execute(
            batch_table.insert().values(**batch)
        )

        if memberships:
            await connection.execute(
                membership_table.insert(),
                [
                    {
                        "lifecycle_batch_id": (
                            batch["lifecycle_batch_id"]
                        ),
                        "lifecycle_kind": (
                            batch["lifecycle_kind"]
                        ),
                        **membership,
                    }
                    for membership in memberships
                ],
            )

        if observation_memberships is None:
            observation_memberships = [
                {
                    "event_ordinal": 0,
                    "event_id": observation_one["event_id"],
                },
                {
                    "event_ordinal": 1,
                    "event_id": observation_two["event_id"],
                },
            ][: batch["normalized_count"]]

        if observation_memberships:
            await connection.execute(
                batch_observation_table.insert(),
                [
                    {
                        "lifecycle_batch_id": (
                            batch["lifecycle_batch_id"]
                        ),
                        "lifecycle_kind": (
                            batch["lifecycle_kind"]
                        ),
                        **membership,
                    }
                    for membership in observation_memberships
                ],
            )

        await connection.execute(
            text("SET CONSTRAINTS ALL IMMEDIATE")
        )

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
                "head",
            )

            raw_one = _raw_connection_lifecycle_values(
                marker="1",
                connection_session_id="batch-session-1",
                source_order_scope_id="batch-scope-1",
                source_order=0,
            )
            raw_two = _raw_connection_lifecycle_values(
                marker="2",
                connection_session_id="batch-session-2",
                source_order_scope_id="batch-scope-2",
                source_order=0,
            )

            observation_one = (
                _provider_lifecycle_observation_values(
                    raw_event=raw_one,
                    marker="e",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=raw_one[
                        "connection_session_id"
                    ],
                )
            )
            observation_two = (
                _provider_lifecycle_observation_values(
                    raw_event=raw_two,
                    marker="f",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=raw_two[
                        "connection_session_id"
                    ],
                )
            )

            async with engine.begin() as connection:
                await connection.execute(
                    raw_table.insert(),
                    [raw_one, raw_two],
                )
                await connection.execute(
                    observation_table.insert(),
                    [observation_one, observation_two],
                )
                await connection.execute(
                    connection_table.insert(),
                    [
                        _connection_lifecycle_observation_values(
                            observation=observation_one,
                            raw_event=raw_one,
                        ),
                        _connection_lifecycle_observation_values(
                            observation=observation_two,
                            raw_event=raw_two,
                        ),
                    ],
                )
                await connection.execute(
                    text("SET CONSTRAINTS ALL IMMEDIATE")
                )

            # Insert in reversed physical order. Logical replay remains
            # input_ordinal 0, 1, 2.
            valid_memberships = [
                {
                    "input_ordinal": 2,
                    "raw_event_id": raw_one["raw_event_id"],
                    "is_exact_duplicate": True,
                    "first_occurrence_ordinal": 0,
                },
                {
                    "input_ordinal": 1,
                    "raw_event_id": raw_two["raw_event_id"],
                    "is_exact_duplicate": False,
                    "first_occurrence_ordinal": 1,
                },
                {
                    "input_ordinal": 0,
                    "raw_event_id": raw_one["raw_event_id"],
                    "is_exact_duplicate": False,
                    "first_occurrence_ordinal": 0,
                },
            ]

            async with engine.begin() as connection:
                await insert_batch(
                    connection,
                    marker="3",
                    memberships=valid_memberships,
                )

            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text(
                            "SELECT "
                            "input_ordinal, "
                            "raw_event_id, "
                            "is_exact_duplicate, "
                            "first_occurrence_ordinal "
                            "FROM provider_lifecycle_batch_events "
                            "WHERE lifecycle_batch_id = :batch_id "
                            "ORDER BY input_ordinal"
                        ),
                        {
                            "batch_id": (
                                "sha256:" + "3" * 64
                            )
                        },
                    )
                ).mappings().all()

            assert [
                row["input_ordinal"]
                for row in rows
            ] == [0, 1, 2]

            assert [
                row["is_exact_duplicate"]
                for row in rows
            ] == [False, False, True]

            # Immediate duplicate-shape rejection.
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="4",
                        memberships=[
                            {
                                "input_ordinal": 0,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 0,
                            },
                            {
                                "input_ordinal": 1,
                                "raw_event_id": (
                                    raw_two["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 0,
                            },
                            {
                                "input_ordinal": 2,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": True,
                                "first_occurrence_ordinal": 0,
                            },
                        ],
                    )

            # Deferred count and contiguous-order rejection.
            with pytest.raises(
                DBAPIError,
                match="count mismatch|not contiguous",
            ):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="5",
                        memberships=[
                            {
                                "input_ordinal": 0,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 0,
                            },
                            {
                                "input_ordinal": 2,
                                "raw_event_id": (
                                    raw_two["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 2,
                            },
                        ],
                    )

            # A duplicate must reference the first occurrence of the
            # same raw event.
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="6",
                        memberships=[
                            {
                                "input_ordinal": 0,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 0,
                            },
                            {
                                "input_ordinal": 1,
                                "raw_event_id": (
                                    raw_two["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 1,
                            },
                            {
                                "input_ordinal": 2,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": True,
                                "first_occurrence_ordinal": 1,
                            },
                        ],
                    )

            # Duplicate chains are forbidden: every duplicate points
            # directly to the unique first occurrence.
            with pytest.raises(
                DBAPIError,
                match="first occurrence",
            ):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="7",
                        input_count=3,
                        unique_count=1,
                        normalized_count=1,
                        duplicate_count=2,
                        memberships=[
                            {
                                "input_ordinal": 0,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 0,
                            },
                            {
                                "input_ordinal": 1,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": True,
                                "first_occurrence_ordinal": 0,
                            },
                            {
                                "input_ordinal": 2,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": True,
                                "first_occurrence_ordinal": 1,
                            },
                        ],
                    )

            # Composite batch/raw kind boundaries cannot be crossed.
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="8",
                        input_count=1,
                        unique_count=1,
                        normalized_count=1,
                        duplicate_count=0,
                        memberships=[
                            {
                                "lifecycle_kind": "subscription",
                                "input_ordinal": 0,
                                "raw_event_id": (
                                    raw_one["raw_event_id"]
                                ),
                                "is_exact_duplicate": False,
                                "first_occurrence_ordinal": 0,
                            },
                        ],
                    )
    finally:
        await dispose_database_engine(engine)

def _provider_lifecycle_observation_values(
    *,
    raw_event: dict[str, object],
    marker: str,
    event_type: str,
    subject_id: str,
    **overrides,
) -> dict[str, object]:
    values = {
        "event_id": "sha256:" + marker * 64,
        "raw_event_id": raw_event["raw_event_id"],
        "event_type": event_type,
        "subject_id": subject_id,
        "lifecycle_kind": raw_event["lifecycle_kind"],
        "provider": raw_event["provider"],
        "connection_session_id": (
            raw_event["connection_session_id"]
        ),
        "source_order_scope_id": (
            raw_event["source_order_scope_id"]
        ),
        "source_order": raw_event["source_order"],
        "occurred_at": raw_event["occurred_at"],
        "available_at": raw_event["available_at"],
        "recorded_at": raw_event["recorded_at"],
        "normalization_schema_version": 1,
        "normalizer_implementation_version": (
            "upstox-v3-normalizer-1"
        ),
        "provider_sequence": None,
        "payload": {
            "fixture": "provider_lifecycle_observation",
        },
    }
    values.update(overrides)
    return values


def _connection_lifecycle_observation_values(
    *,
    observation: dict[str, object],
    raw_event: dict[str, object],
    **overrides,
) -> dict[str, object]:
    values = {
        "event_id": observation["event_id"],
        "event_type": observation["event_type"],
        "subject_id": observation["subject_id"],
        "lifecycle_kind": observation["lifecycle_kind"],
        "connection_session_id": (
            observation["connection_session_id"]
        ),
        "previous_state": raw_event["previous_state"],
        "state": raw_event["state"],
        "redacted_reason_code": (
            raw_event["redacted_reason_code"]
        ),
    }
    values.update(overrides)
    return values


def _subscription_lifecycle_observation_values(
    *,
    observation: dict[str, object],
    raw_event: dict[str, object],
    **overrides,
) -> dict[str, object]:
    values = {
        "event_id": observation["event_id"],
        "event_type": observation["event_type"],
        "subject_id": observation["subject_id"],
        "lifecycle_kind": observation["lifecycle_kind"],
        "connection_session_id": (
            observation["connection_session_id"]
        ),
        "subscription_scope_id": (
            raw_event["subscription_scope_id"]
        ),
        "previous_state": raw_event["previous_state"],
        "state": raw_event["state"],
        "request_mode": raw_event["request_mode"],
        "instrument_keys_digest": (
            raw_event["instrument_keys_digest"]
        ),
        "instrument_key_count": (
            raw_event["instrument_key_count"]
        ),
        "redacted_reason_code": (
            raw_event["redacted_reason_code"]
        ),
    }
    values.update(overrides)
    return values


@pytest.mark.anyio
async def test_provider_lifecycle_observation_subtypes_and_set_binding(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    raw_table = Base.metadata.tables[
        "raw_provider_lifecycle_events"
    ]
    observation_table = Base.metadata.tables[
        "provider_lifecycle_observations"
    ]
    connection_table = Base.metadata.tables[
        "provider_connection_lifecycle_observations"
    ]
    subscription_table = Base.metadata.tables[
        "provider_subscription_lifecycle_observations"
    ]

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
                "head",
            )

            async with engine.begin() as connection:
                instrument_keys_digest = (
                    await _insert_subscription_instrument_set(
                        connection,
                        prefix="OBSERVATION_ONE",
                        count=1,
                    )
                )

            raw_connection = (
                _raw_connection_lifecycle_values(
                    marker="1",
                    connection_session_id=(
                        "observation-connection-session"
                    ),
                    source_order_scope_id=(
                        "observation-connection-scope"
                    ),
                    source_order=0,
                )
            )
            raw_subscription = (
                _raw_subscription_lifecycle_values(
                    marker="2",
                    instrument_keys_digest=(
                        instrument_keys_digest
                    ),
                    instrument_key_count=1,
                    connection_session_id=(
                        "observation-connection-session"
                    ),
                    subscription_scope_id=(
                        "observation-subscription-scope"
                    ),
                    source_order_scope_id=(
                        "observation-connection-scope"
                    ),
                    source_order=1,
                )
            )

            subscription_subject_id = stable_hash(
                {
                    "entity": "provider_subscription",
                    "provider": "upstox",
                    "connection_session_id": (
                        raw_subscription[
                            "connection_session_id"
                        ]
                    ),
                    "subscription_scope_id": (
                        raw_subscription[
                            "subscription_scope_id"
                        ]
                    ),
                }
            )

            connection_observation = (
                _provider_lifecycle_observation_values(
                    raw_event=raw_connection,
                    marker="3",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=raw_connection[
                        "connection_session_id"
                    ],
                )
            )
            subscription_observation = (
                _provider_lifecycle_observation_values(
                    raw_event=raw_subscription,
                    marker="4",
                    event_type=(
                        "provider_subscription_"
                        "lifecycle_observation"
                    ),
                    subject_id=subscription_subject_id,
                )
            )

            async with engine.begin() as connection:
                await connection.execute(
                    raw_table.insert(),
                    [
                        raw_connection,
                        raw_subscription,
                    ],
                )
                await connection.execute(
                    observation_table.insert(),
                    [
                        connection_observation,
                        subscription_observation,
                    ],
                )
                await connection.execute(
                    connection_table.insert().values(
                        **_connection_lifecycle_observation_values(
                            observation=connection_observation,
                            raw_event=raw_connection,
                        )
                    )
                )
                await connection.execute(
                    subscription_table.insert().values(
                        **_subscription_lifecycle_observation_values(
                            observation=subscription_observation,
                            raw_event=raw_subscription,
                        )
                    )
                )
                await connection.execute(
                    text("SET CONSTRAINTS ALL IMMEDIATE")
                )

            async with engine.connect() as connection:
                stored_counts = {
                    table_name: await connection.scalar(
                        text(
                            f"SELECT count(*) "
                            f"FROM {table_name}"
                        )
                    )
                    for table_name in (
                        "provider_lifecycle_observations",
                        (
                            "provider_connection_"
                            "lifecycle_observations"
                        ),
                        (
                            "provider_subscription_"
                            "lifecycle_observations"
                        ),
                    )
                }

            assert stored_counts == {
                "provider_lifecycle_observations": 2,
                (
                    "provider_connection_"
                    "lifecycle_observations"
                ): 1,
                (
                    "provider_subscription_"
                    "lifecycle_observations"
                ): 1,
            }

            missing_subtype_raw = (
                _raw_connection_lifecycle_values(
                    marker="5",
                    connection_session_id=(
                        "missing-subtype-session"
                    ),
                    source_order_scope_id=(
                        "missing-subtype-scope"
                    ),
                )
            )
            missing_subtype_observation = (
                _provider_lifecycle_observation_values(
                    raw_event=missing_subtype_raw,
                    marker="6",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=missing_subtype_raw[
                        "connection_session_id"
                    ],
                )
            )

            with pytest.raises(
                DBAPIError,
                match=(
                    "must have exactly one "
                    "connection subtype"
                ),
            ):
                async with engine.begin() as connection:
                    await connection.execute(
                        raw_table.insert().values(
                            **missing_subtype_raw
                        )
                    )
                    await connection.execute(
                        observation_table.insert().values(
                            **missing_subtype_observation
                        )
                    )
                    await connection.execute(
                        text(
                            "SET CONSTRAINTS ALL IMMEDIATE"
                        )
                    )

            invalid_transition_raw = (
                _raw_connection_lifecycle_values(
                    marker="7",
                    connection_session_id=(
                        "invalid-transition-session"
                    ),
                    source_order_scope_id=(
                        "invalid-transition-scope"
                    ),
                )
            )
            invalid_transition_observation = (
                _provider_lifecycle_observation_values(
                    raw_event=invalid_transition_raw,
                    marker="8",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=invalid_transition_raw[
                        "connection_session_id"
                    ],
                )
            )

            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        raw_table.insert().values(
                            **invalid_transition_raw
                        )
                    )
                    await connection.execute(
                        observation_table.insert().values(
                            **invalid_transition_observation
                        )
                    )
                    await connection.execute(
                        connection_table.insert().values(
                            **_connection_lifecycle_observation_values(
                                observation=(
                                    invalid_transition_observation
                                ),
                                raw_event=invalid_transition_raw,
                                state="connected",
                            )
                        )
                    )

            cross_kind_raw = (
                _raw_connection_lifecycle_values(
                    marker="9",
                    connection_session_id=(
                        "cross-kind-session"
                    ),
                    source_order_scope_id=(
                        "cross-kind-scope"
                    ),
                )
            )
            cross_kind_observation = (
                _provider_lifecycle_observation_values(
                    raw_event=cross_kind_raw,
                    marker="a",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=cross_kind_raw[
                        "connection_session_id"
                    ],
                )
            )

            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        raw_table.insert().values(
                            **cross_kind_raw
                        )
                    )
                    await connection.execute(
                        observation_table.insert().values(
                            **cross_kind_observation
                        )
                    )
                    await connection.execute(
                        subscription_table.insert().values(
                            **_subscription_lifecycle_observation_values(
                                observation={
                                    **cross_kind_observation,
                                    "event_type": (
                                        "provider_subscription_"
                                        "lifecycle_observation"
                                    ),
                                    "subject_id": (
                                        "sha256:" + "b" * 64
                                    ),
                                    "lifecycle_kind": (
                                        "subscription"
                                    ),
                                },
                                raw_event={
                                    **cross_kind_raw,
                                    "subscription_scope_id": (
                                        "cross-kind-subscription"
                                    ),
                                    "request_mode": "ltpc",
                                    "instrument_keys_digest": (
                                        instrument_keys_digest
                                    ),
                                    "instrument_key_count": 1,
                                },
                            )
                        )
                    )

            count_mismatch_raw = (
                _raw_subscription_lifecycle_values(
                    marker="c",
                    instrument_keys_digest=(
                        instrument_keys_digest
                    ),
                    instrument_key_count=1,
                    connection_session_id=(
                        "count-mismatch-session"
                    ),
                    subscription_scope_id=(
                        "count-mismatch-subscription"
                    ),
                    source_order_scope_id=(
                        "count-mismatch-scope"
                    ),
                )
            )
            count_mismatch_subject = stable_hash(
                {
                    "entity": "provider_subscription",
                    "provider": "upstox",
                    "connection_session_id": (
                        count_mismatch_raw[
                            "connection_session_id"
                        ]
                    ),
                    "subscription_scope_id": (
                        count_mismatch_raw[
                            "subscription_scope_id"
                        ]
                    ),
                }
            )
            count_mismatch_observation = (
                _provider_lifecycle_observation_values(
                    raw_event=count_mismatch_raw,
                    marker="d",
                    event_type=(
                        "provider_subscription_"
                        "lifecycle_observation"
                    ),
                    subject_id=count_mismatch_subject,
                )
            )

            with pytest.raises(
                DBAPIError,
                match="instrument count mismatch",
            ):
                async with engine.begin() as connection:
                    await connection.execute(
                        raw_table.insert().values(
                            **count_mismatch_raw
                        )
                    )
                    await connection.execute(
                        observation_table.insert().values(
                            **count_mismatch_observation
                        )
                    )
                    await connection.execute(
                        subscription_table.insert().values(
                            **_subscription_lifecycle_observation_values(
                                observation=(
                                    count_mismatch_observation
                                ),
                                raw_event=(
                                    count_mismatch_raw
                                ),
                                instrument_key_count=2,
                            )
                        )
                    )
    finally:
        await dispose_database_engine(engine)



@pytest.mark.anyio
async def test_lifecycle_batch_observation_order_and_membership_integrity(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    batch_table = Base.metadata.tables[
        "provider_lifecycle_batches"
    ]
    raw_table = Base.metadata.tables[
        "raw_provider_lifecycle_events"
    ]
    batch_event_table = Base.metadata.tables[
        "provider_lifecycle_batch_events"
    ]
    observation_table = Base.metadata.tables[
        "provider_lifecycle_observations"
    ]
    connection_table = Base.metadata.tables[
        "provider_connection_lifecycle_observations"
    ]
    batch_observation_table = Base.metadata.tables[
        "provider_lifecycle_batch_observations"
    ]

    async def insert_batch(
        connection,
        *,
        marker: str,
        event_memberships: list[dict[str, object]],
        observation_memberships: list[dict[str, object]],
    ) -> dict[str, object]:
        batch = _lifecycle_batch_values(marker=marker)

        await connection.execute(
            batch_table.insert().values(**batch)
        )
        await connection.execute(
            batch_event_table.insert(),
            [
                {
                    "lifecycle_batch_id": (
                        batch["lifecycle_batch_id"]
                    ),
                    "lifecycle_kind": (
                        batch["lifecycle_kind"]
                    ),
                    **membership,
                }
                for membership in event_memberships
            ],
        )
        await connection.execute(
            batch_observation_table.insert(),
            [
                {
                    "lifecycle_batch_id": (
                        batch["lifecycle_batch_id"]
                    ),
                    "lifecycle_kind": (
                        batch["lifecycle_kind"]
                    ),
                    **membership,
                }
                for membership in observation_memberships
            ],
        )
        await connection.execute(
            text("SET CONSTRAINTS ALL IMMEDIATE")
        )
        return batch

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
                "head",
            )

            raw_one = _raw_connection_lifecycle_values(
                marker="1",
                connection_session_id="batch-observation-session-1",
                source_order_scope_id="batch-observation-scope-1",
                source_order=0,
            )
            raw_two = _raw_connection_lifecycle_values(
                marker="2",
                connection_session_id="batch-observation-session-2",
                source_order_scope_id="batch-observation-scope-2",
                source_order=0,
            )
            raw_outside = _raw_connection_lifecycle_values(
                marker="3",
                connection_session_id="batch-observation-session-3",
                source_order_scope_id="batch-observation-scope-3",
                source_order=0,
            )

            observation_one = _provider_lifecycle_observation_values(
                raw_event=raw_one,
                marker="4",
                event_type=(
                    "provider_connection_lifecycle_observation"
                ),
                subject_id=raw_one["connection_session_id"],
            )
            observation_two = _provider_lifecycle_observation_values(
                raw_event=raw_two,
                marker="5",
                event_type=(
                    "provider_connection_lifecycle_observation"
                ),
                subject_id=raw_two["connection_session_id"],
            )
            observation_outside = (
                _provider_lifecycle_observation_values(
                    raw_event=raw_outside,
                    marker="6",
                    event_type=(
                        "provider_connection_"
                        "lifecycle_observation"
                    ),
                    subject_id=(
                        raw_outside["connection_session_id"]
                    ),
                )
            )

            async with engine.begin() as connection:
                await connection.execute(
                    raw_table.insert(),
                    [
                        raw_one,
                        raw_two,
                        raw_outside,
                    ],
                )
                await connection.execute(
                    observation_table.insert(),
                    [
                        observation_one,
                        observation_two,
                        observation_outside,
                    ],
                )
                await connection.execute(
                    connection_table.insert(),
                    [
                        _connection_lifecycle_observation_values(
                            observation=observation_one,
                            raw_event=raw_one,
                        ),
                        _connection_lifecycle_observation_values(
                            observation=observation_two,
                            raw_event=raw_two,
                        ),
                        _connection_lifecycle_observation_values(
                            observation=observation_outside,
                            raw_event=raw_outside,
                        ),
                    ],
                )
                await connection.execute(
                    text("SET CONSTRAINTS ALL IMMEDIATE")
                )

            valid_event_memberships = [
                {
                    "input_ordinal": 2,
                    "raw_event_id": raw_one["raw_event_id"],
                    "is_exact_duplicate": True,
                    "first_occurrence_ordinal": 0,
                },
                {
                    "input_ordinal": 1,
                    "raw_event_id": raw_two["raw_event_id"],
                    "is_exact_duplicate": False,
                    "first_occurrence_ordinal": 1,
                },
                {
                    "input_ordinal": 0,
                    "raw_event_id": raw_one["raw_event_id"],
                    "is_exact_duplicate": False,
                    "first_occurrence_ordinal": 0,
                },
            ]
            valid_observation_memberships = [
                {
                    "event_ordinal": 1,
                    "event_id": observation_two["event_id"],
                },
                {
                    "event_ordinal": 0,
                    "event_id": observation_one["event_id"],
                },
            ]

            async with engine.begin() as connection:
                valid_batch = await insert_batch(
                    connection,
                    marker="7",
                    event_memberships=valid_event_memberships,
                    observation_memberships=(
                        valid_observation_memberships
                    ),
                )

            async with engine.connect() as connection:
                stored = (
                    await connection.execute(
                        text(
                            "SELECT event_ordinal, event_id "
                            "FROM provider_lifecycle_batch_observations "
                            "WHERE lifecycle_batch_id = :batch_id "
                            "ORDER BY event_ordinal"
                        ),
                        {
                            "batch_id": (
                                valid_batch["lifecycle_batch_id"]
                            )
                        },
                    )
                ).mappings().all()

            assert [
                row["event_ordinal"]
                for row in stored
            ] == [0, 1]
            assert [
                row["event_id"]
                for row in stored
            ] == [
                observation_one["event_id"],
                observation_two["event_id"],
            ]

            with pytest.raises(
                DBAPIError,
                match="observation count mismatch",
            ):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="8",
                        event_memberships=(
                            valid_event_memberships
                        ),
                        observation_memberships=[
                            {
                                "event_ordinal": 0,
                                "event_id": (
                                    observation_one["event_id"]
                                ),
                            },
                        ],
                    )

            with pytest.raises(
                DBAPIError,
                match="normalized order mismatch",
            ):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="9",
                        event_memberships=(
                            valid_event_memberships
                        ),
                        observation_memberships=[
                            {
                                "event_ordinal": 0,
                                "event_id": (
                                    observation_two["event_id"]
                                ),
                            },
                            {
                                "event_ordinal": 1,
                                "event_id": (
                                    observation_one["event_id"]
                                ),
                            },
                        ],
                    )

            with pytest.raises(
                DBAPIError,
                match="normalized order mismatch",
            ):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="a",
                        event_memberships=(
                            valid_event_memberships
                        ),
                        observation_memberships=[
                            {
                                "event_ordinal": 0,
                                "event_id": (
                                    observation_one["event_id"]
                                ),
                            },
                            {
                                "event_ordinal": 1,
                                "event_id": (
                                    observation_outside["event_id"]
                                ),
                            },
                        ],
                    )

            with pytest.raises(
                DBAPIError,
                match="exceeds declared normalized count",
            ):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="b",
                        event_memberships=(
                            valid_event_memberships
                        ),
                        observation_memberships=[
                            {
                                "event_ordinal": 0,
                                "event_id": (
                                    observation_one["event_id"]
                                ),
                            },
                            {
                                "event_ordinal": 2,
                                "event_id": (
                                    observation_two["event_id"]
                                ),
                            },
                        ],
                    )

            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await insert_batch(
                        connection,
                        marker="c",
                        event_memberships=(
                            valid_event_memberships
                        ),
                        observation_memberships=[
                            {
                                "event_ordinal": 0,
                                "event_id": (
                                    observation_one["event_id"]
                                ),
                                "lifecycle_kind": "subscription",
                            },
                            {
                                "event_ordinal": 1,
                                "event_id": (
                                    observation_two["event_id"]
                                ),
                            },
                        ],
                    )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_data14_downgrade_removes_owned_lifecycle_functions(
    postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(postgres_settings)
    config = alembic_config(postgres_url)

    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(DATA_1_4_REVISION)
    assert revision is not None

    owned_function_names = tuple(
        revision.module.DATA14_LIFECYCLE_VALIDATION_FUNCTIONS
    )

    assert set(owned_function_names) == {
        "data14_validate_subscription_instrument_key_ordinal",
        "data14_validate_subscription_instrument_set",
        "data14_validate_raw_lifecycle_instrument_count",
        "data14_validate_lifecycle_batch_event_ordinal",
        "data14_validate_lifecycle_batch_events",
        "data14_validate_provider_lifecycle_observation_subtype",
        "data14_validate_subscription_lifecycle_observation_count",
        "data14_validate_lifecycle_batch_observation_ordinal",
        "data14_validate_lifecycle_batch_observations",
    }

    async def public_owned_functions() -> set[str]:
        async with engine.connect() as connection:
            return set(
                (
                    await connection.execute(
                        text(
                            "SELECT function.proname "
                            "FROM pg_proc AS function "
                            "JOIN pg_namespace AS namespace "
                            "ON namespace.oid = "
                            "function.pronamespace "
                            "WHERE namespace.nspname = 'public' "
                            "AND function.proname = ANY("
                            "CAST(:names AS text[]))"
                        ),
                        {
                            "names": list(
                                owned_function_names
                            )
                        },
                    )
                ).scalars()
            )

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
                EXPECTED_REVISION,
            )

            assert await public_owned_functions() == set(
                owned_function_names
            )

            await asyncio.to_thread(
                command.downgrade,
                config,
                DATA_1_3_REVISION,
            )

            assert await public_owned_functions() == set()
            assert await _revision(engine) == DATA_1_3_REVISION

            await asyncio.to_thread(
                command.upgrade,
                config,
                EXPECTED_REVISION,
            )

            assert await public_owned_functions() == set(
                owned_function_names
            )
            assert await _revision(engine) == EXPECTED_REVISION

            await asyncio.to_thread(
                command.check,
                config,
            )
    finally:
        await dispose_database_engine(engine)