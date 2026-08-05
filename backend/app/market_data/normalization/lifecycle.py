from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.core.hashing import stable_hash
from app.market_data.normalization.enums import ProviderRequestMode
from app.market_data.normalization.errors import ConflictingRawIdentityError
from app.market_data.normalization.models import (
    NORMALIZATION_SCHEMA_VERSION,
    NORMALIZER_IMPLEMENTATION_VERSION,
)
from app.market_data.normalization.limits import (
    MAX_LIFECYCLE_EVENTS_PER_BATCH,
    validate_opaque_identifier,
    validate_redacted_reason_code_size,
    validate_source_order,
)
from app.market_data.normalization.provider_identifiers import validate_provider_contract_key
from app.market_data.point_in_time import NormalizedMarketEventIdentity


_CONTROLLED_REASON = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
_SENSITIVE_REASON_PARTS = ("token", "url", "traceback", "socket", "account", "user_id", "exception")
MAX_SUBSCRIPTION_INSTRUMENT_KEYS = 5_000
SUBSCRIPTION_MODE_INSTRUMENT_LIMITS = {
    ProviderRequestMode.LTPC: 5_000,
    ProviderRequestMode.OPTION_GREEKS: 3_000,
    ProviderRequestMode.FULL_D5: 2_000,
    ProviderRequestMode.FULL_D30: 50,
}


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


@dataclass(frozen=True)
class SubscriptionInstrumentSetV1:
    provider_contract_keys: tuple[str, ...]
    instrument_keys_digest: str = field(init=False)
    instrument_key_count: int = field(init=False)

    def __post_init__(self) -> None:
        keys = self.provider_contract_keys
        if not keys:
            raise ValueError("subscription instrument set must not be empty")
        if len(keys) > MAX_SUBSCRIPTION_INSTRUMENT_KEYS:
            raise ValueError("too_many_subscription_instrument_keys")
        for key in keys:
            validate_provider_contract_key(key)
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate_instrument_key")
        canonical = tuple(sorted(keys))
        object.__setattr__(self, "provider_contract_keys", canonical)
        object.__setattr__(self, "instrument_key_count", len(canonical))
        object.__setattr__(
            self,
            "instrument_keys_digest",
            stable_hash(
                {
                    "entity": "provider_subscription_instrument_keys_v1",
                    "provider_contract_keys": canonical,
                }
            ),
        )


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
        _apply_raw_canonical_values(self, raw)
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
    request_mode: ProviderRequestMode | None
    instrument_set: SubscriptionInstrumentSetV1
    instrument_keys_digest: str = field(init=False)
    instrument_key_count: int = field(init=False)
    redacted_reason_code: str | None = None
    provider_sequence: None = None

    def __post_init__(self) -> None:
        _validate_common(self)
        validate_opaque_identifier(self.subscription_scope_id, "subscription_scope_id")
        if not isinstance(self.instrument_set, SubscriptionInstrumentSetV1):
            raise TypeError("subscription instrument set is required")
        object.__setattr__(self, "instrument_keys_digest", self.instrument_set.instrument_keys_digest)
        object.__setattr__(self, "instrument_key_count", self.instrument_set.instrument_key_count)
        if self.request_mode is not None:
            object.__setattr__(self, "request_mode", ProviderRequestMode(self.request_mode))
            if self.instrument_key_count > SUBSCRIPTION_MODE_INSTRUMENT_LIMITS[self.request_mode]:
                raise ValueError("subscription_request_mode_instrument_limit_exceeded")
        previous = SubscriptionLifecycleState(self.previous_state) if self.previous_state is not None else None
        state = SubscriptionLifecycleState(self.state)
        object.__setattr__(self, "previous_state", previous)
        object.__setattr__(self, "state", state)
        if state not in SUBSCRIPTION_TRANSITIONS.get(previous, frozenset()):
            raise ValueError("invalid_subscription_lifecycle_transition")
        if state in {
            SubscriptionLifecycleState.SUBSCRIBE_REQUESTED,
            SubscriptionLifecycleState.SUBSCRIBED,
            SubscriptionLifecycleState.MODE_CHANGE_REQUESTED,
            SubscriptionLifecycleState.MODE_CHANGED,
        } and self.request_mode is None:
            raise ValueError("subscription request mode is required")
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
    request_mode: ProviderRequestMode | None
    instrument_set: SubscriptionInstrumentSetV1
    instrument_keys_digest: str = field(init=False)
    instrument_key_count: int = field(init=False)
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
            instrument_set=self.instrument_set,
            redacted_reason_code=self.redacted_reason_code,
            provider_sequence=self.provider_sequence,
        )
        _apply_raw_canonical_values(self, raw)
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
        instrument_set=raw.instrument_set,
        redacted_reason_code=raw.redacted_reason_code,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        normalizer_implementation_version=NORMALIZER_IMPLEMENTATION_VERSION,
        provider_sequence=None,
    )


