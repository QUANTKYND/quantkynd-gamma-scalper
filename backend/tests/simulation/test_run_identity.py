from decimal import Decimal

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config, simulation_run_config_hash
from app.simulation.engine import SIMULATOR_VERSION, build_simulation_run_config, simulation_run_id
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config
from tests.simulation.support import sessions_for_path


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17), sessions_for_path(strategy, market, 15))
    return strategy, market, path


def test_runtime_risk_and_accounting_tolerance_change_run_identity() -> None:
    strategy, market, path = inputs()
    base = build_simulation_run_config(strategy, market, path, "no_hedge", ZERO, ZERO)
    killed = build_simulation_run_config(
        strategy,
        market,
        path,
        "no_hedge",
        ZERO,
        ZERO,
        manual_kill_switch_engaged=True,
    )
    tolerant = build_simulation_run_config(
        strategy,
        market,
        path,
        "no_hedge",
        ZERO,
        ZERO,
        accounting_tolerance=Decimal("0.02"),
    )
    assert len({simulation_run_id(base), simulation_run_id(killed), simulation_run_id(tolerant)}) == 3


def test_policy_parameters_are_in_run_contract() -> None:
    strategy, market, path = inputs()
    base = build_simulation_run_config(strategy, market, path, "constant_band", ZERO, ZERO)
    parameters = strategy.hedging.constant_band.model_copy(update={"lower_net_delta_units": -0.1})
    hedging = strategy.hedging.model_copy(update={"constant_band": parameters})
    changed = strategy.model_copy(update={"hedging": hedging})
    alternate = build_simulation_run_config(changed, market, path, "constant_band", ZERO, ZERO)
    assert base.policy_parameters != alternate.policy_parameters
    assert simulation_run_id(base) != simulation_run_id(alternate)


def test_simulator_version_changes_run_hash_and_id() -> None:
    strategy, market, path = inputs()
    current = build_simulation_run_config(strategy, market, path, "no_hedge", ZERO, ZERO)
    legacy = current.model_copy(update={"simulator_version": "sim-1.1"})
    assert SIMULATOR_VERSION == "sim-1.2"
    assert current.simulator_version == SIMULATOR_VERSION
    assert current.schema_version == 2
    assert simulation_run_config_hash(current) != simulation_run_config_hash(legacy)
    assert simulation_run_id(current) != simulation_run_id(legacy)
