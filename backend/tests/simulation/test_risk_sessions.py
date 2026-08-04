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
    state = initialize_risk_state(Decimal("1000"), date(2026, 1, 2))
    first_session = mark_risk_state(state, Decimal("900"), date(2026, 1, 2))
    next_session = mark_risk_state(first_session, Decimal("925"), date(2026, 1, 5))
    assert first_session.position_pnl_from_entry == Decimal("-100")
    assert first_session.session_pnl == Decimal("-100")
    assert next_session.position_pnl_from_entry == Decimal("-75")
    assert next_session.session_pnl == Decimal("0.00")
    later = mark_risk_state(next_session, Decimal("900"), date(2026, 1, 5))
    assert later.position_pnl_from_entry == Decimal("-100")
    assert later.session_pnl == Decimal("-25")


def test_session_hedge_count_resets_but_total_persists() -> None:
    state = initialize_risk_state(Decimal("1000"), date(2026, 1, 2))
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
    state = initialize_risk_state(Decimal("1000000"), date(2026, 1, 2))
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
    assert by_rule["daily_loss_limit"].observed_value == Decimal("2000")
    assert all(decision.session_date == date(2026, 1, 5) for decision in decisions)
