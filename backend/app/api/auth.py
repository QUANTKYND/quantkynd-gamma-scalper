"""Broker authentication API routes."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse

from app.auth.state import generate_state, validate_state as validate_state_payload
from app.auth.token_store import TokenStoreError, token_store
from app.auth.upstox import UpstoxAuthError
from app.core.config import settings
from app.schemas.auth import AuthDisconnectResponse, AuthStatusResponse
from app.services.broker_registry import get_broker_connector
from app.services.connection_state import connection_state


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/upstox/login", status_code=status.HTTP_302_FOUND)
def upstox_login() -> RedirectResponse:
    state = generate_state()
    authorize_url = get_broker_connector("upstox").build_authorize_url(state)
    return RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)


@router.get("/upstox/callback", status_code=status.HTTP_302_FOUND)
def upstox_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    if error:
        return _redirect_to_frontend(auth="error", reason=error)
    if not code:
        return _redirect_to_frontend(auth="error", reason="missing_code")
    if not state:
        return _redirect_to_frontend(auth="error", reason="missing_state")

    state_result = validate_state_payload(state)
    if not state_result.valid:
        return _redirect_to_frontend(auth="error", reason=state_result.reason or "invalid_state")

    connector = get_broker_connector("upstox")
    try:
        token = connector.exchange_code_for_token(code)
    except UpstoxAuthError as exc:
        return _redirect_to_frontend(auth="error", reason=exc.reason)

    try:
        token_store.save_token(token)
    except TokenStoreError:
        return _redirect_to_frontend(auth="error", reason="token_save_failed")

    connection_state.set_connected("upstox")
    return _redirect_to_frontend(auth="success")


@router.get("/status", response_model=AuthStatusResponse)
def auth_status() -> AuthStatusResponse:
    broker = "upstox"
    if token_store.load_error:
        return AuthStatusResponse(
            broker=broker,
            status="error",
            connected=False,
            error="saved token could not be loaded",
        )

    if token_store.is_connected():
        connection_state.set_connected(broker)
        return AuthStatusResponse(
            broker=broker,
            status="connected",
            connected=True,
            profile=token_store.get_public_profile(),
        )

    connection_state.clear()
    return AuthStatusResponse(broker=broker, status="disconnected", connected=False)


@router.post("/disconnect", response_model=AuthDisconnectResponse)
def disconnect() -> AuthDisconnectResponse:
    token_store.delete_token()
    connection_state.clear()
    return AuthDisconnectResponse(broker="upstox", status="disconnected", connected=False)


def _redirect_to_frontend(*, auth: str, reason: str | None = None) -> RedirectResponse:
    params = {"auth": auth}
    if reason:
        params["reason"] = reason
    return RedirectResponse(_frontend_url_with_params(params), status_code=status.HTTP_302_FOUND)


def _frontend_url_with_params(params: dict[str, str]) -> str:
    split_url = urlsplit(settings.front_url)
    query = dict(parse_qsl(split_url.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit(
        (
            split_url.scheme,
            split_url.netloc,
            split_url.path or "/",
            urlencode(query),
            split_url.fragment,
        )
    )
