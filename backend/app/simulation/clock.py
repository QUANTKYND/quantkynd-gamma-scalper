from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.simulation.config import SimulationClockConfig


@dataclass(frozen=True)
class SimulationSession:
    session_index: int
    decision_index: int
    session_date: date
    local_decision_at: datetime
    decision_at: datetime
    year_fraction_from_previous: float


@dataclass(frozen=True)
class SimulationExpiry:
    expiry_session_date: date
    remaining_trading_sessions: int
    time_to_expiry_years: float


def generate_simulation_sessions(
    start_session_date: date,
    session_count: int,
    config: SimulationClockConfig,
    entry_time_local: time,
) -> tuple[SimulationSession, ...]:
    if session_count <= 0:
        raise ValueError("session count must be positive")
    if entry_time_local not in config.decision_times_local:
        raise ValueError("strategy entry time must be a configured decision time")
    dates = _trading_dates(start_session_date, session_count)
    timezone = ZoneInfo(config.timezone)
    year_fraction = 1 / (config.trading_periods_per_year * len(config.decision_times_local))
    sessions = []
    sequence = 0
    for session_index, session_date in enumerate(dates):
        for decision_index, decision_time in enumerate(config.decision_times_local):
            if session_index == 0 and decision_time < entry_time_local:
                continue
            local = datetime.combine(session_date, decision_time, timezone)
            sessions.append(
                SimulationSession(
                    session_index,
                    decision_index,
                    session_date,
                    local,
                    local.astimezone(UTC),
                    0.0 if sequence == 0 else year_fraction,
                )
            )
            sequence += 1
    return tuple(sessions)


def expiry_for_remaining_sessions(
    entry_session_date: date,
    remaining_trading_sessions: int,
    config: SimulationClockConfig,
) -> SimulationExpiry:
    if remaining_trading_sessions <= 0:
        raise ValueError("remaining expiry sessions must be positive")
    dates = _trading_dates(entry_session_date, remaining_trading_sessions + 1)
    return SimulationExpiry(
        dates[-1],
        remaining_trading_sessions,
        remaining_trading_sessions / config.trading_periods_per_year,
    )


def remaining_time_to_expiry(
    expiry: SimulationExpiry,
    elapsed_year_fraction: float,
) -> float:
    if elapsed_year_fraction < 0:
        raise ValueError("elapsed year fraction must be non-negative")
    return max(expiry.time_to_expiry_years - elapsed_year_fraction, 0.0)


def _trading_dates(start: date, count: int) -> tuple[date, ...]:
    dates = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)
