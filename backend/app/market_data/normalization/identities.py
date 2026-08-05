from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.hashing import stable_hash
from app.market_data.normalization.enums import RawCaptureBasis
from app.market_data.normalization.errors import ConflictingRawIdentityError, RawFrameValidationError


MAX_FRAME_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class RawMarketFrameIdentityV1:
    provider: str
    provider_schema_id: str
    connection_session_id: str
    source_order_scope_id: str
    source_order: int

    def __post_init__(self) -> None:
        _require_text(
            self.provider,
            self.provider_schema_id,
            self.connection_session_id,
            self.source_order_scope_id,
        )
        if self.provider != "upstox":
            raise RawFrameValidationError("provider must be upstox")
        if not isinstance(self.source_order, int) or isinstance(self.source_order, bool) or self.source_order < 0:
            raise RawFrameValidationError("source_order must be a non-negative integer")

    @property
    def raw_event_id(self) -> str:
        return stable_hash(
            {
                "entity": "raw_market_frame",
                "provider": self.provider,
                "provider_schema_id": self.provider_schema_id,
                "connection_session_id": self.connection_session_id,
                "source_order_scope_id": self.source_order_scope_id,
                "source_order": self.source_order,
            }
        )

    @property
    def provider_event_id(self) -> None:
        return None

    @property
    def provider_sequence(self) -> None:
        return None


@dataclass(frozen=True)
class RawMarketFrameV1:
    provider: str
    provider_schema_id: str
    provider_schema_sha256: str
    connection_session_id: str
    source_order_scope_id: str
    source_order: int
    frame_bytes: bytes
    frame_content_hash: str
    received_at: datetime | None
    available_at: datetime
    recorded_at: datetime
    capture_basis: RawCaptureBasis
    source_file_id: str | None = None
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        identity = self.identity
        _require_text(self.provider_schema_sha256, self.frame_content_hash)
        if not isinstance(self.frame_bytes, bytes) or not self.frame_bytes:
            raise RawFrameValidationError("frame_bytes must be non-empty immutable bytes")
        if len(self.frame_bytes) > MAX_FRAME_BYTES:
            raise RawFrameValidationError("frame_too_large")
        actual_hash = f"sha256:{hashlib.sha256(self.frame_bytes).hexdigest()}"
        if self.frame_content_hash != actual_hash:
            raise RawFrameValidationError("frame_content_hash mismatch")
        object.__setattr__(self, "capture_basis", RawCaptureBasis(self.capture_basis))
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        object.__setattr__(self, "recorded_at", _utc(self.recorded_at, "recorded_at"))
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
        if self.recorded_at < self.available_at:
            raise RawFrameValidationError("recorded_at cannot precede available_at")
        if self.received_at is not None and self.available_at < self.received_at:
            raise RawFrameValidationError("available_at cannot precede received_at")
        if self.capture_basis is RawCaptureBasis.LIVE_RECEIVED:
            if self.received_at is None or self.available_at != self.received_at:
                raise RawFrameValidationError("live_received requires equal receipt and availability")
        if self.capture_basis is RawCaptureBasis.HISTORICAL_IMPORT and self.received_at is not None:
            raise RawFrameValidationError("historical_import requires absent received_at")
        if (self.source_file_id is None) != (self.source_record_id is None):
            raise RawFrameValidationError("source file and record IDs must appear together")
        if self.source_file_id is not None:
            _require_text(self.source_file_id, self.source_record_id or "")
        if identity.provider_schema_id != self.provider_schema_id:
            raise RawFrameValidationError("raw frame identity mismatch")

    @property
    def identity(self) -> RawMarketFrameIdentityV1:
        return RawMarketFrameIdentityV1(
            provider=self.provider,
            provider_schema_id=self.provider_schema_id,
            connection_session_id=self.connection_session_id,
            source_order_scope_id=self.source_order_scope_id,
            source_order=self.source_order,
        )

    @property
    def raw_event_id(self) -> str:
        return self.identity.raw_event_id


@dataclass(frozen=True)
class RawFrameIdentityBatchValidationV1:
    unique_frames: tuple[RawMarketFrameV1, ...]
    exact_duplicate_raw_event_ids: tuple[str, ...]
    independent_same_content_hashes: tuple[str, ...]


def validate_raw_frame_identity_batch(
    frames: tuple[RawMarketFrameV1, ...],
) -> RawFrameIdentityBatchValidationV1:
    by_id: dict[str, RawMarketFrameV1] = {}
    exact_duplicates: set[str] = set()
    content_to_ids: dict[str, set[str]] = {}
    for frame in frames:
        raw_event_id = frame.raw_event_id
        existing = by_id.get(raw_event_id)
        if existing is not None:
            if existing != frame:
                raise ConflictingRawIdentityError(raw_event_id)
            exact_duplicates.add(raw_event_id)
        else:
            by_id[raw_event_id] = frame
        content_to_ids.setdefault(frame.frame_content_hash, set()).add(raw_event_id)
    same_content = sorted(content_hash for content_hash, ids in content_to_ids.items() if len(ids) > 1)
    return RawFrameIdentityBatchValidationV1(
        unique_frames=tuple(sorted(by_id.values(), key=lambda frame: frame.raw_event_id)),
        exact_duplicate_raw_event_ids=tuple(sorted(exact_duplicates)),
        independent_same_content_hashes=tuple(same_content),
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RawFrameValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise RawFrameValidationError("raw frame text values must be non-empty")
