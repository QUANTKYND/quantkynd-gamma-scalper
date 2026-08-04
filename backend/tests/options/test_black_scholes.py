import math

import pytest

from app.options.black_scholes import price, value


ARGS = (100.0, 100.0, 1.0, 0.05, 0.0, 0.2)


def test_reference_prices_and_parity() -> None:
    call = price("call", *ARGS)
    put = price("put", *ARGS)
    assert call == pytest.approx(10.45058357, abs=1e-8)
    assert put == pytest.approx(5.57352602, abs=1e-8)
    assert call - put == pytest.approx(100 - 100 * math.exp(-0.05), abs=1e-10)


@pytest.mark.parametrize(("option_type", "spot", "expected"), [("call", 110, 10), ("put", 90, 10)])
def test_expiry_is_intrinsic(option_type: str, spot: float, expected: float) -> None:
    assert price(option_type, spot, 100, 0, 0.05, 0, 0.2) == expected


def test_zero_volatility_is_discounted_deterministic_payoff() -> None:
    assert price("call", *ARGS[:-1], 0.0) == pytest.approx(100 - 100 * math.exp(-0.05))


@pytest.mark.parametrize("spot", [1.0, 50.0, 100.0, 200.0, 10_000.0])
def test_extreme_moneyness_and_small_time_are_finite(spot: float) -> None:
    result = value("call", spot, 100, 1e-12, 0.05, 0.01, 0.2)
    assert math.isfinite(result.price)
    assert math.isfinite(result.greeks.delta)


def test_analytical_greeks_match_finite_differences() -> None:
    valuation = value("call", *ARGS)
    ds = 1e-3
    dv = 1e-5
    dt = 1e-5
    up = price("call", ARGS[0] + ds, *ARGS[1:])
    down = price("call", ARGS[0] - ds, *ARGS[1:])
    delta = (up - down) / (2 * ds)
    gamma = (up - 2 * valuation.price + down) / (ds * ds)
    vega = (price("call", *ARGS[:-1], ARGS[-1] + dv) - price("call", *ARGS[:-1], ARGS[-1] - dv)) / (2 * dv)
    theta = -(price("call", ARGS[0], ARGS[1], ARGS[2] + dt, *ARGS[3:]) - price("call", ARGS[0], ARGS[1], ARGS[2] - dt, *ARGS[3:])) / (2 * dt)
    assert valuation.greeks.delta == pytest.approx(delta, rel=1e-7)
    assert valuation.greeks.gamma == pytest.approx(gamma, rel=2e-4)
    assert valuation.greeks.vega_per_unit_volatility == pytest.approx(vega, rel=1e-7)
    assert valuation.greeks.theta_per_year == pytest.approx(theta, rel=1e-7)


@pytest.mark.parametrize(
    "args",
    [
        ("other", *ARGS),
        ("call", 0, *ARGS[1:]),
        ("call", ARGS[0], 0, *ARGS[2:]),
        ("call", ARGS[0], ARGS[1], -1, *ARGS[3:]),
        ("call", *ARGS[:-1], -0.1),
    ],
)
def test_invalid_inputs_fail(args: tuple) -> None:
    with pytest.raises(ValueError):
        price(*args)
