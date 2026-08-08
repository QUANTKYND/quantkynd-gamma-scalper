from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, Self, TypeAlias
from zoneinfo import ZoneInfo

from app.core.hashing import stable_hash
from app.market_data.persistence.planner import ParameterChunk, plan_parameter_chunks
from app.market_data.quality.contracts import (
    AssessmentIdentity,
    AssessmentRunIdentity,
    DependencyIdentity,
    DependencyOutcome,
    EvaluationContext,
    MARKET_TIME_BASIS,
    ReasonDefinitionIdentity,
    ReasonOccurrenceIdentity,
    ReceiptBasis,
    TargetKind,
    reduce_disposition,
)
from app.market_data.quality.dependency_resolution import RankedCandidate, TemporalCandidate
from app.market_data.quality.evaluator import (
    ConnectionFact,
    MarketStatusFact,
    ProvenanceDependencyFact,
    QualityEvaluationInput,
    QualityEvaluationResult,
    QualityReasonOccurrence,
    QuoteTarget,
    SessionFact,
    StatusTarget,
    SubjectScopeFact,
    SubscriptionFact,
    SubscriptionResolutionState,
    TargetDependencies,
    evaluate_quality,
)
from app.market_data.quality.policy_schema import ParsedQualityPolicy

_SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTROLLED = re.compile(r"[A-Za-z0-9_.:/-]+\Z")
_SNAKE_CASE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
_BOOTSTRAP_REVISION = "20260804_05"

DATA15_ADVISORY_LOCK_NAMESPACE = -806150233
DATA15_LOCK_STRIPE_COUNT = 128
QUALITY_AUDIT_CURSOR_SCHEMA_VERSION = 1


class ReceiptTargetKind(StrEnum):
    PROVIDER_MAPPING_RECORD = "provider_mapping_record"
    INSTRUMENT_VERSION_RECORD = "instrument_version_record"
    CATALOGUE_VERSION_RECORD = "catalogue_version_record"
    TRADING_SESSION_RECORD = "trading_session_record"


class DependencyKind(StrEnum):
    PROVIDER_MAPPING = "provider_mapping"
    INSTRUMENT_VERSION = "instrument_version"
    CATALOGUE_VERSION = "catalogue_version"
    CATALOGUE_MEMBERSHIP = "catalogue_membership"
    TRADING_SESSION = "trading_session"
    MARKET_SEGMENT_STATUS = "market_segment_status"
    CONNECTION_SESSION = "connection_session"
    SUBSCRIPTION_SCOPE = "subscription_scope"


class LockEntityNamespace(StrEnum):
    POLICY_VERSION = "policy_version"
    ASSESSMENT = "assessment"
    ASSESSMENT_RUN = "assessment_run"


DEPENDENCY_KIND_ORDER = (
    DependencyKind.PROVIDER_MAPPING,
    DependencyKind.INSTRUMENT_VERSION,
    DependencyKind.CATALOGUE_VERSION,
    DependencyKind.CATALOGUE_MEMBERSHIP,
    DependencyKind.TRADING_SESSION,
    DependencyKind.MARKET_SEGMENT_STATUS,
    DependencyKind.CONNECTION_SESSION,
    DependencyKind.SUBSCRIPTION_SCOPE,
)
_DEPENDENCY_KIND_ORDINAL = {
    kind: ordinal for ordinal, kind in enumerate(DEPENDENCY_KIND_ORDER)
}


class WriteFamily(StrEnum):
    ASSESSMENTS = "assessments"
    REASONS = "reasons"
    DEPENDENCIES = "dependencies"
    CANDIDATES = "candidates"
    MEMBERSHIPS = "memberships"


@dataclass(frozen=True)
class TemporalRecordReceipt:
    target_kind: ReceiptTargetKind
    record_id: str
    receipt_at: datetime
    receipt_basis: ReceiptBasis
    bootstrap_revision: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_kind", ReceiptTargetKind(self.target_kind))
        _sha256(self.record_id, "record_id")
        object.__setattr__(self, "receipt_at", _utc(self.receipt_at, "receipt_at"))
        object.__setattr__(self, "receipt_basis", ReceiptBasis(self.receipt_basis))
        _validate_receipt_basis(self.receipt_basis, self.bootstrap_revision)

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "target_kind": self.target_kind.value,
            "record_id": self.record_id,
            "receipt_at": self.receipt_at,
            "receipt_basis": self.receipt_basis.value,
            "bootstrap_revision": self.bootstrap_revision,
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class CatalogueMembershipReceipt:
    membership_id: str
    ingestion_run_id: str
    receipt_at: datetime
    receipt_basis: ReceiptBasis
    bootstrap_revision: str | None = None

    def __post_init__(self) -> None:
        _sha256(self.membership_id, "membership_id")
        _sha256(self.ingestion_run_id, "ingestion_run_id")
        object.__setattr__(self, "receipt_at", _utc(self.receipt_at, "receipt_at"))
        object.__setattr__(self, "receipt_basis", ReceiptBasis(self.receipt_basis))
        _validate_receipt_basis(self.receipt_basis, self.bootstrap_revision)

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "membership_id": self.membership_id,
            "ingestion_run_id": self.ingestion_run_id,
            "receipt_at": self.receipt_at,
            "receipt_basis": self.receipt_basis.value,
            "bootstrap_revision": self.bootstrap_revision,
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class MappingScope:
    provider: str
    provider_contract_key: str

    def __post_init__(self) -> None:
        _controlled(self.provider, "provider")
        _opaque(self.provider_contract_key, "provider_contract_key")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.PROVIDER_MAPPING.value,
            "provider": self.provider,
            "provider_contract_key": self.provider_contract_key,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class InstrumentScope:
    instrument_id: str

    def __post_init__(self) -> None:
        _sha256(self.instrument_id, "instrument_id")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.INSTRUMENT_VERSION.value,
            "instrument_id": self.instrument_id,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class CatalogueScope:
    provider: str

    def __post_init__(self) -> None:
        _controlled(self.provider, "provider")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.CATALOGUE_VERSION.value,
            "provider": self.provider,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class MembershipScope:
    catalogue_version_id: str
    provider_contract_key: str
    economic_subject_id: str
    contract_version_id: str
    market_cutoff: datetime
    knowledge_cutoff: datetime
    ingestion_profile: str = "upstox-nse-nifty-index-derivatives-v1"

    def __post_init__(self) -> None:
        for name in (
            "catalogue_version_id",
            "economic_subject_id",
            "contract_version_id",
        ):
            _sha256(getattr(self, name), name)
        _opaque(self.provider_contract_key, "provider_contract_key")
        object.__setattr__(
            self,
            "market_cutoff",
            _utc(self.market_cutoff, "market_cutoff"),
        )
        object.__setattr__(
            self,
            "knowledge_cutoff",
            _utc(self.knowledge_cutoff, "knowledge_cutoff"),
        )
        if self.knowledge_cutoff < self.market_cutoff:
            raise ValueError("knowledge_cutoff cannot precede market_cutoff")
        _controlled(self.ingestion_profile, "ingestion_profile")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.CATALOGUE_MEMBERSHIP.value,
            "catalogue_version_id": self.catalogue_version_id,
            "provider_contract_key": self.provider_contract_key,
            "economic_subject_id": self.economic_subject_id,
            "contract_version_id": self.contract_version_id,
            "ingestion_profile": self.ingestion_profile,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class SessionScope:
    exchange: str
    session_date: date
    session_kind: str
    market_cutoff: datetime

    def __post_init__(self) -> None:
        _controlled(self.exchange, "exchange")
        if not isinstance(self.session_date, date) or isinstance(self.session_date, datetime):
            raise TypeError("session_date must be a date")
        _controlled(self.session_kind, "session_kind")
        object.__setattr__(
            self,
            "market_cutoff",
            _utc(self.market_cutoff, "market_cutoff"),
        )
        expected_date = self.market_cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date()
        if self.session_date != expected_date:
            raise ValueError("session_date must be derived from market_cutoff in Asia/Kolkata")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.TRADING_SESSION.value,
            "exchange": self.exchange,
            "session_date": self.session_date,
            "session_kind": self.session_kind,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class SegmentScope:
    provider: str
    segment: str

    def __post_init__(self) -> None:
        _controlled(self.provider, "provider")
        _controlled(self.segment, "segment")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.MARKET_SEGMENT_STATUS.value,
            "provider": self.provider,
            "segment": self.segment,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class ConnectionScope:
    provider: str
    connection_session_id: str

    def __post_init__(self) -> None:
        _controlled(self.provider, "provider")
        _opaque(self.connection_session_id, "connection_session_id")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.CONNECTION_SESSION.value,
            "provider": self.provider,
            "connection_session_id": self.connection_session_id,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class SubscriptionScope:
    provider: str
    connection_session_id: str
    provider_contract_key: str
    request_mode: str

    def __post_init__(self) -> None:
        _controlled(self.provider, "provider")
        _opaque(self.connection_session_id, "connection_session_id")
        _opaque(self.provider_contract_key, "provider_contract_key")
        _controlled(self.request_mode, "request_mode")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": DependencyKind.SUBSCRIPTION_SCOPE.value,
            "provider": self.provider,
            "connection_session_id": self.connection_session_id,
            "provider_contract_key": self.provider_contract_key,
            "request_mode": self.request_mode,
        }

    @property
    def search_scope_hash(self) -> str:
        return stable_hash(self.canonical_payload)


