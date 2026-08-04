from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.execution.models import ExecutionCostParameters
from app.simulation.config import (
    CostModelConfig,
    RuntimeRiskInputs,
    SimulationEntryAssumptions,
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
    assert config.schema_version == 2
    assert config.options.multiplier == 1
    assert config.futures.delta_per_contract == 1
    assert simulation_market_config_hash(config) == simulation_market_config_hash(config)
    payload = config.model_dump(mode="python")
    payload["hidden"] = True
    with pytest.raises(ValidationError):
        SimulationMarketConfig.model_validate(payload)


@pytest.mark.parametrize("schema_version", [1, 3])
def test_market_loader_rejects_unsupported_schema_explicitly(
    tmp_path: Path, schema_version: int
) -> None:
    payload = load_simulation_market_config(CONFIG).model_dump(mode="json")
    payload["schema_version"] = schema_version
    config_path = tmp_path / "market.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        ValueError,
        match=f"unsupported simulation-market schema version: {schema_version}",
    ):
        load_simulation_market_config(config_path)


def test_market_schema_version_participates_in_hash() -> None:
    config = load_simulation_market_config(CONFIG)
    legacy_payload = config.model_dump(mode="json")
    legacy_payload["schema_version"] = 1
    assert simulation_market_config_hash(config) != stable_hash(legacy_payload)


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
        schema_version=2,
        simulator_version="sim-1.2",
        strategy_config_hash=HASH,
        market_config_hash=HASH,
        path_config_hash=HASH,
        path_hash=HASH,
        policy_id="no_hedge",
        policy_parameters={},
        option_cost_model=costs,
        futures_cost_model=costs,
        runtime_risk_inputs=RuntimeRiskInputs(manual_kill_switch_engaged=False),
        entry_assumptions=SimulationEntryAssumptions(
            edge_gate_mode="not_evaluated_hedge_policy_benchmark"
        ),
        accounting_tolerance=Decimal("0.01"),
        quantity_rounding="nearest_integer_half_even",
    )
    killed = base.model_copy(update={"runtime_risk_inputs": RuntimeRiskInputs(manual_kill_switch_engaged=True)})
    tolerance = base.model_copy(update={"accounting_tolerance": Decimal("0.02")})
    assert simulation_run_config_hash(base) != simulation_run_config_hash(killed)
    assert simulation_run_config_hash(base) != simulation_run_config_hash(tolerance)
    assert stable_hash({"b": 1.0, "a": Decimal("2.00")}) == stable_hash({"a": 2, "b": 1})


def test_legacy_run_schema_is_distinct_and_rejected() -> None:
    costs = CostModelConfig(
        fixed_cost_per_order=Decimal("0"),
        proportional_notional_rate=Decimal("0"),
        half_spread_per_unit=Decimal("0"),
        slippage_per_unit=Decimal("0"),
    )
    current = SimulationRunConfig(
        schema_version=2,
        simulator_version="sim-1.2",
        strategy_config_hash=HASH,
        market_config_hash=HASH,
        path_config_hash=HASH,
        path_hash=HASH,
        policy_id="no_hedge",
        policy_parameters={},
        option_cost_model=costs,
        futures_cost_model=costs,
        runtime_risk_inputs=RuntimeRiskInputs(manual_kill_switch_engaged=False),
        entry_assumptions=SimulationEntryAssumptions(
            edge_gate_mode="not_evaluated_hedge_policy_benchmark"
        ),
        accounting_tolerance=Decimal("0.01"),
        quantity_rounding="nearest_integer_half_even",
    )
    legacy_payload = current.model_dump(mode="python")
    legacy_payload["schema_version"] = 1
    assert simulation_run_config_hash(current) != stable_hash(legacy_payload)
    with pytest.raises(ValidationError):
        SimulationRunConfig.model_validate(legacy_payload)
