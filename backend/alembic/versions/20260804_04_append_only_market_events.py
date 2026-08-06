from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260804_04"
down_revision = "20260804_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ID = 71

TABLES = (
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


def _non_empty_data14_tables() -> tuple[str, ...]:
    connection = op.get_bind()
    non_empty: list[str] = []

    for table_name in sorted(TABLES):
        has_rows = connection.execute(
            sa.text(
                f"SELECT EXISTS ("
                f"SELECT 1 FROM {table_name} LIMIT 1"
                f")"
            )
        ).scalar_one()

        if has_rows:
            non_empty.append(table_name)

    return tuple(non_empty)


def _create_raw_market_frames() -> None:
    op.create_table(
        "raw_market_frames",
        sa.Column("raw_event_id", sa.String(ID), primary_key=True),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("provider_schema_id", sa.String(512), nullable=False),
        sa.Column("provider_schema_sha256", sa.String(64), nullable=False),
        sa.Column("connection_session_id", sa.String(512), nullable=False),
        sa.Column("source_order_scope_id", sa.String(512), nullable=False),
        sa.Column("source_order", sa.BigInteger(), nullable=False),
        sa.Column("frame_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("frame_content_hash", sa.String(ID), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("capture_basis", sa.String(64), nullable=False),
        sa.Column("source_file_id", sa.String(512), nullable=True),
        sa.Column("source_record_id", sa.String(512), nullable=True),
        sa.Column(
            "persistence_recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="raw_market_frames_id_sha256",
        ),
        sa.CheckConstraint(
            "provider = 'upstox'",
            name="raw_market_frames_provider",
        ),
        sa.CheckConstraint(
            "octet_length(provider_schema_id) BETWEEN 1 AND 512",
            name="raw_market_frames_schema_id_bytes",
        ),
        sa.CheckConstraint(
            "provider_schema_sha256 ~ '^[0-9a-f]{64}$'",
            name="raw_market_frames_schema_sha256",
        ),
        sa.CheckConstraint(
            "octet_length(connection_session_id) BETWEEN 1 AND 512",
            name="raw_market_frames_connection_bytes",
        ),
        sa.CheckConstraint(
            "octet_length(source_order_scope_id) BETWEEN 1 AND 512",
            name="raw_market_frames_scope_bytes",
        ),
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 9223372036854775807",
            name="raw_market_frames_source_order",
        ),
        sa.CheckConstraint(
            "octet_length(frame_bytes) BETWEEN 1 AND 16777216",
            name="raw_market_frames_frame_bytes",
        ),
        sa.CheckConstraint(
            "frame_content_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="raw_market_frames_content_sha256",
        ),
        sa.CheckConstraint(
            "received_at IS NULL OR "
            "(received_at <> 'infinity'::timestamptz "
            "AND received_at <> '-infinity'::timestamptz)",
            name="raw_market_frames_received_finite",
        ),
        sa.CheckConstraint(
            "available_at <> 'infinity'::timestamptz "
            "AND available_at <> '-infinity'::timestamptz",
            name="raw_market_frames_available_finite",
        ),
        sa.CheckConstraint(
            "recorded_at <> 'infinity'::timestamptz "
            "AND recorded_at <> '-infinity'::timestamptz",
            name="raw_market_frames_recorded_finite",
        ),
        sa.CheckConstraint(
            "persistence_recorded_at <> 'infinity'::timestamptz "
            "AND persistence_recorded_at <> '-infinity'::timestamptz",
            name="raw_market_frames_persistence_finite",
        ),
        sa.CheckConstraint(
            "recorded_at >= available_at",
            name="raw_market_frames_recorded_after_available",
        ),
        sa.CheckConstraint(
            "received_at IS NULL OR available_at >= received_at",
            name="raw_market_frames_available_after_received",
        ),
        sa.CheckConstraint(
            "capture_basis IN "
            "('live_received', "
            "'recorded_with_original_receipt', "
            "'historical_import')",
            name="raw_market_frames_capture_basis",
        ),
        sa.CheckConstraint(
            "("
            "capture_basis IN "
            "('live_received', 'recorded_with_original_receipt') "
            "AND received_at IS NOT NULL "
            "AND available_at = received_at"
            ") OR ("
            "capture_basis = 'historical_import' "
            "AND received_at IS NULL"
            ")",
            name="raw_market_frames_capture_clock_shape",
        ),
        sa.CheckConstraint(
            "(source_file_id IS NULL) = (source_record_id IS NULL)",
            name="raw_market_frames_source_pair",
        ),
        sa.CheckConstraint(
            "source_file_id IS NULL OR "
            "octet_length(source_file_id) BETWEEN 1 AND 512",
            name="raw_market_frames_source_file_bytes",
        ),
        sa.CheckConstraint(
            "source_record_id IS NULL OR "
            "octet_length(source_record_id) BETWEEN 1 AND 512",
            name="raw_market_frames_source_record_bytes",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_schema_id",
            "connection_session_id",
            "source_order_scope_id",
            "source_order",
            name="uq_raw_market_frames_capture_identity",
        ),
    )

    op.create_index(
        "ix_raw_market_frames_capture_order",
        "raw_market_frames",
        (
            "provider",
            "connection_session_id",
            "source_order_scope_id",
            "source_order",
            "raw_event_id",
        ),
    )
    op.create_index(
        "ix_raw_market_frames_content_hash",
        "raw_market_frames",
        ("frame_content_hash",),
    )
    op.create_index(
        "ix_raw_market_frames_persistence_order",
        "raw_market_frames",
        (
            "persistence_recorded_at",
            "raw_event_id",
        ),
    )


def _create_market_normalization_results() -> None:
    op.create_table(
        "market_normalization_results",
        sa.Column("result_id", sa.String(ID), primary_key=True),
        sa.Column(
            "raw_event_id",
            sa.String(ID),
            sa.ForeignKey(
                "raw_market_frames.raw_event_id",
                ondelete="NO ACTION",
            ),
            nullable=False,
        ),
        sa.Column(
            "normalization_schema_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "normalizer_implementation_version",
            sa.String(128),
            nullable=False,
        ),
        sa.Column("response_type", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decoded_entry_count", sa.Integer(), nullable=False),
        sa.Column("accepted_entry_count", sa.Integer(), nullable=False),
        sa.Column("failed_entry_count", sa.Integer(), nullable=False),
        sa.Column("frame_failure_present", sa.Boolean(), nullable=False),
        sa.Column(
            "unadopted_schema_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "present_unadopted_message_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "secondary_payload_paths_present",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column("full_result_hash", sa.String(ID), nullable=False),
        sa.Column("adopted_semantics_hash", sa.String(ID), nullable=False),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "persistence_recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_normalization_results_id_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_normalization_results_raw_sha256",
        ),
        sa.CheckConstraint(
            "normalization_schema_version = 1 "
            "AND normalizer_implementation_version = "
            "'upstox-v3-normalizer-1'",
            name="market_normalization_results_schema_label",
        ),
        sa.CheckConstraint(
            "response_type IS NULL OR "
            "response_type IN "
            "('initial_feed', 'live_feed', 'market_info')",
            name="market_normalization_results_response_type",
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'partial', 'failed')",
            name="market_normalization_results_status",
        ),
        sa.CheckConstraint(
            "decoded_entry_count BETWEEN 0 AND 5000 "
            "AND accepted_entry_count BETWEEN 0 AND 5000 "
            "AND failed_entry_count BETWEEN 0 AND 5000",
            name="market_normalization_results_count_bounds",
        ),
        sa.CheckConstraint(
            "("
            "frame_failure_present "
            "AND status = 'failed' "
            "AND accepted_entry_count = 0 "
            "AND failed_entry_count = 0"
            ") OR ("
            "NOT frame_failure_present "
            "AND decoded_entry_count = "
            "accepted_entry_count + failed_entry_count "
            "AND ("
            "(status = 'complete' "
            "AND accepted_entry_count > 0 "
            "AND failed_entry_count = 0) "
            "OR "
            "(status = 'partial' "
            "AND accepted_entry_count > 0 "
            "AND failed_entry_count > 0) "
            "OR "
            "(status = 'failed' "
            "AND accepted_entry_count = 0)"
            ")"
            ")",
            name="market_normalization_results_status_shape",
        ),
        sa.CheckConstraint(
            "array_position(unadopted_schema_paths, NULL) IS NULL",
            name="market_normalization_results_unadopted_no_null",
        ),
        sa.CheckConstraint(
            "array_position("
            "present_unadopted_message_paths, NULL"
            ") IS NULL",
            name="market_normalization_results_present_no_null",
        ),
        sa.CheckConstraint(
            "array_position("
            "secondary_payload_paths_present, NULL"
            ") IS NULL",
            name="market_normalization_results_secondary_no_null",
        ),
        sa.CheckConstraint(
            "full_result_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="market_normalization_results_full_sha256",
        ),
        sa.CheckConstraint(
            "adopted_semantics_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="market_normalization_results_adopted_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata_payload) = 'object'",
            name="market_normalization_results_metadata_object",
        ),
        sa.CheckConstraint(
            "persistence_recorded_at "
            "<> 'infinity'::timestamptz "
            "AND persistence_recorded_at "
            "<> '-infinity'::timestamptz",
            name="market_normalization_results_persistence_finite",
        ),
        sa.UniqueConstraint(
            "raw_event_id",
            "normalization_schema_version",
            name="uq_market_normalization_results_raw_schema",
        ),
        sa.UniqueConstraint(
            "result_id",
            "raw_event_id",
            name="uq_market_normalization_results_result_raw",
        ),
    )

    op.create_index(
        "ix_market_normalization_results_schema_raw",
        "market_normalization_results",
        (
            "normalization_schema_version",
            "raw_event_id",
        ),
    )
    op.create_index(
        "ix_market_normalization_results_persistence",
        "market_normalization_results",
        (
            "normalization_schema_version",
            "persistence_recorded_at",
            "result_id",
        ),
    )
    op.create_index(
        "ix_market_normalization_results_status",
        "market_normalization_results",
        (
            "normalization_schema_version",
            "status",
            "result_id",
        ),
    )


def _create_temporal_provenance_targets() -> None:
    op.create_unique_constraint(
        "uq_provider_mapping_records_record_semantic",
        "provider_mapping_records",
        ("record_id", "mapping_id"),
    )
    op.create_unique_constraint(
        "uq_instrument_version_records_record_semantic",
        "instrument_version_records",
        ("record_id", "version_id"),
    )
    op.create_unique_constraint(
        "uq_catalogue_version_records_record_semantic",
        "catalogue_version_records",
        ("record_id", "catalogue_version_id"),
    )