QueryScope: TypeAlias = (
    MappingScope
    | InstrumentScope
    | CatalogueScope
    | MembershipScope
    | SessionScope
    | SegmentScope
    | ConnectionScope
    | SubscriptionScope
)


@dataclass(frozen=True)
class MarketEventCandidateReference:
    event_id: str
    result_id: str
    raw_event_id: str

    def __post_init__(self) -> None:
        for name in ("event_id", "result_id", "raw_event_id"):
            _sha256(getattr(self, name), name)

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset({DependencyKind.MARKET_SEGMENT_STATUS})

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "market_event_id": self.event_id,
            "market_result_id": self.result_id,
            "market_raw_event_id": self.raw_event_id,
        }


@dataclass(frozen=True)
class ProviderMappingCandidateReference:
    record_id: str
    mapping_id: str

    def __post_init__(self) -> None:
        _sha256(self.record_id, "record_id")
        _sha256(self.mapping_id, "mapping_id")

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset({DependencyKind.PROVIDER_MAPPING})

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "provider_mapping_record_id": self.record_id,
            "provider_mapping_id": self.mapping_id,
        }


@dataclass(frozen=True)
class InstrumentVersionCandidateReference:
    record_id: str
    version_id: str

    def __post_init__(self) -> None:
        _sha256(self.record_id, "record_id")
        _sha256(self.version_id, "version_id")

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset({DependencyKind.INSTRUMENT_VERSION})

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "instrument_version_record_id": self.record_id,
            "instrument_version_id": self.version_id,
        }


@dataclass(frozen=True)
class CatalogueCandidateReference:
    record_id: str
    catalogue_version_id: str
    ingestion_run_id: str

    def __post_init__(self) -> None:
        for name in ("record_id", "catalogue_version_id", "ingestion_run_id"):
            _sha256(getattr(self, name), name)

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset({DependencyKind.CATALOGUE_VERSION})

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "catalogue_record_id": self.record_id,
            "catalogue_version_id": self.catalogue_version_id,
            "catalogue_ingestion_run_id": self.ingestion_run_id,
        }


@dataclass(frozen=True)
class CatalogueMembershipCandidateReference:
    membership_id: str
    ingestion_run_id: str

    def __post_init__(self) -> None:
        _sha256(self.membership_id, "membership_id")
        _sha256(self.ingestion_run_id, "ingestion_run_id")

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset({DependencyKind.CATALOGUE_MEMBERSHIP})

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "catalogue_membership_id": self.membership_id,
            "catalogue_ingestion_run_id": self.ingestion_run_id,
        }


@dataclass(frozen=True)
class TradingSessionCandidateReference:
    record_id: str
    session_version_id: str

    def __post_init__(self) -> None:
        _sha256(self.record_id, "record_id")
        _sha256(self.session_version_id, "session_version_id")

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset({DependencyKind.TRADING_SESSION})

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "trading_session_record_id": self.record_id,
            "trading_session_version_id": self.session_version_id,
        }


@dataclass(frozen=True)
class LifecycleCandidateReference:
    event_id: str
    lifecycle_kind: str
    batch_id: str
    instrument_keys_digest: str | None = None

    def __post_init__(self) -> None:
        _sha256(self.event_id, "event_id")
        _controlled(self.lifecycle_kind, "lifecycle_kind")
        _sha256(self.batch_id, "batch_id")
        if self.instrument_keys_digest is not None:
            _sha256(self.instrument_keys_digest, "instrument_keys_digest")

    @property
    def candidate_kind(self) -> frozenset[DependencyKind]:
        return frozenset(
            {DependencyKind.CONNECTION_SESSION, DependencyKind.SUBSCRIPTION_SCOPE}
        )

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "lifecycle_event_id": self.event_id,
            "lifecycle_kind": self.lifecycle_kind,
            "lifecycle_batch_id": self.batch_id,
            "instrument_keys_digest": self.instrument_keys_digest,
        }


CandidateReference: TypeAlias = (
    MarketEventCandidateReference
    | ProviderMappingCandidateReference
    | InstrumentVersionCandidateReference
    | CatalogueCandidateReference
    | CatalogueMembershipCandidateReference
    | TradingSessionCandidateReference
    | LifecycleCandidateReference
)


@dataclass(frozen=True)
class TemporalDependencyCandidate:
    dependency_kind: DependencyKind
    candidate: TemporalCandidate
    reference: CandidateReference

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_kind", DependencyKind(self.dependency_kind))
        if self.dependency_kind not in {
            DependencyKind.PROVIDER_MAPPING,
            DependencyKind.INSTRUMENT_VERSION,
            DependencyKind.CATALOGUE_VERSION,
            DependencyKind.TRADING_SESSION,
        }:
            raise ValueError("temporal candidate uses a non-temporal dependency kind")
        if not isinstance(self.candidate, TemporalCandidate):
            raise TypeError("candidate must be TemporalCandidate")
        _validate_reference_kind(self.dependency_kind, self.reference)
        record_id = getattr(self.reference, "record_id", None)
        if record_id != self.candidate.record_id:
            raise ValueError("temporal candidate record/reference mismatch")
        semantic_id = {
            DependencyKind.PROVIDER_MAPPING: getattr(self.reference, "mapping_id", None),
            DependencyKind.INSTRUMENT_VERSION: getattr(self.reference, "version_id", None),
            DependencyKind.CATALOGUE_VERSION: getattr(
                self.reference, "catalogue_version_id", None
            ),
            DependencyKind.TRADING_SESSION: getattr(
                self.reference, "session_version_id", None
            ),
        }[self.dependency_kind]
        if semantic_id != self.candidate.semantic_id:
            raise ValueError("temporal candidate semantic/reference mismatch")

    @property
    def candidate_id(self) -> str:
        return self.candidate.record_id

    @property
    def candidate_content_hash(self) -> str:
        return self.candidate.content_hash

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": self.dependency_kind.value,
            "candidate_id": self.candidate_id,
            "candidate_content_hash": self.candidate_content_hash,
            "recorded_at": self.candidate.recorded_at,
            "receipt_at": self.candidate.receipt_at,
            "valid_from": self.candidate.valid_from,
            "valid_until": self.candidate.valid_until,
            "supersedes_record_id": self.candidate.supersedes_record_id,
            "semantic_id": self.candidate.semantic_id,
            "scope_id": self.candidate.scope_id,
            "candidate_payload": _thaw(self.candidate.payload),
            "reference": self.reference.canonical_payload,
        }


