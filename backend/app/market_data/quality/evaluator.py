from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Iterable, Mapping

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import (
    DependencyOutcome,
    EvaluationContext,
    QualityDisposition,
    QualitySeverity,
    TargetKind,
    reduce_disposition,
)
from app.market_data.quality.errors import InvalidQualityEvaluationCommandError
from app.market_data.quality.policy_schema import ParsedQualityPolicy
from app.market_data.quality.reason_registry import REASONS_BY_CODE, ReasonDefinition

_SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTROLLED = re.compile(r"[A-Za-z0-9_.:/|+-]+\Z")
LEASE_MS = Decimal("43200000")


class SubscriptionResolutionState(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    NOT_ACTIVE = "not_active"
    INSTRUMENT_MISSING = "instrument_missing"
    MULTIPLE_ACTIVE = "multiple_active"
    SELECTED = "selected"


@dataclass(frozen=True)
class EvidenceValue:
    name: str
    type: str
    value: str | bool
    unit: str

    def __post_init__(self) -> None:
        _controlled(self.name, "evidence name")
        if self.type not in {
            "integer",
            "decimal",
            "timestamp",
            "identifier",
            "state",
            "boolean",
            "controlled_text",
        }:
            raise ValueError("unsupported evidence type")
        if self.unit not in {
            "none",
            "milliseconds",
            "ticks",
            "basis_points",
            "price",
            "quantity",
            "count",
            "state",
            "identifier",
        }:
            raise ValueError("unsupported evidence unit")
        if self.type == "boolean":
            if not isinstance(self.value, bool):
                raise TypeError("boolean evidence must use a bool value")
        elif not isinstance(self.value, str) or not self.value:
            raise ValueError("non-boolean evidence must use non-empty canonical text")
        if self.type == "identifier" and isinstance(self.value, str):
            _sha256(self.value, "identifier evidence")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class ReasonEvidence:
    observed: tuple[EvidenceValue, ...] = ()
    thresholds: tuple[EvidenceValue, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    details: tuple[EvidenceValue, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("reason evidence schema version must be 1")
        for name in ("observed", "thresholds", "details"):
            values = tuple(sorted(getattr(self, name), key=lambda item: item.name))
            if len(values) > 16:
                raise ValueError(f"{name} evidence is limited to 16 items")
            if len({item.name for item in values}) != len(values):
                raise ValueError(f"{name} evidence names must be unique")
            object.__setattr__(self, name, values)
        dependency_ids = tuple(sorted(set(self.dependency_ids)))
        if len(dependency_ids) > 16:
            raise ValueError("reason evidence is limited to 16 dependency IDs")
        for dependency_id in dependency_ids:
            _sha256(dependency_id, "dependency_id")
        object.__setattr__(self, "dependency_ids", dependency_ids)

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observed": tuple(item.canonical_payload for item in self.observed),
            "thresholds": tuple(item.canonical_payload for item in self.thresholds),
            "dependency_ids": self.dependency_ids,
            "details": tuple(item.canonical_payload for item in self.details),
        }

    @property
    def evidence_hash(self) -> str:
        return stable_hash(self.canonical_payload)


@dataclass(frozen=True)
class QualityReasonOccurrence:
    reason_code: str
    subject_key: str
    target_kind: TargetKind
    evidence: ReasonEvidence

    def __post_init__(self) -> None:
        definition = REASONS_BY_CODE.get(self.reason_code)
        if definition is None:
            raise ValueError("reason code is not in the DATA-1.5 registry")
        object.__setattr__(self, "target_kind", TargetKind(self.target_kind))
        if self.target_kind not in definition.applicable_target_kinds:
            raise ValueError("reason code is not applicable to target kind")
        if self.subject_key not in definition.subject_keys:
            raise ValueError("subject key is not permitted by reason definition")
        if not isinstance(self.evidence, ReasonEvidence):
            raise TypeError("evidence must be ReasonEvidence")

    @property
    def definition(self) -> ReasonDefinition:
        return REASONS_BY_CODE[self.reason_code]

    @property
    def severity(self) -> QualitySeverity:
        return self.definition.severity

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "reason_code": self.reason_code,
            "registry_ordinal": self.definition.ordinal,
            "severity": self.severity.value,
            "subject_key": self.subject_key,
            "evidence": self.evidence.canonical_payload,
        }


@dataclass(frozen=True)
class ProvenanceDependencyFact:
    dependency_id: str
    outcome: DependencyOutcome
    candidate_count: int
    has_visible_knowledge_leaf: bool
    persisted_semantic_id: str | None = None
    persisted_record_id: str | None = None
    selected_semantic_id: str | None = None
    selected_record_id: str | None = None
    selected_effective: bool = True
    candidate_set_hash: str | None = None
    trading_status: str | None = None
    tick_size: Decimal | None = None

    def __post_init__(self) -> None:
        _sha256(self.dependency_id, "dependency_id")
        object.__setattr__(self, "outcome", DependencyOutcome(self.outcome))
        _candidate_count_shape(self.outcome, self.candidate_count)
        for field_name in (
            "persisted_semantic_id",
            "persisted_record_id",
            "selected_semantic_id",
            "selected_record_id",
            "candidate_set_hash",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _sha256(value, field_name)
        if self.outcome is DependencyOutcome.SELECTED:
            if self.selected_semantic_id is None or self.selected_record_id is None:
                raise ValueError("selected dependency requires selected semantic and record IDs")
        if self.outcome is DependencyOutcome.AMBIGUOUS and self.candidate_set_hash is None:
            raise ValueError("ambiguous dependency requires candidate_set_hash")
        if self.tick_size is not None and not isinstance(self.tick_size, Decimal):
            raise TypeError("tick_size must be Decimal when present")


@dataclass(frozen=True)
class SessionFact:
    dependency_id: str
    outcome: DependencyOutcome
    candidate_count: int
    candidate_set_hash: str | None = None
    timezone: str | None = None
    status: str | None = None
    open_at: datetime | None = None
    close_at: datetime | None = None

    def __post_init__(self) -> None:
        _sha256(self.dependency_id, "dependency_id")
        object.__setattr__(self, "outcome", DependencyOutcome(self.outcome))
        _candidate_count_shape(self.outcome, self.candidate_count)
        if self.candidate_set_hash is not None:
            _sha256(self.candidate_set_hash, "candidate_set_hash")
        if self.outcome is DependencyOutcome.SELECTED:
            if self.timezone is None or self.status is None or self.open_at is None or self.close_at is None:
                raise ValueError("selected session requires timezone, status, open_at and close_at")
            object.__setattr__(self, "open_at", _utc(self.open_at, "open_at"))
            object.__setattr__(self, "close_at", _utc(self.close_at, "close_at"))
            if self.close_at <= self.open_at:
                raise ValueError("session close must be after open")


@dataclass(frozen=True)
class MarketStatusFact:
    dependency_id: str
    outcome: DependencyOutcome
    candidate_count: int
    candidate_set_hash: str | None = None
    provider_timestamp: datetime | None = None
    status_is_known: bool | None = None
    status_name: str | None = None

    def __post_init__(self) -> None:
        _sha256(self.dependency_id, "dependency_id")
        object.__setattr__(self, "outcome", DependencyOutcome(self.outcome))
        _candidate_count_shape(self.outcome, self.candidate_count)
        if self.candidate_set_hash is not None:
            _sha256(self.candidate_set_hash, "candidate_set_hash")
        if self.outcome is DependencyOutcome.SELECTED:
            if self.provider_timestamp is None or self.status_is_known is None or self.status_name is None:
                raise ValueError("selected status requires timestamp, known flag and status name")
            object.__setattr__(
                self,
                "provider_timestamp",
                _utc(self.provider_timestamp, "provider_timestamp"),
            )


@dataclass(frozen=True)
class ConnectionFact:
    dependency_id: str
    outcome: DependencyOutcome
    candidate_count: int
    candidate_set_hash: str | None = None
    state: str | None = None
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        _sha256(self.dependency_id, "dependency_id")
        object.__setattr__(self, "outcome", DependencyOutcome(self.outcome))
        _candidate_count_shape(self.outcome, self.candidate_count)
        if self.candidate_set_hash is not None:
            _sha256(self.candidate_set_hash, "candidate_set_hash")
        if self.outcome is DependencyOutcome.SELECTED:
            if self.state is None or self.occurred_at is None:
                raise ValueError("selected connection requires state and occurred_at")
            object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "occurred_at"))


