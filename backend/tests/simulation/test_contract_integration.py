from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config, simulation_market_config_hash
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
    return strategy, market, path


def test_engine_uses_market_contract_for_options_expiry_and_strike() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    assert result.call_contract.multiplier == market.options.multiplier
    assert result.put_contract.multiplier == market.options.multiplier
    assert result.call_contract.expiry == result.market_states[0].session_date.replace(day=12)
    assert result.call_contract.strike % market.options.strike_interval == 0


def test_engine_uses_futures_multiplier_and_delta_per_contract() -> None:
    strategy, market, path = inputs()
    shocked = replace(
        path,
        states=path.states[:1]
        + tuple(
            replace(state, spot=state.spot * 1.5, futures_price=state.futures_price * 1.5)
            for state in path.states[1:]
        ),
        path_hash="sha256:" + "9" * 64,
    )
    result = run_simulation(strategy, market, shocked, "fixed_interval", ZERO, ZERO)
    futures_fills = [fill for fill in result.fills if fill.instrument_id == market.futures.instrument_id]
    assert futures_fills
    assert all(fill.multiplier == market.futures.multiplier for fill in futures_fills)
    assert result.futures_delta_per_contract == market.futures.delta_per_contract


def test_market_behavior_changes_run_identity() -> None:
    strategy, market, path = inputs()
    base = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    options = market.options.model_copy(update={"multiplier": 25})
    changed = market.model_copy(update={"options": options})
    alternate = run_simulation(strategy, changed, path, "no_hedge", ZERO, ZERO)
    assert alternate.run_id != base.run_id
    assert alternate.market_config_hash != base.market_config_hash


def test_no_eligible_expiry_fails_explicitly() -> None:
    strategy, market, path = inputs()
    options = market.options.model_copy(update={"eligible_expiry_sessions": (2, 3)})
    changed = market.model_copy(update={"options": options})
    with pytest.raises(ValueError, match="no eligible expiry"):
        run_simulation(strategy, changed, path, "no_hedge", ZERO, ZERO)


def test_strike_grid_change_is_hashed() -> None:
    _, market, _ = inputs()
    options = market.options.model_copy(update={"strike_interval": 100})
    changed = market.model_copy(update={"options": options})
    assert simulation_market_config_hash(changed) != simulation_market_config_hash(market)
