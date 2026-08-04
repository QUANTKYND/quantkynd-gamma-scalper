from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config
from app.simulation.engine import run_simulation
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 5, 1 / 252, 17, datetime(2026, 1, 1, tzinfo=UTC))
    )
    shocked = replace(
        path,
        states=path.states[:1]
        + tuple(
            replace(state, spot=state.spot * 1.5, futures_price=state.futures_price * 1.5)
            for state in path.states[1:]
        ),
        path_hash="sha256:" + "8" * 64,
    )
    return strategy, market, shocked


def hedge_intents_at(result, timestamp):
    return [
        intent
        for intent in result.order_intents
        if intent.timestamp == timestamp and "-hedge-" in intent.intent_id
    ]


def test_maximum_holding_exit_occurs_before_new_hedge() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "fixed_interval", ZERO, ZERO)
    assert result.exit_reason == "maximum_holding_period"
    assert not hedge_intents_at(result, result.market_states[-1].timestamp)


def test_kill_switch_exit_occurs_before_policy() -> None:
    strategy, market, path = inputs()
    result = run_simulation(
        strategy,
        market,
        path,
        "fixed_interval",
        ZERO,
        ZERO,
        manual_kill_switch_engaged=True,
    )
    assert result.exit_reason == "manual_kill_switch"
    assert not hedge_intents_at(result, result.market_states[-1].timestamp)


def test_insufficient_time_exit_occurs_before_new_hedge() -> None:
    strategy, market, path = inputs()
    expiry = strategy.expiry.model_copy(update={"safety_buffer_sessions": 7})
    constrained = strategy.model_copy(update={"expiry": expiry})
    short = replace(path, states=path.states[:2], path_hash="sha256:" + "7" * 64)
    options = market.options.model_copy(update={"eligible_expiry_sessions": (7,)})
    result = run_simulation(constrained, market.model_copy(update={"options": options}), short, "fixed_interval", ZERO, ZERO)
    assert result.exit_reason == "insufficient_time_to_expiry"
    assert not hedge_intents_at(result, result.market_states[-1].timestamp)


def test_daily_loss_precedes_position_loss_without_opening_hedge() -> None:
    strategy, market, path = inputs()
    risk = strategy.risk.model_copy(
        update={
            "maximum_daily_loss_fraction": 0.000001,
            "maximum_position_loss_fraction": 0.000001,
        }
    )
    constrained = strategy.model_copy(update={"risk": risk})
    collapsed = replace(
        path,
        states=path.states[:1]
        + tuple(
            replace(
                state,
                spot=path.states[0].spot,
                futures_price=path.states[0].futures_price,
                implied_volatility=0.0,
            )
            for state in path.states[1:]
        ),
        path_hash="sha256:" + "6" * 64,
    )
    result = run_simulation(constrained, market, collapsed, "fixed_interval", ZERO, ZERO)
    assert result.exit_reason == "daily_loss_limit"
    assert not hedge_intents_at(result, result.market_states[-1].timestamp)


def test_truncated_path_exits_before_last_timestamp_hedge() -> None:
    strategy, market, path = inputs()
    truncated = replace(path, states=path.states[:2], path_hash="sha256:" + "5" * 64)
    result = run_simulation(strategy, market, truncated, "fixed_interval", ZERO, ZERO)
    assert result.exit_reason == "simulation_end"
    assert not hedge_intents_at(result, result.market_states[-1].timestamp)
