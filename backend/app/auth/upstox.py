"""Upstox OAuth connector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.state import verify_state
from app.core.config import settings


class UpstoxAuthError(RuntimeError):
    def __init__(self, message: str, *, reason: str = "token_exchange_failed") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class UpstoxConnector:
    name: str = "upstox"
    display_name: str = "Upstox"

    def build_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.upstox_client_id,
            "redirect_uri": settings.upstox_redirect_uri,
            "state": state,
        }
        return f"{settings.upstox_login_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        data = {
            "code": code,
            "client_id": settings.upstox_client_id,
            "client_secret": settings.upstox_client_secret,
            "redirect_uri": settings.upstox_redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = httpx.post(
                settings.upstox_token_url,
                data=data,
                headers=headers,
                timeout=15.0,
            )
        except httpx.RequestError as exc:
            raise UpstoxAuthError(str(exc), reason="token_endpoint_unreachable") from exc

        if response.status_code >= 400:
            reason, message = _parse_upstox_error(response)
            raise UpstoxAuthError(message, reason=reason)

        try:
            token = response.json()
        except ValueError as exc:
            raise UpstoxAuthError("token endpoint returned invalid JSON") from exc

        if not isinstance(token, dict) or not token.get("access_token"):
            raise UpstoxAuthError("token endpoint did not return an access token")

        return token

    def fetch_user_profile(self, access_token: str) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        try:
            response = httpx.get(
                "https://api.upstox.com/v2/user/profile",
                headers=headers,
                timeout=15.0,
            )
        except httpx.RequestError as exc:
            raise UpstoxAuthError(str(exc), reason="profile_fetch_failed") from exc

        if response.status_code >= 400:
            reason, message = _parse_upstox_error(response)
            raise UpstoxAuthError(message, reason=reason)

        try:
            profile = response.json()
        except ValueError as exc:
            raise UpstoxAuthError("profile endpoint returned invalid JSON", reason="profile_fetch_failed") from exc

        if not isinstance(profile, dict):
            raise UpstoxAuthError("profile endpoint returned an unexpected payload", reason="profile_fetch_failed")

        return profile

    def validate_state(self, state: str) -> bool:
        return verify_state(state)


def build_authorize_url(state: str) -> str:
    return UpstoxConnector().build_authorize_url(state)


def exchange_code_for_token(code: str) -> dict[str, Any]:
    return UpstoxConnector().exchange_code_for_token(code)


def fetch_user_profile(access_token: str) -> dict[str, Any]:
    return UpstoxConnector().fetch_user_profile(access_token)


def validate_state(state: str) -> bool:
    return UpstoxConnector().validate_state(state)


def _parse_upstox_error(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except ValueError:
        return "token_exchange_failed", f"Upstox token exchange failed with HTTP {response.status_code}"

    code = _find_error_code(payload)
    message = _find_error_message(payload) or f"Upstox request failed with HTTP {response.status_code}"
    reason_by_code = {
        "UDAPI100057": "invalid_auth_code",
        "UDAPI100068": "client_or_redirect_uri_invalid",
        "UDAPI100069": "client_credentials_invalid",
        "UDAPI100070": "redirect_uri_mismatch",
    }
    return reason_by_code.get(code, "token_exchange_failed"), message


def _find_error_code(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("errorCode", "error_code", "code"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        errors = payload.get("errors")
        if isinstance(errors, list):
            for error in errors:
                code = _find_error_code(error)
                if code:
                    return code
    return None


def _find_error_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("message", "error", "error_description"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        errors = payload.get("errors")
        if isinstance(errors, list):
            for error in errors:
                message = _find_error_message(error)
                if message:
                    return message
    return None
