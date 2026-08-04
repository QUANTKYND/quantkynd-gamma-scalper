from dataclasses import replace
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config, simulation_market_config_hash
from app.simulation.engine import run_simulation
from app.simulation.clock import expiry_for_remaining_sessions
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.strategy.config import load_strategy_config
from tests.simulation.support import sessions_for_path


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17), sessions_for_path(strategy, market, 15))
    return strategy, market, path


def test_engine_uses_market_contract_for_options_expiry_and_strike() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    assert result.call_contract.multiplier == market.options.multiplier
    assert result.put_contract.multiplier == market.options.multiplier
    assert result.call_contract.expiry == expiry_for_remaining_sessions(
        result.market_states[0].session_date,
        7,
        market.clock,
    ).expiry_session_date
    assert result.call_contract.strike % market.options.strike_interval == 0


def test_option_valuation_units_scale_to_position_economics() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    valuation = result.option_valuations[0]
    scale = valuation.quantity * valuation.multiplier
    assert valuation.market_value == Decimal(str(round(valuation.unit_price * scale, 2)))
    assert valuation.portfolio_delta == pytest.approx(valuation.unit_delta * scale)
    assert valuation.portfolio_gamma == pytest.approx(valuation.unit_gamma * scale)
    assert valuation.portfolio_theta_per_year == pytest.approx(valuation.unit_theta_per_year * scale)
    assert valuation.portfolio_vega_per_volatility_unit == pytest.approx(
        valuation.unit_vega_per_volatility_unit * scale
    )


def test_engine_uses_futures_multiplier_and_delta_per_contract() -> None:
    strategy, market, path = inputs()
    shocked = replace(
        path,
        points=path.points[:1]
        + tuple(
            replace(point, spot=point.spot * 1.5)
            for point in path.points[1:]
        ),
    )
    result = run_simulation(strategy, market, shocked, "fixed_interval", ZERO, ZERO)
    futures_fills = [fill for fill in result.fills if fill.instrument_id == market.futures.instrument_id]
    assert futures_fills
    assert all(fill.multiplier == market.futures.multiplier for fill in futures_fills)
    assert result.futures_delta_per_contract == market.futures.delta_per_contract


def test_market_behavior_changes_run_identity() -> None:
    strategy, market, path = inputs()
    strategy = strategy.model_copy(
        update={"risk": strategy.risk.model_copy(update={"maximum_daily_theta_fraction": 1.0})}
    )
    base = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    options = market.options.model_copy(update={"multiplier": 25})
    changed = market.model_copy(update={"options": options})
    alternate = run_simulation(strategy, changed, path, "no_hedge", ZERO, ZERO)
    assert alternate.run_id != base.run_id
    assert alternate.market_config_hash != base.market_config_hash


def test_option_multiplier_scales_premium_risk_and_blocks_before_ledger_fills(monkeypatch) -> None:
    strategy, market, path = inputs()
    baseline = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    baseline_premium = next(
        decision.observed_value
        for decision in baseline.risk_decisions
        if decision.rule_id == "maximum_premium_at_risk"
    )
    options = market.options.model_copy(update={"multiplier": 100})
    changed = market.model_copy(update={"options": options})

    def reject_persisted_fill(*args, **kwargs):
        pytest.fail("entry fill was persisted before premium risk approval")

    monkeypatch.setattr("app.simulation.engine.PortfolioLedger.record_fill", reject_persisted_fill)
    with pytest.raises(ValueError, match="premium_at_risk_breached"):
        run_simulation(strategy, changed, path, "no_hedge", ZERO, ZERO)
    assert baseline_premium > Decimal("0")


def test_option_entry_costs_are_included_in_premium_risk() -> None:
    strategy, market, path = inputs()
    costs = ExecutionCostParameters(Decimal("10"), Decimal("0.001"), Decimal("1"), Decimal("2"))
    result = run_simulation(strategy, market, path, "no_hedge", costs, ZERO)
    premium = next(
        decision.observed_value
        for decision in result.risk_decisions
        if decision.rule_id == "maximum_premium_at_risk"
    )
    entry_fills = result.fills[:2]
    assert premium == sum(
        (fill.gross_notional + fill.total_cost for fill in entry_fills),
        start=Decimal("0"),
    )


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
