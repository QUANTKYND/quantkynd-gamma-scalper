from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_03"
down_revision: str | None = "20260804_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ID = 71
NAME = 128
KEY = 512
HASH = 128


def upgrade() -> None:
    op.create_table(
        "catalogue_source_artifacts",
        sa.Column("source_artifact_id", sa.String(length=ID), nullable=False),
        sa.Column("provider", sa.String(length=NAME), nullable=False),
        sa.Column("profile_version", sa.String(length=NAME), nullable=False),
        sa.Column("media_type", sa.String(length=NAME), nullable=False),
        sa.Column("compression", sa.String(length=16), nullable=False),
        sa.Column("compressed_sha256", sa.String(length=HASH), nullable=False),
        sa.Column("decompressed_sha256", sa.String(length=HASH), nullable=False),
        sa.Column("compressed_byte_count", sa.Integer(), nullable=False),
        sa.Column("decompressed_byte_count", sa.Integer(), nullable=False),
        sa.Column("source_schema_version", sa.String(length=NAME), nullable=False),
        sa.Column("artifact_object_key", sa.String(length=KEY), nullable=False),
        sa.CheckConstraint("char_length(source_artifact_id) > 0", name=op.f("ck_catalogue_source_artifact_id_nonempty")),
        sa.CheckConstraint("char_length(provider) > 0", name=op.f("ck_catalogue_source_artifact_provider_nonempty")),
        sa.CheckConstraint("char_length(profile_version) > 0", name=op.f("ck_catalogue_source_artifact_profile_nonempty")),
        sa.CheckConstraint("media_type = 'application/json'", name=op.f("ck_catalogue_source_artifact_media_type")),
        sa.CheckConstraint("compression = 'gzip'", name=op.f("ck_catalogue_source_artifact_compression")),
        sa.CheckConstraint("char_length(compressed_sha256) > 0", name=op.f("ck_catalogue_source_artifact_compressed_hash_nonempty")),
        sa.CheckConstraint("char_length(decompressed_sha256) > 0", name=op.f("ck_catalogue_source_artifact_decompressed_hash_nonempty")),
        sa.CheckConstraint("compressed_byte_count >= 0", name=op.f("ck_catalogue_source_artifact_compressed_count_nonnegative")),
        sa.CheckConstraint("decompressed_byte_count >= 0", name=op.f("ck_catalogue_source_artifact_decompressed_count_nonnegative")),
        sa.CheckConstraint("char_length(source_schema_version) > 0", name=op.f("ck_catalogue_source_artifact_schema_nonempty")),
        sa.CheckConstraint("char_length(artifact_object_key) > 0", name=op.f("ck_catalogue_source_artifact_object_key_nonempty")),
        sa.PrimaryKeyConstraint("source_artifact_id", name="pk_catalogue_source_artifacts"),
        sa.UniqueConstraint(
            "provider",
            "profile_version",
            "compression",
            "media_type",
            "compressed_sha256",
            "decompressed_sha256",
            "source_schema_version",
            name="uq_catalogue_source_artifact_identity",
        ),
    )
    op.create_index("ix_catalogue_source_artifacts_provider_profile", "catalogue_source_artifacts", ["provider", "profile_version"])
    op.create_table(
        "catalogue_ingestion_runs",
        sa.Column("ingestion_run_id", sa.String(length=ID), nullable=False),
        sa.Column("idempotency_key", sa.String(length=KEY), nullable=False),
        sa.Column("command_digest", sa.String(length=HASH), nullable=False),
        sa.Column("source_artifact_id", sa.String(length=ID), nullable=False),
        sa.Column("catalogue_version_id", sa.String(length=ID), nullable=False),
        sa.Column("catalogue_record_id", sa.String(length=ID), nullable=False),
        sa.Column("profile_version", sa.String(length=NAME), nullable=False),
        sa.Column("original_file_name", sa.String(length=KEY), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized_catalogue_hash", sa.String(length=HASH), nullable=False),
        sa.Column("physical_row_count", sa.Integer(), nullable=False),
        sa.Column("accepted_unique_count", sa.Integer(), nullable=False),
        sa.Column("exact_duplicate_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("database_revision", sa.String(length=NAME), nullable=False),
        sa.CheckConstraint("char_length(ingestion_run_id) > 0", name=op.f("ck_catalogue_ingestion_run_id_nonempty")),
        sa.CheckConstraint("char_length(idempotency_key) > 0", name=op.f("ck_catalogue_ingestion_idempotency_nonempty")),
        sa.CheckConstraint("char_length(command_digest) > 0", name=op.f("ck_catalogue_ingestion_command_digest_nonempty")),
        sa.CheckConstraint("char_length(profile_version) > 0", name=op.f("ck_catalogue_ingestion_profile_nonempty")),
        sa.CheckConstraint("char_length(original_file_name) > 0", name=op.f("ck_catalogue_ingestion_file_name_nonempty")),
        sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name=op.f("ck_catalogue_ingestion_effective_interval")),
        sa.CheckConstraint("completed_at >= started_at", name=op.f("ck_catalogue_ingestion_completed_after_started")),
        sa.CheckConstraint("char_length(normalized_catalogue_hash) > 0", name=op.f("ck_catalogue_ingestion_catalogue_hash_nonempty")),
        sa.CheckConstraint("physical_row_count >= 0", name=op.f("ck_catalogue_ingestion_physical_count_nonnegative")),
        sa.CheckConstraint("accepted_unique_count >= 0", name=op.f("ck_catalogue_ingestion_accepted_count_nonnegative")),
        sa.CheckConstraint("exact_duplicate_count >= 0", name=op.f("ck_catalogue_ingestion_duplicate_count_nonnegative")),
        sa.CheckConstraint("excluded_count >= 0", name=op.f("ck_catalogue_ingestion_excluded_count_nonnegative")),
        sa.CheckConstraint("physical_row_count = accepted_unique_count + exact_duplicate_count + excluded_count", name=op.f("ck_catalogue_ingestion_row_reconciliation")),
        sa.CheckConstraint("char_length(database_revision) > 0", name=op.f("ck_catalogue_ingestion_revision_nonempty")),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["catalogue_source_artifacts.source_artifact_id"], name="fk_catalogue_ingestion_runs_source_artifact_id"),
        sa.ForeignKeyConstraint(["catalogue_version_id"], ["catalogue_versions.catalogue_version_id"], name="fk_catalogue_ingestion_runs_catalogue_version_id"),
        sa.ForeignKeyConstraint(["catalogue_record_id"], ["catalogue_version_records.record_id"], name="fk_catalogue_ingestion_runs_catalogue_record_id"),
        sa.PrimaryKeyConstraint("ingestion_run_id", name="pk_catalogue_ingestion_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_catalogue_ingestion_idempotency_key"),
    )
    op.create_index("ix_catalogue_ingestion_runs_artifact", "catalogue_ingestion_runs", ["source_artifact_id"])
    op.create_index("ix_catalogue_ingestion_runs_catalogue", "catalogue_ingestion_runs", ["catalogue_version_id"])
    op.create_table(
        "catalogue_row_outcomes",
        sa.Column("row_outcome_id", sa.String(length=ID), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=ID), nullable=False),
        sa.Column("source_row_occurrence_id", sa.String(length=ID), nullable=False),
        sa.Column("source_row_semantic_id", sa.String(length=ID), nullable=False),
        sa.Column("physical_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row_hash", sa.String(length=HASH), nullable=False),
        sa.Column("normalized_row_hash", sa.String(length=HASH), nullable=True),
        sa.Column("provider_contract_key", sa.String(length=KEY), nullable=True),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("reason_codes", sa.String(length=KEY), nullable=False),
        sa.Column("instrument_id", sa.String(length=ID), nullable=True),
        sa.Column("version_id", sa.String(length=ID), nullable=True),
        sa.Column("mapping_id", sa.String(length=ID), nullable=True),
        sa.CheckConstraint("char_length(row_outcome_id) > 0", name=op.f("ck_catalogue_row_outcome_id_nonempty")),
        sa.CheckConstraint("char_length(source_row_occurrence_id) > 0", name=op.f("ck_catalogue_row_occurrence_id_nonempty")),
        sa.CheckConstraint("char_length(source_row_semantic_id) > 0", name=op.f("ck_catalogue_row_semantic_id_nonempty")),
        sa.CheckConstraint("physical_row_number > 0", name=op.f("ck_catalogue_row_number_positive")),
        sa.CheckConstraint("char_length(raw_row_hash) > 0", name=op.f("ck_catalogue_row_raw_hash_nonempty")),
        sa.CheckConstraint("normalized_row_hash IS NULL OR char_length(normalized_row_hash) > 0", name=op.f("ck_catalogue_row_normalized_hash_nonempty")),
        sa.CheckConstraint("disposition IN ('accepted', 'exact_duplicate', 'excluded_by_profile')", name=op.f("ck_catalogue_row_disposition_supported")),
        sa.CheckConstraint("char_length(reason_codes) >= 2", name=op.f("ck_catalogue_row_reason_codes_json_nonempty")),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["catalogue_ingestion_runs.ingestion_run_id"], name="fk_catalogue_row_outcomes_ingestion_run_id"),
        sa.PrimaryKeyConstraint("row_outcome_id", name="pk_catalogue_row_outcomes"),
        sa.UniqueConstraint("ingestion_run_id", "source_row_occurrence_id", name="uq_catalogue_row_outcome_occurrence"),
    )
    op.create_index("ix_catalogue_row_outcomes_run_number", "catalogue_row_outcomes", ["ingestion_run_id", "physical_row_number"])
    op.create_index("ix_catalogue_row_outcomes_disposition", "catalogue_row_outcomes", ["disposition"])
    op.create_index("ix_catalogue_row_outcomes_provider_key", "catalogue_row_outcomes", ["provider_contract_key"])
    op.create_table(
        "catalogue_memberships",
        sa.Column("membership_id", sa.String(length=ID), nullable=False),
        sa.Column("catalogue_version_id", sa.String(length=ID), nullable=False),
        sa.Column("row_outcome_id", sa.String(length=ID), nullable=False),
        sa.Column("source_row_occurrence_id", sa.String(length=ID), nullable=False),
        sa.Column("source_row_semantic_id", sa.String(length=ID), nullable=False),
        sa.Column("instrument_id", sa.String(length=ID), nullable=False),
        sa.Column("version_id", sa.String(length=ID), nullable=False),
        sa.Column("mapping_id", sa.String(length=ID), nullable=False),
        sa.Column("provider_contract_key", sa.String(length=KEY), nullable=False),
        sa.Column("raw_row_hash", sa.String(length=HASH), nullable=False),
        sa.Column("normalized_row_hash", sa.String(length=HASH), nullable=False),
        sa.CheckConstraint("char_length(membership_id) > 0", name=op.f("ck_catalogue_membership_id_nonempty")),
        sa.CheckConstraint("char_length(source_row_occurrence_id) > 0", name=op.f("ck_catalogue_membership_occurrence_id_nonempty")),
        sa.CheckConstraint("char_length(source_row_semantic_id) > 0", name=op.f("ck_catalogue_membership_semantic_id_nonempty")),
        sa.CheckConstraint("char_length(provider_contract_key) > 0", name=op.f("ck_catalogue_membership_provider_key_nonempty")),
        sa.CheckConstraint("char_length(raw_row_hash) > 0", name=op.f("ck_catalogue_membership_raw_hash_nonempty")),
        sa.CheckConstraint("char_length(normalized_row_hash) > 0", name=op.f("ck_catalogue_membership_normalized_hash_nonempty")),
        sa.ForeignKeyConstraint(["catalogue_version_id"], ["catalogue_versions.catalogue_version_id"], name="fk_catalogue_memberships_catalogue_version_id"),
        sa.ForeignKeyConstraint(["row_outcome_id"], ["catalogue_row_outcomes.row_outcome_id"], name="fk_catalogue_memberships_row_outcome_id"),
        sa.ForeignKeyConstraint(["instrument_id"], ["market_instruments.instrument_id"], name="fk_catalogue_memberships_instrument_id"),
        sa.ForeignKeyConstraint(["version_id"], ["instrument_versions.version_id"], name="fk_catalogue_memberships_version_id"),
        sa.ForeignKeyConstraint(["mapping_id"], ["provider_contract_mappings.mapping_id"], name="fk_catalogue_memberships_mapping_id"),
        sa.PrimaryKeyConstraint("membership_id", name="pk_catalogue_memberships"),
        sa.UniqueConstraint("catalogue_version_id", "source_row_semantic_id", name="uq_catalogue_membership_semantic_row"),
    )
    op.create_index("ix_catalogue_memberships_catalogue", "catalogue_memberships", ["catalogue_version_id"])
    op.create_index("ix_catalogue_memberships_mapping", "catalogue_memberships", ["mapping_id"])
    op.create_index("ix_catalogue_memberships_provider_key", "catalogue_memberships", ["provider_contract_key"])


def downgrade() -> None:
    op.drop_index("ix_catalogue_memberships_provider_key", table_name="catalogue_memberships")
    op.drop_index("ix_catalogue_memberships_mapping", table_name="catalogue_memberships")
    op.drop_index("ix_catalogue_memberships_catalogue", table_name="catalogue_memberships")
    op.drop_table("catalogue_memberships")
    op.drop_index("ix_catalogue_row_outcomes_provider_key", table_name="catalogue_row_outcomes")
    op.drop_index("ix_catalogue_row_outcomes_disposition", table_name="catalogue_row_outcomes")
    op.drop_index("ix_catalogue_row_outcomes_run_number", table_name="catalogue_row_outcomes")
    op.drop_table("catalogue_row_outcomes")
    op.drop_index("ix_catalogue_ingestion_runs_catalogue", table_name="catalogue_ingestion_runs")
    op.drop_index("ix_catalogue_ingestion_runs_artifact", table_name="catalogue_ingestion_runs")
    op.drop_table("catalogue_ingestion_runs")
    op.drop_index("ix_catalogue_source_artifacts_provider_profile", table_name="catalogue_source_artifacts")
    op.drop_table("catalogue_source_artifacts")
