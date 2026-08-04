from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_versions",
        sa.Column("catalogue_version_id", sa.String(length=71), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("source_content_hash", sa.String(length=128), nullable=False),
        sa.Column("catalogue_schema_version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("char_length(catalogue_version_id) > 0", name=op.f("ck_catalogue_version_id_nonempty")),
        sa.CheckConstraint("char_length(provider) > 0", name=op.f("ck_catalogue_provider_nonempty")),
        sa.CheckConstraint("char_length(source_content_hash) > 0", name=op.f("ck_catalogue_hash_nonempty")),
        sa.CheckConstraint("catalogue_schema_version > 0", name=op.f("ck_catalogue_schema_version_positive")),
        sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name=op.f("ck_catalogue_effective_interval")),
        sa.CheckConstraint("row_count >= 0", name=op.f("ck_catalogue_row_count_nonnegative")),
        sa.PrimaryKeyConstraint("catalogue_version_id", name="pk_catalogue_versions"),
    )
    op.create_index("ix_catalogue_versions_provider_effective", "catalogue_versions", ["provider", "effective_from"])
    op.create_index("ix_catalogue_versions_provider_recorded", "catalogue_versions", ["provider", "recorded_at"])
    op.create_table(
        "market_instruments",
        sa.Column("instrument_id", sa.String(length=71), nullable=False),
        sa.Column("instrument_kind", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.CheckConstraint("char_length(instrument_id) > 0", name=op.f("ck_market_instrument_id_nonempty")),
        sa.CheckConstraint("instrument_kind IN ('underlying', 'future', 'option')", name=op.f("ck_instrument_kind_supported")),
        sa.CheckConstraint("char_length(exchange) > 0", name=op.f("ck_market_instrument_exchange_nonempty")),
        sa.CheckConstraint("char_length(currency) > 0", name=op.f("ck_market_instrument_currency_nonempty")),
        sa.PrimaryKeyConstraint("instrument_id", name="pk_market_instruments"),
        sa.UniqueConstraint("instrument_id", "instrument_kind", name="uq_market_instruments_instrument_id"),
    )
    op.create_table(
        "trading_sessions",
        sa.Column("session_id", sa.String(length=71), nullable=False),
        sa.Column("exchange", sa.String(length=128), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("session_kind", sa.String(length=16), nullable=False),
        sa.CheckConstraint("char_length(session_id) > 0", name=op.f("ck_trading_session_id_nonempty")),
        sa.CheckConstraint("char_length(exchange) > 0", name=op.f("ck_trading_session_exchange_nonempty")),
        sa.CheckConstraint("session_kind IN ('regular', 'special')", name=op.f("ck_session_kind_supported")),
        sa.PrimaryKeyConstraint("session_id", name="pk_trading_sessions"),
        sa.UniqueConstraint("exchange", "session_date", "session_kind", name="uq_trading_sessions_exchange"),
    )
    op.create_index("ix_trading_sessions_exchange_date", "trading_sessions", ["exchange", "session_date"])
    op.create_table(
        "instrument_versions",
        sa.Column("version_id", sa.String(length=71), nullable=False),
        sa.Column("instrument_id", sa.String(length=71), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("display_symbol", sa.String(length=512), nullable=False),
        sa.Column("trading_status", sa.String(length=16), nullable=False),
        sa.Column("catalogue_version_id", sa.String(length=71), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(version_id) > 0", name=op.f("ck_instrument_version_id_nonempty")),
        sa.CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name=op.f("ck_instrument_version_valid_interval")),
        sa.CheckConstraint("lot_size > 0", name=op.f("ck_instrument_version_lot_size_positive")),
        sa.CheckConstraint("tick_size > 0", name=op.f("ck_instrument_version_tick_size_positive")),
        sa.CheckConstraint("char_length(display_symbol) > 0", name=op.f("ck_instrument_version_symbol_nonempty")),
        sa.CheckConstraint("trading_status IN ('active', 'suspended', 'expired', 'delisted')", name=op.f("ck_instrument_version_status_supported")),
        sa.CheckConstraint("superseded_at IS NULL OR superseded_at > recorded_at", name=op.f("ck_instrument_version_system_interval")),
        sa.ForeignKeyConstraint(["catalogue_version_id"], ["catalogue_versions.catalogue_version_id"], name="fk_instrument_versions_catalogue_version_id"),
        sa.ForeignKeyConstraint(["instrument_id"], ["market_instruments.instrument_id"], name="fk_instrument_versions_instrument_id"),
        sa.PrimaryKeyConstraint("version_id", name="pk_instrument_versions"),
    )
    op.create_index("ix_instrument_versions_catalogue", "instrument_versions", ["catalogue_version_id"])
    op.create_index("ix_instrument_versions_instrument_valid", "instrument_versions", ["instrument_id", "valid_from"])
    op.create_index("ix_instrument_versions_recorded_superseded", "instrument_versions", ["recorded_at", "superseded_at"])
    op.create_table(
        "trading_session_versions",
        sa.Column("session_version_id", sa.String(length=71), nullable=False),
        sa.Column("session_id", sa.String(length=71), nullable=False),
        sa.Column("pre_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("post_close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(session_version_id) > 0", name=op.f("ck_session_version_id_nonempty")),
        sa.CheckConstraint("open_at < close_at", name=op.f("ck_session_open_before_close")),
        sa.CheckConstraint("pre_open_at IS NULL OR pre_open_at <= open_at", name=op.f("ck_session_pre_open_boundary")),
        sa.CheckConstraint("post_close_at IS NULL OR post_close_at >= close_at", name=op.f("ck_session_post_close_boundary")),
        sa.CheckConstraint("timezone = 'Asia/Kolkata'", name=op.f("ck_session_timezone_supported")),
        sa.CheckConstraint("status IN ('scheduled', 'closed', 'cancelled')", name=op.f("ck_session_status_supported")),
        sa.CheckConstraint("superseded_at IS NULL OR superseded_at > recorded_at", name=op.f("ck_session_version_system_interval")),
        sa.ForeignKeyConstraint(["session_id"], ["trading_sessions.session_id"], name="fk_trading_session_versions_session_id"),
        sa.PrimaryKeyConstraint("session_version_id", name="pk_trading_session_versions"),
    )
    op.create_index("ix_trading_session_versions_session_recorded", "trading_session_versions", ["session_id", "recorded_at"])
    op.create_index("ix_trading_session_versions_system", "trading_session_versions", ["recorded_at", "superseded_at"])
    _create_instrument_subtypes()
    op.create_table(
        "provider_contract_mappings",
        sa.Column("mapping_id", sa.String(length=71), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("provider_contract_key", sa.String(length=512), nullable=False),
        sa.Column("contract_version_id", sa.String(length=71), nullable=False),
        sa.Column("provider_payload_hash", sa.String(length=128), nullable=False),
        sa.Column("source_row_identity", sa.String(length=512), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(mapping_id) > 0", name=op.f("ck_provider_mapping_id_nonempty")),
        sa.CheckConstraint("char_length(provider) > 0", name=op.f("ck_provider_mapping_provider_nonempty")),
        sa.CheckConstraint("char_length(provider_contract_key) > 0", name=op.f("ck_provider_mapping_key_nonempty")),
        sa.CheckConstraint("char_length(provider_payload_hash) > 0", name=op.f("ck_provider_mapping_hash_nonempty")),
        sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name=op.f("ck_provider_mapping_effective_interval")),
        sa.CheckConstraint("superseded_at IS NULL OR superseded_at > recorded_at", name=op.f("ck_provider_mapping_system_interval")),
        sa.ForeignKeyConstraint(["contract_version_id"], ["instrument_versions.version_id"], name="fk_provider_contract_mappings_contract_version_id"),
        sa.PrimaryKeyConstraint("mapping_id", name="pk_provider_contract_mappings"),
    )
    op.create_index("ix_provider_contract_mappings_contract_version", "provider_contract_mappings", ["contract_version_id"])
    op.create_index("ix_provider_contract_mappings_effective", "provider_contract_mappings", ["effective_from", "effective_until"])
    op.create_index("ix_provider_contract_mappings_provider_key", "provider_contract_mappings", ["provider", "provider_contract_key"])
    op.create_index("ix_provider_contract_mappings_system", "provider_contract_mappings", ["recorded_at", "superseded_at"])


def _create_instrument_subtypes() -> None:
    op.create_table(
        "underlying_instruments",
        sa.Column("instrument_id", sa.String(length=71), nullable=False),
        sa.Column("instrument_kind", sa.String(length=16), nullable=False),
        sa.Column("canonical_symbol", sa.String(length=128), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.CheckConstraint("instrument_kind = 'underlying'", name=op.f("ck_underlying_kind")),
        sa.CheckConstraint("char_length(canonical_symbol) > 0", name=op.f("ck_underlying_symbol_nonempty")),
        sa.CheckConstraint("instrument_type IN ('index', 'equity')", name=op.f("ck_underlying_type_supported")),
        sa.ForeignKeyConstraint(["instrument_id", "instrument_kind"], ["market_instruments.instrument_id", "market_instruments.instrument_kind"], name="fk_underlying_instruments_instrument_id"),
        sa.PrimaryKeyConstraint("instrument_id", name="pk_underlying_instruments"),
    )
    op.create_table(
        "futures_contracts",
        sa.Column("contract_id", sa.String(length=71), nullable=False),
        sa.Column("instrument_kind", sa.String(length=16), nullable=False),
        sa.Column("underlying_instrument_id", sa.String(length=71), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("settlement_type", sa.String(length=16), nullable=False),
        sa.Column("multiplier", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.CheckConstraint("instrument_kind = 'future'", name=op.f("ck_future_kind")),
        sa.CheckConstraint("settlement_type IN ('cash', 'physical')", name=op.f("ck_future_settlement_supported")),
        sa.CheckConstraint("multiplier > 0", name=op.f("ck_future_multiplier_positive")),
        sa.ForeignKeyConstraint(["contract_id", "instrument_kind"], ["market_instruments.instrument_id", "market_instruments.instrument_kind"], name="fk_futures_contracts_contract_id"),
        sa.ForeignKeyConstraint(["underlying_instrument_id"], ["underlying_instruments.instrument_id"], name="fk_futures_contracts_underlying_instrument_id"),
        sa.PrimaryKeyConstraint("contract_id", name="pk_futures_contracts"),
    )
    op.create_index("ix_futures_contracts_underlying_expiry", "futures_contracts", ["underlying_instrument_id", "expiry"])
    op.create_table(
        "option_contracts",
        sa.Column("contract_id", sa.String(length=71), nullable=False),
        sa.Column("instrument_kind", sa.String(length=16), nullable=False),
        sa.Column("underlying_instrument_id", sa.String(length=71), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("strike", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("option_side", sa.String(length=8), nullable=False),
        sa.Column("exercise_style", sa.String(length=16), nullable=False),
        sa.Column("settlement_type", sa.String(length=16), nullable=False),
        sa.Column("multiplier", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.CheckConstraint("instrument_kind = 'option'", name=op.f("ck_option_kind")),
        sa.CheckConstraint("strike > 0", name=op.f("ck_option_strike_positive")),
        sa.CheckConstraint("option_side IN ('call', 'put')", name=op.f("ck_option_side_supported")),
        sa.CheckConstraint("exercise_style IN ('european')", name=op.f("ck_option_exercise_supported")),
        sa.CheckConstraint("settlement_type IN ('cash', 'physical')", name=op.f("ck_option_settlement_supported")),
        sa.CheckConstraint("multiplier > 0", name=op.f("ck_option_multiplier_positive")),
        sa.ForeignKeyConstraint(["contract_id", "instrument_kind"], ["market_instruments.instrument_id", "market_instruments.instrument_kind"], name="fk_option_contracts_contract_id"),
        sa.ForeignKeyConstraint(["underlying_instrument_id"], ["underlying_instruments.instrument_id"], name="fk_option_contracts_underlying_instrument_id"),
        sa.PrimaryKeyConstraint("contract_id", name="pk_option_contracts"),
    )
    op.create_index("ix_option_contracts_expiry_strike_side", "option_contracts", ["expiry", "strike", "option_side"])
    op.create_index("ix_option_contracts_underlying_expiry", "option_contracts", ["underlying_instrument_id", "expiry"])


def downgrade() -> None:
    op.drop_index("ix_provider_contract_mappings_system", table_name="provider_contract_mappings")
    op.drop_index("ix_provider_contract_mappings_provider_key", table_name="provider_contract_mappings")
    op.drop_index("ix_provider_contract_mappings_effective", table_name="provider_contract_mappings")
    op.drop_index("ix_provider_contract_mappings_contract_version", table_name="provider_contract_mappings")
    op.drop_table("provider_contract_mappings")
    op.drop_index("ix_option_contracts_underlying_expiry", table_name="option_contracts")
    op.drop_index("ix_option_contracts_expiry_strike_side", table_name="option_contracts")
    op.drop_table("option_contracts")
    op.drop_index("ix_futures_contracts_underlying_expiry", table_name="futures_contracts")
    op.drop_table("futures_contracts")
    op.drop_table("underlying_instruments")
    op.drop_index("ix_trading_session_versions_system", table_name="trading_session_versions")
    op.drop_index("ix_trading_session_versions_session_recorded", table_name="trading_session_versions")
    op.drop_table("trading_session_versions")
    op.drop_index("ix_instrument_versions_recorded_superseded", table_name="instrument_versions")
    op.drop_index("ix_instrument_versions_instrument_valid", table_name="instrument_versions")
    op.drop_index("ix_instrument_versions_catalogue", table_name="instrument_versions")
    op.drop_table("instrument_versions")
    op.drop_index("ix_trading_sessions_exchange_date", table_name="trading_sessions")
    op.drop_table("trading_sessions")
    op.drop_table("market_instruments")
    op.drop_index("ix_catalogue_versions_provider_recorded", table_name="catalogue_versions")
    op.drop_index("ix_catalogue_versions_provider_effective", table_name="catalogue_versions")
    op.drop_table("catalogue_versions")
