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

def upgrade() -> None:
    for name in TABLES:
        columns = [sa.Column("id", sa.String(ID), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        if name == "raw_market_frames":
            columns += [sa.Column("raw_event_id", sa.String(ID), nullable=False, unique=True), sa.Column("frame_bytes", sa.LargeBinary, nullable=False), sa.Column("frame_content_hash", sa.String(128), nullable=False), sa.Column("source_order", sa.BigInteger, nullable=False)]
        elif name == "market_normalization_results":
            columns += [sa.Column("raw_event_id", sa.String(ID), nullable=False), sa.Column("full_result_hash", sa.String(128), nullable=False), sa.Column("adopted_semantics_hash", sa.String(128), nullable=False), sa.Column("normalization_schema_version", sa.Integer, nullable=False), sa.Column("normalizer_implementation_version", sa.String(128), nullable=False)]
        elif name == "provider_lifecycle_observations":
            columns += [sa.Column("raw_event_id", sa.String(ID), nullable=False), sa.Column("lifecycle_kind", sa.String(32), nullable=False)]
        op.create_table(name, *columns)
        op.create_check_constraint(f"ck_{name}_append_created", name, "id <> ''")
        if name == "raw_market_frames":
            op.create_check_constraint("ck_raw_market_frames_bytes", name, "octet_length(frame_bytes) BETWEEN 1 AND 16777216")
            op.create_check_constraint("ck_raw_market_frames_source_order", name, "source_order BETWEEN -9223372036854775808 AND 9223372036854775807")
    op.execute("""CREATE OR REPLACE FUNCTION data14_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'DATA-1.4 tables are append-only'; END; $$""")
    for name in TABLES:
        op.execute(f"CREATE TRIGGER data14_{name}_immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION data14_reject_mutation()")
        op.execute(f"CREATE TRIGGER data14_{name}_no_truncate BEFORE TRUNCATE ON {name} FOR EACH STATEMENT EXECUTE FUNCTION data14_reject_mutation()")

def downgrade() -> None:
    for name in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS data14_{name}_immutable ON {name}")
        op.execute(f"DROP TRIGGER IF EXISTS data14_{name}_no_truncate ON {name}")
    op.execute("DROP FUNCTION IF EXISTS data14_reject_mutation()")
    for name in reversed(TABLES):
        op.drop_table(name)
