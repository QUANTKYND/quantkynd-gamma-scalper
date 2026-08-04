from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from app.strategy.models import RiskPolicyConfig


@dataclass(frozen=True)
class SimulationRiskDecision:
    timestamp: datetime
    session_date: date
    rule_id: str
    observed_value: float | Decimal | bool
    configured_limit: float | Decimal | bool
    decision: str
    reason_code: str


@dataclass(frozen=True)
class SimulationRiskState:
    position_open_value: Decimal
    position_pnl_from_entry: Decimal
    session_open_portfolio_value: Decimal
    session_pnl: Decimal
    hedges_in_current_session: int
    total_hedges: int
    current_session_date: date


def initialize_risk_state(portfolio_value: Decimal, session_date: date) -> SimulationRiskState:
    return SimulationRiskState(
        portfolio_value,
        Decimal("0.00"),
        portfolio_value,
        Decimal("0.00"),
        0,
        0,
        session_date,
    )


def mark_risk_state(
    state: SimulationRiskState,
    portfolio_value: Decimal,
    session_date: date,
) -> SimulationRiskState:
    if session_date != state.current_session_date:
        return SimulationRiskState(
            state.position_open_value,
            portfolio_value - state.position_open_value,
            portfolio_value,
            Decimal("0.00"),
            0,
            state.total_hedges,
            session_date,
        )
    return replace(
        state,
        position_pnl_from_entry=portfolio_value - state.position_open_value,
        session_pnl=portfolio_value - state.session_open_portfolio_value,
    )


def record_risk_hedge(state: SimulationRiskState) -> SimulationRiskState:
    return replace(
        state,
        hedges_in_current_session=state.hedges_in_current_session + 1,
        total_hedges=state.total_hedges + 1,
    )


def entry_risk_decisions(
    timestamp: datetime,
    session_date: date,
    premium_at_risk: float,
    policy: RiskPolicyConfig,
) -> tuple[SimulationRiskDecision, ...]:
    limit = policy.starting_nav_inr * policy.maximum_premium_at_risk_fraction
    breached = premium_at_risk > limit
    return (
        SimulationRiskDecision(
            timestamp,
            session_date,
            "maximum_premium_at_risk",
            premium_at_risk,
            limit,
            "reject" if breached else "approve",
            "premium_at_risk_breached" if breached else "premium_at_risk_within_limit",
        ),
    )


def state_risk_decisions(
    timestamp: datetime,
    risk_state: SimulationRiskState,
    net_delta: float,
    policy: RiskPolicyConfig,
    kill_switch_engaged: bool,
) -> tuple[SimulationRiskDecision, ...]:
    position_loss_limit = Decimal(str(policy.starting_nav_inr * policy.maximum_position_loss_fraction))
    daily_loss_limit = Decimal(str(policy.starting_nav_inr * policy.maximum_daily_loss_fraction))
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
            max(-risk_state.session_pnl, Decimal("0")),
            daily_loss_limit,
            risk_state.session_pnl <= -daily_loss_limit,
            "daily_loss_limit_breached",
        ),
        (
            "position_loss_limit",
            max(-risk_state.position_pnl_from_entry, Decimal("0")),
            position_loss_limit,
            risk_state.position_pnl_from_entry <= -position_loss_limit,
            "position_loss_limit_breached",
        ),
        (
            "maximum_hedge_count",
            risk_state.hedges_in_current_session,
            policy.maximum_hedges_per_session,
            risk_state.hedges_in_current_session >= policy.maximum_hedges_per_session,
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
            risk_state.current_session_date,
            rule_id,
            observed,
            limit,
            "exit" if breached and rule_id != "maximum_absolute_delta" else "record" if breached else "pass",
            reason if breached else f"{rule_id}_within_limit",
        )
        for rule_id, observed, limit, breached, reason in rules
    )