def _create_market_observations() -> None:
    op.create_table(
        "market_observations",
        sa.Column("event_id", sa.String(ID), primary_key=True),
        sa.Column(
            "raw_event_id",
            sa.String(ID),
            sa.ForeignKey(
                "raw_market_frames.raw_event_id",
                ondelete="NO ACTION",
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(ID), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column(
            "provider_contract_key",
            sa.String(512),
            nullable=True,
        ),
        sa.Column(
            "economic_subject_id",
            sa.String(ID),
            sa.ForeignKey(
                "market_instruments.instrument_id",
                ondelete="NO ACTION",
            ),
            nullable=True,
        ),
        sa.Column(
            "provider_mapping_id",
            sa.String(ID),
            sa.ForeignKey(
                "provider_contract_mappings.mapping_id",
                ondelete="NO ACTION",
            ),
            nullable=True,
        ),
        sa.Column(
            "contract_version_id",
            sa.String(ID),
            sa.ForeignKey(
                "instrument_versions.version_id",
                ondelete="NO ACTION",
            ),
            nullable=True,
        ),
        sa.Column(
            "catalogue_version_id",
            sa.String(ID),
            sa.ForeignKey(
                "catalogue_versions.catalogue_version_id",
                ondelete="NO ACTION",
            ),
            nullable=True,
        ),
        sa.Column(
            "provider_mapping_record_id",
            sa.String(ID),
            nullable=True,
        ),
        sa.Column(
            "contract_version_record_id",
            sa.String(ID),
            nullable=True,
        ),
        sa.Column(
            "catalogue_version_record_id",
            sa.String(ID),
            nullable=True,
        ),
        sa.Column(
            "resolution_market_as_of",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resolution_known_as_of",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "provider_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "exchange_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "availability_basis",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "source_order_scope_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "source_order",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "normalization_schema_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "normalizer_implementation_version",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "provider_sequence",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "supersedes_event_id",
            sa.String(ID),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            [
                "provider_mapping_record_id",
                "provider_mapping_id",
            ],
            [
                "provider_mapping_records.record_id",
                "provider_mapping_records.mapping_id",
            ],
            ondelete="NO ACTION",
            name=(
                "fk_market_observations_"
                "mapping_record_semantic"
            ),
        ),
        sa.ForeignKeyConstraint(
            [
                "contract_version_record_id",
                "contract_version_id",
            ],
            [
                "instrument_version_records.record_id",
                "instrument_version_records.version_id",
            ],
            ondelete="NO ACTION",
            name=(
                "fk_market_observations_"
                "contract_record_semantic"
            ),
        ),
        sa.ForeignKeyConstraint(
            [
                "catalogue_version_record_id",
                "catalogue_version_id",
            ],
            [
                "catalogue_version_records.record_id",
                "catalogue_version_records.catalogue_version_id",
            ],
            ondelete="NO ACTION",
            name=(
                "fk_market_observations_"
                "catalogue_record_semantic"
            ),
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_event_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_raw_sha256",
        ),
        sa.CheckConstraint(
            "subject_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_subject_sha256",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'underlying_quote_observation', "
            "'futures_quote_observation', "
            "'option_quote_observation', "
            "'market_segment_status_observation'"
            ")",
            name="market_observations_event_type",
        ),
        sa.CheckConstraint(
            "provider = 'upstox'",
            name="market_observations_provider",
        ),
        sa.CheckConstraint(
            "provider_contract_key IS NULL OR ("
            "octet_length(provider_contract_key) BETWEEN 1 AND 512 "
            "AND provider_contract_key = btrim(provider_contract_key) "
            "AND provider_contract_key !~ '[[:cntrl:]]'"
            ")",
            name="market_observations_provider_key_shape",
        ),
        sa.CheckConstraint(
            "economic_subject_id IS NULL OR "
            "economic_subject_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_economic_subject_sha256",
        ),
        sa.CheckConstraint(
            "provider_mapping_id IS NULL OR "
            "provider_mapping_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_mapping_sha256",
        ),
        sa.CheckConstraint(
            "contract_version_id IS NULL OR "
            "contract_version_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_contract_version_sha256",
        ),
        sa.CheckConstraint(
            "catalogue_version_id IS NULL OR "
            "catalogue_version_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_catalogue_sha256",
        ),
        sa.CheckConstraint(
            "provider_mapping_record_id IS NULL OR "
            "provider_mapping_record_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_mapping_record_sha256",
        ),
        sa.CheckConstraint(
            "contract_version_record_id IS NULL OR "
            "contract_version_record_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_contract_record_sha256",
        ),
        sa.CheckConstraint(
            "catalogue_version_record_id IS NULL OR "
            "catalogue_version_record_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_observations_catalogue_record_sha256",
        ),
        sa.CheckConstraint(
            "("
            "provider_mapping_record_id IS NULL "
            "AND contract_version_record_id IS NULL "
            "AND catalogue_version_record_id IS NULL"
            ") OR ("
            "provider_mapping_record_id IS NOT NULL "
            "AND contract_version_record_id IS NOT NULL "
            "AND catalogue_version_record_id IS NOT NULL"
            ")",
            name="market_observations_temporal_record_trio",
        ),
        sa.CheckConstraint(
            "provider_timestamp <> 'infinity'::timestamptz "
            "AND provider_timestamp <> '-infinity'::timestamptz",
            name="market_observations_provider_timestamp_finite",
        ),
        sa.CheckConstraint(
            "exchange_timestamp IS NULL",
            name="market_observations_exchange_timestamp_absent",
        ),
        sa.CheckConstraint(
            "received_at IS NULL OR "
            "(received_at <> 'infinity'::timestamptz "
            "AND received_at <> '-infinity'::timestamptz)",
            name="market_observations_received_finite",
        ),
        sa.CheckConstraint(
            "available_at <> 'infinity'::timestamptz "
            "AND available_at <> '-infinity'::timestamptz",
            name="market_observations_available_finite",
        ),
        sa.CheckConstraint(
            "recorded_at <> 'infinity'::timestamptz "
            "AND recorded_at <> '-infinity'::timestamptz",
            name="market_observations_recorded_finite",
        ),
        sa.CheckConstraint(
            "resolution_market_as_of IS NULL OR "
            "(resolution_market_as_of <> 'infinity'::timestamptz "
            "AND resolution_market_as_of <> '-infinity'::timestamptz)",
            name="market_observations_resolution_market_finite",
        ),
        sa.CheckConstraint(
            "resolution_known_as_of IS NULL OR "
            "(resolution_known_as_of <> 'infinity'::timestamptz "
            "AND resolution_known_as_of <> '-infinity'::timestamptz)",
            name="market_observations_resolution_known_finite",
        ),
        sa.CheckConstraint(
            "recorded_at >= available_at",
            name="market_observations_recorded_after_available",
        ),
        sa.CheckConstraint(
            "received_at IS NULL OR available_at >= received_at",
            name="market_observations_available_after_received",
        ),
        sa.CheckConstraint(
            "("
            "availability_basis = 'received' "
            "AND received_at IS NOT NULL "
            "AND available_at = received_at"
            ") OR ("
            "availability_basis = 'historical_import' "
            "AND received_at IS NULL"
            ")",
            name="market_observations_availability_shape",
        ),
        sa.CheckConstraint(
            "octet_length(source_order_scope_id) BETWEEN 1 AND 512",
            name="market_observations_source_scope_bytes",
        ),
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 9223372036854775807",
            name="market_observations_source_order",
        ),
        sa.CheckConstraint(
            "normalization_schema_version = 1 "
            "AND normalizer_implementation_version = "
            "'upstox-v3-normalizer-1'",
            name="market_observations_schema_label",
        ),
        sa.CheckConstraint(
            "provider_sequence IS NULL",
            name="market_observations_provider_sequence_absent",
        ),
        sa.CheckConstraint(
            "supersedes_event_id IS NULL",
            name="market_observations_corrections_deferred",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="market_observations_payload_object",
        ),
        sa.CheckConstraint(
            "("
            "event_type IN ("
            "'underlying_quote_observation', "
            "'futures_quote_observation', "
            "'option_quote_observation'"
            ") "
            "AND provider_contract_key IS NOT NULL "
            "AND economic_subject_id IS NOT NULL "
            "AND provider_mapping_id IS NOT NULL "
            "AND contract_version_id IS NOT NULL "
            "AND catalogue_version_id IS NOT NULL "
            "AND provider_mapping_record_id IS NOT NULL "
            "AND contract_version_record_id IS NOT NULL "
            "AND catalogue_version_record_id IS NOT NULL "
            "AND resolution_market_as_of IS NOT NULL "
            "AND resolution_known_as_of IS NOT NULL "
            "AND subject_id = economic_subject_id"
            ") OR ("
            "event_type = 'market_segment_status_observation' "
            "AND provider_contract_key IS NULL "
            "AND economic_subject_id IS NULL "
            "AND provider_mapping_id IS NULL "
            "AND contract_version_id IS NULL "
            "AND catalogue_version_id IS NULL "
            "AND provider_mapping_record_id IS NULL "
            "AND contract_version_record_id IS NULL "
            "AND catalogue_version_record_id IS NULL "
            "AND resolution_market_as_of IS NULL "
            "AND resolution_known_as_of IS NULL"
            ")",
            name="market_observations_provenance_shape",
        ),
        sa.UniqueConstraint(
            "event_id",
            "raw_event_id",
            name="uq_market_observations_event_raw",
        ),
        sa.UniqueConstraint(
            "event_id",
            "event_type",
            "subject_id",
            name="uq_market_observations_event_type_subject",
        ),
    )

    op.create_index(
        "ix_market_observations_subject_provider_time",
        "market_observations",
        (
            "normalization_schema_version",
            "economic_subject_id",
            "event_type",
            "provider_timestamp",
            "available_at",
            "event_id",
        ),
    )
    op.create_index(
        "ix_market_observations_subject_availability",
        "market_observations",
        (
            "normalization_schema_version",
            "economic_subject_id",
            "availability_basis",
            "available_at",
            "event_id",
        ),
    )
    op.create_index(
        "ix_market_observations_raw",
        "market_observations",
        (
            "raw_event_id",
            "event_id",
        ),
    )
    op.create_index(
        "ix_market_observations_mapping_provenance",
        "market_observations",
        (
            "provider_mapping_id",
            "contract_version_id",
            "catalogue_version_id",
            "event_id",
        ),
    )
    op.create_index(
        "ix_market_observations_temporal_provenance",
        "market_observations",
        (
            "provider_mapping_record_id",
            "contract_version_record_id",
            "catalogue_version_record_id",
            "event_id",
        ),
    )


def _create_market_normalization_result_events() -> None:
    op.create_table(
        "market_normalization_result_events",
        sa.Column("result_id", sa.String(ID), nullable=False),
        sa.Column("raw_event_id", sa.String(ID), nullable=False),
        sa.Column("event_ordinal", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(ID), nullable=False),
        sa.PrimaryKeyConstraint(
            "result_id",
            "event_ordinal",
            name="pk_market_normalization_result_events",
        ),
        sa.UniqueConstraint(
            "result_id",
            "event_id",
            name="uq_market_normalization_result_events_event",
        ),
        sa.ForeignKeyConstraint(
            ["result_id", "raw_event_id"],
            [
                "market_normalization_results.result_id",
                "market_normalization_results.raw_event_id",
            ],
            ondelete="NO ACTION",
            name="fk_market_result_events_result_raw",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "raw_event_id"],
            [
                "market_observations.event_id",
                "market_observations.raw_event_id",
            ],
            ondelete="NO ACTION",
            name="fk_market_result_events_event_raw",
        ),
        sa.CheckConstraint(
            "result_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_result_events_result_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_result_events_raw_sha256",
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_result_events_event_sha256",
        ),
        sa.CheckConstraint(
            "event_ordinal BETWEEN 0 AND 4999",
            name="market_result_events_ordinal",
        ),
    )

    op.create_index(
        "ix_market_normalization_result_events_event",
        "market_normalization_result_events",
        (
            "event_id",
            "result_id",
        ),
    )


