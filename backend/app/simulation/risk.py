from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.strategy.models import RiskPolicyConfig


@dataclass(frozen=True)
class SimulationRiskDecision:
    timestamp: datetime
    rule_id: str
    observed_value: float | bool
    configured_limit: float | bool
    decision: str
    reason_code: str


def entry_risk_decisions(
    timestamp: datetime,
    premium_at_risk: float,
    policy: RiskPolicyConfig,
) -> tuple[SimulationRiskDecision, ...]:
    limit = policy.starting_nav_inr * policy.maximum_premium_at_risk_fraction
    breached = premium_at_risk > limit
    return (
        SimulationRiskDecision(
            timestamp,
            "maximum_premium_at_risk",
            premium_at_risk,
            limit,
            "reject" if breached else "approve",
            "premium_at_risk_breached" if breached else "premium_at_risk_within_limit",
        ),
    )


def state_risk_decisions(
    timestamp: datetime,
    pnl: float,
    net_delta: float,
    hedge_count: int,
    policy: RiskPolicyConfig,
    kill_switch_engaged: bool,
) -> tuple[SimulationRiskDecision, ...]:
    position_loss_limit = policy.starting_nav_inr * policy.maximum_position_loss_fraction
    daily_loss_limit = policy.starting_nav_inr * policy.maximum_daily_loss_fraction
    rules = (
        (
            "manual_kill_switch",
            kill_switch_engaged,
            False,
            kill_switch_engaged,
            "manual_kill_switch_engaged",
        ),
        (
            "daily_loss_limit",
            max(-pnl, 0.0),
            daily_loss_limit,
            pnl <= -daily_loss_limit,
            "daily_loss_limit_breached",
        ),
        (
            "position_loss_limit",
            max(-pnl, 0.0),
            position_loss_limit,
            pnl <= -position_loss_limit,
            "position_loss_limit_breached",
        ),
        (
            "maximum_hedge_count",
            hedge_count,
            policy.maximum_hedges_per_session,
            hedge_count >= policy.maximum_hedges_per_session,
            "maximum_hedge_count_breached",
        ),
        (
            "maximum_absolute_delta",
            abs(net_delta),
            policy.maximum_absolute_delta_units,
            abs(net_delta) > policy.maximum_absolute_delta_units,
            "maximum_absolute_delta_breached",
        ),
    )
    return tuple(
        SimulationRiskDecision(
            timestamp,
            rule_id,
            observed,
            limit,
            "exit" if breached and rule_id != "maximum_absolute_delta" else "record" if breached else "pass",
            reason if breached else f"{rule_id}_within_limit",
        )
        for rule_id, observed, limit, breached, reason in rules
    )
