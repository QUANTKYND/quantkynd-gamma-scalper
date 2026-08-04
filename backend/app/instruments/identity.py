from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from app.core.hashing import stable_hash


class InstrumentType(StrEnum):
    INDEX = "index"
    EQUITY = "equity"


class OptionSide(StrEnum):
    CALL = "call"
    PUT = "put"


class ExerciseStyle(StrEnum):
    EUROPEAN = "european"


class SettlementType(StrEnum):
    CASH = "cash"
    PHYSICAL = "physical"


class TradingStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    DELISTED = "delisted"


@dataclass(frozen=True)
class UnderlyingInstrumentIdentity:
    exchange: str
    canonical_symbol: str
    instrument_type: InstrumentType
    currency: str

    def __post_init__(self) -> None:
        _require_text(self.exchange, self.canonical_symbol, self.currency)
        object.__setattr__(self, "instrument_type", InstrumentType(self.instrument_type))

    @property
    def instrument_id(self) -> str:
        return stable_hash(
            {
                "entity": "underlying_instrument",
                "exchange": self.exchange,
                "canonical_symbol": self.canonical_symbol,
                "instrument_type": self.instrument_type.value,
                "currency": self.currency,
            }
        )


@dataclass(frozen=True)
class FuturesContractIdentity:
    exchange: str
    underlying_instrument_id: str
    expiry: date
    settlement_type: SettlementType
    multiplier: Decimal
    currency: str

    def __post_init__(self) -> None:
        _require_text(self.exchange, self.underlying_instrument_id, self.currency)
        _require_expiry(self.expiry)
        object.__setattr__(self, "settlement_type", SettlementType(self.settlement_type))
        _require_positive_decimal(self.multiplier, "multiplier")

    @property
    def contract_id(self) -> str:
        return stable_hash(
            {
                "entity": "futures_contract",
                "exchange": self.exchange,
                "underlying_instrument_id": self.underlying_instrument_id,
                "expiry": self.expiry,
                "settlement_type": self.settlement_type.value,
                "multiplier": self.multiplier,
                "currency": self.currency,
            }
        )


@dataclass(frozen=True)
class OptionContractIdentity:
    exchange: str
    underlying_instrument_id: str
    expiry: date
    strike: Decimal
    option_side: OptionSide
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    multiplier: Decimal
    currency: str

    def __post_init__(self) -> None:
        _require_text(self.exchange, self.underlying_instrument_id, self.currency)
        _require_expiry(self.expiry)
        object.__setattr__(self, "option_side", OptionSide(self.option_side))
        object.__setattr__(self, "exercise_style", ExerciseStyle(self.exercise_style))
        object.__setattr__(self, "settlement_type", SettlementType(self.settlement_type))
        _require_positive_decimal(self.strike, "strike")
        _require_positive_decimal(self.multiplier, "multiplier")

    @property
    def contract_id(self) -> str:
        return stable_hash(
            {
                "entity": "option_contract",
                "exchange": self.exchange,
                "underlying_instrument_id": self.underlying_instrument_id,
                "expiry": self.expiry,
                "strike": self.strike,
                "option_side": self.option_side.value,
                "exercise_style": self.exercise_style.value,
                "settlement_type": self.settlement_type.value,
                "multiplier": self.multiplier,
                "currency": self.currency,
            }
        )


@dataclass(frozen=True)
class ContractVersionMetadata:
    valid_from: datetime
    valid_until: datetime | None
    lot_size: int
    tick_size: Decimal
    display_symbol: str
    trading_status: TradingStatus
    catalogue_version_id: str
    recorded_at: datetime
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        _normalize_interval(self, "valid_from", "valid_until")
        _normalize_system_interval(self)
        if not isinstance(self.lot_size, int) or isinstance(self.lot_size, bool) or self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        _require_positive_decimal(self.tick_size, "tick_size")
        _require_text(self.display_symbol, self.catalogue_version_id)
        object.__setattr__(self, "trading_status", TradingStatus(self.trading_status))

    def effective_at(self, market_as_of: datetime, known_as_of: datetime | None = None) -> bool:
        market_time = _utc(market_as_of, "market_as_of")
        knowledge_time = _utc(known_as_of, "known_as_of") if known_as_of is not None else None
        market_valid = self.valid_from <= market_time and (
            self.valid_until is None or market_time < self.valid_until
        )
        knowledge_valid = knowledge_time is None or (
            self.recorded_at <= knowledge_time
            and (self.superseded_at is None or knowledge_time < self.superseded_at)
        )
        return market_valid and knowledge_valid


