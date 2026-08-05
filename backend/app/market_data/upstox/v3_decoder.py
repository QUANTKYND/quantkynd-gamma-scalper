from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.message import DecodeError

from app.market_data.normalization.conversions import epoch_milliseconds
from app.market_data.normalization.errors import FrameDecodeError
from app.market_data.normalization.identities import RawMarketFrameV1
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.market_data.upstox.v3_schema import (
    UPSTOX_V3_MAX_FEEDS,
    UPSTOX_V3_MAX_STATUS_SEGMENTS,
    UPSTOX_V3_SCHEMA_ID,
    UPSTOX_V3_SCHEMA_SHA256,
)


@dataclass(frozen=True)
class DecodedUpstoxV3Frame:
    response: MarketDataFeed_pb2.FeedResponse
    response_type_numeric: int
    provider_contract_keys: tuple[str, ...]
    status_segments: tuple[str, ...]


def decode_upstox_v3_frame(frame: RawMarketFrameV1) -> DecodedUpstoxV3Frame:
    if frame.provider_schema_id != UPSTOX_V3_SCHEMA_ID or frame.provider_schema_sha256 != UPSTOX_V3_SCHEMA_SHA256:
        raise FrameDecodeError("protobuf_decode_failed")
    response = MarketDataFeed_pb2.FeedResponse()
    try:
        response.ParseFromString(frame.frame_bytes)
    except DecodeError as error:
        raise FrameDecodeError("protobuf_decode_failed") from error
    response_type = int(response.type)
    if response_type not in (
        MarketDataFeed_pb2.initial_feed,
        MarketDataFeed_pb2.live_feed,
        MarketDataFeed_pb2.market_info,
    ):
        raise FrameDecodeError("unsupported_response_type")
    if response.currentTs == 0:
        raise FrameDecodeError("missing_provider_timestamp")
    try:
        epoch_milliseconds(response.currentTs, zero_is_none=False)
    except ValueError as error:
        raise FrameDecodeError("invalid_provider_timestamp") from error
    if len(response.feeds) > UPSTOX_V3_MAX_FEEDS:
        raise FrameDecodeError("too_many_feeds")
    if len(response.marketInfo.segmentStatus) > UPSTOX_V3_MAX_STATUS_SEGMENTS:
        raise FrameDecodeError("too_many_status_segments")
    provider_keys = tuple(sorted(response.feeds.keys()))
    status_segments = tuple(sorted(response.marketInfo.segmentStatus.keys()))
    if response_type == MarketDataFeed_pb2.market_info and not status_segments:
        raise FrameDecodeError("empty_primary_payload")
    if response_type in (MarketDataFeed_pb2.initial_feed, MarketDataFeed_pb2.live_feed) and not provider_keys:
        raise FrameDecodeError("empty_primary_payload")
    return DecodedUpstoxV3Frame(response, response_type, provider_keys, status_segments)
