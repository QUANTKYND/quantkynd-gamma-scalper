from __future__ import annotations

from dataclasses import asdict
from zoneinfo import ZoneInfo

from app.simulation.clock import SimulationExpiry, generate_simulation_sessions, remaining_time_to_expiry
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
    validate_underlying_path_clock(strategy, market, path)
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
                futures_time_to_expiry_years=remaining_futures_maturity,
                step_year_fraction=point.realized_step_year_fraction,
                session_date=point.session_date,
                local_timestamp=point.timestamp.astimezone(timezone),
            )
        )
    return tuple(states)


def executable_market_state_hash(states: tuple[MarketState, ...]) -> str:
    return stable_hash([asdict(state) for state in states])


def validate_underlying_path_clock(
    strategy: StrategyContractV1,
    market: SimulationMarketConfig,
    path: GeneratedUnderlyingPath,
) -> None:
    if not path.points:
        raise ValueError("simulation path cannot be empty")
    timezone = ZoneInfo(market.clock.timezone)
    first_local = path.points[0].timestamp.astimezone(timezone)
    expected = generate_simulation_sessions(
        first_local.date(),
        len(path.points) // len(market.clock.decision_times_local) + 2,
        market.clock,
        strategy.entry.entry_time_local,
    )[: len(path.points)]
    if len(expected) != len(path.points):
        raise ValueError("underlying path exceeds generated clock")
    for step_index, (point, session) in enumerate(zip(path.points, expected, strict=True)):
        if point.timestamp.utcoffset() != session.decision_at.utcoffset():
            raise ValueError("underlying path timestamps must use UTC")
        if point.timestamp != session.decision_at:
            raise ValueError("underlying path timestamp does not match simulation clock")
        if point.session_date != session.session_date or point.session_index != session.session_index:
            raise ValueError("underlying path session identity does not match simulation clock")
        if point.step_index != step_index:
            raise ValueError("underlying path step index does not match simulation clock")
        if point.realized_step_year_fraction != session.year_fraction_from_previous:
            raise ValueError("underlying path year fraction does not match simulation clock")
