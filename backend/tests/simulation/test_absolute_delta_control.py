from dataclasses import replace
from decimal import Decimal

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config
from app.simulation.engine import run_simulation
from app.simulation.paths import GBMPathConfig, generate_gbm_path, replace_path_points
from app.strategy.config import load_strategy_config
from tests.simulation.support import sessions_for_path


ZERO_COSTS = ExecutionCostParameters(*(Decimal("0"),) * 4)


def shocked_inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17),
        sessions_for_path(strategy, market, 15),
    )
    shocked = replace_path_points(
        path,
        path.points[:1]
        + tuple(replace(point, spot=point.spot * 1.5) for point in path.points[1:]),
    )
    return strategy, market, shocked


def test_hard_delta_limit_overrides_no_hedge_policy() -> None:
    strategy, market, path = shocked_inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO_COSTS, ZERO_COSTS)
    forced = [
        decision
        for decision in result.hedge_decisions
        if decision.reason_code == "absolute_delta_forced_hedge"
    ]
    assert forced
    assert all(
        abs(decision.net_delta_after_fill) <= strategy.risk.maximum_absolute_delta_units
        and abs(decision.net_delta_after_fill) < abs(decision.net_delta_before_decision)
        for decision in forced
    )
    assert all(
        abs(decision.net_delta_after_fill) <= strategy.risk.maximum_absolute_delta_units
        for decision in result.hedge_decisions
    )
    assert any(
        decision.reason_code == "absolute_delta_forced_hedge"
        and decision.decision == "override"
        for decision in result.risk_decisions
    )
    assert any(
        intent.reason_code == "absolute_delta_forced_hedge" for intent in result.order_intents
    )


def test_unhedgeable_delta_exits_without_executing_a_non_reducing_fill() -> None:
    strategy, market, path = shocked_inputs()
    coarse_market = market.model_copy(
        update={"futures": market.futures.model_copy(update={"delta_per_contract": 10.0})}
    )
    result = run_simulation(strategy, coarse_market, path, "no_hedge", ZERO_COSTS, ZERO_COSTS)
    terminal_decision = result.hedge_decisions[-1]
    assert result.exit_reason == "absolute_delta_unhedgeable"
    assert result.hedge_count == 0
    assert terminal_decision.reason_code == "absolute_delta_unhedgeable"
    assert terminal_decision.executed_futures_quantity == 0
    assert any(
        decision.decision == "exit" and decision.reason_code == "absolute_delta_unhedgeable"
        for decision in result.risk_decisions
    )
    assert any(event.event_type == "risk_control_failed" for event in result.events)
    assert any(event.event_type == "exit_required" for event in result.events)
