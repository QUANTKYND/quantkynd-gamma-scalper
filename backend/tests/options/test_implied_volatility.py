import pytest

from app.options.black_scholes import price
from app.options.implied_volatility import solve_implied_volatility


@pytest.mark.parametrize(
    ("option_type", "spot", "strike", "time", "volatility"),
    [
        ("call", 100, 100, 1, 0.2),
        ("put", 100, 100, 1, 0.2),
        ("call", 100, 100, 0.01, 0.05),
        ("put", 80, 100, 2, 1.2),
        ("call", 50, 100, 0.25, 0.4),
    ],
)
def test_round_trip(option_type: str, spot: float, strike: float, time: float, volatility: float) -> None:
    observed = price(option_type, spot, strike, time, 0.04, 0.01, volatility)
    result = solve_implied_volatility(option_type, observed, spot, strike, time, 0.04, 0.01)
    assert result.converged
    assert result.implied_volatility == pytest.approx(volatility, abs=5e-7)


def test_impossible_price_fails() -> None:
    with pytest.raises(ValueError):
        solve_implied_volatility("call", 101, 100, 100, 1, 0, 0)


def test_non_convergence_is_explicit() -> None:
    observed = price("call", 100, 100, 1, 0, 0, 0.2)
    result = solve_implied_volatility("call", observed, 100, 100, 1, 0, 0, maximum_iterations=0)
    assert not result.converged
    assert result.implied_volatility is None
