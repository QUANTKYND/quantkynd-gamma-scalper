from __future__ import annotations

from dataclasses import dataclass

from app.market_data.normalization.enums import (
    FrameNormalizationStatus,
    NormalizationFailureScope,
    ProviderFeedUnion,
)
from app.market_data.normalization.identities import RawMarketFrameIdentityV1
from app.market_data.normalization.models import MarketObservationV1


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
class FrameNormalizationResultV1:
    raw_frame_identity: RawMarketFrameIdentityV1
    frame_content_hash: str
    status: FrameNormalizationStatus
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
        object.__setattr__(self, "status", FrameNormalizationStatus(self.status))
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
