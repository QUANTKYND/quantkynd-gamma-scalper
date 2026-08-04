from dataclasses import replace
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.engine import run_simulation
from app.simulation.config import load_simulation_market_config
from app.simulation.metrics import summarize
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config
from app.simulation.paths import replace_path_points
from tests.simulation.support import sessions_for_path


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v2.yaml")
    path = generate_gbm_path(GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17), sessions_for_path(strategy, market, 15))
    return strategy, market, path


def relaxed_delta_limit(strategy):
    return strategy.model_copy(
        update={"risk": strategy.risk.model_copy(update={"maximum_absolute_delta_units": 10.0})}
    )


def test_engine_is_deterministic_and_reconciles() -> None:
    strategy, market, path = inputs()
    strategy = relaxed_delta_limit(strategy)
    first = run_simulation(strategy, market, path, "constant_band", ZERO, ZERO)
    second = run_simulation(strategy, market, path, "constant_band", ZERO, ZERO)
    assert first == second
    assert first.status == "complete"
    assert first.reconciliation.reconciled
    assert first.reconciliation.residual == Decimal("0.00")
    assert first.exit_reason == "maximum_holding_period"


def test_premium_at_risk_blocks_entry() -> None:
    strategy, market, path = inputs()
    risk = strategy.risk.model_copy(update={"maximum_premium_at_risk_fraction": 0.000001})
    constrained = strategy.model_copy(update={"risk": risk})
    with pytest.raises(ValueError, match="premium_at_risk_breached"):
        run_simulation(constrained, market, path, "no_hedge", ZERO, ZERO)


def test_manual_kill_switch_exits_reconstructably() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO, manual_kill_switch_engaged=True)
    assert result.exit_reason == "manual_kill_switch"
    assert any(record.reason_code == "manual_kill_switch_engaged" for record in result.risk_decisions)


def test_maximum_hedge_count_triggers_exit() -> None:
    strategy, market, path = inputs()
    risk = strategy.risk.model_copy(update={"maximum_hedges_per_session": 1})
    constrained = strategy.model_copy(update={"risk": risk})
    shocked_points = path.points[:1] + tuple(
        replace(
            point,
            spot=point.spot * 1.5,
        )
        for point in path.points[1:]
    )
    shocked = replace_path_points(path, shocked_points)
    result = run_simulation(constrained, market, shocked, "fixed_interval", ZERO, ZERO)
    assert result.hedge_count == 1
    assert result.exit_reason == "maximum_hedge_count"


def test_future_path_changes_do_not_change_earlier_decisions() -> None:
    strategy, market, path = inputs()
    changed_points = path.points[:3] + tuple(
        replace(point, spot=point.spot * 1.5) for point in path.points[3:]
    )
    changed = replace_path_points(path, changed_points)
    first = run_simulation(strategy, market, path, "constant_band", ZERO, ZERO)
    second = run_simulation(strategy, market, changed, "constant_band", ZERO, ZERO)
    assert first.hedge_decisions[:3] == second.hedge_decisions[:3]


def test_frictionless_hedging_reduces_delta_error_on_controlled_path() -> None:
    strategy, market, path = inputs()
    strategy = relaxed_delta_limit(strategy)
    shocked_points = path.points[:1] + tuple(
        replace(point, spot=point.spot * 1.5)
        for point in path.points[1:]
    )
    shocked = replace_path_points(path, shocked_points)
    unhedged_result = run_simulation(strategy, market, shocked, "no_hedge", ZERO, ZERO)
    hedged_result = run_simulation(strategy, market, shocked, "fixed_interval", ZERO, ZERO)
    unhedged = summarize(unhedged_result)
    hedged = summarize(hedged_result)
    assert hedged.post_hedge_residual_delta_rmse < unhedged.post_hedge_residual_delta_rmse
    traded = [decision for decision in hedged_result.hedge_decisions if decision.executed_futures_quantity]
    assert traded
    assert all(abs(decision.net_delta_after_fill) < abs(decision.net_delta_before_decision) for decision in traded)


def test_hold_decisions_preserve_timed_delta_and_summary_uses_each_timing() -> None:
    strategy, market, path = inputs()
    strategy = relaxed_delta_limit(strategy)
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    assert result.hedge_decisions
    assert all(
        decision.net_delta_before_decision == decision.net_delta_after_fill
        and decision.rounded_requested_futures_quantity == 0
        and decision.executed_futures_quantity == 0
        for decision in result.hedge_decisions
    )
    summary = summarize(result)
    assert summary.maximum_absolute_pre_hedge_net_delta == max(
        abs(decision.net_delta_before_decision) for decision in result.hedge_decisions
    )
    assert summary.maximum_absolute_post_hedge_residual_delta == max(
        abs(decision.net_delta_after_fill) for decision in result.hedge_decisions
    )


