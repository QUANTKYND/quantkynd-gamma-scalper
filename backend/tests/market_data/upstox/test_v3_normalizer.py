from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest

from app.market_data.normalization.enums import FrameNormalizationStatus
from app.market_data.normalization.ports import StaticSubjectManifestResolver
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.services.market_frame_normalization_service import MarketFrameNormalizationService
from tests.market_data.normalization.helpers import AT, raw_frame, subjects


def normalize(response, *, source_order=1):
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(subjects()))
    return asyncio.run(
        service.normalize(raw_frame(response.SerializeToString(), source_order=source_order), market_as_of=AT, known_as_of=AT)
    )


def feed_response(response_type=MarketDataFeed_pb2.live_feed):
    return MarketDataFeed_pb2.FeedResponse(type=response_type, currentTs=1_754_365_200_123)


def ltpc(ltp=25000.5, ltt=1_754_365_200_000, ltq=4, cp=24950.0):
    return MarketDataFeed_pb2.LTPC(ltp=ltp, ltt=ltt, ltq=ltq, cp=cp)


def test_direct_ltpc_preserves_zero_and_proto_presence_semantics() -> None:
    response = feed_response()
    response.feeds["NSE_INDEX|Nifty 50"].requestMode = MarketDataFeed_pb2.ltpc
    response.feeds["NSE_INDEX|Nifty 50"].ltpc.CopyFrom(MarketDataFeed_pb2.LTPC())
    result = normalize(response)
    assert result.status is FrameNormalizationStatus.COMPLETE
    event = result.accepted_events[0]
    assert event.last_price == Decimal(0)
    assert event.last_size == 0
    assert event.previous_close_price == Decimal(0)
    assert event.last_trade_at is None
    assert event.bid_price is None
    assert event.is_snapshot is False
    assert event.provider_sequence is None


def test_initial_index_full_feed_uses_wire_snapshot_flag() -> None:
    response = feed_response(MarketDataFeed_pb2.initial_feed)
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.indexFF.ltpc.CopyFrom(ltpc())
    feed.fullFeed.indexFF.marketOHLC.ohlc.add(interval="1d", open=float("nan"))
    result = normalize(response)
    event = result.accepted_events[0]
    assert event.is_snapshot is True
    assert event.feed_union.value == "indexFF"
    assert event.last_size == 4
    assert "IndexFullFeed.marketOHLC" in event.present_unadopted_message_paths


def test_market_full_feed_adopts_best_depth_and_ignores_deeper_invalid_values() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|future"]
    feed.requestMode = MarketDataFeed_pb2.full_d30
    payload = feed.fullFeed.marketFF
    payload.ltpc.CopyFrom(ltpc())
    payload.marketLevel.bidAskQuote.add(bidQ=10, bidP=100.25, askQ=20, askP=100.5)
    payload.marketLevel.bidAskQuote.add(bidQ=-1, bidP=float("nan"), askQ=-1, askP=-1)
    payload.vtt = 300
    payload.oi = 500.0
    payload.iv = float("nan")
    result = normalize(response)
    event = result.accepted_events[0]
    assert event.bid_price == Decimal("100.25")
    assert event.ask_price == Decimal("100.5")
    assert event.reported_volume == 300
    assert event.open_interest == 500
    assert event.provider_depth_levels_present == 2
    assert event.normalized_depth_levels == 1
    assert event.unadopted_depth_level_count == 1


def test_first_level_with_greeks_adopts_quote_not_provider_analytics() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.option_greeks
    payload = feed.firstLevelWithGreeks
    payload.ltpc.CopyFrom(ltpc())
    payload.firstDepth.CopyFrom(MarketDataFeed_pb2.Quote(bidQ=2, bidP=20.0, askQ=3, askP=20.5))
    payload.optionGreeks.delta = float("nan")
    payload.iv = float("nan")
    payload.vtt = 12
    payload.oi = 30.0
    result = normalize(response)
    event = result.accepted_events[0]
    assert event.bid_size == 2
    assert event.ask_size == 3
    assert "FirstLevelWithGreeks.optionGreeks" in event.present_unadopted_message_paths
    assert not hasattr(event, "implied_volatility")


def test_unknown_subject_produces_deterministic_partial_result() -> None:
    response = feed_response()
    known = response.feeds["NSE_INDEX|Nifty 50"]
    known.requestMode = MarketDataFeed_pb2.ltpc
    known.ltpc.CopyFrom(ltpc())
    unknown = response.feeds["NSE_FO|unknown"]
    unknown.requestMode = MarketDataFeed_pb2.ltpc
    unknown.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.status is FrameNormalizationStatus.PARTIAL
    assert result.accepted_event_count == 1
    assert result.failed_entry_count == 1
    assert result.decoded_entry_count == 2
    assert result.failures[0].reason_code == "unknown_provider_key"


def test_kind_and_union_mismatch_fails_only_subject() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.indexFF.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.status is FrameNormalizationStatus.FAILED
    assert result.failures[0].reason_code == "subject_kind_mismatch"


def test_market_status_preserves_exact_known_and_unknown_values() -> None:
    response = feed_response(MarketDataFeed_pb2.market_info)
    response.marketInfo.segmentStatus["NSE_EQ"] = MarketDataFeed_pb2.NORMAL_OPEN
    response.marketInfo.segmentStatus["NSE_FO"] = 99
    result = normalize(response)
    assert [event.segment for event in result.accepted_events] == ["NSE_EQ", "NSE_FO"]
    assert result.accepted_events[0].provider_status_name == "NORMAL_OPEN"
    assert result.accepted_events[1].provider_status_name == "UNKNOWN"
    assert result.accepted_events[1].provider_status_numeric == 99
    assert result.accepted_events[1].status_is_known is False


