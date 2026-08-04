from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.postgres.base import Base


ID_LENGTH = 71
NAME_LENGTH = 128
KEY_LENGTH = 512
HASH_LENGTH = 128
DECIMAL_TYPE = Numeric(38, 18)


def _temporal_record_constraints(table_name: str, semantic_column: str) -> tuple:
    return (
        CheckConstraint("char_length(record_id) > 0", name=f"{table_name}_record_id_nonempty"),
        CheckConstraint("char_length(scope_id) > 0", name=f"{table_name}_scope_id_nonempty"),
        CheckConstraint(
            "supersedes_record_id IS NULL OR supersedes_record_id <> record_id",
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
        CheckConstraint("char_length(catalogue_version_id) > 0", name="catalogue_version_id_nonempty"),
        CheckConstraint("char_length(provider) > 0", name="catalogue_provider_nonempty"),
        CheckConstraint("char_length(source_content_hash) > 0", name="catalogue_hash_nonempty"),
        CheckConstraint("catalogue_schema_version > 0", name="catalogue_schema_version_positive"),
        CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name="catalogue_effective_interval"),
        CheckConstraint("row_count >= 0", name="catalogue_row_count_nonnegative"),
        Index("ix_catalogue_versions_provider_effective", "provider", "effective_from"),
    )

    catalogue_version_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    provider: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    catalogue_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)


class MarketInstrumentRow(Base):
    __tablename__ = "market_instruments"
    __table_args__ = (
        CheckConstraint("char_length(instrument_id) > 0", name="market_instrument_id_nonempty"),
        CheckConstraint("instrument_kind IN ('underlying', 'future', 'option')", name="instrument_kind_supported"),
        CheckConstraint("char_length(exchange) > 0", name="market_instrument_exchange_nonempty"),
        CheckConstraint("char_length(currency) > 0", name="market_instrument_currency_nonempty"),
        UniqueConstraint("instrument_id", "instrument_kind"),
    )

    instrument_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    instrument_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)


class UnderlyingInstrumentRow(Base):
    __tablename__ = "underlying_instruments"
    __table_args__ = (
        CheckConstraint("instrument_kind = 'underlying'", name="underlying_kind"),
        CheckConstraint("char_length(canonical_symbol) > 0", name="underlying_symbol_nonempty"),
        CheckConstraint("instrument_type IN ('index', 'equity')", name="underlying_type_supported"),
        ForeignKeyConstraint(
            ["instrument_id", "instrument_kind"],
            ["market_instruments.instrument_id", "market_instruments.instrument_kind"],
        ),
    )

    instrument_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    instrument_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="underlying")
    canonical_symbol: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)


class FuturesContractRow(Base):
    __tablename__ = "futures_contracts"
    __table_args__ = (
        CheckConstraint("instrument_kind = 'future'", name="future_kind"),
        CheckConstraint("settlement_type IN ('cash', 'physical')", name="future_settlement_supported"),
        CheckConstraint("multiplier > 0", name="future_multiplier_positive"),
        ForeignKeyConstraint(
            ["contract_id", "instrument_kind"],
            ["market_instruments.instrument_id", "market_instruments.instrument_kind"],
        ),
        Index("ix_futures_contracts_underlying_expiry", "underlying_instrument_id", "expiry"),
    )

    contract_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    instrument_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="future")
    underlying_instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("underlying_instruments.instrument_id"),
        nullable=False,
    )
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(DECIMAL_TYPE, nullable=False)


class OptionContractRow(Base):
    __tablename__ = "option_contracts"
    __table_args__ = (
        CheckConstraint("instrument_kind = 'option'", name="option_kind"),
        CheckConstraint("strike > 0", name="option_strike_positive"),
        CheckConstraint("option_side IN ('call', 'put')", name="option_side_supported"),
        CheckConstraint("exercise_style IN ('european')", name="option_exercise_supported"),
        CheckConstraint("settlement_type IN ('cash', 'physical')", name="option_settlement_supported"),
        CheckConstraint("multiplier > 0", name="option_multiplier_positive"),
        ForeignKeyConstraint(
            ["contract_id", "instrument_kind"],
            ["market_instruments.instrument_id", "market_instruments.instrument_kind"],
        ),
        Index("ix_option_contracts_underlying_expiry", "underlying_instrument_id", "expiry"),
        Index("ix_option_contracts_expiry_strike_side", "expiry", "strike", "option_side"),
    )

    contract_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    instrument_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="option")
    underlying_instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("underlying_instruments.instrument_id"),
        nullable=False,
    )
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal] = mapped_column(DECIMAL_TYPE, nullable=False)
    option_side: Mapped[str] = mapped_column(String(8), nullable=False)
    exercise_style: Mapped[str] = mapped_column(String(16), nullable=False)
    settlement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(DECIMAL_TYPE, nullable=False)


