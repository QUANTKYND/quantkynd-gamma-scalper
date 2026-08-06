from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.postgres.base import Base


ID_LENGTH = 71
NAME_LENGTH = 128
KEY_LENGTH = 512
HASH_LENGTH = 128
DECIMAL_TYPE = Numeric(38, 18)


RAW_MARKET_FRAMES_TABLE = Table(
    "raw_market_frames",
    Base.metadata,
    Column("raw_event_id", String(ID_LENGTH), primary_key=True),
    Column("provider", String(NAME_LENGTH), nullable=False),
    Column("provider_schema_id", String(KEY_LENGTH), nullable=False),
    Column("provider_schema_sha256", String(64), nullable=False),
    Column("connection_session_id", String(KEY_LENGTH), nullable=False),
    Column("source_order_scope_id", String(KEY_LENGTH), nullable=False),
    Column("source_order", BigInteger, nullable=False),
    Column("frame_bytes", LargeBinary, nullable=False),
    Column("frame_content_hash", String(ID_LENGTH), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=True),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("capture_basis", String(64), nullable=False),
    Column("source_file_id", String(KEY_LENGTH), nullable=True),
    Column("source_record_id", String(KEY_LENGTH), nullable=True),
    Column("persistence_recorded_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="raw_market_frames_id_sha256",
    ),
    CheckConstraint("provider = 'upstox'", name="raw_market_frames_provider"),
    CheckConstraint(
        "octet_length(provider_schema_id) BETWEEN 1 AND 512",
        name="raw_market_frames_schema_id_bytes",
    ),
    CheckConstraint(
        "provider_schema_sha256 ~ '^[0-9a-f]{64}$'",
        name="raw_market_frames_schema_sha256",
    ),
    CheckConstraint(
        "octet_length(connection_session_id) BETWEEN 1 AND 512",
        name="raw_market_frames_connection_bytes",
    ),
    CheckConstraint(
        "octet_length(source_order_scope_id) BETWEEN 1 AND 512",
        name="raw_market_frames_scope_bytes",
    ),
    CheckConstraint(
        "source_order BETWEEN 0 AND 9223372036854775807",
        name="raw_market_frames_source_order",
    ),
    CheckConstraint(
        "octet_length(frame_bytes) BETWEEN 1 AND 16777216",
        name="raw_market_frames_frame_bytes",
    ),
    CheckConstraint(
        "frame_content_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="raw_market_frames_content_sha256",
    ),
    CheckConstraint(
        "received_at IS NULL OR "
        "(received_at <> 'infinity'::timestamptz "
        "AND received_at <> '-infinity'::timestamptz)",
        name="raw_market_frames_received_finite",
    ),
    CheckConstraint(
        "available_at <> 'infinity'::timestamptz "
        "AND available_at <> '-infinity'::timestamptz",
        name="raw_market_frames_available_finite",
    ),
    CheckConstraint(
        "recorded_at <> 'infinity'::timestamptz "
        "AND recorded_at <> '-infinity'::timestamptz",
        name="raw_market_frames_recorded_finite",
    ),
    CheckConstraint(
        "persistence_recorded_at <> 'infinity'::timestamptz "
        "AND persistence_recorded_at <> '-infinity'::timestamptz",
        name="raw_market_frames_persistence_finite",
    ),
    CheckConstraint(
        "recorded_at >= available_at",
        name="raw_market_frames_recorded_after_available",
    ),
    CheckConstraint(
        "received_at IS NULL OR available_at >= received_at",
        name="raw_market_frames_available_after_received",
    ),
    CheckConstraint(
        "capture_basis IN "
        "('live_received', 'recorded_with_original_receipt', 'historical_import')",
        name="raw_market_frames_capture_basis",
    ),
    CheckConstraint(
        "("
        "capture_basis IN ('live_received', 'recorded_with_original_receipt') "
        "AND received_at IS NOT NULL "
        "AND available_at = received_at"
        ") OR ("
        "capture_basis = 'historical_import' "
        "AND received_at IS NULL"
        ")",
        name="raw_market_frames_capture_clock_shape",
    ),
    CheckConstraint(
        "(source_file_id IS NULL) = (source_record_id IS NULL)",
        name="raw_market_frames_source_pair",
    ),
    CheckConstraint(
        "source_file_id IS NULL OR "
        "octet_length(source_file_id) BETWEEN 1 AND 512",
        name="raw_market_frames_source_file_bytes",
    ),
    CheckConstraint(
        "source_record_id IS NULL OR "
        "octet_length(source_record_id) BETWEEN 1 AND 512",
        name="raw_market_frames_source_record_bytes",
    ),
    UniqueConstraint(
        "provider",
        "provider_schema_id",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        name="uq_raw_market_frames_capture_identity",
    ),
    Index(
        "ix_raw_market_frames_capture_order",
        "provider",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        "raw_event_id",
    ),
    Index("ix_raw_market_frames_content_hash", "frame_content_hash"),
    Index(
        "ix_raw_market_frames_persistence_order",
        "persistence_recorded_at",
        "raw_event_id",
    ),
)


MARKET_NORMALIZATION_RESULTS_TABLE = Table(
    "market_normalization_results",
    Base.metadata,
    Column("result_id", String(ID_LENGTH), primary_key=True),
    Column(
        "raw_event_id",
        String(ID_LENGTH),
        ForeignKey("raw_market_frames.raw_event_id", ondelete="NO ACTION"),
        nullable=False,
    ),
    Column("normalization_schema_version", Integer, nullable=False),
    Column("normalizer_implementation_version", String(NAME_LENGTH), nullable=False),
    Column("response_type", String(32), nullable=True),
    Column("status", String(16), nullable=False),
    Column("decoded_entry_count", Integer, nullable=False),
    Column("accepted_entry_count", Integer, nullable=False),
    Column("failed_entry_count", Integer, nullable=False),
    Column("frame_failure_present", Boolean, nullable=False),
    Column("unadopted_schema_paths", ARRAY(String(KEY_LENGTH)), nullable=False),
    Column(
        "present_unadopted_message_paths",
        ARRAY(String(KEY_LENGTH)),
        nullable=False,
    ),
    Column(
        "secondary_payload_paths_present",
        ARRAY(String(KEY_LENGTH)),
        nullable=False,
    ),
    Column("full_result_hash", String(ID_LENGTH), nullable=False),
    Column("adopted_semantics_hash", String(ID_LENGTH), nullable=False),
    Column("metadata_payload", JSONB, nullable=False),
    Column("persistence_recorded_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "result_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_normalization_results_id_sha256",
    ),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_normalization_results_raw_sha256",
    ),
    CheckConstraint(
        "normalization_schema_version = 1 "
        "AND normalizer_implementation_version = 'upstox-v3-normalizer-1'",
        name="market_normalization_results_schema_label",
    ),
    CheckConstraint(
        "response_type IS NULL OR "
        "response_type IN ('initial_feed', 'live_feed', 'market_info')",
        name="market_normalization_results_response_type",
    ),
    CheckConstraint(
        "status IN ('complete', 'partial', 'failed')",
        name="market_normalization_results_status",
    ),
    CheckConstraint(
        "decoded_entry_count BETWEEN 0 AND 5000 "
        "AND accepted_entry_count BETWEEN 0 AND 5000 "
        "AND failed_entry_count BETWEEN 0 AND 5000",
        name="market_normalization_results_count_bounds",
    ),
    CheckConstraint(
        "("
        "frame_failure_present "
        "AND status = 'failed' "
        "AND accepted_entry_count = 0 "
        "AND failed_entry_count = 0"
        ") OR ("
        "NOT frame_failure_present "
        "AND decoded_entry_count = accepted_entry_count + failed_entry_count "
        "AND ("
        "(status = 'complete' AND accepted_entry_count > 0 AND failed_entry_count = 0) "
        "OR "
        "(status = 'partial' AND accepted_entry_count > 0 AND failed_entry_count > 0) "
        "OR "
        "(status = 'failed' AND accepted_entry_count = 0)"
        ")"
        ")",
        name="market_normalization_results_status_shape",
    ),
    CheckConstraint(
        "array_position(unadopted_schema_paths, NULL) IS NULL",
        name="market_normalization_results_unadopted_no_null",
    ),
    CheckConstraint(
        "array_position(present_unadopted_message_paths, NULL) IS NULL",
        name="market_normalization_results_present_no_null",
    ),
    CheckConstraint(
        "array_position(secondary_payload_paths_present, NULL) IS NULL",
        name="market_normalization_results_secondary_no_null",
    ),
    CheckConstraint(
        "full_result_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="market_normalization_results_full_sha256",
    ),
    CheckConstraint(
        "adopted_semantics_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="market_normalization_results_adopted_sha256",
    ),
    CheckConstraint(
        "jsonb_typeof(metadata_payload) = 'object'",
        name="market_normalization_results_metadata_object",
    ),
    CheckConstraint(
        "persistence_recorded_at <> 'infinity'::timestamptz "
        "AND persistence_recorded_at <> '-infinity'::timestamptz",
        name="market_normalization_results_persistence_finite",
    ),
    UniqueConstraint(
        "raw_event_id",
        "normalization_schema_version",
        name="uq_market_normalization_results_raw_schema",
    ),
    UniqueConstraint(
        "result_id",
        "raw_event_id",
        name="uq_market_normalization_results_result_raw",
    ),
    Index(
        "ix_market_normalization_results_schema_raw",
        "normalization_schema_version",
        "raw_event_id",
    ),
    Index(
        "ix_market_normalization_results_persistence",
        "normalization_schema_version",
        "persistence_recorded_at",
        "result_id",
    ),
    Index(
        "ix_market_normalization_results_status",
        "normalization_schema_version",
        "status",
        "result_id",
    ),
)


