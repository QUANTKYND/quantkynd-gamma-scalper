from datetime import UTC, datetime

import pytest

from app.hedging.models import HedgePolicyState
from app.hedging.whalley_wilmott import (
    WhalleyWilmottPolicy,
    whalley_wilmott_band,
    whalley_wilmott_half_band,
)
from app.strategy.config import load_strategy_config


def band(cost: float = 0.0002, gamma: float = 0.01, cap: float = 10):
    return whalley_wilmott_band(cost, 1.0, 24000, gamma, cap)


def test_exact_source_formula_numeric_regression() -> None:
    expected = ((3 * 0.01 * 100 * 0.02**2) / (2 * 2.0)) ** (1 / 3)
    assert whalley_wilmott_half_band(0.01, 100, 0.02, 2.0) == pytest.approx(expected)


def test_higher_cost_and_gamma_do_not_narrow_band() -> None:
    assert band(cost=0.0004).half_width_delta_units > band(cost=0.0002).half_width_delta_units
    assert band(gamma=0.02).half_width_delta_units > band(gamma=0.01).half_width_delta_units


def test_zero_cost_or_gamma_has_zero_width() -> None:
    assert band(cost=0).half_width_delta_units == 0
    assert band(gamma=0).half_width_delta_units == 0


@pytest.mark.parametrize(
    "args",
    [
        (-1, 1, 100, 0.01, 1),
        (0.01, 0, 100, 0.01, 1),
        (0.01, 1, 0, 0.01, 1),
        (0.01, 1, 100, -0.01, 1),
        (0.01, 1, 100, 0.01, float("nan")),
    ],
)
def test_invalid_inputs_fail(args: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        whalley_wilmott_band(*args)


def test_near_expiry_width_is_finite_and_capped() -> None:
    result = band(gamma=1000, cap=0.5)
    assert result.half_width_delta_units == 0.5
    assert result.capped


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_source_inputs_fail(value: float) -> None:
    with pytest.raises(ValueError):
        whalley_wilmott_half_band(0.01, 100, value, 1)


def test_policy_holds_inside_and_trades_to_boundary() -> None:
    parameters = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml").hedging.whalley_wilmott
    policy = WhalleyWilmottPolicy(parameters)
    base = HedgePolicyState(
        datetime(2026, 1, 1, tzinfo=UTC), 1, 1, 0, 0, 0, 0.01, 24000, 0.05, 0.01
    )
    assert policy.decide(base).action == "hold"
    breached = HedgePolicyState(
        base.timestamp, 1, 1, 1, 0, 1, 0.01, 24000, 0.05, 0.01
    )
    assert policy.decide(breached).action == "sell_hedge"


def test_wider_analytical_band_trades_no_more_often() -> None:
    parameters = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml").hedging.whalley_wilmott
    narrow = WhalleyWilmottPolicy(parameters.model_copy(update={"transaction_cost_rate": 0.00001}))
    wide = WhalleyWilmottPolicy(parameters.model_copy(update={"transaction_cost_rate": 0.001}))
    states = [
        HedgePolicyState(
            datetime(2026, 1, 1, tzinfo=UTC),
            index,
            1,
            delta,
            0,
            delta,
            0.01,
            24000,
            0.05,
            0.01,
        )
        for index, delta in enumerate((-0.6, -0.3, 0.0, 0.3, 0.6))
    ]
    narrow_trades = sum(narrow.decide(state).action != "hold" for state in states)
    wide_trades = sum(wide.decide(state).action != "hold" for state in states)
    assert wide_trades <= narrow_trades