def _create_market_normalization_failures() -> None:
    op.create_table(
        "market_normalization_failures",
        sa.Column("failure_id", sa.String(ID), primary_key=True),
        sa.Column("result_id", sa.String(ID), nullable=False),
        sa.Column("raw_event_id", sa.String(ID), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column(
            "provider_contract_key",
            sa.String(512),
            nullable=True,
        ),
        sa.Column("segment", sa.String(128), nullable=True),
        sa.Column("safe_detail_code", sa.String(128), nullable=True),
        sa.Column("selected_feed_union", sa.String(64), nullable=True),
        sa.Column(
            "provider_depth_levels_present",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "field_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "unadopted_schema_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "present_unadopted_message_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["result_id", "raw_event_id"],
            [
                "market_normalization_results.result_id",
                "market_normalization_results.raw_event_id",
            ],
            ondelete="NO ACTION",
            name="fk_market_failures_result_raw",
        ),
        sa.UniqueConstraint(
            "failure_id",
            "result_id",
            "raw_event_id",
            name="uq_market_failures_failure_result_raw",
        ),
        sa.CheckConstraint(
            "failure_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_failures_failure_sha256",
        ),
        sa.CheckConstraint(
            "result_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_failures_result_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_failures_raw_sha256",
        ),
        sa.CheckConstraint(
            "scope IN ('frame', 'subject', 'segment')",
            name="market_failures_scope",
        ),
        sa.CheckConstraint(
            "octet_length(reason_code) BETWEEN 1 AND 128 "
            "AND reason_code ~ '^[A-Za-z0-9_]+$'",
            name="market_failures_reason_shape",
        ),
        sa.CheckConstraint(
            "safe_detail_code IS NULL OR ("
            "octet_length(safe_detail_code) BETWEEN 1 AND 128 "
            "AND safe_detail_code ~ '^[A-Za-z0-9_]+$'"
            ")",
            name="market_failures_safe_detail_shape",
        ),
        sa.CheckConstraint(
            "provider_contract_key IS NULL OR ("
            "octet_length(provider_contract_key) BETWEEN 1 AND 512 "
            "AND provider_contract_key = btrim(provider_contract_key) "
            "AND provider_contract_key !~ '[[:cntrl:]]'"
            ")",
            name="market_failures_provider_key_shape",
        ),
        sa.CheckConstraint(
            "segment IS NULL OR ("
            "octet_length(segment) BETWEEN 1 AND 128 "
            "AND segment = btrim(segment) "
            "AND segment !~ '[[:cntrl:]]'"
            ")",
            name="market_failures_segment_shape",
        ),
        sa.CheckConstraint(
            "("
            "scope = 'frame' "
            "AND provider_contract_key IS NULL "
            "AND segment IS NULL"
            ") OR ("
            "scope = 'subject' "
            "AND provider_contract_key IS NOT NULL "
            "AND segment IS NULL"
            ") OR ("
            "scope = 'segment' "
            "AND provider_contract_key IS NULL "
            "AND segment IS NOT NULL"
            ")",
            name="market_failures_scope_shape",
        ),
        sa.CheckConstraint(
            "selected_feed_union IS NULL OR "
            "selected_feed_union IN "
            "('ltpc', 'indexFF', 'marketFF', 'firstLevelWithGreeks')",
            name="market_failures_selected_union",
        ),
        sa.CheckConstraint(
            "provider_depth_levels_present IS NULL OR "
            "provider_depth_levels_present BETWEEN 0 AND 30",
            name="market_failures_depth",
        ),
        sa.CheckConstraint(
            "array_position(field_paths, NULL) IS NULL "
            "AND cardinality(field_paths) <= 5000",
            name="market_failures_field_paths",
        ),
        sa.CheckConstraint(
            "array_position(unadopted_schema_paths, NULL) IS NULL "
            "AND cardinality(unadopted_schema_paths) <= 5000",
            name="market_failures_unadopted_paths",
        ),
        sa.CheckConstraint(
            "array_position("
            "present_unadopted_message_paths, NULL"
            ") IS NULL "
            "AND cardinality(present_unadopted_message_paths) <= 5000",
            name="market_failures_present_paths",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="market_failures_payload_object",
        ),
    )

    op.create_index(
        "ix_market_normalization_failures_result_scope",
        "market_normalization_failures",
        (
            "result_id",
            "scope",
            "failure_id",
        ),
    )
    op.create_index(
        "ix_market_normalization_failures_reason",
        "market_normalization_failures",
        (
            "reason_code",
            "failure_id",
        ),
    )


def _create_market_normalization_result_failures() -> None:
    op.create_table(
        "market_normalization_result_failures",
        sa.Column("result_id", sa.String(ID), nullable=False),
        sa.Column("raw_event_id", sa.String(ID), nullable=False),
        sa.Column("failure_role", sa.String(16), nullable=False),
        sa.Column("failure_ordinal", sa.Integer(), nullable=False),
        sa.Column("failure_id", sa.String(ID), nullable=False),
        sa.PrimaryKeyConstraint(
            "result_id",
            "failure_role",
            "failure_ordinal",
            name="pk_market_normalization_result_failures",
        ),
        sa.UniqueConstraint(
            "result_id",
            "raw_event_id",
            "failure_role",
            "failure_ordinal",
            name="uq_market_result_failures_result_raw_role_ordinal",
        ),
        sa.ForeignKeyConstraint(
            ["result_id", "raw_event_id"],
            [
                "market_normalization_results.result_id",
                "market_normalization_results.raw_event_id",
            ],
            ondelete="NO ACTION",
            name="fk_market_result_failures_result_raw",
        ),
        sa.ForeignKeyConstraint(
            ["failure_id", "result_id", "raw_event_id"],
            [
                "market_normalization_failures.failure_id",
                "market_normalization_failures.result_id",
                "market_normalization_failures.raw_event_id",
            ],
            ondelete="NO ACTION",
            name="fk_market_result_failures_failure_result_raw",
        ),
        sa.CheckConstraint(
            "result_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_result_failures_result_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_result_failures_raw_sha256",
        ),
        sa.CheckConstraint(
            "failure_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_result_failures_failure_sha256",
        ),
        sa.CheckConstraint(
            "failure_role IN ('frame', 'entry')",
            name="market_result_failures_role",
        ),
        sa.CheckConstraint(
            "failure_ordinal BETWEEN 0 AND 4999",
            name="market_result_failures_ordinal",
        ),
    )

    op.create_index(
        "uq_market_normalization_result_failures_one_frame",
        "market_normalization_result_failures",
        ("result_id",),
        unique=True,
        postgresql_where=sa.text("failure_role = 'frame'"),
    )
    op.create_index(
        "ix_market_normalization_result_failures_failure",
        "market_normalization_result_failures",
        (
            "failure_id",
            "result_id",
        ),
    )


QUOTE_PRICE_COLUMNS = (
    "bid_price",
    "ask_price",
    "last_price",
    "previous_close_price",
)

QUOTE_QUANTITY_COLUMNS = (
    "bid_size",
    "ask_size",
    "last_size",
    "reported_volume",
)


def _create_quote_observation_table(
    table_name: str,
    event_type: str,
    feed_shape: str,
) -> None:
    finite_nonnegative_prices = " AND ".join(
        f"({column} IS NULL OR ("
        f"{column} >= 0 AND "
        f"{column}::text NOT IN "
        f"('NaN', 'Infinity', '-Infinity')"
        f"))"
        for column in QUOTE_PRICE_COLUMNS
    )
    quantity_bounds = " AND ".join(
        f"({column} IS NULL OR "
        f"{column} BETWEEN 0 AND 9223372036854775807)"
        for column in QUOTE_QUANTITY_COLUMNS
    )

    op.create_table(
        table_name,
        sa.Column("event_id", sa.String(ID), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(ID), nullable=False),
        sa.Column("feed_response_type", sa.String(32), nullable=False),
        sa.Column("request_mode", sa.String(32), nullable=False),
        sa.Column("feed_union", sa.String(64), nullable=False),
        sa.Column("is_snapshot", sa.Boolean(), nullable=False),
        sa.Column("presence_semantics", sa.String(64), nullable=False),
        sa.Column("numeric_basis", sa.String(64), nullable=False),
        sa.Column("quantity_basis", sa.String(64), nullable=False),
        sa.Column("bid_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("bid_size", sa.BigInteger(), nullable=True),
        sa.Column("ask_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("ask_size", sa.BigInteger(), nullable=True),
        sa.Column("last_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("last_size", sa.BigInteger(), nullable=True),
        sa.Column(
            "last_trade_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "previous_close_price",
            sa.Numeric(38, 18),
            nullable=True,
        ),
        sa.Column("reported_volume", sa.BigInteger(), nullable=True),
        sa.Column("open_interest", sa.BigInteger(), nullable=True),
        sa.Column(
            "provider_depth_levels_present",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "normalized_depth_levels",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "unadopted_depth_level_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "unadopted_schema_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "present_unadopted_message_paths",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.Column(
            "secondary_payload_paths_present",
            postgresql.ARRAY(sa.String(512)),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "event_type", "subject_id"],
            [
                "market_observations.event_id",
                "market_observations.event_type",
                "market_observations.subject_id",
            ],
            ondelete="NO ACTION",
            name=f"fk_{table_name}_event_type_subject",
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name=f"{table_name}_event_sha256",
        ),
        sa.CheckConstraint(
            "subject_id ~ '^sha256:[0-9a-f]{64}$'",
            name=f"{table_name}_subject_sha256",
        ),
        sa.CheckConstraint(
            f"event_type = '{event_type}'",
            name=f"{table_name}_event_type",
        ),
        sa.CheckConstraint(
            "feed_response_type IN ('initial_feed', 'live_feed')",
            name=f"{table_name}_response_type",
        ),
        sa.CheckConstraint(
            "request_mode IN "
            "('ltpc', 'full_d5', 'option_greeks', 'full_d30')",
            name=f"{table_name}_request_mode",
        ),
        sa.CheckConstraint(
            "feed_union IN "
            "('ltpc', 'indexFF', 'marketFF', "
            "'firstLevelWithGreeks')",
            name=f"{table_name}_feed_union",
        ),
        sa.CheckConstraint(
            "(feed_response_type = 'initial_feed' AND is_snapshot) "
            "OR (feed_response_type = 'live_feed' AND NOT is_snapshot)",
            name=f"{table_name}_snapshot_shape",
        ),
        sa.CheckConstraint(
            "presence_semantics = 'proto3_parent_implied_v1' "
            "AND numeric_basis = "
            "'protobuf_double_roundtrip_decimal_v1' "
            "AND quantity_basis = 'upstox_reported_quantity_v1'",
            name=f"{table_name}_semantic_basis",
        ),
        sa.CheckConstraint(
            finite_nonnegative_prices,
            name=f"{table_name}_price_shape",
        ),
        sa.CheckConstraint(
            quantity_bounds,
            name=f"{table_name}_quantity_shape",
        ),
        sa.CheckConstraint(
            "open_interest IS NULL OR "
            "open_interest BETWEEN 0 AND 9007199254740992",
            name=f"{table_name}_open_interest",
        ),
        sa.CheckConstraint(
            "last_trade_at IS NULL OR ("
            "last_trade_at <> 'infinity'::timestamptz "
            "AND last_trade_at <> '-infinity'::timestamptz"
            ")",
            name=f"{table_name}_last_trade_finite",
        ),
        sa.CheckConstraint(
            "provider_depth_levels_present BETWEEN 0 AND 30 "
            "AND normalized_depth_levels IN (0, 1) "
            "AND unadopted_depth_level_count BETWEEN 0 AND 30 "
            "AND unadopted_depth_level_count = "
            "provider_depth_levels_present - normalized_depth_levels",
            name=f"{table_name}_depth_reconciliation",
        ),
        sa.CheckConstraint(
            feed_shape,
            name=f"{table_name}_feed_shape",
        ),
        sa.CheckConstraint(
            "array_position(unadopted_schema_paths, NULL) IS NULL "
            "AND cardinality(unadopted_schema_paths) <= 5000",
            name=f"{table_name}_unadopted_paths",
        ),
        sa.CheckConstraint(
            "array_position("
            "present_unadopted_message_paths, NULL"
            ") IS NULL "
            "AND cardinality("
            "present_unadopted_message_paths"
            ") <= 5000",
            name=f"{table_name}_present_paths",
        ),
        sa.CheckConstraint(
            "array_position("
            "secondary_payload_paths_present, NULL"
            ") IS NULL "
            "AND cardinality("
            "secondary_payload_paths_present"
            ") <= 5000",
            name=f"{table_name}_secondary_paths",
        ),
    )

    op.create_index(
        f"ix_{table_name}_mode_union",
        table_name,
        ("request_mode", "feed_union", "event_id"),
    )


def _create_market_segment_status_observations() -> None:
    op.create_table(
        "market_segment_status_observations",
        sa.Column("event_id", sa.String(ID), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(ID), nullable=False),
        sa.Column("segment", sa.String(128), nullable=False),
        sa.Column(
            "provider_status_name",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "provider_status_numeric",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("status_is_known", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id", "event_type", "subject_id"],
            [
                "market_observations.event_id",
                "market_observations.event_type",
                "market_observations.subject_id",
            ],
            ondelete="NO ACTION",
            name="fk_market_segment_status_event_type_subject",
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_segment_status_event_sha256",
        ),
        sa.CheckConstraint(
            "subject_id ~ '^sha256:[0-9a-f]{64}$'",
            name="market_segment_status_subject_sha256",
        ),
        sa.CheckConstraint(
            "event_type = 'market_segment_status_observation'",
            name="market_segment_status_event_type",
        ),
        sa.CheckConstraint(
            "octet_length(segment) BETWEEN 1 AND 128 "
            "AND segment = btrim(segment) "
            "AND segment !~ '[[:cntrl:]]'",
            name="market_segment_status_segment_shape",
        ),
        sa.CheckConstraint(
            "octet_length(provider_status_name) BETWEEN 1 AND 128 "
            "AND provider_status_name ~ '^[A-Z0-9_]+$'",
            name="market_segment_status_name_shape",
        ),
        sa.CheckConstraint(
            "(status_is_known AND ("
            "(provider_status_numeric = 0 "
            "AND provider_status_name = 'PRE_OPEN_START') OR "
            "(provider_status_numeric = 1 "
            "AND provider_status_name = 'PRE_OPEN_END') OR "
            "(provider_status_numeric = 2 "
            "AND provider_status_name = 'NORMAL_OPEN') OR "
            "(provider_status_numeric = 3 "
            "AND provider_status_name = 'NORMAL_CLOSE') OR "
            "(provider_status_numeric = 4 "
            "AND provider_status_name = 'CLOSING_START') OR "
            "(provider_status_numeric = 5 "
            "AND provider_status_name = 'CLOSING_END')"
            ")) OR ("
            "NOT status_is_known "
            "AND provider_status_numeric NOT IN (0, 1, 2, 3, 4, 5) "
            "AND provider_status_name = 'UNKNOWN'"
            ")",
            name="market_segment_status_known_mapping",
        ),
    )

    op.create_index(
        "ix_market_segment_status_segment_code",
        "market_segment_status_observations",
        ("segment", "provider_status_numeric", "event_id"),
    )


def _create_provider_subscription_instrument_sets() -> None:
    op.create_table(
        "provider_subscription_instrument_sets",
        sa.Column(
            "instrument_keys_digest",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "instrument_key_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "provider_contract_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "canonical_payload_hash",
            sa.String(ID),
            nullable=False,
        ),
        sa.CheckConstraint(
            "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="instrument_sets_digest_sha256",
        ),
        sa.CheckConstraint(
            "instrument_key_count BETWEEN 1 AND 5000",
            name="instrument_sets_count_bounds",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provider_contract_keys) = 'array'",
            name="instrument_sets_payload_array",
        ),
        sa.CheckConstraint(
            """
            CASE
                WHEN jsonb_typeof(provider_contract_keys) = 'array'
                THEN jsonb_array_length(provider_contract_keys)
                     = instrument_key_count
                ELSE FALSE
            END
            """,
            name="instrument_sets_payload_count",
        ),
        sa.CheckConstraint(
            "canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="instrument_sets_payload_hash_sha256",
        ),
        sa.CheckConstraint(
            "canonical_payload_hash = instrument_keys_digest",
            name="instrument_sets_payload_hash_identity",
        ),
    )

    op.create_table(
        "provider_subscription_instrument_set_keys",
        sa.Column(
            "instrument_keys_digest",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "key_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "provider_contract_key",
            sa.String(512),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "instrument_keys_digest",
            "key_ordinal",
            name="pk_provider_subscription_instrument_set_keys",
        ),
        sa.UniqueConstraint(
            "instrument_keys_digest",
            "provider_contract_key",
            name="uq_instrument_set_keys_digest_key",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_keys_digest"],
            [
                "provider_subscription_instrument_sets."
                "instrument_keys_digest"
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_instrument_set_keys_set",
        ),
        sa.CheckConstraint(
            "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="instrument_set_keys_digest_sha256",
        ),
        sa.CheckConstraint(
            "key_ordinal BETWEEN 0 AND 4999",
            name="instrument_set_keys_ordinal_bounds",
        ),
        sa.CheckConstraint(
            """
            octet_length(provider_contract_key) BETWEEN 1 AND 512
            AND provider_contract_key = btrim(provider_contract_key)
            AND provider_contract_key !~ '[[:cntrl:]]'
            """,
            name="instrument_set_keys_provider_key_shape",
        ),
    )

    # A key ordinal must fit within its owning set's declared count.
    # This is an O(1) parent lookup and also prevents later additions
    # to an already complete immutable set.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_subscription_instrument_key_ordinal()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            declared_count integer;
        BEGIN
            SELECT instrument_key_count
            INTO declared_count
            FROM provider_subscription_instrument_sets
            WHERE instrument_keys_digest = NEW.instrument_keys_digest;

            -- Parent existence is owned by
            -- fk_instrument_set_keys_set. Do not mask its
            -- foreign-key violation with a generic trigger error.
            IF declared_count IS NULL THEN
                RETURN NEW;
            END IF;

            IF NEW.key_ordinal >= declared_count THEN
                RAISE EXCEPTION
                    'subscription instrument key ordinal % exceeds '
                    'declared count % for %',
                    NEW.key_ordinal,
                    declared_count,
                    NEW.instrument_keys_digest;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER
        data14_subscription_instrument_key_ordinal
        BEFORE INSERT
        ON provider_subscription_instrument_set_keys
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_subscription_instrument_key_ordinal()
        """
    )

    # One deferred validation runs for each newly registered set.
    # It sees all keys inserted later in the same transaction.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_subscription_instrument_set()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            declared_count integer;
            stored_payload jsonb;
            stored_payload_hash varchar(71);
            actual_count integer;
            minimum_ordinal integer;
            maximum_ordinal integer;
            ordered_keys text[];
            canonically_sorted_keys text[];
            ordered_keys_json text;
            canonical_set_json text;
            recomputed_digest text;
        BEGIN
            SELECT
                instrument_key_count,
                provider_contract_keys,
                canonical_payload_hash
            INTO
                declared_count,
                stored_payload,
                stored_payload_hash
            FROM provider_subscription_instrument_sets
            WHERE instrument_keys_digest = NEW.instrument_keys_digest;

            SELECT
                count(*),
                min(key_ordinal),
                max(key_ordinal),
                array_agg(
                    provider_contract_key
                    ORDER BY key_ordinal
                ),
                array_agg(
                    provider_contract_key
                    ORDER BY provider_contract_key COLLATE "C"
                ),
                '[' ||
                COALESCE(
                    string_agg(
                        to_json(provider_contract_key)::text,
                        ','
                        ORDER BY key_ordinal
                    ),
                    ''
                ) ||
                ']'
            INTO
                actual_count,
                minimum_ordinal,
                maximum_ordinal,
                ordered_keys,
                canonically_sorted_keys,
                ordered_keys_json
            FROM provider_subscription_instrument_set_keys
            WHERE instrument_keys_digest = NEW.instrument_keys_digest;

            IF actual_count <> declared_count THEN
                RAISE EXCEPTION
                    'subscription instrument set count mismatch '
                    'for %: declared %, stored %',
                    NEW.instrument_keys_digest,
                    declared_count,
                    actual_count;
            END IF;

            IF minimum_ordinal <> 0
               OR maximum_ordinal <> declared_count - 1 THEN
                RAISE EXCEPTION
                    'subscription instrument set ordinals are not '
                    'contiguous for %',
                    NEW.instrument_keys_digest;
            END IF;

            IF ordered_keys IS DISTINCT FROM canonically_sorted_keys THEN
                RAISE EXCEPTION
                    'subscription instrument set keys are not '
                    'canonically sorted for %',
                    NEW.instrument_keys_digest;
            END IF;

            IF stored_payload
               IS DISTINCT FROM ordered_keys_json::jsonb THEN
                RAISE EXCEPTION
                    'subscription instrument set payload mismatch '
                    'for %',
                    NEW.instrument_keys_digest;
            END IF;

            canonical_set_json :=
                '{"entity":'
                '"provider_subscription_instrument_keys_v1",'
                '"provider_contract_keys":'
                || ordered_keys_json
                || '}';

            recomputed_digest :=
                'sha256:'
                || encode(
                    sha256(
                        convert_to(
                            canonical_set_json,
                            'UTF8'
                        )
                    ),
                    'hex'
                );

            IF NEW.instrument_keys_digest
               IS DISTINCT FROM recomputed_digest THEN
                RAISE EXCEPTION
                    'subscription instrument set digest mismatch '
                    'for %',
                    NEW.instrument_keys_digest;
            END IF;

            IF stored_payload_hash
               IS DISTINCT FROM recomputed_digest THEN
                RAISE EXCEPTION
                    'subscription instrument set payload hash '
                    'mismatch for %',
                    NEW.instrument_keys_digest;
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
        data14_subscription_instrument_set_integrity
        AFTER INSERT
        ON provider_subscription_instrument_sets
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_subscription_instrument_set()
        """
    )


def _create_provider_lifecycle_batches() -> None:
    op.create_table(
        "provider_lifecycle_batches",
        sa.Column(
            "lifecycle_batch_id",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "lifecycle_kind",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "normalization_schema_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "normalizer_implementation_version",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "input_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "unique_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "normalized_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "duplicate_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "batch_hash",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "normalized_sequence_hash",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "persistence_recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "lifecycle_batch_id",
            "lifecycle_kind",
            name="uq_provider_lifecycle_batches_id_kind",
        ),
        sa.CheckConstraint(
            "lifecycle_batch_id ~ '^sha256:[0-9a-f]{64}$'",
            name="provider_lifecycle_batches_id_sha256",
        ),
        sa.CheckConstraint(
            "lifecycle_kind IN ('connection', 'subscription')",
            name="provider_lifecycle_batches_kind",
        ),
        sa.CheckConstraint(
            "provider = 'upstox'",
            name="provider_lifecycle_batches_provider",
        ),
        sa.CheckConstraint(
            "normalization_schema_version = 1 "
            "AND normalizer_implementation_version = "
            "'upstox-v3-normalizer-1'",
            name="provider_lifecycle_batches_schema_label",
        ),
        sa.CheckConstraint(
            "input_count BETWEEN 0 AND 10000 "
            "AND unique_count BETWEEN 0 AND 10000 "
            "AND normalized_count BETWEEN 0 AND 10000 "
            "AND duplicate_count BETWEEN 0 AND 10000",
            name="provider_lifecycle_batches_count_bounds",
        ),
        sa.CheckConstraint(
            "normalized_count = unique_count "
            "AND duplicate_count = input_count - unique_count "
            "AND ("
            "(input_count = 0 AND unique_count = 0) "
            "OR ("
            "input_count BETWEEN 1 AND 10000 "
            "AND unique_count BETWEEN 1 AND input_count"
            ")"
            ")",
            name="provider_lifecycle_batches_count_reconciliation",
        ),
        sa.CheckConstraint(
            "batch_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="provider_lifecycle_batches_batch_hash",
        ),
        sa.CheckConstraint(
            "normalized_sequence_hash "
            "~ '^sha256:[0-9a-f]{64}$'",
            name="provider_lifecycle_batches_sequence_hash",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata_payload) = 'object'",
            name="provider_lifecycle_batches_metadata_object",
        ),
        sa.CheckConstraint(
            "persistence_recorded_at "
            "<> 'infinity'::timestamptz "
            "AND persistence_recorded_at "
            "<> '-infinity'::timestamptz",
            name="provider_lifecycle_batches_persistence_finite",
        ),
    )

    op.create_index(
        "ix_provider_lifecycle_batches_acceptance",
        "provider_lifecycle_batches",
        (
            "normalization_schema_version",
            "provider",
            "lifecycle_kind",
            "persistence_recorded_at",
            "lifecycle_batch_id",
        ),
    )


def _create_raw_provider_lifecycle_events() -> None:
    op.create_table(
        "raw_provider_lifecycle_events",
        sa.Column(
            "raw_event_id",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "lifecycle_kind",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "connection_session_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "subscription_scope_id",
            sa.String(512),
            nullable=True,
        ),
        sa.Column(
            "previous_state",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "source_order_scope_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "source_order",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "request_mode",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "instrument_keys_digest",
            sa.String(ID),
            sa.ForeignKey(
                "provider_subscription_instrument_sets."
                "instrument_keys_digest",
                ondelete="NO ACTION",
                onupdate="NO ACTION",
            ),
            nullable=True,
        ),
        sa.Column(
            "instrument_key_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "redacted_reason_code",
            sa.String(128),
            nullable=True,
        ),
        sa.Column(
            "provider_sequence",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "raw_event_id",
            "lifecycle_kind",
            name="uq_raw_provider_lifecycle_events_id_kind",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="raw_provider_lifecycle_events_id_sha256",
        ),
        sa.CheckConstraint(
            "lifecycle_kind IN ('connection', 'subscription')",
            name="raw_provider_lifecycle_events_kind",
        ),
        sa.CheckConstraint(
            "provider = 'upstox'",
            name="raw_provider_lifecycle_events_provider",
        ),
        sa.CheckConstraint(
            "octet_length(connection_session_id) BETWEEN 1 AND 512 "
            "AND connection_session_id ~ '[^[:space:]]'",
            name="raw_provider_lifecycle_events_connection_bytes",
        ),
        sa.CheckConstraint(
            "octet_length(source_order_scope_id) BETWEEN 1 AND 512 "
            "AND source_order_scope_id ~ '[^[:space:]]'",
            name="raw_provider_lifecycle_events_source_scope_bytes",
        ),
        sa.CheckConstraint(
            "subscription_scope_id IS NULL OR ("
            "octet_length(subscription_scope_id) BETWEEN 1 AND 512 "
            "AND subscription_scope_id ~ '[^[:space:]]'"
            ")",
            name="raw_provider_lifecycle_events_subscription_scope_bytes",
        ),
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 9223372036854775807",
            name="raw_provider_lifecycle_events_source_order",
        ),
        sa.CheckConstraint(
            "occurred_at <> 'infinity'::timestamptz "
            "AND occurred_at <> '-infinity'::timestamptz",
            name="raw_provider_lifecycle_events_occurred_finite",
        ),
        sa.CheckConstraint(
            "available_at <> 'infinity'::timestamptz "
            "AND available_at <> '-infinity'::timestamptz",
            name="raw_provider_lifecycle_events_available_finite",
        ),
        sa.CheckConstraint(
            "recorded_at <> 'infinity'::timestamptz "
            "AND recorded_at <> '-infinity'::timestamptz",
            name="raw_provider_lifecycle_events_recorded_finite",
        ),
        sa.CheckConstraint(
            "available_at >= occurred_at "
            "AND recorded_at >= available_at",
            name="raw_provider_lifecycle_events_clock_order",
        ),
        sa.CheckConstraint(
            "request_mode IS NULL OR "
            "request_mode IN ("
            "'ltpc', "
            "'option_greeks', "
            "'full_d5', "
            "'full_d30'"
            ")",
            name="raw_provider_lifecycle_events_request_mode",
        ),
        sa.CheckConstraint(
            "instrument_keys_digest IS NULL OR "
            "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="raw_provider_lifecycle_events_instrument_digest",
        ),
        sa.CheckConstraint(
            "instrument_key_count IS NULL OR "
            "instrument_key_count BETWEEN 1 AND 5000",
            name="raw_provider_lifecycle_events_instrument_count",
        ),
        sa.CheckConstraint(
            "("
            "lifecycle_kind = 'connection' "
            "AND subscription_scope_id IS NULL "
            "AND request_mode IS NULL "
            "AND instrument_keys_digest IS NULL "
            "AND instrument_key_count IS NULL"
            ") OR ("
            "lifecycle_kind = 'subscription' "
            "AND subscription_scope_id IS NOT NULL "
            "AND instrument_keys_digest IS NOT NULL "
            "AND instrument_key_count IS NOT NULL"
            ")",
            name="raw_provider_lifecycle_events_kind_columns",
        ),
        sa.CheckConstraint(
            "COALESCE(("
            "("
            "lifecycle_kind = 'connection' AND ("
            "(previous_state IS NULL AND state = 'connecting') "
            "OR (previous_state = 'connecting' "
            "AND state IN ('connected', 'failed', 'closing')) "
            "OR (previous_state = 'connected' "
            "AND state IN ('authorized', 'closing', 'failed')) "
            "OR (previous_state = 'authorized' "
            "AND state IN ('closing', 'reconnecting', 'failed')) "
            "OR (previous_state = 'reconnecting' "
            "AND state IN ('closing', 'failed')) "
            "OR (previous_state = 'closing' "
            "AND state IN ('closed', 'failed')) "
            "OR (previous_state = 'failed' "
            "AND state IN ('reconnecting', 'closing', 'closed'))"
            ")"
            ") OR ("
            "lifecycle_kind = 'subscription' AND ("
            "(previous_state IS NULL "
            "AND state = 'subscribe_requested') "
            "OR (previous_state = 'subscribe_requested' "
            "AND state IN ('subscribed', 'subscription_failed')) "
            "OR (previous_state = 'subscribed' "
            "AND state IN ("
            "'mode_change_requested', "
            "'unsubscribe_requested', "
            "'subscription_failed'"
            ")) "
            "OR (previous_state = 'mode_change_requested' "
            "AND state IN ('mode_changed', 'subscription_failed')) "
            "OR (previous_state = 'mode_changed' "
            "AND state IN ("
            "'mode_change_requested', "
            "'unsubscribe_requested', "
            "'subscription_failed'"
            ")) "
            "OR (previous_state = 'unsubscribe_requested' "
            "AND state IN ('unsubscribed', 'subscription_failed'))"
            ")"
            ")"
            "), FALSE)",
            name="raw_provider_lifecycle_events_transition",
        ),
        sa.CheckConstraint(
            "("
            "lifecycle_kind = 'connection' "
            "AND request_mode IS NULL"
            ") OR ("
            "lifecycle_kind = 'subscription' AND ("
            "("
            "state IN ("
            "'subscribe_requested', "
            "'subscribed', "
            "'mode_change_requested', "
            "'mode_changed'"
            ") "
            "AND request_mode IS NOT NULL"
            ") OR ("
            "state IN ("
            "'unsubscribe_requested', "
            "'unsubscribed', "
            "'subscription_failed'"
            ")"
            ")"
            ")"
            ")",
            name="raw_provider_lifecycle_events_mode_shape",
        ),
        sa.CheckConstraint(
            "request_mode IS NULL "
            "OR (request_mode = 'ltpc' "
            "AND instrument_key_count BETWEEN 1 AND 5000) "
            "OR (request_mode = 'option_greeks' "
            "AND instrument_key_count BETWEEN 1 AND 3000) "
            "OR (request_mode = 'full_d5' "
            "AND instrument_key_count BETWEEN 1 AND 2000) "
            "OR (request_mode = 'full_d30' "
            "AND instrument_key_count BETWEEN 1 AND 50)",
            name="raw_provider_lifecycle_events_mode_limit",
        ),
        sa.CheckConstraint(
            "redacted_reason_code IS NULL OR ("
            "octet_length(redacted_reason_code) BETWEEN 1 AND 128 "
            "AND redacted_reason_code "
            "~ '^[a-z0-9]+(_[a-z0-9]+)*$' "
            "AND redacted_reason_code "
            "!~ '(token|url|traceback|socket|account|user_id|exception)'"
            ")",
            name="raw_provider_lifecycle_events_reason_format",
        ),
        sa.CheckConstraint(
            "("
            "lifecycle_kind = 'connection' AND ("
            "(state = 'failed' AND redacted_reason_code IS NOT NULL) "
            "OR (state <> 'failed' AND redacted_reason_code IS NULL)"
            ")"
            ") OR ("
            "lifecycle_kind = 'subscription' AND ("
            "(state = 'subscription_failed' "
            "AND redacted_reason_code IS NOT NULL) "
            "OR (state <> 'subscription_failed' "
            "AND redacted_reason_code IS NULL)"
            ")"
            ")",
            name="raw_provider_lifecycle_events_reason_shape",
        ),
        sa.CheckConstraint(
            "provider_sequence IS NULL",
            name="raw_provider_lifecycle_events_provider_sequence",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="raw_provider_lifecycle_events_payload_object",
        ),
    )

    op.create_index(
        "ix_raw_provider_lifecycle_events_scope_order",
        "raw_provider_lifecycle_events",
        (
            "provider",
            "connection_session_id",
            "source_order_scope_id",
            "source_order",
            "raw_event_id",
        ),
    )

    op.create_index(
        "ix_raw_provider_lifecycle_events_subscription_scope",
        "raw_provider_lifecycle_events",
        (
            "provider",
            "connection_session_id",
            "subscription_scope_id",
            "source_order",
            "raw_event_id",
        ),
        postgresql_where=sa.text(
            "lifecycle_kind = 'subscription'"
        ),
    )

    # The immutable set FK owns parent existence. This trigger
    # verifies the redundant typed count without masking an
    # orphan-digest foreign-key violation.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_raw_lifecycle_instrument_count()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            declared_count integer;
        BEGIN
            IF NEW.lifecycle_kind <> 'subscription' THEN
                RETURN NEW;
            END IF;

            SELECT instrument_key_count
            INTO declared_count
            FROM provider_subscription_instrument_sets
            WHERE instrument_keys_digest =
                NEW.instrument_keys_digest;

            IF declared_count IS NULL THEN
                RETURN NEW;
            END IF;

            IF NEW.instrument_key_count
               IS DISTINCT FROM declared_count THEN
                RAISE EXCEPTION
                    'raw lifecycle instrument count mismatch '
                    'for %: declared %, event %',
                    NEW.instrument_keys_digest,
                    declared_count,
                    NEW.instrument_key_count;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER
        data14_raw_lifecycle_instrument_count
        BEFORE INSERT
        ON raw_provider_lifecycle_events
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_raw_lifecycle_instrument_count()
        """
    )


def _create_provider_lifecycle_batch_events() -> None:
    op.create_table(
        "provider_lifecycle_batch_events",
        sa.Column(
            "lifecycle_batch_id",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "lifecycle_kind",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "input_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "raw_event_id",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "is_exact_duplicate",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "first_occurrence_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "lifecycle_batch_id",
            "input_ordinal",
            name="pk_provider_lifecycle_batch_events",
        ),
        sa.UniqueConstraint(
            "lifecycle_batch_id",
            "raw_event_id",
            "input_ordinal",
            name="uq_lifecycle_batch_events_membership",
        ),
        sa.ForeignKeyConstraint(
            [
                "lifecycle_batch_id",
                "lifecycle_kind",
            ],
            [
                "provider_lifecycle_batches.lifecycle_batch_id",
                "provider_lifecycle_batches.lifecycle_kind",
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_lifecycle_batch_events_batch",
        ),
        sa.ForeignKeyConstraint(
            [
                "raw_event_id",
                "lifecycle_kind",
            ],
            [
                "raw_provider_lifecycle_events.raw_event_id",
                "raw_provider_lifecycle_events.lifecycle_kind",
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_lifecycle_batch_events_raw_event",
        ),
        sa.ForeignKeyConstraint(
            [
                "lifecycle_batch_id",
                "raw_event_id",
                "first_occurrence_ordinal",
            ],
            [
                "provider_lifecycle_batch_events.lifecycle_batch_id",
                "provider_lifecycle_batch_events.raw_event_id",
                "provider_lifecycle_batch_events.input_ordinal",
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
            name="fk_lifecycle_batch_events_first_occurrence",
        ),
        sa.CheckConstraint(
            "lifecycle_batch_id ~ '^sha256:[0-9a-f]{64}$'",
            name="lifecycle_batch_events_batch_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="lifecycle_batch_events_raw_sha256",
        ),
        sa.CheckConstraint(
            "lifecycle_kind IN ('connection', 'subscription')",
            name="lifecycle_batch_events_kind",
        ),
        sa.CheckConstraint(
            "input_ordinal BETWEEN 0 AND 9999",
            name="lifecycle_batch_events_input_ordinal",
        ),
        sa.CheckConstraint(
            "first_occurrence_ordinal BETWEEN 0 AND 9999 "
            "AND first_occurrence_ordinal <= input_ordinal",
            name="lifecycle_batch_events_first_ordinal",
        ),
        sa.CheckConstraint(
            "is_exact_duplicate = "
            "(first_occurrence_ordinal < input_ordinal)",
            name="lifecycle_batch_events_duplicate_shape",
        ),
    )

    op.create_index(
        "ix_lifecycle_batch_events_raw",
        "provider_lifecycle_batch_events",
        (
            "raw_event_id",
            "lifecycle_batch_id",
            "input_ordinal",
        ),
    )

    op.create_index(
        "ix_lifecycle_batch_events_first_occurrence",
        "provider_lifecycle_batch_events",
        (
            "lifecycle_batch_id",
            "raw_event_id",
            "first_occurrence_ordinal",
        ),
    )

    # Prevent an ordinal from exceeding its owning batch's declared
    # input count. Missing or cross-kind parents remain owned by the
    # composite foreign key rather than being masked by this trigger.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_lifecycle_batch_event_ordinal()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            declared_input_count integer;
        BEGIN
            SELECT input_count
            INTO declared_input_count
            FROM provider_lifecycle_batches
            WHERE lifecycle_batch_id =
                NEW.lifecycle_batch_id
              AND lifecycle_kind =
                NEW.lifecycle_kind;

            IF declared_input_count IS NULL THEN
                RETURN NEW;
            END IF;

            IF NEW.input_ordinal >= declared_input_count THEN
                RAISE EXCEPTION
                    'lifecycle batch input ordinal % exceeds '
                    'declared input count % for %',
                    NEW.input_ordinal,
                    declared_input_count,
                    NEW.lifecycle_batch_id;
            END IF;

            IF NEW.first_occurrence_ordinal
               >= declared_input_count THEN
                RAISE EXCEPTION
                    'lifecycle batch first occurrence ordinal % '
                    'exceeds declared input count % for %',
                    NEW.first_occurrence_ordinal,
                    declared_input_count,
                    NEW.lifecycle_batch_id;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER
        data14_lifecycle_batch_event_ordinal
        BEFORE INSERT
        ON provider_lifecycle_batch_events
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_lifecycle_batch_event_ordinal()
        """
    )

    # One deferred aggregate check runs from the batch root. The root
    # is inserted before its memberships and therefore sees the
    # complete input sequence at transaction commit.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_lifecycle_batch_events()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            declared_input_count integer;
            declared_unique_count integer;
            declared_duplicate_count integer;
            actual_count bigint;
            minimum_ordinal integer;
            maximum_ordinal integer;
            classified_unique_count bigint;
            classified_duplicate_count bigint;
            distinct_raw_count bigint;
            invalid_first_occurrence boolean;
        BEGIN
            SELECT
                input_count,
                unique_count,
                duplicate_count
            INTO
                declared_input_count,
                declared_unique_count,
                declared_duplicate_count
            FROM provider_lifecycle_batches
            WHERE lifecycle_batch_id =
                NEW.lifecycle_batch_id;

            SELECT
                count(*),
                min(input_ordinal),
                max(input_ordinal),
                count(*) FILTER (
                    WHERE NOT is_exact_duplicate
                ),
                count(*) FILTER (
                    WHERE is_exact_duplicate
                ),
                count(DISTINCT raw_event_id)
            INTO
                actual_count,
                minimum_ordinal,
                maximum_ordinal,
                classified_unique_count,
                classified_duplicate_count,
                distinct_raw_count
            FROM provider_lifecycle_batch_events
            WHERE lifecycle_batch_id =
                NEW.lifecycle_batch_id;

            IF actual_count <> declared_input_count THEN
                RAISE EXCEPTION
                    'lifecycle batch event count mismatch '
                    'for %: declared %, stored %',
                    NEW.lifecycle_batch_id,
                    declared_input_count,
                    actual_count;
            END IF;

            IF declared_input_count > 0
               AND (
                   minimum_ordinal <> 0
                   OR maximum_ordinal
                      <> declared_input_count - 1
               ) THEN
                RAISE EXCEPTION
                    'lifecycle batch input ordinals are not '
                    'contiguous for %',
                    NEW.lifecycle_batch_id;
            END IF;

            IF classified_unique_count
               <> declared_unique_count THEN
                RAISE EXCEPTION
                    'lifecycle batch unique classification '
                    'mismatch for %',
                    NEW.lifecycle_batch_id;
            END IF;

            IF classified_duplicate_count
               <> declared_duplicate_count THEN
                RAISE EXCEPTION
                    'lifecycle batch duplicate classification '
                    'mismatch for %',
                    NEW.lifecycle_batch_id;
            END IF;

            IF distinct_raw_count
               <> declared_unique_count THEN
                RAISE EXCEPTION
                    'lifecycle batch distinct raw count '
                    'mismatch for %',
                    NEW.lifecycle_batch_id;
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM provider_lifecycle_batch_events current_row
                LEFT JOIN provider_lifecycle_batch_events first_row
                    ON first_row.lifecycle_batch_id =
                        current_row.lifecycle_batch_id
                    AND first_row.raw_event_id =
                        current_row.raw_event_id
                    AND first_row.input_ordinal =
                        current_row.first_occurrence_ordinal
                WHERE current_row.lifecycle_batch_id =
                    NEW.lifecycle_batch_id
                AND first_row.input_ordinal IS NOT NULL
                AND (
                    first_row.is_exact_duplicate
                    OR first_row.first_occurrence_ordinal
                        <> first_row.input_ordinal
                )
            )
            INTO invalid_first_occurrence;

            IF invalid_first_occurrence THEN
                RAISE EXCEPTION
                    'lifecycle batch first occurrence '
                    'classification mismatch for %',
                    NEW.lifecycle_batch_id;
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
        data14_lifecycle_batch_events_integrity
        AFTER INSERT
        ON provider_lifecycle_batches
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_lifecycle_batch_events()
        """
    )


def _create_provider_lifecycle_observations() -> None:
    op.create_table(
        "provider_lifecycle_observations",
        sa.Column(
            "event_id",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "raw_event_id",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "lifecycle_kind",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "connection_session_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "source_order_scope_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "source_order",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "normalization_schema_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "normalizer_implementation_version",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "provider_sequence",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "event_id",
            "raw_event_id",
            name="uq_provider_lifecycle_observations_event_raw",
        ),
        sa.UniqueConstraint(
            "raw_event_id",
            "normalization_schema_version",
            name="uq_provider_lifecycle_observations_raw_schema",
        ),
        sa.UniqueConstraint(
            "event_id",
            "event_type",
            "subject_id",
            "lifecycle_kind",
            "connection_session_id",
            name="uq_provider_lifecycle_observations_typed_identity",
        ),
        sa.ForeignKeyConstraint(
            [
                "raw_event_id",
                "lifecycle_kind",
            ],
            [
                "raw_provider_lifecycle_events.raw_event_id",
                "raw_provider_lifecycle_events.lifecycle_kind",
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_provider_lifecycle_observations_raw_event",
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="provider_lifecycle_observations_event_sha256",
        ),
        sa.CheckConstraint(
            "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="provider_lifecycle_observations_raw_sha256",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'provider_connection_lifecycle_observation', "
            "'provider_subscription_lifecycle_observation'"
            ")",
            name="provider_lifecycle_observations_event_type",
        ),
        sa.CheckConstraint(
            "octet_length(subject_id) BETWEEN 1 AND 512 "
            "AND subject_id ~ '[^[:space:]]'",
            name="provider_lifecycle_observations_subject_bytes",
        ),
        sa.CheckConstraint(
            "lifecycle_kind IN ('connection', 'subscription')",
            name="provider_lifecycle_observations_kind",
        ),
        sa.CheckConstraint(
            "("
            "lifecycle_kind = 'connection' "
            "AND event_type = "
            "'provider_connection_lifecycle_observation' "
            "AND subject_id = connection_session_id"
            ") OR ("
            "lifecycle_kind = 'subscription' "
            "AND event_type = "
            "'provider_subscription_lifecycle_observation' "
            "AND subject_id ~ '^sha256:[0-9a-f]{64}$'"
            ")",
            name="provider_lifecycle_observations_identity_shape",
        ),
        sa.CheckConstraint(
            "provider = 'upstox'",
            name="provider_lifecycle_observations_provider",
        ),
        sa.CheckConstraint(
            "octet_length(connection_session_id) BETWEEN 1 AND 512 "
            "AND connection_session_id ~ '[^[:space:]]'",
            name="provider_lifecycle_observations_connection_bytes",
        ),
        sa.CheckConstraint(
            "octet_length(source_order_scope_id) BETWEEN 1 AND 512 "
            "AND source_order_scope_id ~ '[^[:space:]]'",
            name="provider_lifecycle_observations_source_scope_bytes",
        ),
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 9223372036854775807",
            name="provider_lifecycle_observations_source_order",
        ),
        sa.CheckConstraint(
            "occurred_at <> 'infinity'::timestamptz "
            "AND occurred_at <> '-infinity'::timestamptz",
            name="provider_lifecycle_observations_occurred_finite",
        ),
        sa.CheckConstraint(
            "available_at <> 'infinity'::timestamptz "
            "AND available_at <> '-infinity'::timestamptz",
            name="provider_lifecycle_observations_available_finite",
        ),
        sa.CheckConstraint(
            "recorded_at <> 'infinity'::timestamptz "
            "AND recorded_at <> '-infinity'::timestamptz",
            name="provider_lifecycle_observations_recorded_finite",
        ),
        sa.CheckConstraint(
            "available_at >= occurred_at "
            "AND recorded_at >= available_at",
            name="provider_lifecycle_observations_clock_order",
        ),
        sa.CheckConstraint(
            "normalization_schema_version = 1 "
            "AND normalizer_implementation_version = "
            "'upstox-v3-normalizer-1'",
            name="provider_lifecycle_observations_schema_label",
        ),
        sa.CheckConstraint(
            "provider_sequence IS NULL",
            name="provider_lifecycle_observations_provider_sequence",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="provider_lifecycle_observations_payload_object",
        ),
    )

    op.create_index(
        "ix_provider_lifecycle_observations_scope_order",
        "provider_lifecycle_observations",
        (
            "normalization_schema_version",
            "provider",
            "connection_session_id",
            "source_order_scope_id",
            "source_order",
            "event_id",
        ),
    )
    op.create_index(
        "ix_provider_lifecycle_observations_subject_time",
        "provider_lifecycle_observations",
        (
            "normalization_schema_version",
            "subject_id",
            "lifecycle_kind",
            "available_at",
            "event_id",
        ),
    )
    op.create_index(
        "ix_provider_lifecycle_observations_raw",
        "provider_lifecycle_observations",
        (
            "raw_event_id",
            "event_id",
        ),
    )


def _create_provider_connection_lifecycle_observations() -> None:
    op.create_table(
        "provider_connection_lifecycle_observations",
        sa.Column(
            "event_id",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "event_type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "lifecycle_kind",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "connection_session_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "previous_state",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "redacted_reason_code",
            sa.String(128),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            [
                "event_id",
                "event_type",
                "subject_id",
                "lifecycle_kind",
                "connection_session_id",
            ],
            [
                "provider_lifecycle_observations.event_id",
                "provider_lifecycle_observations.event_type",
                "provider_lifecycle_observations.subject_id",
                "provider_lifecycle_observations.lifecycle_kind",
                "provider_lifecycle_observations.connection_session_id",
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_connection_lifecycle_observations_typed_identity",
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="connection_lifecycle_observations_event_sha256",
        ),
        sa.CheckConstraint(
            "event_type = "
            "'provider_connection_lifecycle_observation'",
            name="connection_lifecycle_observations_event_type",
        ),
        sa.CheckConstraint(
            "lifecycle_kind = 'connection'",
            name="connection_lifecycle_observations_kind",
        ),
        sa.CheckConstraint(
            "octet_length(connection_session_id) BETWEEN 1 AND 512 "
            "AND connection_session_id ~ '[^[:space:]]' "
            "AND subject_id = connection_session_id",
            name="connection_lifecycle_observations_identity_shape",
        ),
        sa.CheckConstraint(
            "COALESCE(("
            "(previous_state IS NULL AND state = 'connecting') "
            "OR (previous_state = 'connecting' "
            "AND state IN ('connected', 'failed', 'closing')) "
            "OR (previous_state = 'connected' "
            "AND state IN ('authorized', 'closing', 'failed')) "
            "OR (previous_state = 'authorized' "
            "AND state IN ('closing', 'reconnecting', 'failed')) "
            "OR (previous_state = 'reconnecting' "
            "AND state IN ('closing', 'failed')) "
            "OR (previous_state = 'closing' "
            "AND state IN ('closed', 'failed')) "
            "OR (previous_state = 'failed' "
            "AND state IN ('reconnecting', 'closing', 'closed'))"
            "), FALSE)",
            name="connection_lifecycle_observations_transition",
        ),
        sa.CheckConstraint(
            "redacted_reason_code IS NULL OR ("
            "octet_length(redacted_reason_code) BETWEEN 1 AND 128 "
            "AND redacted_reason_code "
            "~ '^[a-z0-9]+(_[a-z0-9]+)*$' "
            "AND redacted_reason_code "
            "!~ '(token|url|traceback|socket|account|user_id|exception)'"
            ")",
            name="connection_lifecycle_observations_reason_format",
        ),
        sa.CheckConstraint(
            "(state = 'failed' "
            "AND redacted_reason_code IS NOT NULL) "
            "OR (state <> 'failed' "
            "AND redacted_reason_code IS NULL)",
            name="connection_lifecycle_observations_reason_shape",
        ),
    )

    op.create_index(
        "ix_provider_connection_lifecycle_state",
        "provider_connection_lifecycle_observations",
        (
            "connection_session_id",
            "state",
            "event_id",
        ),
    )


def _create_provider_subscription_lifecycle_observations() -> None:
    op.create_table(
        "provider_subscription_lifecycle_observations",
        sa.Column(
            "event_id",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "event_type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "lifecycle_kind",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "connection_session_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "subscription_scope_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "previous_state",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "request_mode",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "instrument_keys_digest",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "instrument_key_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "redacted_reason_code",
            sa.String(128),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            [
                "event_id",
                "event_type",
                "subject_id",
                "lifecycle_kind",
                "connection_session_id",
            ],
            [
                "provider_lifecycle_observations.event_id",
                "provider_lifecycle_observations.event_type",
                "provider_lifecycle_observations.subject_id",
                "provider_lifecycle_observations.lifecycle_kind",
                "provider_lifecycle_observations.connection_session_id",
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_subscription_lifecycle_observations_typed_identity",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_keys_digest"],
            [
                "provider_subscription_instrument_sets."
                "instrument_keys_digest"
            ],
            ondelete="NO ACTION",
            onupdate="NO ACTION",
            name="fk_subscription_lifecycle_observations_instrument_set",
        ),
        sa.CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name="subscription_lifecycle_observations_event_sha256",
        ),
        sa.CheckConstraint(
            "event_type = "
            "'provider_subscription_lifecycle_observation'",
            name="subscription_lifecycle_observations_event_type",
        ),
        sa.CheckConstraint(
            "subject_id ~ '^sha256:[0-9a-f]{64}$'",
            name="subscription_lifecycle_observations_subject_sha256",
        ),
        sa.CheckConstraint(
            "lifecycle_kind = 'subscription'",
            name="subscription_lifecycle_observations_kind",
        ),
        sa.CheckConstraint(
            "octet_length(connection_session_id) BETWEEN 1 AND 512 "
            "AND connection_session_id ~ '[^[:space:]]'",
            name="subscription_lifecycle_observations_connection_bytes",
        ),
        sa.CheckConstraint(
            "octet_length(subscription_scope_id) BETWEEN 1 AND 512 "
            "AND subscription_scope_id ~ '[^[:space:]]'",
            name="subscription_lifecycle_observations_scope_bytes",
        ),
        sa.CheckConstraint(
            "COALESCE(("
            "(previous_state IS NULL "
            "AND state = 'subscribe_requested') "
            "OR (previous_state = 'subscribe_requested' "
            "AND state IN ('subscribed', 'subscription_failed')) "
            "OR (previous_state = 'subscribed' "
            "AND state IN ("
            "'mode_change_requested', "
            "'unsubscribe_requested', "
            "'subscription_failed'"
            ")) "
            "OR (previous_state = 'mode_change_requested' "
            "AND state IN ('mode_changed', 'subscription_failed')) "
            "OR (previous_state = 'mode_changed' "
            "AND state IN ("
            "'mode_change_requested', "
            "'unsubscribe_requested', "
            "'subscription_failed'"
            ")) "
            "OR (previous_state = 'unsubscribe_requested' "
            "AND state IN ('unsubscribed', 'subscription_failed'))"
            "), FALSE)",
            name="subscription_lifecycle_observations_transition",
        ),
        sa.CheckConstraint(
            "request_mode IS NULL OR "
            "request_mode IN ("
            "'ltpc', "
            "'option_greeks', "
            "'full_d5', "
            "'full_d30'"
            ")",
            name="subscription_lifecycle_observations_request_mode",
        ),
        sa.CheckConstraint(
            "("
            "state IN ("
            "'subscribe_requested', "
            "'subscribed', "
            "'mode_change_requested', "
            "'mode_changed'"
            ") "
            "AND request_mode IS NOT NULL"
            ") OR ("
            "state IN ("
            "'unsubscribe_requested', "
            "'unsubscribed', "
            "'subscription_failed'"
            ")"
            ")",
            name="subscription_lifecycle_observations_mode_shape",
        ),
        sa.CheckConstraint(
            "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="subscription_lifecycle_observations_instrument_digest",
        ),
        sa.CheckConstraint(
            "instrument_key_count BETWEEN 1 AND 5000",
            name="subscription_lifecycle_observations_instrument_count",
        ),
        sa.CheckConstraint(
            "request_mode IS NULL "
            "OR (request_mode = 'ltpc' "
            "AND instrument_key_count BETWEEN 1 AND 5000) "
            "OR (request_mode = 'option_greeks' "
            "AND instrument_key_count BETWEEN 1 AND 3000) "
            "OR (request_mode = 'full_d5' "
            "AND instrument_key_count BETWEEN 1 AND 2000) "
            "OR (request_mode = 'full_d30' "
            "AND instrument_key_count BETWEEN 1 AND 50)",
            name="subscription_lifecycle_observations_mode_limit",
        ),
        sa.CheckConstraint(
            "redacted_reason_code IS NULL OR ("
            "octet_length(redacted_reason_code) BETWEEN 1 AND 128 "
            "AND redacted_reason_code "
            "~ '^[a-z0-9]+(_[a-z0-9]+)*$' "
            "AND redacted_reason_code "
            "!~ '(token|url|traceback|socket|account|user_id|exception)'"
            ")",
            name="subscription_lifecycle_observations_reason_format",
        ),
        sa.CheckConstraint(
            "(state = 'subscription_failed' "
            "AND redacted_reason_code IS NOT NULL) "
            "OR (state <> 'subscription_failed' "
            "AND redacted_reason_code IS NULL)",
            name="subscription_lifecycle_observations_reason_shape",
        ),
    )

    op.create_index(
        "ix_provider_subscription_lifecycle_scope_state",
        "provider_subscription_lifecycle_observations",
        (
            "connection_session_id",
            "subscription_scope_id",
            "state",
            "event_id",
        ),
    )
    op.create_index(
        "ix_provider_subscription_lifecycle_instrument_set",
        "provider_subscription_lifecycle_observations",
        (
            "instrument_keys_digest",
            "event_id",
        ),
    )

    # The immutable set FK owns parent existence. This trigger
    # verifies the redundant typed count without masking an
    # orphan-digest foreign-key violation.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_subscription_lifecycle_observation_count()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            declared_count integer;
        BEGIN
            SELECT instrument_key_count
            INTO declared_count
            FROM provider_subscription_instrument_sets
            WHERE instrument_keys_digest =
                NEW.instrument_keys_digest;

            IF declared_count IS NULL THEN
                RETURN NEW;
            END IF;

            IF NEW.instrument_key_count
               IS DISTINCT FROM declared_count THEN
                RAISE EXCEPTION
                    'subscription lifecycle observation '
                    'instrument count mismatch for %: '
                    'declared %, observation %',
                    NEW.instrument_keys_digest,
                    declared_count,
                    NEW.instrument_key_count;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER
        data14_subscription_lifecycle_observation_count
        BEFORE INSERT
        ON provider_subscription_lifecycle_observations
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_subscription_lifecycle_observation_count()
        """
    )


