from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from app.options.contracts import OptionContract
from app.strategy.models import ExpirySelectionConfig


@dataclass(frozen=True)
class SyntheticOptionPair:
    strike: float
    call: OptionContract
    put: OptionContract
    combined_relative_spread: float
    combined_volume: int
    combined_open_interest: int


def select_expiry(remaining_sessions_by_expiry: dict[date, int], config: ExpirySelectionConfig) -> date:
    eligible = [
        expiry
        for expiry, sessions in remaining_sessions_by_expiry.items()
        if config.minimum_remaining_sessions <= sessions <= config.maximum_remaining_sessions
    ]
    if not eligible:
        raise ValueError("no eligible expiry")
    return min(eligible)


def continuous_forward(spot: float, risk_free_rate: float, dividend_yield: float, time_years: float) -> float:
    if spot <= 0 or time_years < 0:
        raise ValueError("spot must be positive and time non-negative")
    return spot * math.exp((risk_free_rate - dividend_yield) * time_years)


def synthetic_chain(
    underlying: str,
    forward: float,
    strike_interval: float,
    strikes_below: int,
    strikes_above: int,
    expiry: date,
    multiplier: int,
) -> tuple[SyntheticOptionPair, ...]:
    if forward <= 0 or strike_interval <= 0 or strikes_below < 0 or strikes_above < 0:
        raise ValueError("synthetic-chain parameters are invalid")
    center = round(forward / strike_interval) * strike_interval
    strikes = [center + offset * strike_interval for offset in range(-strikes_below, strikes_above + 1)]
    return tuple(
        SyntheticOptionPair(
            strike=strike,
            call=OptionContract(f"{underlying}-{expiry}-C-{strike:g}", underlying, "call", strike, expiry, multiplier),
            put=OptionContract(f"{underlying}-{expiry}-P-{strike:g}", underlying, "put", strike, expiry, multiplier),
            combined_relative_spread=0.02,
            combined_volume=1000,
            combined_open_interest=5000,
        )
        for strike in strikes
        if strike > 0
    )


def select_straddle(chain: tuple[SyntheticOptionPair, ...], forward: float) -> SyntheticOptionPair:
    if not chain:
        raise ValueError("option chain is empty")
    return min(
        chain,
        key=lambda pair: (
            abs(pair.strike - forward),
            pair.combined_relative_spread,
            -pair.combined_volume,
            -pair.combined_open_interest,
            pair.strike,
        ),
    )
