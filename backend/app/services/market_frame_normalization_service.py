from __future__ import annotations

from datetime import UTC, datetime

from app.market_data.normalization.enums import FeedResponseType, FrameNormalizationStatus, NormalizationFailureScope
from app.market_data.normalization.errors import FrameDecodeError
from app.market_data.normalization.identities import RawMarketFrameV1
from app.market_data.normalization.ports import MarketSubjectResolver
from app.market_data.normalization.results import (
    FrameNormalizationResultV1,
    FrameCaptureProvenanceV1,
    NormalizationFailureV1,
    failed_entry_scope_count,
)
from app.market_data.normalization.serialization import adopted_semantics_hash, full_result_hash
from app.market_data.upstox.v3_decoder import decode_upstox_v3_frame
from app.market_data.upstox.v3_normalizer import normalize_upstox_v3_frame
from app.market_data.upstox.proto import MarketDataFeed_pb2


class MarketFrameNormalizationService:
    def __init__(self, subject_resolver: MarketSubjectResolver) -> None:
        self._subject_resolver = subject_resolver

    async def normalize(
        self,
        frame: RawMarketFrameV1,
        *,
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> FrameNormalizationResultV1:
        market_cutoff = _utc(market_as_of, "market_as_of")
        knowledge_cutoff = _utc(known_as_of, "known_as_of")
        try:
            decoded = decode_upstox_v3_frame(frame)
        except FrameDecodeError as error:
            response_type = (
                _response_type(error.response_type_numeric)
                if error.response_type_numeric is not None
                else None
            )
            frame_failure = NormalizationFailureV1(
                scope=NormalizationFailureScope.FRAME,
                reason_code=error.code,
            )
            return _result(frame, response_type, (), frame_failure, (), (), (), (), 0)
        response_type = _response_type(decoded.response_type_numeric)
        subjects = None
        if decoded.response_type_numeric != MarketDataFeed_pb2.market_info:
            subjects = await self._subject_resolver.resolve_many(
                frame.provider,
                decoded.provider_contract_keys,
                market_cutoff,
                knowledge_cutoff,
            )
            if (
                subjects.provider_contract_keys != decoded.provider_contract_keys
                or any(subject.provider != frame.provider for subject in subjects.resolved)
                or any(
                    subject.resolution_market_as_of != market_cutoff
                    or subject.resolution_known_as_of != knowledge_cutoff
                    for subject in subjects.resolved
                )
            ):
                frame_failure = NormalizationFailureV1(
                    scope=NormalizationFailureScope.FRAME,
                    reason_code="invalid_subject_resolution_batch",
                )
                return _result(
                    frame,
                    response_type,
                    (),
                    frame_failure,
                    (),
                    (),
                    (),
                    (),
                    len(decoded.provider_contract_keys),
                )
        draft = normalize_upstox_v3_frame(decoded, frame, subjects)
        event_ids = tuple(event.event_id for event in draft.accepted_events)
        if len(event_ids) != len(set(event_ids)):
            frame_failure = NormalizationFailureV1(
                scope=NormalizationFailureScope.FRAME,
                reason_code="duplicate_normalized_identity",
            )
            return _result(
                frame,
                response_type,
                (),
                frame_failure,
                (),
                draft.unadopted_schema_paths,
                draft.present_unadopted_message_paths,
                draft.secondary_payload_paths_present,
                draft.decoded_entry_count,
            )
        return _result(
            frame,
            response_type,
            draft.accepted_events,
            None,
            draft.entry_failures,
            draft.unadopted_schema_paths,
            draft.present_unadopted_message_paths,
            draft.secondary_payload_paths_present,
            draft.decoded_entry_count,
        )


def _result(frame, response_type, events, frame_failure, entry_failures, unadopted, present, secondary, decoded_count):
    failed_count = failed_entry_scope_count(entry_failures)
    status = (
        FrameNormalizationStatus.FAILED
        if frame_failure is not None
        else FrameNormalizationStatus.COMPLETE
        if events and not entry_failures
        else FrameNormalizationStatus.PARTIAL
        if events and entry_failures
        else FrameNormalizationStatus.FAILED
    )
    adopted_hash = adopted_semantics_hash(events, frame_failure, entry_failures)
    capture_provenance = FrameCaptureProvenanceV1(
        provider_schema_sha256=f"sha256:{frame.provider_schema_sha256}",
        received_at=frame.received_at,
        available_at=frame.available_at,
        recorded_at=frame.recorded_at,
        capture_basis=frame.capture_basis,
        source_file_id=frame.source_file_id,
        source_record_id=frame.source_record_id,
    )
    full_projection = {
            "schema": "data-1.3-full-result-v1",
            "raw_frame_identity": frame.identity,
            "frame_content_hash": frame.frame_content_hash,
            "capture_provenance": capture_provenance,
            "accepted_events": events,
            "frame_failure": frame_failure,
            "entry_failures": entry_failures,
            "status": status,
            "response_type": response_type,
            "decoded_entry_count": decoded_count,
            "accepted_entry_count": len(events),
            "failed_entry_count": failed_count,
            "unadopted_schema_paths": unadopted,
            "present_unadopted_message_paths": present,
            "secondary_payload_paths_present": secondary,
        }
    full_hash = full_result_hash(full_projection)
    return FrameNormalizationResultV1(
        raw_frame_identity=frame.identity,
        frame_content_hash=frame.frame_content_hash,
        capture_provenance=capture_provenance,
        status=status,
        response_type=response_type,
        accepted_events=events,
        frame_failure=frame_failure,
        entry_failures=entry_failures,
        unadopted_schema_paths=unadopted,
        present_unadopted_message_paths=present,
        secondary_payload_paths_present=secondary,
        decoded_entry_count=decoded_count,
        accepted_entry_count=len(events),
        failed_entry_count=failed_count,
        full_result_hash=full_hash,
        adopted_semantics_hash=adopted_hash,
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _response_type(response_type_numeric: int) -> FeedResponseType:
    return {
        MarketDataFeed_pb2.initial_feed: FeedResponseType.INITIAL_FEED,
        MarketDataFeed_pb2.live_feed: FeedResponseType.LIVE_FEED,
        MarketDataFeed_pb2.market_info: FeedResponseType.MARKET_INFO,
    }[response_type_numeric]