def instrument_keys_digest(provider_contract_keys: tuple[str, ...]) -> str:
    return SubscriptionInstrumentSetV1(provider_contract_keys).instrument_keys_digest


def validate_connection_lifecycle_sequence(
    events: tuple[RawProviderConnectionLifecycleEventV1 | ProviderConnectionLifecycleObservationV1, ...],
) -> None:
    session_scopes: dict[str, str] = {}
    scope_sessions: dict[str, str] = {}
    scope_orders: dict[str, int] = {}
    previous = None
    for current in events:
        bound_scope = session_scopes.get(current.connection_session_id)
        bound_session = scope_sessions.get(current.source_order_scope_id)
        if previous is not None and current.connection_session_id != previous.connection_session_id and (
            previous.state is not ConnectionLifecycleState.RECONNECTING
            or current.previous_state is not None
            or current.state is not ConnectionLifecycleState.CONNECTING
            or bound_scope is not None
            or bound_session is not None
        ):
            raise ValueError("invalid_connection_reconnect_sequence")
        if bound_scope is not None and bound_scope != current.source_order_scope_id:
            raise ValueError("invalid_connection_lifecycle_sequence")
        if bound_session is not None and bound_session != current.connection_session_id:
            raise ValueError("invalid_connection_lifecycle_sequence")
        prior_order = scope_orders.get(current.source_order_scope_id)
        if prior_order is not None and current.source_order <= prior_order:
            raise ValueError("invalid_connection_lifecycle_sequence")
        if previous is not None and current.connection_session_id == previous.connection_session_id:
            if current.previous_state is not previous.state:
                raise ValueError("invalid_connection_lifecycle_sequence")
        if previous is not None and current.provider != previous.provider:
            raise ValueError("invalid_connection_lifecycle_sequence")
        session_scopes[current.connection_session_id] = current.source_order_scope_id
        scope_sessions[current.source_order_scope_id] = current.connection_session_id
        scope_orders[current.source_order_scope_id] = current.source_order
        previous = current


def validate_subscription_lifecycle_sequence(
    events: tuple[RawProviderSubscriptionLifecycleEventV1 | ProviderSubscriptionLifecycleObservationV1, ...],
) -> None:
    scope_events = {}
    source_scope_bindings: dict[str, tuple[str, str]] = {}
    source_scope_orders: dict[str, int] = {}
    for current in events:
        source_binding = (current.provider, current.connection_session_id)
        if source_scope_bindings.get(current.source_order_scope_id, source_binding) != source_binding:
            raise ValueError("invalid_subscription_lifecycle_sequence")
        prior_order = source_scope_orders.get(current.source_order_scope_id)
        if prior_order is not None and current.source_order <= prior_order:
            raise ValueError("invalid_subscription_lifecycle_sequence")
        previous = scope_events.get(current.subscription_scope_id)
        if previous is None:
            if current.previous_state is not None or current.state is not SubscriptionLifecycleState.SUBSCRIBE_REQUESTED:
                raise ValueError("invalid_subscription_lifecycle_sequence")
        elif (
            current.provider != previous.provider
            or current.connection_session_id != previous.connection_session_id
            or current.source_order_scope_id != previous.source_order_scope_id
            or current.previous_state is not previous.state
            or current.instrument_set != previous.instrument_set
            or not _subscription_modes_agree(previous, current)
        ):
            raise ValueError("invalid_subscription_lifecycle_sequence")
        source_scope_bindings[current.source_order_scope_id] = source_binding
        source_scope_orders[current.source_order_scope_id] = current.source_order
        scope_events[current.subscription_scope_id] = current


