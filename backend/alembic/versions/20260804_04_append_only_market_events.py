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
    "raw_market_frames", "market_normalization_results", "market_observations",
    "underlying_quote_observations", "futures_quote_observations", "option_quote_observations",
    "market_segment_status_observations", "market_normalization_result_events",
    "market_normalization_failures", "market_normalization_result_failures",
    "provider_subscription_instrument_sets", "provider_subscription_instrument_set_keys",
    "provider_lifecycle_batches", "raw_provider_lifecycle_events", "provider_lifecycle_batch_events",
    "provider_lifecycle_observations", "provider_connection_lifecycle_observations",
    "provider_subscription_lifecycle_observations", "provider_lifecycle_batch_observations",
)


def _create_raw_market_frames() -> None:
    op.create_table(
        "raw_market_frames",
        sa.Column(
            "raw_event_id",
            sa.String(ID),
            primary_key=True,
        ),
        sa.Column(
            "provider",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "provider_schema_id",
            sa.String(512),
            nullable=False,
        ),
        sa.Column(
            "provider_schema_sha256",
            sa.String(64),
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
            "frame_bytes",
            sa.LargeBinary(),
            nullable=False,
        ),
        sa.Column(
            "frame_content_hash",
            sa.String(ID),
            nullable=False,
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
            "capture_basis",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "source_file_id",
            sa.String(512),
            nullable=True,
        ),
        sa.Column(
            "source_record_id",
            sa.String(512),
            nullable=True,
        ),
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
            (
                "received_at IS NULL OR "
                "(received_at <> 'infinity'::timestamptz "
                "AND received_at <> '-infinity'::timestamptz)"
            ),
            name="raw_market_frames_received_finite",
        ),
        sa.CheckConstraint(
            (
                "available_at <> 'infinity'::timestamptz "
                "AND available_at <> '-infinity'::timestamptz"
            ),
            name="raw_market_frames_available_finite",
        ),
        sa.CheckConstraint(
            (
                "recorded_at <> 'infinity'::timestamptz "
                "AND recorded_at <> '-infinity'::timestamptz"
            ),
            name="raw_market_frames_recorded_finite",
        ),
        sa.CheckConstraint(
            (
                "persistence_recorded_at <> 'infinity'::timestamptz "
                "AND persistence_recorded_at <> '-infinity'::timestamptz"
            ),
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
            (
                "capture_basis IN ("
                "'live_received', "
                "'recorded_with_original_receipt', "
                "'historical_import'"
                ")"
            ),
            name="raw_market_frames_capture_basis",
        ),
        sa.CheckConstraint(
            (
                "("
                "capture_basis IN ("
                "'live_received', "
                "'recorded_with_original_receipt'"
                ") "
                "AND received_at IS NOT NULL "
                "AND available_at = received_at"
                ") OR ("
                "capture_basis = 'historical_import' "
                "AND received_at IS NULL"
                ")"
            ),
            name="raw_market_frames_capture_clock_shape",
        ),
        sa.CheckConstraint(
            "(source_file_id IS NULL) = (source_record_id IS NULL)",
            name="raw_market_frames_source_pair",
        ),
        sa.CheckConstraint(
            (
                "source_file_id IS NULL OR "
                "octet_length(source_file_id) BETWEEN 1 AND 512"
            ),
            name="raw_market_frames_source_file_bytes",
        ),
        sa.CheckConstraint(
            (
                "source_record_id IS NULL OR "
                "octet_length(source_record_id) BETWEEN 1 AND 512"
            ),
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
        [
            "provider",
            "connection_session_id",
            "source_order_scope_id",
            "source_order",
            "raw_event_id",
        ],
    )

    op.create_index(
        "ix_raw_market_frames_content_hash",
        "raw_market_frames",
        ["frame_content_hash"],
    )

    op.create_index(
        "ix_raw_market_frames_persistence_order",
        "raw_market_frames",
        [
            "persistence_recorded_at",
            "raw_event_id",
        ],
    )


