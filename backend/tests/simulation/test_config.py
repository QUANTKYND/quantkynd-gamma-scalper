from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.execution.models import ExecutionCostParameters
from app.simulation.config import (
    CostModelConfig,
    RuntimeRiskInputs,
    SimulationMarketConfig,
    SimulationRunConfig,
    load_simulation_market_config,
    simulation_market_config_hash,
    simulation_run_config_hash,
    stable_hash,
)


CONFIG = Path(__file__).parents[3] / "config/simulation/nifty-synthetic-market-v1.yaml"
HASH = "sha256:" + "a" * 64


def test_market_config_is_strict_and_hashable() -> None:
    config = load_simulation_market_config(CONFIG)
    assert config.options.multiplier == 1
    assert config.futures.delta_per_contract == 1
    assert simulation_market_config_hash(config) == simulation_market_config_hash(config)
    payload = config.model_dump(mode="python")
    payload["hidden"] = True
    with pytest.raises(ValidationError):
        SimulationMarketConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("multiplier", 25),
        ("strike_interval", 100),
        ("strikes_below", 3),
        ("eligible_expiry_sessions", (8, 10, 15)),
    ],
)
def test_behavioral_option_market_changes_change_hash(field: str, value: object) -> None:
    config = load_simulation_market_config(CONFIG)
    options = config.options.model_copy(update={field: value})
    changed = config.model_copy(update={"options": options})
    assert simulation_market_config_hash(changed) != simulation_market_config_hash(config)


def test_cost_model_round_trip() -> None:
    parameters = ExecutionCostParameters(Decimal("1"), Decimal("0.01"), Decimal("2"), Decimal("3"))
    assert CostModelConfig.from_parameters(parameters).to_parameters() == parameters


def test_futures_execution_spread_is_owned_only_by_run_cost_model() -> None:
    config = load_simulation_market_config(CONFIG)
    assert not hasattr(config.futures, "half_spread_per_unit")
    payload = config.model_dump(mode="python")
    payload["futures"]["half_spread_per_unit"] = Decimal("0.25")
    with pytest.raises(ValidationError):
        SimulationMarketConfig.model_validate(payload)


def test_run_config_identity_includes_runtime_and_accounting_inputs() -> None:
    costs = CostModelConfig(
        fixed_cost_per_order=Decimal("0"),
        proportional_notional_rate=Decimal("0"),
        half_spread_per_unit=Decimal("0"),
        slippage_per_unit=Decimal("0"),
    )
    base = SimulationRunConfig(
        schema_version=1,
        simulator_version="sim-1.1",
        strategy_config_hash=HASH,
        market_config_hash=HASH,
        path_config_hash=HASH,
        path_hash=HASH,
        policy_id="no_hedge",
        policy_parameters={},
        option_cost_model=costs,
        futures_cost_model=costs,
        runtime_risk_inputs=RuntimeRiskInputs(manual_kill_switch_engaged=False),
        accounting_tolerance=Decimal("0.01"),
        quantity_rounding="nearest_integer_half_even",
    )
    killed = base.model_copy(update={"runtime_risk_inputs": RuntimeRiskInputs(manual_kill_switch_engaged=True)})
    tolerance = base.model_copy(update={"accounting_tolerance": Decimal("0.02")})
    assert simulation_run_config_hash(base) != simulation_run_config_hash(killed)
    assert simulation_run_config_hash(base) != simulation_run_config_hash(tolerance)
    assert stable_hash({"b": 1.0, "a": Decimal("2.00")}) == stable_hash({"a": 2, "b": 1})
