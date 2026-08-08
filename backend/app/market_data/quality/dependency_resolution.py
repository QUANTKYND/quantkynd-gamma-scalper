from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import DependencyOutcome
from app.market_data.quality.errors import QualityDurableCorruptionError

_SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class TemporalCandidate:
    record_id: str
    semantic_id: str
    scope_id: str
    recorded_at: datetime
    receipt_at: datetime
    valid_from: datetime
    valid_until: datetime | None
    supersedes_record_id: str | None
    content_hash: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        for field_name in ("record_id", "semantic_id", "content_hash"):
            _sha256(getattr(self, field_name), field_name)
        if not isinstance(self.scope_id, str) or not self.scope_id.strip():
            raise ValueError("scope_id must be non-empty")
        for field_name in ("recorded_at", "receipt_at", "valid_from"):
            object.__setattr__(self, field_name, _utc(getattr(self, field_name), field_name))
        if self.valid_until is not None:
            object.__setattr__(self, "valid_until", _utc(self.valid_until, "valid_until"))
            if self.valid_until <= self.valid_from:
                raise ValueError("valid_until must be after valid_from")
        if self.supersedes_record_id is not None:
            _sha256(self.supersedes_record_id, "supersedes_record_id")
            if self.supersedes_record_id == self.record_id:
                raise ValueError("a temporal record cannot supersede itself")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def effective_at(self, market_as_of: datetime) -> bool:
        return self.valid_from <= market_as_of and (
            self.valid_until is None or market_as_of < self.valid_until
        )


@dataclass(frozen=True)
class TemporalResolution:
    outcome: DependencyOutcome
    visible_candidates: tuple[TemporalCandidate, ...]
    effective_candidates: tuple[TemporalCandidate, ...]
    selected: TemporalCandidate | None
    has_visible_knowledge_leaf: bool

    @property
    def candidate_set_hash(self) -> str:
        return stable_hash(
            tuple(
                {
                    "record_id": item.record_id,
                    "semantic_id": item.semantic_id,
                    "scope_id": item.scope_id,
                    "content_hash": item.content_hash,
                }
                for item in self.effective_candidates
            )
        )


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    effective_at: datetime
    source_order_scope_id: str
    source_order: int
    content_hash: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        _sha256(self.candidate_id, "candidate_id")
        _sha256(self.content_hash, "content_hash")
        object.__setattr__(self, "effective_at", _utc(self.effective_at, "effective_at"))
        if not isinstance(self.source_order_scope_id, str) or not self.source_order_scope_id.strip():
            raise ValueError("source_order_scope_id must be non-empty")
        if (
            not isinstance(self.source_order, int)
            or isinstance(self.source_order, bool)
            or self.source_order < 0
            or self.source_order > 2**63 - 1
        ):
            raise ValueError("source_order must be an unsigned signed-64-bit integer")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class RankedResolution:
    outcome: DependencyOutcome
    ranked_candidates: tuple[RankedCandidate, ...]
    selected: RankedCandidate | None
    benign_duplicate_ids: tuple[str, ...]

    @property
    def candidate_set_hash(self) -> str:
        return stable_hash(
            tuple(
                {
                    "candidate_id": item.candidate_id,
                    "effective_at": item.effective_at,
                    "source_order_scope_id": item.source_order_scope_id,
                    "source_order": item.source_order,
                    "content_hash": item.content_hash,
                }
                for item in self.ranked_candidates
            )
        )


def resolve_temporal_candidates(
    candidates: tuple[TemporalCandidate, ...],
    market_as_of: datetime,
    known_as_of: datetime,
) -> TemporalResolution:
    market_time = _utc(market_as_of, "market_as_of")
    knowledge_time = _utc(known_as_of, "known_as_of")
    visible = tuple(
        sorted(
            (
                item
                for item in candidates
                if item.recorded_at <= knowledge_time and item.receipt_at <= knowledge_time
            ),
            key=lambda item: item.record_id,
        )
    )
    graph = _validate_temporal_graph(visible)
    knowledge_leaves = tuple(
        item
        for item in visible
        if item.record_id not in graph.successor_by_record_id
    )

    eligible = tuple(item for item in visible if item.effective_at(market_time))
    eligible_ids = {item.record_id for item in eligible}
    hidden: set[str] = set()
    for item in eligible:
        predecessor_id = graph.predecessor_by_record_id[item.record_id]
        while predecessor_id is not None:
            if predecessor_id in eligible_ids:
                hidden.add(predecessor_id)
            predecessor_id = graph.predecessor_by_record_id[predecessor_id]
    effective = tuple(
        sorted(
            (item for item in eligible if item.record_id not in hidden),
            key=lambda item: item.record_id,
        )
    )
    if not effective:
        return TemporalResolution(
            DependencyOutcome.ABSENT,
            visible,
            (),
            None,
            bool(knowledge_leaves),
        )
    if len(effective) > 1:
        return TemporalResolution(
            DependencyOutcome.AMBIGUOUS,
            visible,
            effective,
            None,
            bool(knowledge_leaves),
        )
    return TemporalResolution(
        DependencyOutcome.SELECTED,
        visible,
        effective,
        effective[0],
        bool(knowledge_leaves),
    )