MARKET_OBSERVATIONS_TABLE = Table(
    "market_observations",
    Base.metadata,
    Column("event_id", String(ID_LENGTH), primary_key=True),
    Column(
        "raw_event_id",
        String(ID_LENGTH),
        ForeignKey("raw_market_frames.raw_event_id", ondelete="NO ACTION"),
        nullable=False,
    ),
    Column("event_type", String(64), nullable=False),
    Column("subject_id", String(ID_LENGTH), nullable=False),
    Column("provider", String(NAME_LENGTH), nullable=False),
    Column("provider_contract_key", String(KEY_LENGTH), nullable=True),
    Column(
        "economic_subject_id",
        String(ID_LENGTH),
        ForeignKey("market_instruments.instrument_id", ondelete="NO ACTION"),
        nullable=True,
    ),
    Column(
        "provider_mapping_id",
        String(ID_LENGTH),
        ForeignKey("provider_contract_mappings.mapping_id", ondelete="NO ACTION"),
        nullable=True,
    ),
    Column(
        "contract_version_id",
        String(ID_LENGTH),
        ForeignKey("instrument_versions.version_id", ondelete="NO ACTION"),
        nullable=True,
    ),
    Column(
        "catalogue_version_id",
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id", ondelete="NO ACTION"),
        nullable=True,
    ),
    Column("provider_mapping_record_id", String(ID_LENGTH), nullable=True),
    Column("contract_version_record_id", String(ID_LENGTH), nullable=True),
    Column("catalogue_version_record_id", String(ID_LENGTH), nullable=True),
    Column("resolution_market_as_of", DateTime(timezone=True), nullable=True),
    Column("resolution_known_as_of", DateTime(timezone=True), nullable=True),
    Column("provider_timestamp", DateTime(timezone=True), nullable=False),
    Column("exchange_timestamp", DateTime(timezone=True), nullable=True),
    Column("received_at", DateTime(timezone=True), nullable=True),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("availability_basis", String(32), nullable=False),
    Column("source_order_scope_id", String(KEY_LENGTH), nullable=False),
    Column("source_order", BigInteger, nullable=False),
    Column("normalization_schema_version", Integer, nullable=False),
    Column("normalizer_implementation_version", String(NAME_LENGTH), nullable=False),
    Column("provider_sequence", BigInteger, nullable=True),
    Column("supersedes_event_id", String(ID_LENGTH), nullable=True),
    Column("payload", JSONB, nullable=False),
    ForeignKeyConstraint(
        ["provider_mapping_record_id", "provider_mapping_id"],
        [
            "provider_mapping_records.record_id",
            "provider_mapping_records.mapping_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_observations_mapping_record_semantic",
    ),
    ForeignKeyConstraint(
        ["contract_version_record_id", "contract_version_id"],
        [
            "instrument_version_records.record_id",
            "instrument_version_records.version_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_observations_contract_record_semantic",
    ),
    ForeignKeyConstraint(
        ["catalogue_version_record_id", "catalogue_version_id"],
        [
            "catalogue_version_records.record_id",
            "catalogue_version_records.catalogue_version_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_observations_catalogue_record_semantic",
    ),
    CheckConstraint(
        "event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_event_sha256",
    ),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_raw_sha256",
    ),
    CheckConstraint(
        "subject_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_subject_sha256",
    ),
    CheckConstraint(
        "event_type IN ("
        "'underlying_quote_observation', "
        "'futures_quote_observation', "
        "'option_quote_observation', "
        "'market_segment_status_observation'"
        ")",
        name="market_observations_event_type",
    ),
    CheckConstraint("provider = 'upstox'", name="market_observations_provider"),
    CheckConstraint(
        "provider_contract_key IS NULL OR ("
        "octet_length(provider_contract_key) BETWEEN 1 AND 512 "
        "AND provider_contract_key = btrim(provider_contract_key) "
        "AND provider_contract_key !~ '[[:cntrl:]]'"
        ")",
        name="market_observations_provider_key_shape",
    ),
    CheckConstraint(
        "economic_subject_id IS NULL OR "
        "economic_subject_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_economic_subject_sha256",
    ),
    CheckConstraint(
        "provider_mapping_id IS NULL OR "
        "provider_mapping_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_mapping_sha256",
    ),
    CheckConstraint(
        "contract_version_id IS NULL OR "
        "contract_version_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_contract_version_sha256",
    ),
    CheckConstraint(
        "catalogue_version_id IS NULL OR "
        "catalogue_version_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_catalogue_sha256",
    ),
    CheckConstraint(
        "provider_mapping_record_id IS NULL OR "
        "provider_mapping_record_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_mapping_record_sha256",
    ),
    CheckConstraint(
        "contract_version_record_id IS NULL OR "
        "contract_version_record_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_contract_record_sha256",
    ),
    CheckConstraint(
        "catalogue_version_record_id IS NULL OR "
        "catalogue_version_record_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_observations_catalogue_record_sha256",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "provider_timestamp <> 'infinity'::timestamptz "
        "AND provider_timestamp <> '-infinity'::timestamptz",
        name="market_observations_provider_timestamp_finite",
    ),
    CheckConstraint(
        "exchange_timestamp IS NULL",
        name="market_observations_exchange_timestamp_absent",
    ),
    CheckConstraint(
        "received_at IS NULL OR "
        "(received_at <> 'infinity'::timestamptz "
        "AND received_at <> '-infinity'::timestamptz)",
        name="market_observations_received_finite",
    ),
    CheckConstraint(
        "available_at <> 'infinity'::timestamptz "
        "AND available_at <> '-infinity'::timestamptz",
        name="market_observations_available_finite",
    ),
    CheckConstraint(
        "recorded_at <> 'infinity'::timestamptz "
        "AND recorded_at <> '-infinity'::timestamptz",
        name="market_observations_recorded_finite",
    ),
    CheckConstraint(
        "resolution_market_as_of IS NULL OR "
        "(resolution_market_as_of <> 'infinity'::timestamptz "
        "AND resolution_market_as_of <> '-infinity'::timestamptz)",
        name="market_observations_resolution_market_finite",
    ),
    CheckConstraint(
        "resolution_known_as_of IS NULL OR "
        "(resolution_known_as_of <> 'infinity'::timestamptz "
        "AND resolution_known_as_of <> '-infinity'::timestamptz)",
        name="market_observations_resolution_known_finite",
    ),
    CheckConstraint(
        "recorded_at >= available_at",
        name="market_observations_recorded_after_available",
    ),
    CheckConstraint(
        "received_at IS NULL OR available_at >= received_at",
        name="market_observations_available_after_received",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "octet_length(source_order_scope_id) BETWEEN 1 AND 512",
        name="market_observations_source_scope_bytes",
    ),
    CheckConstraint(
        "source_order BETWEEN 0 AND 9223372036854775807",
        name="market_observations_source_order",
    ),
    CheckConstraint(
        "normalization_schema_version = 1 "
        "AND normalizer_implementation_version = 'upstox-v3-normalizer-1'",
        name="market_observations_schema_label",
    ),
    CheckConstraint(
        "provider_sequence IS NULL",
        name="market_observations_provider_sequence_absent",
    ),
    CheckConstraint(
        "supersedes_event_id IS NULL",
        name="market_observations_corrections_deferred",
    ),
    CheckConstraint(
        "jsonb_typeof(payload) = 'object'",
        name="market_observations_payload_object",
    ),
    CheckConstraint(
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
    UniqueConstraint(
        "event_id",
        "raw_event_id",
        name="uq_market_observations_event_raw",
    ),
    UniqueConstraint(
        "event_id",
        "event_type",
        "subject_id",
        name="uq_market_observations_event_type_subject",
    ),
    Index(
        "ix_market_observations_subject_provider_time",
        "normalization_schema_version",
        "economic_subject_id",
        "event_type",
        "provider_timestamp",
        "available_at",
        "event_id",
    ),
    Index(
        "ix_market_observations_subject_availability",
        "normalization_schema_version",
        "economic_subject_id",
        "availability_basis",
        "available_at",
        "event_id",
    ),
    Index("ix_market_observations_raw", "raw_event_id", "event_id"),
    Index(
        "ix_market_observations_mapping_provenance",
        "provider_mapping_id",
        "contract_version_id",
        "catalogue_version_id",
        "event_id",
    ),
    Index(
        "ix_market_observations_temporal_provenance",
        "provider_mapping_record_id",
        "contract_version_record_id",
        "catalogue_version_record_id",
        "event_id",
    ),
)


MARKET_NORMALIZATION_RESULT_EVENTS_TABLE = Table(
    "market_normalization_result_events",
    Base.metadata,
    Column("result_id", String(ID_LENGTH), nullable=False),
    Column("raw_event_id", String(ID_LENGTH), nullable=False),
    Column("event_ordinal", Integer, nullable=False),
    Column("event_id", String(ID_LENGTH), nullable=False),
    PrimaryKeyConstraint(
        "result_id",
        "event_ordinal",
        name="pk_market_normalization_result_events",
    ),
    UniqueConstraint(
        "result_id",
        "event_id",
        name="uq_market_normalization_result_events_event",
    ),
    ForeignKeyConstraint(
        ["result_id", "raw_event_id"],
        [
            "market_normalization_results.result_id",
            "market_normalization_results.raw_event_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_result_events_result_raw",
    ),
    ForeignKeyConstraint(
        ["event_id", "raw_event_id"],
        [
            "market_observations.event_id",
            "market_observations.raw_event_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_result_events_event_raw",
    ),
    CheckConstraint(
        "result_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_result_events_result_sha256",
    ),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_result_events_raw_sha256",
    ),
    CheckConstraint(
        "event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_result_events_event_sha256",
    ),
    CheckConstraint(
        "event_ordinal BETWEEN 0 AND 4999",
        name="market_result_events_ordinal",
    ),
    Index(
        "ix_market_normalization_result_events_event",
        "event_id",
        "result_id",
    ),
)


MARKET_NORMALIZATION_FAILURES_TABLE = Table(
    "market_normalization_failures",
    Base.metadata,
    Column("failure_id", String(ID_LENGTH), primary_key=True),
    Column("result_id", String(ID_LENGTH), nullable=False),
    Column("raw_event_id", String(ID_LENGTH), nullable=False),
    Column("scope", String(32), nullable=False),
    Column("reason_code", String(NAME_LENGTH), nullable=False),
    Column("provider_contract_key", String(KEY_LENGTH), nullable=True),
    Column("segment", String(NAME_LENGTH), nullable=True),
    Column("safe_detail_code", String(NAME_LENGTH), nullable=True),
    Column("selected_feed_union", String(64), nullable=True),
    Column("provider_depth_levels_present", Integer, nullable=True),
    Column("field_paths", ARRAY(String(KEY_LENGTH)), nullable=False),
    Column("unadopted_schema_paths", ARRAY(String(KEY_LENGTH)), nullable=False),
    Column(
        "present_unadopted_message_paths",
        ARRAY(String(KEY_LENGTH)),
        nullable=False,
    ),
    Column("payload", JSONB, nullable=False),
    ForeignKeyConstraint(
        ["result_id", "raw_event_id"],
        [
            "market_normalization_results.result_id",
            "market_normalization_results.raw_event_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_failures_result_raw",
    ),
    UniqueConstraint(
        "failure_id",
        "result_id",
        "raw_event_id",
        name="uq_market_failures_failure_result_raw",
    ),
    CheckConstraint(
        "failure_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_failures_failure_sha256",
    ),
    CheckConstraint(
        "result_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_failures_result_sha256",
    ),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_failures_raw_sha256",
    ),
    CheckConstraint(
        "scope IN ('frame', 'subject', 'segment')",
        name="market_failures_scope",
    ),
    CheckConstraint(
        "octet_length(reason_code) BETWEEN 1 AND 128 "
        "AND reason_code ~ '^[A-Za-z0-9_]+$'",
        name="market_failures_reason_shape",
    ),
    CheckConstraint(
        "safe_detail_code IS NULL OR ("
        "octet_length(safe_detail_code) BETWEEN 1 AND 128 "
        "AND safe_detail_code ~ '^[A-Za-z0-9_]+$'"
        ")",
        name="market_failures_safe_detail_shape",
    ),
    CheckConstraint(
        "provider_contract_key IS NULL OR ("
        "octet_length(provider_contract_key) BETWEEN 1 AND 512 "
        "AND provider_contract_key = btrim(provider_contract_key) "
        "AND provider_contract_key !~ '[[:cntrl:]]'"
        ")",
        name="market_failures_provider_key_shape",
    ),
    CheckConstraint(
        "segment IS NULL OR ("
        "octet_length(segment) BETWEEN 1 AND 128 "
        "AND segment = btrim(segment) "
        "AND segment !~ '[[:cntrl:]]'"
        ")",
        name="market_failures_segment_shape",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "selected_feed_union IS NULL OR "
        "selected_feed_union IN "
        "('ltpc', 'indexFF', 'marketFF', 'firstLevelWithGreeks')",
        name="market_failures_selected_union",
    ),
    CheckConstraint(
        "provider_depth_levels_present IS NULL OR "
        "provider_depth_levels_present BETWEEN 0 AND 30",
        name="market_failures_depth",
    ),
    CheckConstraint(
        "array_position(field_paths, NULL) IS NULL "
        "AND cardinality(field_paths) <= 5000",
        name="market_failures_field_paths",
    ),
    CheckConstraint(
        "array_position(unadopted_schema_paths, NULL) IS NULL "
        "AND cardinality(unadopted_schema_paths) <= 5000",
        name="market_failures_unadopted_paths",
    ),
    CheckConstraint(
        "array_position(present_unadopted_message_paths, NULL) IS NULL "
        "AND cardinality(present_unadopted_message_paths) <= 5000",
        name="market_failures_present_paths",
    ),
    CheckConstraint(
        "jsonb_typeof(payload) = 'object'",
        name="market_failures_payload_object",
    ),
    Index(
        "ix_market_normalization_failures_result_scope",
        "result_id",
        "scope",
        "failure_id",
    ),
    Index(
        "ix_market_normalization_failures_reason",
        "reason_code",
        "failure_id",
    ),
)


MARKET_NORMALIZATION_RESULT_FAILURES_TABLE = Table(
    "market_normalization_result_failures",
    Base.metadata,
    Column("result_id", String(ID_LENGTH), nullable=False),
    Column("raw_event_id", String(ID_LENGTH), nullable=False),
    Column("failure_role", String(16), nullable=False),
    Column("failure_ordinal", Integer, nullable=False),
    Column("failure_id", String(ID_LENGTH), nullable=False),
    PrimaryKeyConstraint(
        "result_id",
        "failure_role",
        "failure_ordinal",
        name="pk_market_normalization_result_failures",
    ),
    UniqueConstraint(
        "result_id",
        "raw_event_id",
        "failure_role",
        "failure_ordinal",
        name="uq_market_result_failures_result_raw_role_ordinal",
    ),
    ForeignKeyConstraint(
        ["result_id", "raw_event_id"],
        [
            "market_normalization_results.result_id",
            "market_normalization_results.raw_event_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_result_failures_result_raw",
    ),
    ForeignKeyConstraint(
        ["failure_id", "result_id", "raw_event_id"],
        [
            "market_normalization_failures.failure_id",
            "market_normalization_failures.result_id",
            "market_normalization_failures.raw_event_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_result_failures_failure_result_raw",
    ),
    CheckConstraint(
        "result_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_result_failures_result_sha256",
    ),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_result_failures_raw_sha256",
    ),
    CheckConstraint(
        "failure_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_result_failures_failure_sha256",
    ),
    CheckConstraint(
        "failure_role IN ('frame', 'entry')",
        name="market_result_failures_role",
    ),
    CheckConstraint(
        "failure_ordinal BETWEEN 0 AND 4999",
        name="market_result_failures_ordinal",
    ),
    Index(
        "uq_market_normalization_result_failures_one_frame",
        "result_id",
        unique=True,
        postgresql_where=text("failure_role = 'frame'"),
    ),
    Index(
        "ix_market_normalization_result_failures_failure",
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


def _quote_subtype_table(
    table_name: str,
    event_type: str,
    feed_shape: str,
) -> Table:
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

    return Table(
        table_name,
        Base.metadata,
        Column("event_id", String(ID_LENGTH), primary_key=True),
        Column("event_type", String(64), nullable=False),
        Column("subject_id", String(ID_LENGTH), nullable=False),
        Column("feed_response_type", String(32), nullable=False),
        Column("request_mode", String(32), nullable=False),
        Column("feed_union", String(64), nullable=False),
        Column("is_snapshot", Boolean, nullable=False),
        Column("presence_semantics", String(64), nullable=False),
        Column("numeric_basis", String(64), nullable=False),
        Column("quantity_basis", String(64), nullable=False),
        Column("bid_price", DECIMAL_TYPE, nullable=True),
        Column("bid_size", BigInteger, nullable=True),
        Column("ask_price", DECIMAL_TYPE, nullable=True),
        Column("ask_size", BigInteger, nullable=True),
        Column("last_price", DECIMAL_TYPE, nullable=True),
        Column("last_size", BigInteger, nullable=True),
        Column(
            "last_trade_at",
            DateTime(timezone=True),
            nullable=True,
        ),
        Column(
            "previous_close_price",
            DECIMAL_TYPE,
            nullable=True,
        ),
        Column("reported_volume", BigInteger, nullable=True),
        Column("open_interest", BigInteger, nullable=True),
        Column(
            "provider_depth_levels_present",
            Integer,
            nullable=False,
        ),
        Column(
            "normalized_depth_levels",
            Integer,
            nullable=False,
        ),
        Column(
            "unadopted_depth_level_count",
            Integer,
            nullable=False,
        ),
        Column(
            "unadopted_schema_paths",
            ARRAY(String(KEY_LENGTH)),
            nullable=False,
        ),
        Column(
            "present_unadopted_message_paths",
            ARRAY(String(KEY_LENGTH)),
            nullable=False,
        ),
        Column(
            "secondary_payload_paths_present",
            ARRAY(String(KEY_LENGTH)),
            nullable=False,
        ),
        ForeignKeyConstraint(
            ["event_id", "event_type", "subject_id"],
            [
                "market_observations.event_id",
                "market_observations.event_type",
                "market_observations.subject_id",
            ],
            ondelete="NO ACTION",
            name=f"fk_{table_name}_event_type_subject",
        ),
        CheckConstraint(
            "event_id ~ '^sha256:[0-9a-f]{64}$'",
            name=f"{table_name}_event_sha256",
        ),
        CheckConstraint(
            "subject_id ~ '^sha256:[0-9a-f]{64}$'",
            name=f"{table_name}_subject_sha256",
        ),
        CheckConstraint(
            f"event_type = '{event_type}'",
            name=f"{table_name}_event_type",
        ),
        CheckConstraint(
            "feed_response_type IN ('initial_feed', 'live_feed')",
            name=f"{table_name}_response_type",
        ),
        CheckConstraint(
            "request_mode IN "
            "('ltpc', 'full_d5', 'option_greeks', 'full_d30')",
            name=f"{table_name}_request_mode",
        ),
        CheckConstraint(
            "feed_union IN "
            "('ltpc', 'indexFF', 'marketFF', "
            "'firstLevelWithGreeks')",
            name=f"{table_name}_feed_union",
        ),
        CheckConstraint(
            "(feed_response_type = 'initial_feed' AND is_snapshot) "
            "OR (feed_response_type = 'live_feed' AND NOT is_snapshot)",
            name=f"{table_name}_snapshot_shape",
        ),
        CheckConstraint(
            "presence_semantics = 'proto3_parent_implied_v1' "
            "AND numeric_basis = "
            "'protobuf_double_roundtrip_decimal_v1' "
            "AND quantity_basis = 'upstox_reported_quantity_v1'",
            name=f"{table_name}_semantic_basis",
        ),
        CheckConstraint(
            finite_nonnegative_prices,
            name=f"{table_name}_price_shape",
        ),
        CheckConstraint(
            quantity_bounds,
            name=f"{table_name}_quantity_shape",
        ),
        CheckConstraint(
            "open_interest IS NULL OR "
            "open_interest BETWEEN 0 AND 9007199254740992",
            name=f"{table_name}_open_interest",
        ),
        CheckConstraint(
            "last_trade_at IS NULL OR ("
            "last_trade_at <> 'infinity'::timestamptz "
            "AND last_trade_at <> '-infinity'::timestamptz"
            ")",
            name=f"{table_name}_last_trade_finite",
        ),
        CheckConstraint(
            "provider_depth_levels_present BETWEEN 0 AND 30 "
            "AND normalized_depth_levels IN (0, 1) "
            "AND unadopted_depth_level_count BETWEEN 0 AND 30 "
            "AND unadopted_depth_level_count = "
            "provider_depth_levels_present - normalized_depth_levels",
            name=f"{table_name}_depth_reconciliation",
        ),
        CheckConstraint(
            feed_shape,
            name=f"{table_name}_feed_shape",
        ),
        CheckConstraint(
            "array_position(unadopted_schema_paths, NULL) IS NULL "
            "AND cardinality(unadopted_schema_paths) <= 5000",
            name=f"{table_name}_unadopted_paths",
        ),
        CheckConstraint(
            "array_position("
            "present_unadopted_message_paths, NULL"
            ") IS NULL "
            "AND cardinality("
            "present_unadopted_message_paths"
            ") <= 5000",
            name=f"{table_name}_present_paths",
        ),
        CheckConstraint(
            "array_position("
            "secondary_payload_paths_present, NULL"
            ") IS NULL "
            "AND cardinality("
            "secondary_payload_paths_present"
            ") <= 5000",
            name=f"{table_name}_secondary_paths",
        ),
        Index(
            f"ix_{table_name}_mode_union",
            "request_mode",
            "feed_union",
            "event_id",
        ),
    )


UNDERLYING_QUOTE_OBSERVATIONS_TABLE = _quote_subtype_table(
    "underlying_quote_observations",
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

FUTURES_QUOTE_OBSERVATIONS_TABLE = _quote_subtype_table(
    "futures_quote_observations",
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
    "WHEN provider_depth_levels_present > 0 THEN 1 ELSE 0 END)",
)

OPTION_QUOTE_OBSERVATIONS_TABLE = _quote_subtype_table(
    "option_quote_observations",
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
    "WHEN provider_depth_levels_present > 0 THEN 1 ELSE 0 END) "
    "OR (feed_union = 'firstLevelWithGreeks' "
    "AND request_mode = 'option_greeks' "
    "AND provider_depth_levels_present IN (0, 1) "
    "AND normalized_depth_levels = provider_depth_levels_present)",
)


MARKET_SEGMENT_STATUS_OBSERVATIONS_TABLE = Table(
    "market_segment_status_observations",
    Base.metadata,
    Column("event_id", String(ID_LENGTH), primary_key=True),
    Column("event_type", String(64), nullable=False),
    Column("subject_id", String(ID_LENGTH), nullable=False),
    Column("segment", String(NAME_LENGTH), nullable=False),
    Column("provider_status_name", String(NAME_LENGTH), nullable=False),
    Column("provider_status_numeric", Integer, nullable=False),
    Column("status_is_known", Boolean, nullable=False),
    ForeignKeyConstraint(
        ["event_id", "event_type", "subject_id"],
        [
            "market_observations.event_id",
            "market_observations.event_type",
            "market_observations.subject_id",
        ],
        ondelete="NO ACTION",
        name="fk_market_segment_status_event_type_subject",
    ),
    CheckConstraint(
        "event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_segment_status_event_sha256",
    ),
    CheckConstraint(
        "subject_id ~ '^sha256:[0-9a-f]{64}$'",
        name="market_segment_status_subject_sha256",
    ),
    CheckConstraint(
        "event_type = 'market_segment_status_observation'",
        name="market_segment_status_event_type",
    ),
    CheckConstraint(
        "octet_length(segment) BETWEEN 1 AND 128 "
        "AND segment = btrim(segment) "
        "AND segment !~ '[[:cntrl:]]'",
        name="market_segment_status_segment_shape",
    ),
    CheckConstraint(
        "octet_length(provider_status_name) BETWEEN 1 AND 128 "
        "AND provider_status_name ~ '^[A-Z0-9_]+$'",
        name="market_segment_status_name_shape",
    ),
    CheckConstraint(
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
    Index(
        "ix_market_segment_status_segment_code",
        "segment",
        "provider_status_numeric",
        "event_id",
    ),
)


PROVIDER_SUBSCRIPTION_INSTRUMENT_SETS_TABLE = Table(
    "provider_subscription_instrument_sets",
    Base.metadata,
    Column(
        "instrument_keys_digest",
        String(ID_LENGTH),
        primary_key=True,
    ),
    Column(
        "instrument_key_count",
        Integer,
        nullable=False,
    ),
    Column(
        "provider_contract_keys",
        JSONB,
        nullable=False,
    ),
    Column(
        "canonical_payload_hash",
        String(ID_LENGTH),
        nullable=False,
    ),
    CheckConstraint(
        "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="instrument_sets_digest_sha256",
    ),
    CheckConstraint(
        "instrument_key_count BETWEEN 1 AND 5000",
        name="instrument_sets_count_bounds",
    ),
    CheckConstraint(
        "jsonb_typeof(provider_contract_keys) = 'array'",
        name="instrument_sets_payload_array",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="instrument_sets_payload_hash_sha256",
    ),
    CheckConstraint(
        "canonical_payload_hash = instrument_keys_digest",
        name="instrument_sets_payload_hash_identity",
    ),
)


PROVIDER_LIFECYCLE_BATCHES_TABLE = Table(
    "provider_lifecycle_batches",
    Base.metadata,
    Column(
        "lifecycle_batch_id",
        String(ID_LENGTH),
        primary_key=True,
    ),
    Column(
        "lifecycle_kind",
        String(32),
        nullable=False,
    ),
    Column(
        "provider",
        String(NAME_LENGTH),
        nullable=False,
    ),
    Column(
        "normalization_schema_version",
        Integer,
        nullable=False,
    ),
    Column(
        "normalizer_implementation_version",
        String(NAME_LENGTH),
        nullable=False,
    ),
    Column(
        "input_count",
        Integer,
        nullable=False,
    ),
    Column(
        "unique_count",
        Integer,
        nullable=False,
    ),
    Column(
        "normalized_count",
        Integer,
        nullable=False,
    ),
    Column(
        "duplicate_count",
        Integer,
        nullable=False,
    ),
    Column(
        "batch_hash",
        String(ID_LENGTH),
        nullable=False,
    ),
    Column(
        "normalized_sequence_hash",
        String(ID_LENGTH),
        nullable=False,
    ),
    Column(
        "metadata_payload",
        JSONB,
        nullable=False,
    ),
    Column(
        "persistence_recorded_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    UniqueConstraint(
        "lifecycle_batch_id",
        "lifecycle_kind",
        name="uq_provider_lifecycle_batches_id_kind",
    ),
    CheckConstraint(
        "lifecycle_batch_id ~ '^sha256:[0-9a-f]{64}$'",
        name="provider_lifecycle_batches_id_sha256",
    ),
    CheckConstraint(
        "lifecycle_kind IN ('connection', 'subscription')",
        name="provider_lifecycle_batches_kind",
    ),
    CheckConstraint(
        "provider = 'upstox'",
        name="provider_lifecycle_batches_provider",
    ),
    CheckConstraint(
        "normalization_schema_version = 1 "
        "AND normalizer_implementation_version = "
        "'upstox-v3-normalizer-1'",
        name="provider_lifecycle_batches_schema_label",
    ),
    CheckConstraint(
        "input_count BETWEEN 0 AND 10000 "
        "AND unique_count BETWEEN 0 AND 10000 "
        "AND normalized_count BETWEEN 0 AND 10000 "
        "AND duplicate_count BETWEEN 0 AND 10000",
        name="provider_lifecycle_batches_count_bounds",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "batch_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="provider_lifecycle_batches_batch_hash",
    ),
    CheckConstraint(
        "normalized_sequence_hash "
        "~ '^sha256:[0-9a-f]{64}$'",
        name="provider_lifecycle_batches_sequence_hash",
    ),
    CheckConstraint(
        "jsonb_typeof(metadata_payload) = 'object'",
        name="provider_lifecycle_batches_metadata_object",
    ),
    CheckConstraint(
        "persistence_recorded_at "
        "<> 'infinity'::timestamptz "
        "AND persistence_recorded_at "
        "<> '-infinity'::timestamptz",
        name="provider_lifecycle_batches_persistence_finite",
    ),
    Index(
        "ix_provider_lifecycle_batches_acceptance",
        "normalization_schema_version",
        "provider",
        "lifecycle_kind",
        "persistence_recorded_at",
        "lifecycle_batch_id",
    ),
)


PROVIDER_SUBSCRIPTION_INSTRUMENT_SET_KEYS_TABLE = Table(
    "provider_subscription_instrument_set_keys",
    Base.metadata,
    Column(
        "instrument_keys_digest",
        String(ID_LENGTH),
        nullable=False,
    ),
    Column(
        "key_ordinal",
        Integer,
        nullable=False,
    ),
    Column(
        "provider_contract_key",
        String(KEY_LENGTH),
        nullable=False,
    ),
    PrimaryKeyConstraint(
        "instrument_keys_digest",
        "key_ordinal",
        name="pk_provider_subscription_instrument_set_keys",
    ),
    UniqueConstraint(
        "instrument_keys_digest",
        "provider_contract_key",
        name="uq_instrument_set_keys_digest_key",
    ),
    ForeignKeyConstraint(
        ["instrument_keys_digest"],
        [
            "provider_subscription_instrument_sets."
            "instrument_keys_digest"
        ],
        ondelete="NO ACTION",
        onupdate="NO ACTION",
        name="fk_instrument_set_keys_set",
    ),
    CheckConstraint(
        "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="instrument_set_keys_digest_sha256",
    ),
    CheckConstraint(
        "key_ordinal BETWEEN 0 AND 4999",
        name="instrument_set_keys_ordinal_bounds",
    ),
    CheckConstraint(
        """
        octet_length(provider_contract_key) BETWEEN 1 AND 512
        AND provider_contract_key = btrim(provider_contract_key)
        AND provider_contract_key !~ '[[:cntrl:]]'
        """,
        name="instrument_set_keys_provider_key_shape",
    ),
)


RAW_PROVIDER_LIFECYCLE_EVENTS_TABLE = Table(
    "raw_provider_lifecycle_events",
    Base.metadata,
    Column(
        "raw_event_id",
        String(ID_LENGTH),
        primary_key=True,
    ),
    Column(
        "lifecycle_kind",
        String(32),
        nullable=False,
    ),
    Column(
        "provider",
        String(NAME_LENGTH),
        nullable=False,
    ),
    Column(
        "connection_session_id",
        String(KEY_LENGTH),
        nullable=False,
    ),
    Column(
        "subscription_scope_id",
        String(KEY_LENGTH),
        nullable=True,
    ),
    Column(
        "previous_state",
        String(32),
        nullable=True,
    ),
    Column(
        "state",
        String(32),
        nullable=False,
    ),
    Column(
        "source_order_scope_id",
        String(KEY_LENGTH),
        nullable=False,
    ),
    Column(
        "source_order",
        BigInteger,
        nullable=False,
    ),
    Column(
        "occurred_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column(
        "available_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column(
        "recorded_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column(
        "request_mode",
        String(32),
        nullable=True,
    ),
    Column(
        "instrument_keys_digest",
        String(ID_LENGTH),
        ForeignKey(
            "provider_subscription_instrument_sets."
            "instrument_keys_digest",
            ondelete="NO ACTION",
            onupdate="NO ACTION",
        ),
        nullable=True,
    ),
    Column(
        "instrument_key_count",
        Integer,
        nullable=True,
    ),
    Column(
        "redacted_reason_code",
        String(NAME_LENGTH),
        nullable=True,
    ),
    Column(
        "provider_sequence",
        BigInteger,
        nullable=True,
    ),
    Column(
        "payload",
        JSONB,
        nullable=False,
    ),
    UniqueConstraint(
        "raw_event_id",
        "lifecycle_kind",
        name="uq_raw_provider_lifecycle_events_id_kind",
    ),
    CheckConstraint(
        "raw_event_id ~ '^sha256:[0-9a-f]{64}$'",
        name="raw_provider_lifecycle_events_id_sha256",
    ),
    CheckConstraint(
        "lifecycle_kind IN ('connection', 'subscription')",
        name="raw_provider_lifecycle_events_kind",
    ),
    CheckConstraint(
        "provider = 'upstox'",
        name="raw_provider_lifecycle_events_provider",
    ),
    CheckConstraint(
        "octet_length(connection_session_id) BETWEEN 1 AND 512 "
        "AND connection_session_id ~ '[^[:space:]]'",
        name="raw_provider_lifecycle_events_connection_bytes",
    ),
    CheckConstraint(
        "octet_length(source_order_scope_id) BETWEEN 1 AND 512 "
        "AND source_order_scope_id ~ '[^[:space:]]'",
        name="raw_provider_lifecycle_events_source_scope_bytes",
    ),
    CheckConstraint(
        "subscription_scope_id IS NULL OR ("
        "octet_length(subscription_scope_id) BETWEEN 1 AND 512 "
        "AND subscription_scope_id ~ '[^[:space:]]'"
        ")",
        name="raw_provider_lifecycle_events_subscription_scope_bytes",
    ),
    CheckConstraint(
        "source_order BETWEEN 0 AND 9223372036854775807",
        name="raw_provider_lifecycle_events_source_order",
    ),
    CheckConstraint(
        "occurred_at <> 'infinity'::timestamptz "
        "AND occurred_at <> '-infinity'::timestamptz",
        name="raw_provider_lifecycle_events_occurred_finite",
    ),
    CheckConstraint(
        "available_at <> 'infinity'::timestamptz "
        "AND available_at <> '-infinity'::timestamptz",
        name="raw_provider_lifecycle_events_available_finite",
    ),
    CheckConstraint(
        "recorded_at <> 'infinity'::timestamptz "
        "AND recorded_at <> '-infinity'::timestamptz",
        name="raw_provider_lifecycle_events_recorded_finite",
    ),
    CheckConstraint(
        "available_at >= occurred_at "
        "AND recorded_at >= available_at",
        name="raw_provider_lifecycle_events_clock_order",
    ),
    CheckConstraint(
        "request_mode IS NULL OR "
        "request_mode IN ("
        "'ltpc', 'option_greeks', 'full_d5', 'full_d30'"
        ")",
        name="raw_provider_lifecycle_events_request_mode",
    ),
    CheckConstraint(
        "instrument_keys_digest IS NULL OR "
        "instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="raw_provider_lifecycle_events_instrument_digest",
    ),
    CheckConstraint(
        "instrument_key_count IS NULL OR "
        "instrument_key_count BETWEEN 1 AND 5000",
        name="raw_provider_lifecycle_events_instrument_count",
    ),
    CheckConstraint(
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
    CheckConstraint(
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
    CheckConstraint(
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
    CheckConstraint(
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
    CheckConstraint(
        "redacted_reason_code IS NULL OR ("
        "octet_length(redacted_reason_code) BETWEEN 1 AND 128 "
        "AND redacted_reason_code "
        "~ '^[a-z0-9]+(_[a-z0-9]+)*$' "
        "AND redacted_reason_code "
        "!~ '(token|url|traceback|socket|account|user_id|exception)'"
        ")",
        name="raw_provider_lifecycle_events_reason_format",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "provider_sequence IS NULL",
        name="raw_provider_lifecycle_events_provider_sequence",
    ),
    CheckConstraint(
        "jsonb_typeof(payload) = 'object'",
        name="raw_provider_lifecycle_events_payload_object",
    ),
    Index(
        "ix_raw_provider_lifecycle_events_scope_order",
        "provider",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        "raw_event_id",
    ),
    Index(
        "ix_raw_provider_lifecycle_events_subscription_scope",
        "provider",
        "connection_session_id",
        "subscription_scope_id",
        "source_order",
        "raw_event_id",
        postgresql_where=text(
            "lifecycle_kind = 'subscription'"
        ),
    ),
)


DATA14_PLACEHOLDER_TABLE_COLUMNS = {
    "provider_lifecycle_observations": (
        Column(
            "raw_event_id",
            String(ID_LENGTH),
            nullable=False,
        ),
        Column(
            "lifecycle_kind",
            String(32),
            nullable=False,
        ),
    ),
}

DATA14_REMAINING_PLACEHOLDER_TABLES = (
    "provider_lifecycle_batch_events",
    "provider_lifecycle_observations",
    "provider_connection_lifecycle_observations",
    "provider_subscription_lifecycle_observations",
    "provider_lifecycle_batch_observations",
)

for _data14_table in DATA14_REMAINING_PLACEHOLDER_TABLES:
    Table(
        _data14_table,
        Base.metadata,
        Column(
            "id",
            String(ID_LENGTH),
            primary_key=True,
        ),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
        ),
        *DATA14_PLACEHOLDER_TABLE_COLUMNS.get(
            _data14_table,
            (),
        ),
    )


def _temporal_record_constraints(
    table_name: str,
    semantic_column: str,
) -> tuple:
    return (
        CheckConstraint(
            "char_length(record_id) > 0",
            name=f"{table_name}_record_id_nonempty",
        ),
        CheckConstraint(
            "char_length(scope_id) > 0",
            name=f"{table_name}_scope_id_nonempty",
        ),
        CheckConstraint(
            "supersedes_record_id IS NULL "
            "OR supersedes_record_id <> record_id",
            name=f"{table_name}_not_self_superseding",
        ),
        Index(f"ix_{table_name}_semantic", semantic_column),
        Index(f"ix_{table_name}_recorded", "recorded_at"),
        Index(f"ix_{table_name}_successor", "supersedes_record_id"),
        Index(
            f"uq_{table_name}_one_successor",
            "supersedes_record_id",
            unique=True,
            postgresql_where=text("supersedes_record_id IS NOT NULL"),
        ),
    )


class CatalogueVersionRow(Base):
    __tablename__ = "catalogue_versions"
    __table_args__ = (
        CheckConstraint(
            "char_length(catalogue_version_id) > 0",
            name="catalogue_version_id_nonempty",
        ),
        CheckConstraint(
            "char_length(provider) > 0",
            name="catalogue_provider_nonempty",
        ),
        CheckConstraint(
            "char_length(source_content_hash) > 0",
            name="catalogue_hash_nonempty",
        ),
        CheckConstraint(
            "catalogue_schema_version > 0",
            name="catalogue_schema_version_positive",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="catalogue_effective_interval",
        ),
        CheckConstraint(
            "row_count >= 0",
            name="catalogue_row_count_nonnegative",
        ),
        Index(
            "ix_catalogue_versions_provider_effective",
            "provider",
            "effective_from",
        ),
    )

    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    source_content_hash: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    catalogue_schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)


class MarketInstrumentRow(Base):
    __tablename__ = "market_instruments"
    __table_args__ = (
        CheckConstraint(
            "char_length(instrument_id) > 0",
            name="market_instrument_id_nonempty",
        ),
        CheckConstraint(
            "instrument_kind IN ('underlying', 'future', 'option')",
            name="instrument_kind_supported",
        ),
        CheckConstraint(
            "char_length(exchange) > 0",
            name="market_instrument_exchange_nonempty",
        ),
        CheckConstraint(
            "char_length(currency) > 0",
            name="market_instrument_currency_nonempty",
        ),
        UniqueConstraint("instrument_id", "instrument_kind"),
    )

    instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    instrument_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )


class UnderlyingInstrumentRow(Base):
    __tablename__ = "underlying_instruments"
    __table_args__ = (
        CheckConstraint(
            "instrument_kind = 'underlying'",
            name="underlying_kind",
        ),
        CheckConstraint(
            "char_length(canonical_symbol) > 0",
            name="underlying_symbol_nonempty",
        ),
        CheckConstraint(
            "instrument_type IN ('index', 'equity')",
            name="underlying_type_supported",
        ),
        ForeignKeyConstraint(
            ["instrument_id", "instrument_kind"],
            [
                "market_instruments.instrument_id",
                "market_instruments.instrument_kind",
            ],
        ),
    )

    instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    instrument_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="underlying",
    )
    canonical_symbol: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    instrument_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )


class FuturesContractRow(Base):
    __tablename__ = "futures_contracts"
    __table_args__ = (
        CheckConstraint(
            "instrument_kind = 'future'",
            name="future_kind",
        ),
        CheckConstraint(
            "settlement_type IN ('cash', 'physical')",
            name="future_settlement_supported",
        ),
        CheckConstraint(
            "multiplier > 0",
            name="future_multiplier_positive",
        ),
        ForeignKeyConstraint(
            ["contract_id", "instrument_kind"],
            [
                "market_instruments.instrument_id",
                "market_instruments.instrument_kind",
            ],
        ),
        Index(
            "ix_futures_contracts_underlying_expiry",
            "underlying_instrument_id",
            "expiry",
        ),
    )

    contract_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    instrument_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="future",
    )
    underlying_instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("underlying_instruments.instrument_id"),
        nullable=False,
    )
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    multiplier: Mapped[Decimal] = mapped_column(
        DECIMAL_TYPE,
        nullable=False,
    )


class OptionContractRow(Base):
    __tablename__ = "option_contracts"
    __table_args__ = (
        CheckConstraint(
            "instrument_kind = 'option'",
            name="option_kind",
        ),
        CheckConstraint(
            "strike > 0",
            name="option_strike_positive",
        ),
        CheckConstraint(
            "option_side IN ('call', 'put')",
            name="option_side_supported",
        ),
        CheckConstraint(
            "exercise_style IN ('european')",
            name="option_exercise_supported",
        ),
        CheckConstraint(
            "settlement_type IN ('cash', 'physical')",
            name="option_settlement_supported",
        ),
        CheckConstraint(
            "multiplier > 0",
            name="option_multiplier_positive",
        ),
        ForeignKeyConstraint(
            ["contract_id", "instrument_kind"],
            [
                "market_instruments.instrument_id",
                "market_instruments.instrument_kind",
            ],
        ),
        Index(
            "ix_option_contracts_underlying_expiry",
            "underlying_instrument_id",
            "expiry",
        ),
        Index(
            "ix_option_contracts_expiry_strike_side",
            "expiry",
            "strike",
            "option_side",
        ),
    )

    contract_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    instrument_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="option",
    )
    underlying_instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("underlying_instruments.instrument_id"),
        nullable=False,
    )
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal] = mapped_column(
        DECIMAL_TYPE,
        nullable=False,
    )
    option_side: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )
    exercise_style: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    settlement_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    multiplier: Mapped[Decimal] = mapped_column(
        DECIMAL_TYPE,
        nullable=False,
    )


class InstrumentVersionRow(Base):
    __tablename__ = "instrument_versions"
    __table_args__ = (
        CheckConstraint(
            "char_length(version_id) > 0",
            name="instrument_version_id_nonempty",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="instrument_version_valid_interval",
        ),
        CheckConstraint(
            "lot_size > 0",
            name="instrument_version_lot_size_positive",
        ),
        CheckConstraint(
            "tick_size > 0",
            name="instrument_version_tick_size_positive",
        ),
        CheckConstraint(
            "char_length(display_symbol) > 0",
            name="instrument_version_symbol_nonempty",
        ),
        CheckConstraint(
            "trading_status IN "
            "('active', 'suspended', 'expired', 'delisted')",
            name="instrument_version_status_supported",
        ),
        Index(
            "ix_instrument_versions_instrument_valid",
            "instrument_id",
            "valid_from",
        ),
        Index(
            "ix_instrument_versions_catalogue",
            "catalogue_version_id",
        ),
    )

    version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("market_instruments.instrument_id"),
        nullable=False,
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(
        DECIMAL_TYPE,
        nullable=False,
    )
    display_symbol: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    trading_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id"),
        nullable=False,
    )


class ProviderContractMappingRow(Base):
    __tablename__ = "provider_contract_mappings"
    __table_args__ = (
        CheckConstraint(
            "char_length(mapping_id) > 0",
            name="provider_mapping_id_nonempty",
        ),
        CheckConstraint(
            "char_length(provider) > 0",
            name="provider_mapping_provider_nonempty",
        ),
        CheckConstraint(
            "char_length(provider_contract_key) > 0",
            name="provider_mapping_key_nonempty",
        ),
        CheckConstraint(
            "char_length(provider_payload_hash) > 0",
            name="provider_mapping_hash_nonempty",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="provider_mapping_effective_interval",
        ),
        Index(
            "ix_provider_contract_mappings_provider_key",
            "provider",
            "provider_contract_key",
        ),
        Index(
            "ix_provider_contract_mappings_contract_version",
            "contract_version_id",
        ),
        Index(
            "ix_provider_contract_mappings_effective",
            "effective_from",
            "effective_until",
        ),
    )

    mapping_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    provider_contract_key: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    contract_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_versions.version_id"),
        nullable=False,
    )
    provider_payload_hash: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    source_row_identity: Mapped[str | None] = mapped_column(
        String(KEY_LENGTH),
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )


