from __future__ import annotations

import math
from dataclasses import dataclass

from app.hedging.models import HedgeDecision, HedgePolicyState
from app.hedging.policies import _hold, _trade_to_target
from app.strategy.models import WhalleyWilmottParameters


@dataclass(frozen=True)
class WhalleyWilmottBand:
    raw_half_width_delta_units: float
    half_width_delta_units: float
    lower_net_delta_units: float
    upper_net_delta_units: float
    capped: bool


def whalley_wilmott_half_band(
    transaction_cost_rate: float,
    spot_inr: float,
    portfolio_gamma_units_per_inr: float,
    risk_aversion_per_inr: float,
) -> float:
    values = (
        transaction_cost_rate,
        spot_inr,
        portfolio_gamma_units_per_inr,
        risk_aversion_per_inr,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Whalley-Wilmott inputs must be finite")
    if transaction_cost_rate < 0 or portfolio_gamma_units_per_inr < 0:
        raise ValueError("transaction cost and portfolio gamma must be non-negative")
    if risk_aversion_per_inr <= 0 or spot_inr <= 0:
        raise ValueError("risk aversion and spot must be positive")
    return math.cbrt(
        3
        * transaction_cost_rate
        * spot_inr
        * portfolio_gamma_units_per_inr**2
        / (2 * risk_aversion_per_inr)
    )


def whalley_wilmott_band(
    transaction_cost_rate: float,
    risk_aversion_per_inr: float,
    spot_inr: float,
    portfolio_gamma_units_per_inr: float,
    maximum_half_width_delta_units: float,
) -> WhalleyWilmottBand:
    if not math.isfinite(maximum_half_width_delta_units) or maximum_half_width_delta_units <= 0:
        raise ValueError("maximum half-width must be positive and finite")
    raw = whalley_wilmott_half_band(
        transaction_cost_rate,
        spot_inr,
        portfolio_gamma_units_per_inr,
        risk_aversion_per_inr,
    )
    half_width = min(raw, maximum_half_width_delta_units)
    return WhalleyWilmottBand(raw, half_width, -half_width, half_width, raw > half_width)


class WhalleyWilmottPolicy:
    policy_id = "whalley_wilmott"

    def __init__(self, parameters: WhalleyWilmottParameters):
        self.parameters = parameters

    def decide(self, state: HedgePolicyState) -> HedgeDecision:
        band = whalley_wilmott_band(
            self.parameters.transaction_cost_rate,
            self.parameters.risk_aversion_per_inr,
            state.spot,
            abs(state.option_gamma),
            self.parameters.maximum_half_width_delta_units,
        )
        if band.lower_net_delta_units <= state.current_net_delta <= band.upper_net_delta_units:
            return _hold(
                state,
                self.policy_id,
                state.current_net_delta,
                band.lower_net_delta_units,
                band.upper_net_delta_units,
                "inside_whalley_wilmott_band",
            )
        target = (
            band.lower_net_delta_units
            if state.current_net_delta < band.lower_net_delta_units
            else band.upper_net_delta_units
        )
        return _trade_to_target(
            state,
            self.policy_id,
            target,
            band.lower_net_delta_units,
            band.upper_net_delta_units,
            "whalley_wilmott_band_breached",
        )