@dataclass(frozen=True)
class SubscriptionFact:
    dependency_id: str
    state: SubscriptionResolutionState
    candidate_count: int
    candidate_set_hash: str | None = None
    scope_id: str | None = None
    effective_mode: str | None = None
    target_mode: str | None = None
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        _sha256(self.dependency_id, "dependency_id")
        object.__setattr__(self, "state", SubscriptionResolutionState(self.state))
        if not isinstance(self.candidate_count, int) or isinstance(self.candidate_count, bool) or self.candidate_count < 0:
            raise ValueError("candidate_count must be a non-negative integer")
        if self.candidate_set_hash is not None:
            _sha256(self.candidate_set_hash, "candidate_set_hash")
        if self.state is SubscriptionResolutionState.SELECTED:
            if self.scope_id is None or self.effective_mode is None or self.target_mode is None or self.occurred_at is None:
                raise ValueError("selected subscription requires scope, modes and occurred_at")
            object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "occurred_at"))


@dataclass(frozen=True)
class TargetDependencies:
    provider_mapping: ProvenanceDependencyFact | None = None
    instrument_version: ProvenanceDependencyFact | None = None
    catalogue_version: ProvenanceDependencyFact | None = None
    trading_session: SessionFact | None = None
    market_segment_status: MarketStatusFact | None = None
    connection: ConnectionFact | None = None
    subscription: SubscriptionFact | None = None


@dataclass(frozen=True)
class QuoteTarget:
    event_id: str
    target_kind: TargetKind
    provider: str
    provider_contract_key: str
    normalization_schema_version: int
    normalizer_implementation_version: str
    provider_timestamp: datetime
    available_at: datetime
    availability_basis: str
    feed_response_type: str
    request_mode: str
    subject_in_scope: bool
    resolution_market_as_of: datetime
    resolution_known_as_of: datetime
    bid_price: object | None = None
    bid_size: object | None = None
    ask_price: object | None = None
    ask_size: object | None = None
    last_price: object | None = None
    last_size: object | None = None
    last_trade_at: object | None = None
    previous_close_price: object | None = None
    reported_volume: object | None = None
    open_interest: object | None = None
    provider_depth_levels_present: int = 0
    normalized_depth_levels: int = 0
    unadopted_depth_level_count: int = 0
    unadopted_schema_paths: tuple[str, ...] = ()
    present_unadopted_message_paths: tuple[str, ...] = ()
    secondary_payload_paths_present: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _sha256(self.event_id, "event_id")
        object.__setattr__(self, "target_kind", TargetKind(self.target_kind))
        if not self.target_kind.is_quote:
            raise ValueError("QuoteTarget requires a quote target kind")
        for field_name in (
            "provider_timestamp",
            "available_at",
            "resolution_market_as_of",
            "resolution_known_as_of",
        ):
            object.__setattr__(self, field_name, _utc(getattr(self, field_name), field_name))
        for field_name in (
            "unadopted_schema_paths",
            "present_unadopted_message_paths",
            "secondary_payload_paths_present",
        ):
            values = tuple(sorted(set(getattr(self, field_name))))
            object.__setattr__(self, field_name, values)


