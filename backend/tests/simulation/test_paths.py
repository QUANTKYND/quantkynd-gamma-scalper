from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.simulation.paths import (
    GBMPathConfig,
    PiecewisePathConfig,
    VolatilityRegime,
    generate_gbm_path,
    generate_piecewise_path,
    load_user_path,
)


def gbm_config(seed: int = 17) -> GBMPathConfig:
    return GBMPathConfig(24000, 0.05, 0.2, 5, 1 / 252, seed, datetime(2026, 1, 1, tzinfo=UTC))


def test_seeded_gbm_is_deterministic() -> None:
    first = generate_gbm_path(gbm_config())
    second = generate_gbm_path(gbm_config())
    assert first.states == second.states
    assert first.path_hash == second.path_hash


def test_different_seed_changes_path() -> None:
    assert generate_gbm_path(gbm_config()).path_hash != generate_gbm_path(gbm_config(18)).path_hash


def test_user_path_validation() -> None:
    states = generate_gbm_path(gbm_config()).states
    with pytest.raises(ValueError):
        load_user_path((states[1], states[0]))
    assert load_user_path(states).states == states


def test_piecewise_regimes_are_deterministic_and_cover_steps() -> None:
    config = PiecewisePathConfig(
        24000,
        0.03,
        (VolatilityRegime(1, 2, 0.1), VolatilityRegime(3, 5, 0.4)),
        5,
        1 / 252,
        17,
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert generate_piecewise_path(config) == generate_piecewise_path(config)
    with pytest.raises(ValueError):
        generate_piecewise_path(replace(config, volatility_regimes=(VolatilityRegime(1, 4, 0.2),)))
