from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.instruments.identity import ProviderContractMapping
from app.market_data.normalization.enums import FrameNormalizationStatus, NormalizationFailureScope
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
    assert result.accepted_entry_count == 1
    assert result.failed_entry_count == 1
    assert result.decoded_entry_count == 2
    assert result.entry_failures[0].reason_code == "unknown_provider_key"
    assert result.entry_failures[0].scope is NormalizationFailureScope.SUBJECT


def test_kind_and_union_mismatch_fails_only_subject() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.indexFF.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.status is FrameNormalizationStatus.FAILED
    assert result.entry_failures[0].reason_code == "subject_kind_mismatch"


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
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == reason
    assert result.decoded_entry_count == 0


class _UncalledResolver:
    def __init__(self) -> None:
        self.call_count = 0

    async def resolve_many(self, provider, provider_contract_keys, market_as_of, known_as_of):
        self.call_count += 1
        raise AssertionError("resolver must not be called")


@pytest.mark.parametrize("key", ("", "   ", " leading", "trailing ", "line\nbreak", "nul\x00key", "k" * 513))
@pytest.mark.parametrize("response_type", (MarketDataFeed_pb2.live_feed, MarketDataFeed_pb2.initial_feed))
def test_invalid_primary_provider_contract_key_is_a_frame_failure(key, response_type) -> None:
    response = feed_response(response_type)
    response.feeds[key].requestMode = MarketDataFeed_pb2.ltpc
    response.feeds[key].ltpc.CopyFrom(ltpc())
    resolver = _UncalledResolver()
    result = asyncio.run(
        MarketFrameNormalizationService(resolver).normalize(
            raw_frame(response.SerializeToString()), market_as_of=AT, known_as_of=AT
        )
    )
    assert resolver.call_count == 0
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "invalid_provider_contract_key"
    assert result.response_type.value == ("live_feed" if response_type == MarketDataFeed_pb2.live_feed else "initial_feed")
    assert (result.decoded_entry_count, result.accepted_entry_count, result.failed_entry_count) == (0, 0, 0)


def test_provider_contract_key_utf8_byte_boundary_and_mixed_failure() -> None:
    accepted_response = feed_response()
    accepted_response.feeds["k" * 512].requestMode = MarketDataFeed_pb2.ltpc
    accepted_response.feeds["k" * 512].ltpc.CopyFrom(ltpc())
    accepted = normalize(accepted_response)
    assert accepted.frame_failure is None
    assert accepted.failed_entry_count == 1
    multibyte = feed_response()
    multibyte.feeds["é" * 257].requestMode = MarketDataFeed_pb2.ltpc
    multibyte.feeds["é" * 257].ltpc.CopyFrom(ltpc())
    assert normalize(multibyte).frame_failure.reason_code == "invalid_provider_contract_key"
    mixed = feed_response()
    for key in ("NSE_INDEX|Nifty 50", " bad"):
        mixed.feeds[key].requestMode = MarketDataFeed_pb2.ltpc
        mixed.feeds[key].ltpc.CopyFrom(ltpc())
    result = normalize(mixed)
    assert result.frame_failure.reason_code == "invalid_provider_contract_key"
    assert result.accepted_events == ()


@pytest.mark.parametrize("segment", ("", "   ", " leading", "trailing ", "line\nbreak", "nul\x00segment", "s" * 129))
def test_invalid_primary_market_segment_is_a_frame_failure(segment) -> None:
    response = feed_response(MarketDataFeed_pb2.market_info)
    response.marketInfo.segmentStatus[segment] = MarketDataFeed_pb2.NORMAL_OPEN
    result = normalize(response)
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "invalid_market_segment"
    assert result.response_type.value == "market_info"
    assert (result.decoded_entry_count, result.accepted_entry_count, result.failed_entry_count) == (0, 0, 0)


def test_market_segment_utf8_byte_boundary_and_mixed_failure() -> None:
    accepted_response = feed_response(MarketDataFeed_pb2.market_info)
    accepted_response.marketInfo.segmentStatus["s" * 128] = MarketDataFeed_pb2.NORMAL_OPEN
    accepted = normalize(accepted_response)
    assert accepted.frame_failure is None
    assert accepted.accepted_entry_count == 1
    multibyte = feed_response(MarketDataFeed_pb2.market_info)
    multibyte.marketInfo.segmentStatus["é" * 65] = MarketDataFeed_pb2.NORMAL_OPEN
    assert normalize(multibyte).frame_failure.reason_code == "invalid_market_segment"
    mixed = feed_response(MarketDataFeed_pb2.market_info)
    mixed.marketInfo.segmentStatus["NSE_FO"] = MarketDataFeed_pb2.NORMAL_OPEN
    mixed.marketInfo.segmentStatus["bad "] = MarketDataFeed_pb2.NORMAL_OPEN
    result = normalize(mixed)
    assert result.frame_failure.reason_code == "invalid_market_segment"
    assert result.accepted_events == ()


