from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from app.core.hashing import canonical_json, stable_hash
from app.market_data.normalization.models import (
    ProviderMarketSegmentStatusObservationV1,
    QuoteObservationV1,
)
from app.market_data.normalization.results import NormalizationFailureV1


def canonical_normalization_json(value: object) -> str:
    return canonical_json(_payload(value))


def full_result_hash(payload: object) -> str:
    return stable_hash(_payload(payload))


def adopted_semantics_hash(
    events: tuple[QuoteObservationV1 | ProviderMarketSegmentStatusObservationV1, ...],
    frame_failure: NormalizationFailureV1 | None,
    entry_failures: tuple[NormalizationFailureV1, ...],
) -> str:
    return stable_hash(
        {
            "schema": "data-1.3-adopted-semantics-v1",
            "events": tuple(_adopted_event_payload(event) for event in events),
            "frame_failure": _payload(frame_failure),
            "entry_failures": tuple(_payload(failure) for failure in entry_failures),
        }
    )


def _adopted_event_payload(event: QuoteObservationV1 | ProviderMarketSegmentStatusObservationV1) -> object:
    if isinstance(event, QuoteObservationV1):
        return {
            "event_type": event.identity.event_type,
            "economic_subject_id": event.economic_subject_id,
            "feed_response_type": event.feed_response_type.value,
            "request_mode": event.request_mode.value,
            "feed_union": event.feed_union.value,
            "is_snapshot": event.is_snapshot,
            "presence_semantics": event.presence_semantics,
            "numeric_basis": event.numeric_basis,
            "quantity_basis": event.quantity_basis,
            "provider_timestamp": event.event_time.provider_timestamp,
            "bid_price": event.bid_price,
            "bid_size": event.bid_size,
            "ask_price": event.ask_price,
            "ask_size": event.ask_size,
            "last_price": event.last_price,
            "last_size": event.last_size,
            "last_trade_at": event.last_trade_at,
            "previous_close_price": event.previous_close_price,
            "reported_volume": event.reported_volume,
            "open_interest": event.open_interest,
            "provider_depth_levels_present": event.provider_depth_levels_present,
            "normalized_depth_levels": event.normalized_depth_levels,
            "unadopted_depth_level_count": event.unadopted_depth_level_count,
        }
    return {
        "event_type": event.identity.event_type,
        "segment": event.segment,
        "provider_status_name": event.provider_status_name,
        "provider_status_numeric": event.provider_status_numeric,
        "status_is_known": event.status_is_known,
        "provider_timestamp": event.provider_timestamp,
    }


def _payload(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _payload(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_payload(item) for item in value)
    if isinstance(value, (set, frozenset)):
        normalized = tuple(_payload(item) for item in value)
        return tuple(sorted(normalized, key=canonical_json))
    return value
