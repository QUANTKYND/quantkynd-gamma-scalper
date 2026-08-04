from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.execution.fills import simulate_fill
from app.execution.models import ExecutionCostParameters, OrderIntent


def intent(side: str) -> OrderIntent:
    return OrderIntent("i-1", datetime(2026, 1, 1, tzinfo=UTC), "NIFTY", side, 2, 50, "test", "p-1", "policy")


def costs() -> ExecutionCostParameters:
    return ExecutionCostParameters(Decimal("10"), Decimal("0.001"), Decimal("0.50"), Decimal("0.25"))


def test_buy_and_sell_fills_are_side_aware() -> None:
    buy = simulate_fill(intent("buy"), 100, costs())
    sell = simulate_fill(intent("sell"), 100, costs())
    assert buy.fill_price == Decimal("100.75")
    assert sell.fill_price == Decimal("99.25")


def test_cost_components_are_separate_and_sum() -> None:
    fill = simulate_fill(intent("buy"), 100, costs())
    assert fill.gross_notional == Decimal("10000.00")
    assert fill.fixed_cost == Decimal("10.00")
    assert fill.proportional_cost == Decimal("10.00")
    assert fill.half_spread_cost == Decimal("50.00")
    assert fill.slippage_cost == Decimal("25.00")
    assert fill.total_cost == sum(
        (fill.fixed_cost, fill.proportional_cost, fill.half_spread_cost, fill.slippage_cost),
        start=Decimal("0.00"),
    )


def test_option_and_futures_cost_parameters_are_independent() -> None:
    cheap = ExecutionCostParameters(Decimal("0"), Decimal("0"), Decimal("0.01"), Decimal("0"))
    assert simulate_fill(intent("buy"), 100, cheap).total_cost != simulate_fill(intent("buy"), 100, costs()).total_cost
