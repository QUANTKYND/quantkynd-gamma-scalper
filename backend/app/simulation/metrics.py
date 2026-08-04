from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal

from app.execution.costs import money
from app.simulation.results import SimulationResult


@dataclass(frozen=True)
class SimulationSummary:
    run_id: str
    status: str
    policy_id: str
    starting_nav: Decimal
    terminal_portfolio_value: Decimal
    terminal_net_pnl: Decimal
    gross_option_pnl: Decimal
    gross_futures_hedge_pnl: Decimal
    cash_financing_pnl: Decimal
    option_transaction_costs: Decimal
    futures_transaction_costs: Decimal
    total_transaction_costs: Decimal
    hedge_count: int
    turnover: Decimal
    maximum_absolute_pre_hedge_net_delta: float | None
    mean_absolute_pre_hedge_net_delta: float | None
    pre_hedge_net_delta_rmse: float | None
    maximum_absolute_post_hedge_residual_delta: float | None
    mean_absolute_post_hedge_residual_delta: float | None
    post_hedge_residual_delta_rmse: float | None
    maximum_drawdown: Decimal | None
    position_holding_duration_seconds: float
    delta_contribution: float
    gamma_contribution: float
    theta_contribution: float
    vega_contribution: float
    attribution_residual: float
    ledger_reconciliation_residual: Decimal
    exit_reason: str
    units: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize(result: SimulationResult) -> SimulationSummary:
    pre_hedge_deltas = [decision.net_delta_before_decision for decision in result.hedge_decisions]
    post_hedge_deltas = [decision.net_delta_after_fill for decision in result.hedge_decisions]
    values = [result.starting_nav]
    values.extend(
        value
        for decision in result.hedge_decisions
        for value in (decision.portfolio_value_before_fill, decision.portfolio_value_after_fill)
        if value is not None
    )
    values.append(result.terminal_portfolio_value)
    peak = values[0]
    max_drawdown = Decimal("0.00")
    for current in values:
        peak = max(peak, current)
        max_drawdown = max(max_drawdown, peak - current)
    attribution = result.pnl_attribution
    futures_turnover = money(
        sum(
            (fill.gross_notional for fill in result.fills if fill.instrument_id == result.futures_instrument_id),
            start=Decimal("0"),
        )
    )
    return SimulationSummary(
        result.run_id,
        result.status,
        result.policy_id,
        result.starting_nav,
        result.terminal_portfolio_value,
        result.reconciliation.terminal_pnl,
        result.reconciliation.gross_option_pnl,
        result.reconciliation.gross_futures_pnl,
        result.reconciliation.cash_financing_pnl,
        result.reconciliation.option_costs,
        result.reconciliation.futures_costs,
        result.reconciliation.option_costs + result.reconciliation.futures_costs,
        result.hedge_count,
        futures_turnover,
        max((abs(value) for value in pre_hedge_deltas), default=None),
        sum(abs(value) for value in pre_hedge_deltas) / len(pre_hedge_deltas) if pre_hedge_deltas else None,
        math.sqrt(sum(value * value for value in pre_hedge_deltas) / len(pre_hedge_deltas)) if pre_hedge_deltas else None,
        max((abs(value) for value in post_hedge_deltas), default=None),
        sum(abs(value) for value in post_hedge_deltas) / len(post_hedge_deltas) if post_hedge_deltas else None,
        math.sqrt(sum(value * value for value in post_hedge_deltas) / len(post_hedge_deltas)) if post_hedge_deltas else None,
        money(max_drawdown),
        (result.market_states[-1].timestamp - result.market_states[0].timestamp).total_seconds(),
        sum(item.delta_contribution for item in attribution),
        sum(item.gamma_contribution for item in attribution),
        sum(item.theta_contribution for item in attribution),
        sum(item.vega_contribution for item in attribution),
        sum(item.residual for item in attribution),
        result.reconciliation.residual,
        result.exit_reason,
        {
            "money": "INR",
            "delta": "portfolio_underlying_equivalent_units",
            "gamma": "portfolio_underlying_equivalent_units_per_INR",
            "theta": "INR_per_year",
            "vega": "INR_per_unit_volatility",
            "duration": "seconds",
            "turnover": "INR_reference_notional",
        },
    )
