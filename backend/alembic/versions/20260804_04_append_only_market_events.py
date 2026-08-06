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
        # Step 5 binds these three IDs to temporal-record composite FKs.
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
            "AND resolution_market_as_of IS NOT NULL "
            "AND resolution_known_as_of IS NOT NULL"
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


def upgrade() -> None:
    for name in TABLES:
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

        if name == "provider_lifecycle_observations":
            columns += [
                sa.Column(
                    "raw_event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "lifecycle_kind",
                    sa.String(32),
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
