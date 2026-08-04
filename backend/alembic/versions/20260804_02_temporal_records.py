from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.core.hashing import stable_hash
from app.instruments.temporal_records import TemporalRecord, TemporalRecordKind


revision: str = "20260804_02"
down_revision: str | None = "20260804_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_TEMPORAL_TABLES = (
    "instrument_versions",
    "provider_contract_mappings",
    "trading_session_versions",
)


def upgrade() -> None:
    connection = op.get_bind()
    for table_name in LEGACY_TEMPORAL_TABLES:
        count = connection.scalar(
            sa.text(f"SELECT count(*) FROM {table_name} WHERE superseded_at IS NOT NULL")
        )
        if count:
            raise RuntimeError(
                f"DATA-1.1 temporal migration refused: {table_name} contains legacy non-null superseded_at values"
            )
    _create_record_table(
        "catalogue_version_records",
        "catalogue_version_id",
        "catalogue_versions.catalogue_version_id",
    )
    _create_record_table(
        "instrument_version_records",
        "version_id",
        "instrument_versions.version_id",
    )
    _create_record_table(
        "provider_mapping_records",
        "mapping_id",
        "provider_contract_mappings.mapping_id",
    )
    _create_record_table(
        "trading_session_version_records",
        "session_version_id",
        "trading_session_versions.session_version_id",
    )
    _migrate_catalogue_records(connection)
    _migrate_instrument_version_records(connection)
    _migrate_provider_mapping_records(connection)
    _migrate_trading_session_version_records(connection)
    op.drop_index("ix_catalogue_versions_provider_recorded", table_name="catalogue_versions")
    op.drop_column("catalogue_versions", "recorded_at")
    op.drop_index("ix_instrument_versions_recorded_superseded", table_name="instrument_versions")
    op.drop_constraint(
        op.f("ck_instrument_version_system_interval"),
        "instrument_versions",
        type_="check",
    )
    op.drop_column("instrument_versions", "superseded_at")
    op.drop_column("instrument_versions", "recorded_at")
    op.drop_index("ix_provider_contract_mappings_system", table_name="provider_contract_mappings")
    op.drop_constraint(
        op.f("ck_provider_mapping_system_interval"),
        "provider_contract_mappings",
        type_="check",
    )
    op.drop_column("provider_contract_mappings", "superseded_at")
    op.drop_column("provider_contract_mappings", "recorded_at")
    op.drop_index("ix_trading_session_versions_system", table_name="trading_session_versions")
    op.drop_index(
        "ix_trading_session_versions_session_recorded",
        table_name="trading_session_versions",
    )
    op.drop_constraint(
        op.f("ck_session_version_system_interval"),
        "trading_session_versions",
        type_="check",
    )
    op.drop_column("trading_session_versions", "superseded_at")
    op.drop_column("trading_session_versions", "recorded_at")


def downgrade() -> None:
    connection = op.get_bind()
    table_keys = (
        ("catalogue_version_records", "catalogue_version_id"),
        ("instrument_version_records", "version_id"),
        ("provider_mapping_records", "mapping_id"),
        ("trading_session_version_records", "session_version_id"),
    )
    for table_name, semantic_column in table_keys:
        superseding = connection.scalar(
            sa.text(
                f"SELECT count(*) FROM {table_name} WHERE supersedes_record_id IS NOT NULL"
            )
        )
        duplicates = connection.scalar(
            sa.text(
                f"SELECT count(*) FROM (SELECT {semantic_column} FROM {table_name} GROUP BY {semantic_column} HAVING count(*) > 1) values"
            )
        )
        if superseding or duplicates:
            raise RuntimeError(
                f"DATA-1.1 downgrade refused: {table_name} contains append-only history not representable by 20260804_01"
            )
    _restore_legacy_columns(connection)
    for table_name in (
        "trading_session_version_records",
        "provider_mapping_records",
        "instrument_version_records",
        "catalogue_version_records",
    ):
        op.drop_table(table_name)


def _create_record_table(
    table_name: str,
    semantic_column: str,
    semantic_reference: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column("record_id", sa.String(length=71), nullable=False),
        sa.Column(semantic_column, sa.String(length=71), nullable=False),
        sa.Column("scope_id", sa.String(length=512), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_record_id", sa.String(length=71), nullable=True),
        sa.Column("source_provenance_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "char_length(record_id) > 0",
            name=op.f(f"ck_{table_name}_record_id_nonempty"),
        ),
        sa.CheckConstraint(
            "char_length(scope_id) > 0",
            name=op.f(f"ck_{table_name}_scope_id_nonempty"),
        ),
        sa.CheckConstraint(
            "supersedes_record_id IS NULL OR supersedes_record_id <> record_id",
            name=op.f(f"ck_{table_name}_not_self_superseding"),
        ),
        sa.ForeignKeyConstraint(
            [semantic_column],
            [semantic_reference],
            name=f"fk_{table_name}_{semantic_column}",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_record_id"],
            [f"{table_name}.record_id"],
            name=f"fk_{table_name}_supersedes_record_id",
        ),
        sa.PrimaryKeyConstraint("record_id", name=f"pk_{table_name}"),
    )
    op.create_index(f"ix_{table_name}_semantic", table_name, [semantic_column])
    op.create_index(f"ix_{table_name}_recorded", table_name, ["recorded_at"])
    op.create_index(f"ix_{table_name}_successor", table_name, ["supersedes_record_id"])
    op.create_index(
        f"uq_{table_name}_one_successor",
        table_name,
        ["supersedes_record_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_record_id IS NOT NULL"),
    )


def _migrate_catalogue_records(connection) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT catalogue_version_id, provider, source_content_hash, recorded_at FROM catalogue_versions"
        )
    ).mappings()
    _insert_records(
        connection,
        "catalogue_version_records",
        "catalogue_version_id",
        (
            (
                TemporalRecord(
                    TemporalRecordKind.CATALOGUE_VERSION,
                    row["catalogue_version_id"],
                    row["provider"],
                    row["recorded_at"],
                    source_provenance_id=row["source_content_hash"],
                ),
                row["catalogue_version_id"],
            )
            for row in rows
        ),
    )


