from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution.costs import money
from app.execution.models import SimulatedFill


@dataclass(frozen=True)
class InstrumentPosition:
    instrument_id: str
    quantity: int
    multiplier: int
    average_price: Decimal
    mark_price: Decimal
    realized_pnl: Decimal

    @property
    def market_value(self) -> Decimal:
        return money(self.mark_price * self.quantity * self.multiplier)

    @property
    def unrealized_pnl(self) -> Decimal:
        return money((self.mark_price - self.average_price) * self.quantity * self.multiplier)


def apply_fill(position: InstrumentPosition | None, fill: SimulatedFill) -> InstrumentPosition:
    signed_quantity = fill.quantity if fill.side == "buy" else -fill.quantity
    if position is None:
        return InstrumentPosition(
            fill.instrument_id,
            signed_quantity,
            fill.multiplier,
            fill.reference_price,
            fill.reference_price,
            Decimal("0.00"),
        )
    if position.multiplier != fill.multiplier:
        raise ValueError("fill multiplier does not match position")
    old_quantity = position.quantity
    new_quantity = old_quantity + signed_quantity
    realized = position.realized_pnl
    if old_quantity == 0 or old_quantity * signed_quantity > 0:
        total_cost = position.average_price * abs(old_quantity) + fill.reference_price * abs(signed_quantity)
        average = total_cost / abs(new_quantity)
    else:
        closed = min(abs(old_quantity), abs(signed_quantity))
        direction = Decimal(1 if old_quantity > 0 else -1)
        realized += money((fill.reference_price - position.average_price) * closed * fill.multiplier * direction)
        average = fill.reference_price if old_quantity * new_quantity < 0 else position.average_price
        if new_quantity == 0:
            average = Decimal("0.00")
    return InstrumentPosition(
        position.instrument_id,
        new_quantity,
        position.multiplier,
        money(average),
        fill.reference_price,
        money(realized),
    )