class TradingSessionRow(Base):
    __tablename__ = "trading_sessions"
    __table_args__ = (
        CheckConstraint(
            "char_length(session_id) > 0",
            name="trading_session_id_nonempty",
        ),
        CheckConstraint(
            "char_length(exchange) > 0",
            name="trading_session_exchange_nonempty",
        ),
        CheckConstraint(
            "session_kind IN ('regular', 'special')",
            name="session_kind_supported",
        ),
        UniqueConstraint(
            "exchange",
            "session_date",
            "session_kind",
        ),
        Index(
            "ix_trading_sessions_exchange_date",
            "exchange",
            "session_date",
        ),
    )

    session_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    exchange: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    session_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    session_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )


class TradingSessionVersionRow(Base):
    __tablename__ = "trading_session_versions"
    __table_args__ = (
        CheckConstraint(
            "open_at < close_at",
            name="session_open_before_close",
        ),
        CheckConstraint(
            "pre_open_at IS NULL OR pre_open_at <= open_at",
            name="session_pre_open_boundary",
        ),
        CheckConstraint(
            "post_close_at IS NULL OR post_close_at >= close_at",
            name="session_post_close_boundary",
        ),
        CheckConstraint(
            "timezone = 'Asia/Kolkata'",
            name="session_timezone_supported",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'closed', 'cancelled')",
            name="session_status_supported",
        ),
    )

    session_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("trading_sessions.session_id"),
        nullable=False,
    )
    pre_open_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    open_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    close_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    post_close_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )


