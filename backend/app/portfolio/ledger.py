from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.execution.costs import money
from app.execution.models import SimulatedFill
from app.portfolio.positions import InstrumentPosition, apply_fill


LedgerEntryType = Literal[
    "initial_capital",
    "option_entry",
    "option_exit",
    "option_expiry_settlement",
    "futures_hedge_buy",
    "futures_hedge_sell",
    "futures_close",
    "transaction_cost",
    "cash_financing",
    "simulation_close",
]


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    timestamp: datetime
    entry_type: LedgerEntryType
    instrument_id: str | None
    quantity_change: int
    cash_change: Decimal
    cost: Decimal
    reference_id: str
    strategy_position_id: str


class PortfolioLedger:
    def __init__(self, starting_nav: Decimal, opened_at: datetime, strategy_position_id: str):
        if starting_nav <= 0 or opened_at.tzinfo is None:
            raise ValueError("ledger starting NAV and timestamp are invalid")
        self.starting_nav = money(starting_nav)
        self.entries = [
            LedgerEntry(
                "ledger-initial",
                opened_at,
                "initial_capital",
                None,
                0,
                self.starting_nav,
                Decimal("0.00"),
                "initial-capital",
                strategy_position_id,
            )
        ]
        self.positions: dict[str, InstrumentPosition] = {}

    @property
    def cash(self) -> Decimal:
        return money(sum((entry.cash_change for entry in self.entries), start=Decimal("0.00")))

    @property
    def transaction_costs(self) -> Decimal:
        return money(sum((entry.cost for entry in self.entries), start=Decimal("0.00")))

    def record_fill(self, fill: SimulatedFill, entry_type: LedgerEntryType, strategy_position_id: str) -> None:
        sign = Decimal(-1) if fill.side == "buy" else Decimal(1)
        quantity_change = fill.quantity if fill.side == "buy" else -fill.quantity
        self.entries.append(
            LedgerEntry(
                f"ledger-{fill.fill_id}-trade",
                fill.timestamp,
                entry_type,
                fill.instrument_id,
                quantity_change,
                money(sign * fill.gross_notional),
                Decimal("0.00"),
                fill.fill_id,
                strategy_position_id,
            )
        )
        self.entries.append(
            LedgerEntry(
                f"ledger-{fill.fill_id}-cost",
                fill.timestamp,
                "transaction_cost",
                fill.instrument_id,
                0,
                -fill.total_cost,
                fill.total_cost,
                fill.fill_id,
                strategy_position_id,
            )
        )
        self.positions[fill.instrument_id] = apply_fill(self.positions.get(fill.instrument_id), fill)

    def mark(self, instrument_id: str, price: float | Decimal) -> None:
        position = self.positions[instrument_id]
        self.positions[instrument_id] = InstrumentPosition(
            position.instrument_id,
            position.quantity,
            position.multiplier,
            position.average_price,
            money(Decimal(str(price))),
            position.realized_pnl,
        )

    def portfolio_value(self) -> Decimal:
        return money(self.cash + sum((position.market_value for position in self.positions.values()), start=Decimal("0.00")))

    def terminal_pnl(self) -> Decimal:
        return money(self.portfolio_value() - self.starting_nav)
