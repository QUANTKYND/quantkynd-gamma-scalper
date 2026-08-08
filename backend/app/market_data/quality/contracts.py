from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Iterable

from app.core.hashing import stable_hash

_SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTROLLED_TEXT = re.compile(r"[A-Za-z0-9_.:-]+\Z")

POLICY_NAME = "upstox_nse_nifty_index_derivatives_quality"
POLICY_PROVIDER = "upstox"
OBSERVATION_DOMAIN = "normalized_market_observation"
QUALITY_POLICY_SCHEMA_VERSION = 1
QUALITY_EVALUATOR_IMPLEMENTATION_VERSION = "market-data-quality-evaluator-1"
ASSESSMENT_RUN_SCHEMA_VERSION = 1
MARKET_TIME_BASIS = "provider_timestamp_v1"


class QualityDisposition(StrEnum):
    ELIGIBLE = "eligible"
    WARNING = "warning"
    INELIGIBLE = "ineligible"

    @property
    def is_eligible(self) -> bool:
        return self in {self.ELIGIBLE, self.WARNING}


class QualitySeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class DependencyOutcome(StrEnum):
    SELECTED = "selected"
    ABSENT = "absent"
    AMBIGUOUS = "ambiguous"


class TargetKind(StrEnum):
    UNDERLYING_QUOTE = "underlying_quote"
    FUTURES_QUOTE = "futures_quote"
    OPTION_QUOTE = "option_quote"
    MARKET_SEGMENT_STATUS = "market_segment_status"

    @property
    def is_quote(self) -> bool:
        return self is not self.MARKET_SEGMENT_STATUS


class ReceiptBasis(StrEnum):
    LEGACY_BOOTSTRAP = "legacy_bootstrap"
    REPOSITORY_INSERT = "repository_insert"


@dataclass(frozen=True)
class EvaluationContext:
    evaluation_market_as_of: datetime
    evaluation_known_as_of: datetime

    def __post_init__(self) -> None:
        market = _utc(self.evaluation_market_as_of, "evaluation_market_as_of")
        known = _utc(self.evaluation_known_as_of, "evaluation_known_as_of")
        if known < market:
            raise ValueError("evaluation_known_as_of cannot precede evaluation_market_as_of")
        object.__setattr__(self, "evaluation_market_as_of", market)
        object.__setattr__(self, "evaluation_known_as_of", known)

    def dependency_market_as_of(self, provider_timestamp: datetime) -> datetime:
        provider_time = _utc(provider_timestamp, "provider_timestamp")
        return min(provider_time, self.evaluation_market_as_of)


@dataclass(frozen=True)
class QualityPolicyIdentity:
    policy_name: str = POLICY_NAME
    provider: str = POLICY_PROVIDER
    observation_domain: str = OBSERVATION_DOMAIN

    def __post_init__(self) -> None:
        _controlled(self.policy_name, "policy_name")
        _controlled(self.provider, "provider")
        _controlled(self.observation_domain, "observation_domain")

    @property
    def policy_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_policy",
                "policy_name": self.policy_name,
                "provider": self.provider,
                "observation_domain": self.observation_domain,
            }
        )


@dataclass(frozen=True)
class QualityPolicyVersionIdentity:
    policy_id: str
    version: int = 1

    def __post_init__(self) -> None:
        _sha256_id(self.policy_id, "policy_id")
        _positive_int(self.version, "version")

    @property
    def policy_version_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_policy_version",
                "policy_id": self.policy_id,
                "version": self.version,
            }
        )


@dataclass(frozen=True)
class AssessmentIdentity:
    event_id: str
    policy_version_id: str
    context: EvaluationContext

    def __post_init__(self) -> None:
        _sha256_id(self.event_id, "event_id")
        _sha256_id(self.policy_version_id, "policy_version_id")
        if not isinstance(self.context, EvaluationContext):
            raise TypeError("context must be EvaluationContext")

    @property
    def assessment_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_assessment",
                "event_id": self.event_id,
                "policy_version_id": self.policy_version_id,
                "evaluation_market_as_of": self.context.evaluation_market_as_of,
                "evaluation_known_as_of": self.context.evaluation_known_as_of,
            }
        )


