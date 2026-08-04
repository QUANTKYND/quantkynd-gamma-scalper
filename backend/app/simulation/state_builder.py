from __future__ import annotations

from dataclasses import asdict
from zoneinfo import ZoneInfo

from app.simulation.clock import SimulationExpiry, remaining_time_to_expiry
from app.simulation.config import SimulationMarketConfig, stable_hash
from app.simulation.market import MarketState, carry_futures_price
from app.simulation.paths import GeneratedUnderlyingPath
from app.strategy.models import StrategyContractV1


def build_executable_market_states(
    strategy: StrategyContractV1,
    market: SimulationMarketConfig,
    path: GeneratedUnderlyingPath,
    option_expiry: SimulationExpiry,
) -> tuple[MarketState, ...]:
    futures_maturity = (
        strategy.expiry.holding_horizon_sessions + market.futures.expiry_buffer_sessions
    ) / market.clock.trading_periods_per_year
    elapsed = 0.0
    timezone = ZoneInfo(market.clock.timezone)
    states = []
    for point in path.points:
        elapsed += point.realized_step_year_fraction
        remaining_futures_maturity = max(futures_maturity - elapsed, 0.0)
        states.append(
            MarketState(
                timestamp=point.timestamp,
                session_index=point.session_index,
                step_index=point.step_index,
                spot=point.spot,
                futures_price=carry_futures_price(
                    point.spot,
                    point.risk_free_rate,
                    point.dividend_yield,
                    remaining_futures_maturity,
                ),
                risk_free_rate=point.risk_free_rate,
                dividend_yield=point.dividend_yield,
                implied_volatility=point.implied_volatility,
                time_to_expiry_years=remaining_time_to_expiry(option_expiry, elapsed),
                step_year_fraction=point.realized_step_year_fraction,
                session_date=point.session_date,
                local_timestamp=point.timestamp.astimezone(timezone),
            )
        )
    return tuple(states)


def executable_market_state_hash(states: tuple[MarketState, ...]) -> str:
    return stable_hash([asdict(state) for state in states])