class CatalogueVersionRecordRow(Base):
    __tablename__ = "catalogue_version_records"
    __table_args__ = (
        *_temporal_record_constraints(
            "catalogue_version_records",
            "catalogue_version_id",
        ),
        UniqueConstraint(
            "record_id",
            "catalogue_version_id",
            name="uq_catalogue_version_records_record_semantic",
        ),
    )


    record_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_version_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(
        String(HASH_LENGTH),
    )


class InstrumentVersionRecordRow(Base):
    __tablename__ = "instrument_version_records"
    __table_args__ = (
        *_temporal_record_constraints(
            "instrument_version_records",
            "version_id",
        ),
        UniqueConstraint(
            "record_id",
            "version_id",
            name="uq_instrument_version_records_record_semantic",
        ),
    )


    record_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_versions.version_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_version_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(
        String(HASH_LENGTH),
    )


class ProviderMappingRecordRow(Base):
    __tablename__ = "provider_mapping_records"
    __table_args__ = (
        *_temporal_record_constraints(
            "provider_mapping_records",
            "mapping_id",
        ),
        UniqueConstraint(
            "record_id",
            "mapping_id",
            name="uq_provider_mapping_records_record_semantic",
        ),
    )


    record_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    mapping_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("provider_contract_mappings.mapping_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("provider_mapping_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(
        String(HASH_LENGTH),
    )


class TradingSessionVersionRecordRow(Base):
    __tablename__ = "trading_session_version_records"
    __table_args__ = _temporal_record_constraints(
        "trading_session_version_records",
        "session_version_id",
    )

    record_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    session_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("trading_session_versions.session_version_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("trading_session_version_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(
        String(HASH_LENGTH),
    )


class CatalogueSourceArtifactRow(Base):
    __tablename__ = "catalogue_source_artifacts"
    __table_args__ = (
        CheckConstraint(
            "char_length(source_artifact_id) > 0",
            name="catalogue_source_artifact_id_nonempty",
        ),
        CheckConstraint(
            "char_length(provider) > 0",
            name="catalogue_source_artifact_provider_nonempty",
        ),
        CheckConstraint(
            "char_length(profile_version) > 0",
            name="catalogue_source_artifact_profile_nonempty",
        ),
        CheckConstraint(
            "media_type = 'application/json'",
            name="catalogue_source_artifact_media_type",
        ),
        CheckConstraint(
            "compression = 'gzip'",
            name="catalogue_source_artifact_compression",
        ),
        CheckConstraint(
            "char_length(compressed_sha256) > 0",
            name="catalogue_source_artifact_compressed_hash_nonempty",
        ),
        CheckConstraint(
            "char_length(decompressed_sha256) > 0",
            name="catalogue_source_artifact_decompressed_hash_nonempty",
        ),
        CheckConstraint(
            "compressed_byte_count >= 0",
            name="catalogue_source_artifact_compressed_count_nonnegative",
        ),
        CheckConstraint(
            "decompressed_byte_count >= 0",
            name="catalogue_source_artifact_decompressed_count_nonnegative",
        ),
        CheckConstraint(
            "char_length(source_schema_version) > 0",
            name="catalogue_source_artifact_schema_nonempty",
        ),
        CheckConstraint(
            "char_length(artifact_object_key) > 0",
            name="catalogue_source_artifact_object_key_nonempty",
        ),
        UniqueConstraint(
            "provider",
            "profile_version",
            "compression",
            "media_type",
            "compressed_sha256",
            "decompressed_sha256",
            "source_schema_version",
            name="uq_catalogue_source_artifact_identity",
        ),
        Index(
            "ix_catalogue_source_artifacts_provider_profile",
            "provider",
            "profile_version",
        ),
    )

    source_artifact_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    profile_version: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    media_type: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    compression: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    compressed_sha256: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    decompressed_sha256: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    compressed_byte_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    decompressed_byte_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    source_schema_version: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    artifact_object_key: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )


class CatalogueIngestionRunRow(Base):
    __tablename__ = "catalogue_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "char_length(ingestion_run_id) > 0",
            name="catalogue_ingestion_run_id_nonempty",
        ),
        CheckConstraint(
            "char_length(idempotency_key) > 0",
            name="catalogue_ingestion_idempotency_nonempty",
        ),
        CheckConstraint(
            "char_length(command_digest) > 0",
            name="catalogue_ingestion_command_digest_nonempty",
        ),
        CheckConstraint(
            "char_length(profile_version) > 0",
            name="catalogue_ingestion_profile_nonempty",
        ),
        CheckConstraint(
            "char_length(original_file_name) > 0",
            name="catalogue_ingestion_file_name_nonempty",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="catalogue_ingestion_effective_interval",
        ),
        CheckConstraint(
            "completed_at >= started_at",
            name="catalogue_ingestion_completed_after_started",
        ),
        CheckConstraint(
            "char_length(normalized_catalogue_hash) > 0",
            name="catalogue_ingestion_catalogue_hash_nonempty",
        ),
        CheckConstraint(
            "physical_row_count >= 0",
            name="catalogue_ingestion_physical_count_nonnegative",
        ),
        CheckConstraint(
            "accepted_unique_count >= 0",
            name="catalogue_ingestion_accepted_count_nonnegative",
        ),
        CheckConstraint(
            "exact_duplicate_count >= 0",
            name="catalogue_ingestion_duplicate_count_nonnegative",
        ),
        CheckConstraint(
            "excluded_count >= 0",
            name="catalogue_ingestion_excluded_count_nonnegative",
        ),
        CheckConstraint(
            "physical_row_count = accepted_unique_count "
            "+ exact_duplicate_count + excluded_count",
            name="catalogue_ingestion_row_reconciliation",
        ),
        CheckConstraint(
            "char_length(database_revision) > 0",
            name="catalogue_ingestion_revision_nonempty",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_catalogue_ingestion_idempotency_key",
        ),
        Index(
            "ix_catalogue_ingestion_runs_artifact",
            "source_artifact_id",
        ),
        Index(
            "ix_catalogue_ingestion_runs_catalogue",
            "catalogue_version_id",
        ),
    )

    ingestion_run_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    command_digest: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    source_artifact_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_source_artifacts.source_artifact_id"),
        nullable=False,
    )
    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id"),
        nullable=False,
    )
    catalogue_record_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_version_records.record_id"),
        nullable=False,
    )
    profile_version: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )
    original_file_name: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    normalized_catalogue_hash: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    physical_row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    accepted_unique_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    exact_duplicate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    excluded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    database_revision: Mapped[str] = mapped_column(
        String(NAME_LENGTH),
        nullable=False,
    )


