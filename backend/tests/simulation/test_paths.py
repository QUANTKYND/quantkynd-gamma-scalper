from dataclasses import replace
from datetime import date

import pytest

from app.simulation.paths import (
    GBMPathConfig,
    PiecewisePathConfig,
    VolatilityRegime,
    generate_gbm_path,
    generate_piecewise_path,
    load_user_path,
)
from app.simulation.clock import generate_simulation_sessions
from app.simulation.config import load_simulation_market_config
from app.strategy.config import load_strategy_config


STRATEGY = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
MARKET = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")


def sessions():
    return generate_simulation_sessions(
        date(2026, 1, 2),
        2,
        MARKET.clock,
        STRATEGY.entry.entry_time_local,
    )


def gbm_config(seed: int = 17) -> GBMPathConfig:
    return GBMPathConfig(24000, 0.05, 0.2, 5, 1 / (252 * 3), seed)


def test_seeded_gbm_is_deterministic() -> None:
    first = generate_gbm_path(gbm_config(), sessions())
    second = generate_gbm_path(gbm_config(), sessions())
    assert first.points == second.points
    assert first.path_hash == second.path_hash


def test_different_seed_changes_path() -> None:
    assert generate_gbm_path(gbm_config(), sessions()).path_hash != generate_gbm_path(gbm_config(18), sessions()).path_hash


def test_user_path_validation() -> None:
    points = generate_gbm_path(gbm_config(), sessions()).points
    with pytest.raises(ValueError):
        load_user_path((points[1], points[0]))
    assert load_user_path(points).points == points


def test_piecewise_regimes_are_deterministic_and_cover_steps() -> None:
    config = PiecewisePathConfig(
        24000,
        0.03,
        (VolatilityRegime(1, 2, 0.1), VolatilityRegime(3, 5, 0.4)),
        5,
        1 / 252,
        17,
    )
    assert generate_piecewise_path(config, sessions()) == generate_piecewise_path(config, sessions())
    with pytest.raises(ValueError):
        generate_piecewise_path(
            replace(config, volatility_regimes=(VolatilityRegime(1, 4, 0.2),)),
            sessions(),
        )