@dataclass(frozen=True)
class RankedDependencyCandidate:
    dependency_kind: DependencyKind
    candidate: RankedCandidate
    available_at: datetime
    persistence_recorded_at: datetime
    reference: CandidateReference

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_kind", DependencyKind(self.dependency_kind))
        if self.dependency_kind not in {
            DependencyKind.MARKET_SEGMENT_STATUS,
            DependencyKind.CONNECTION_SESSION,
            DependencyKind.SUBSCRIPTION_SCOPE,
        }:
            raise ValueError("ranked candidate uses a non-ranked dependency kind")
        if not isinstance(self.candidate, RankedCandidate):
            raise TypeError("candidate must be RankedCandidate")
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        object.__setattr__(
            self,
            "persistence_recorded_at",
            _utc(self.persistence_recorded_at, "persistence_recorded_at"),
        )
        if self.persistence_recorded_at < self.available_at:
            raise ValueError("persistence_recorded_at cannot precede available_at")
        _validate_reference_kind(self.dependency_kind, self.reference)
        if isinstance(self.reference, LifecycleCandidateReference):
            if self.dependency_kind is DependencyKind.CONNECTION_SESSION:
                if (
                    self.reference.lifecycle_kind != "connection"
                    or self.reference.instrument_keys_digest is not None
                ):
                    raise ValueError("connection candidate lifecycle shape mismatch")
            elif (
                self.reference.lifecycle_kind != "subscription"
                or self.reference.instrument_keys_digest is None
            ):
                raise ValueError("subscription candidate lifecycle shape mismatch")
        event_id = getattr(self.reference, "event_id", None)
        if event_id != self.candidate.candidate_id:
            raise ValueError("ranked candidate identity/reference mismatch")

    @property
    def candidate_id(self) -> str:
        return self.candidate.candidate_id

    @property
    def candidate_content_hash(self) -> str:
        return self.candidate.content_hash

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": self.dependency_kind.value,
            "candidate_id": self.candidate_id,
            "candidate_content_hash": self.candidate_content_hash,
            "effective_at": self.candidate.effective_at,
            "source_order_scope_id": self.candidate.source_order_scope_id,
            "source_order": self.candidate.source_order,
            "available_at": self.available_at,
            "persistence_recorded_at": self.persistence_recorded_at,
            "candidate_payload": _thaw(self.candidate.payload),
            "reference": self.reference.canonical_payload,
        }


@dataclass(frozen=True)
class MembershipDependencyCandidate:
    dependency_kind: DependencyKind
    membership_id: str
    receipt_at: datetime
    content_hash: str
    payload: Mapping[str, object]
    reference: CatalogueMembershipCandidateReference

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_kind", DependencyKind(self.dependency_kind))
        if self.dependency_kind is not DependencyKind.CATALOGUE_MEMBERSHIP:
            raise ValueError("membership candidate kind mismatch")
        _sha256(self.membership_id, "membership_id")
        object.__setattr__(self, "receipt_at", _utc(self.receipt_at, "receipt_at"))
        _sha256(self.content_hash, "content_hash")
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        if self.reference.membership_id != self.membership_id:
            raise ValueError("membership candidate identity/reference mismatch")

    @property
    def candidate_id(self) -> str:
        return self.membership_id

    @property
    def candidate_content_hash(self) -> str:
        return self.content_hash

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "dependency_kind": self.dependency_kind.value,
            "candidate_id": self.candidate_id,
            "candidate_content_hash": self.candidate_content_hash,
            "receipt_at": self.receipt_at,
            "candidate_payload": _thaw(self.payload),
            "reference": self.reference.canonical_payload,
        }


DependencyCandidate: TypeAlias = (
    TemporalDependencyCandidate
    | RankedDependencyCandidate
    | MembershipDependencyCandidate
)


@dataclass(frozen=True)
class DependencyCandidates:
    dependency_kind: DependencyKind
    subject_key: str
    scope: QueryScope
    market_cutoff: datetime
    knowledge_cutoff: datetime
    selection_rule_version: str
    candidates: tuple[DependencyCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_kind", DependencyKind(self.dependency_kind))
        _snake_case(self.subject_key, "subject_key")
        _validate_scope_kind(self.dependency_kind, self.scope)
        object.__setattr__(self, "market_cutoff", _utc(self.market_cutoff, "market_cutoff"))
        object.__setattr__(
            self,
            "knowledge_cutoff",
            _utc(self.knowledge_cutoff, "knowledge_cutoff"),
        )
        _controlled(self.selection_rule_version, "selection_rule_version")
        expected_rule = {
            DependencyKind.PROVIDER_MAPPING: "temporal-successor-graph-with-receipt-v1",
            DependencyKind.INSTRUMENT_VERSION: "temporal-successor-graph-with-receipt-v1",
            DependencyKind.CATALOGUE_VERSION: "temporal-successor-graph-with-receipt-v1",
            DependencyKind.TRADING_SESSION: "temporal-successor-graph-with-receipt-v1",
            DependencyKind.CATALOGUE_MEMBERSHIP: "catalogue-membership-profile-v1",
            DependencyKind.MARKET_SEGMENT_STATUS: "ranked-market-status-v1",
            DependencyKind.CONNECTION_SESSION: "ranked-connection-lifecycle-v1",
            DependencyKind.SUBSCRIPTION_SCOPE: "staged-subscription-scope-v1",
        }[self.dependency_kind]
        if self.selection_rule_version != expected_rule:
            raise ValueError("selection_rule_version does not match dependency kind")
        expected_subject = {
            DependencyKind.PROVIDER_MAPPING: "provider_mapping",
            DependencyKind.INSTRUMENT_VERSION: "instrument_version",
            DependencyKind.CATALOGUE_VERSION: "catalogue_version",
            DependencyKind.CATALOGUE_MEMBERSHIP: "catalogue_membership",
            DependencyKind.TRADING_SESSION: "trading_session",
            DependencyKind.MARKET_SEGMENT_STATUS: "market_segment_status",
            DependencyKind.CONNECTION_SESSION: "connection_session",
            DependencyKind.SUBSCRIPTION_SCOPE: "subscription_scope",
        }[self.dependency_kind]
        if self.subject_key != expected_subject:
            raise ValueError("subject_key does not match dependency kind")
        if self.knowledge_cutoff < self.market_cutoff:
            raise ValueError("knowledge_cutoff cannot precede market_cutoff")
        if isinstance(self.scope, MembershipScope):
            if (
                self.scope.market_cutoff != self.market_cutoff
                or self.scope.knowledge_cutoff != self.knowledge_cutoff
            ):
                raise ValueError("membership scope cutoffs do not match candidate cutoffs")
        if isinstance(self.scope, SessionScope) and self.scope.market_cutoff != self.market_cutoff:
            raise ValueError("session scope market cutoff does not match candidate cutoff")
        ordered = tuple(sorted(self.candidates, key=lambda item: item.candidate_id))
        if len(ordered) > 5000:
            raise ValueError("dependency candidates are limited to 5000")
        if self.dependency_kind is DependencyKind.CATALOGUE_MEMBERSHIP and len(ordered) > 1:
            raise ValueError("catalogue membership dependency permits at most one candidate")
        if len({item.candidate_id for item in ordered}) != len(ordered):
            raise ValueError("dependency candidate IDs must be unique")
        for item in ordered:
            if item.dependency_kind is not self.dependency_kind:
                raise ValueError("dependency candidate kind mismatch")
            if isinstance(item, TemporalDependencyCandidate):
                if item.candidate.recorded_at > self.knowledge_cutoff:
                    raise ValueError("temporal candidate is after knowledge cutoff")
                if item.candidate.receipt_at > self.knowledge_cutoff:
                    raise ValueError("temporal receipt is after knowledge cutoff")
            elif isinstance(item, RankedDependencyCandidate):
                if item.candidate.effective_at > self.market_cutoff:
                    raise ValueError("ranked candidate is after market cutoff")
                if item.available_at > self.knowledge_cutoff:
                    raise ValueError("ranked candidate is after knowledge cutoff")
                if item.persistence_recorded_at > self.knowledge_cutoff:
                    raise ValueError("ranked persistence is after knowledge cutoff")
            elif item.receipt_at > self.knowledge_cutoff:
                raise ValueError("membership receipt is after knowledge cutoff")
        object.__setattr__(self, "candidates", ordered)

    @property
    def search_scope_payload(self) -> Mapping[str, object]:
        return _freeze_mapping(self.scope.canonical_payload)

    @property
    def search_scope_hash(self) -> str:
        return self.scope.search_scope_hash

    @property
    def candidate_set_hash(self) -> str:
        return stable_hash(tuple(item.canonical_payload for item in self.candidates))


@dataclass(frozen=True)
class PolicyRegistrationBundle:
    policy: ParsedQualityPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ParsedQualityPolicy):
            raise TypeError("policy must be ParsedQualityPolicy")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy.policy_id,
            "policy_version_id": self.policy.policy_version_id,
            "policy_definition_hash": self.policy.policy_definition_hash,
            "source_artifact_id": self.policy.source_artifact_id,
            "source_sha256": self.policy.source_sha256,
            "reason_definitions": tuple(
                {
                    "reason_definition_id": ReasonDefinitionIdentity(
                        self.policy.policy_version_id,
                        definition.code,
                    ).reason_definition_id,
                    "canonical_payload_hash": definition.canonical_payload_hash,
                }
                for definition in self.policy.reason_definitions
            ),
        }

    @property
    def bundle_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class PolicyRegistrationResult:
    policy_version_id: str
    source_artifact_id: str
    policy_inserted: bool
    policy_version_inserted: bool
    source_artifact_inserted: bool
    reason_definitions_inserted: int

    def __post_init__(self) -> None:
        _sha256(self.policy_version_id, "policy_version_id")
        _sha256(self.source_artifact_id, "source_artifact_id")
        for name in (
            "policy_inserted",
            "policy_version_inserted",
            "source_artifact_inserted",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if (
            not isinstance(self.reason_definitions_inserted, int)
            or isinstance(self.reason_definitions_inserted, bool)
            or self.reason_definitions_inserted not in {0, 69}
        ):
            raise ValueError("reason_definitions_inserted must be 0 or 69")


@dataclass(frozen=True)
class QualityPolicyBundle:
    policy: ParsedQualityPolicy
    registered_at: datetime
    source_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ParsedQualityPolicy):
            raise TypeError("policy must be ParsedQualityPolicy")
        object.__setattr__(self, "registered_at", _utc(self.registered_at, "registered_at"))
        artifacts = _sorted_unique_ids(self.source_artifact_ids, "source_artifact_id")
        if self.policy.source_artifact_id not in artifacts:
            raise ValueError("policy source artifact is missing from bundle")
        object.__setattr__(self, "source_artifact_ids", artifacts)


