from __future__ import annotations

from dataclasses import dataclass

from app.market_data.normalization.enums import FrameNormalizationStatus
from app.market_data.normalization.identities import RawMarketFrameIdentityV1
from app.market_data.normalization.models import MarketObservationV1


@dataclass(frozen=True)
class NormalizationFailureV1:
    reason_code: str
    provider_contract_key: str | None = None
    segment: str | None = None

    def __post_init__(self) -> None:
        if not self.reason_code:
            raise ValueError("failure reason code is required")
        if self.provider_contract_key is not None and self.segment is not None:
            raise ValueError("failure scope must be singular")


@dataclass(frozen=True)
class FrameNormalizationResultV1:
    raw_frame_identity: RawMarketFrameIdentityV1
    frame_content_hash: str
    status: FrameNormalizationStatus
    accepted_events: tuple[MarketObservationV1, ...]
    failures: tuple[NormalizationFailureV1, ...]
    unadopted_schema_paths: tuple[str, ...]
    present_unadopted_message_paths: tuple[str, ...]
    secondary_payload_paths_present: tuple[str, ...]
    decoded_entry_count: int
    accepted_event_count: int
    failed_entry_count: int
    full_result_hash: str
    adopted_semantics_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", FrameNormalizationStatus(self.status))
        if self.accepted_event_count != len(self.accepted_events):
            raise ValueError("accepted event count mismatch")
        if self.failed_entry_count != len(self.failures):
            raise ValueError("failed entry count mismatch")
        if self.decoded_entry_count != self.accepted_event_count + self.failed_entry_count:
            raise ValueError("decoded entry reconciliation failed")
        expected_status = (
            FrameNormalizationStatus.COMPLETE
            if self.accepted_events and not self.failures
            else FrameNormalizationStatus.PARTIAL
            if self.accepted_events and self.failures
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
    failures: tuple[NormalizationFailureV1, ...]
    unadopted_schema_paths: tuple[str, ...]
    present_unadopted_message_paths: tuple[str, ...]
    secondary_payload_paths_present: tuple[str, ...]
    decoded_entry_count: int
