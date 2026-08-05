from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

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


def upgrade() -> None:
    for name in TABLES:
        if name == "raw_market_frames":
            _create_raw_market_frames()
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

        if name == "market_normalization_results":
            columns += [
                sa.Column(
                    "raw_event_id",
                    sa.String(ID),
                    nullable=False,
                ),
                sa.Column(
                    "full_result_hash",
                    sa.String(128),
                    nullable=False,
                ),
                sa.Column(
                    "adopted_semantics_hash",
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
            ]
        elif name == "market_observations":
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
        op.execute(f"DROP TRIGGER IF EXISTS data14_{name}_immutable ON {name}")
        op.execute(f"DROP TRIGGER IF EXISTS data14_{name}_no_truncate ON {name}")
    op.execute("DROP FUNCTION IF EXISTS data14_reject_mutation()")
    for name in reversed(TABLES):
        op.drop_table(name)