@dataclass(frozen=True)
class TargetBundle:
    event_id: str
    raw_event_id: str
    result_id: str
    target: QuoteTarget | StatusTarget
    result_persistence_recorded_at: datetime
    event_payload_hash: str
    result_payload_hash: str
    raw_event_payload_hash: str
    connection_session_id: str
    result_event_ordinal: int

    def __post_init__(self) -> None:
        for name in (
            "event_id",
            "raw_event_id",
            "result_id",
            "event_payload_hash",
            "result_payload_hash",
            "raw_event_payload_hash",
        ):
            _sha256(getattr(self, name), name)
        if not isinstance(self.target, (QuoteTarget, StatusTarget)):
            raise TypeError("target must be QuoteTarget or StatusTarget")
        if self.target.event_id != self.event_id:
            raise ValueError("target event identity mismatch")
        object.__setattr__(
            self,
            "result_persistence_recorded_at",
            _utc(self.result_persistence_recorded_at, "result_persistence_recorded_at"),
        )
        if self.result_persistence_recorded_at < self.target.available_at:
            raise ValueError("result persistence cannot precede target availability")
        _opaque(self.connection_session_id, "connection_session_id")
        if (
            not isinstance(self.result_event_ordinal, int)
            or isinstance(self.result_event_ordinal, bool)
            or self.result_event_ordinal < 0
        ):
            raise ValueError("result_event_ordinal must be a non-negative integer")

    @property
    def target_kind(self) -> TargetKind:
        return self.target.target_kind

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "raw_event_id": self.raw_event_id,
            "result_id": self.result_id,
            "target_kind": self.target_kind.value,
            "target_available_at": self.target.available_at,
            "result_persistence_recorded_at": self.result_persistence_recorded_at,
            "event_payload_hash": self.event_payload_hash,
            "result_payload_hash": self.result_payload_hash,
            "raw_event_payload_hash": self.raw_event_payload_hash,
            "connection_session_id": self.connection_session_id,
            "result_event_ordinal": self.result_event_ordinal,
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class VisibleTargetQueryResult:
    requested_event_ids: tuple[str, ...]
    known_as_of: datetime
    targets: tuple[TargetBundle, ...]

    def __post_init__(self) -> None:
        requested = _sorted_unique_ids(self.requested_event_ids, "event_id")
        if len(requested) > 5000:
            raise ValueError("visible-target query is limited to 5000 event IDs")
        object.__setattr__(self, "requested_event_ids", requested)
        object.__setattr__(self, "known_as_of", _utc(self.known_as_of, "known_as_of"))
        ordered = tuple(sorted(self.targets, key=lambda item: item.event_id))
        if any(not isinstance(item, TargetBundle) for item in ordered):
            raise TypeError("targets must contain TargetBundle values")
        returned_ids = tuple(item.event_id for item in ordered)
        if len(set(returned_ids)) != len(returned_ids):
            raise ValueError("visible-target results must not contain duplicate events")
        if not set(returned_ids) <= set(requested):
            raise ValueError("visible-target results contain an unrequested event")
        for item in ordered:
            if item.target.available_at > self.known_as_of:
                raise ValueError("visible target is after the knowledge cutoff")
            if item.result_persistence_recorded_at > self.known_as_of:
                raise ValueError("visible target result is after the knowledge cutoff")
        object.__setattr__(self, "targets", ordered)

    @property
    def hidden_event_ids(self) -> tuple[str, ...]:
        returned = {item.event_id for item in self.targets}
        return tuple(item for item in self.requested_event_ids if item not in returned)

    @property
    def is_complete(self) -> bool:
        return not self.hidden_event_ids


@dataclass(frozen=True)
class AssessmentReasonPlan:
    assessment_id: str
    policy_version_id: str
    reason_ordinal: int
    occurrence: QualityReasonOccurrence

    def __post_init__(self) -> None:
        _sha256(self.assessment_id, "assessment_id")
        _sha256(self.policy_version_id, "policy_version_id")
        if (
            not isinstance(self.reason_ordinal, int)
            or isinstance(self.reason_ordinal, bool)
            or not 0 <= self.reason_ordinal <= 127
        ):
            raise ValueError("reason_ordinal must be in 0..127")
        if not isinstance(self.occurrence, QualityReasonOccurrence):
            raise TypeError("occurrence must be QualityReasonOccurrence")

    @property
    def reason_occurrence_id(self) -> str:
        return ReasonOccurrenceIdentity(
            self.assessment_id,
            self.occurrence.reason_code,
            self.occurrence.subject_key,
        ).reason_occurrence_id

    @property
    def reason_definition_id(self) -> str:
        return ReasonDefinitionIdentity(
            self.policy_version_id,
            self.occurrence.reason_code,
        ).reason_definition_id

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "reason_occurrence_id": self.reason_occurrence_id,
            "assessment_id": self.assessment_id,
            "policy_version_id": self.policy_version_id,
            "reason_definition_id": self.reason_definition_id,
            "reason_code": self.occurrence.reason_code,
            "registry_ordinal": self.occurrence.definition.ordinal,
            "severity": self.occurrence.severity.value,
            "subject_key": self.occurrence.subject_key,
            "reason_ordinal": self.reason_ordinal,
            "evidence": self.occurrence.evidence.canonical_payload,
            "evidence_hash": self.occurrence.evidence.evidence_hash,
        }


