from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution.models import OrderIntent, SimulatedFill
from app.attribution.greeks import GreekAttributionRecord
from app.hedging.models import HedgeDecision
from app.options.contracts import OptionContract
from app.portfolio.ledger import LedgerEntry
from app.simulation.events import SimulationEvent
from app.simulation.market import MarketState
from app.simulation.config import SimulationRunConfig
from app.simulation.risk import SimulationRiskDecision


@dataclass(frozen=True)
class OptionValuationRecord:
    contract_id: str
    timestamp: object
    quantity: int
    multiplier: int
    unit_price: float
    unit_intrinsic_value: float
    unit_time_value: float
    unit_delta: float
    unit_gamma: float
    unit_theta_per_year: float
    unit_vega_per_volatility_unit: float
    market_value: Decimal
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta_per_year: float
    portfolio_vega_per_volatility_unit: float


@dataclass(frozen=True)
class SimulationReconciliation:
    terminal_pnl: Decimal
    gross_option_pnl: Decimal
    gross_futures_pnl: Decimal
    cash_financing_pnl: Decimal
    option_costs: Decimal
    futures_costs: Decimal
    residual: Decimal
    reconciled: bool


@dataclass(frozen=True)
class SimulationResult:
    run_id: str
    run_config: SimulationRunConfig
    status: str
    strategy_config_hash: str
    market_config_hash: str
    path_hash: str
    policy_id: str
    call_contract: OptionContract
    put_contract: OptionContract
    futures_instrument_id: str
    futures_multiplier: int
    futures_delta_per_contract: float
    market_states: tuple[MarketState, ...]
    option_valuations: tuple[OptionValuationRecord, ...]
    hedge_decisions: tuple[HedgeDecision, ...]
    risk_decisions: tuple[SimulationRiskDecision, ...]
    order_intents: tuple[OrderIntent, ...]
    fills: tuple[SimulatedFill, ...]
    ledger_entries: tuple[LedgerEntry, ...]
    events: tuple[SimulationEvent, ...]
    pnl_attribution: tuple[GreekAttributionRecord, ...]
    starting_nav: Decimal
    terminal_portfolio_value: Decimal
    exit_reason: str
    hedge_count: int
    reconciliation: SimulationReconciliation