class CatalogueRowOutcomeRow(Base):
    __tablename__ = "catalogue_row_outcomes"
    __table_args__ = (
        CheckConstraint(
            "char_length(row_outcome_id) > 0",
            name="catalogue_row_outcome_id_nonempty",
        ),
        CheckConstraint(
            "char_length(source_row_occurrence_id) > 0",
            name="catalogue_row_occurrence_id_nonempty",
        ),
        CheckConstraint(
            "char_length(source_row_semantic_id) > 0",
            name="catalogue_row_semantic_id_nonempty",
        ),
        CheckConstraint(
            "physical_row_number > 0",
            name="catalogue_row_number_positive",
        ),
        CheckConstraint(
            "char_length(raw_row_hash) > 0",
            name="catalogue_row_raw_hash_nonempty",
        ),
        CheckConstraint(
            "normalized_row_hash IS NULL "
            "OR char_length(normalized_row_hash) > 0",
            name="catalogue_row_normalized_hash_nonempty",
        ),
        CheckConstraint(
            "disposition IN "
            "('accepted', 'exact_duplicate', 'excluded_by_profile')",
            name="catalogue_row_disposition_supported",
        ),
        CheckConstraint(
            "char_length(reason_codes) >= 2",
            name="catalogue_row_reason_codes_json_nonempty",
        ),
        UniqueConstraint(
            "ingestion_run_id",
            "source_row_occurrence_id",
            name="uq_catalogue_row_outcome_occurrence",
        ),
        Index(
            "ix_catalogue_row_outcomes_run_number",
            "ingestion_run_id",
            "physical_row_number",
        ),
        Index(
            "ix_catalogue_row_outcomes_disposition",
            "disposition",
        ),
        Index(
            "ix_catalogue_row_outcomes_provider_key",
            "provider_contract_key",
        ),
    )

    row_outcome_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    ingestion_run_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_ingestion_runs.ingestion_run_id"),
        nullable=False,
    )
    source_row_occurrence_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        nullable=False,
    )
    source_row_semantic_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        nullable=False,
    )
    physical_row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    raw_row_hash: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    normalized_row_hash: Mapped[str | None] = mapped_column(
        String(HASH_LENGTH),
    )
    provider_contract_key: Mapped[str | None] = mapped_column(
        String(KEY_LENGTH),
    )
    disposition: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    reason_codes: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    instrument_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
    )
    version_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
    )
    mapping_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
    )


