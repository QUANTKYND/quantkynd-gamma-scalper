from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class MarketState:
    timestamp: datetime
    session_index: int
    step_index: int
    spot: float
    futures_price: float
    risk_free_rate: float
    dividend_yield: float
    implied_volatility: float
    time_to_expiry_years: float
    step_year_fraction: float
    session_date: date | None = None
    local_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("market-state timestamp must be timezone-aware")
        if self.local_timestamp is not None and self.local_timestamp.tzinfo is None:
            raise ValueError("market-state local timestamp must be timezone-aware")
        if self.session_index < 0 or self.step_index < 0:
            raise ValueError("market-state indexes must be non-negative")
        finite = (
            self.spot,
            self.futures_price,
            self.risk_free_rate,
            self.dividend_yield,
            self.implied_volatility,
            self.time_to_expiry_years,
            self.step_year_fraction,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ValueError("market-state values must be finite")
        if self.spot <= 0 or self.futures_price <= 0:
            raise ValueError("market prices must be positive")
        if self.implied_volatility < 0 or self.time_to_expiry_years < 0:
            raise ValueError("volatility and time to expiry must be non-negative")
        if self.step_year_fraction < 0:
            raise ValueError("step year fraction must be non-negative")


def carry_futures_price(
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    maturity_years: float,
) -> float:
    if spot <= 0 or maturity_years < 0:
        raise ValueError("spot must be positive and maturity non-negative")
    return spot * math.exp((risk_free_rate - dividend_yield) * maturity_years)
