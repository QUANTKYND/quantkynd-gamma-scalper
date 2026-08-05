from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.market_data.normalization.conversions import (
    epoch_milliseconds,
    provider_double_to_price,
    reported_open_interest,
    reported_quantity,
)
from app.market_data.normalization.enums import (
    FeedResponseType,
    MarketSubjectKind,
    NormalizationFailureScope,
    NormalizedAvailabilityBasis,
    ProviderFeedUnion,
    ProviderRequestMode,
    RawCaptureBasis,
)
from app.market_data.normalization.identities import RawMarketFrameV1
from app.market_data.normalization.models import (
    NORMALIZATION_SCHEMA_VERSION,
    NORMALIZER_IMPLEMENTATION_VERSION,
    NUMERIC_BASIS,
    PRESENCE_SEMANTICS,
    PROVIDER_MARKET_STATUS_NAMES,
    QUANTITY_BASIS,
    FuturesQuoteObservationV1,
    NormalizedMarketEventTimeV1,
    OptionQuoteObservationV1,
    ProviderMarketSegmentStatusObservationV1,
    QuoteObservationV1,
    ResolvedMarketSubjectV1,
    UnderlyingQuoteObservationV1,
    market_segment_status_subject_id,
)
from app.market_data.normalization.ports import SubjectResolutionBatch
from app.market_data.normalization.results import (
    FrameNormalizationDraftV1,
    NormalizationFailureV1,
    failed_entry_scope_count,
)
from app.market_data.point_in_time import NormalizedMarketEventIdentity
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.market_data.upstox.v3_decoder import DecodedUpstoxV3Frame
from app.market_data.upstox.v3_schema import UNADOPTED_SCHEMA_PATHS, UPSTOX_V3_MAX_DEPTH_LEVELS


RESPONSE_TYPES = {
    MarketDataFeed_pb2.initial_feed: FeedResponseType.INITIAL_FEED,
    MarketDataFeed_pb2.live_feed: FeedResponseType.LIVE_FEED,
    MarketDataFeed_pb2.market_info: FeedResponseType.MARKET_INFO,
}
REQUEST_MODES = {
    MarketDataFeed_pb2.ltpc: ProviderRequestMode.LTPC,
    MarketDataFeed_pb2.full_d5: ProviderRequestMode.FULL_D5,
    MarketDataFeed_pb2.option_greeks: ProviderRequestMode.OPTION_GREEKS,
    MarketDataFeed_pb2.full_d30: ProviderRequestMode.FULL_D30,
}
@dataclass(frozen=True)
class _AdoptedQuoteFields:
    feed_union: ProviderFeedUnion
    bid_price: Decimal | None
    bid_size: int | None
    ask_price: Decimal | None
    ask_size: int | None
    last_price: Decimal
    last_size: int
    last_trade_at: object
    previous_close_price: Decimal
    reported_volume: int | None
    open_interest: int | None
    provider_depth_levels_present: int
    normalized_depth_levels: int
    present_unadopted_message_paths: tuple[str, ...]


def normalize_upstox_v3_frame(
    decoded: DecodedUpstoxV3Frame,
    frame: RawMarketFrameV1,
    subjects: SubjectResolutionBatch | None,
) -> FrameNormalizationDraftV1:
    response_type = RESPONSE_TYPES[decoded.response_type_numeric]
    secondary_paths = _secondary_payload_paths(decoded)
    if response_type is FeedResponseType.MARKET_INFO:
        events, failures = _normalize_statuses(decoded, frame)
    else:
        if subjects is None:
            raise ValueError("quote normalization requires subject resolutions")
        events, failures = _normalize_quotes(decoded, frame, subjects, response_type, secondary_paths)
    present_paths = tuple(
        sorted(
            {
                path
                for event in events
                if isinstance(event, QuoteObservationV1)
                for path in event.present_unadopted_message_paths
            }
        )
    )
    ordered_events = tuple(sorted(events, key=_event_order_key))
    ordered_failures = tuple(
        sorted(failures, key=lambda item: (item.provider_contract_key or "", item.segment or "", item.reason_code))
    )
    return FrameNormalizationDraftV1(
        accepted_events=ordered_events,
        entry_failures=ordered_failures,
        unadopted_schema_paths=UNADOPTED_SCHEMA_PATHS,
        present_unadopted_message_paths=present_paths,
        secondary_payload_paths_present=secondary_paths,
        decoded_entry_count=len(ordered_events) + failed_entry_scope_count(ordered_failures),
    )