@dataclass(frozen=True)
class AssessmentDependencyPlan:
    assessment_id: str
    dependency_ordinal: int
    candidates: DependencyCandidates
    outcome: DependencyOutcome
    selected_candidate_id: str | None = None

    def __post_init__(self) -> None:
        _sha256(self.assessment_id, "assessment_id")
        if (
            not isinstance(self.dependency_ordinal, int)
            or isinstance(self.dependency_ordinal, bool)
            or not 0 <= self.dependency_ordinal <= 15
        ):
            raise ValueError("dependency_ordinal must be in 0..15")
        if not isinstance(self.candidates, DependencyCandidates):
            raise TypeError("candidates must be DependencyCandidates")
        object.__setattr__(self, "outcome", DependencyOutcome(self.outcome))
        candidate_ids = tuple(item.candidate_id for item in self.candidates.candidates)
        if self.outcome is DependencyOutcome.SELECTED:
            if len(candidate_ids) != 1 or self.selected_candidate_id != candidate_ids[0]:
                raise ValueError("selected dependency requires its one candidate ID")
        elif self.outcome is DependencyOutcome.ABSENT:
            if candidate_ids or self.selected_candidate_id is not None:
                raise ValueError("absent dependency cannot contain candidates")
        else:
            if len(candidate_ids) < 2 or self.selected_candidate_id is not None:
                raise ValueError("ambiguous dependency requires two or more candidates")

    @property
    def dependency_kind(self) -> DependencyKind:
        return self.candidates.dependency_kind

    @property
    def subject_key(self) -> str:
        return self.candidates.subject_key

    @property
    def assessment_dependency_id(self) -> str:
        return DependencyIdentity(
            self.assessment_id,
            self.dependency_kind.value,
            self.subject_key,
        ).assessment_dependency_id

    @property
    def selected_candidate_ordinal(self) -> int | None:
        if self.selected_candidate_id is None:
            return None
        return tuple(item.candidate_id for item in self.candidates.candidates).index(
            self.selected_candidate_id
        )

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "assessment_dependency_id": self.assessment_dependency_id,
            "assessment_id": self.assessment_id,
            "dependency_ordinal": self.dependency_ordinal,
            "dependency_kind": self.dependency_kind.value,
            "subject_key": self.subject_key,
            "outcome": self.outcome.value,
            "market_cutoff": self.candidates.market_cutoff,
            "knowledge_cutoff": self.candidates.knowledge_cutoff,
            "selection_rule_version": self.candidates.selection_rule_version,
            "candidate_count": len(self.candidates.candidates),
            "selected_candidate_ordinal": self.selected_candidate_ordinal,
            "search_scope_payload": _thaw(self.candidates.search_scope_payload),
            "search_scope_hash": self.candidates.search_scope_hash,
            "candidate_set_hash": self.candidates.candidate_set_hash,
            "candidates": tuple(
                item.canonical_payload for item in self.candidates.candidates
            ),
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class AssessmentPlan:
    assessment_id: str
    target: TargetBundle
    policy_bundle: QualityPolicyBundle
    evaluation_dependencies: TargetDependencies
    policy_id: str
    policy_version_id: str
    context: EvaluationContext
    evaluation: QualityEvaluationResult
    reasons: tuple[AssessmentReasonPlan, ...]
    dependencies: tuple[AssessmentDependencyPlan, ...]
    policy_registered_after_known_as_of: bool

    def __post_init__(self) -> None:
        _sha256(self.assessment_id, "assessment_id")
        _sha256(self.policy_id, "policy_id")
        _sha256(self.policy_version_id, "policy_version_id")
        if not isinstance(self.target, TargetBundle):
            raise TypeError("target must be TargetBundle")
        if not isinstance(self.policy_bundle, QualityPolicyBundle):
            raise TypeError("policy_bundle must be QualityPolicyBundle")
        if not isinstance(self.evaluation_dependencies, TargetDependencies):
            raise TypeError("evaluation_dependencies must be TargetDependencies")
        if not isinstance(self.context, EvaluationContext):
            raise TypeError("context must be EvaluationContext")
        if not isinstance(self.evaluation, QualityEvaluationResult):
            raise TypeError("evaluation must be QualityEvaluationResult")
        if self.policy_id != self.policy_bundle.policy.policy_id:
            raise ValueError("assessment policy identity mismatch")
        if self.policy_version_id != self.policy_bundle.policy.policy_version_id:
            raise ValueError("assessment policy-version identity mismatch")
        if self.target.target.available_at > self.context.evaluation_known_as_of:
            raise ValueError("assessment target is after the knowledge cutoff")
        if self.target.result_persistence_recorded_at > self.context.evaluation_known_as_of:
            raise ValueError("assessment target result is after the knowledge cutoff")
        expected_evaluation = evaluate_quality(
            QualityEvaluationInput(
                self.policy_bundle.policy,
                self.context,
                self.target.target,
                self.evaluation_dependencies,
            )
        )
        if self.evaluation != expected_evaluation:
            raise ValueError("assessment evaluation does not match its exact inputs")
        expected_id = AssessmentIdentity(
            self.target.event_id,
            self.policy_version_id,
            self.context,
        ).assessment_id
        if self.assessment_id != expected_id:
            raise ValueError("assessment identity mismatch")
        if self.evaluation.target_kind is not self.target.target_kind:
            raise ValueError("evaluation target kind mismatch")
        expected_t = self.context.dependency_market_as_of(
            self.target.target.provider_timestamp
        )
        if self.evaluation.dependency_market_as_of != expected_t:
            raise ValueError("evaluation dependency cutoff mismatch")
        if len(self.evaluation.reasons) > 127:
            raise ValueError("assessment reasons are limited to 127")
        reason_order = tuple(
            (item.definition.ordinal, item.reason_code, item.subject_key)
            for item in self.evaluation.reasons
        )
        if reason_order != tuple(sorted(reason_order)):
            raise ValueError("evaluation reasons must use canonical registry order")
        if len({(item.reason_code, item.subject_key) for item in self.evaluation.reasons}) != len(
            self.evaluation.reasons
        ):
            raise ValueError("evaluation reason occurrences must be unique")
        if self.evaluation.disposition is not reduce_disposition(
            item.severity for item in self.evaluation.reasons
        ):
            raise ValueError("evaluation disposition does not match reason severities")
        expected_reasons = tuple(
            AssessmentReasonPlan(
                self.assessment_id,
                self.policy_version_id,
                ordinal,
                occurrence,
            )
            for ordinal, occurrence in enumerate(self.evaluation.reasons)
        )
        if self.reasons != expected_reasons:
            raise ValueError("assessment reason plan mismatch")
        _ = self.reason_set_hash
        ordered_dependencies = tuple(
            sorted(
                self.dependencies,
                key=lambda item: (
                    _DEPENDENCY_KIND_ORDINAL[item.dependency_kind],
                    item.subject_key,
                ),
            )
        )
        if ordered_dependencies != self.dependencies:
            raise ValueError("assessment dependencies must be canonically ordered")
        required_kinds = (
            {
                DependencyKind.CATALOGUE_MEMBERSHIP,
                DependencyKind.CATALOGUE_VERSION,
                DependencyKind.CONNECTION_SESSION,
                DependencyKind.INSTRUMENT_VERSION,
                DependencyKind.MARKET_SEGMENT_STATUS,
                DependencyKind.PROVIDER_MAPPING,
                DependencyKind.SUBSCRIPTION_SCOPE,
                DependencyKind.TRADING_SESSION,
            }
            if self.target.target_kind.is_quote
            else {
                DependencyKind.CONNECTION_SESSION,
                DependencyKind.TRADING_SESSION,
            }
        )
        actual_kinds = tuple(item.dependency_kind for item in self.dependencies)
        if len(actual_kinds) != len(required_kinds) or set(actual_kinds) != required_kinds:
            raise ValueError("assessment dependency applicability set mismatch")
        if tuple(item.dependency_ordinal for item in self.dependencies) != tuple(
            range(len(self.dependencies))
        ):
            raise ValueError("dependency ordinals must be contiguous")
        if any(item.assessment_id != self.assessment_id for item in self.dependencies):
            raise ValueError("dependency plan belongs to another assessment")
        if any(
            item.candidates.market_cutoff != self.evaluation.dependency_market_as_of
            or item.candidates.knowledge_cutoff
            != self.context.evaluation_known_as_of
            for item in self.dependencies
        ):
            raise ValueError("dependency cutoffs must match the assessment context")
        _validate_evaluation_dependency_bindings(
            self.assessment_id,
            self.target.target_kind,
            self.evaluation_dependencies,
            self.dependencies,
        )
        if not isinstance(self.policy_registered_after_known_as_of, bool):
            raise TypeError("policy_registered_after_known_as_of must be bool")
        expected_registration_flag = (
            self.policy_bundle.registered_at > self.context.evaluation_known_as_of
        )
        if self.policy_registered_after_known_as_of is not expected_registration_flag:
            raise ValueError("policy registration cutoff flag mismatch")

    @classmethod
    def build(
        cls,
        *,
        policy: QualityPolicyBundle,
        context: EvaluationContext,
        target: TargetBundle,
        evaluation_dependencies: TargetDependencies,
        evaluation: QualityEvaluationResult,
        dependency_candidates: tuple[
            tuple[DependencyCandidates, DependencyOutcome, str | None], ...
        ],
    ) -> AssessmentPlan:
        assessment_id = AssessmentIdentity(
            target.event_id,
            policy.policy.policy_version_id,
            context,
        ).assessment_id
        reasons = tuple(
            AssessmentReasonPlan(
                assessment_id,
                policy.policy.policy_version_id,
                ordinal,
                occurrence,
            )
            for ordinal, occurrence in enumerate(evaluation.reasons)
        )
        ordered_drafts = tuple(
            sorted(
                dependency_candidates,
                key=lambda item: (
                    _DEPENDENCY_KIND_ORDINAL[item[0].dependency_kind],
                    item[0].subject_key,
                ),
            )
        )
        dependencies = tuple(
            AssessmentDependencyPlan(
                assessment_id,
                ordinal,
                candidate_set,
                outcome,
                selected_candidate_id,
            )
            for ordinal, (candidate_set, outcome, selected_candidate_id) in enumerate(
                ordered_drafts
            )
        )
        return cls(
            assessment_id,
            target,
            policy,
            evaluation_dependencies,
            policy.policy.policy_id,
            policy.policy.policy_version_id,
            context,
            evaluation,
            reasons,
            dependencies,
            policy.registered_at > context.evaluation_known_as_of,
        )

    @property
    def reason_set_hash(self) -> str:
        expected = stable_hash(
            tuple(item.occurrence.canonical_payload for item in self.reasons)
        )
        if expected != self.evaluation.reason_set_hash:
            raise ValueError("evaluation reason-set hash mismatch")
        return expected

    @property
    def dependency_closure_hash(self) -> str:
        return stable_hash(tuple(item.canonical_payload for item in self.dependencies))

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "event_id": self.target.event_id,
            "raw_event_id": self.target.raw_event_id,
            "result_id": self.target.result_id,
            "policy_id": self.policy_id,
            "policy_version_id": self.policy_version_id,
            "evaluation_market_as_of": self.context.evaluation_market_as_of,
            "evaluation_known_as_of": self.context.evaluation_known_as_of,
            "dependency_market_as_of": self.evaluation.dependency_market_as_of,
            "market_time_basis": MARKET_TIME_BASIS,
            "target_kind": self.target.target_kind.value,
            "disposition": self.evaluation.disposition.value,
            "reason_count": len(self.reasons),
            "dependency_count": len(self.dependencies),
            "reason_set_hash": self.reason_set_hash,
            "dependency_closure_hash": self.dependency_closure_hash,
            "target_bundle_hash": self.target.canonical_payload_hash,
            "policy_registered_after_known_as_of": (
                self.policy_registered_after_known_as_of
            ),
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class RunMembershipPlan:
    assessment_run_id: str
    target_ordinal: int
    event_id: str
    assessment_id: str

    def __post_init__(self) -> None:
        _sha256(self.assessment_run_id, "assessment_run_id")
        _sha256(self.event_id, "event_id")
        _sha256(self.assessment_id, "assessment_id")
        if (
            not isinstance(self.target_ordinal, int)
            or isinstance(self.target_ordinal, bool)
            or not 0 <= self.target_ordinal <= 4999
        ):
            raise ValueError("target_ordinal must be in 0..4999")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "assessment_run_id": self.assessment_run_id,
            "target_ordinal": self.target_ordinal,
            "event_id": self.event_id,
            "assessment_id": self.assessment_id,
        }


