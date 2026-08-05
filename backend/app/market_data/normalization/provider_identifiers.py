from __future__ import annotations


MAX_PROVIDER_CONTRACT_KEY_BYTES = 512
MAX_MARKET_SEGMENT_BYTES = 128


def validate_provider_contract_key(value: object) -> str:
    return _validate_provider_identifier(value, MAX_PROVIDER_CONTRACT_KEY_BYTES, "provider contract key")


def validate_market_segment(value: object) -> str:
    return _validate_provider_identifier(value, MAX_MARKET_SEGMENT_BYTES, "market segment")


def _validate_provider_identifier(value: object, maximum_bytes: int, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"invalid {name}")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"invalid {name}")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"invalid {name}") from error
    if len(encoded) > maximum_bytes:
        raise ValueError(f"invalid {name}")
    return value
