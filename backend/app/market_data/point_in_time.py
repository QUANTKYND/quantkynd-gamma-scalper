from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

from app.core.hashing import stable_hash
from app.instruments.identity import (
    OptionContractIdentity,
    OptionContractVersion,
    ProviderContractMapping,
)


class AvailabilityBasis(StrEnum):
    RECEIVED = "received"
    PROVIDER_DISSEMINATED = "provider_disseminated"
    HISTORICAL_IMPORT = "historical_import"

    @property
    def is_defensible_knowledge_time(self) -> bool:
        return self in {self.RECEIVED, self.PROVIDER_DISSEMINATED}


class QuoteQualityDisposition(StrEnum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_FLAGS = "accepted_with_flags"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"

    @property
    def is_eligible(self) -> bool:
        return self in {self.ACCEPTED, self.ACCEPTED_WITH_FLAGS}


@dataclass(frozen=True)
class MarketEventTime:
    exchange_timestamp: datetime
    available_at: datetime
    recorded_at: datetime
    received_at: datetime | None
    availability_basis: AvailabilityBasis

    def __post_init__(self) -> None:
        object.__setattr__(self, "availability_basis", AvailabilityBasis(self.availability_basis))
        for field_name in ("exchange_timestamp", "available_at", "recorded_at"):
            object.__setattr__(self, field_name, _utc(getattr(self, field_name), field_name))
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at cannot precede available_at")
        if (
            self.availability_basis is AvailabilityBasis.RECEIVED
            and self.received_at is None
        ):
            raise ValueError("received availability requires received_at")
        if self.received_at is not None and self.available_at < self.received_at:
            raise ValueError("available_at cannot precede received_at")

    @property
    def has_defensible_knowledge_time(self) -> bool:
        return self.availability_basis.is_defensible_knowledge_time


@dataclass(frozen=True)
class PointInTimeQuery:
    market_as_of: datetime
    known_as_of: datetime | None
    quality_policy_id: str
    quality_policy_version: int
    require_defensible_availability: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "market_as_of", _utc(self.market_as_of, "market_as_of"))
        if self.known_as_of is not None:
            object.__setattr__(self, "known_as_of", _utc(self.known_as_of, "known_as_of"))
        if not self.quality_policy_id:
            raise ValueError("quality_policy_id is required")
        if (
            not isinstance(self.quality_policy_version, int)
            or isinstance(self.quality_policy_version, bool)
            or self.quality_policy_version <= 0
        ):
            raise ValueError("quality_policy_version must be positive")

    @property
    def mode(self) -> str:
        return "known_as_of" if self.known_as_of is not None else "market_as_of"


@dataclass(frozen=True)
class RawMarketObservationIdentity:
    provider: str
    content_hash: str
    connection_id: str | None = None
    provider_event_id: str | None = None
    provider_sequence: int | None = None
    source_file_id: str | None = None
    source_row_id: str | None = None
    ingestion_event_id: str | None = None

    def __post_init__(self) -> None:
        if not self.provider or not self.content_hash:
            raise ValueError("provider and content_hash are required")
        if self.provider_sequence is not None and (
            not isinstance(self.provider_sequence, int)
            or isinstance(self.provider_sequence, bool)
            or self.provider_sequence < 0
        ):
            raise ValueError("provider_sequence must be non-negative")
        if (self.source_file_id is None) != (self.source_row_id is None):
            raise ValueError("batch identity requires source_file_id and source_row_id")
        if not any(
            (
                self.provider_event_id,
                self.provider_sequence is not None,
                self.source_file_id,
                self.ingestion_event_id,
            )
        ):
            raise ValueError("an explicit provider, batch, or ingestion event identity is required")

    @property
    def raw_event_id(self) -> str:
        if self.provider_event_id is not None:
            identity_type = "provider_event_id"
            identity_value: object = self.provider_event_id
        elif self.provider_sequence is not None:
            identity_type = "provider_sequence"
            identity_value = {
                "connection_id": self.connection_id,
                "provider_sequence": self.provider_sequence,
            }
        elif self.source_file_id is not None:
            identity_type = "source_row"
            identity_value = {
                "source_file_id": self.source_file_id,
                "source_row_id": self.source_row_id,
            }
        else:
            identity_type = "ingestion_event_id"
            identity_value = self.ingestion_event_id
        return stable_hash(
            {
                "entity": "raw_market_observation",
                "provider": self.provider,
                "identity_type": identity_type,
                "identity_value": identity_value,
            }
        )