@dataclass(frozen=True)
class LockRoot:
    entity_namespace: LockEntityNamespace
    canonical_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entity_namespace",
            LockEntityNamespace(self.entity_namespace),
        )
        _sha256(self.canonical_id, "canonical_id")

    @property
    def stripe(self) -> int:
        return data15_lock_stripe(self.entity_namespace, self.canonical_id)


@dataclass(frozen=True)
class AssessmentRunPlan:
    assessment_run_id: str
    policy_version_id: str
    context: EvaluationContext
    assessments: tuple[AssessmentPlan, ...]
    memberships: tuple[RunMembershipPlan, ...]

    def __post_init__(self) -> None:
        _sha256(self.assessment_run_id, "assessment_run_id")
        _sha256(self.policy_version_id, "policy_version_id")
        if not isinstance(self.context, EvaluationContext):
            raise TypeError("context must be EvaluationContext")
        ordered = tuple(sorted(self.assessments, key=lambda item: item.target.event_id))
        if ordered != self.assessments:
            raise ValueError("assessments must be ordered by event ID")
        if not 1 <= len(self.assessments) <= 5000:
            raise ValueError("assessment run requires 1..5000 assessments")
        event_ids = tuple(item.target.event_id for item in self.assessments)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("assessment run target IDs must be unique")
        if any(item.policy_version_id != self.policy_version_id for item in self.assessments):
            raise ValueError("assessment run mixes policy versions")
        if any(item.context != self.context for item in self.assessments):
            raise ValueError("assessment run mixes evaluation contexts")
        expected_id = AssessmentRunIdentity(
            self.policy_version_id,
            self.context,
            event_ids,
        ).assessment_run_id
        if self.assessment_run_id != expected_id:
            raise ValueError("assessment run identity mismatch")
        expected_memberships = tuple(
            RunMembershipPlan(
                self.assessment_run_id,
                ordinal,
                assessment.target.event_id,
                assessment.assessment_id,
            )
            for ordinal, assessment in enumerate(self.assessments)
        )
        if self.memberships != expected_memberships:
            raise ValueError("assessment run membership mismatch")

    @classmethod
    def build(
        cls,
        assessments: tuple[AssessmentPlan, ...],
    ) -> AssessmentRunPlan:
        ordered = tuple(sorted(assessments, key=lambda item: item.target.event_id))
        if not ordered:
            raise ValueError("assessment run requires at least one assessment")
        policy_version_id = ordered[0].policy_version_id
        context = ordered[0].context
        event_ids = tuple(item.target.event_id for item in ordered)
        run_id = AssessmentRunIdentity(
            policy_version_id,
            context,
            event_ids,
        ).assessment_run_id
        memberships = tuple(
            RunMembershipPlan(
                run_id,
                ordinal,
                assessment.target.event_id,
                assessment.assessment_id,
            )
            for ordinal, assessment in enumerate(ordered)
        )
        return cls(run_id, policy_version_id, context, ordered, memberships)

    @property
    def ordered_target_event_ids(self) -> tuple[str, ...]:
        return tuple(item.target.event_id for item in self.assessments)

    @property
    def canonical_payload(self) -> dict[str, object]:
        identity = AssessmentRunIdentity(
            self.policy_version_id,
            self.context,
            self.ordered_target_event_ids,
        )
        return {
            "assessment_run_id": self.assessment_run_id,
            "assessment_run_schema_version": identity.assessment_run_schema_version,
            "policy_version_id": self.policy_version_id,
            "evaluation_market_as_of": self.context.evaluation_market_as_of,
            "evaluation_known_as_of": self.context.evaluation_known_as_of,
            "quality_evaluator_implementation_version": (
                identity.quality_evaluator_implementation_version
            ),
            "target_count": len(self.assessments),
            "ordered_target_event_ids": self.ordered_target_event_ids,
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)

    @property
    def complete_plan_hash(self) -> str:
        return stable_hash(
            {
                "run": self.canonical_payload,
                "assessments": tuple(
                    item.canonical_payload_hash for item in self.assessments
                ),
                "memberships": tuple(
                    item.canonical_payload for item in self.memberships
                ),
            }
        )

    @property
    def lock_roots(self) -> tuple[LockRoot, ...]:
        return tuple(
            [LockRoot(LockEntityNamespace.POLICY_VERSION, self.policy_version_id)]
            + [
                LockRoot(LockEntityNamespace.ASSESSMENT, item.assessment_id)
                for item in self.assessments
            ]
            + [LockRoot(LockEntityNamespace.ASSESSMENT_RUN, self.assessment_run_id)]
        )


