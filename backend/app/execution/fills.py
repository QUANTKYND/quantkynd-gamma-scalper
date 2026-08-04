from __future__ import annotations

from decimal import Decimal

from app.execution.costs import money
from app.execution.models import ExecutionCostParameters, OrderIntent, SimulatedFill


def simulate_fill(
    intent: OrderIntent,
    reference_price: float | Decimal,
    costs: ExecutionCostParameters,
    fill_id: str | None = None,
) -> SimulatedFill:
    reference = Decimal(str(reference_price))
    if reference < 0:
        raise ValueError("fill reference price must be non-negative")
    direction = Decimal(1) if intent.side == "buy" else Decimal(-1)
    execution_adjustment = costs.half_spread_per_unit + costs.slippage_per_unit
    fill_price = money(max(reference + direction * execution_adjustment, Decimal("0")))
    units = Decimal(intent.quantity * intent.multiplier)
    gross_notional = money(reference * units)
    half_spread_cost = money(costs.half_spread_per_unit * units)
    slippage_cost = money(costs.slippage_per_unit * units)
    proportional_cost = money(costs.proportional_notional_rate * gross_notional)
    fixed_cost = money(costs.fixed_cost_per_order)
    total_cost = half_spread_cost + slippage_cost + proportional_cost + fixed_cost
    return SimulatedFill(
        fill_id=fill_id or f"fill-{intent.intent_id}",
        intent_id=intent.intent_id,
        timestamp=intent.timestamp,
        instrument_id=intent.instrument_id,
        side=intent.side,
        quantity=intent.quantity,
        multiplier=intent.multiplier,
        reference_price=money(reference),
        fill_price=fill_price,
        gross_notional=gross_notional,
        half_spread_cost=half_spread_cost,
        slippage_cost=slippage_cost,
        fixed_cost=fixed_cost,
        proportional_cost=proportional_cost,
        total_cost=total_cost,
    )