def test_only_selected_primary_payload_identities_are_validated() -> None:
    market_info = feed_response(MarketDataFeed_pb2.market_info)
    market_info.marketInfo.segmentStatus["NSE_FO"] = MarketDataFeed_pb2.NORMAL_OPEN
    market_info.feeds[" bad"].requestMode = MarketDataFeed_pb2.ltpc
    market_info.feeds[" bad"].ltpc.CopyFrom(ltpc())
    market_result = normalize(market_info)
    assert market_result.frame_failure is None
    assert market_result.secondary_payload_paths_present == ("FeedResponse.feeds",)
    quote = feed_response()
    quote.feeds["NSE_INDEX|Nifty 50"].requestMode = MarketDataFeed_pb2.ltpc
    quote.feeds["NSE_INDEX|Nifty 50"].ltpc.CopyFrom(ltpc())
    quote.marketInfo.segmentStatus[" bad"] = MarketDataFeed_pb2.NORMAL_OPEN
    quote_result = normalize(quote)
    assert quote_result.frame_failure is None
    assert quote_result.secondary_payload_paths_present == ("FeedResponse.marketInfo.segmentStatus",)


def test_malformed_protobuf_is_whole_frame_failure() -> None:
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(subjects()))
    result = asyncio.run(service.normalize(raw_frame(b"\x80"), market_as_of=AT, known_as_of=AT))
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "protobuf_decode_failed"
    assert result.decoded_entry_count == 0


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
    assert result.entry_failures[0].reason_code == reason


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
    assert result.entry_failures[0].reason_code == reason


def test_depth_limit_failure_does_not_validate_deeper_levels() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.full_d30
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for _ in range(31):
        feed.fullFeed.marketFF.marketLevel.bidAskQuote.add(bidQ=-1, bidP=float("nan"))
    result = normalize(response)
    assert result.entry_failures[0].reason_code == "depth_limit_exceeded"


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


def test_failed_subject_deferred_presence_changes_full_hash_only() -> None:
    first = feed_response()
    second = feed_response()
    for response in (first, second):
        feed = response.feeds["NSE_FO|unknown"]
        feed.requestMode = MarketDataFeed_pb2.full_d5
        feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    second.feeds["NSE_FO|unknown"].fullFeed.marketFF.optionGreeks.delta = 0.5
    left = normalize(first, source_order=40)
    right = normalize(second, source_order=41)
    assert left.full_result_hash != right.full_result_hash
    assert left.adopted_semantics_hash == right.adopted_semantics_hash
    assert left.entry_failures[0].present_unadopted_message_paths == ()
    assert right.entry_failures[0].present_unadopted_message_paths == ("MarketFullFeed.optionGreeks",)


def test_resolver_cutoff_mismatch_is_a_whole_frame_failure() -> None:
    response = feed_response()
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    stale_subject = replace(subjects()[0], resolution_known_as_of=AT + timedelta(seconds=1))

    class IncorrectResolver:
        async def resolve_many(self, provider, provider_contract_keys, market_as_of, known_as_of):
            from app.market_data.normalization.ports import SubjectResolutionBatch

            return SubjectResolutionBatch((stale_subject,), ())

    service = MarketFrameNormalizationService(IncorrectResolver())
    result = asyncio.run(service.normalize(raw_frame(response.SerializeToString()), market_as_of=AT, known_as_of=AT))
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "invalid_subject_resolution_batch"
    assert result.accepted_events == ()


def test_failed_subject_preserves_union_scoped_structural_metadata() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|unknown"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for _ in range(3):
        feed.fullFeed.marketFF.marketLevel.bidAskQuote.add()
    feed.fullFeed.marketFF.optionGreeks.delta = float("nan")
    result = normalize(response)
    failure = result.entry_failures[0]
    assert failure.selected_feed_union.value == "marketFF"
    assert failure.provider_depth_levels_present == 3
    assert "MarketFullFeed.iv" in failure.unadopted_schema_paths
    assert failure.present_unadopted_message_paths == ("MarketFullFeed.optionGreeks",)
    assert result.unadopted_schema_paths == failure.unadopted_schema_paths


