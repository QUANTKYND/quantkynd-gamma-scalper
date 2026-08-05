from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.market_data.normalization.enums import (
    FrameNormalizationStatus,
    FeedResponseType,
    NormalizationFailureScope,
    ProviderFeedUnion,
    RawCaptureBasis,
)
from app.market_data.normalization.identities import RawMarketFrameIdentityV1
from app.market_data.normalization.models import MarketObservationV1
from app.market_data.normalization.result_hashing import adopted_semantics_hash, full_result_hash


@dataclass(frozen=True)
class NormalizationFailureV1:
    scope: NormalizationFailureScope
    reason_code: str
    provider_contract_key: str | None = None
    segment: str | None = None
    field_paths: tuple[str, ...] = ()
    safe_detail_code: str | None = None
    selected_feed_union: ProviderFeedUnion | None = None
    unadopted_schema_paths: tuple[str, ...] = ()
    present_unadopted_message_paths: tuple[str, ...] = ()
    provider_depth_levels_present: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", NormalizationFailureScope(self.scope))
        if self.selected_feed_union is not None:
            object.__setattr__(self, "selected_feed_union", ProviderFeedUnion(self.selected_feed_union))
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("failure reason code is required")
        if not self.reason_code.replace("_", "").isalnum():
            raise ValueError("failure reason code must be controlled")
        if tuple(sorted(set(self.field_paths))) != self.field_paths:
            raise ValueError("failure field paths must be sorted and unique")
        if any(not isinstance(path, str) or not path.strip() or "\n" in path or "\r" in path for path in self.field_paths):
            raise ValueError("failure field paths must be controlled non-empty text")
        if self.safe_detail_code is not None and (not isinstance(self.safe_detail_code, str) or not self.safe_detail_code.strip()):
            raise ValueError("safe detail code must be non-empty")
        if self.safe_detail_code is not None and not self.safe_detail_code.replace("_", "").isalnum():
            raise ValueError("safe detail code must be controlled")
        for name in ("unadopted_schema_paths", "present_unadopted_message_paths"):
            paths = getattr(self, name)
            if tuple(sorted(set(paths))) != paths:
                raise ValueError(f"{name} must be sorted and unique")
            if any(not isinstance(path, str) or not path.strip() for path in paths):
                raise ValueError(f"{name} must contain non-empty text")
        if self.provider_depth_levels_present is not None and (
            not isinstance(self.provider_depth_levels_present, int)
            or isinstance(self.provider_depth_levels_present, bool)
            or self.provider_depth_levels_present < 0
        ):
            raise ValueError("provider depth metadata must be a non-negative integer")
        if self.scope is NormalizationFailureScope.FRAME:
            if self.provider_contract_key is not None or self.segment is not None:
                raise ValueError("frame failure cannot carry entry scope")
        elif self.scope is NormalizationFailureScope.SUBJECT:
            if not self.provider_contract_key or self.segment is not None:
                raise ValueError("subject failure requires only provider_contract_key")
        elif self.scope is NormalizationFailureScope.SEGMENT:
            if not self.segment or self.provider_contract_key is not None:
                raise ValueError("segment failure requires only segment")

    @property
    def entry_scope_key(self) -> tuple[str, str] | None:
        if self.scope is NormalizationFailureScope.SUBJECT:
            return self.scope.value, self.provider_contract_key or ""
        if self.scope is NormalizationFailureScope.SEGMENT:
            return self.scope.value, self.segment or ""
        return None


@dataclass(frozen=True)
class FrameCaptureProvenanceV1:
    provider_schema_sha256: str
    received_at: datetime | None
    available_at: datetime
    recorded_at: datetime
    capture_basis: RawCaptureBasis
    source_file_id: str | None
    source_record_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_schema_sha256, str) or not self.provider_schema_sha256.strip():
            raise ValueError("provider schema hash is required")
        object.__setattr__(self, "capture_basis", RawCaptureBasis(self.capture_basis))
        for name in ("available_at", "recorded_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at cannot precede available_at")
        if (self.source_file_id is None) != (self.source_record_id is None):
            raise ValueError("source file and record IDs must appear together")
        if self.source_file_id is not None and any(
            not isinstance(value, str) or not value.strip()
            for value in (self.source_file_id, self.source_record_id)
        ):
            raise ValueError("source file and record IDs must be non-empty text")


