from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.core.hashing import stable_hash
from app.market_data.normalization.models import (
    NORMALIZATION_SCHEMA_VERSION,
    NORMALIZER_IMPLEMENTATION_VERSION,
)
from app.market_data.point_in_time import NormalizedMarketEventIdentity


_CONTROLLED_REASON = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
_SENSITIVE_REASON_PARTS = ("token", "url", "traceback", "socket", "account", "user_id", "exception")


class ConnectionLifecycleState(StrEnum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHORIZED = "authorized"
    CLOSING = "closing"
    CLOSED = "closed"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class SubscriptionLifecycleState(StrEnum):
    SUBSCRIBE_REQUESTED = "subscribe_requested"
    SUBSCRIBED = "subscribed"
    MODE_CHANGE_REQUESTED = "mode_change_requested"
    MODE_CHANGED = "mode_changed"
    UNSUBSCRIBE_REQUESTED = "unsubscribe_requested"
    UNSUBSCRIBED = "unsubscribed"
    SUBSCRIPTION_FAILED = "subscription_failed"


CONNECTION_TRANSITIONS = {
    None: frozenset({ConnectionLifecycleState.CONNECTING}),
    ConnectionLifecycleState.CONNECTING: frozenset(
        {ConnectionLifecycleState.CONNECTED, ConnectionLifecycleState.FAILED, ConnectionLifecycleState.CLOSING}
    ),
    ConnectionLifecycleState.CONNECTED: frozenset(
        {ConnectionLifecycleState.AUTHORIZED, ConnectionLifecycleState.CLOSING, ConnectionLifecycleState.FAILED}
    ),
    ConnectionLifecycleState.AUTHORIZED: frozenset(
        {ConnectionLifecycleState.CLOSING, ConnectionLifecycleState.RECONNECTING, ConnectionLifecycleState.FAILED}
    ),
    ConnectionLifecycleState.RECONNECTING: frozenset(
        {ConnectionLifecycleState.CLOSING, ConnectionLifecycleState.FAILED}
    ),
    ConnectionLifecycleState.CLOSING: frozenset(
        {ConnectionLifecycleState.CLOSED, ConnectionLifecycleState.FAILED}
    ),
    ConnectionLifecycleState.FAILED: frozenset(
        {ConnectionLifecycleState.RECONNECTING, ConnectionLifecycleState.CLOSING, ConnectionLifecycleState.CLOSED}
    ),
}

SUBSCRIPTION_TRANSITIONS = {
    None: frozenset({SubscriptionLifecycleState.SUBSCRIBE_REQUESTED}),
    SubscriptionLifecycleState.SUBSCRIBE_REQUESTED: frozenset(
        {SubscriptionLifecycleState.SUBSCRIBED, SubscriptionLifecycleState.SUBSCRIPTION_FAILED}
    ),
    SubscriptionLifecycleState.SUBSCRIBED: frozenset(
        {
            SubscriptionLifecycleState.MODE_CHANGE_REQUESTED,
            SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED,
            SubscriptionLifecycleState.SUBSCRIPTION_FAILED,
        }
    ),
    SubscriptionLifecycleState.MODE_CHANGE_REQUESTED: frozenset(
        {SubscriptionLifecycleState.MODE_CHANGED, SubscriptionLifecycleState.SUBSCRIPTION_FAILED}
    ),
    SubscriptionLifecycleState.MODE_CHANGED: frozenset(
        {
            SubscriptionLifecycleState.MODE_CHANGE_REQUESTED,
            SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED,
            SubscriptionLifecycleState.SUBSCRIPTION_FAILED,
        }
    ),
    SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED: frozenset(
        {SubscriptionLifecycleState.UNSUBSCRIBED, SubscriptionLifecycleState.SUBSCRIPTION_FAILED}
    ),
}


@dataclass(frozen=True)
class RawProviderConnectionLifecycleEventV1:
    provider: str
    connection_session_id: str
    previous_state: ConnectionLifecycleState | None
    state: ConnectionLifecycleState
    source_order_scope_id: str
    source_order: int
    occurred_at: datetime
    available_at: datetime
    recorded_at: datetime
    redacted_reason_code: str | None = None
    provider_sequence: None = None

    def __post_init__(self) -> None:
        _validate_common(self)
        previous = ConnectionLifecycleState(self.previous_state) if self.previous_state is not None else None
        state = ConnectionLifecycleState(self.state)
        object.__setattr__(self, "previous_state", previous)
        object.__setattr__(self, "state", state)
        if state not in CONNECTION_TRANSITIONS.get(previous, frozenset()):
            raise ValueError("invalid_connection_lifecycle_transition")
        _validate_reason(state is ConnectionLifecycleState.FAILED, self.redacted_reason_code)

    @property
    def raw_event_id(self) -> str:
        return stable_hash(
            {
                "entity": "raw_provider_connection_lifecycle_event_v1",
                "provider": self.provider,
                "connection_session_id": self.connection_session_id,
                "source_order_scope_id": self.source_order_scope_id,
                "source_order": self.source_order,
                "lifecycle_kind": "connection",
            }
        )


@dataclass(frozen=True)
class ProviderConnectionLifecycleObservationV1:
    identity: NormalizedMarketEventIdentity
    raw_event_id: str
    provider: str
    connection_session_id: str
    previous_state: ConnectionLifecycleState | None
    state: ConnectionLifecycleState
    source_order_scope_id: str
    source_order: int
    occurred_at: datetime
    available_at: datetime
    recorded_at: datetime
    redacted_reason_code: str | None
    normalization_schema_version: int
    normalizer_implementation_version: str
    provider_sequence: None

    def __post_init__(self) -> None:
        raw = RawProviderConnectionLifecycleEventV1(
            provider=self.provider,
            connection_session_id=self.connection_session_id,
            previous_state=self.previous_state,
            state=self.state,
            source_order_scope_id=self.source_order_scope_id,
            source_order=self.source_order,
            occurred_at=self.occurred_at,
            available_at=self.available_at,
            recorded_at=self.recorded_at,
            redacted_reason_code=self.redacted_reason_code,
            provider_sequence=self.provider_sequence,
        )
        _validate_normalized(self, raw.raw_event_id, self.connection_session_id, "provider_connection_lifecycle_observation")

    @property
    def event_id(self) -> str:
        return self.identity.event_id


@dataclass(frozen=True)
class RawProviderSubscriptionLifecycleEventV1:
    provider: str
    connection_session_id: str
    subscription_scope_id: str
    previous_state: SubscriptionLifecycleState | None
    state: SubscriptionLifecycleState
    source_order_scope_id: str
    source_order: int
    occurred_at: datetime
    available_at: datetime
    recorded_at: datetime
    request_mode: str | None
    instrument_keys_digest: str
    instrument_key_count: int
    redacted_reason_code: str | None = None
    provider_sequence: None = None

    def __post_init__(self) -> None:
        _validate_common(self)
        _require_text(self.subscription_scope_id, self.instrument_keys_digest)
        if not isinstance(self.instrument_key_count, int) or isinstance(self.instrument_key_count, bool) or self.instrument_key_count < 0:
            raise ValueError("instrument_key_count must be a non-negative integer")
        if self.request_mode is not None:
            _require_text(self.request_mode)
        previous = SubscriptionLifecycleState(self.previous_state) if self.previous_state is not None else None
        state = SubscriptionLifecycleState(self.state)
        object.__setattr__(self, "previous_state", previous)
        object.__setattr__(self, "state", state)
        if state not in SUBSCRIPTION_TRANSITIONS.get(previous, frozenset()):
            raise ValueError("invalid_subscription_lifecycle_transition")
        _validate_reason(state is SubscriptionLifecycleState.SUBSCRIPTION_FAILED, self.redacted_reason_code)

    @property
    def subject_id(self) -> str:
        return stable_hash(
            {
                "entity": "provider_subscription",
                "provider": self.provider,
                "connection_session_id": self.connection_session_id,
                "subscription_scope_id": self.subscription_scope_id,
            }
        )

    @property
    def raw_event_id(self) -> str:
        return stable_hash(
            {
                "entity": "raw_provider_subscription_lifecycle_event_v1",
                "provider": self.provider,
                "connection_session_id": self.connection_session_id,
                "subscription_scope_id": self.subscription_scope_id,
                "source_order_scope_id": self.source_order_scope_id,
                "source_order": self.source_order,
                "lifecycle_kind": "subscription",
            }
        )


@dataclass(frozen=True)
class ProviderSubscriptionLifecycleObservationV1:
    identity: NormalizedMarketEventIdentity
    raw_event_id: str
    provider: str
    connection_session_id: str
    subscription_scope_id: str
    previous_state: SubscriptionLifecycleState | None
    state: SubscriptionLifecycleState
    source_order_scope_id: str
    source_order: int
    occurred_at: datetime
    available_at: datetime
    recorded_at: datetime
    request_mode: str | None
    instrument_keys_digest: str
    instrument_key_count: int
    redacted_reason_code: str | None
    normalization_schema_version: int
    normalizer_implementation_version: str
    provider_sequence: None

    def __post_init__(self) -> None:
        raw = RawProviderSubscriptionLifecycleEventV1(
            provider=self.provider,
            connection_session_id=self.connection_session_id,
            subscription_scope_id=self.subscription_scope_id,
            previous_state=self.previous_state,
            state=self.state,
            source_order_scope_id=self.source_order_scope_id,
            source_order=self.source_order,
            occurred_at=self.occurred_at,
            available_at=self.available_at,
            recorded_at=self.recorded_at,
            request_mode=self.request_mode,
            instrument_keys_digest=self.instrument_keys_digest,
            instrument_key_count=self.instrument_key_count,
            redacted_reason_code=self.redacted_reason_code,
            provider_sequence=self.provider_sequence,
        )
        _validate_normalized(self, raw.raw_event_id, raw.subject_id, "provider_subscription_lifecycle_observation")

    @property
    def event_id(self) -> str:
        return self.identity.event_id


def normalize_connection_lifecycle(
    raw: RawProviderConnectionLifecycleEventV1,
) -> ProviderConnectionLifecycleObservationV1:
    identity = NormalizedMarketEventIdentity(
        raw_event_id=raw.raw_event_id,
        event_type="provider_connection_lifecycle_observation",
        subject_id=raw.connection_session_id,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
    )
    return ProviderConnectionLifecycleObservationV1(
        identity=identity,
        raw_event_id=raw.raw_event_id,
        provider=raw.provider,
        connection_session_id=raw.connection_session_id,
        previous_state=raw.previous_state,
        state=raw.state,
        source_order_scope_id=raw.source_order_scope_id,
        source_order=raw.source_order,
        occurred_at=raw.occurred_at,
        available_at=raw.available_at,
        recorded_at=raw.recorded_at,
        redacted_reason_code=raw.redacted_reason_code,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        normalizer_implementation_version=NORMALIZER_IMPLEMENTATION_VERSION,
        provider_sequence=None,
    )


def normalize_subscription_lifecycle(
    raw: RawProviderSubscriptionLifecycleEventV1,
) -> ProviderSubscriptionLifecycleObservationV1:
    identity = NormalizedMarketEventIdentity(
        raw_event_id=raw.raw_event_id,
        event_type="provider_subscription_lifecycle_observation",
        subject_id=raw.subject_id,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
    )
    return ProviderSubscriptionLifecycleObservationV1(
        identity=identity,
        raw_event_id=raw.raw_event_id,
        provider=raw.provider,
        connection_session_id=raw.connection_session_id,
        subscription_scope_id=raw.subscription_scope_id,
        previous_state=raw.previous_state,
        state=raw.state,
        source_order_scope_id=raw.source_order_scope_id,
        source_order=raw.source_order,
        occurred_at=raw.occurred_at,
        available_at=raw.available_at,
        recorded_at=raw.recorded_at,
        request_mode=raw.request_mode,
        instrument_keys_digest=raw.instrument_keys_digest,
        instrument_key_count=raw.instrument_key_count,
        redacted_reason_code=raw.redacted_reason_code,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        normalizer_implementation_version=NORMALIZER_IMPLEMENTATION_VERSION,
        provider_sequence=None,
    )


def instrument_keys_digest(provider_contract_keys: tuple[str, ...]) -> str:
    if any(not isinstance(key, str) or not key.strip() for key in provider_contract_keys):
        raise ValueError("instrument keys must be non-empty text")
    if len(set(provider_contract_keys)) != len(provider_contract_keys):
        raise ValueError("duplicate_instrument_key")
    return stable_hash(
        {
            "entity": "provider_subscription_instrument_keys_v1",
            "provider_contract_keys": tuple(sorted(provider_contract_keys)),
        }
    )


def validate_connection_lifecycle_sequence(
    events: tuple[RawProviderConnectionLifecycleEventV1 | ProviderConnectionLifecycleObservationV1, ...],
) -> None:
    for previous, current in zip(events, events[1:], strict=False):
        if current.provider != previous.provider or current.source_order <= previous.source_order:
            raise ValueError("invalid_connection_lifecycle_sequence")
        if current.connection_session_id == previous.connection_session_id:
            if current.source_order_scope_id != previous.source_order_scope_id or current.previous_state is not previous.state:
                raise ValueError("invalid_connection_lifecycle_sequence")
        elif (
            previous.state is not ConnectionLifecycleState.RECONNECTING
            or current.previous_state is not None
            or current.state is not ConnectionLifecycleState.CONNECTING
            or current.source_order_scope_id == previous.source_order_scope_id
        ):
            raise ValueError("invalid_connection_reconnect_sequence")


def validate_subscription_lifecycle_sequence(
    events: tuple[RawProviderSubscriptionLifecycleEventV1 | ProviderSubscriptionLifecycleObservationV1, ...],
) -> None:
    for previous, current in zip(events, events[1:], strict=False):
        if (
            current.provider != previous.provider
            or current.connection_session_id != previous.connection_session_id
            or current.subscription_scope_id != previous.subscription_scope_id
            or current.source_order_scope_id != previous.source_order_scope_id
            or current.source_order <= previous.source_order
            or current.previous_state is not previous.state
            or current.instrument_keys_digest != previous.instrument_keys_digest
            or current.instrument_key_count != previous.instrument_key_count
        ):
            raise ValueError("invalid_subscription_lifecycle_sequence")


def _validate_common(event) -> None:
    _require_text(event.provider, event.connection_session_id, event.source_order_scope_id)
    if not isinstance(event.source_order, int) or isinstance(event.source_order, bool) or event.source_order < 0:
        raise ValueError("source_order must be a non-negative integer")
    for name in ("occurred_at", "available_at", "recorded_at"):
        object.__setattr__(event, name, _utc(getattr(event, name), name))
    if event.available_at < event.occurred_at:
        raise ValueError("available_at cannot precede occurred_at")
    if event.recorded_at < event.available_at:
        raise ValueError("recorded_at cannot precede available_at")
    if event.provider_sequence is not None:
        raise ValueError("provider_sequence must be absent")


def _validate_normalized(event, raw_event_id: str, subject_id: str, event_type: str) -> None:
    if not isinstance(event.identity, NormalizedMarketEventIdentity):
        raise TypeError("normalized lifecycle identity is required")
    if event.raw_event_id != raw_event_id or event.identity.raw_event_id != raw_event_id:
        raise ValueError("normalized lifecycle raw identity mismatch")
    if event.identity.subject_id != subject_id or event.identity.event_type != event_type:
        raise ValueError("normalized lifecycle identity mismatch")
    if event.normalization_schema_version != NORMALIZATION_SCHEMA_VERSION:
        raise ValueError("unsupported normalization schema version")
    if event.identity.normalization_schema_version != event.normalization_schema_version:
        raise ValueError("lifecycle identity schema version mismatch")
    if event.normalizer_implementation_version != NORMALIZER_IMPLEMENTATION_VERSION:
        raise ValueError("normalizer implementation semantics mismatch")


def _validate_reason(required: bool, value: str | None) -> None:
    if required and value is None:
        raise ValueError("redacted_reason_code is required for failure")
    if not required and value is not None:
        raise ValueError("redacted_reason_code is only valid for failure")
    if value is not None and (
        _CONTROLLED_REASON.fullmatch(value) is None
        or any(part in value for part in _SENSITIVE_REASON_PARTS)
    ):
        raise ValueError("redacted_reason_code must be controlled and redacted")


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("lifecycle text values must be non-empty")


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
