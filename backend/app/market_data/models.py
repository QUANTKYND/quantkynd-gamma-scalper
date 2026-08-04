from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd


TransportState = Literal["idle", "auth_missing", "connecting", "connected", "reconnecting", "disconnected", "failed", "stopping"]
SubscriptionState = Literal["unsubscribed", "subscribing", "subscribed", "rejected"]
FreshnessState = Literal["awaiting_first_tick", "fresh", "stale", "unknown"]


@dataclass(frozen=True)
class HistoricalCloseDataset:
    instrument_key: str
    prices: pd.Series
    source: Literal["upstox_historical"] = "upstox_historical"

    @property
    def start_date(self) -> date:
        return pd.Timestamp(self.prices.index[0]).date()

    @property
    def end_date(self) -> date:
        return pd.Timestamp(self.prices.index[-1]).date()


@dataclass(frozen=True)
class LiveQuoteState:
    instrument_key: str
    ltp: float
    previous_close: float | None
    last_trade_quantity: int | None
    last_trade_at: datetime
    provider_message_at: datetime
    received_at: datetime
    processed_at: datetime
    market_status: str | None
    sequence: int


@dataclass(frozen=True)
class MarketDataStatus:
    authentication_state: str
    transport_state: TransportState
    subscription_state: SubscriptionState
    market_status: str | None
    active_instrument_keys: tuple[str, ...]
    connected_at: datetime | None
    last_message_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    reconnect_attempt: int
