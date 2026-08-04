from __future__ import annotations

import math
from dataclasses import dataclass

from app.options.black_scholes import price
from app.options.contracts import OptionType


@dataclass(frozen=True)
class ImpliedVolatilityResult:
    implied_volatility: float | None
    converged: bool
    iterations: int
    final_price_error: float


def solve_implied_volatility(
    option_type: OptionType,
    observed_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    lower_volatility: float = 0.0,
    upper_volatility: float = 5.0,
    price_tolerance: float = 1e-8,
    maximum_iterations: int = 200,
) -> ImpliedVolatilityResult:
    if not math.isfinite(observed_price) or observed_price < 0:
        raise ValueError("observed price must be non-negative and finite")
    if lower_volatility < 0 or upper_volatility <= lower_volatility:
        raise ValueError("volatility bounds are invalid")
    if price_tolerance <= 0 or maximum_iterations < 0:
        raise ValueError("solver tolerance and iteration count are invalid")
    lower_price = price(
        option_type, spot, strike, time_to_expiry_years, risk_free_rate, dividend_yield, 0.0
    )
    upper_static = (
        spot * math.exp(-dividend_yield * time_to_expiry_years)
        if option_type == "call"
        else strike * math.exp(-risk_free_rate * time_to_expiry_years)
    )
    if observed_price < lower_price - price_tolerance or observed_price > upper_static + price_tolerance:
        raise ValueError("observed price violates static no-arbitrage bounds")
    if abs(observed_price - lower_price) <= price_tolerance:
        return ImpliedVolatilityResult(0.0, True, 0, lower_price - observed_price)
    low = lower_volatility
    high = upper_volatility
    low_error = price(option_type, spot, strike, time_to_expiry_years, risk_free_rate, dividend_yield, low) - observed_price
    high_error = price(option_type, spot, strike, time_to_expiry_years, risk_free_rate, dividend_yield, high) - observed_price
    if low_error > 0 or high_error < 0:
        return ImpliedVolatilityResult(None, False, 0, min(abs(low_error), abs(high_error)))
    error = low_error
    midpoint = low
    for iteration in range(1, maximum_iterations + 1):
        midpoint = (low + high) / 2
        error = price(
            option_type, spot, strike, time_to_expiry_years, risk_free_rate, dividend_yield, midpoint
        ) - observed_price
        if abs(error) <= price_tolerance:
            return ImpliedVolatilityResult(midpoint, True, iteration, error)
        if error < 0:
            low = midpoint
        else:
            high = midpoint
    return ImpliedVolatilityResult(midpoint if maximum_iterations else None, False, maximum_iterations, error)