@dataclass(frozen=True)
class NormalizedMarketEventIdentity:
    raw_event_id: str
    event_type: str
    subject_id: str
    normalization_schema_version: int

    def __post_init__(self) -> None:
        if not self.raw_event_id or not self.event_type or not self.subject_id:
            raise ValueError("normalized event identity fields are required")
        if (
            not isinstance(self.normalization_schema_version, int)
            or isinstance(self.normalization_schema_version, bool)
            or self.normalization_schema_version <= 0
        ):
            raise ValueError("normalization_schema_version must be positive")

    @property
    def event_id(self) -> str:
        return stable_hash(
            {
                "entity": "normalized_market_event",
                "raw_event_id": self.raw_event_id,
                "event_type": self.event_type,
                "subject_id": self.subject_id,
                "normalization_schema_version": self.normalization_schema_version,
            }
        )


@dataclass(frozen=True)
class DataQualityAssessment:
    assessment_run_id: str
    event_id: str
    quality_policy_id: str
    quality_policy_version: int
    disposition: QuoteQualityDisposition
    reason_codes: tuple[str, ...]
    assessed_at: datetime
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", QuoteQualityDisposition(self.disposition))
        if not self.assessment_run_id or not self.event_id or not self.quality_policy_id:
            raise ValueError("quality assessment identity fields are required")
        if (
            not isinstance(self.quality_policy_version, int)
            or isinstance(self.quality_policy_version, bool)
            or self.quality_policy_version <= 0
        ):
            raise ValueError("quality_policy_version must be positive")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("quality reason codes must be unique")
        object.__setattr__(self, "reason_codes", tuple(sorted(self.reason_codes)))
        object.__setattr__(self, "assessed_at", _utc(self.assessed_at, "assessed_at"))
        object.__setattr__(self, "recorded_at", _utc(self.recorded_at, "recorded_at"))
        if self.recorded_at < self.assessed_at:
            raise ValueError("quality recorded_at cannot precede assessed_at")

    @property
    def assessment_id(self) -> str:
        return stable_hash(
            {
                "entity": "data_quality_assessment",
                "assessment_run_id": self.assessment_run_id,
                "event_id": self.event_id,
                "quality_policy_id": self.quality_policy_id,
                "quality_policy_version": self.quality_policy_version,
                "disposition": self.disposition.value,
                "reason_codes": self.reason_codes,
            }
        )


