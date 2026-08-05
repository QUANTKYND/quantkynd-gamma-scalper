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
from app.core.hashing import stable_hash


NORMALIZATION_SCHEMA_VERSION = 1
NORMALIZER_IMPLEMENTATION_VERSION = "upstox-v3-normalizer-1"
PRESENCE_SEMANTICS = "proto3_parent_implied_v1"
NUMERIC_BASIS = "protobuf_double_roundtrip_decimal_v1"
QUANTITY_BASIS = "upstox_reported_quantity_v1"
PROVIDER_MARKET_STATUS_NAMES = {
    0: "PRE_OPEN_START",
    1: "PRE_OPEN_END",
    2: "NORMAL_OPEN",
    3: "NORMAL_CLOSE",
    4: "CLOSING_START",
    5: "CLOSING_END",
}


@dataclass(frozen=True)
class ResolvedMarketSubjectV1:
    provider: str
    provider_contract_key: str
    provider_mapping_id: str
    provider_mapping: ProviderContractMapping
    contract_version_id: str
    economic_subject_id: str
    instrument_kind: MarketSubjectKind
    economic_identity: UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity
    contract_version: ContractVersion
    resolution_market_as_of: datetime
    resolution_known_as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_kind", MarketSubjectKind(self.instrument_kind))
        _require_text(
            self.provider,
            self.provider_contract_key,
            self.provider_mapping_id,
            self.contract_version_id,
            self.economic_subject_id,
        )
        for name in ("resolution_market_as_of", "resolution_known_as_of"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
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
        if self.provider_mapping.mapping_id != self.provider_mapping_id:
            raise ValueError("provider mapping identity mismatch")
        if self.provider_mapping.provider != self.provider:
            raise ValueError("provider mapping provider mismatch")
        if self.provider_mapping.provider_contract_key != self.provider_contract_key:
            raise ValueError("provider mapping key mismatch")
        if self.provider_mapping.contract_version_id != self.contract_version_id:
            raise ValueError("provider mapping version mismatch")
        if not self.provider_mapping.effective_at(self.resolution_market_as_of, self.resolution_known_as_of):
            raise ValueError("stale_provider_mapping")
        if not self.contract_version.effective_at(self.resolution_market_as_of, self.resolution_known_as_of):
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
        if self.availability_basis is NormalizedAvailabilityBasis.RECEIVED and self.available_at != self.received_at:
            raise ValueError("received availability requires equal receipt and availability")
        if self.availability_basis is NormalizedAvailabilityBasis.HISTORICAL_IMPORT and self.received_at is not None:
            raise ValueError("historical_import requires absent received_at")


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
        if not isinstance(self.identity, NormalizedMarketEventIdentity) or not isinstance(self.subject, ResolvedMarketSubjectV1):
            raise TypeError("quote identity and subject types are required")
        if not isinstance(self.event_time, NormalizedMarketEventTimeV1):
            raise TypeError("quote event_time type is required")
        object.__setattr__(self, "feed_response_type", FeedResponseType(self.feed_response_type))
        object.__setattr__(self, "request_mode", ProviderRequestMode(self.request_mode))
        object.__setattr__(self, "feed_union", ProviderFeedUnion(self.feed_union))
        if self.identity.raw_event_id != self.raw_event_id or self.identity.subject_id != self.economic_subject_id:
            raise ValueError("normalized quote identity mismatch")
        _require_text(
            self.raw_event_id,
            self.provider,
            self.provider_contract_key,
            self.provider_mapping_id,
            self.contract_version_id,
            self.economic_subject_id,
            self.source_order_scope_id,
        )
        if self.provider != self.subject.provider:
            raise ValueError("quote provider provenance mismatch")
        if self.provider_contract_key != self.subject.provider_contract_key:
            raise ValueError("quote provider key provenance mismatch")
        if self.provider_mapping_id != self.subject.provider_mapping.mapping_id:
            raise ValueError("quote provider mapping provenance mismatch")
        if self.contract_version_id != self.subject.contract_version.version_id:
            raise ValueError("quote contract version provenance mismatch")
        if self.economic_subject_id != self.subject.economic_subject_id:
            raise ValueError("quote economic subject provenance mismatch")
        expected = {
            UnderlyingQuoteObservationV1: (MarketSubjectKind.UNDERLYING, "underlying_quote_observation"),
            FuturesQuoteObservationV1: (MarketSubjectKind.FUTURE, "futures_quote_observation"),
            OptionQuoteObservationV1: (MarketSubjectKind.OPTION, "option_quote_observation"),
        }.get(type(self))
        if expected is None or self.subject.instrument_kind is not expected[0] or self.identity.event_type != expected[1]:
            raise ValueError("quote class, subject kind, and event type mismatch")
        if self.feed_response_type is FeedResponseType.MARKET_INFO:
            raise ValueError("market_info cannot produce quote observations")
        expected_snapshot = self.feed_response_type is FeedResponseType.INITIAL_FEED
        if self.is_snapshot is not expected_snapshot:
            raise ValueError("quote snapshot flag does not match response type")
        if not isinstance(self.source_order, int) or isinstance(self.source_order, bool) or self.source_order < 0:
            raise ValueError("source_order must be a non-negative integer")
        if self.provider_sequence is not None or self.supersedes_event_id is not None:
            raise ValueError("provider sequence and supersession must be absent")
        if self.normalization_schema_version != NORMALIZATION_SCHEMA_VERSION:
            raise ValueError("unsupported normalization schema version")
        if self.identity.normalization_schema_version != self.normalization_schema_version:
            raise ValueError("quote identity schema version mismatch")
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
        if not isinstance(self.identity, NormalizedMarketEventIdentity):
            raise TypeError("status identity type is required")
        if self.identity.raw_event_id != self.raw_event_id or self.identity.event_type != "market_segment_status_observation":
            raise ValueError("normalized status identity mismatch")
        if not self.provider or not self.segment or not self.provider_status_name:
            raise ValueError("status identity fields are required")
        _require_text(self.provider, self.segment, self.source_order_scope_id)
        expected_subject_id = market_segment_status_subject_id(self.provider, self.segment)
        if self.identity.subject_id != expected_subject_id:
            raise ValueError("normalized status subject identity mismatch")
        if not isinstance(self.source_order, int) or isinstance(self.source_order, bool) or self.source_order < 0:
            raise ValueError("source_order must be a non-negative integer")
        if not isinstance(self.provider_status_numeric, int) or isinstance(self.provider_status_numeric, bool):
            raise ValueError("provider status numeric value must be an integer")
        if not isinstance(self.status_is_known, bool):
            raise ValueError("status_is_known must be boolean")
        for name in ("provider_timestamp", "available_at", "recorded_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
            if self.available_at < self.received_at:
                raise ValueError("available_at cannot precede received_at")
        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at cannot precede available_at")
        if self.normalization_schema_version != NORMALIZATION_SCHEMA_VERSION:
            raise ValueError("unsupported normalization schema version")
        if self.identity.normalization_schema_version != self.normalization_schema_version:
            raise ValueError("status identity schema version mismatch")
        if self.normalizer_implementation_version != NORMALIZER_IMPLEMENTATION_VERSION:
            raise ValueError("normalizer implementation semantics mismatch")
        expected_name = PROVIDER_MARKET_STATUS_NAMES.get(self.provider_status_numeric)
        if expected_name is None:
            if self.provider_status_name != "UNKNOWN" or self.status_is_known:
                raise ValueError("unknown provider status semantics mismatch")
        elif self.provider_status_name != expected_name or not self.status_is_known:
            raise ValueError("known provider status semantics mismatch")

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


def market_segment_status_subject_id(provider: str, segment: str) -> str:
    _require_text(provider, segment)
    return stable_hash({"entity": "provider_market_segment", "provider": provider, "segment": segment})


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("normalization text values must be non-empty")
