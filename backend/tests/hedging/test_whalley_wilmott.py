from datetime import UTC, datetime

import pytest

from app.hedging.models import HedgePolicyState
from app.hedging.whalley_wilmott import WhalleyWilmottPolicy, whalley_wilmott_band
from app.strategy.config import load_strategy_config


def band(cost: float = 0.0002, gamma: float = 0.01, cap: float = 10):
    return whalley_wilmott_band(cost, 1.0, 24000, gamma, 0.05, 0.06, cap)


def test_higher_cost_and_gamma_do_not_narrow_band() -> None:
    assert band(cost=0.0004).half_width_delta_units > band(cost=0.0002).half_width_delta_units
    assert band(gamma=0.02).half_width_delta_units > band(gamma=0.01).half_width_delta_units


def test_zero_cost_or_gamma_has_zero_width() -> None:
    assert band(cost=0).half_width_delta_units == 0
    assert band(gamma=0).half_width_delta_units == 0


@pytest.mark.parametrize(
    "args",
    [
        (-1, 1, 100, 0.01, 1, 0, 1),
        (0.01, 0, 100, 0.01, 1, 0, 1),
        (0.01, 1, 0, 0.01, 1, 0, 1),
        (0.01, 1, 100, -0.01, 1, 0, 1),
    ],
)
def test_invalid_inputs_fail(args: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        whalley_wilmott_band(*args)


def test_near_expiry_width_is_finite_and_capped() -> None:
    result = band(gamma=1000, cap=0.5)
    assert result.half_width_delta_units == 0.5
    assert result.capped


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