@dataclass(frozen=True)
class PointInTimeOptionQuote:
    identity: NormalizedMarketEventIdentity
    contract: OptionContractIdentity
    contract_version_id: str
    provider_mapping_id: str
    event_time: MarketEventTime
    bid_price: Decimal | None = None
    bid_size_contracts: int | None = None
    ask_price: Decimal | None = None
    ask_size_contracts: int | None = None
    last_price: Decimal | None = None
    last_size_contracts: int | None = None
    volume_contracts: int | None = None
    open_interest_contracts: int | None = None
    provider_sequence: int | None = None
    event_order: int | None = None
    supersedes_event_id: str | None = None

    def __post_init__(self) -> None:
        if self.identity.subject_id != self.contract.contract_id:
            raise ValueError("quote subject must match economic contract identity")
        if not self.contract_version_id or not self.provider_mapping_id:
            raise ValueError("quote contract version and provider mapping are required")
        for field_name in ("bid_price", "ask_price", "last_price"):
            _optional_positive_decimal(getattr(self, field_name), field_name)
        for field_name in (
            "bid_size_contracts",
            "ask_size_contracts",
            "last_size_contracts",
            "volume_contracts",
            "open_interest_contracts",
            "provider_sequence",
            "event_order",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be non-negative")

    @property
    def event_id(self) -> str:
        return self.identity.event_id


def reconstruct_option_chain(
    quotes: Iterable[PointInTimeOptionQuote],
    contract_versions: Iterable[OptionContractVersion],
    provider_mappings: Iterable[ProviderContractMapping],
    quality_assessments: Iterable[DataQualityAssessment],
    query: PointInTimeQuery,
) -> tuple[PointInTimeOptionQuote, ...]:
    versions = {item.version_id: item for item in contract_versions}
    mappings = {item.mapping_id: item for item in provider_mappings}
    assessments = tuple(quality_assessments)
    visible = [
        quote
        for quote in quotes
        if _quote_is_visible(quote, versions, mappings, assessments, query)
    ]
    superseded_ids = {
        quote.supersedes_event_id
        for quote in visible
        if quote.supersedes_event_id is not None
    }
    latest_by_contract: dict[str, PointInTimeOptionQuote] = {}
    for quote in visible:
        if quote.event_id in superseded_ids:
            continue
        contract_id = quote.contract.contract_id
        current = latest_by_contract.get(contract_id)
        if current is None or _quote_order(quote) > _quote_order(current):
            latest_by_contract[contract_id] = quote
    return tuple(
        sorted(
            latest_by_contract.values(),
            key=lambda quote: (
                quote.contract.expiry,
                quote.contract.strike,
                quote.contract.option_side.value,
            ),
        )
    )


def _quote_is_visible(
    quote: PointInTimeOptionQuote,
    versions: dict[str, OptionContractVersion],
    mappings: dict[str, ProviderContractMapping],
    assessments: tuple[DataQualityAssessment, ...],
    query: PointInTimeQuery,
) -> bool:
    version = versions.get(quote.contract_version_id)
    mapping = mappings.get(quote.provider_mapping_id)
    if version is None or mapping is None:
        return False
    if version.contract_id != quote.contract.contract_id:
        return False
    if mapping.contract_version_id != version.version_id:
        return False
    if not version.effective_at(query.market_as_of, query.known_as_of):
        return False
    if not mapping.effective_at(query.market_as_of, query.known_as_of):
        return False
    if quote.event_time.exchange_timestamp > query.market_as_of:
        return False
    if query.known_as_of is not None:
        if quote.event_time.available_at > query.known_as_of:
            return False
        if query.require_defensible_availability and not quote.event_time.has_defensible_knowledge_time:
            return False
    assessment = _selected_assessment(quote.event_id, assessments, query)
    return assessment is not None and assessment.disposition.is_eligible


def _selected_assessment(
    event_id: str,
    assessments: tuple[DataQualityAssessment, ...],
    query: PointInTimeQuery,
) -> DataQualityAssessment | None:
    candidates = [
        assessment
        for assessment in assessments
        if assessment.event_id == event_id
        and assessment.quality_policy_id == query.quality_policy_id
        and assessment.quality_policy_version == query.quality_policy_version
        and (query.known_as_of is None or assessment.recorded_at <= query.known_as_of)
    ]
    return max(
        candidates,
        key=lambda assessment: (assessment.recorded_at, assessment.assessment_id),
        default=None,
    )


def _quote_order(
    quote: PointInTimeOptionQuote,
) -> tuple[datetime, int, int, datetime, datetime, str]:
    return (
        quote.event_time.exchange_timestamp,
        quote.provider_sequence if quote.provider_sequence is not None else -1,
        quote.event_order if quote.event_order is not None else -1,
        quote.event_time.received_at or quote.event_time.available_at,
        quote.event_time.available_at,
        quote.event_id,
    )


def _optional_positive_decimal(value: Decimal | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be positive and finite")


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