@dataclass(frozen=True)
class StatusTarget:
    event_id: str
    provider: str
    segment: str
    normalization_schema_version: int
    normalizer_implementation_version: str
    provider_timestamp: datetime
    available_at: datetime
    availability_basis: str
    status_is_known: bool
    status_name: str
    subject_in_scope: bool = True
    target_kind: TargetKind = TargetKind.MARKET_SEGMENT_STATUS

    def __post_init__(self) -> None:
        _sha256(self.event_id, "event_id")
        object.__setattr__(self, "target_kind", TargetKind(self.target_kind))
        if self.target_kind is not TargetKind.MARKET_SEGMENT_STATUS:
            raise ValueError("StatusTarget requires market_segment_status kind")
        object.__setattr__(
            self,
            "provider_timestamp",
            _utc(self.provider_timestamp, "provider_timestamp"),
        )
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))


@dataclass(frozen=True)
class QualityEvaluationInput:
    policy: ParsedQualityPolicy
    context: EvaluationContext
    target: QuoteTarget | StatusTarget
    dependencies: TargetDependencies

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ParsedQualityPolicy):
            raise TypeError("policy must be ParsedQualityPolicy")
        if not isinstance(self.context, EvaluationContext):
            raise TypeError("context must be EvaluationContext")
        if not isinstance(self.target, (QuoteTarget, StatusTarget)):
            raise TypeError("target must be QuoteTarget or StatusTarget")
        if not isinstance(self.dependencies, TargetDependencies):
            raise TypeError("dependencies must be TargetDependencies")


@dataclass(frozen=True)
class QualityEvaluationResult:
    target_kind: TargetKind
    dependency_market_as_of: datetime
    reasons: tuple[QualityReasonOccurrence, ...]
    disposition: QualityDisposition

    @property
    def reason_set_hash(self) -> str:
        return stable_hash(tuple(item.canonical_payload for item in self.reasons))

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "target_kind": self.target_kind.value,
            "dependency_market_as_of": self.dependency_market_as_of,
            "reasons": tuple(item.canonical_payload for item in self.reasons),
            "disposition": self.disposition.value,
            "reason_set_hash": self.reason_set_hash,
        }


def evaluate_quality(command: QualityEvaluationInput) -> QualityEvaluationResult:
    target = command.target
    context = command.context
    target_kind = target.target_kind
    dependency_market_as_of = context.dependency_market_as_of(target.provider_timestamp)
    _require_dependency_shape(target_kind, command.dependencies)

    reasons: list[QualityReasonOccurrence] = []
    _evaluate_common(target, context, reasons)
    if isinstance(target, QuoteTarget):
        _evaluate_quote(target, command.policy, context, command.dependencies, reasons)
    else:
        _evaluate_status_target(target, context, reasons)
    _evaluate_session(command.dependencies.trading_session, target_kind, dependency_market_as_of, reasons)
    _evaluate_connection(command.dependencies.connection, target_kind, dependency_market_as_of, reasons)
    if isinstance(target, QuoteTarget):
        _evaluate_status_dependency(
            command.dependencies.market_segment_status,
            target_kind,
            dependency_market_as_of,
            command.policy,
            reasons,
        )
        _evaluate_subscription(
            command.dependencies.subscription,
            target,
            dependency_market_as_of,
            reasons,
        )

    indexed: dict[tuple[str, str], QualityReasonOccurrence] = {}
    for reason in reasons:
        key = (reason.reason_code, reason.subject_key)
        existing = indexed.get(key)
        if existing is not None and existing != reason:
            raise InvalidQualityEvaluationCommandError(
                "one reason occurrence has conflicting canonical evidence"
            )
        indexed[key] = reason
    ordered = tuple(
        sorted(
            indexed.values(),
            key=lambda item: (
                item.definition.ordinal,
                item.reason_code,
                item.subject_key,
            ),
        )
    )
    disposition = reduce_disposition(item.severity for item in ordered)
    return QualityEvaluationResult(
        target_kind,
        dependency_market_as_of,
        ordered,
        disposition,
    )