def _create_market_normalization_results() -> None:
    op.create_table(
        "market_normalization_results",
        sa.Column(
            "result_id",
            sa.String(ID),
            primary_key=True,
        ),
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
        sa.Column(
            "response_type",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
        ),
        sa.Column(
            "decoded_entry_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "accepted_entry_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "failed_entry_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "frame_failure_present",
            sa.Boolean(),
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
        sa.Column(
            "full_result_hash",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "adopted_semantics_hash",
            sa.String(ID),
            nullable=False,
        ),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(
                astext_type=sa.Text(),
            ),
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
            (
                "normalization_schema_version = 1 "
                "AND normalizer_implementation_version = "
                "'upstox-v3-normalizer-1'"
            ),
            name="market_normalization_results_schema_label",
        ),
        sa.CheckConstraint(
            (
                "response_type IS NULL OR "
                "response_type IN ("
                "'initial_feed', "
                "'live_feed', "
                "'market_info'"
                ")"
            ),
            name="market_normalization_results_response_type",
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'partial', 'failed')",
            name="market_normalization_results_status",
        ),
        sa.CheckConstraint(
            (
                "decoded_entry_count BETWEEN 0 AND 5000 "
                "AND accepted_entry_count BETWEEN 0 AND 5000 "
                "AND failed_entry_count BETWEEN 0 AND 5000"
            ),
            name="market_normalization_results_count_bounds",
        ),
        sa.CheckConstraint(
            (
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
                "("
                "status = 'complete' "
                "AND accepted_entry_count > 0 "
                "AND failed_entry_count = 0"
                ") OR ("
                "status = 'partial' "
                "AND accepted_entry_count > 0 "
                "AND failed_entry_count > 0"
                ") OR ("
                "status = 'failed' "
                "AND accepted_entry_count = 0"
                ")"
                ")"
                ")"
            ),
            name="market_normalization_results_status_shape",
        ),
        sa.CheckConstraint(
            (
                "array_position("
                "unadopted_schema_paths, NULL"
                ") IS NULL"
            ),
            name="market_normalization_results_unadopted_no_null",
        ),
        sa.CheckConstraint(
            (
                "array_position("
                "present_unadopted_message_paths, NULL"
                ") IS NULL"
            ),
            name="market_normalization_results_present_no_null",
        ),
        sa.CheckConstraint(
            (
                "array_position("
                "secondary_payload_paths_present, NULL"
                ") IS NULL"
            ),
            name="market_normalization_results_secondary_no_null",
        ),
        sa.CheckConstraint(
            "full_result_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="market_normalization_results_full_sha256",
        ),
        sa.CheckConstraint(
            (
                "adopted_semantics_hash "
                "~ '^sha256:[0-9a-f]{64}$'"
            ),
            name="market_normalization_results_adopted_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata_payload) = 'object'",
            name="market_normalization_results_metadata_object",
        ),
        sa.CheckConstraint(
            (
                "persistence_recorded_at "
                "<> 'infinity'::timestamptz "
                "AND persistence_recorded_at "
                "<> '-infinity'::timestamptz"
            ),
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


def upgrade() -> None:
    for name in TABLES:
        if name == "raw_market_frames":
            _create_raw_market_frames()
            continue

        if name == "market_normalization_results":
            _create_market_normalization_results()
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

        if name == "market_observations":
            columns += [
                sa.Column(
                    "raw_event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "event_type",
                    sa.String(32),
                    nullable=False,
                ),
                sa.Column(
                    "normalization_schema_version",
                    sa.Integer(),
                    nullable=False,
                ),
                sa.Column(
                    "payload",
                    sa.JSON(),
                    nullable=False,
                ),
            ]
        elif name == "market_normalization_result_events":
            columns += [
                sa.Column(
                    "result_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "raw_event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "event_ordinal",
                    sa.Integer(),
                    nullable=False,
                ),
            ]
        elif name == "market_normalization_failures":
            columns += [
                sa.Column(
                    "result_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "raw_event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "failure_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "payload",
                    sa.JSON(),
                    nullable=False,
                ),
            ]
        elif name == "market_normalization_result_failures":
            columns += [
                sa.Column(
                    "result_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "raw_event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "failure_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "failure_role",
                    sa.String(16),
                    nullable=False,
                ),
                sa.Column(
                    "failure_ordinal",
                    sa.Integer(),
                    nullable=False,
                ),
            ]
        elif name == "provider_lifecycle_observations":
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

        op.create_table(
            name,
            *columns,
        )

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
        op.execute(f"DROP TRIGGER IF EXISTS data14_{name}_immutable ON {name}")
        op.execute(f"DROP TRIGGER IF EXISTS data14_{name}_no_truncate ON {name}")
    op.execute("DROP FUNCTION IF EXISTS data14_reject_mutation()")
    for name in reversed(TABLES):
        op.drop_table(name)
