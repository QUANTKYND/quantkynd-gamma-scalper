from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


OptionType = Literal["call", "put"]


@dataclass(frozen=True)
class OptionContract:
    contract_id: str
    underlying: str
    option_type: OptionType
    strike: float
    expiry: date
    multiplier: int
    exercise_style: Literal["european"] = "european"
    settlement_type: Literal["cash"] = "cash"
    currency: Literal["INR"] = "INR"

    def __post_init__(self) -> None:
        if not self.contract_id or not self.underlying:
            raise ValueError("contract identity and underlying are required")
        if self.option_type not in ("call", "put"):
            raise ValueError("option_type must be call or put")
        if self.strike <= 0 or self.multiplier <= 0:
            raise ValueError("strike and multiplier must be positive")
