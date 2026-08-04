from dataclasses import replace
from decimal import Decimal

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.config import load_simulation_market_config
from app.simulation.engine import run_simulation, select_simulation_contracts
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.simulation.risk import entry_risk_decisions
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


@pytest.mark.parametrize(
    ("market_update", "reason"),
    [
        ({"relative_spread": 0.11}, "option_spread_breached"),
        ({"synthetic_volume_base": 0}, "option_volume_breached"),
        ({"synthetic_open_interest_base": 0}, "option_open_interest_breached"),
    ],
)
def test_quote_quality_and_liquidity_reject_before_entry_fill(
    market_update: dict[str, object],
    reason: str,
    monkeypatch,
) -> None:
    strategy, market, path = inputs()
    changed = market.model_copy(update={"options": market.options.model_copy(update=market_update)})

    def reject_persisted_fill(*args, **kwargs):
        pytest.fail("entry fill persisted before entry risk approval")

    monkeypatch.setattr("app.simulation.engine.PortfolioLedger.record_fill", reject_persisted_fill)
    with pytest.raises(ValueError, match=reason):
        run_simulation(strategy, changed, path, "no_hedge", ZERO, ZERO)


def test_passing_entry_records_quality_theta_and_edge_dispositions() -> None:
    strategy, market, path = inputs()
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    entry = {decision.rule_id: decision for decision in result.risk_decisions[:7]}
    assert entry["option_spread_quality"].decision == "approve"
    assert entry["option_volume_quality"].decision == "approve"
    assert entry["option_open_interest_quality"].decision == "approve"
    assert entry["matched_straddle_integrity"].decision == "approve"
    assert entry["maximum_daily_theta"].decision == "approve"
    assert entry["minimum_expected_net_edge"].decision == "not_evaluated"
    assert entry["minimum_expected_net_edge"].reason_code == "deferred_to_edge_1"
    assert result.run_config.entry_assumptions.edge_gate_mode == "not_evaluated_hedge_policy_benchmark"


def test_tight_daily_theta_limit_rejects_and_multiplier_scales_burden() -> None:
    strategy, market, path = inputs()
    base = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    base_theta = next(
        item.observed_value for item in base.risk_decisions if item.rule_id == "maximum_daily_theta"
    )
    risk = strategy.risk.model_copy(
        update={"maximum_daily_theta_fraction": 0.000001, "maximum_premium_at_risk_fraction": 1.0}
    )
    constrained = strategy.model_copy(update={"risk": risk})
    with pytest.raises(ValueError, match="daily_theta_breached"):
        run_simulation(constrained, market, path, "no_hedge", ZERO, ZERO)
    doubled_market = market.model_copy(
        update={"options": market.options.model_copy(update={"multiplier": 2})}
    )
    doubled = run_simulation(strategy, doubled_market, path, "no_hedge", ZERO, ZERO)
    doubled_theta = next(
        item.observed_value for item in doubled.risk_decisions if item.rule_id == "maximum_daily_theta"
    )
    assert doubled_theta == pytest.approx(base_theta * 2, abs=Decimal("0.01"))


def test_mismatched_multiplier_has_explicit_integrity_rejection() -> None:
    strategy, market, path = inputs()
    _, selected = select_simulation_contracts(strategy, market, path)
    mismatched = replace(selected, put=replace(selected.put, multiplier=2))
    decisions = entry_risk_decisions(
        path.points[0].timestamp,
        path.points[0].session_date,
        Decimal("100"),
        Decimal("100"),
        mismatched,
        strategy.risk,
        True,
        True,
    )
    integrity = next(item for item in decisions if item.rule_id == "matched_straddle_integrity")
    assert integrity.decision == "reject"
    assert integrity.reason_code == "matched_straddle_integrity_breached"
