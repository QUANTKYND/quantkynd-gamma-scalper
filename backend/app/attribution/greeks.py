from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.options.contracts import OptionContract
from app.simulation.market import MarketState

if TYPE_CHECKING:
    from app.simulation.results import OptionValuationRecord


@dataclass(frozen=True)
class GreekAttributionRecord:
    interval_start: datetime
    interval_end: datetime
    exact_option_mark_change: float
    delta_contribution: float
    gamma_contribution: float
    theta_contribution: float
    vega_contribution: float
    residual: float


def calculate_greek_attribution(
    states: tuple[MarketState, ...],
    valuations: tuple[OptionValuationRecord, ...],
    call_contract: OptionContract,
    put_contract: OptionContract,
    _units: int,
) -> tuple[GreekAttributionRecord, ...]:
    by_timestamp = {
        (record.timestamp, record.contract_id): record
        for record in valuations
    }
    contracts = (call_contract, put_contract)
    records = []
    for previous_state, current_state in zip(states, states[1:], strict=False):
        delta_contribution = 0.0
        gamma_contribution = 0.0
        theta_contribution = 0.0
        vega_contribution = 0.0
        exact_change = 0.0
        spot_change = current_state.spot - previous_state.spot
        volatility_change = current_state.implied_volatility - previous_state.implied_volatility
        for contract in contracts:
            previous = by_timestamp[(previous_state.timestamp, contract.contract_id)]
            current = by_timestamp[(current_state.timestamp, contract.contract_id)]
            delta_contribution += previous.portfolio_delta * spot_change
            gamma_contribution += 0.5 * previous.portfolio_gamma * spot_change**2
            theta_contribution += previous.portfolio_theta_per_year * current_state.step_year_fraction
            vega_contribution += previous.portfolio_vega_per_volatility_unit * volatility_change
            exact_change += (current.unit_price - previous.unit_price) * previous.quantity * previous.multiplier
        approximation = delta_contribution + gamma_contribution + theta_contribution + vega_contribution
        records.append(
            GreekAttributionRecord(
                previous_state.timestamp,
                current_state.timestamp,
                exact_change,
                delta_contribution,
                gamma_contribution,
                theta_contribution,
                vega_contribution,
                exact_change - approximation,
            )
        )
    return tuple(records)
