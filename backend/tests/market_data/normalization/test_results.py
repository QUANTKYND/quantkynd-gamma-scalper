import asyncio
from dataclasses import replace

import pytest

from app.market_data.normalization.enums import NormalizationFailureScope
from app.market_data.normalization.ports import StaticSubjectManifestResolver
from app.instruments.identity import ProviderContractMapping
from app.market_data.normalization.results import NormalizationFailureV1
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.services.market_frame_normalization_service import MarketFrameNormalizationService
from tests.market_data.normalization.helpers import AT, raw_frame, subjects
from tests.market_data.upstox.test_v3_normalizer import feed_response, ltpc, normalize


def test_failure_scope_and_paths_are_explicit() -> None:
    frame = NormalizationFailureV1(
        scope=NormalizationFailureScope.FRAME,
        reason_code="protobuf_decode_failed",
        field_paths=("FeedResponse",),
        safe_detail_code="decode_error",
    )
    assert frame.provider_contract_key is None
    subject = NormalizationFailureV1(
        scope=NormalizationFailureScope.SUBJECT,
        reason_code="negative_price",
        provider_contract_key="NSE_FO|option",
        field_paths=("Quote.bidP",),
    )
    assert subject.scope is NormalizationFailureScope.SUBJECT
    with pytest.raises(ValueError, match="sorted and unique"):
        NormalizationFailureV1(
            scope=NormalizationFailureScope.FRAME,
            reason_code="failed",
            field_paths=("z", "a"),
        )
    with pytest.raises(ValueError, match="requires only"):
        NormalizationFailureV1(
            scope=NormalizationFailureScope.SUBJECT,
            reason_code="failed",
        )


def test_structural_failures_decode_zero_entries() -> None:
    malformed_service = MarketFrameNormalizationService(StaticSubjectManifestResolver(subjects()))
    malformed = asyncio.run(malformed_service.normalize(raw_frame(b"\x80"), market_as_of=AT, known_as_of=AT))
    assert malformed.decoded_entry_count == 0
    assert malformed.accepted_entry_count == 0
    assert malformed.failed_entry_count == 0
    assert malformed.frame_failure is not None
    for response in (
        MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed),
        MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed, currentTs=1),
    ):
        result = normalize(response)
        assert result.decoded_entry_count == 0
        assert result.frame_failure is not None


def test_too_many_feeds_is_frame_failure_before_entry_decode() -> None:
    response = feed_response()
    for index in range(5001):
        feed = response.feeds[f"key-{index:04d}"]
        feed.requestMode = MarketDataFeed_pb2.ltpc
        feed.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.decoded_entry_count == 0
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "too_many_feeds"


def test_partial_two_feed_result_reconciles_entries() -> None:
    response = feed_response()
    for key in ("NSE_INDEX|Nifty 50", "unknown"):
        feed = response.feeds[key]
        feed.requestMode = MarketDataFeed_pb2.ltpc
        feed.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.frame_failure is None
    assert result.decoded_entry_count == 2
    assert result.accepted_entry_count == 1
    assert result.failed_entry_count == 1
    second_diagnostic = replace(
        result.entry_failures[0],
        reason_code="missing_sequence",
    )
    multi_diagnostic = replace(
        result,
        entry_failures=(result.entry_failures[0], second_diagnostic),
    )
    assert multi_diagnostic.failed_entry_count == 1
    assert len(multi_diagnostic.entry_failures) == 2


def test_market_info_result_reconciles_segments_and_structural_failure() -> None:
    response = feed_response(MarketDataFeed_pb2.market_info)
    response.marketInfo.segmentStatus["NSE_EQ"] = MarketDataFeed_pb2.NORMAL_OPEN
    response.marketInfo.segmentStatus["NSE_FO"] = MarketDataFeed_pb2.NORMAL_CLOSE
    complete = normalize(response)
    assert complete.frame_failure is None
    assert complete.decoded_entry_count == 2
    assert complete.accepted_entry_count == 2
    assert complete.failed_entry_count == 0
    empty = normalize(feed_response(MarketDataFeed_pb2.market_info))
    assert empty.decoded_entry_count == 0
    assert empty.frame_failure is not None
    assert empty.frame_failure.reason_code == "empty_primary_payload"


def test_status_segment_limit_boundary() -> None:
    accepted = feed_response(MarketDataFeed_pb2.market_info)
    for index in range(256):
        accepted.marketInfo.segmentStatus[f"segment-{index:03d}"] = MarketDataFeed_pb2.NORMAL_OPEN
    accepted_result = normalize(accepted)
    assert accepted_result.decoded_entry_count == 256
    rejected = feed_response(MarketDataFeed_pb2.market_info)
    for index in range(257):
        rejected.marketInfo.segmentStatus[f"segment-{index:03d}"] = MarketDataFeed_pb2.NORMAL_OPEN
    rejected_result = normalize(rejected)
    assert rejected_result.decoded_entry_count == 0
    assert rejected_result.frame_failure is not None
    assert rejected_result.frame_failure.reason_code == "too_many_status_segments"


def test_duplicate_identity_failure_preserves_present_structural_metadata() -> None:
    option = subjects()[2]
    second_mapping = ProviderContractMapping(
        provider=option.provider,
        provider_contract_key="NSE_FO|option-alias",
        contract_version_id=option.contract_version_id,
        provider_payload_hash="sha256:" + "b" * 64,
        source_row_identity="row-option-alias",
        effective_from=option.provider_mapping.effective_from,
        effective_until=None,
        recorded_at=option.provider_mapping.recorded_at,
    )
    alias = replace(
        option,
        provider_contract_key=second_mapping.provider_contract_key,
        provider_mapping=second_mapping,
        provider_mapping_id=second_mapping.mapping_id,
    )
    response = feed_response()
    for key in (option.provider_contract_key, alias.provider_contract_key):
        feed = response.feeds[key]
        feed.requestMode = MarketDataFeed_pb2.full_d5
        feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    response.feeds[alias.provider_contract_key].fullFeed.marketFF.optionGreeks.delta = 0.5
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver((option, alias)))
    result = asyncio.run(service.normalize(raw_frame(response.SerializeToString()), market_as_of=AT, known_as_of=AT))
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "duplicate_normalized_identity"
    assert result.present_unadopted_message_paths == ("MarketFullFeed.optionGreeks",)
