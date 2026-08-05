from __future__ import annotations


MAX_SOURCE_ORDER = 2**63 - 1
MAX_OPAQUE_IDENTIFIER_BYTES = 512
MAX_REDACTED_REASON_CODE_BYTES = 128
MAX_LIFECYCLE_FIXTURE_BYTES = 16 * 1024 * 1024
MAX_LIFECYCLE_EVENTS_PER_BATCH = 10_000


def validate_source_order(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_SOURCE_ORDER:
        raise ValueError("source_order must be an integer in the signed 64-bit range")
    return value


def validate_opaque_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field_name} must be valid UTF-8 text") from error
    if len(encoded) > MAX_OPAQUE_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} exceeds the UTF-8 byte limit")
    return value


def validate_redacted_reason_code_size(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("redacted_reason_code must be text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("redacted_reason_code must be valid UTF-8 text") from error
    if len(encoded) > MAX_REDACTED_REASON_CODE_BYTES:
        raise ValueError("redacted_reason_code exceeds the UTF-8 byte limit")
    return value