def test_decision_event_records_aligned_before_and_after_state() -> None:
    strategy, market, path = inputs()
    strategy = relaxed_delta_limit(strategy)
    costs = ExecutionCostParameters(Decimal("5"), Decimal("0"), Decimal("0.25"), Decimal("0"))
    result = run_simulation(strategy, market, path, "fixed_interval", ZERO, costs)
    events = [event for event in result.events if event.event_type == "decision_completed"]
    assert len(events) == len(result.hedge_decisions)
    for event, decision in zip(events, result.hedge_decisions, strict=True):
        assert event.timestamp == decision.timestamp
        assert event.details["net_delta_before_decision"] == decision.net_delta_before_decision
        assert event.details["net_delta_after_fill"] == decision.net_delta_after_fill
        assert event.details["portfolio_value_before_fill"] == str(decision.portfolio_value_before_fill)
        assert event.details["portfolio_value_after_fill"] == str(decision.portfolio_value_after_fill)


def test_more_trading_increases_modeled_costs() -> None:
    strategy, market, path = inputs()
    strategy = relaxed_delta_limit(strategy)
    shocked_points = path.points[:1] + tuple(
        replace(point, spot=point.spot * 1.5)
        for point in path.points[1:]
    )
    shocked = replace_path_points(path, shocked_points)
    costs = ExecutionCostParameters(Decimal("5"), Decimal("0.001"), Decimal("0.25"), Decimal("0.10"))
    unhedged = summarize(run_simulation(strategy, market, shocked, "no_hedge", ZERO, costs))
    hedged = summarize(run_simulation(strategy, market, shocked, "fixed_interval", ZERO, costs))
    assert hedged.hedge_count > unhedged.hedge_count
    assert hedged.total_transaction_costs > unhedged.total_transaction_costs


@pytest.mark.parametrize(
    ("daily_fraction", "position_fraction", "expected_reason"),
    [(1.0, 0.0001, "position_loss_limit"), (0.0001, 1.0, "daily_loss_limit")],
)
def test_loss_limits_exit_deterministically(
    daily_fraction: float,
    position_fraction: float,
    expected_reason: str,
) -> None:
    strategy, market, path = inputs()
    collapsed_points = path.points[:1] + tuple(
        replace(
            point,
            spot=path.points[0].spot,
            implied_volatility=0.0,
        )
        for point in path.points[1:]
    )
    collapsed = replace_path_points(path, collapsed_points)
    risk = strategy.risk.model_copy(
        update={
            "maximum_daily_loss_fraction": daily_fraction,
            "maximum_position_loss_fraction": position_fraction,
        }
    )
    constrained = strategy.model_copy(update={"risk": risk})
    result = run_simulation(constrained, market, collapsed, "no_hedge", ZERO, ZERO)
    assert result.exit_reason == expected_reason
    assert any(record.reason_code == f"{expected_reason}_breached" for record in result.risk_decisions)


def test_overnight_gap_can_trigger_daily_loss_at_first_new_session_decision() -> None:
    strategy, market, path = inputs()
    first_session_date = path.points[0].session_date
    next_session_date = next(
        point.session_date for point in path.points if point.session_date != first_session_date
    )
    controlled = replace_path_points(
        path,
        tuple(
            replace(
                point,
                spot=path.points[0].spot,
                implied_volatility=0.0 if point.session_date == next_session_date else 0.18,
            )
            for point in path.points
        ),
    )
    risk = strategy.risk.model_copy(
        update={
            "maximum_daily_loss_fraction": 0.0001,
            "maximum_position_loss_fraction": 1.0,
            "maximum_absolute_delta_units": 10.0,
        }
    )
    result = run_simulation(
        strategy.model_copy(update={"risk": risk}),
        market,
        controlled,
        "no_hedge",
        ZERO,
        ZERO,
    )
    first_new_session_timestamp = next(
        point.timestamp for point in controlled.points if point.session_date == next_session_date
    )
    assert result.exit_reason == "daily_loss_limit"
    exit_event = next(event for event in result.events if event.event_type == "exit_required")
    assert exit_event.timestamp == first_new_session_timestamp