def test_secondary_payload_is_declared_but_not_normalized() -> None:
    response = feed_response()
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    response.marketInfo.segmentStatus["NSE_EQ"] = MarketDataFeed_pb2.NORMAL_OPEN
    result = normalize(response)
    assert result.secondary_payload_paths_present == ("FeedResponse.marketInfo.segmentStatus",)
    assert len(result.accepted_events) == 1


def test_map_order_is_deterministic() -> None:
    first = feed_response()
    second = feed_response()
    for response, keys in (
        (first, ("NSE_FO|option", "NSE_INDEX|Nifty 50")),
        (second, ("NSE_INDEX|Nifty 50", "NSE_FO|option")),
    ):
        for key in keys:
            feed = response.feeds[key]
            feed.requestMode = MarketDataFeed_pb2.ltpc
            feed.ltpc.CopyFrom(ltpc())
    left = normalize(first, source_order=7)
    right = normalize(second, source_order=7)
    assert [event.event_id for event in left.accepted_events] == [event.event_id for event in right.accepted_events]
    assert left.adopted_semantics_hash == right.adopted_semantics_hash


def test_deferred_field_change_does_not_change_adopted_semantics_hash() -> None:
    first = feed_response()
    second = feed_response()
    for response, value in ((first, 0.2), (second, 0.8)):
        feed = response.feeds["NSE_FO|option"]
        feed.requestMode = MarketDataFeed_pb2.full_d5
        payload = feed.fullFeed.marketFF
        payload.ltpc.CopyFrom(ltpc())
        payload.iv = value
    left = normalize(first, source_order=8)
    right = normalize(second, source_order=9)
    assert left.frame_content_hash != right.frame_content_hash
    assert left.full_result_hash != right.full_result_hash
    assert left.adopted_semantics_hash == right.adopted_semantics_hash


@pytest.mark.parametrize(
    "response,reason",
    [
        (MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed), "missing_provider_timestamp"),
        (MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed, currentTs=1), "empty_primary_payload"),
    ],
)
def test_structural_frame_failures_are_explicit(response, reason) -> None:
    result = normalize(response)
    assert result.status is FrameNormalizationStatus.FAILED
    assert result.failures[0].reason_code == reason


def test_malformed_protobuf_is_whole_frame_failure() -> None:
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(subjects()))
    result = asyncio.run(service.normalize(raw_frame(b"\x80"), market_as_of=AT, known_as_of=AT))
    assert result.failures[0].reason_code == "protobuf_decode_failed"


@pytest.mark.parametrize(
    "price,reason",
    [(float("nan"), "nonfinite_price"), (float("inf"), "nonfinite_price"), (-1.0, "negative_price")],
)
def test_invalid_adopted_price_fails_subject(price, reason) -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|future"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    feed.fullFeed.marketFF.marketLevel.bidAskQuote.add(bidQ=1, bidP=price, askQ=1, askP=1.0)
    result = normalize(response)
    assert result.failures[0].reason_code == reason


@pytest.mark.parametrize(
    "open_interest,reason",
    [(1.5, "fractional_open_interest"), (float(2**53 + 2), "unsafe_open_interest")],
)
def test_invalid_open_interest_fails_subject(open_interest, reason) -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|future"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    feed.fullFeed.marketFF.oi = open_interest
    result = normalize(response)
    assert result.failures[0].reason_code == reason


def test_depth_limit_failure_does_not_validate_deeper_levels() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.full_d30
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for _ in range(31):
        feed.fullFeed.marketFF.marketLevel.bidAskQuote.add(bidQ=-1, bidP=float("nan"))
    result = normalize(response)
    assert result.failures[0].reason_code == "depth_limit_exceeded"


def test_unknown_wire_field_changes_full_provenance_only() -> None:
    response = feed_response()
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    base_bytes = response.SerializeToString()
    unknown_bytes = base_bytes + b"\x98\x06\x01"
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(subjects()))
    base = asyncio.run(service.normalize(raw_frame(base_bytes, source_order=20), market_as_of=AT, known_as_of=AT))
    unknown = asyncio.run(service.normalize(raw_frame(unknown_bytes, source_order=21), market_as_of=AT, known_as_of=AT))
    assert base.full_result_hash != unknown.full_result_hash
    assert base.adopted_semantics_hash == unknown.adopted_semantics_hash


def test_provider_timestamp_can_be_later_than_local_capture_clock() -> None:
    response = feed_response()
    response.currentTs = 1_900_000_000_000
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.accepted_events[0].event_time.provider_timestamp > result.accepted_events[0].event_time.recorded_at


def test_duplicate_normalized_identity_is_whole_result_failure() -> None:
    manifest = subjects()
    alias = replace(manifest[0], provider_contract_key="NSE_INDEX|alias", provider_mapping_id="mapping-alias")
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(manifest + (alias,)))
    response = feed_response()
    for key in ("NSE_INDEX|Nifty 50", "NSE_INDEX|alias"):
        feed = response.feeds[key]
        feed.requestMode = MarketDataFeed_pb2.ltpc
        feed.ltpc.CopyFrom(ltpc())
    result = asyncio.run(service.normalize(raw_frame(response.SerializeToString()), market_as_of=AT, known_as_of=AT))
    assert result.status is FrameNormalizationStatus.FAILED
    assert result.accepted_events == ()
    assert result.failures[0].reason_code == "duplicate_normalized_identity"


def test_invalid_provider_timestamp_is_whole_frame_failure() -> None:
    response = feed_response()
    response.currentTs = -1
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.failures[0].reason_code == "invalid_provider_timestamp"
