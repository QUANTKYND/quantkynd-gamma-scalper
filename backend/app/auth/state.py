"""Signed one-time OAuth state tokens."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


DEFAULT_STATE_TTL_SECONDS = 600

_nonce_lock = threading.Lock()
_nonces: dict[str, int] = {}


@dataclass(frozen=True)
class StateValidationResult:
    valid: bool
    reason: str | None = None


def generate_state(ttl_seconds: int = DEFAULT_STATE_TTL_SECONDS) -> str:
    """Generate a signed, short-lived, one-time OAuth state token."""

    now = int(time.time())
    expires_at = now + ttl_seconds
    nonce = secrets.token_urlsafe(24)
    payload = {"nonce": nonce, "iat": now, "exp": expires_at}
    encoded_payload = _b64encode(_json_bytes(payload))
    signature = _sign(encoded_payload)

    with _nonce_lock:
        _purge_expired_nonces(now)
        _nonces[nonce] = expires_at

    return f"{encoded_payload}.{signature}"


def verify_state(state: str) -> bool:
    return validate_state(state).valid


def validate_state(state: str) -> StateValidationResult:
    now = int(time.time())

    if not state:
        return StateValidationResult(valid=False, reason="missing_state")

    try:
        encoded_payload, signature = state.split(".", maxsplit=1)
    except ValueError:
        return StateValidationResult(valid=False, reason="invalid_state")

    expected_signature = _sign(encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        return StateValidationResult(valid=False, reason="invalid_state")

    try:
        payload = _decode_payload(encoded_payload)
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return StateValidationResult(valid=False, reason="invalid_state")

    nonce = payload.get("nonce")
    expires_at = payload.get("exp")
    if not isinstance(nonce, str) or not isinstance(expires_at, int):
        return StateValidationResult(valid=False, reason="invalid_state")

    if expires_at <= now:
        with _nonce_lock:
            _nonces.pop(nonce, None)
        return StateValidationResult(valid=False, reason="expired_auth_flow")

    with _nonce_lock:
        _purge_expired_nonces(now)
        stored_expires_at = _nonces.pop(nonce, None)

    if stored_expires_at is None:
        return StateValidationResult(valid=False, reason="state_replayed")
    if stored_expires_at <= now:
        return StateValidationResult(valid=False, reason="expired_auth_flow")

    return StateValidationResult(valid=True)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _decode_payload(encoded_payload: str) -> dict[str, Any]:
    raw = _b64decode(encoded_payload)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("state payload must be an object")
    return payload


def _sign(encoded_payload: str) -> str:
    digest = hmac.new(
        settings.upstox_state_signing_secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _purge_expired_nonces(now: int) -> None:
    expired = [nonce for nonce, expires_at in _nonces.items() if expires_at <= now]
    for nonce in expired:
        _nonces.pop(nonce, None)
