from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.market_data.normalization.lifecycle import (
    ConnectionLifecycleState,
    RawProviderConnectionLifecycleEventV1,
    RawProviderSubscriptionLifecycleEventV1,
    SubscriptionInstrumentSetV1,
    SubscriptionLifecycleState,
    instrument_keys_digest,
    normalize_connection_lifecycle,
    normalize_subscription_lifecycle,
    validate_connection_lifecycle_sequence,
    validate_raw_lifecycle_identity_batch,
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


def subscription(
    previous,
    state,
    order,
    *,
    reason=None,
    mode="full_d5",
    keys=("NSE_FO|future", "NSE_FO|option"),
    subscription_scope="subscription-1",
    session="session-1",
    source_scope="scope-1",
):
    return RawProviderSubscriptionLifecycleEventV1(
        provider="upstox",
        connection_session_id=session,
        subscription_scope_id=subscription_scope,
        previous_state=previous,
        state=state,
        source_order_scope_id=source_scope,
        source_order=order,
        occurred_at=AT + timedelta(seconds=order),
        available_at=AT + timedelta(seconds=order),
        recorded_at=AT + timedelta(seconds=order),
        request_mode=mode,
        instrument_set=SubscriptionInstrumentSetV1(keys),
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
        connection(ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.AUTHORIZED, 99),
        connection(ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.RECONNECTING, 100),
        connection(None, ConnectionLifecycleState.CONNECTING, 0, session="session-2", scope="scope-2"),
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
    with pytest.raises(ValueError, match="must not be empty"):
        SubscriptionInstrumentSetV1(())
    assert SubscriptionInstrumentSetV1(("a",)).instrument_key_count == 1
    assert instrument_keys_digest(("b", "a")) == instrument_keys_digest(("a", "b"))
    with pytest.raises(ValueError, match="duplicate_instrument_key"):
        instrument_keys_digest(("a", "a"))
    with pytest.raises(ValueError, match="non-empty"):
        SubscriptionInstrumentSetV1(("",))
    assert SubscriptionInstrumentSetV1(("b", "a")).provider_contract_keys == ("a", "b")
    with pytest.raises(TypeError):
        SubscriptionInstrumentSetV1(("a",), instrument_keys_digest="forged")


def test_interleaved_subscription_scopes_validate_independently() -> None:
    events = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0, subscription_scope="A"),
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 1, subscription_scope="B"),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 2, subscription_scope="A"),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 3, subscription_scope="B"),
    )
    validate_subscription_lifecycle_sequence(events)


def test_interleaved_mode_change_and_subscription_scope_bindings() -> None:
    events = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0, subscription_scope="A"),
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 1, subscription_scope="B"),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 2, subscription_scope="A"),
        subscription(SubscriptionLifecycleState.SUBSCRIBED, SubscriptionLifecycleState.MODE_CHANGE_REQUESTED, 3, subscription_scope="A", mode="ltpc"),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 4, subscription_scope="B"),
        subscription(SubscriptionLifecycleState.MODE_CHANGE_REQUESTED, SubscriptionLifecycleState.MODE_CHANGED, 5, subscription_scope="A", mode="ltpc"),
    )
    validate_subscription_lifecycle_sequence(events)
    with pytest.raises(ValueError):
        validate_subscription_lifecycle_sequence(events + (replace(events[-1], source_order=4),))
    with pytest.raises(ValueError):
        validate_subscription_lifecycle_sequence((events[0], replace(events[2], connection_session_id="session-2")))
    with pytest.raises(ValueError):
        validate_subscription_lifecycle_sequence((events[0], replace(events[2], source_order_scope_id="scope-2")))
    with pytest.raises(ValueError):
        validate_subscription_lifecycle_sequence((events[0], replace(events[2], instrument_set=SubscriptionInstrumentSetV1(("other",)))))


def test_completed_subscription_scope_cannot_restart_or_be_reintroduced() -> None:
    completed = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0, subscription_scope="A"),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 1, subscription_scope="A"),
        subscription(SubscriptionLifecycleState.SUBSCRIBED, SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED, 2, subscription_scope="A"),
        subscription(SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED, SubscriptionLifecycleState.UNSUBSCRIBED, 3, subscription_scope="A"),
    )
    with pytest.raises(ValueError):
        validate_subscription_lifecycle_sequence(completed + (subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 4, subscription_scope="A"),))
    failed = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0, subscription_scope="A"),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIPTION_FAILED, 1, subscription_scope="A", reason="provider_rejected"),
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 2, subscription_scope="B"),
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 3, subscription_scope="A"),
    )
    with pytest.raises(ValueError):
        validate_subscription_lifecycle_sequence(failed)


def test_invalid_subscription_transition_and_sequence_are_rejected() -> None:
    with pytest.raises(ValueError, match="invalid_subscription"):
        subscription(None, SubscriptionLifecycleState.SUBSCRIBED, 0)
    raw = (
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0),
        subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 1),
    )
    with pytest.raises(ValueError, match="invalid_subscription_lifecycle_sequence"):
        validate_subscription_lifecycle_sequence((raw[0], subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 1, mode="ltpc")))
    with pytest.raises(ValueError):
        subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0, mode="arbitrary")


