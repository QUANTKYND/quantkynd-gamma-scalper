from datetime import UTC, date, datetime
from decimal import Decimal

from app.execution.fills import simulate_fill
from app.execution.models import ExecutionCostParameters, OrderIntent
from app.simulation.risk import (
    initialize_risk_state,
    mark_risk_state,
    option_entry_premium_at_risk,
    record_risk_hedge,
    state_risk_decisions,
)
from app.strategy.config import load_strategy_config


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def option_fill(multiplier: int):
    intent = OrderIntent(
        f"entry-{multiplier}",
        datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
        "NIFTY-CALL",
        "buy",
        2,
        multiplier,
        "open_long_straddle",
        "position-1",
        "no_hedge",
    )
    return simulate_fill(intent, Decimal("100"), ZERO)


def test_option_multiplier_scales_premium_at_risk() -> None:
    baseline = option_entry_premium_at_risk((option_fill(1),))
    scaled = option_entry_premium_at_risk((option_fill(5),))
    assert baseline == Decimal("200.00")
    assert scaled == baseline * 5


def test_position_pnl_persists_while_daily_pnl_resets() -> None:
    state = initialize_risk_state(Decimal("1000"), Decimal("1000"), date(2026, 1, 2))
    first_session = mark_risk_state(state, Decimal("900"), date(2026, 1, 2))
    next_session = mark_risk_state(first_session, Decimal("925"), date(2026, 1, 5))
    assert first_session.position_pnl_from_entry == Decimal("-100")
    assert first_session.session_pnl == Decimal("-100")
    assert next_session.position_pnl_from_entry == Decimal("-75")
    assert next_session.session_pnl == Decimal("25")
    later = mark_risk_state(next_session, Decimal("900"), date(2026, 1, 5))
    assert later.position_pnl_from_entry == Decimal("-100")
    assert later.session_pnl == Decimal("0")


def test_session_hedge_count_resets_but_total_persists() -> None:
    state = initialize_risk_state(Decimal("1000"), Decimal("1000"), date(2026, 1, 2))
    state = record_risk_hedge(record_risk_hedge(state))
    assert state.hedges_in_current_session == 2
    assert state.total_hedges == 2
    state = mark_risk_state(state, Decimal("1000"), date(2026, 1, 5))
    assert state.hedges_in_current_session == 0
    assert state.total_hedges == 2
    state = record_risk_hedge(state)
    assert state.hedges_in_current_session == 1
    assert state.total_hedges == 3


def test_risk_decisions_use_separate_daily_and_position_values() -> None:
    policy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml").risk
    state = initialize_risk_state(
        Decimal("1000000"), Decimal("1000000"), date(2026, 1, 2)
    )
    state = mark_risk_state(state, Decimal("990000"), date(2026, 1, 2))
    state = mark_risk_state(state, Decimal("991000"), date(2026, 1, 5))
    state = mark_risk_state(state, Decimal("989000"), date(2026, 1, 5))
    decisions = state_risk_decisions(
        datetime(2026, 1, 5, 4, 0, tzinfo=UTC),
        state,
        0.0,
        policy,
        False,
    )
    by_rule = {decision.rule_id: decision for decision in decisions}
    assert by_rule["position_loss_limit"].observed_value == Decimal("11000")
    assert by_rule["daily_loss_limit"].observed_value == Decimal("1000")
    assert all(decision.session_date == date(2026, 1, 5) for decision in decisions)


def test_entry_costs_are_immediate_position_and_session_losses() -> None:
    state = initialize_risk_state(Decimal("1000"), Decimal("985"), date(2026, 1, 2))
    assert state.position_pnl_from_entry == Decimal("-15")
    assert state.session_pnl == Decimal("-15")


def test_overnight_gap_uses_prior_session_final_mark() -> None:
    state = initialize_risk_state(Decimal("1000"), Decimal("990"), date(2026, 1, 2))
    prior_close = mark_risk_state(state, Decimal("1020"), date(2026, 1, 2))
    loss_open = mark_risk_state(prior_close, Decimal("980"), date(2026, 1, 5))
    gain_open = mark_risk_state(prior_close, Decimal("1050"), date(2026, 1, 5))
    assert loss_open.session_reference_portfolio_value == Decimal("1020")
    assert loss_open.session_pnl == Decimal("-40")
    assert loss_open.position_pnl_from_entry == Decimal("-20")
    assert gain_open.session_pnl == Decimal("30")
    assert gain_open.position_pnl_from_entry == Decimal("50")
