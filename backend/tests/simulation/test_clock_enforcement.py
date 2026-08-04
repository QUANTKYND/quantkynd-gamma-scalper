from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config
from app.simulation.engine import run_simulation
from app.simulation.paths import GBMPathConfig, generate_gbm_path, replace_path_points
from app.strategy.config import load_strategy_config
from tests.simulation.support import sessions_for_path


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs(start: date = date(2026, 1, 2)):
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17),
        sessions_for_path(strategy, market, 15, start),
    )
    return strategy, market, path


@pytest.mark.parametrize(
    "change",
    [
        {"timestamp": datetime(2026, 1, 3, 4, 0, tzinfo=UTC), "session_date": date(2026, 1, 3)},
        {"timestamp": datetime(2026, 1, 2, 5, 0, tzinfo=UTC)},
        {"realized_step_year_fraction": 1 / 252},
    ],
)
def test_engine_rejects_points_outside_configured_clock(change: dict[str, object]) -> None:
    strategy, market, path = inputs()
    points = (replace(path.points[0], **change),) + path.points[1:]
    changed = replace_path_points(path, points)
    with pytest.raises(ValueError, match="simulation clock"):
        run_simulation(strategy, market, changed, "no_hedge", ZERO, ZERO)


def test_non_utc_timestamp_cannot_silently_derive_exchange_date() -> None:
    strategy, market, path = inputs()
    shifted = path.points[0].timestamp.astimezone(timezone(timedelta(hours=1)))
    points = (replace(path.points[0], timestamp=shifted),) + path.points[1:]
    with pytest.raises((TypeError, ValueError)):
        run_simulation(strategy, market, replace_path_points(path, points), "no_hedge", ZERO, ZERO)


def test_friday_to_monday_path_passes_engine_clock_validation() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    dates = {state.session_date for state in result.market_states}
    assert date(2026, 1, 2) in dates
    assert date(2026, 1, 5) in dates
    assert all(session_date.weekday() < 5 for session_date in dates)
