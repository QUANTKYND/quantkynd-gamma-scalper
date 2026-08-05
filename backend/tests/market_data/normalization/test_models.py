from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta

import pytest

from app.instruments.identity import ProviderContractMapping
from app.market_data.normalization.enums import (
    FeedResponseType,
    MarketSubjectKind,
    NormalizedAvailabilityBasis,
    ProviderFeedUnion,
    ProviderRequestMode,
)
from app.market_data.normalization.models import (
    FuturesQuoteObservationV1,
    NormalizedMarketEventTimeV1,
)
from app.market_data.upstox.proto import MarketDataFeed_pb2
from tests.market_data.normalization.helpers import AT, subjects
from tests.market_data.upstox.test_v3_normalizer import feed_response, ltpc, normalize


def _mapping(base, **changes):
    values = {
        "provider": base.provider,
        "provider_contract_key": base.provider_contract_key,
        "contract_version_id": base.contract_version_id,
        "provider_payload_hash": base.provider_payload_hash,
        "source_row_identity": base.source_row_identity,
        "effective_from": base.effective_from,
        "effective_until": base.effective_until,
        "recorded_at": base.recorded_at,
        "superseded_at": base.superseded_at,
    }
    values.update(changes)
    return ProviderContractMapping(**values)


def test_resolved_subject_rejects_wrong_mapping_identity_provider_key_and_version() -> None:
    subject = subjects()[0]
    with pytest.raises(ValueError, match="mapping identity"):
        replace(subject, provider_mapping_id="wrong")
    wrong_provider = _mapping(subject.provider_mapping, provider="other")
    with pytest.raises(ValueError, match="mapping provider"):
        replace(subject, provider_mapping=wrong_provider, provider_mapping_id=wrong_provider.mapping_id)
    wrong_key = _mapping(subject.provider_mapping, provider_contract_key="other-key")
    with pytest.raises(ValueError, match="mapping key"):
        replace(subject, provider_mapping=wrong_key, provider_mapping_id=wrong_key.mapping_id)
    wrong_version = _mapping(subject.provider_mapping, contract_version_id="other-version")
    with pytest.raises(ValueError, match="mapping version"):
        replace(subject, provider_mapping=wrong_version, provider_mapping_id=wrong_version.mapping_id)


def test_resolved_subject_rejects_stale_and_invisible_mapping() -> None:
    subject = subjects()[0]
    stale = _mapping(
        subject.provider_mapping,
        effective_from=AT - timedelta(days=2),
        effective_until=AT,
    )
    with pytest.raises(ValueError, match="stale_provider_mapping"):
        replace(subject, provider_mapping=stale, provider_mapping_id=stale.mapping_id)
    future_known = _mapping(subject.provider_mapping, recorded_at=AT + timedelta(seconds=1))
    with pytest.raises(ValueError, match="stale_provider_mapping"):
        replace(subject, provider_mapping=future_known, provider_mapping_id=future_known.mapping_id)
    superseded = _mapping(
        subject.provider_mapping,
        recorded_at=AT - timedelta(seconds=2),
        superseded_at=AT - timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="stale_provider_mapping"):
        replace(subject, provider_mapping=superseded, provider_mapping_id=superseded.mapping_id)


def test_resolved_subject_rejects_wrong_economic_identity_and_kind() -> None:
    subject = subjects()[0]
    with pytest.raises(ValueError, match="economic identity"):
        replace(subject, economic_subject_id="wrong")
    with pytest.raises(ValueError, match="subject kind"):
        replace(subject, instrument_kind=MarketSubjectKind.FUTURE)


def _underlying_event(response_type=MarketDataFeed_pb2.live_feed):
    response = feed_response(response_type)
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    return normalize(response).accepted_events[0]


@pytest.mark.parametrize(
    "changes,pattern",
    [
        ({"provider": "other"}, "provider provenance"),
        ({"provider_contract_key": "other"}, "provider key provenance"),
        ({"provider_mapping_id": "other"}, "mapping provenance"),
        ({"contract_version_id": "other"}, "version provenance"),
        ({"economic_subject_id": "other"}, "normalized quote identity"),
        ({"source_order": -1}, "source_order"),
        ({"source_order": True}, "source_order"),
        ({"source_order_scope_id": ""}, "non-empty"),
        ({"provider_sequence": 1}, "must be absent"),
        ({"supersedes_event_id": "event"}, "must be absent"),
        ({"feed_response_type": FeedResponseType.MARKET_INFO}, "market_info"),
        ({"is_snapshot": True}, "snapshot flag"),
    ],
)
def test_quote_direct_construction_rejects_invalid_provenance(changes, pattern) -> None:
    with pytest.raises((TypeError, ValueError), match=pattern):
        replace(_underlying_event(), **changes)


