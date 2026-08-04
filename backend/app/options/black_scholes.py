from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from app.options.contracts import OptionType


NORMAL = NormalDist()
SQRT_TWO_PI = math.sqrt(2 * math.pi)


@dataclass(frozen=True)
class OptionGreeks:
    delta: float
    gamma: float
    theta_per_year: float
    vega_per_unit_volatility: float
    rho_per_unit_rate: float


@dataclass(frozen=True)
class OptionValuation:
    price: float
    intrinsic_value: float
    time_value: float
    greeks: OptionGreeks


def price(
    option_type: OptionType,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    volatility: float,
) -> float:
    return value(
        option_type,
        spot,
        strike,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        volatility,
    ).price


def value(
    option_type: OptionType,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    volatility: float,
) -> OptionValuation:
    _validate(option_type, spot, strike, time_to_expiry_years, volatility)
    intrinsic = intrinsic_value(option_type, spot, strike)
    if time_to_expiry_years == 0:
        delta = _expiry_delta(option_type, spot, strike)
        return OptionValuation(intrinsic, intrinsic, 0.0, OptionGreeks(delta, 0.0, 0.0, 0.0, 0.0))
    if volatility == 0:
        return _zero_volatility_value(
            option_type, spot, strike, time_to_expiry_years, risk_free_rate, dividend_yield, intrinsic
        )
    sqrt_time = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility)
        * time_to_expiry_years
    ) / (volatility * sqrt_time)
    d2 = d1 - volatility * sqrt_time
    spot_discount = math.exp(-dividend_yield * time_to_expiry_years)
    strike_discount = math.exp(-risk_free_rate * time_to_expiry_years)
    pdf_d1 = math.exp(-0.5 * d1 * d1) / SQRT_TWO_PI
    if option_type == "call":
        option_price = spot * spot_discount * NORMAL.cdf(d1) - strike * strike_discount * NORMAL.cdf(d2)
        delta = spot_discount * NORMAL.cdf(d1)
        theta = (
            -(spot * spot_discount * pdf_d1 * volatility) / (2 * sqrt_time)
            - risk_free_rate * strike * strike_discount * NORMAL.cdf(d2)
            + dividend_yield * spot * spot_discount * NORMAL.cdf(d1)
        )
        rho = strike * time_to_expiry_years * strike_discount * NORMAL.cdf(d2)
    else:
        option_price = strike * strike_discount * NORMAL.cdf(-d2) - spot * spot_discount * NORMAL.cdf(-d1)
        delta = spot_discount * (NORMAL.cdf(d1) - 1)
        theta = (
            -(spot * spot_discount * pdf_d1 * volatility) / (2 * sqrt_time)
            + risk_free_rate * strike * strike_discount * NORMAL.cdf(-d2)
            - dividend_yield * spot * spot_discount * NORMAL.cdf(-d1)
        )
        rho = -strike * time_to_expiry_years * strike_discount * NORMAL.cdf(-d2)
    gamma = spot_discount * pdf_d1 / (spot * volatility * sqrt_time)
    vega = spot * spot_discount * pdf_d1 * sqrt_time
    return OptionValuation(
        price=max(option_price, 0.0),
        intrinsic_value=intrinsic,
        time_value=option_price - intrinsic,
        greeks=OptionGreeks(delta, gamma, theta, vega, rho),
    )


def call_price(*args: float) -> float:
    return price("call", *args)


def put_price(*args: float) -> float:
    return price("put", *args)


def intrinsic_value(option_type: OptionType, spot: float, strike: float) -> float:
    _validate(option_type, spot, strike, 0.0, 0.0)
    return max(spot - strike, 0.0) if option_type == "call" else max(strike - spot, 0.0)


def time_value(option_type: OptionType, *args: float) -> float:
    return value(option_type, *args).time_value


def _zero_volatility_value(
    option_type: OptionType,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    intrinsic: float,
) -> OptionValuation:
    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry_years)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry_years)
    forward_difference = discounted_spot - discounted_strike
    in_money = forward_difference > 0 if option_type == "call" else forward_difference < 0
    option_price = max(forward_difference, 0.0) if option_type == "call" else max(-forward_difference, 0.0)
    if in_money:
        delta = math.exp(-dividend_yield * time_to_expiry_years) * (1 if option_type == "call" else -1)
        if option_type == "call":
            theta = dividend_yield * discounted_spot - risk_free_rate * discounted_strike
            rho = time_to_expiry_years * discounted_strike
        else:
            theta = risk_free_rate * discounted_strike - dividend_yield * discounted_spot
            rho = -time_to_expiry_years * discounted_strike
    else:
        delta = theta = rho = 0.0
    return OptionValuation(option_price, intrinsic, option_price - intrinsic, OptionGreeks(delta, 0.0, theta, 0.0, rho))


def _expiry_delta(option_type: OptionType, spot: float, strike: float) -> float:
    if spot == strike:
        return 0.5 if option_type == "call" else -0.5
    if option_type == "call":
        return 1.0 if spot > strike else 0.0
    return -1.0 if spot < strike else 0.0


def _validate(
    option_type: str,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
) -> None:
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be call or put")
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("spot must be positive and finite")
    if not math.isfinite(strike) or strike <= 0:
        raise ValueError("strike must be positive and finite")
    if not math.isfinite(time_to_expiry_years) or time_to_expiry_years < 0:
        raise ValueError("time to expiry must be non-negative and finite")
    if not math.isfinite(volatility) or volatility < 0:
        raise ValueError("volatility must be non-negative and finite")
