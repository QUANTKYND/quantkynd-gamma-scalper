"""Stable API contracts for broker authentication."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class AuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthStatusResponse(AuthModel):
    broker: str
    status: Literal["connected", "disconnected", "error"]
    connected: bool
    profile: dict[str, Any] | None = None
    error: str | None = None


class AuthDisconnectResponse(AuthModel):
    broker: str
    status: Literal["disconnected"]
    connected: Literal[False]
