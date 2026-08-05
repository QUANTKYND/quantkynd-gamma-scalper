from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.instruments.identity import (
    ContractVersion,
    FuturesContractIdentity,
    FuturesContractVersion,
    OptionContractIdentity,
    OptionContractVersion,
    ProviderContractMapping,
    UnderlyingInstrumentIdentity,
    UnderlyingInstrumentVersion,
)
from app.market_data.normalization.enums import (
    FeedResponseType,
    MarketSubjectKind,
    NormalizedAvailabilityBasis,
    ProviderFeedUnion,
    ProviderRequestMode,
)
from app.market_data.point_in_time import NormalizedMarketEventIdentity


NORMALIZATION_SCHEMA_VERSION = 1
NORMALIZER_IMPLEMENTATION_VERSION = "upstox-v3-normalizer-1"
PRESENCE_SEMANTICS = "proto3_parent_implied_v1"
NUMERIC_BASIS = "protobuf_double_roundtrip_decimal_v1"
QUANTITY_BASIS = "upstox_reported_quantity_v1"


@dataclass(frozen=True)
class ResolvedMarketSubjectV1:
    provider: str
    provider_contract_key: str
    provider_mapping_id: str
    contract_version_id: str
    economic_subject_id: str
    instrument_kind: MarketSubjectKind
    economic_identity: UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity
    contract_version: ContractVersion
    mapping_effective_from: datetime
    mapping_effective_until: datetime | None
    version_effective_from: datetime
    version_effective_until: datetime | None
    resolution_market_as_of: datetime
    resolution_known_as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_kind", MarketSubjectKind(self.instrument_kind))
        for name in (
            "mapping_effective_from",
            "version_effective_from",
            "resolution_market_as_of",
            "resolution_known_as_of",
        ):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        for name in ("mapping_effective_until", "version_effective_until"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, name))
        expected = {
            MarketSubjectKind.UNDERLYING: (UnderlyingInstrumentIdentity, UnderlyingInstrumentVersion),
            MarketSubjectKind.FUTURE: (FuturesContractIdentity, FuturesContractVersion),
            MarketSubjectKind.OPTION: (OptionContractIdentity, OptionContractVersion),
        }[self.instrument_kind]
        if not isinstance(self.economic_identity, expected[0]) or not isinstance(self.contract_version, expected[1]):
            raise ValueError("subject kind does not match identity and version")
        identity_id = getattr(self.economic_identity, "instrument_id", None) or getattr(self.economic_identity, "contract_id")
        version_subject_id = getattr(self.contract_version, "instrument_id", None) or getattr(self.contract_version, "contract_id")
        if identity_id != self.economic_subject_id or version_subject_id != identity_id:
            raise ValueError("subject economic identity mismatch")
        if self.contract_version.version_id != self.contract_version_id:
            raise ValueError("contract version identity mismatch")
        if not self.contract_version.effective_at(self.resolution_market_as_of, self.resolution_known_as_of):
            raise ValueError("stale_contract_version")
        if not _effective(self.mapping_effective_from, self.mapping_effective_until, self.resolution_market_as_of):
            raise ValueError("stale_provider_mapping")
        if not _effective(self.version_effective_from, self.version_effective_until, self.resolution_market_as_of):
            raise ValueError("stale_contract_version")


@dataclass(frozen=True)
class NormalizedMarketEventTimeV1:
    provider_timestamp: datetime
    exchange_timestamp: None
    received_at: datetime | None
    available_at: datetime
    recorded_at: datetime
    availability_basis: NormalizedAvailabilityBasis

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_timestamp", _utc(self.provider_timestamp, "provider_timestamp"))
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        object.__setattr__(self, "recorded_at", _utc(self.recorded_at, "recorded_at"))
        object.__setattr__(self, "availability_basis", NormalizedAvailabilityBasis(self.availability_basis))
        if self.exchange_timestamp is not None:
            raise ValueError("exchange_timestamp is unavailable in DATA-1.3")
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at cannot precede available_at")
        if self.received_at is not None and self.available_at < self.received_at:
            raise ValueError("available_at cannot precede received_at")
        if self.availability_basis is NormalizedAvailabilityBasis.RECEIVED and self.received_at is None:
            raise ValueError("received availability requires received_at")


