from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class ExecutionCostParameters:
    fixed_cost_per_order: Decimal
    proportional_notional_rate: Decimal
    half_spread_per_unit: Decimal
    slippage_per_unit: Decimal

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.fixed_cost_per_order,
                self.proportional_notional_rate,
                self.half_spread_per_unit,
                self.slippage_per_unit,
            )
        ):
            raise ValueError("execution costs must be non-negative")


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    timestamp: datetime
    instrument_id: str
    side: Side
    quantity: int
    multiplier: int
    reason_code: str
    strategy_position_id: str
    policy_id: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("intent timestamp must be timezone-aware")
        if self.side not in ("buy", "sell") or self.quantity <= 0 or self.multiplier <= 0:
            raise ValueError("intent side, quantity, and multiplier are invalid")


@dataclass(frozen=True)
class SimulatedFill:
    fill_id: str
    intent_id: str
    timestamp: datetime
    instrument_id: str
    side: Side
    quantity: int
    multiplier: int
    reference_price: Decimal
    fill_price: Decimal
    gross_notional: Decimal
    half_spread_cost: Decimal
    slippage_cost: Decimal
    fixed_cost: Decimal
    proportional_cost: Decimal
    total_cost: Decimal