def _create_provider_lifecycle_observation_integrity() -> None:
    # A normalized lifecycle observation root must have exactly one
    # typed subtype by commit. The root is inserted first, so this
    # deferred trigger sees the subtype inserted later in the same
    # transaction.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        data14_validate_provider_lifecycle_observation_subtype()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            connection_count bigint;
            subscription_count bigint;
        BEGIN
            SELECT count(*)
            INTO connection_count
            FROM provider_connection_lifecycle_observations
            WHERE event_id = NEW.event_id;

            SELECT count(*)
            INTO subscription_count
            FROM provider_subscription_lifecycle_observations
            WHERE event_id = NEW.event_id;

            IF NEW.lifecycle_kind = 'connection' THEN
                IF connection_count <> 1
                   OR subscription_count <> 0 THEN
                    RAISE EXCEPTION
                        'provider lifecycle observation % '
                        'must have exactly one connection subtype',
                        NEW.event_id;
                END IF;
            ELSIF NEW.lifecycle_kind = 'subscription' THEN
                IF connection_count <> 0
                   OR subscription_count <> 1 THEN
                    RAISE EXCEPTION
                        'provider lifecycle observation % '
                        'must have exactly one subscription subtype',
                        NEW.event_id;
                END IF;
            ELSE
                RAISE EXCEPTION
                    'provider lifecycle observation % '
                    'has unsupported lifecycle kind %',
                    NEW.event_id,
                    NEW.lifecycle_kind;
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
        data14_provider_lifecycle_observation_subtype_integrity
        AFTER INSERT
        ON provider_lifecycle_observations
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
        data14_validate_provider_lifecycle_observation_subtype()
        """
    )

def upgrade() -> None:
    _create_temporal_provenance_targets()
    _create_provider_subscription_instrument_sets()
    _create_provider_lifecycle_batches()
    _create_raw_provider_lifecycle_events()
    _create_provider_lifecycle_batch_events()
    _create_provider_lifecycle_observations()
    _create_provider_connection_lifecycle_observations()
    _create_provider_subscription_lifecycle_observations()
    _create_provider_lifecycle_observation_integrity()

    for name in TABLES:
        if name in {
            "provider_subscription_instrument_sets",
            "provider_subscription_instrument_set_keys",
            "provider_lifecycle_batches",
            "raw_provider_lifecycle_events",
            "provider_lifecycle_batch_events",
            "provider_lifecycle_observations",
            "provider_connection_lifecycle_observations",
            "provider_subscription_lifecycle_observations",
        }:
            continue

        if name == "raw_market_frames":
            _create_raw_market_frames()
            continue

        if name == "market_normalization_results":
            _create_market_normalization_results()
            continue

        if name == "market_observations":
            _create_market_observations()
            continue

        if name == "market_normalization_result_events":
            _create_market_normalization_result_events()
            continue

        if name == "market_normalization_failures":
            _create_market_normalization_failures()
            continue

        if name == "market_normalization_result_failures":
            _create_market_normalization_result_failures()
            continue

        if name == "underlying_quote_observations":
            _create_quote_observation_table(
                name,
                "underlying_quote_observation",
                "(feed_union = 'ltpc' "
                "AND request_mode = 'ltpc' "
                "AND provider_depth_levels_present = 0 "
                "AND normalized_depth_levels = 0) "
                "OR (feed_union = 'indexFF' "
                "AND request_mode IN ('full_d5', 'full_d30') "
                "AND provider_depth_levels_present = 0 "
                "AND normalized_depth_levels = 0)",
            )
            continue

        if name == "futures_quote_observations":
            _create_quote_observation_table(
                name,
                "futures_quote_observation",
                "(feed_union = 'ltpc' "
                "AND request_mode = 'ltpc' "
                "AND provider_depth_levels_present = 0 "
                "AND normalized_depth_levels = 0) "
                "OR (feed_union = 'marketFF' "
                "AND ((request_mode = 'full_d5' "
                "AND provider_depth_levels_present <= 5) "
                "OR (request_mode = 'full_d30' "
                "AND provider_depth_levels_present <= 30)) "
                "AND normalized_depth_levels = CASE "
                "WHEN provider_depth_levels_present > 0 "
                "THEN 1 ELSE 0 END)",
            )
            continue

        if name == "option_quote_observations":
            _create_quote_observation_table(
                name,
                "option_quote_observation",
                "(feed_union = 'ltpc' "
                "AND request_mode = 'ltpc' "
                "AND provider_depth_levels_present = 0 "
                "AND normalized_depth_levels = 0) "
                "OR (feed_union = 'marketFF' "
                "AND ((request_mode = 'full_d5' "
                "AND provider_depth_levels_present <= 5) "
                "OR (request_mode = 'full_d30' "
                "AND provider_depth_levels_present <= 30)) "
                "AND normalized_depth_levels = CASE "
                "WHEN provider_depth_levels_present > 0 "
                "THEN 1 ELSE 0 END) "
                "OR (feed_union = 'firstLevelWithGreeks' "
                "AND request_mode = 'option_greeks' "
                "AND provider_depth_levels_present IN (0, 1) "
                "AND normalized_depth_levels = "
                "provider_depth_levels_present)",
            )
            continue

        if name == "market_segment_status_observations":
            _create_market_segment_status_observations()
            continue

        columns = [
            sa.Column(
                "id",
                sa.String(ID),
                primary_key=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
        ]

        op.create_table(name, *columns)

        op.create_check_constraint(
            f"ck_{name}_append_created",
            name,
            "id <> ''",
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION data14_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'DATA-1.4 tables are append-only';
        END;
        $$
        """
    )

    for name in TABLES:
        op.execute(
            f"""
            CREATE TRIGGER data14_{name}_immutable
            BEFORE UPDATE OR DELETE ON {name}
            FOR EACH ROW
            EXECUTE FUNCTION data14_reject_mutation()
            """
        )

        op.execute(
            f"""
            CREATE TRIGGER data14_{name}_no_truncate
            BEFORE TRUNCATE ON {name}
            FOR EACH STATEMENT
            EXECUTE FUNCTION data14_reject_mutation()
            """
        )


def downgrade() -> None:
    non_empty_tables = _non_empty_data14_tables()

    if non_empty_tables:
        raise RuntimeError(
            "DATA-1.4 downgrade refused because durable "
            "history exists in: "
            + ", ".join(non_empty_tables)
        )

    for name in TABLES:
        op.execute(
            f"DROP TRIGGER IF EXISTS "
            f"data14_{name}_immutable ON {name}"
        )
        op.execute(
            f"DROP TRIGGER IF EXISTS "
            f"data14_{name}_no_truncate ON {name}"
        )

    op.execute(
        "DROP FUNCTION IF EXISTS data14_reject_mutation()"
    )

    for name in reversed(TABLES):
        op.drop_table(name)

    op.drop_constraint(
        "uq_catalogue_version_records_record_semantic",
        "catalogue_version_records",
        type_="unique",
    )
    op.drop_constraint(
        "uq_instrument_version_records_record_semantic",
        "instrument_version_records",
        type_="unique",
    )
    op.drop_constraint(
        "uq_provider_mapping_records_record_semantic",
        "provider_mapping_records",
        type_="unique",
    )
