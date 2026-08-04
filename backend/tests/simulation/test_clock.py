from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from app.simulation.clock import expiry_for_remaining_sessions, generate_simulation_sessions, remaining_time_to_expiry
from app.simulation.config import load_simulation_market_config
from app.simulation.paths import GBMPathConfig, generate_gbm_path


CONFIG = Path(__file__).parents[3] / "config/simulation/nifty-synthetic-market-v1.yaml"


def clock():
    return load_simulation_market_config(CONFIG).clock


def test_friday_advances_to_monday_without_weekend_sessions() -> None:
    sessions = generate_simulation_sessions(date(2026, 1, 2), 2, clock(), time(9, 30))
    assert {item.session_date for item in sessions} == {date(2026, 1, 2), date(2026, 1, 5)}
    assert all(item.session_date.weekday() < 5 for item in sessions)


def test_entry_time_and_timezone_convert_to_utc() -> None:
    first = generate_simulation_sessions(date(2026, 1, 2), 1, clock(), time(9, 30))[0]
    assert first.local_decision_at.isoformat() == "2026-01-02T09:30:00+05:30"
    assert first.decision_at.isoformat() == "2026-01-02T04:00:00+00:00"


def test_clock_is_deterministic_and_uses_explicit_periods() -> None:
    first = generate_simulation_sessions(date(2026, 1, 2), 2, clock(), time(9, 30))
    second = generate_simulation_sessions(date(2026, 1, 2), 2, clock(), time(9, 30))
    assert first == second
    assert first[1].year_fraction_from_previous == pytest.approx(1 / (252 * 3))


def test_expiry_date_and_year_fraction_share_one_source() -> None:
    expiry = expiry_for_remaining_sessions(date(2026, 1, 2), 15, clock())
    assert expiry.expiry_session_date == date(2026, 1, 23)
    assert expiry.time_to_expiry_years == pytest.approx(15 / 252)
    assert remaining_time_to_expiry(expiry, 15 / 252) == 0
    assert remaining_time_to_expiry(expiry, 16 / 252) == 0


def test_generated_path_reaches_expiry_without_negative_maturity() -> None:
    expiry = expiry_for_remaining_sessions(date(2026, 1, 2), 7, clock())
    decisions = generate_simulation_sessions(date(2026, 1, 2), 8, clock(), time(9, 30))[:22]
    config = GBMPathConfig(
        24000,
        0.03,
        0.2,
        21,
        1 / (252 * 3),
        17,
        datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
        option_expiry_years=7 / 252,
    )
    path = generate_gbm_path(config, decisions, expiry)
    assert path.states[-1].session_date == expiry.expiry_session_date
    assert path.states[-1].time_to_expiry_years == 0
    assert all(state.time_to_expiry_years >= 0 for state in path.states)