@dataclass(frozen=True)
class BulkWritePlan:
    family: WriteFamily
    item_count: int
    parameters_per_item: int
    chunks: tuple[ParameterChunk, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", WriteFamily(self.family))
        if (
            not isinstance(self.item_count, int)
            or isinstance(self.item_count, bool)
            or self.item_count < 0
        ):
            raise ValueError("item_count must be non-negative")
        if (
            not isinstance(self.parameters_per_item, int)
            or isinstance(self.parameters_per_item, bool)
            or not 1 <= self.parameters_per_item <= 60000
        ):
            raise ValueError("parameters_per_item must be in 1..60000")
        expected = plan_parameter_chunks(
            self.item_count,
            self.parameters_per_item,
            budget=60000,
        )
        if self.chunks != expected:
            raise ValueError("bulk write chunks do not match the canonical planner")


def plan_assessment_run_writes(
    plan: AssessmentRunPlan,
    parameters_per_item: Mapping[WriteFamily | str, int],
) -> tuple[BulkWritePlan, ...]:
    if not isinstance(plan, AssessmentRunPlan):
        raise TypeError("plan must be AssessmentRunPlan")
    normalized = {WriteFamily(key): value for key, value in parameters_per_item.items()}
    if set(normalized) != set(WriteFamily):
        raise ValueError("parameters_per_item must define every write family exactly once")
    counts = {
        WriteFamily.ASSESSMENTS: len(plan.assessments),
        WriteFamily.REASONS: sum(len(item.reasons) for item in plan.assessments),
        WriteFamily.DEPENDENCIES: sum(
            len(item.dependencies) for item in plan.assessments
        ),
        WriteFamily.CANDIDATES: sum(
            len(dependency.candidates.candidates)
            for assessment in plan.assessments
            for dependency in assessment.dependencies
        ),
        WriteFamily.MEMBERSHIPS: len(plan.memberships),
    }
    return tuple(
        BulkWritePlan(
            family,
            counts[family],
            normalized[family],
            plan_parameter_chunks(counts[family], normalized[family], budget=60000),
        )
        for family in WriteFamily
    )


@dataclass(frozen=True)
class PersistenceResult:
    assessment_run_id: str
    inserted: bool
    assessment_count: int
    reason_count: int
    dependency_count: int
    candidate_count: int

    def __post_init__(self) -> None:
        _sha256(self.assessment_run_id, "assessment_run_id")
        if not isinstance(self.inserted, bool):
            raise TypeError("inserted must be bool")
        for name in (
            "assessment_count",
            "reason_count",
            "dependency_count",
            "candidate_count",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class QualityAssessmentBundle:
    plan: AssessmentPlan
    persistence_recorded_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.plan, AssessmentPlan):
            raise TypeError("plan must be AssessmentPlan")
        object.__setattr__(
            self,
            "persistence_recorded_at",
            _utc(self.persistence_recorded_at, "persistence_recorded_at"),
        )


@dataclass(frozen=True)
class QualityAssessmentRunBundle:
    plan: AssessmentRunPlan
    persistence_recorded_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.plan, AssessmentRunPlan):
            raise TypeError("plan must be AssessmentRunPlan")
        object.__setattr__(
            self,
            "persistence_recorded_at",
            _utc(self.persistence_recorded_at, "persistence_recorded_at"),
        )


@dataclass(frozen=True)
class AuditCursor:
    schema_version: int = QUALITY_AUDIT_CURSOR_SCHEMA_VERSION
    position: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != QUALITY_AUDIT_CURSOR_SCHEMA_VERSION:
            raise ValueError("unsupported quality audit cursor schema")
        if self.position is not None:
            _sha256(self.position, "position")