def test_unadopted_declarations_are_scoped_to_selected_unions() -> None:
    response = feed_response()
    direct = response.feeds["NSE_INDEX|Nifty 50"]
    direct.requestMode = MarketDataFeed_pb2.ltpc
    direct.ltpc.CopyFrom(ltpc())
    assert normalize(response).unadopted_schema_paths == ()

    response = feed_response()
    index = response.feeds["NSE_INDEX|Nifty 50"]
    index.requestMode = MarketDataFeed_pb2.full_d5
    index.fullFeed.indexFF.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert "IndexFullFeed.marketOHLC.ohlc" in result.unadopted_schema_paths
    assert "MarketFullFeed.iv" not in result.unadopted_schema_paths


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
    alias_mapping = ProviderContractMapping(
        provider="upstox",
        provider_contract_key="NSE_INDEX|alias",
        contract_version_id=manifest[0].contract_version_id,
        provider_payload_hash="sha256:" + "b" * 64,
        source_row_identity="row-alias",
        effective_from=AT,
        effective_until=None,
        recorded_at=AT,
    )
    alias = replace(
        manifest[0],
        provider_contract_key="NSE_INDEX|alias",
        provider_mapping_id=alias_mapping.mapping_id,
        provider_mapping=alias_mapping,
    )
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(manifest + (alias,)))
    response = feed_response()
    for key in ("NSE_INDEX|Nifty 50", "NSE_INDEX|alias"):
        feed = response.feeds[key]
        feed.requestMode = MarketDataFeed_pb2.ltpc
        feed.ltpc.CopyFrom(ltpc())
    result = asyncio.run(service.normalize(raw_frame(response.SerializeToString()), market_as_of=AT, known_as_of=AT))
    assert result.status is FrameNormalizationStatus.FAILED
    assert result.accepted_events == ()
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "duplicate_normalized_identity"
    assert result.decoded_entry_count == 2
    assert result.accepted_entry_count == 0
    assert result.failed_entry_count == 0


def test_invalid_provider_timestamp_is_whole_frame_failure() -> None:
    response = feed_response()
    response.currentTs = -1
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    result = normalize(response)
    assert result.frame_failure is not None
    assert result.frame_failure.reason_code == "invalid_provider_timestamp"


@pytest.mark.parametrize("depth_count", [0, 1, 5])
def test_full_d5_accepts_up_to_five_depth_levels(depth_count) -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|future"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for index in range(depth_count):
        feed.fullFeed.marketFF.marketLevel.bidAskQuote.add(
            bidQ=1 if index == 0 else -1,
            bidP=1.0 if index == 0 else float("nan"),
            askQ=1 if index == 0 else -1,
            askP=2.0 if index == 0 else float("nan"),
        )
    result = normalize(response)
    assert result.frame_failure is None
    assert result.failed_entry_count == 0
    assert result.accepted_events[0].provider_depth_levels_present == depth_count


def test_full_d5_rejects_six_depth_levels() -> None:
    response = feed_response()
    feed = response.feeds["NSE_FO|future"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for _ in range(6):
        feed.fullFeed.marketFF.marketLevel.bidAskQuote.add()
    result = normalize(response)
    assert result.entry_failures[0].reason_code == "request_mode_depth_mismatch"


def test_full_d30_accepts_thirty_and_rejects_thirty_one_levels() -> None:
    accepted = feed_response()
    accepted_feed = accepted.feeds["NSE_FO|future"]
    accepted_feed.requestMode = MarketDataFeed_pb2.full_d30
    accepted_feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for _ in range(30):
        accepted_feed.fullFeed.marketFF.marketLevel.bidAskQuote.add()
    assert normalize(accepted).failed_entry_count == 0
    rejected = feed_response()
    rejected_feed = rejected.feeds["NSE_FO|future"]
    rejected_feed.requestMode = MarketDataFeed_pb2.full_d30
    rejected_feed.fullFeed.marketFF.ltpc.CopyFrom(ltpc())
    for _ in range(31):
        rejected_feed.fullFeed.marketFF.marketLevel.bidAskQuote.add()
    assert normalize(rejected).entry_failures[0].reason_code == "depth_limit_exceeded"
