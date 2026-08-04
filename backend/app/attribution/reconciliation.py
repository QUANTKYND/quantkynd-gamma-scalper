from __future__ import annotations

from decimal import Decimal

from app.execution.costs import money
from app.execution.models import SimulatedFill
from app.portfolio.positions import InstrumentPosition
from app.simulation.results import SimulationReconciliation


def reconcile(
    terminal_pnl: Decimal,
    positions: tuple[InstrumentPosition, ...],
    fills: tuple[SimulatedFill, ...],
    option_ids: frozenset[str],
    futures_id: str,
    tolerance: Decimal = Decimal("0.01"),
) -> SimulationReconciliation:
    option_pnl = money(sum((position.realized_pnl for position in positions if position.instrument_id in option_ids), start=Decimal("0")))
    futures_pnl = money(sum((position.realized_pnl for position in positions if position.instrument_id == futures_id), start=Decimal("0")))
    option_costs = money(sum((fill.total_cost for fill in fills if fill.instrument_id in option_ids), start=Decimal("0")))
    futures_costs = money(sum((fill.total_cost for fill in fills if fill.instrument_id == futures_id), start=Decimal("0")))
    financing = Decimal("0.00")
    residual = money(terminal_pnl - (option_pnl + futures_pnl + financing - option_costs - futures_costs))
    return SimulationReconciliation(
        terminal_pnl,
        option_pnl,
        futures_pnl,
        financing,
        option_costs,
        futures_costs,
        residual,
        abs(residual) <= tolerance,
    )