@dataclass(frozen=True)
class QuoteObservationV1:
    identity: NormalizedMarketEventIdentity
    raw_event_id: str
    provider: str
    provider_contract_key: str
    provider_mapping_id: str
    contract_version_id: str
    economic_subject_id: str
    subject: ResolvedMarketSubjectV1
    event_time: NormalizedMarketEventTimeV1
    source_order_scope_id: str
    source_order: int
    feed_response_type: FeedResponseType
    request_mode: ProviderRequestMode
    feed_union: ProviderFeedUnion
    is_snapshot: bool
    presence_semantics: str
    numeric_basis: str
    quantity_basis: str
    normalization_schema_version: int
    normalizer_implementation_version: str
    provider_sequence: None
    supersedes_event_id: None
    bid_price: Decimal | None
    bid_size: int | None
    ask_price: Decimal | None
    ask_size: int | None
    last_price: Decimal | None
    last_size: int | None
    last_trade_at: datetime | None
    previous_close_price: Decimal | None
    reported_volume: int | None
    open_interest: int | None
    provider_depth_levels_present: int
    normalized_depth_levels: int
    unadopted_depth_level_count: int
    unadopted_schema_paths: tuple[str, ...]
    present_unadopted_message_paths: tuple[str, ...]
    secondary_payload_paths_present: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "feed_response_type", FeedResponseType(self.feed_response_type))
        object.__setattr__(self, "request_mode", ProviderRequestMode(self.request_mode))
        object.__setattr__(self, "feed_union", ProviderFeedUnion(self.feed_union))
        if self.identity.raw_event_id != self.raw_event_id or self.identity.subject_id != self.economic_subject_id:
            raise ValueError("normalized quote identity mismatch")
        if self.normalization_schema_version != NORMALIZATION_SCHEMA_VERSION:
            raise ValueError("unsupported normalization schema version")
        if self.presence_semantics != PRESENCE_SEMANTICS or self.numeric_basis != NUMERIC_BASIS:
            raise ValueError("normalization numeric semantics mismatch")
        if self.quantity_basis != QUANTITY_BASIS or self.normalizer_implementation_version != NORMALIZER_IMPLEMENTATION_VERSION:
            raise ValueError("normalizer implementation semantics mismatch")
        if self.last_trade_at is not None:
            object.__setattr__(self, "last_trade_at", _utc(self.last_trade_at, "last_trade_at"))
        for value in (self.bid_price, self.ask_price, self.last_price, self.previous_close_price):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
                raise ValueError("quote prices must be finite non-negative Decimal values")
        for value in (self.bid_size, self.ask_size, self.last_size, self.reported_volume, self.open_interest):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError("quote quantities must be non-negative integers")
        if self.provider_depth_levels_present < self.normalized_depth_levels:
            raise ValueError("normalized depth cannot exceed provider depth")
        if self.unadopted_depth_level_count != self.provider_depth_levels_present - self.normalized_depth_levels:
            raise ValueError("unadopted depth reconciliation failed")
        for name in (
            "unadopted_schema_paths",
            "present_unadopted_message_paths",
            "secondary_payload_paths_present",
        ):
            values = getattr(self, name)
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and unique")

    @property
    def event_id(self) -> str:
        return self.identity.event_id


@dataclass(frozen=True)
class UnderlyingQuoteObservationV1(QuoteObservationV1):
    pass


@dataclass(frozen=True)
class FuturesQuoteObservationV1(QuoteObservationV1):
    pass


@dataclass(frozen=True)
class OptionQuoteObservationV1(QuoteObservationV1):
    pass


@dataclass(frozen=True)
class ProviderMarketSegmentStatusObservationV1:
    identity: NormalizedMarketEventIdentity
    raw_event_id: str
    provider: str
    segment: str
    provider_status_name: str
    provider_status_numeric: int
    status_is_known: bool
    provider_timestamp: datetime
    received_at: datetime | None
    available_at: datetime
    recorded_at: datetime
    source_order_scope_id: str
    source_order: int
    normalization_schema_version: int
    normalizer_implementation_version: str

    def __post_init__(self) -> None:
        if self.identity.raw_event_id != self.raw_event_id or self.identity.event_type != "market_segment_status_observation":
            raise ValueError("normalized status identity mismatch")
        if not self.provider or not self.segment or not self.provider_status_name:
            raise ValueError("status identity fields are required")
        if not isinstance(self.provider_status_numeric, int) or isinstance(self.provider_status_numeric, bool):
            raise ValueError("provider status numeric value must be an integer")
        for name in ("provider_timestamp", "available_at", "recorded_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at cannot precede available_at")
        if self.normalization_schema_version != NORMALIZATION_SCHEMA_VERSION:
            raise ValueError("unsupported normalization schema version")
        if self.normalizer_implementation_version != NORMALIZER_IMPLEMENTATION_VERSION:
            raise ValueError("normalizer implementation semantics mismatch")

    @property
    def event_id(self) -> str:
        return self.identity.event_id


MarketObservationV1 = (
    UnderlyingQuoteObservationV1
    | FuturesQuoteObservationV1
    | OptionQuoteObservationV1
    | ProviderMarketSegmentStatusObservationV1
)


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _effective(start: datetime, end: datetime | None, at: datetime) -> bool:
    return start <= at and (end is None or at < end)