def _normalize_statuses(decoded: DecodedUpstoxV3Frame, frame: RawMarketFrameV1):
    provider_timestamp = epoch_milliseconds(decoded.response.currentTs, zero_is_none=False)
    events: list[ProviderMarketSegmentStatusObservationV1] = []
    for segment in decoded.status_segments:
        numeric = int(decoded.response.marketInfo.segmentStatus[segment])
        name = PROVIDER_MARKET_STATUS_NAMES.get(numeric, "UNKNOWN")
        subject_id = market_segment_status_subject_id(frame.provider, segment)
        identity = NormalizedMarketEventIdentity(
            raw_event_id=frame.raw_event_id,
            event_type="market_segment_status_observation",
            subject_id=subject_id,
            normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        )
        events.append(
            ProviderMarketSegmentStatusObservationV1(
                identity=identity,
                raw_event_id=frame.raw_event_id,
                provider=frame.provider,
                segment=segment,
                provider_status_name=name,
                provider_status_numeric=numeric,
                status_is_known=numeric in PROVIDER_MARKET_STATUS_NAMES,
                provider_timestamp=provider_timestamp,
                received_at=frame.received_at,
                available_at=frame.available_at,
                recorded_at=frame.recorded_at,
                source_order_scope_id=frame.source_order_scope_id,
                source_order=frame.source_order,
                normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
                normalizer_implementation_version=NORMALIZER_IMPLEMENTATION_VERSION,
            )
        )
    return events, []


def _normalize_quotes(
    decoded: DecodedUpstoxV3Frame,
    frame: RawMarketFrameV1,
    subjects: SubjectResolutionBatch,
    response_type: FeedResponseType,
    secondary_paths: tuple[str, ...],
):
    events: list[QuoteObservationV1] = []
    failures: list[NormalizationFailureV1] = []
    for key in decoded.provider_contract_keys:
        resolution_failure = subjects.failure_for(key)
        if resolution_failure is not None:
            failures.append(
                NormalizationFailureV1(
                    scope=NormalizationFailureScope.SUBJECT,
                    reason_code=resolution_failure.reason_code,
                    provider_contract_key=key,
                )
            )
            continue
        subject = subjects.subject_for(key)
        if subject is None:
            failures.append(
                NormalizationFailureV1(
                    scope=NormalizationFailureScope.SUBJECT,
                    reason_code="unknown_provider_key",
                    provider_contract_key=key,
                )
            )
            continue
        try:
            event = _normalize_quote(
                decoded.response.feeds[key],
                frame,
                subject,
                response_type,
                epoch_milliseconds(decoded.response.currentTs, zero_is_none=False),
                secondary_paths,
            )
        except ValueError as error:
            reason = str(error)
            if reason not in {
                "subject_kind_mismatch",
                "request_mode_union_mismatch",
                "unsupported_feed_union",
                "empty_supported_payload",
                "invalid_timestamp",
                "nonfinite_price",
                "negative_price",
                "invalid_quantity",
                "fractional_open_interest",
                "unsafe_open_interest",
                "depth_limit_exceeded",
                "request_mode_depth_mismatch",
            }:
                raise
            failures.append(
                NormalizationFailureV1(
                    scope=NormalizationFailureScope.SUBJECT,
                    reason_code=reason,
                    provider_contract_key=key,
                )
            )
        else:
            events.append(event)
    return events, failures


