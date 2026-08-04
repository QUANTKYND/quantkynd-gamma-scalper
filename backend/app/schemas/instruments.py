from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InstrumentDefinition(ApiModel):
    instrument_key: str
    exchange: Literal["NSE", "BSE"]
    segment: Literal["NSE_INDEX", "BSE_INDEX", "NSE_EQ", "BSE_EQ"]
    kind: Literal["index", "equity"]
    name: str
    short_name: str | None
    trading_symbol: str
    isin: str | None
    tick_size: float | None
    lot_size: int


class InstrumentSearchResponse(ApiModel):
    query: str
    provider: Literal["upstox"] = "upstox"
    items: list[InstrumentDefinition]
    received_at: datetime