class MarketDataQualityRepository(Protocol):
    async def register_policy_bundle(
        self,
        bundle: PolicyRegistrationBundle,
    ) -> PolicyRegistrationResult: ...

    async def get_policy_bundle(
        self,
        policy_version_id: str,
    ) -> QualityPolicyBundle | None: ...

    async def load_visible_targets(
        self,
        event_ids: tuple[str, ...],
        known_as_of: datetime,
    ) -> VisibleTargetQueryResult: ...

    async def list_provider_mapping_candidates(
        self,
        scope: MappingScope,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def list_instrument_version_candidates(
        self,
        scope: InstrumentScope,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def list_catalogue_candidates(
        self,
        scope: CatalogueScope,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def list_catalogue_membership_candidates(
        self,
        scope: MembershipScope,
    ) -> DependencyCandidates: ...

    async def list_trading_session_candidates(
        self,
        scope: SessionScope,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def list_segment_status_candidates(
        self,
        scope: SegmentScope,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def list_connection_candidates(
        self,
        scope: ConnectionScope,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def list_subscription_scope_candidates(
        self,
        scope: SubscriptionScope,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> DependencyCandidates: ...

    async def acquire_write_locks(self, roots: tuple[LockRoot, ...]) -> None: ...

    async def persist_assessment_run(
        self,
        plan: AssessmentRunPlan,
    ) -> PersistenceResult: ...

    async def get_assessment_exact(
        self,
        event_id: str,
        policy_version_id: str,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> QualityAssessmentBundle | None: ...

    async def list_assessments_for_audit(
        self,
        cursor: AuditCursor,
        limit: int,
    ) -> tuple[QualityAssessmentBundle, ...]: ...

    async def reconstruct_run(
        self,
        assessment_run_id: str,
    ) -> QualityAssessmentRunBundle | None: ...


class MarketDataQualityUnitOfWork(Protocol):
    market_data_quality: MarketDataQualityRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc_value, traceback) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


def data15_lock_stripe(
    entity_namespace: LockEntityNamespace | str,
    canonical_id: str,
) -> int:
    namespace = LockEntityNamespace(entity_namespace)
    _sha256(canonical_id, "canonical_id")
    payload = (
        b"data15-lock-stripe-v1\0"
        + namespace.value.encode("ascii")
        + b"\0"
        + canonical_id.encode("ascii")
    )
    return int.from_bytes(hashlib.sha256(payload).digest(), "big") % DATA15_LOCK_STRIPE_COUNT


def derive_data15_lock_stripes(roots: tuple[LockRoot, ...]) -> tuple[int, ...]:
    return tuple(sorted({root.stripe for root in roots}))


def _validate_receipt_basis(
    receipt_basis: ReceiptBasis,
    bootstrap_revision: str | None,
) -> None:
    if receipt_basis is ReceiptBasis.LEGACY_BOOTSTRAP:
        if bootstrap_revision != _BOOTSTRAP_REVISION:
            raise ValueError("legacy receipt requires bootstrap revision 20260804_05")
    elif bootstrap_revision is not None:
        raise ValueError("repository receipt cannot carry bootstrap revision")


def _validate_reference_kind(
    dependency_kind: DependencyKind,
    reference: CandidateReference,
) -> None:
    if not isinstance(
        reference,
        (
            MarketEventCandidateReference,
            ProviderMappingCandidateReference,
            InstrumentVersionCandidateReference,
            CatalogueCandidateReference,
            CatalogueMembershipCandidateReference,
            TradingSessionCandidateReference,
            LifecycleCandidateReference,
        ),
    ):
        raise TypeError("unsupported candidate reference")
    if dependency_kind not in reference.candidate_kind:
        raise ValueError("candidate reference does not match dependency kind")


def _validate_scope_kind(
    dependency_kind: DependencyKind,
    scope: QueryScope,
) -> None:
    expected_type = {
        DependencyKind.PROVIDER_MAPPING: MappingScope,
        DependencyKind.INSTRUMENT_VERSION: InstrumentScope,
        DependencyKind.CATALOGUE_VERSION: CatalogueScope,
        DependencyKind.CATALOGUE_MEMBERSHIP: MembershipScope,
        DependencyKind.TRADING_SESSION: SessionScope,
        DependencyKind.MARKET_SEGMENT_STATUS: SegmentScope,
        DependencyKind.CONNECTION_SESSION: ConnectionScope,
        DependencyKind.SUBSCRIPTION_SCOPE: SubscriptionScope,
    }[dependency_kind]
    if not isinstance(scope, expected_type):
        raise ValueError("query scope type does not match dependency kind")
    if scope.canonical_payload.get("dependency_kind") != dependency_kind.value:
        raise ValueError("query scope payload does not match dependency kind")


def _validate_evaluation_dependency_bindings(
    assessment_id: str,
    target_kind: TargetKind,
    facts: TargetDependencies,
    plans: tuple[AssessmentDependencyPlan, ...],
) -> None:
    by_kind = {item.dependency_kind: item for item in plans}

    def common(fact: object, kind: DependencyKind, outcome: DependencyOutcome) -> AssessmentDependencyPlan:
        plan = by_kind[kind]
        if getattr(fact, "dependency_id") != plan.assessment_dependency_id:
            raise ValueError(f"{kind.value} evaluator dependency identity mismatch")
        if getattr(fact, "search_scope_hash") != plan.candidates.search_scope_hash:
            raise ValueError(f"{kind.value} evaluator search-scope mismatch")
        if getattr(fact, "candidate_count") != len(plan.candidates.candidates):
            raise ValueError(f"{kind.value} evaluator candidate-count mismatch")
        if plan.outcome is not outcome:
            raise ValueError(f"{kind.value} evaluator outcome mismatch")
        candidate_set_hash = getattr(fact, "candidate_set_hash", None)
        if outcome is DependencyOutcome.AMBIGUOUS:
            if candidate_set_hash != plan.candidates.candidate_set_hash:
                raise ValueError(f"{kind.value} evaluator candidate-set hash mismatch")
        return plan

    def selected_candidate(plan: AssessmentDependencyPlan) -> DependencyCandidate:
        if plan.selected_candidate_ordinal is None:
            raise ValueError("selected dependency is missing selected candidate ordinal")
        return plan.candidates.candidates[plan.selected_candidate_ordinal]

    if target_kind.is_quote:
        subject = facts.subject_scope
        mapping = facts.provider_mapping
        instrument = facts.instrument_version
        catalogue = facts.catalogue_version
        status = facts.market_segment_status
        subscription = facts.subscription
        if any(
            item is None
            for item in (subject, mapping, instrument, catalogue, status, subscription)
        ):
            raise ValueError("quote evaluator dependencies are incomplete")

        assert subject is not None
        subject_outcome = (
            DependencyOutcome.SELECTED if subject.in_scope else DependencyOutcome.ABSENT
        )
        subject_plan = common(
            subject,
            DependencyKind.CATALOGUE_MEMBERSHIP,
            subject_outcome,
        )
        if subject_outcome is DependencyOutcome.SELECTED:
            candidate = selected_candidate(subject_plan)
            if not isinstance(candidate, MembershipDependencyCandidate):
                raise ValueError("catalogue membership selected candidate type mismatch")
            if candidate.membership_id != subject.membership_id:
                raise ValueError("catalogue membership evaluator selection mismatch")

        for fact, kind, semantic_name in (
            (mapping, DependencyKind.PROVIDER_MAPPING, "mapping_id"),
            (instrument, DependencyKind.INSTRUMENT_VERSION, "version_id"),
            (catalogue, DependencyKind.CATALOGUE_VERSION, "catalogue_version_id"),
        ):
            assert isinstance(fact, ProvenanceDependencyFact)
            plan = common(fact, kind, fact.outcome)
            if fact.outcome is DependencyOutcome.SELECTED:
                candidate = selected_candidate(plan)
                if not isinstance(candidate, TemporalDependencyCandidate):
                    raise ValueError(f"{kind.value} selected candidate type mismatch")
                reference = candidate.reference
                if getattr(reference, "record_id", None) != fact.selected_record_id:
                    raise ValueError(f"{kind.value} evaluator selected record mismatch")
                if getattr(reference, semantic_name, None) != fact.selected_semantic_id:
                    raise ValueError(f"{kind.value} evaluator selected semantic mismatch")

        assert isinstance(status, MarketStatusFact)
        status_plan = common(status, DependencyKind.MARKET_SEGMENT_STATUS, status.outcome)
        if status.outcome is DependencyOutcome.SELECTED:
            candidate = selected_candidate(status_plan)
            if not isinstance(candidate, RankedDependencyCandidate):
                raise ValueError("market status selected candidate type mismatch")
            if candidate.candidate_id != status.selected_event_id:
                raise ValueError("market status evaluator selection mismatch")

        assert isinstance(subscription, SubscriptionFact)
        subscription_outcome = {
            SubscriptionResolutionState.SELECTED: DependencyOutcome.SELECTED,
            SubscriptionResolutionState.AMBIGUOUS: DependencyOutcome.AMBIGUOUS,
            SubscriptionResolutionState.MULTIPLE_ACTIVE: DependencyOutcome.AMBIGUOUS,
            SubscriptionResolutionState.MISSING: DependencyOutcome.ABSENT,
            SubscriptionResolutionState.NOT_ACTIVE: DependencyOutcome.ABSENT,
            SubscriptionResolutionState.INSTRUMENT_MISSING: DependencyOutcome.ABSENT,
        }[subscription.state]
        subscription_plan = common(
            subscription,
            DependencyKind.SUBSCRIPTION_SCOPE,
            subscription_outcome,
        )
        if subscription_outcome is DependencyOutcome.SELECTED:
            candidate = selected_candidate(subscription_plan)
            if not isinstance(candidate, RankedDependencyCandidate):
                raise ValueError("subscription selected candidate type mismatch")
            if candidate.candidate_id != subscription.selected_event_id:
                raise ValueError("subscription evaluator selection mismatch")
            reference = candidate.reference
            if not isinstance(reference, LifecycleCandidateReference):
                raise ValueError("subscription selected reference type mismatch")
            if reference.instrument_keys_digest != subscription.instrument_set_digest:
                raise ValueError("subscription instrument-set evidence mismatch")

    session = facts.trading_session
    connection = facts.connection
    if session is None or connection is None:
        raise ValueError("session and connection evaluator dependencies are required")

    session_plan = common(session, DependencyKind.TRADING_SESSION, session.outcome)
    if session.outcome is DependencyOutcome.SELECTED:
        candidate = selected_candidate(session_plan)
        if not isinstance(candidate, TemporalDependencyCandidate):
            raise ValueError("trading session selected candidate type mismatch")
        reference = candidate.reference
        if not isinstance(reference, TradingSessionCandidateReference):
            raise ValueError("trading session selected reference type mismatch")
        if reference.record_id != session.selected_record_id:
            raise ValueError("trading session evaluator selected record mismatch")
        if reference.session_version_id != session.selected_session_version_id:
            raise ValueError("trading session evaluator selected version mismatch")

    connection_plan = common(
        connection,
        DependencyKind.CONNECTION_SESSION,
        connection.outcome,
    )
    if connection.outcome is DependencyOutcome.SELECTED:
        candidate = selected_candidate(connection_plan)
        if not isinstance(candidate, RankedDependencyCandidate):
            raise ValueError("connection selected candidate type mismatch")
        if candidate.candidate_id != connection.selected_event_id:
            raise ValueError("connection evaluator selection mismatch")


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("value must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("mapping keys must be strings")
    return MappingProxyType({key: _freeze(item) for key, item in value.items()})


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    if isinstance(value, (str, int, bool, datetime, date)) or value is None:
        return value
    from decimal import Decimal

    if isinstance(value, Decimal):
        return value
    raise TypeError(f"unsupported canonical mapping value: {type(value).__name__}")


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _sorted_unique_ids(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    ordered = tuple(sorted(values))
    if not ordered:
        raise ValueError(f"{field_name}s cannot be empty")
    for value in ordered:
        _sha256(value, field_name)
    if len(set(ordered)) != len(ordered):
        raise ValueError(f"{field_name}s must be unique")
    return ordered


def _sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be canonical prefixed SHA-256")


def _controlled(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value.encode("utf-8")) <= 128
        or _CONTROLLED.fullmatch(value) is None
    ):
        raise ValueError(f"{field_name} must be controlled text")


def _snake_case(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value.encode("utf-8")) <= 128
        or _SNAKE_CASE.fullmatch(value) is None
    ):
        raise ValueError(f"{field_name} must be lowercase snake case")


def _opaque(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field_name} must be controlled opaque text")


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