@dataclass(frozen=True)
class UnderlyingInstrumentVersion(ContractVersionMetadata):
    instrument_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_text(self.instrument_id)

    @property
    def version_id(self) -> str:
        return _version_id("underlying_instrument_version", self.instrument_id, self)


@dataclass(frozen=True)
class FuturesContractVersion(ContractVersionMetadata):
    contract_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_text(self.contract_id)

    @property
    def version_id(self) -> str:
        return _version_id("futures_contract_version", self.contract_id, self)


@dataclass(frozen=True)
class OptionContractVersion(ContractVersionMetadata):
    contract_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_text(self.contract_id)

    @property
    def version_id(self) -> str:
        return _version_id("option_contract_version", self.contract_id, self)


ContractVersion = UnderlyingInstrumentVersion | FuturesContractVersion | OptionContractVersion


@dataclass(frozen=True)
class ProviderContractMapping:
    provider: str
    provider_contract_key: str
    contract_version_id: str
    provider_payload_hash: str
    source_row_identity: str | None
    effective_from: datetime
    effective_until: datetime | None
    recorded_at: datetime
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(
            self.provider,
            self.provider_contract_key,
            self.contract_version_id,
            self.provider_payload_hash,
        )
        if self.source_row_identity is not None:
            _require_text(self.source_row_identity)
        _normalize_interval(self, "effective_from", "effective_until")
        _normalize_system_interval(self)

    @property
    def mapping_id(self) -> str:
        return stable_hash(
            {
                "entity": "provider_contract_mapping",
                "provider": self.provider,
                "provider_contract_key": self.provider_contract_key,
                "contract_version_id": self.contract_version_id,
                "provider_payload_hash": self.provider_payload_hash,
                "source_row_identity": self.source_row_identity,
                "effective_from": self.effective_from,
                "effective_until": self.effective_until,
            }
        )

    def effective_at(self, market_as_of: datetime, known_as_of: datetime | None = None) -> bool:
        market_time = _utc(market_as_of, "market_as_of")
        knowledge_time = _utc(known_as_of, "known_as_of") if known_as_of is not None else None
        market_valid = self.effective_from <= market_time and (
            self.effective_until is None or market_time < self.effective_until
        )
        knowledge_valid = knowledge_time is None or (
            self.recorded_at <= knowledge_time
            and (self.superseded_at is None or knowledge_time < self.superseded_at)
        )
        return market_valid and knowledge_valid


def _version_id(
    entity: str,
    identity_id: str,
    metadata: ContractVersionMetadata,
) -> str:
    return stable_hash(
        {
            "entity": entity,
            "identity_id": identity_id,
            "valid_from": metadata.valid_from,
            "valid_until": metadata.valid_until,
            "lot_size": metadata.lot_size,
            "tick_size": metadata.tick_size,
            "display_symbol": metadata.display_symbol,
            "trading_status": metadata.trading_status.value,
            "catalogue_version_id": metadata.catalogue_version_id,
        }
    )


def _normalize_interval(instance: object, start_name: str, end_name: str) -> None:
    start = _utc(getattr(instance, start_name), start_name)
    end_value = getattr(instance, end_name)
    end = _utc(end_value, end_name) if end_value is not None else None
    if end is not None and end <= start:
        raise ValueError(f"{end_name} must be after {start_name}")
    object.__setattr__(instance, start_name, start)
    object.__setattr__(instance, end_name, end)


def _normalize_system_interval(instance: object) -> None:
    recorded_at = _utc(getattr(instance, "recorded_at"), "recorded_at")
    superseded_value = getattr(instance, "superseded_at")
    superseded_at = _utc(superseded_value, "superseded_at") if superseded_value is not None else None
    if superseded_at is not None and superseded_at <= recorded_at:
        raise ValueError("superseded_at must be after recorded_at")
    object.__setattr__(instance, "recorded_at", recorded_at)
    object.__setattr__(instance, "superseded_at", superseded_at)


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be positive and finite")


def _require_expiry(value: date) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError("expiry must be an exchange date")


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("identity text values must be non-empty")