def _normalize_quote(feed, frame, subject, response_type, provider_timestamp, secondary_paths):
    request_mode = REQUEST_MODES.get(int(feed.requestMode))
    if request_mode is None:
        raise ValueError("request_mode_union_mismatch")
    union = feed.WhichOneof("FeedUnion")
    adopted = _adopt_fields(feed, union, request_mode, subject.instrument_kind)
    event_type, event_class = {
        MarketSubjectKind.UNDERLYING: ("underlying_quote_observation", UnderlyingQuoteObservationV1),
        MarketSubjectKind.FUTURE: ("futures_quote_observation", FuturesQuoteObservationV1),
        MarketSubjectKind.OPTION: ("option_quote_observation", OptionQuoteObservationV1),
    }[subject.instrument_kind]
    identity = NormalizedMarketEventIdentity(
        raw_event_id=frame.raw_event_id,
        event_type=event_type,
        subject_id=subject.economic_subject_id,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
    )
    event_time = NormalizedMarketEventTimeV1(
        provider_timestamp=provider_timestamp,
        exchange_timestamp=None,
        received_at=frame.received_at,
        available_at=frame.available_at,
        recorded_at=frame.recorded_at,
        availability_basis=(
            NormalizedAvailabilityBasis.HISTORICAL_IMPORT
            if frame.capture_basis is RawCaptureBasis.HISTORICAL_IMPORT
            else NormalizedAvailabilityBasis.RECEIVED
        ),
    )
    return event_class(
        identity=identity,
        raw_event_id=frame.raw_event_id,
        provider=frame.provider,
        provider_contract_key=subject.provider_contract_key,
        provider_mapping_id=subject.provider_mapping_id,
        contract_version_id=subject.contract_version_id,
        economic_subject_id=subject.economic_subject_id,
        subject=subject,
        event_time=event_time,
        source_order_scope_id=frame.source_order_scope_id,
        source_order=frame.source_order,
        feed_response_type=response_type,
        request_mode=request_mode,
        feed_union=adopted.feed_union,
        is_snapshot=response_type is FeedResponseType.INITIAL_FEED,
        presence_semantics=PRESENCE_SEMANTICS,
        numeric_basis=NUMERIC_BASIS,
        quantity_basis=QUANTITY_BASIS,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        normalizer_implementation_version=NORMALIZER_IMPLEMENTATION_VERSION,
        provider_sequence=None,
        supersedes_event_id=None,
        bid_price=adopted.bid_price,
        bid_size=adopted.bid_size,
        ask_price=adopted.ask_price,
        ask_size=adopted.ask_size,
        last_price=adopted.last_price,
        last_size=adopted.last_size,
        last_trade_at=adopted.last_trade_at,
        previous_close_price=adopted.previous_close_price,
        reported_volume=adopted.reported_volume,
        open_interest=adopted.open_interest,
        provider_depth_levels_present=adopted.provider_depth_levels_present,
        normalized_depth_levels=adopted.normalized_depth_levels,
        unadopted_depth_level_count=adopted.provider_depth_levels_present - adopted.normalized_depth_levels,
        unadopted_schema_paths=UNADOPTED_SCHEMA_PATHS,
        present_unadopted_message_paths=adopted.present_unadopted_message_paths,
        secondary_payload_paths_present=secondary_paths,
    )


