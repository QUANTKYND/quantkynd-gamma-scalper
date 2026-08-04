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
    maximum_absolute_net_delta: float | None
    mean_absolute_net_delta: float | None
    net_delta_rmse: float | None
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
    net_deltas = [float(event.details["net_delta"]) for event in result.events if "net_delta" in event.details]
    values = [result.starting_nav]
    values.extend(
        Decimal(str(event.details["portfolio_value"]))
        for event in result.events
        if "portfolio_value" in event.details
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
            (fill.gross_notional for fill in result.fills if fill.instrument_id == "NIFTY-FUTURE-SIM"),
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
        max((abs(value) for value in net_deltas), default=None),
        sum(abs(value) for value in net_deltas) / len(net_deltas) if net_deltas else None,
        math.sqrt(sum(value * value for value in net_deltas) / len(net_deltas)) if net_deltas else None,
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
