from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Generic, Iterable, TypeVar

from app.core.hashing import stable_hash


class TemporalRecordKind(StrEnum):
    CATALOGUE_VERSION = "catalogue_version"
    INSTRUMENT_VERSION = "instrument_version"
    PROVIDER_MAPPING = "provider_mapping"
    TRADING_SESSION_VERSION = "trading_session_version"


class InvalidTemporalGraphError(ValueError):
    pass


class TemporalSupersessionConflictError(ValueError):
    pass


class AmbiguousPointInTimeResultError(ValueError):
    pass


@dataclass(frozen=True)
class TemporalRecord:
    kind: TemporalRecordKind
    semantic_id: str
    scope_id: str
    recorded_at: datetime
    supersedes_record_id: str | None = None
    source_provenance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", TemporalRecordKind(self.kind))
        if not self.semantic_id.strip() or not self.scope_id.strip():
            raise ValueError("temporal semantic and scope identities are required")
        if self.supersedes_record_id is not None and not self.supersedes_record_id.strip():
            raise ValueError("supersedes_record_id must not be blank")
        if self.source_provenance_id is not None and not self.source_provenance_id.strip():
            raise ValueError("source_provenance_id must not be blank")
        recorded_at = _utc(self.recorded_at, "recorded_at")
        object.__setattr__(self, "recorded_at", recorded_at)
        if self.supersedes_record_id == self.record_id:
            raise ValueError("a temporal record cannot supersede itself")

    @property
    def record_id(self) -> str:
        return stable_hash(
            {
                "entity": f"{self.kind.value}_record",
                "semantic_id": self.semantic_id,
                "scope_id": self.scope_id,
                "recorded_at": self.recorded_at,
                "supersedes_record_id": self.supersedes_record_id,
                "source_provenance_id": self.source_provenance_id,
            }
        )


ValueType = TypeVar("ValueType")


@dataclass(frozen=True)
class TemporalState(Generic[ValueType]):
    record: TemporalRecord
    value: ValueType


def resolve_temporal_state(
    states: Iterable[TemporalState[ValueType]],
    known_as_of: datetime | None,
    market_eligible: Callable[[ValueType], bool],
) -> TemporalState[ValueType] | None:
    knowledge_time = _utc(known_as_of, "known_as_of") if known_as_of is not None else None
    visible = [
        state
        for state in states
        if knowledge_time is None or state.record.recorded_at <= knowledge_time
    ]
    indexed = _validated_visible_graph(visible)
    eligible = [state for state in indexed.values() if market_eligible(state.value)]
    hidden = {
        state.record.supersedes_record_id
        for state in eligible
        if state.record.supersedes_record_id is not None
    }
    leaves = sorted(
        (state for state in eligible if state.record.record_id not in hidden),
        key=lambda state: state.record.record_id,
    )
    if len(leaves) > 1:
        raise AmbiguousPointInTimeResultError(
            "multiple temporal records are eligible leaves at the requested cutoffs"
        )
    return leaves[0] if leaves else None


def resolve_temporal_knowledge_leaf(
    states: Iterable[TemporalState[ValueType]],
    known_as_of: datetime | None,
) -> TemporalState[ValueType] | None:
    knowledge_time = _utc(known_as_of, "known_as_of") if known_as_of is not None else None
    visible = [
        state
        for state in states
        if knowledge_time is None or state.record.recorded_at <= knowledge_time
    ]
    indexed = _validated_visible_graph(visible)
    superseded = {
        state.record.supersedes_record_id
        for state in indexed.values()
        if state.record.supersedes_record_id is not None
    }
    leaves = sorted(
        (state for state in indexed.values() if state.record.record_id not in superseded),
        key=lambda state: state.record.record_id,
    )
    if len(leaves) > 1:
        raise AmbiguousPointInTimeResultError(
            "multiple temporal records are current knowledge leaves"
        )
    return leaves[0] if leaves else None


def catalogue_temporal_record(value, supersedes_record_id: str | None = None) -> TemporalRecord:
    return TemporalRecord(
        TemporalRecordKind.CATALOGUE_VERSION,
        value.catalogue_version_id,
        value.provider,
        value.recorded_at,
        supersedes_record_id,
        value.source_content_hash,
    )


def instrument_version_temporal_record(
    value,
    supersedes_record_id: str | None = None,
) -> TemporalRecord:
    if value.superseded_at is not None:
        raise ValueError("superseded_at is derived and cannot be persisted directly")
    scope_id = getattr(value, "instrument_id", None) or value.contract_id
    return TemporalRecord(
        TemporalRecordKind.INSTRUMENT_VERSION,
        value.version_id,
        scope_id,
        value.recorded_at,
        supersedes_record_id,
        value.catalogue_version_id,
    )


def provider_mapping_temporal_record(
    value,
    supersedes_record_id: str | None = None,
) -> TemporalRecord:
    if value.superseded_at is not None:
        raise ValueError("superseded_at is derived and cannot be persisted directly")
    scope_id = stable_hash(
        {
            "entity": "provider_mapping_scope",
            "provider": value.provider,
            "provider_contract_key": value.provider_contract_key,
        }
    )
    provenance = stable_hash(
        {
            "provider_payload_hash": value.provider_payload_hash,
            "source_row_identity": value.source_row_identity,
        }
    )
    return TemporalRecord(
        TemporalRecordKind.PROVIDER_MAPPING,
        value.mapping_id,
        scope_id,
        value.recorded_at,
        supersedes_record_id,
        provenance,
    )


def trading_session_version_temporal_record(
    value,
    supersedes_record_id: str | None = None,
) -> TemporalRecord:
    if value.superseded_at is not None:
        raise ValueError("superseded_at is derived and cannot be persisted directly")
    return TemporalRecord(
        TemporalRecordKind.TRADING_SESSION_VERSION,
        value.session_version_id,
        value.session_id,
        value.recorded_at,
        supersedes_record_id,
    )


def _validated_visible_graph(
    states: Iterable[TemporalState[ValueType]],
) -> dict[str, TemporalState[ValueType]]:
    indexed: dict[str, TemporalState[ValueType]] = {}
    for state in states:
        record_id = state.record.record_id
        existing = indexed.get(record_id)
        if existing is not None and existing != state:
            raise InvalidTemporalGraphError(
                "one temporal record identity has conflicting immutable content"
            )
        indexed[record_id] = state
    successors: dict[str, str] = {}
    for record_id, state in indexed.items():
        target_id = state.record.supersedes_record_id
        if target_id is None:
            continue
        if target_id == record_id:
            raise InvalidTemporalGraphError("temporal records cannot supersede themselves")
        target = indexed.get(target_id)
        if target is None:
            raise InvalidTemporalGraphError("visible temporal successor target is missing")
        if target.record.kind != state.record.kind or target.record.scope_id != state.record.scope_id:
            raise InvalidTemporalGraphError("temporal successor crosses an entity scope")
        if state.record.recorded_at <= target.record.recorded_at:
            raise InvalidTemporalGraphError(
                "temporal successor must be recorded strictly after its target"
            )
        existing_successor = successors.get(target_id)
        if existing_successor is not None and existing_successor != record_id:
            raise InvalidTemporalGraphError("temporal successor graph contains a branch")
        successors[target_id] = record_id
    for starting_id in indexed:
        visited: set[str] = set()
        current_id: str | None = starting_id
        while current_id is not None:
            if current_id in visited:
                raise InvalidTemporalGraphError("temporal successor graph contains a cycle")
            visited.add(current_id)
            current_id = successors.get(current_id)
    return indexed


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
