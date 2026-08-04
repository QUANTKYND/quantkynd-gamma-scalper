from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.engine import run_simulation
from app.simulation.config import load_simulation_market_config
from app.simulation.metrics import summarize
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def result():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 5, 1 / 252, 17, datetime(2026, 1, 1, tzinfo=UTC))
    )
    return run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)


def test_component_sum_plus_residual_matches_exact_option_change() -> None:
    for item in result().pnl_attribution:
        total = (
            item.delta_contribution
            + item.gamma_contribution
            + item.theta_contribution
            + item.vega_contribution
            + item.residual
        )
        assert total == pytest.approx(item.exact_option_mark_change)


def test_constant_volatility_has_zero_vega_contribution_and_long_theta_is_negative() -> None:
    attribution = result().pnl_attribution
    assert all(item.vega_contribution == 0 for item in attribution)
    assert sum(item.theta_contribution for item in attribution) < 0


def test_summary_is_separate_from_exact_reconciliation_and_has_units() -> None:
    simulation = result()
    summary = summarize(simulation)
    assert summary.terminal_net_pnl == simulation.reconciliation.terminal_pnl
    assert summary.ledger_reconciliation_residual == Decimal("0.00")
    assert summary.attribution_residual != 0
    assert summary.units["money"] == "INR"