def _migrate_instrument_version_records(connection) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT version_id, instrument_id, catalogue_version_id, recorded_at FROM instrument_versions"
        )
    ).mappings()
    _insert_records(
        connection,
        "instrument_version_records",
        "version_id",
        (
            (
                TemporalRecord(
                    TemporalRecordKind.INSTRUMENT_VERSION,
                    row["version_id"],
                    row["instrument_id"],
                    row["recorded_at"],
                    source_provenance_id=row["catalogue_version_id"],
                ),
                row["version_id"],
            )
            for row in rows
        ),
    )


def _migrate_provider_mapping_records(connection) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT mapping_id, provider, provider_contract_key, provider_payload_hash, source_row_identity, recorded_at FROM provider_contract_mappings"
        )
    ).mappings()
    values = []
    for row in rows:
        scope_id = stable_hash(
            {
                "entity": "provider_mapping_scope",
                "provider": row["provider"],
                "provider_contract_key": row["provider_contract_key"],
            }
        )
        provenance = stable_hash(
            {
                "provider_payload_hash": row["provider_payload_hash"],
                "source_row_identity": row["source_row_identity"],
            }
        )
        values.append(
            (
                TemporalRecord(
                    TemporalRecordKind.PROVIDER_MAPPING,
                    row["mapping_id"],
                    scope_id,
                    row["recorded_at"],
                    source_provenance_id=provenance,
                ),
                row["mapping_id"],
            )
        )
    _insert_records(
        connection,
        "provider_mapping_records",
        "mapping_id",
        values,
    )


def _migrate_trading_session_version_records(connection) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT session_version_id, session_id, recorded_at FROM trading_session_versions"
        )
    ).mappings()
    _insert_records(
        connection,
        "trading_session_version_records",
        "session_version_id",
        (
            (
                TemporalRecord(
                    TemporalRecordKind.TRADING_SESSION_VERSION,
                    row["session_version_id"],
                    row["session_id"],
                    row["recorded_at"],
                ),
                row["session_version_id"],
            )
            for row in rows
        ),
    )


def _insert_records(connection, table_name, semantic_column, records) -> None:
    statement = sa.text(
        f"INSERT INTO {table_name} (record_id, {semantic_column}, scope_id, recorded_at, supersedes_record_id, source_provenance_id) VALUES (:record_id, :semantic_id, :scope_id, :recorded_at, :supersedes_record_id, :source_provenance_id)"
    )
    for record, semantic_id in records:
        connection.execute(
            statement,
            {
                "record_id": record.record_id,
                "semantic_id": semantic_id,
                "scope_id": record.scope_id,
                "recorded_at": record.recorded_at,
                "supersedes_record_id": None,
                "source_provenance_id": record.source_provenance_id,
            },
        )


def _restore_legacy_columns(connection) -> None:
    op.add_column(
        "catalogue_versions",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instrument_versions",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instrument_versions",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_contract_mappings",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_contract_mappings",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trading_session_versions",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trading_session_versions",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    mappings = (
        ("catalogue_versions", "catalogue_version_records", "catalogue_version_id"),
        ("instrument_versions", "instrument_version_records", "version_id"),
        ("provider_contract_mappings", "provider_mapping_records", "mapping_id"),
        (
            "trading_session_versions",
            "trading_session_version_records",
            "session_version_id",
        ),
    )
    for semantic_table, record_table, semantic_column in mappings:
        connection.execute(
            sa.text(
                f"UPDATE {semantic_table} semantic SET recorded_at = record.recorded_at FROM {record_table} record WHERE semantic.{semantic_column} = record.{semantic_column}"
            )
        )
        op.alter_column(semantic_table, "recorded_at", nullable=False)
    op.create_index(
        "ix_catalogue_versions_provider_recorded",
        "catalogue_versions",
        ["provider", "recorded_at"],
    )
    op.create_check_constraint(
        op.f("ck_instrument_version_system_interval"),
        "instrument_versions",
        "superseded_at IS NULL OR superseded_at > recorded_at",
    )
    op.create_index(
        "ix_instrument_versions_recorded_superseded",
        "instrument_versions",
        ["recorded_at", "superseded_at"],
    )
    op.create_check_constraint(
        op.f("ck_provider_mapping_system_interval"),
        "provider_contract_mappings",
        "superseded_at IS NULL OR superseded_at > recorded_at",
    )
    op.create_index(
        "ix_provider_contract_mappings_system",
        "provider_contract_mappings",
        ["recorded_at", "superseded_at"],
    )
    op.create_check_constraint(
        op.f("ck_session_version_system_interval"),
        "trading_session_versions",
        "superseded_at IS NULL OR superseded_at > recorded_at",
    )
    op.create_index(
        "ix_trading_session_versions_session_recorded",
        "trading_session_versions",
        ["session_id", "recorded_at"],
    )
    op.create_index(
        "ix_trading_session_versions_system",
        "trading_session_versions",
        ["recorded_at", "superseded_at"],
    )
