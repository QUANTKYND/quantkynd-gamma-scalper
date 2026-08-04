from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.execution.models import ExecutionCostParameters
from app.simulation.config import (
    CostModelConfig,
    SimulationMarketConfig,
    SimulationRunConfig,
    load_simulation_market_config,
)
from app.simulation.engine import build_simulation_run_config
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config
from app.strategy.models import StrategyContractV1
from tests.simulation.support import sessions_for_path


STRATEGY_CONFIG = Path("../config/strategies/nifty-long-gamma-v1.yaml")
MARKET_CONFIG = Path("../config/simulation/nifty-synthetic-market-v1.yaml")
ZERO_COSTS = ExecutionCostParameters(*(Decimal("0"),) * 4)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("risk", "starting_nav_inr"),
        ("risk", "maximum_daily_loss_fraction"),
        ("risk", "maximum_absolute_delta_units"),
        ("hedging.whalley_wilmott", "risk_aversion_per_inr"),
        ("hedging.whalley_wilmott", "transaction_cost_rate"),
        ("hedging.delta_threshold", "maximum_absolute_net_delta_units"),
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_strategy_rejects_nonfinite_values(section: str, field: str, value: float) -> None:
    payload = load_strategy_config(STRATEGY_CONFIG).model_dump(mode="python")
    target = payload
    for part in section.split("."):
        target = target[part]
    target[field] = value
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("options", "strike_interval"),
        ("options", "relative_spread"),
        ("futures", "delta_per_contract"),
        ("clock", "trading_periods_per_year"),
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_market_config_rejects_nonfinite_values(section: str, field: str, value: float) -> None:
    payload = load_simulation_market_config(MARKET_CONFIG).model_dump(mode="python")
    payload[section][field] = value
    with pytest.raises(ValidationError):
        SimulationMarketConfig.model_validate(payload)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_cost_models_reject_nonfinite_values(value: Decimal) -> None:
    with pytest.raises(ValueError):
        ExecutionCostParameters(value, Decimal("0"), Decimal("0"), Decimal("0"))
    with pytest.raises(ValidationError):
        CostModelConfig(
            fixed_cost_per_order=value,
            proportional_notional_rate=Decimal("0"),
            half_spread_per_unit=Decimal("0"),
            slippage_per_unit=Decimal("0"),
        )


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_run_config_rejects_nonfinite_accounting_tolerance(value: Decimal) -> None:
    strategy = load_strategy_config(STRATEGY_CONFIG)
    market = load_simulation_market_config(MARKET_CONFIG)
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 3, 1 / (252 * 3), 17),
        sessions_for_path(strategy, market, 3),
    )
    valid = build_simulation_run_config(
        strategy,
        market,
        path,
        "no_hedge",
        ZERO_COSTS,
        ZERO_COSTS,
    )
    payload = valid.model_dump(mode="python")
    payload["accounting_tolerance"] = value
    with pytest.raises(ValidationError):
        SimulationRunConfig.model_validate(payload)
