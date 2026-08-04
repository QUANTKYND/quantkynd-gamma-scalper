from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol


HedgeAction = Literal["hold", "buy_hedge", "sell_hedge"]


@dataclass(frozen=True)
class HedgePolicyState:
    timestamp: datetime
    step_index: int
    session_index: int
    current_option_delta: float
    current_hedge_delta: float
    current_net_delta: float
    option_gamma: float
    spot: float
    time_to_expiry_years: float
    futures_delta_per_contract: float
    risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.step_index < 0 or self.session_index < 0:
            raise ValueError("hedge policy timestamp and indexes are invalid")
        if self.spot <= 0 or self.time_to_expiry_years < 0 or self.futures_delta_per_contract <= 0:
            raise ValueError("hedge policy market inputs are invalid")


@dataclass(frozen=True)
class HedgeDecision:
    timestamp: datetime
    policy_id: str
    current_option_delta: float
    current_hedge_delta: float
    current_net_delta: float
    target_net_delta: float
    lower_boundary: float | None
    upper_boundary: float | None
    action: HedgeAction
    continuous_target_quantity: float
    requested_quantity: int
    post_trade_residual_delta: float
    reason_code: str


class HedgePolicy(Protocol):
    policy_id: str

    def decide(self, state: HedgePolicyState) -> HedgeDecision: ...