def test_quote_class_kind_and_event_type_must_match() -> None:
    event = _underlying_event()
    values = {field.name: getattr(event, field.name) for field in fields(event)}
    with pytest.raises(ValueError, match="class, subject kind"):
        FuturesQuoteObservationV1(**values)
    with pytest.raises(ValueError, match="class, subject kind"):
        replace(event, identity=replace(event.identity, event_type="futures_quote_observation"))


def test_initial_and_live_snapshot_flags_are_exact() -> None:
    initial = _underlying_event(MarketDataFeed_pb2.initial_feed)
    live = _underlying_event(MarketDataFeed_pb2.live_feed)
    assert initial.is_snapshot is True
    assert live.is_snapshot is False


def test_normalized_event_time_enforces_availability_basis() -> None:
    received = NormalizedMarketEventTimeV1(
        provider_timestamp=AT,
        exchange_timestamp=None,
        received_at=AT,
        available_at=AT,
        recorded_at=AT,
        availability_basis=NormalizedAvailabilityBasis.RECEIVED,
    )
    assert received.available_at == received.received_at
    historical = replace(
        received,
        received_at=None,
        availability_basis=NormalizedAvailabilityBasis.HISTORICAL_IMPORT,
    )
    assert historical.received_at is None
    with pytest.raises(ValueError, match="equal receipt"):
        replace(received, available_at=AT + timedelta(seconds=1), recorded_at=AT + timedelta(seconds=1))
    with pytest.raises(ValueError, match="absent received"):
        replace(received, availability_basis=NormalizedAvailabilityBasis.HISTORICAL_IMPORT)


@pytest.mark.parametrize(
    "field,value,pattern",
    [
        ("bid_size", True, "signed 64-bit"),
        ("ask_size", 2**63, "signed 64-bit"),
        ("last_size", -1, "signed 64-bit"),
        ("reported_volume", 2**63, "signed 64-bit"),
        ("open_interest", True, "safe range"),
        ("open_interest", 2**53 + 1, "safe range"),
        ("provider_depth_levels_present", True, "provider depth"),
        ("provider_depth_levels_present", 31, "provider depth"),
        ("normalized_depth_levels", 2, "normalized depth"),
        ("unadopted_depth_level_count", True, "unadopted depth"),
        ("unadopted_depth_level_count", -1, "unadopted depth"),
    ],
)
def test_quote_direct_construction_rejects_numeric_and_depth_bypass(field, value, pattern) -> None:
    with pytest.raises(ValueError, match=pattern):
        replace(_underlying_event(), **{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_depth_levels_present": 1, "normalized_depth_levels": 1, "unadopted_depth_level_count": 0},
        {
            "feed_union": ProviderFeedUnion.MARKET_FULL_FEED,
            "request_mode": ProviderRequestMode.FULL_D5,
            "provider_depth_levels_present": 6,
            "normalized_depth_levels": 1,
            "unadopted_depth_level_count": 5,
        },
        {
            "feed_union": ProviderFeedUnion.FIRST_LEVEL_WITH_GREEKS,
            "request_mode": ProviderRequestMode.OPTION_GREEKS,
            "provider_depth_levels_present": 1,
            "normalized_depth_levels": 0,
            "unadopted_depth_level_count": 1,
        },
    ],
)
def test_quote_direct_construction_rejects_feed_union_depth_mismatch(changes) -> None:
    with pytest.raises(ValueError, match="feed union depth mismatch"):
        replace(_underlying_event(), **changes)


@pytest.mark.parametrize("value", [("",), ("bad path",), ("bad\npath",), (1,)])
def test_quote_direct_construction_rejects_uncontrolled_paths(value) -> None:
    with pytest.raises(ValueError, match="controlled paths"):
        replace(_underlying_event(), unadopted_schema_paths=value)
