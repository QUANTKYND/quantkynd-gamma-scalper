from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
import hashlib

from app.core.hashing import canonical_json, stable_hash

CANONICAL_SCHEMA_VERSION = 1
CANONICAL_IMPLEMENTATION = "upstox-v3-normalizer-1"
DATA14_ADVISORY_LOCK_NAMESPACE = -1377601296
DATA14_LOCK_STRIPE_COUNT = 64
PERSISTENCE_SCHEMA_VERSION = 1

def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)

def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value

@dataclass(frozen=True)
class DurableResultIdentity:
    raw_event_id: str
    normalization_schema_version: int = 1
    normalizer_implementation_version: str = CANONICAL_IMPLEMENTATION
    def __post_init__(self):
        _text(self.raw_event_id, "raw_event_id")
        if self.normalization_schema_version != 1:
            raise ValueError("unsupported normalization schema version")
        if self.normalizer_implementation_version != CANONICAL_IMPLEMENTATION:
            raise ValueError("unsupported normalizer implementation")
    @property
    def result_id(self) -> str:
        return stable_hash({"entity":"market_normalization_result", "raw_event_id":self.raw_event_id, "normalization_schema_version":self.normalization_schema_version})

@dataclass(frozen=True)
class FailureIdentity:
    result_id: str
    scope: str
    reason_code: str
    provider_contract_key: str | None = None
    segment: str | None = None
    def __post_init__(self):
        for n in ("result_id", "scope", "reason_code"):
            _text(getattr(self,n), n)
        if self.scope not in {"frame", "subject", "segment"}:
            raise ValueError("unsupported failure scope")
        if self.scope == "subject" and not self.provider_contract_key: raise ValueError("subject failure key required")
        if self.scope == "segment" and not self.segment: raise ValueError("segment failure required")
    @property
    def failure_id(self) -> str:
        return stable_hash({"entity":"market_normalization_failure", **self.__dict__})

@dataclass(frozen=True)
class LifecycleBatchIdentity:
    provider: str
    connection_session_id: str
    source_order_scope_id: str
    source_order: int
    def __post_init__(self):
        for n in ("provider","connection_session_id","source_order_scope_id"): _text(getattr(self,n), n)
        if not isinstance(self.source_order,int) or isinstance(self.source_order,bool) or self.source_order < 0 or self.source_order > 9223372036854775807: raise ValueError("invalid source order")
    @property
    def batch_id(self): return stable_hash({"entity":"provider_lifecycle_batch", **self.__dict__})

@dataclass(frozen=True)
class QueryCursor:
    schema_version: int
    position: str | None = None
    def __post_init__(self):
        if self.schema_version != PERSISTENCE_SCHEMA_VERSION: raise ValueError("unsupported cursor schema")
        if self.position is not None: _text(self.position, "position")

@dataclass(frozen=True)
class PersistenceSummary:
    result_id: str
    inserted: bool
    accepted_count: int
    failure_count: int
    def __post_init__(self):
        _text(self.result_id,"result_id")
        if any(not isinstance(v,int) or v<0 for v in (self.accepted_count,self.failure_count)): raise ValueError("counts must be non-negative")

@dataclass(frozen=True)
class FramePersistenceCommand:
    raw_frame: Any
    normalization_result: Any
    market_as_of: datetime
    known_as_of: datetime
    def __post_init__(self):
        object.__setattr__(self,"market_as_of",_utc(self.market_as_of,"market_as_of")); object.__setattr__(self,"known_as_of",_utc(self.known_as_of,"known_as_of"))
        if self.known_as_of < self.market_as_of: raise ValueError("known_as_of cannot precede market_as_of")

class MarketEventRepository(Protocol):
    async def persist_frame_result(self, command: FramePersistenceCommand) -> PersistenceSummary: ...
    async def get_result(self, result_id: str): ...

class PersistenceUnitOfWork(Protocol):
    market_events: MarketEventRepository
    async def __aenter__(self): ...
    async def __aexit__(self, exc_type, exc_value, traceback): ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