def _evaluate_common(
    target: QuoteTarget | StatusTarget,
    context: EvaluationContext,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if target.provider != "upstox":
        _append(
            reasons,
            target.target_kind,
            "unsupported_provider",
            "observation",
            observed=(
                _text("observed_provider", target.provider),
                _text("expected_provider", "upstox"),
            ),
            dependency_ids=(target.event_id,),
        )
    if (
        target.normalization_schema_version != 1
        or target.normalizer_implementation_version != "upstox-v3-normalizer-1"
    ):
        _append(
            reasons,
            target.target_kind,
            "unsupported_normalization_schema",
            "observation",
            observed=(
                _integer("observed_schema", target.normalization_schema_version),
                _text("observed_implementation", target.normalizer_implementation_version),
            ),
            thresholds=(
                _integer("expected_schema", 1),
                _text("expected_implementation", "upstox-v3-normalizer-1"),
            ),
        )
    if not target.subject_in_scope:
        _append(
            reasons,
            target.target_kind,
            "unsupported_subject_scope",
            "observation",
            observed=(
                _state("target_kind", target.target_kind.value),
                _boolean("subject_in_scope", False),
            ),
            dependency_ids=(target.event_id,),
        )
    future_offset = _milliseconds(target.provider_timestamp - context.evaluation_market_as_of)
    if future_offset > 0:
        _append(
            reasons,
            target.target_kind,
            "provider_timestamp_in_future",
            "observation",
            observed=(
                _timestamp("provider_timestamp", target.provider_timestamp),
                _timestamp("evaluation_market_as_of", context.evaluation_market_as_of),
                _decimal("future_offset_ms", future_offset, "milliseconds"),
            ),
        )
    if target.availability_basis == "historical_import":
        _append(
            reasons,
            target.target_kind,
            "historical_import_availability",
            "observation",
            observed=(
                _state("availability_basis", target.availability_basis),
                _timestamp("available_at", target.available_at),
            ),
        )
    elif target.availability_basis != "received":
        _append(
            reasons,
            target.target_kind,
            "availability_basis_invalid",
            "observation",
            observed=(
                _state("availability_basis", _safe_state(target.availability_basis)),
                _timestamp("available_at", target.available_at),
            ),
        )


def _evaluate_quote(
    target: QuoteTarget,
    policy: ParsedQualityPolicy,
    context: EvaluationContext,
    dependencies: TargetDependencies,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if target.provider_timestamp <= context.evaluation_market_as_of:
        threshold = _quote_freshness(policy, target)
        _evaluate_age(
            target.target_kind,
            target.provider_timestamp,
            context.evaluation_market_as_of,
            threshold,
            "quote_age_warning",
            "quote_stale",
            "observation",
            reasons,
        )

    _evaluate_resolution_cutoffs(target, context, reasons)
    _evaluate_provider_segment(target, reasons)
    _evaluate_quote_components(target, reasons)
    _evaluate_numeric_fields(target, reasons)
    _evaluate_completeness(target, reasons)

    _evaluate_provenance_family(
        "instrument_version",
        dependencies.instrument_version,
        target.target_kind,
        reasons,
    )
    _evaluate_provenance_family(
        "provider_mapping",
        dependencies.provider_mapping,
        target.target_kind,
        reasons,
    )
    _evaluate_provenance_family(
        "catalogue_provenance",
        dependencies.catalogue_version,
        target.target_kind,
        reasons,
    )

    instrument = dependencies.instrument_version
    tick_size = instrument.tick_size if instrument is not None and instrument.outcome is DependencyOutcome.SELECTED else None
    if instrument is not None and instrument.outcome is DependencyOutcome.SELECTED:
        if instrument.trading_status != "active":
            _append(
                reasons,
                target.target_kind,
                "instrument_trading_status_not_active",
                "instrument_version",
                observed=(_state("state", _safe_state(instrument.trading_status)),),
                dependency_ids=(instrument.dependency_id,),
            )
    _evaluate_tick_and_market(
        target,
        policy,
        tick_size,
        instrument,
        _provenance_usable(instrument),
        reasons,
    )


def _evaluate_status_target(
    target: StatusTarget,
    context: EvaluationContext,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if target.provider_timestamp <= context.evaluation_market_as_of:
        _evaluate_age(
            target.target_kind,
            target.provider_timestamp,
            context.evaluation_market_as_of,
            {"warning_ms": 60000, "error_ms": 300000},
            "status_age_warning",
            "status_stale",
            "market_segment_status",
            reasons,
        )
    if target.segment not in {"NSE_INDEX", "NSE_FO"}:
        _append(
            reasons,
            target.target_kind,
            "provider_segment_mismatch",
            "provider_segment",
            observed=(
                _state("observed_segment", _safe_state(target.segment)),
                _state("expected_segment", "NSE_INDEX_OR_NSE_FO"),
            ),
        )
    if not target.status_is_known:
        _append(
            reasons,
            target.target_kind,
            "segment_status_unknown",
            "market_segment_status",
            observed=(_state("state", _safe_state(target.status_name)),),
            dependency_ids=(target.event_id,),
        )
    elif target.status_name != "NORMAL_OPEN":
        _append(
            reasons,
            target.target_kind,
            "segment_not_normal_open",
            "market_segment_status",
            observed=(_state("state", _safe_state(target.status_name)),),
            dependency_ids=(target.event_id,),
        )


def _evaluate_resolution_cutoffs(
    target: QuoteTarget,
    context: EvaluationContext,
    reasons: list[QualityReasonOccurrence],
) -> None:
    dependency_market_as_of = context.dependency_market_as_of(target.provider_timestamp)
    if (
        target.resolution_market_as_of > dependency_market_as_of
        or target.resolution_known_as_of > context.evaluation_known_as_of
    ):
        _append(
            reasons,
            target.target_kind,
            "resolution_cutoff_after_evaluation",
            "observation",
            observed=(
                _timestamp("resolution_market_as_of", target.resolution_market_as_of),
                _timestamp("resolution_known_as_of", target.resolution_known_as_of),
            ),
            thresholds=(
                _timestamp("dependency_market_as_of", dependency_market_as_of),
                _timestamp("evaluation_known_as_of", context.evaluation_known_as_of),
            ),
        )


def _evaluate_provider_segment(
    target: QuoteTarget,
    reasons: list[QualityReasonOccurrence],
) -> None:
    expected = {
        TargetKind.UNDERLYING_QUOTE: "NSE_INDEX",
        TargetKind.FUTURES_QUOTE: "NSE_FO",
        TargetKind.OPTION_QUOTE: "NSE_FO",
    }[target.target_kind]
    if "|" not in target.provider_contract_key:
        _append(
            reasons,
            target.target_kind,
            "provider_segment_unresolvable",
            "provider_segment",
            observed=(
                _identifier("provider_key_hash", stable_hash(target.provider_contract_key)),
                _state("observed_segment", "unresolved"),
            ),
            thresholds=(_state("expected_segment", expected),),
        )
        return
    observed = target.provider_contract_key.split("|", 1)[0]
    if observed != expected:
        _append(
            reasons,
            target.target_kind,
            "provider_segment_mismatch",
            "provider_segment",
            observed=(
                _identifier("provider_key_hash", stable_hash(target.provider_contract_key)),
                _state("observed_segment", _safe_state(observed)),
            ),
            thresholds=(_state("expected_segment", expected),),
        )


def _evaluate_quote_components(
    target: QuoteTarget,
    reasons: list[QualityReasonOccurrence],
) -> None:
    for price_name, child_names in (
        ("bid_price", ("bid_size",)),
        ("ask_price", ("ask_size",)),
        ("last_price", ("last_size", "last_trade_at")),
    ):
        if getattr(target, price_name) is None:
            for child_name in child_names:
                if getattr(target, child_name) is not None:
                    _append(
                        reasons,
                        target.target_kind,
                        "orphan_quote_component",
                        child_name,
                        observed=(
                            _text("field_name", child_name),
                            _state("presence", "present_without_parent_price"),
                        ),
                    )

    if target.target_kind is TargetKind.UNDERLYING_QUOTE:
        if target.last_price is None:
            _append(
                reasons,
                target.target_kind,
                "required_last_price_missing",
                "last_price",
                observed=(
                    _text("field_name", "last_price"),
                    _state("presence", "absent"),
                ),
            )
        if (target.bid_price is None) != (target.ask_price is None):
            _append(
                reasons,
                target.target_kind,
                "one_sided_quote",
                "bid_ask_spread",
                observed=(
                    _state("bid_presence", _presence(target.bid_price)),
                    _state("ask_presence", _presence(target.ask_price)),
                ),
            )
    else:
        for field_name, code in (
            ("bid_price", "bid_missing"),
            ("ask_price", "ask_missing"),
            ("bid_size", "bid_size_missing"),
            ("ask_size", "ask_size_missing"),
        ):
            if getattr(target, field_name) is None:
                _append(
                    reasons,
                    target.target_kind,
                    code,
                    field_name,
                    observed=(
                        _text("field_name", field_name),
                        _state("presence", "absent"),
                    ),
                )


def _evaluate_numeric_fields(
    target: QuoteTarget,
    reasons: list[QualityReasonOccurrence],
) -> None:
    for field_name in ("bid_price", "ask_price", "last_price", "previous_close_price"):
        value = getattr(target, field_name)
        if value is None:
            continue
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            _append(
                reasons,
                target.target_kind,
                "invalid_numeric_value",
                field_name,
                observed=(
                    _text("field_name", field_name),
                    _state("violation", "invalid_decimal"),
                ),
            )
    for field_name in ("bid_size", "ask_size", "last_size", "reported_volume", "open_interest"):
        value = getattr(target, field_name)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _append(
                reasons,
                target.target_kind,
                "invalid_numeric_value",
                field_name,
                observed=(
                    _text("field_name", field_name),
                    _state("violation", "invalid_integer"),
                ),
            )

    if target.target_kind is not TargetKind.UNDERLYING_QUOTE:
        for field_name, code in (
            ("bid_price", "bid_zero"),
            ("ask_price", "ask_zero"),
            ("bid_size", "bid_size_zero"),
            ("ask_size", "ask_size_zero"),
        ):
            value = getattr(target, field_name)
            if value == 0:
                _append(
                    reasons,
                    target.target_kind,
                    code,
                    field_name,
                    observed=(
                        _text("field_name", field_name),
                        _decimal_or_integer("value", value),
                    ),
                )
    if target.last_price == 0:
        _append(
            reasons,
            target.target_kind,
            "last_price_zero",
            "last_price",
            observed=(
                _text("field_name", "last_price"),
                _decimal("value", Decimal(0), "price"),
            ),
        )


def _evaluate_completeness(
    target: QuoteTarget,
    reasons: list[QualityReasonOccurrence],
) -> None:
    for field_name, code in (
        ("unadopted_schema_paths", "unadopted_schema_paths_present"),
        ("present_unadopted_message_paths", "present_unadopted_message_paths"),
        ("secondary_payload_paths_present", "secondary_payload_paths_present"),
    ):
        values = getattr(target, field_name)
        if values:
            _append(
                reasons,
                target.target_kind,
                code,
                "observation",
                observed=(
                    _integer("count", len(values)),
                    _identifier("path_set_hash", stable_hash(values)),
                ),
                dependency_ids=(target.event_id,),
            )
    if target.unadopted_depth_level_count > 0:
        _append(
            reasons,
            target.target_kind,
            "depth_truncated",
            "observation",
            observed=(
                _integer("provider_depth", target.provider_depth_levels_present),
                _integer("normalized_depth", target.normalized_depth_levels),
                _integer("truncated_count", target.unadopted_depth_level_count),
            ),
        )


def _evaluate_provenance_family(
    family: str,
    fact: ProvenanceDependencyFact | None,
    target_kind: TargetKind,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if fact is None:
        raise InvalidQualityEvaluationCommandError(
            f"explicit {family} dependency fact is required"
        )
    code_prefix = family
    subject_key = {
        "instrument_version": "instrument_version",
        "provider_mapping": "provider_mapping",
        "catalogue_provenance": "catalogue_version",
    }[family]
    if fact.outcome is DependencyOutcome.ABSENT:
        code = (
            f"{code_prefix}_not_effective"
            if fact.has_visible_knowledge_leaf
            else f"{code_prefix}_missing"
        )
        _append_dependency_reason(reasons, target_kind, code, subject_key, fact)
        return
    if fact.outcome is DependencyOutcome.AMBIGUOUS:
        _append_dependency_reason(
            reasons,
            target_kind,
            f"{code_prefix}_ambiguous",
            subject_key,
            fact,
        )
        return
    if not fact.selected_effective:
        _append_dependency_reason(
            reasons,
            target_kind,
            f"{code_prefix}_not_effective",
            subject_key,
            fact,
        )
        return
    if (
        fact.persisted_semantic_id != fact.selected_semantic_id
        or fact.persisted_record_id != fact.selected_record_id
    ):
        _append(
            reasons,
            target_kind,
            f"{code_prefix}_mismatch",
            subject_key,
            observed=(
                _identifier("persisted_semantic_id", _required_id(fact.persisted_semantic_id)),
                _identifier("persisted_record_id", _required_id(fact.persisted_record_id)),
                _identifier("selected_semantic_id", _required_id(fact.selected_semantic_id)),
                _identifier("selected_record_id", _required_id(fact.selected_record_id)),
            ),
            dependency_ids=(fact.dependency_id,),
        )



def _provenance_usable(fact: ProvenanceDependencyFact | None) -> bool:
    return bool(
        fact is not None
        and fact.outcome is DependencyOutcome.SELECTED
        and fact.selected_effective
        and fact.persisted_semantic_id is not None
        and fact.persisted_record_id is not None
        and fact.persisted_semantic_id == fact.selected_semantic_id
        and fact.persisted_record_id == fact.selected_record_id
    )

def _evaluate_tick_and_market(
    target: QuoteTarget,
    policy: ParsedQualityPolicy,
    tick_size: Decimal | None,
    instrument: ProvenanceDependencyFact | None,
    allow_tick_evaluation: bool,
    reasons: list[QualityReasonOccurrence],
) -> None:
    dependency_ids = () if instrument is None else (instrument.dependency_id,)
    valid_tick = (
        allow_tick_evaluation
        and isinstance(tick_size, Decimal)
        and tick_size.is_finite()
        and tick_size > 0
    )
    if allow_tick_evaluation and not valid_tick:
        _append(
            reasons,
            target.target_kind,
            "tick_size_missing_or_invalid",
            "instrument_version",
            observed=(_state("tick_size_state", "missing_or_invalid"),),
            dependency_ids=dependency_ids,
        )
    valid_prices: dict[str, Decimal] = {}
    for field_name in ("bid_price", "ask_price", "last_price"):
        value = getattr(target, field_name)
        if isinstance(value, Decimal) and value.is_finite() and value > 0:
            valid_prices[field_name] = value
            if valid_tick:
                remainder = value % tick_size
                if remainder != 0:
                    _append(
                        reasons,
                        target.target_kind,
                        "price_not_tick_aligned",
                        field_name,
                        observed=(
                            _text("field_name", field_name),
                            _decimal("price", value, "price"),
                            _decimal("remainder", remainder, "price"),
                        ),
                        thresholds=(_decimal("tick_size", tick_size, "price"),),
                        dependency_ids=dependency_ids,
                    )

    bid = valid_prices.get("bid_price")
    ask = valid_prices.get("ask_price")
    if bid is None or ask is None:
        return
    if bid > ask:
        _append(
            reasons,
            target.target_kind,
            "market_crossed",
            "bid_ask_spread",
            observed=(
                _decimal("bid_price", bid, "price"),
                _decimal("ask_price", ask, "price"),
                _state("comparison", "bid_above_ask"),
            ),
        )
        return
    if bid == ask:
        _append(
            reasons,
            target.target_kind,
            "market_locked",
            "bid_ask_spread",
            observed=(
                _decimal("bid_price", bid, "price"),
                _decimal("ask_price", ask, "price"),
                _state("comparison", "equal"),
            ),
        )
        return
    if not valid_tick:
        return

    spread = ask - bid
    mid = (ask + bid) / Decimal(2)
    spread_ticks = spread / tick_size
    spread_bps = (spread / mid) * Decimal(10000)
    thresholds = _spread_thresholds(policy, target.target_kind)
    error = (
        spread_ticks >= thresholds["error_ticks"]
        or spread_bps >= thresholds["error_bps"]
    )
    warning = (
        spread_ticks >= thresholds["warning_ticks"]
        or spread_bps >= thresholds["warning_bps"]
    )
    if not error and not warning:
        return
    _append(
        reasons,
        target.target_kind,
        "spread_limit_exceeded" if error else "spread_warning",
        "bid_ask_spread",
        observed=(
            _decimal("spread_ticks", spread_ticks, "ticks"),
            _decimal("spread_bps", spread_bps, "basis_points"),
        ),
        thresholds=tuple(
            _decimal(name, value, "ticks" if name.endswith("ticks") else "basis_points")
            for name, value in sorted(thresholds.items())
        ),
    )


def _evaluate_session(
    fact: SessionFact | None,
    target_kind: TargetKind,
    dependency_market_as_of: datetime,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if fact is None:
        raise InvalidQualityEvaluationCommandError(
            "explicit trading_session dependency fact is required"
        )
    if fact.outcome is DependencyOutcome.ABSENT:
        _append_dependency_reason(
            reasons,
            target_kind,
            "trading_session_missing",
            "trading_session",
            fact,
        )
        return
    if fact.outcome is DependencyOutcome.AMBIGUOUS:
        _append_dependency_reason(
            reasons,
            target_kind,
            "trading_session_ambiguous",
            "trading_session",
            fact,
        )
        return
    assert fact.open_at is not None and fact.close_at is not None
    if fact.timezone != "Asia/Kolkata":
        _append(
            reasons,
            target_kind,
            "trading_session_timezone_mismatch",
            "trading_session",
            observed=(
                _state("timezone", _safe_state(fact.timezone)),
                _timestamp("open_at", fact.open_at),
                _timestamp("close_at", fact.close_at),
                _timestamp("dependency_market_as_of", dependency_market_as_of),
            ),
            dependency_ids=(fact.dependency_id,),
        )
    if fact.status != "scheduled":
        _append(
            reasons,
            target_kind,
            "trading_session_not_scheduled",
            "trading_session",
            observed=(
                _state("status", _safe_state(fact.status)),
                _timestamp("open_at", fact.open_at),
                _timestamp("close_at", fact.close_at),
                _timestamp("dependency_market_as_of", dependency_market_as_of),
            ),
            dependency_ids=(fact.dependency_id,),
        )
    if not (fact.open_at <= dependency_market_as_of < fact.close_at):
        _append(
            reasons,
            target_kind,
            "outside_regular_session",
            "trading_session",
            observed=(
                _timestamp("open_at", fact.open_at),
                _timestamp("close_at", fact.close_at),
                _timestamp("dependency_market_as_of", dependency_market_as_of),
            ),
            dependency_ids=(fact.dependency_id,),
        )


def _evaluate_status_dependency(
    fact: MarketStatusFact | None,
    target_kind: TargetKind,
    dependency_market_as_of: datetime,
    policy: ParsedQualityPolicy,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if fact is None:
        raise InvalidQualityEvaluationCommandError(
            "explicit market_segment_status dependency fact is required"
        )
    if fact.outcome is DependencyOutcome.ABSENT:
        _append_dependency_reason(
            reasons,
            target_kind,
            "segment_status_missing",
            "market_segment_status",
            fact,
        )
        return
    if fact.outcome is DependencyOutcome.AMBIGUOUS:
        _append_dependency_reason(
            reasons,
            target_kind,
            "segment_status_ambiguous",
            "market_segment_status",
            fact,
        )
        return
    assert fact.provider_timestamp is not None
    _evaluate_age(
        target_kind,
        fact.provider_timestamp,
        dependency_market_as_of,
        policy.semantic_projection["freshness"]["segment_status"],
        "status_age_warning",
        "status_stale",
        "market_segment_status",
        reasons,
        dependency_ids=(fact.dependency_id,),
    )
    if not fact.status_is_known:
        _append(
            reasons,
            target_kind,
            "segment_status_unknown",
            "market_segment_status",
            observed=(_state("state", _safe_state(fact.status_name)),),
            dependency_ids=(fact.dependency_id,),
        )
    elif fact.status_name != "NORMAL_OPEN":
        _append(
            reasons,
            target_kind,
            "segment_not_normal_open",
            "market_segment_status",
            observed=(_state("state", _safe_state(fact.status_name)),),
            dependency_ids=(fact.dependency_id,),
        )


def _evaluate_connection(
    fact: ConnectionFact | None,
    target_kind: TargetKind,
    dependency_market_as_of: datetime,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if fact is None:
        raise InvalidQualityEvaluationCommandError(
            "explicit connection dependency fact is required"
        )
    if fact.outcome is DependencyOutcome.ABSENT:
        _append_dependency_reason(
            reasons,
            target_kind,
            "connection_state_missing",
            "connection_session",
            fact,
        )
        return
    if fact.outcome is DependencyOutcome.AMBIGUOUS:
        _append_dependency_reason(
            reasons,
            target_kind,
            "connection_state_ambiguous",
            "connection_session",
            fact,
        )
        return
    assert fact.occurred_at is not None
    if fact.state != "authorized":
        _append(
            reasons,
            target_kind,
            "connection_not_authorized",
            "connection_session",
            observed=(
                _state("state", _safe_state(fact.state)),
                _timestamp("occurred_at", fact.occurred_at),
            ),
            dependency_ids=(fact.dependency_id,),
        )
    age = _milliseconds(dependency_market_as_of - fact.occurred_at)
    if age > LEASE_MS:
        _append(
            reasons,
            target_kind,
            "connection_state_stale",
            "connection_session",
            observed=(
                _timestamp("occurred_at", fact.occurred_at),
                _timestamp("dependency_market_as_of", dependency_market_as_of),
                _decimal("age_ms", age, "milliseconds"),
            ),
            thresholds=(_decimal("lease_ms", LEASE_MS, "milliseconds"),),
            dependency_ids=(fact.dependency_id,),
        )


def _evaluate_subscription(
    fact: SubscriptionFact | None,
    target: QuoteTarget,
    dependency_market_as_of: datetime,
    reasons: list[QualityReasonOccurrence],
) -> None:
    if fact is None:
        raise InvalidQualityEvaluationCommandError(
            "explicit subscription dependency fact is required"
        )
    code_by_state = {
        SubscriptionResolutionState.MISSING: "subscription_state_missing",
        SubscriptionResolutionState.AMBIGUOUS: "subscription_state_ambiguous",
        SubscriptionResolutionState.NOT_ACTIVE: "subscription_not_active",
        SubscriptionResolutionState.INSTRUMENT_MISSING: "subscription_instrument_missing",
        SubscriptionResolutionState.MULTIPLE_ACTIVE: "ambiguous_active_subscription",
    }
    code = code_by_state.get(fact.state)
    if code is not None:
        _append(
            reasons,
            target.target_kind,
            code,
            "subscription_scope",
            observed=(
                _integer("candidate_count", fact.candidate_count),
                _identifier(
                    "candidate_set_hash",
                    fact.candidate_set_hash
                    or stable_hash((fact.state.value, fact.candidate_count)),
                ),
            ),
            dependency_ids=(fact.dependency_id,),
        )
        return
    assert fact.occurred_at is not None
    if fact.effective_mode != fact.target_mode:
        _append(
            reasons,
            target.target_kind,
            "subscription_mode_mismatch",
            "subscription_scope",
            observed=(
                _state("observed_mode", _safe_state(fact.effective_mode)),
                _state("expected_mode", _safe_state(fact.target_mode)),
                _identifier("target_key_hash", stable_hash(target.provider_contract_key)),
            ),
            dependency_ids=(fact.dependency_id,),
        )
    age = _milliseconds(dependency_market_as_of - fact.occurred_at)
    if age > LEASE_MS:
        _append(
            reasons,
            target.target_kind,
            "subscription_state_stale",
            "subscription_scope",
            observed=(
                _timestamp("occurred_at", fact.occurred_at),
                _timestamp("dependency_market_as_of", dependency_market_as_of),
                _decimal("age_ms", age, "milliseconds"),
            ),
            thresholds=(_decimal("lease_ms", LEASE_MS, "milliseconds"),),
            dependency_ids=(fact.dependency_id,),
        )


def _evaluate_age(
    target_kind: TargetKind,
    observed_at: datetime,
    cutoff: datetime,
    thresholds: Mapping[str, object],
    warning_code: str,
    error_code: str,
    subject_key: str,
    reasons: list[QualityReasonOccurrence],
    dependency_ids: tuple[str, ...] = (),
) -> None:
    age = _milliseconds(cutoff - observed_at)
    if age < 0:
        return
    warning_ms = Decimal(thresholds["warning_ms"])
    error_ms = Decimal(thresholds["error_ms"])
    code = error_code if age >= error_ms else warning_code if age >= warning_ms else None
    if code is None:
        return
    _append(
        reasons,
        target_kind,
        code,
        subject_key,
        observed=(
            _timestamp("observed_timestamp", observed_at),
            _timestamp("cutoff", cutoff),
            _decimal("age_ms", age, "milliseconds"),
        ),
        thresholds=(
            _decimal("warning_ms", warning_ms, "milliseconds"),
            _decimal("error_ms", error_ms, "milliseconds"),
        ),
        dependency_ids=dependency_ids,
    )


def _append_dependency_reason(
    reasons: list[QualityReasonOccurrence],
    target_kind: TargetKind,
    reason_code: str,
    subject_key: str,
    fact: object,
) -> None:
    candidate_count = getattr(fact, "candidate_count")
    dependency_id = getattr(fact, "dependency_id")
    candidate_set_hash = getattr(fact, "candidate_set_hash", None)
    observed = [_integer("candidate_count", candidate_count)]
    if candidate_set_hash is not None:
        observed.append(_identifier("candidate_set_hash", candidate_set_hash))
    _append(
        reasons,
        target_kind,
        reason_code,
        subject_key,
        observed=tuple(observed),
        dependency_ids=(dependency_id,),
    )


def _append(
    reasons: list[QualityReasonOccurrence],
    target_kind: TargetKind,
    reason_code: str,
    subject_key: str,
    *,
    observed: tuple[EvidenceValue, ...] = (),
    thresholds: tuple[EvidenceValue, ...] = (),
    dependency_ids: tuple[str, ...] = (),
    details: tuple[EvidenceValue, ...] = (),
) -> None:
    reasons.append(
        QualityReasonOccurrence(
            reason_code,
            subject_key,
            target_kind,
            ReasonEvidence(observed, thresholds, dependency_ids, details),
        )
    )


def _require_dependency_shape(
    target_kind: TargetKind,
    dependencies: TargetDependencies,
) -> None:
    required = [dependencies.trading_session, dependencies.connection]
    if target_kind.is_quote:
        required.extend(
            [
                dependencies.provider_mapping,
                dependencies.instrument_version,
                dependencies.catalogue_version,
                dependencies.market_segment_status,
                dependencies.subscription,
            ]
        )
    if any(item is None for item in required):
        raise InvalidQualityEvaluationCommandError(
            "all applicable dependency facts must be explicit"
        )


def _quote_freshness(policy: ParsedQualityPolicy, target: QuoteTarget) -> Mapping[str, object]:
    freshness = policy.semantic_projection["freshness"]
    if target.feed_response_type == "initial_feed":
        return freshness["any_initial"]
    key = {
        TargetKind.UNDERLYING_QUOTE: "underlying_live",
        TargetKind.FUTURES_QUOTE: "future_live",
        TargetKind.OPTION_QUOTE: "option_live",
    }[target.target_kind]
    return freshness[key]


def _spread_thresholds(
    policy: ParsedQualityPolicy,
    target_kind: TargetKind,
) -> Mapping[str, Decimal]:
    key = {
        TargetKind.UNDERLYING_QUOTE: "underlying",
        TargetKind.FUTURES_QUOTE: "future",
        TargetKind.OPTION_QUOTE: "option",
    }[target_kind]
    return policy.semantic_projection["spread"][key]


def _candidate_count_shape(outcome: DependencyOutcome, candidate_count: int) -> None:
    if not isinstance(candidate_count, int) or isinstance(candidate_count, bool):
        raise TypeError("candidate_count must be an integer")
    valid = (
        (outcome is DependencyOutcome.SELECTED and candidate_count == 1)
        or (outcome is DependencyOutcome.ABSENT and candidate_count == 0)
        or (outcome is DependencyOutcome.AMBIGUOUS and 2 <= candidate_count <= 5000)
    )
    if not valid:
        raise ValueError("candidate_count does not match dependency outcome")


def _required_id(value: str | None) -> str:
    if value is None:
        raise InvalidQualityEvaluationCommandError(
            "selected dependency comparison requires persisted IDs"
        )
    return value


def _presence(value: object | None) -> str:
    return "present" if value is not None else "absent"


def _safe_state(value: object | None) -> str:
    if value is None:
        return "missing"
    text = str(value)
    return text if _CONTROLLED.fullmatch(text) else "unsupported"


def _milliseconds(delta) -> Decimal:
    total_microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    return Decimal(total_microseconds) / Decimal(1000)


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("evidence decimal must be finite")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def _text(name: str, value: str) -> EvidenceValue:
    return EvidenceValue(name, "controlled_text", _safe_state(value), "none")


def _state(name: str, value: object | None) -> EvidenceValue:
    return EvidenceValue(name, "state", _safe_state(value), "state")


def _integer(name: str, value: int) -> EvidenceValue:
    return EvidenceValue(name, "integer", str(int(value)), "count")


def _boolean(name: str, value: bool) -> EvidenceValue:
    return EvidenceValue(name, "boolean", value, "none")


def _decimal(name: str, value: Decimal, unit: str) -> EvidenceValue:
    return EvidenceValue(name, "decimal", _canonical_decimal(value), unit)


def _decimal_or_integer(name: str, value: object) -> EvidenceValue:
    if isinstance(value, Decimal):
        return _decimal(name, value, "price")
    return EvidenceValue(name, "integer", str(int(value)), "quantity")


def _timestamp(name: str, value: datetime) -> EvidenceValue:
    return EvidenceValue(
        name,
        "timestamp",
        _utc(value, name).isoformat(),
        "none",
    )


def _identifier(name: str, value: str) -> EvidenceValue:
    return EvidenceValue(name, "identifier", value, "identifier")


def _controlled(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 128:
        raise ValueError(f"{field_name} must be controlled text")
    if _CONTROLLED.fullmatch(value) is None:
        raise ValueError(f"{field_name} contains unsupported characters")


def _sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be canonical prefixed SHA-256")


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
