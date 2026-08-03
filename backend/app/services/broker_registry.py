"""Broker connector registry."""

from __future__ import annotations

from app.auth.upstox import UpstoxConnector
from app.core.config import settings


BROKER_CONNECTORS = {
    "upstox": UpstoxConnector(),
}


def get_broker_connector(name: str | None = None) -> UpstoxConnector:
    broker_name = (name or settings.broker).lower()
    connector = BROKER_CONNECTORS.get(broker_name)
    if connector is None:
        raise KeyError(f"unsupported broker: {broker_name}")
    return connector
