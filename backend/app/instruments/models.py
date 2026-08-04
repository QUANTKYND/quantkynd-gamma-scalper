from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InstrumentKind = Literal["index", "equity"]


@dataclass(frozen=True)
class InstrumentDefinition:
    instrument_key: str
    exchange: Literal["NSE", "BSE"]
    segment: Literal["NSE_INDEX", "BSE_INDEX", "NSE_EQ", "BSE_EQ"]
    kind: InstrumentKind
    name: str
    short_name: str | None
    trading_symbol: str
    isin: str | None
    tick_size: float | None
    lot_size: int
