from datetime import date

from app.simulation.clock import generate_simulation_sessions


def sessions_for_path(strategy, market, number_of_steps: int, start: date = date(2026, 1, 2)):
    session_count = number_of_steps // len(market.clock.decision_times_local) + 2
    return generate_simulation_sessions(
        start,
        session_count,
        market.clock,
        strategy.entry.entry_time_local,
    )[: number_of_steps + 1]
