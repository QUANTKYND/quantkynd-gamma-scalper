from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from app.market_data.normalization.lifecycle import (
    ConnectionLifecycleState,
    RawProviderConnectionLifecycleEventV1,
    RawProviderSubscriptionLifecycleEventV1,
    SubscriptionLifecycleState,
    instrument_keys_digest,
    normalize_connection_lifecycle,
    normalize_subscription_lifecycle,
    validate_connection_lifecycle_sequence,
    validate_subscription_lifecycle_sequence,
)
from tests.market_data.normalization.helpers import AT


def connection(previous, state, order, *, session="session-1", scope="scope-1", reason=None):
    return RawProviderConnectionLifecycleEventV1(
        provider="upstox",
        connection_session_id=session,
        previous_state=previous,
        state=state,
        source_order_scope_id=scope,
        source_order=order,
        occurred_at=AT + timedelta(seconds=order),
        available_at=AT + timedelta(seconds=order),
        recorded_at=AT + timedelta(seconds=order),
        redacted_reason_code=reason,
    )


def subscription(previous, state, order, *, reason=None):
    keys = ("NSE_FO|future", "NSE_FO|option")
    return RawProviderSubscriptionLifecycleEventV1(
        provider="upstox",
        connection_session_id="session-1",
        subscription_scope_id="subscription-1",
        previous_state=previous,
        state=state,
        source_order_scope_id="scope-1",
        source_order=order,
        occurred_at=AT + timedelta(seconds=order),
        available_at=AT + timedelta(seconds=order),
        recorded_at=AT + timedelta(seconds=order),
        request_mode="full_d5",
        instrument_keys_digest=instrument_keys_digest(keys),
        instrument_key_count=len(keys),
        redacted_reason_code=reason,
    )


def test_connection_sequence_and_normalized_identity() -> None:
    raw = (
        connection(None, ConnectionLifecycleState.CONNECTING, 0),
        connection(ConnectionLifecycleState.CONNECTING, ConnectionLifecycleState.CONNECTED, 1),
        connection(ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.AUTHORIZED, 2),
    )
    validate_connection_lifecycle_sequence(raw)
    normalized = tuple(normalize_connection_lifecycle(item) for item in raw)
    validate_connection_lifecycle_sequence(normalized)
    assert normalized[0].identity.subject_id == "session-1"
    assert normalized[0].provider_sequence is None


def test_reconnect_requires_a_new_session_and_scope() -> None:
    raw = (
        connection(ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.AUTHORIZED, 1),
        connection(ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.RECONNECTING, 2),
        connection(None, ConnectionLifecycleState.CONNECTING, 3, session="session-2", scope="scope-2"),
    )
    validate_connection_lifecycle_sequence(raw)
    with pytest.raises(ValueError, match="reconnect"):
        validate_connection_lifecycle_sequence(raw[:-1] + (replace(raw[-1], source_order_scope_id="scope-1"),))


def test_invalid_connection_transition_and_sensitive_reason_are_rejected() -> None:
    with pytest.raises(ValueError, match="invalid_connection"):
        connection(None, ConnectionLifecycleState.AUTHORIZED, 0)
    with pytest.raises(ValueError, match="controlled and redacted"):
        connection(ConnectionLifecycleState.CONNECTING, ConnectionLifecycleState.FAILED, 1, reason="token_expired")
    failed = connection(ConnectionLifecycleState.CONNECTING, ConnectionLifecycleState.FAILED, 1, reason="authorization_failed")
    assert failed.redacted_reason_code == "authorization_failed"


def test_lifecycle_time_and_order_invariants() -> None:
    event = connection(None, ConnectionLifecycleState.CONNECTING, 0)
    with pytest.raises(ValueError, match="source_order"):
        replace(event, source_order=True)
    with pytest.raises(ValueError, match="precede occurred_at"):
        replace(event, occurred_at=AT + timedelta(seconds=1))


def test_subscription_sequence_digest_and_normalized_identity() -> None:
    raw = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 1),
        subscription(SubscriptionLifecycleState.SUBSCRIBED, SubscriptionLifecycleState.MODE_CHANGE_REQUESTED, 2),
        subscription(SubscriptionLifecycleState.MODE_CHANGE_REQUESTED, SubscriptionLifecycleState.MODE_CHANGED, 3),
        subscription(SubscriptionLifecycleState.MODE_CHANGED, SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED, 4),
        subscription(SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED, SubscriptionLifecycleState.UNSUBSCRIBED, 5),
    )
    validate_subscription_lifecycle_sequence(raw)
    normalized = tuple(normalize_subscription_lifecycle(item) for item in raw)
    validate_subscription_lifecycle_sequence(normalized)
    assert normalized[0].identity.subject_id == raw[0].subject_id


def test_subscription_digest_is_sorted_and_rejects_duplicates() -> None:
    assert instrument_keys_digest(("b", "a")) == instrument_keys_digest(("a", "b"))
    with pytest.raises(ValueError, match="duplicate_instrument_key"):
        instrument_keys_digest(("a", "a"))


def test_invalid_subscription_transition_and_sequence_are_rejected() -> None:
    with pytest.raises(ValueError, match="invalid_subscription"):
        subscription(None, SubscriptionLifecycleState.SUBSCRIBED, 0)
    raw = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 1),
    )
    with pytest.raises(ValueError, match="invalid_subscription_lifecycle_sequence"):
        validate_subscription_lifecycle_sequence((raw[0], replace(raw[1], instrument_key_count=3)))
