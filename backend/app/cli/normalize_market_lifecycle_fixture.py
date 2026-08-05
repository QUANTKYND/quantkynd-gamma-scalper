from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.core.hashing import canonical_json, stable_hash
from app.market_data.normalization.errors import ConflictingRawIdentityError
from app.market_data.normalization.lifecycle import (
    ConnectionLifecycleState,
    RawProviderConnectionLifecycleEventV1,
    RawProviderSubscriptionLifecycleEventV1,
    SubscriptionLifecycleState,
    normalize_connection_lifecycle,
    normalize_subscription_lifecycle,
    validate_connection_lifecycle_sequence,
    validate_raw_lifecycle_identity_batch,
    validate_subscription_lifecycle_sequence,
)
from app.market_data.normalization.enums import ProviderRequestMode
from app.market_data.normalization.serialization import canonical_normalization_json


LIFECYCLE_FIXTURE_SCHEMA_VERSION = "data-1.3-lifecycle-fixture-v1"


class LifecycleFixtureConfigurationError(ValueError):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize one deterministic provider lifecycle fixture")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", choices=("json",), default="json")
    return parser


def run(argv: list[str] | None = None) -> tuple[int, str]:
    try:
        args = _parser().parse_args(argv)
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        kind, items = _validate_fixture(payload)
        if kind == "connection":
            raw = tuple(_connection(item) for item in items)
            identity_batch = validate_raw_lifecycle_identity_batch(raw)
            validate_connection_lifecycle_sequence(identity_batch.unique_events)
            normalized = tuple(normalize_connection_lifecycle(item) for item in identity_batch.unique_events)
            validate_connection_lifecycle_sequence(normalized)
        else:
            raw = tuple(_subscription(item) for item in items)
            identity_batch = validate_raw_lifecycle_identity_batch(raw)
            validate_subscription_lifecycle_sequence(identity_batch.unique_events)
            normalized = tuple(normalize_subscription_lifecycle(item) for item in identity_batch.unique_events)
            validate_subscription_lifecycle_sequence(normalized)
    except (OSError, json.JSONDecodeError, LifecycleFixtureConfigurationError):
        return 2, canonical_json({"error": "lifecycle_fixture_configuration_error"})
    except ConflictingRawIdentityError:
        return 1, canonical_json({"error": "raw_identity_conflict"})
    except ValueError as error:
        reason = str(error)
        controlled = reason if reason.replace("_", "").isalnum() else "invalid_lifecycle_fixture"
        return 1, canonical_json({"error": controlled})
    normalized_payload = json.loads(canonical_normalization_json(normalized))
    result = {
        "fixture_schema_version": LIFECYCLE_FIXTURE_SCHEMA_VERSION,
        "lifecycle_kind": kind,
        "events": normalized_payload,
        "exact_duplicate_raw_event_ids": identity_batch.exact_duplicate_raw_event_ids,
        "normalized_sequence_hash": stable_hash(normalized_payload),
    }
    return 0, canonical_json(result)


def _connection(item):
    return RawProviderConnectionLifecycleEventV1(
        provider=item["provider"],
        connection_session_id=item["connection_session_id"],
        previous_state=item.get("previous_state"),
        state=item["state"],
        source_order_scope_id=item["source_order_scope_id"],
        source_order=_integer(item, "source_order"),
        occurred_at=_datetime(item["occurred_at"]),
        available_at=_datetime(item["available_at"]),
        recorded_at=_datetime(item["recorded_at"]),
        redacted_reason_code=item.get("redacted_reason_code"),
    )


def _subscription(item):
    from app.market_data.normalization.lifecycle import SubscriptionInstrumentSetV1

    instrument_set = SubscriptionInstrumentSetV1(tuple(item["provider_contract_keys"]))
    return RawProviderSubscriptionLifecycleEventV1(
        provider=item["provider"],
        connection_session_id=item["connection_session_id"],
        subscription_scope_id=item["subscription_scope_id"],
        previous_state=item.get("previous_state"),
        state=item["state"],
        source_order_scope_id=item["source_order_scope_id"],
        source_order=_integer(item, "source_order"),
        occurred_at=_datetime(item["occurred_at"]),
        available_at=_datetime(item["available_at"]),
        recorded_at=_datetime(item["recorded_at"]),
        request_mode=item.get("request_mode"),
        instrument_set=instrument_set,
        redacted_reason_code=item.get("redacted_reason_code"),
    )


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("lifecycle timestamp must be timezone-aware")
    return parsed


def _integer(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _validate_fixture(payload) -> tuple[str, list[dict]]:
    if not isinstance(payload, dict):
        raise LifecycleFixtureConfigurationError("fixture must be an object")
    if payload.get("fixture_schema_version") != LIFECYCLE_FIXTURE_SCHEMA_VERSION:
        raise LifecycleFixtureConfigurationError("unsupported fixture schema")
    kind = payload.get("lifecycle_kind")
    if kind not in {"connection", "subscription"}:
        raise LifecycleFixtureConfigurationError("unsupported lifecycle kind")
    items = payload.get("events")
    if not isinstance(items, list):
        raise LifecycleFixtureConfigurationError("events must be an array")
    for item in items:
        _validate_event(item, kind)
    return kind, items


def _validate_event(item, kind: str) -> None:
    if not isinstance(item, dict):
        raise LifecycleFixtureConfigurationError("event must be an object")
    required_text = (
        "provider",
        "connection_session_id",
        "state",
        "source_order_scope_id",
        "occurred_at",
        "available_at",
        "recorded_at",
    )
    if kind == "subscription":
        required_text += ("subscription_scope_id",)
    for key in required_text:
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise LifecycleFixtureConfigurationError(f"{key} must be non-empty text")
    if "previous_state" not in item or (item["previous_state"] is not None and not isinstance(item["previous_state"], str)):
        raise LifecycleFixtureConfigurationError("previous_state must be null or text")
    if not isinstance(item.get("source_order"), int) or isinstance(item["source_order"], bool):
        raise LifecycleFixtureConfigurationError("source_order must be an integer")
    for key in ("occurred_at", "available_at", "recorded_at"):
        try:
            _datetime(item[key])
        except (TypeError, AttributeError, ValueError) as error:
            raise LifecycleFixtureConfigurationError(f"{key} must be a timezone-aware timestamp") from error
    reason = item.get("redacted_reason_code")
    if reason is not None and not isinstance(reason, str):
        raise LifecycleFixtureConfigurationError("redacted_reason_code must be null or text")
    if kind == "subscription":
        keys = item.get("provider_contract_keys")
        if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or not key.strip() for key in keys):
            raise LifecycleFixtureConfigurationError("provider_contract_keys must be an array of strings")
        if "request_mode" not in item or (item["request_mode"] is not None and not isinstance(item["request_mode"], str)):
            raise LifecycleFixtureConfigurationError("request_mode must be null or text")
        try:
            SubscriptionLifecycleState(item["state"])
            if item["previous_state"] is not None:
                SubscriptionLifecycleState(item["previous_state"])
            if item["request_mode"] is not None:
                ProviderRequestMode(item["request_mode"])
        except ValueError as error:
            raise LifecycleFixtureConfigurationError("invalid subscription enum value") from error
    else:
        try:
            ConnectionLifecycleState(item["state"])
            if item["previous_state"] is not None:
                ConnectionLifecycleState(item["previous_state"])
        except ValueError as error:
            raise LifecycleFixtureConfigurationError("invalid connection enum value") from error


def main(argv: list[str] | None = None) -> int:
    code, output = run(argv)
    (sys.stdout if code == 0 else sys.stderr).write(output + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
