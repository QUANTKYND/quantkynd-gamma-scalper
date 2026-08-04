from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.execution.costs import money
from app.execution.models import SimulatedFill
from app.options.selection import SyntheticOptionPair
from app.strategy.models import RiskPolicyConfig

if TYPE_CHECKING:
    from app.simulation.results import OptionValuationRecord


@dataclass(frozen=True)
class SimulationRiskDecision:
    timestamp: datetime
    session_date: date
    rule_id: str
    observed_value: float | Decimal | bool | int | str
    configured_limit: float | Decimal | bool | int | str
    decision: str
    reason_code: str
    position_pnl_from_entry: Decimal
    session_pnl: Decimal
    session_hedge_count: int
    total_hedge_count: int


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
    premium_at_risk: Decimal,
    absolute_daily_theta: Decimal,
    selected: SyntheticOptionPair,
    policy: RiskPolicyConfig,
    require_quote_quality: bool,
    require_liquidity: bool,
) -> tuple[SimulationRiskDecision, ...]:
    premium_limit = money(
        Decimal(str(policy.starting_nav_inr))
        * Decimal(str(policy.maximum_premium_at_risk_fraction))
    )
    theta_limit = money(
        Decimal(str(policy.starting_nav_inr))
        * Decimal(str(policy.maximum_daily_theta_fraction))
    )
    integrity = (
        selected.call.strike == selected.put.strike
        and selected.call.expiry == selected.put.expiry
        and selected.call.multiplier == selected.put.multiplier
    )
    rules = (
        (
            "maximum_premium_at_risk",
            premium_at_risk,
            premium_limit,
            premium_at_risk <= premium_limit,
            "premium_at_risk",
        ),
        (
            "option_spread_quality",
            selected.combined_relative_spread,
            policy.maximum_option_relative_spread,
            not require_quote_quality
            or selected.combined_relative_spread <= policy.maximum_option_relative_spread,
            "option_spread",
        ),
        (
            "option_volume_quality",
            selected.combined_volume,
            1,
            not require_liquidity or selected.combined_volume > 0,
            "option_volume",
        ),
        (
            "option_open_interest_quality",
            selected.combined_open_interest,
            1,
            not require_liquidity or selected.combined_open_interest > 0,
            "option_open_interest",
        ),
        (
            "matched_straddle_integrity",
            integrity,
            True,
            integrity,
            "matched_straddle_integrity",
        ),
        (
            "maximum_daily_theta",
            absolute_daily_theta,
            theta_limit,
            absolute_daily_theta <= theta_limit,
            "daily_theta",
        ),
    )
    decisions = tuple(
        SimulationRiskDecision(
            timestamp,
            session_date,
            rule_id,
            observed,
            limit,
            "approve" if approved else "reject",
            f"{reason}_within_limit" if approved else f"{reason}_breached",
            Decimal("0.00"),
            Decimal("0.00"),
            0,
            0,
        )
        for rule_id, observed, limit, approved, reason in rules
    )
    return decisions + (
        SimulationRiskDecision(
            timestamp,
            session_date,
            "minimum_expected_net_edge",
            "not_available_in_sim_1",
            policy.minimum_expected_net_edge_fraction,
            "not_evaluated",
            "deferred_to_edge_1",
            Decimal("0.00"),
            Decimal("0.00"),
            0,
            0,
        ),
    )


def absolute_daily_theta(
    valuations: tuple[OptionValuationRecord, ...],
    trading_periods_per_year: int,
) -> Decimal:
    annual_theta = sum(record.portfolio_theta_per_year for record in valuations)
    return money(Decimal(str(abs(annual_theta) / trading_periods_per_year)))


def option_entry_premium_at_risk(fills: tuple[SimulatedFill, ...]) -> Decimal:
    if any(fill.side != "buy" for fill in fills):
        raise ValueError("premium-at-risk fills must be long option entries")
    return money(sum((fill.gross_notional + fill.total_cost for fill in fills), start=Decimal("0")))


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
            risk_state.position_pnl_from_entry,
            risk_state.session_pnl,
            risk_state.hedges_in_current_session,
            risk_state.total_hedges,
        )
        for rule_id, observed, limit, breached, reason in rules
    )