def test_scoped_connection_ordering_rejects_only_within_scope() -> None:
    with pytest.raises(ValueError, match="invalid_connection_lifecycle_sequence"):
        validate_connection_lifecycle_sequence(
            (
                connection(ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.AUTHORIZED, 100),
                connection(ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.CLOSING, 0),
            )
        )
    reconnecting = connection(ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.RECONNECTING, 100)
    with pytest.raises(ValueError, match="reconnect"):
        validate_connection_lifecycle_sequence((reconnecting, connection(None, ConnectionLifecycleState.CONNECTING, 0, session="session-2", scope="scope-1")))
    with pytest.raises(ValueError, match="reconnect"):
        validate_connection_lifecycle_sequence((connection(ConnectionLifecycleState.CONNECTING, ConnectionLifecycleState.CONNECTED, 100), connection(None, ConnectionLifecycleState.CONNECTING, 0, session="session-2", scope="scope-2")))


def test_normalized_lifecycle_direct_construction_canonicalizes_values() -> None:
    offset = timezone(timedelta(hours=5, minutes=30))
    connection_event = normalize_connection_lifecycle(connection(None, ConnectionLifecycleState.CONNECTING, 0))
    canonical_connection = replace(
        connection_event,
        previous_state=None,
        state="connecting",
        occurred_at=datetime(2026, 8, 5, 9, 30, tzinfo=offset),
        available_at=datetime(2026, 8, 5, 9, 30, tzinfo=offset),
        recorded_at=datetime(2026, 8, 5, 9, 30, tzinfo=offset),
    )
    assert canonical_connection.state is ConnectionLifecycleState.CONNECTING
    assert canonical_connection.occurred_at.tzinfo is UTC
    subscription_event = normalize_subscription_lifecycle(subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0))
    canonical_subscription = replace(
        subscription_event,
        previous_state=None,
        state="subscribe_requested",
        request_mode="full_d5",
        occurred_at=datetime(2026, 8, 5, 9, 30, tzinfo=offset),
        available_at=datetime(2026, 8, 5, 9, 30, tzinfo=offset),
        recorded_at=datetime(2026, 8, 5, 9, 30, tzinfo=offset),
    )
    assert canonical_subscription.state is SubscriptionLifecycleState.SUBSCRIBE_REQUESTED
    assert canonical_subscription.request_mode.value == "full_d5"
    assert canonical_subscription.recorded_at.tzinfo is UTC


def test_subscription_key_change_requires_new_scope() -> None:
    first = subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 0, keys=("a",))
    changed = subscription(SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, SubscriptionLifecycleState.SUBSCRIBED, 1, keys=("b",))
    with pytest.raises(ValueError, match="invalid_subscription_lifecycle_sequence"):
        validate_subscription_lifecycle_sequence((first, changed))
    validate_subscription_lifecycle_sequence((first, subscription(None, SubscriptionLifecycleState.SUBSCRIBE_REQUESTED, 1, keys=("b",), subscription_scope="subscription-2")))


def test_raw_lifecycle_identity_collisions_fail_closed() -> None:
    event = connection(None, ConnectionLifecycleState.CONNECTING, 0)
    duplicate = validate_raw_lifecycle_identity_batch((event, event))
    assert duplicate.exact_duplicate_raw_event_ids == (event.raw_event_id,)
    with pytest.raises(Exception, match=event.raw_event_id):
        validate_raw_lifecycle_identity_batch((event, replace(event, occurred_at=AT - timedelta(seconds=1))))
    independent = replace(event, source_order=1)
    assert len(validate_raw_lifecycle_identity_batch((event, independent)).unique_events) == 2


def test_three_session_reconnect_chain_rejects_non_adjacent_reuse() -> None:
    chain = (
        connection(None, ConnectionLifecycleState.CONNECTING, 0),
        connection(ConnectionLifecycleState.CONNECTING, ConnectionLifecycleState.CONNECTED, 1),
        connection(ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.AUTHORIZED, 2),
        connection(ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.RECONNECTING, 3),
        connection(None, ConnectionLifecycleState.CONNECTING, 0, session="session-2", scope="scope-2"),
        connection(ConnectionLifecycleState.CONNECTING, ConnectionLifecycleState.CONNECTED, 1, session="session-2", scope="scope-2"),
        connection(ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.AUTHORIZED, 2, session="session-2", scope="scope-2"),
        connection(ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.RECONNECTING, 3, session="session-2", scope="scope-2"),
        connection(None, ConnectionLifecycleState.CONNECTING, 0, session="session-3", scope="scope-3"),
    )
    validate_connection_lifecycle_sequence(chain)
    with pytest.raises(ValueError, match="reconnect"):
        validate_connection_lifecycle_sequence(chain[:-1] + (replace(chain[-1], source_order_scope_id="scope-1"),))
    with pytest.raises(ValueError, match="reconnect"):
        validate_connection_lifecycle_sequence(chain[:-1] + (replace(chain[-1], connection_session_id="session-1"),))