class InstrumentVersionRow(Base):
    __tablename__ = "instrument_versions"
    __table_args__ = (
        CheckConstraint("char_length(version_id) > 0", name="instrument_version_id_nonempty"),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="instrument_version_valid_interval"),
        CheckConstraint("lot_size > 0", name="instrument_version_lot_size_positive"),
        CheckConstraint("tick_size > 0", name="instrument_version_tick_size_positive"),
        CheckConstraint("char_length(display_symbol) > 0", name="instrument_version_symbol_nonempty"),
        CheckConstraint(
            "trading_status IN ('active', 'suspended', 'expired', 'delisted')",
            name="instrument_version_status_supported",
        ),
        Index("ix_instrument_versions_instrument_valid", "instrument_id", "valid_from"),
        Index("ix_instrument_versions_catalogue", "catalogue_version_id"),
    )

    version_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("market_instruments.instrument_id"),
        nullable=False,
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(DECIMAL_TYPE, nullable=False)
    display_symbol: Mapped[str] = mapped_column(String(KEY_LENGTH), nullable=False)
    trading_status: Mapped[str] = mapped_column(String(16), nullable=False)
    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id"),
        nullable=False,
    )


class ProviderContractMappingRow(Base):
    __tablename__ = "provider_contract_mappings"
    __table_args__ = (
        CheckConstraint("char_length(mapping_id) > 0", name="provider_mapping_id_nonempty"),
        CheckConstraint("char_length(provider) > 0", name="provider_mapping_provider_nonempty"),
        CheckConstraint("char_length(provider_contract_key) > 0", name="provider_mapping_key_nonempty"),
        CheckConstraint("char_length(provider_payload_hash) > 0", name="provider_mapping_hash_nonempty"),
        CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name="provider_mapping_effective_interval"),
        Index("ix_provider_contract_mappings_provider_key", "provider", "provider_contract_key"),
        Index("ix_provider_contract_mappings_contract_version", "contract_version_id"),
        Index("ix_provider_contract_mappings_effective", "effective_from", "effective_until"),
    )

    mapping_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    provider: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    provider_contract_key: Mapped[str] = mapped_column(String(KEY_LENGTH), nullable=False)
    contract_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_versions.version_id"),
        nullable=False,
    )
    provider_payload_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    source_row_identity: Mapped[str | None] = mapped_column(String(KEY_LENGTH))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TradingSessionRow(Base):
    __tablename__ = "trading_sessions"
    __table_args__ = (
        CheckConstraint("char_length(session_id) > 0", name="trading_session_id_nonempty"),
        CheckConstraint("char_length(exchange) > 0", name="trading_session_exchange_nonempty"),
        CheckConstraint("session_kind IN ('regular', 'special')", name="session_kind_supported"),
        UniqueConstraint("exchange", "session_date", "session_kind"),
        Index("ix_trading_sessions_exchange_date", "exchange", "session_date"),
    )

    session_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_kind: Mapped[str] = mapped_column(String(16), nullable=False)


class TradingSessionVersionRow(Base):
    __tablename__ = "trading_session_versions"
    __table_args__ = (
        CheckConstraint("char_length(session_version_id) > 0", name="session_version_id_nonempty"),
        CheckConstraint("open_at < close_at", name="session_open_before_close"),
        CheckConstraint("pre_open_at IS NULL OR pre_open_at <= open_at", name="session_pre_open_boundary"),
        CheckConstraint("post_close_at IS NULL OR post_close_at >= close_at", name="session_post_close_boundary"),
        CheckConstraint("timezone = 'Asia/Kolkata'", name="session_timezone_supported"),
        CheckConstraint("status IN ('scheduled', 'closed', 'cancelled')", name="session_status_supported"),
    )

    session_version_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("trading_sessions.session_id"),
        nullable=False,
    )
    pre_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    post_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class CatalogueVersionRecordRow(Base):
    __tablename__ = "catalogue_version_records"
    __table_args__ = _temporal_record_constraints(
        "catalogue_version_records",
        "catalogue_version_id",
    )

    record_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    catalogue_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_versions.catalogue_version_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(String(KEY_LENGTH), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("catalogue_version_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(String(HASH_LENGTH))


class InstrumentVersionRecordRow(Base):
    __tablename__ = "instrument_version_records"
    __table_args__ = _temporal_record_constraints(
        "instrument_version_records",
        "version_id",
    )

    record_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_versions.version_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(String(KEY_LENGTH), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("instrument_version_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(String(HASH_LENGTH))


class ProviderMappingRecordRow(Base):
    __tablename__ = "provider_mapping_records"
    __table_args__ = _temporal_record_constraints(
        "provider_mapping_records",
        "mapping_id",
    )

    record_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    mapping_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("provider_contract_mappings.mapping_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(String(KEY_LENGTH), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("provider_mapping_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(String(HASH_LENGTH))


class TradingSessionVersionRecordRow(Base):
    __tablename__ = "trading_session_version_records"
    __table_args__ = _temporal_record_constraints(
        "trading_session_version_records",
        "session_version_id",
    )

    record_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    session_version_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("trading_session_versions.session_version_id"),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(String(KEY_LENGTH), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("trading_session_version_records.record_id"),
    )
    source_provenance_id: Mapped[str | None] = mapped_column(String(HASH_LENGTH))