class CatalogueMembershipRow(Base):
    __tablename__ = "catalogue_memberships"
    __table_args__ = (
        CheckConstraint(
            "char_length(membership_id) > 0",
            name="catalogue_membership_id_nonempty",
        ),
        CheckConstraint(
            "char_length(source_row_occurrence_id) > 0",
            name="catalogue_membership_occurrence_id_nonempty",
        ),
        CheckConstraint(
            "char_length(source_row_semantic_id) > 0",
            name="catalogue_membership_semantic_id_nonempty",
        ),
        CheckConstraint(
            "char_length(provider_contract_key) > 0",
            name="catalogue_membership_provider_key_nonempty",
        ),
        CheckConstraint(
            "char_length(raw_row_hash) > 0",
            name="catalogue_membership_raw_hash_nonempty",
        ),
        CheckConstraint(
            "char_length(normalized_row_hash) > 0",
            name="catalogue_membership_normalized_hash_nonempty",
        ),
        UniqueConstraint(
            "catalogue_version_id",
            "source_row_semantic_id",
            name="uq_catalogue_membership_semantic_row",
        ),
        Index(
            "ix_catalogue_memberships_catalogue",
            "catalogue_version_id",
        ),
        Index(
            "ix_catalogue_memberships_mapping",
            "mapping_id",
        ),
        Index(
            "ix_catalogue_memberships_provider_key",
            "provider_contract_key",
        ),
    )

    membership_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
    )
    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id"),
        nullable=False,
    )
    row_outcome_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_row_outcomes.row_outcome_id"),
        nullable=False,
    )
    source_row_occurrence_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        nullable=False,
    )
    source_row_semantic_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        nullable=False,
    )
    instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("market_instruments.instrument_id"),
        nullable=False,
    )
    version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_versions.version_id"),
        nullable=False,
    )
    mapping_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("provider_contract_mappings.mapping_id"),
        nullable=False,
    )
    provider_contract_key: Mapped[str] = mapped_column(
        String(KEY_LENGTH),
        nullable=False,
    )
    raw_row_hash: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
    normalized_row_hash: Mapped[str] = mapped_column(
        String(HASH_LENGTH),
        nullable=False,
    )
