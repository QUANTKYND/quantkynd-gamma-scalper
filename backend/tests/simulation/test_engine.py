from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.engine import run_simulation
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 5, 1 / 252, 17, datetime(2026, 1, 1, tzinfo=UTC))
    )
    return strategy, path


def test_engine_is_deterministic_and_reconciles() -> None:
    strategy, path = inputs()
    first = run_simulation(strategy, path, "constant_band", ZERO, ZERO)
    second = run_simulation(strategy, path, "constant_band", ZERO, ZERO)
    assert first == second
    assert first.status == "complete"
    assert first.reconciliation.reconciled
    assert first.reconciliation.residual == Decimal("0.00")
    assert first.exit_reason == "maximum_holding_period"


def test_premium_at_risk_blocks_entry() -> None:
    strategy, path = inputs()
    risk = strategy.risk.model_copy(update={"maximum_premium_at_risk_fraction": 0.000001})
    constrained = strategy.model_copy(update={"risk": risk})
    with pytest.raises(ValueError, match="premium_at_risk_breached"):
        run_simulation(constrained, path, "no_hedge", ZERO, ZERO)


def test_manual_kill_switch_exits_reconstructably() -> None:
    strategy, path = inputs()
    result = run_simulation(strategy, path, "no_hedge", ZERO, ZERO, manual_kill_switch_engaged=True)
    assert result.exit_reason == "manual_kill_switch"
    assert any(record.reason_code == "manual_kill_switch_engaged" for record in result.risk_decisions)


def test_maximum_hedge_count_triggers_exit() -> None:
    strategy, path = inputs()
    risk = strategy.risk.model_copy(update={"maximum_hedges_per_session": 1})
    constrained = strategy.model_copy(update={"risk": risk})
    shocked_states = path.states[:1] + tuple(
        replace(state, spot=state.spot * 1.5, futures_price=state.futures_price * 1.5)
        for state in path.states[1:]
    )
    shocked = replace(path, states=shocked_states, path_hash="sha256:" + "e" * 64)
    result = run_simulation(constrained, shocked, "fixed_interval", ZERO, ZERO)
    assert result.hedge_count == 1
    assert result.exit_reason == "maximum_hedge_count"


def test_future_path_changes_do_not_change_earlier_decisions() -> None:
    strategy, path = inputs()
    changed_states = path.states[:3] + tuple(replace(state, spot=state.spot * 1.5, futures_price=state.futures_price * 1.5) for state in path.states[3:])
    changed = replace(path, states=changed_states, path_hash="sha256:" + "f" * 64)
    first = run_simulation(strategy, path, "constant_band", ZERO, ZERO)
    second = run_simulation(strategy, changed, "constant_band", ZERO, ZERO)
    assert first.hedge_decisions[:3] == second.hedge_decisions[:3]