def _adopt_fields(feed, union, request_mode, kind):
    if union == "ltpc":
        if request_mode is not ProviderRequestMode.LTPC:
            raise ValueError("request_mode_union_mismatch")
        return _fields_from_ltpc(feed.ltpc, ProviderFeedUnion.LTPC)
    if union == "firstLevelWithGreeks":
        if request_mode is not ProviderRequestMode.OPTION_GREEKS:
            raise ValueError("request_mode_union_mismatch")
        if kind is not MarketSubjectKind.OPTION:
            raise ValueError("subject_kind_mismatch")
        payload = feed.firstLevelWithGreeks
        if not payload.HasField("ltpc"):
            raise ValueError("empty_supported_payload")
        depth = payload.HasField("firstDepth")
        bid_price = provider_double_to_price(payload.firstDepth.bidP) if depth else None
        bid_size = reported_quantity(payload.firstDepth.bidQ) if depth else None
        ask_price = provider_double_to_price(payload.firstDepth.askP) if depth else None
        ask_size = reported_quantity(payload.firstDepth.askQ) if depth else None
        present = ("FirstLevelWithGreeks.optionGreeks",) if payload.HasField("optionGreeks") else ()
        return _fields_from_ltpc(
            payload.ltpc,
            ProviderFeedUnion.FIRST_LEVEL_WITH_GREEKS,
            bid_price=bid_price,
            bid_size=bid_size,
            ask_price=ask_price,
            ask_size=ask_size,
            reported_volume=reported_quantity(payload.vtt),
            open_interest=reported_open_interest(payload.oi),
            depth_count=1 if depth else 0,
            present_paths=present,
        )
    if union != "fullFeed":
        raise ValueError("unsupported_feed_union")
    if request_mode not in (ProviderRequestMode.FULL_D5, ProviderRequestMode.FULL_D30):
        raise ValueError("request_mode_union_mismatch")
    full_union = feed.fullFeed.WhichOneof("FullFeedUnion")
    if full_union == "indexFF":
        if kind is not MarketSubjectKind.UNDERLYING:
            raise ValueError("subject_kind_mismatch")
        payload = feed.fullFeed.indexFF
        if not payload.HasField("ltpc"):
            raise ValueError("empty_supported_payload")
        present = ("IndexFullFeed.marketOHLC",) if payload.HasField("marketOHLC") else ()
        return _fields_from_ltpc(payload.ltpc, ProviderFeedUnion.INDEX_FULL_FEED, present_paths=present)
    if full_union == "marketFF":
        if kind not in (MarketSubjectKind.FUTURE, MarketSubjectKind.OPTION):
            raise ValueError("subject_kind_mismatch")
        payload = feed.fullFeed.marketFF
        if not payload.HasField("ltpc"):
            raise ValueError("empty_supported_payload")
        depth_count = len(payload.marketLevel.bidAskQuote) if payload.HasField("marketLevel") else 0
        if depth_count > UPSTOX_V3_MAX_DEPTH_LEVELS:
            raise ValueError("depth_limit_exceeded")
        if request_mode is ProviderRequestMode.FULL_D5 and depth_count > 5:
            raise ValueError("request_mode_depth_mismatch")
        first = payload.marketLevel.bidAskQuote[0] if depth_count else None
        present: list[str] = []
        if payload.HasField("optionGreeks"):
            present.append("MarketFullFeed.optionGreeks")
        if payload.HasField("marketOHLC"):
            present.append("MarketFullFeed.marketOHLC")
        return _fields_from_ltpc(
            payload.ltpc,
            ProviderFeedUnion.MARKET_FULL_FEED,
            bid_price=provider_double_to_price(first.bidP) if first is not None else None,
            bid_size=reported_quantity(first.bidQ) if first is not None else None,
            ask_price=provider_double_to_price(first.askP) if first is not None else None,
            ask_size=reported_quantity(first.askQ) if first is not None else None,
            reported_volume=reported_quantity(payload.vtt),
            open_interest=reported_open_interest(payload.oi),
            depth_count=depth_count,
            present_paths=tuple(sorted(present)),
        )
    raise ValueError("unsupported_feed_union")


def _fields_from_ltpc(
    ltpc,
    feed_union,
    *,
    bid_price=None,
    bid_size=None,
    ask_price=None,
    ask_size=None,
    reported_volume=None,
    open_interest=None,
    depth_count=0,
    present_paths=(),
):
    return _AdoptedQuoteFields(
        feed_union=feed_union,
        bid_price=bid_price,
        bid_size=bid_size,
        ask_price=ask_price,
        ask_size=ask_size,
        last_price=provider_double_to_price(ltpc.ltp),
        last_size=reported_quantity(ltpc.ltq),
        last_trade_at=epoch_milliseconds(ltpc.ltt, zero_is_none=True),
        previous_close_price=provider_double_to_price(ltpc.cp),
        reported_volume=reported_volume,
        open_interest=open_interest,
        provider_depth_levels_present=depth_count,
        normalized_depth_levels=1 if depth_count else 0,
        present_unadopted_message_paths=tuple(sorted(set(present_paths))),
    )


def _secondary_payload_paths(decoded: DecodedUpstoxV3Frame) -> tuple[str, ...]:
    paths: list[str] = []
    if decoded.response_type_numeric == MarketDataFeed_pb2.market_info and decoded.response.feeds:
        paths.append("FeedResponse.feeds")
    if decoded.response_type_numeric in (MarketDataFeed_pb2.initial_feed, MarketDataFeed_pb2.live_feed):
        if decoded.response.marketInfo.segmentStatus:
            paths.append("FeedResponse.marketInfo.segmentStatus")
    return tuple(paths)


def _event_order_key(event):
    ranks = {
        "market_segment_status_observation": 3,
        "underlying_quote_observation": 4,
        "futures_quote_observation": 5,
        "option_quote_observation": 6,
    }
    provider_key = getattr(event, "provider_contract_key", getattr(event, "segment", ""))
    subject_id = getattr(event, "economic_subject_id", event.identity.subject_id)
    return ranks[event.identity.event_type], provider_key, subject_id, event.event_id
