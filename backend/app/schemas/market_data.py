from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketDataStatusResponse(ApiModel):
    provider: Literal["upstox"] = "upstox"
    authentication_state: str
    transport_state: str
    subscription_state: str
    feed_quality: str
    market_status: str | None
    active_instrument_keys: list[str]
    connected_at: datetime | None
    last_message_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    reconnect_attempt: int
    counters: dict[str, int]
    browser_clients: int
    active_instruments: int


class LiveQuoteResponse(ApiModel):
    provider: Literal["upstox"] = "upstox"
    instrument_key: str
    status: Literal["awaiting_first_tick", "available"]
    freshness: Literal["awaiting_first_tick", "fresh", "stale", "unknown"]
    ltp: float | None
    previous_close: float | None
    absolute_change: float | None
    percentage_change: float | None
    last_trade_quantity: int | None
    last_trade_at: datetime | None
    provider_message_at: datetime | None
    received_at: datetime | None
    processed_at: datetime | None
    market_status: str | None
    sequence: int | None


class MarketStreamEnvelope(ApiModel):
    version: Literal[1] = 1
    stream: Literal["market-state"] = "market-state"
    sequence: int
    occurred_at: datetime
    event_type: Literal[
        "market_state_snapshot",
        "feed_status_changed",
        "market_status_changed",
        "quote_updated",
        "rv_provisional_updated",
        "resync_required",
        "provider_error",
    ]
    entity_id: str
    payload: dict[str, Any]
