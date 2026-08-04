from dataclasses import replace
from datetime import date

import pytest

from app.options.selection import SyntheticOptionPair, select_expiry, select_straddle, synthetic_chain
from app.strategy.config import load_strategy_config


def strategy():
    return load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")


def test_earliest_eligible_expiry_and_explicit_failure() -> None:
    first = date(2026, 1, 8)
    second = date(2026, 1, 15)
    assert select_expiry({second: 12, first: 7}, strategy().expiry) == first
    with pytest.raises(ValueError):
        select_expiry({first: 6, second: 16}, strategy().expiry)


def pair(strike: float, spread: float, volume: int, oi: int) -> SyntheticOptionPair:
    base = synthetic_chain("NIFTY", 100, 10, 0, 0, date(2026, 1, 30), 50)[0]
    return replace(base, strike=strike, combined_relative_spread=spread, combined_volume=volume, combined_open_interest=oi)


@pytest.mark.parametrize(
    "chain",
    [
        (pair(90, 0.03, 10, 10), pair(110, 0.02, 10, 10)),
        (pair(90, 0.02, 10, 10), pair(110, 0.02, 20, 10)),
        (pair(90, 0.02, 20, 10), pair(110, 0.02, 20, 20)),
    ],
)
def test_tie_break_levels_select_second(chain: tuple[SyntheticOptionPair, ...]) -> None:
    assert select_straddle(chain, 100) == chain[1]


def test_lower_strike_is_final_tie_break() -> None:
    assert select_straddle((pair(110, 0.02, 20, 20), pair(90, 0.02, 20, 20)), 100).strike == 90


def test_synthetic_pair_contracts_match() -> None:
    selected = select_straddle(synthetic_chain("NIFTY", 103, 10, 2, 2, date(2026, 1, 30), 50), 103)
    assert selected.call.strike == selected.put.strike
    assert selected.call.expiry == selected.put.expiry
    assert selected.call.multiplier == selected.put.multiplier