def resolve_ranked_candidates(
    candidates: tuple[RankedCandidate, ...],
    market_as_of: datetime,
) -> RankedResolution:
    market_time = _utc(market_as_of, "market_as_of")
    indexed: dict[str, RankedCandidate] = {}
    for item in candidates:
        existing = indexed.get(item.candidate_id)
        if existing is not None and existing != item:
            raise QualityDurableCorruptionError(
                "one ranked candidate identity has conflicting immutable content"
            )
        indexed[item.candidate_id] = item
    eligible = tuple(item for item in indexed.values() if item.effective_at <= market_time)
    if not eligible:
        return RankedResolution(DependencyOutcome.ABSENT, (), None, ())

    greatest_time = max(item.effective_at for item in eligible)
    at_time = tuple(item for item in eligible if item.effective_at == greatest_time)
    winners: list[RankedCandidate] = []
    for scope_id in sorted({item.source_order_scope_id for item in at_time}):
        scoped = tuple(item for item in at_time if item.source_order_scope_id == scope_id)
        greatest_order = max(item.source_order for item in scoped)
        same_rank = tuple(item for item in scoped if item.source_order == greatest_order)
        content_hashes = {item.content_hash for item in same_rank}
        if len(content_hashes) > 1:
            raise QualityDurableCorruptionError(
                "one source-order rank has conflicting immutable state"
            )
        winners.append(min(same_rank, key=lambda item: item.candidate_id))

    ranked = tuple(sorted(winners, key=lambda item: item.candidate_id))
    if len({item.content_hash for item in ranked}) > 1:
        return RankedResolution(DependencyOutcome.AMBIGUOUS, ranked, None, ())
    selected = min(ranked, key=lambda item: item.candidate_id)
    duplicate_ids = tuple(
        item.candidate_id for item in ranked if item.candidate_id != selected.candidate_id
    )
    return RankedResolution(
        DependencyOutcome.SELECTED,
        ranked,
        selected,
        duplicate_ids,
    )


@dataclass(frozen=True)
class _TemporalGraph:
    predecessor_by_record_id: Mapping[str, str | None]
    successor_by_record_id: Mapping[str, str]


def _validate_temporal_graph(candidates: tuple[TemporalCandidate, ...]) -> _TemporalGraph:
    indexed: dict[str, TemporalCandidate] = {}
    for item in candidates:
        existing = indexed.get(item.record_id)
        if existing is not None and existing != item:
            raise QualityDurableCorruptionError(
                "one temporal record identity has conflicting immutable content"
            )
        indexed[item.record_id] = item

    predecessors: dict[str, str | None] = {}
    successors: dict[str, str] = {}
    for record_id, item in indexed.items():
        predecessor_id = item.supersedes_record_id
        predecessors[record_id] = predecessor_id
        if predecessor_id is None:
            continue
        predecessor = indexed.get(predecessor_id)
        if predecessor is None:
            raise QualityDurableCorruptionError(
                "visible temporal successor target is missing"
            )
        if predecessor.scope_id != item.scope_id:
            raise QualityDurableCorruptionError(
                "temporal successor crosses a semantic scope"
            )
        if item.recorded_at <= predecessor.recorded_at:
            raise QualityDurableCorruptionError(
                "temporal successor is not recorded after its predecessor"
            )
        existing_successor = successors.get(predecessor_id)
        if existing_successor is not None and existing_successor != record_id:
            raise QualityDurableCorruptionError(
                "temporal successor graph contains a branch"
            )
        successors[predecessor_id] = record_id

    for starting_id in indexed:
        visited: set[str] = set()
        current_id: str | None = starting_id
        while current_id is not None:
            if current_id in visited:
                raise QualityDurableCorruptionError(
                    "temporal successor graph contains a cycle"
                )
            visited.add(current_id)
            current_id = successors.get(current_id)
    return _TemporalGraph(
        MappingProxyType(predecessors),
        MappingProxyType(successors),
    )


def _sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be canonical prefixed SHA-256")


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