@dataclass(frozen=True)
class RawLifecycleIdentityBatchValidationV1:
    unique_events: tuple[RawProviderConnectionLifecycleEventV1 | RawProviderSubscriptionLifecycleEventV1, ...]
    exact_duplicate_raw_event_ids: tuple[str, ...]


def validate_raw_lifecycle_identity_batch(events):
    if len(events) > MAX_LIFECYCLE_EVENTS_PER_BATCH:
        raise ValueError("too_many_lifecycle_events")
    by_id = {}
    duplicates = set()
    for event in events:
        existing = by_id.get(event.raw_event_id)
        if existing is not None:
            if existing != event:
                raise ConflictingRawIdentityError(event.raw_event_id)
            duplicates.add(event.raw_event_id)
        else:
            by_id[event.raw_event_id] = event
    return RawLifecycleIdentityBatchValidationV1(
        tuple(by_id.values()),
        tuple(sorted(duplicates)),
    )


def _validate_common(event) -> None:
    validate_opaque_identifier(event.provider, "provider")
    validate_opaque_identifier(event.connection_session_id, "connection_session_id")
    validate_opaque_identifier(event.source_order_scope_id, "source_order_scope_id")
    validate_source_order(event.source_order)
    for name in ("occurred_at", "available_at", "recorded_at"):
        object.__setattr__(event, name, _utc(getattr(event, name), name))
    if event.available_at < event.occurred_at:
        raise ValueError("available_at cannot precede occurred_at")
    if event.recorded_at < event.available_at:
        raise ValueError("recorded_at cannot precede available_at")
    if event.provider_sequence is not None:
        raise ValueError("provider_sequence must be absent")


def _apply_raw_canonical_values(event, raw) -> None:
    for name in (
        "previous_state",
        "state",
        "occurred_at",
        "available_at",
        "recorded_at",
        "provider_sequence",
    ):
        object.__setattr__(event, name, getattr(raw, name))
    if isinstance(raw, RawProviderSubscriptionLifecycleEventV1):
        object.__setattr__(event, "request_mode", raw.request_mode)
        object.__setattr__(event, "instrument_set", raw.instrument_set)
        object.__setattr__(event, "instrument_keys_digest", raw.instrument_keys_digest)
        object.__setattr__(event, "instrument_key_count", raw.instrument_key_count)


def _subscription_modes_agree(previous, current) -> bool:
    if current.state in {
        SubscriptionLifecycleState.SUBSCRIBED,
        SubscriptionLifecycleState.MODE_CHANGED,
        SubscriptionLifecycleState.SUBSCRIPTION_FAILED,
    }:
        return current.request_mode == previous.request_mode
    if current.state is SubscriptionLifecycleState.UNSUBSCRIBED:
        return current.request_mode == previous.request_mode
    if current.state is SubscriptionLifecycleState.UNSUBSCRIBE_REQUESTED:
        return current.request_mode is None or previous.request_mode is None or current.request_mode == previous.request_mode
    return True


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
    if value is not None:
        validate_redacted_reason_code_size(value)
        if _CONTROLLED_REASON.fullmatch(value) is None or any(part in value for part in _SENSITIVE_REASON_PARTS):
            raise ValueError("redacted_reason_code must be controlled and redacted")


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("lifecycle text values must be non-empty")


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