@dataclass(frozen=True)
class FrameNormalizationResultV1:
    raw_frame_identity: RawMarketFrameIdentityV1
    frame_content_hash: str
    capture_provenance: FrameCaptureProvenanceV1 = field(metadata={"normalization_output": False})
    status: FrameNormalizationStatus
    response_type: FeedResponseType | None
    accepted_events: tuple[MarketObservationV1, ...]
    frame_failure: NormalizationFailureV1 | None
    entry_failures: tuple[NormalizationFailureV1, ...]
    unadopted_schema_paths: tuple[str, ...]
    present_unadopted_message_paths: tuple[str, ...]
    secondary_payload_paths_present: tuple[str, ...]
    decoded_entry_count: int
    accepted_entry_count: int
    failed_entry_count: int
    full_result_hash: str
    adopted_semantics_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.capture_provenance, FrameCaptureProvenanceV1):
            raise TypeError("frame capture provenance is required")
        object.__setattr__(self, "status", FrameNormalizationStatus(self.status))
        if self.response_type is not None:
            object.__setattr__(self, "response_type", FeedResponseType(self.response_type))
        for name in ("decoded_entry_count", "accepted_entry_count", "failed_entry_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.accepted_entry_count != len(self.accepted_events):
            raise ValueError("accepted event count mismatch")
        if self.failed_entry_count != failed_entry_scope_count(self.entry_failures):
            raise ValueError("failed entry count mismatch")
        if self.frame_failure is None and self.decoded_entry_count != self.accepted_entry_count + self.failed_entry_count:
            raise ValueError("decoded entry reconciliation failed")
        if self.frame_failure is not None and self.frame_failure.scope is not NormalizationFailureScope.FRAME:
            raise ValueError("frame_failure must have frame scope")
        if self.frame_failure is not None and (self.accepted_events or self.entry_failures):
            raise ValueError("frame failure cannot coexist with entry outcomes")
        if any(failure.scope is NormalizationFailureScope.FRAME for failure in self.entry_failures):
            raise ValueError("entry failures cannot have frame scope")
        expected_status = (
            FrameNormalizationStatus.FAILED
            if self.frame_failure is not None
            else FrameNormalizationStatus.COMPLETE
            if self.accepted_events and not self.entry_failures
            else FrameNormalizationStatus.PARTIAL
            if self.accepted_events and self.entry_failures
            else FrameNormalizationStatus.FAILED
        )
        if self.status is not expected_status:
            raise ValueError("normalization result status mismatch")
        event_ids = tuple(event.event_id for event in self.accepted_events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("duplicate_normalized_identity")
        for name in (
            "unadopted_schema_paths",
            "present_unadopted_message_paths",
            "secondary_payload_paths_present",
        ):
            values = getattr(self, name)
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and unique")
        expected_adopted_hash = adopted_semantics_hash(
            self.accepted_events,
            self.frame_failure,
            self.entry_failures,
        )
        if self.adopted_semantics_hash != expected_adopted_hash:
            raise ValueError("adopted semantics hash mismatch")
        expected_full_hash = full_result_hash(self.full_hash_projection())
        if self.full_result_hash != expected_full_hash:
            raise ValueError("full result hash mismatch")

    def full_hash_projection(self) -> dict:
        return {
            "schema": "data-1.3-full-result-v1",
            "raw_frame_identity": self.raw_frame_identity,
            "frame_content_hash": self.frame_content_hash,
            "capture_provenance": self.capture_provenance,
            "accepted_events": self.accepted_events,
            "frame_failure": self.frame_failure,
            "entry_failures": self.entry_failures,
            "status": self.status,
            "response_type": self.response_type,
            "decoded_entry_count": self.decoded_entry_count,
            "accepted_entry_count": self.accepted_entry_count,
            "failed_entry_count": self.failed_entry_count,
            "unadopted_schema_paths": self.unadopted_schema_paths,
            "present_unadopted_message_paths": self.present_unadopted_message_paths,
            "secondary_payload_paths_present": self.secondary_payload_paths_present,
        }


@dataclass(frozen=True)
class FrameNormalizationDraftV1:
    accepted_events: tuple[MarketObservationV1, ...]
    entry_failures: tuple[NormalizationFailureV1, ...]
    unadopted_schema_paths: tuple[str, ...]
    present_unadopted_message_paths: tuple[str, ...]
    secondary_payload_paths_present: tuple[str, ...]
    decoded_entry_count: int


def failed_entry_scope_count(failures: tuple[NormalizationFailureV1, ...]) -> int:
    return len({failure.entry_scope_key for failure in failures if failure.entry_scope_key is not None})


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
