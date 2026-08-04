import math

import pytest

from app.options.black_scholes import price
from app.options.implied_volatility import solve_implied_volatility


@pytest.mark.parametrize(
    ("risk_free_rate", "dividend_yield"),
    [(math.nan, 0.0), (0.0, math.inf)],
)
def test_black_scholes_rejects_non_finite_rates(
    risk_free_rate: float,
    dividend_yield: float,
) -> None:
    with pytest.raises(ValueError, match="finite"):
        price("call", 100, 100, 1, risk_free_rate, dividend_yield, 0.2)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lower_volatility": math.nan}, "finite"),
        ({"upper_volatility": math.inf}, "finite"),
        ({"lower_volatility": 0.5, "upper_volatility": 0.2}, "bounds"),
        ({"price_tolerance": 0.0}, "tolerance"),
        ({"maximum_iterations": 0}, "iteration"),
    ],
)
def test_implied_volatility_rejects_invalid_solver_inputs(overrides, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        solve_implied_volatility("call", 10, 100, 100, 1, 0.0, 0.0, **overrides)


def test_intrinsic_boundary_reports_zero_volatility_exception_to_positive_lower_bound() -> None:
    observed = price("call", 110, 100, 1, 0.0, 0.0, 0.0)
    result = solve_implied_volatility(
        "call",
        observed,
        110,
        100,
        1,
        0.0,
        0.0,
        lower_volatility=0.1,
    )
    assert result.converged
    assert result.implied_volatility == 0.0
    assert result.reason_code == "intrinsic_boundary"


def test_unbracketed_root_has_explicit_reason_and_no_silent_zero() -> None:
    observed = price("call", 100, 100, 1, 0.0, 0.0, 1.0)
    result = solve_implied_volatility(
        "call",
        observed,
        100,
        100,
        1,
        0.0,
        0.0,
        lower_volatility=0.1,
        upper_volatility=0.2,
    )
    assert not result.converged
    assert result.implied_volatility is None
    assert result.reason_code == "root_not_bracketed"
