from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.core.hashing import canonical_json, stable_hash
from app.market_data.normalization.errors import ConflictingRawIdentityError
from app.market_data.normalization.lifecycle import (
    RawProviderConnectionLifecycleEventV1,
    RawProviderSubscriptionLifecycleEventV1,
    normalize_connection_lifecycle,
    normalize_subscription_lifecycle,
    validate_connection_lifecycle_sequence,
    validate_raw_lifecycle_identity_batch,
    validate_subscription_lifecycle_sequence,
)
from app.market_data.normalization.serialization import canonical_normalization_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize one deterministic provider lifecycle fixture")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", choices=("json",), default="json")
    return parser


def run(argv: list[str] | None = None) -> tuple[int, str]:
    try:
        args = _parser().parse_args(argv)
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        kind = payload["lifecycle_kind"]
        if kind == "connection":
            raw = tuple(_connection(item) for item in payload["events"])
            identity_batch = validate_raw_lifecycle_identity_batch(raw)
            validate_connection_lifecycle_sequence(raw)
            normalized = tuple(normalize_connection_lifecycle(item) for item in raw)
            validate_connection_lifecycle_sequence(normalized)
        elif kind == "subscription":
            raw = tuple(_subscription(item) for item in payload["events"])
            identity_batch = validate_raw_lifecycle_identity_batch(raw)
            validate_subscription_lifecycle_sequence(raw)
            normalized = tuple(normalize_subscription_lifecycle(item) for item in raw)
            validate_subscription_lifecycle_sequence(normalized)
        else:
            raise KeyError("unsupported lifecycle kind")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return 2, canonical_json({"error": "lifecycle_fixture_configuration_error"})
    except ConflictingRawIdentityError:
        return 1, canonical_json({"error": "raw_identity_conflict"})
    except ValueError as error:
        reason = str(error)
        controlled = reason if reason.replace("_", "").isalnum() else "invalid_lifecycle_fixture"
        return 1, canonical_json({"error": controlled})
    normalized_payload = json.loads(canonical_normalization_json(normalized))
    result = {
        "fixture_schema_version": payload.get("fixture_schema_version"),
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


def main(argv: list[str] | None = None) -> int:
    code, output = run(argv)
    (sys.stdout if code == 0 else sys.stderr).write(output + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