@dataclass(frozen=True)
class AssessmentRunIdentity:
    policy_version_id: str
    context: EvaluationContext
    ordered_target_event_ids: tuple[str, ...]
    quality_evaluator_implementation_version: str = (
        QUALITY_EVALUATOR_IMPLEMENTATION_VERSION
    )
    assessment_run_schema_version: int = ASSESSMENT_RUN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _sha256_id(self.policy_version_id, "policy_version_id")
        if not isinstance(self.context, EvaluationContext):
            raise TypeError("context must be EvaluationContext")
        _positive_int(self.assessment_run_schema_version, "assessment_run_schema_version")
        _controlled(
            self.quality_evaluator_implementation_version,
            "quality_evaluator_implementation_version",
        )
        targets = _sorted_unique_ids(self.ordered_target_event_ids)
        if not 1 <= len(targets) <= 5000:
            raise ValueError("ordered_target_event_ids must contain 1..5000 IDs")
        object.__setattr__(self, "ordered_target_event_ids", targets)

    @property
    def assessment_run_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_assessment_run",
                "assessment_run_schema_version": self.assessment_run_schema_version,
                "policy_version_id": self.policy_version_id,
                "evaluation_market_as_of": self.context.evaluation_market_as_of,
                "evaluation_known_as_of": self.context.evaluation_known_as_of,
                "ordered_target_event_ids": self.ordered_target_event_ids,
                "quality_evaluator_implementation_version": (
                    self.quality_evaluator_implementation_version
                ),
            }
        )


@dataclass(frozen=True)
class SourceArtifactIdentity:
    policy_version_id: str
    source_sha256: str
    source_byte_count: int
    media_type: str = "application/yaml"
    parser_label: str = "data15-strict-yaml-1"

    def __post_init__(self) -> None:
        _sha256_id(self.policy_version_id, "policy_version_id")
        _sha256_id(self.source_sha256, "source_sha256")
        if not isinstance(self.source_byte_count, int) or isinstance(self.source_byte_count, bool):
            raise TypeError("source_byte_count must be an integer")
        if not 1 <= self.source_byte_count <= 262_144:
            raise ValueError("source_byte_count must be in 1..262144")
        _controlled(self.media_type, "media_type", allow_slash=True)
        _controlled(self.parser_label, "parser_label")

    @property
    def source_artifact_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_policy_source_artifact",
                "policy_version_id": self.policy_version_id,
                "source_sha256": self.source_sha256,
                "source_byte_count": self.source_byte_count,
                "media_type": self.media_type,
                "parser_label": self.parser_label,
            }
        )


@dataclass(frozen=True)
class ReasonDefinitionIdentity:
    policy_version_id: str
    reason_code: str

    def __post_init__(self) -> None:
        _sha256_id(self.policy_version_id, "policy_version_id")
        _snake_case(self.reason_code, "reason_code")

    @property
    def reason_definition_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_reason_definition",
                "policy_version_id": self.policy_version_id,
                "reason_code": self.reason_code,
            }
        )


@dataclass(frozen=True)
class ReasonOccurrenceIdentity:
    assessment_id: str
    reason_code: str
    subject_key: str

    def __post_init__(self) -> None:
        _sha256_id(self.assessment_id, "assessment_id")
        _snake_case(self.reason_code, "reason_code")
        _snake_case(self.subject_key, "subject_key")

    @property
    def reason_occurrence_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_assessment_reason",
                "assessment_id": self.assessment_id,
                "reason_code": self.reason_code,
                "subject_key": self.subject_key,
            }
        )


@dataclass(frozen=True)
class DependencyIdentity:
    assessment_id: str
    dependency_kind: str
    subject_key: str

    def __post_init__(self) -> None:
        _sha256_id(self.assessment_id, "assessment_id")
        _snake_case(self.dependency_kind, "dependency_kind")
        _snake_case(self.subject_key, "subject_key")

    @property
    def assessment_dependency_id(self) -> str:
        return stable_hash(
            {
                "entity": "market_data_quality_assessment_dependency",
                "assessment_id": self.assessment_id,
                "dependency_kind": self.dependency_kind,
                "subject_key": self.subject_key,
            }
        )


def reduce_disposition(severities: Iterable[QualitySeverity]) -> QualityDisposition:
    values = tuple(QualitySeverity(value) for value in severities)
    if QualitySeverity.ERROR in values:
        return QualityDisposition.INELIGIBLE
    if QualitySeverity.WARNING in values:
        return QualityDisposition.WARNING
    return QualityDisposition.ELIGIBLE


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _sha256_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be canonical prefixed SHA-256")


def _controlled(value: str, field_name: str, *, allow_slash: bool = False) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 128:
        raise ValueError(f"{field_name} must be controlled text of 1..128 bytes")
    pattern = r"[A-Za-z0-9_./:-]+\Z" if allow_slash else _CONTROLLED_TEXT
    if re.fullmatch(pattern, value) is None:
        raise ValueError(f"{field_name} contains unsupported characters")


def _snake_case(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value.encode("utf-8")) <= 128
        or re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", value) is None
    ):
        raise ValueError(f"{field_name} must be controlled lowercase snake case")


def _sorted_unique_ids(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(values)
    for value in normalized:
        _sha256_id(value, "target_event_id")
    if len(set(normalized)) != len(normalized):
        raise ValueError("target event IDs must be unique")
    return tuple(sorted(normalized))
