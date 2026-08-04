from dataclasses import fields
from decimal import Decimal

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config
from app.simulation.engine import run_simulation
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.simulation.state_builder import executable_market_state_hash
from app.strategy.config import load_strategy_config
from tests.simulation.support import sessions_for_path


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17),
        sessions_for_path(strategy, market, 15),
    )
    return strategy, market, path


def test_underlying_path_excludes_derived_contract_state() -> None:
    names = {field.name for field in fields(GBMPathConfig)}
    assert "option_expiry_years" not in names
    assert "futures_maturity_years" not in names
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    assert result.path_hash == path.path_hash
    assert result.executable_market_state_hash != result.path_hash


def test_result_market_state_hash_describes_exact_executed_states() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    assert result.executable_market_state_hash == executable_market_state_hash(result.market_states)


def test_option_expiry_and_futures_buffer_change_executable_state_identity() -> None:
    strategy, market, path = inputs()
    baseline = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    options = market.options.model_copy(update={"eligible_expiry_sessions": (10, 15)})
    later_expiry = run_simulation(
        strategy,
        market.model_copy(update={"options": options}),
        path,
        "no_hedge",
        ZERO,
        ZERO,
    )
    futures = market.futures.model_copy(
        update={"expiry_buffer_sessions": market.futures.expiry_buffer_sessions + 5}
    )
    later_future = run_simulation(
        strategy,
        market.model_copy(update={"futures": futures}),
        path,
        "no_hedge",
        ZERO,
        ZERO,
    )
    assert later_expiry.executable_market_state_hash != baseline.executable_market_state_hash
    assert later_future.executable_market_state_hash != baseline.executable_market_state_hash
    assert later_future.market_states[0].futures_price != baseline.market_states[0].futures_price
    assert later_future.run_id != baseline.run_id
