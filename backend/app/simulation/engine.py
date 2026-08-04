from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.attribution.reconciliation import reconcile
from app.attribution.greeks import calculate_greek_attribution
from app.execution.fills import simulate_fill
from app.execution.models import ExecutionCostParameters, OrderIntent, SimulatedFill
from app.hedging.models import HedgeDecision, HedgePolicyState
from app.hedging.policies import build_hedge_policy
from app.options.black_scholes import value
from app.options.selection import continuous_forward, select_expiry, select_straddle, synthetic_chain
from app.portfolio.ledger import PortfolioLedger
from app.simulation.events import SimulationEvent
from app.simulation.clock import SimulationExpiry, expiry_for_remaining_sessions
from app.simulation.config import SimulationMarketConfig, simulation_market_config_hash
from app.simulation.paths import GeneratedPath
from app.simulation.results import OptionValuationRecord, SimulationResult
from app.simulation.risk import entry_risk_decisions, state_risk_decisions
from app.strategy.hashing import strategy_config_hash
from app.strategy.models import StrategyContractV1


SIMULATOR_VERSION = "sim-1.1"


def run_simulation(
    strategy: StrategyContractV1,
    market: SimulationMarketConfig,
    path: GeneratedPath,
    policy_id: str,
    option_costs: ExecutionCostParameters,
    futures_costs: ExecutionCostParameters,
    manual_kill_switch_engaged: bool = False,
    accounting_tolerance: Decimal = Decimal("0.01"),
) -> SimulationResult:
    if not path.states:
        raise ValueError("simulation path cannot be empty")
    _validate_contract_alignment(strategy, market)
    policy = build_hedge_policy(policy_id, strategy.hedging)
    config_hash = strategy_config_hash(strategy)
    market_hash = simulation_market_config_hash(market)
    run_id = simulation_run_id(config_hash, market_hash, path.path_hash, policy_id, option_costs, futures_costs)
    initial = path.states[0]
    expiry = select_simulation_expiry(strategy, market, initial.session_date or initial.timestamp.date())
    normalized_states = _states_with_expiry(path, expiry)
    initial = normalized_states[0]
    forward = continuous_forward(
        initial.spot,
        initial.risk_free_rate,
        initial.dividend_yield,
        initial.time_to_expiry_years,
    )
    options = market.options
    selected = select_straddle(
        synthetic_chain(
            market.underlying,
            forward,
            options.strike_interval,
            options.strikes_below,
            options.strikes_above,
            expiry.expiry_session_date,
            options.multiplier,
            options.relative_spread,
            options.synthetic_volume_base,
            options.synthetic_open_interest_base,
        ),
        forward,
    )
    futures_id = market.futures.instrument_id
    position_id = f"position-{run_id}"
    ledger = PortfolioLedger(Decimal(str(strategy.risk.starting_nav_inr)), initial.timestamp, position_id)
    valuations: list[OptionValuationRecord] = []
    decisions: list[HedgeDecision] = []
    risk_records = []
    intents: list[OrderIntent] = []
    fills: list[SimulatedFill] = []
    events: list[SimulationEvent] = []
    entry_values = _value_pair(selected.call, selected.put, initial)
    premium = sum(record.price for record in entry_values) * strategy.position.units
    entry_risks = entry_risk_decisions(initial.timestamp, premium, strategy.risk)
    risk_records.extend(entry_risks)
    if any(item.decision == "reject" for item in entry_risks):
        raise ValueError("premium_at_risk_breached")
    for contract, valuation in zip((selected.call, selected.put), entry_values, strict=True):
        intent = OrderIntent(
            f"{run_id}-entry-{contract.option_type}",
            initial.timestamp,
            contract.contract_id,
            "buy",
            strategy.position.units,
            contract.multiplier,
            "open_long_straddle",
            position_id,
            policy_id,
        )
        fill = simulate_fill(intent, valuation.price, option_costs)
        ledger.record_fill(fill, "option_entry", position_id)
        intents.append(intent)
        fills.append(fill)
    hedge_count = 0
    exit_reason = "simulation_end"
    processed_states = []
    for state in normalized_states:
        processed_states.append(state)
        pair_values = _value_pair(selected.call, selected.put, state)
        valuations.extend(pair_values)
        for record in pair_values:
            ledger.mark(record.contract_id, record.price)
        if futures_id in ledger.positions:
            ledger.mark(futures_id, state.futures_price)
        option_delta = sum(record.delta for record in pair_values) * strategy.position.units
        option_gamma = sum(record.gamma for record in pair_values) * strategy.position.units
        hedge_position = ledger.positions.get(futures_id)
        hedge_delta = float(hedge_position.quantity * market.futures.delta_per_contract) if hedge_position else 0.0
        net_delta = option_delta + hedge_delta
        current_pnl = float(ledger.portfolio_value() - ledger.starting_nav)
        state_risks = state_risk_decisions(
            state.timestamp,
            current_pnl,
            net_delta,
            hedge_count,
            strategy.risk,
            manual_kill_switch_engaged,
        )
        risk_records.extend(state_risks)
        risk_exit = _risk_exit_reason(state_risks, strategy.exit.precedence)
        if risk_exit:
            exit_reason = risk_exit
            break
        decision = policy.decide(
            HedgePolicyState(
                state.timestamp,
                state.step_index,
                state.session_index,
                option_delta,
                hedge_delta,
                net_delta,
                option_gamma,
                state.spot,
                state.time_to_expiry_years,
                market.futures.delta_per_contract,
                state.risk_free_rate,
            )
        )
        decisions.append(decision)
        if decision.requested_quantity:
            side = "buy" if decision.requested_quantity > 0 else "sell"
            intent = OrderIntent(
                f"{run_id}-hedge-{state.step_index}-{hedge_count}",
                state.timestamp,
                futures_id,
                side,
                abs(decision.requested_quantity),
                market.futures.multiplier,
                decision.reason_code,
                position_id,
                policy_id,
            )
            fill = simulate_fill(intent, state.futures_price, futures_costs)
            ledger.record_fill(fill, "futures_hedge_buy" if side == "buy" else "futures_hedge_sell", position_id)
            intents.append(intent)
            fills.append(fill)
            hedge_count += 1
        events.append(
            SimulationEvent(
                len(events) + 1,
                state.timestamp,
                "decision_completed",
                position_id,
                {
                    "net_delta": net_delta,
                    "action": decision.action,
                    "portfolio_value": str(ledger.portfolio_value()),
                },
            )
        )
        if state.session_index >= strategy.expiry.holding_horizon_sessions:
            exit_reason = "maximum_holding_period"
            break
    final_state = processed_states[-1]
    final_values = _value_pair(selected.call, selected.put, final_state)
    for contract, valuation in zip((selected.call, selected.put), final_values, strict=True):
        position = ledger.positions[contract.contract_id]
        if position.quantity:
            intent = OrderIntent(
                f"{run_id}-exit-{contract.option_type}",
                final_state.timestamp,
                contract.contract_id,
                "sell",
                abs(position.quantity),
                contract.multiplier,
                exit_reason,
                position_id,
                policy_id,
            )
            fill = simulate_fill(intent, valuation.price, option_costs)
            ledger.record_fill(fill, "option_exit", position_id)
            intents.append(intent)
            fills.append(fill)
    hedge_position = ledger.positions.get(futures_id)
    if hedge_position and hedge_position.quantity:
        side = "sell" if hedge_position.quantity > 0 else "buy"
        intent = OrderIntent(
            f"{run_id}-futures-close",
            final_state.timestamp,
            futures_id,
            side,
            abs(hedge_position.quantity),
            hedge_position.multiplier,
            exit_reason,
            position_id,
            policy_id,
        )
        fill = simulate_fill(intent, final_state.futures_price, futures_costs)
        ledger.record_fill(fill, "futures_close", position_id)
        intents.append(intent)
        fills.append(fill)
    terminal_value = ledger.portfolio_value()
    terminal_pnl = terminal_value - ledger.starting_nav
    reconciliation = reconcile(
        terminal_pnl,
        tuple(ledger.positions.values()),
        tuple(fills),
        frozenset((selected.call.contract_id, selected.put.contract_id)),
        futures_id,
        accounting_tolerance,
    )
    attribution = calculate_greek_attribution(
        tuple(processed_states),
        tuple(valuations),
        selected.call,
        selected.put,
        strategy.position.units,
    )
    status = "complete" if reconciliation.reconciled else "failed"
    return SimulationResult(
        run_id,
        status,
        config_hash,
        market_hash,
        path.path_hash,
        policy_id,
        selected.call,
        selected.put,
        futures_id,
        market.futures.multiplier,
        market.futures.delta_per_contract,
        tuple(processed_states),
        tuple(valuations),
        tuple(decisions),
        tuple(risk_records),
        tuple(intents),
        tuple(fills),
        tuple(ledger.entries),
        tuple(events),
        attribution,
        ledger.starting_nav,
        terminal_value,
        exit_reason if reconciliation.reconciled else "reconciliation_failure",
        hedge_count,
        reconciliation,
    )


def _value_pair(call, put, state):
    records = []
    for contract in (call, put):
        valuation = value(
            contract.option_type,
            state.spot,
            contract.strike,
            state.time_to_expiry_years,
            state.risk_free_rate,
            state.dividend_yield,
            state.implied_volatility,
        )
        records.append(
            OptionValuationRecord(
                contract.contract_id,
                state.timestamp,
                valuation.price,
                valuation.greeks.delta * contract.multiplier,
                valuation.greeks.gamma * contract.multiplier,
                valuation.greeks.theta_per_year * contract.multiplier,
                valuation.greeks.vega_per_unit_volatility * contract.multiplier,
                valuation.intrinsic_value,
                valuation.time_value,
            )
        )
    return tuple(records)


def _risk_exit_reason(records, precedence):
    breached = {record.rule_id for record in records if record.decision == "exit"}
    if "manual_kill_switch" in breached:
        return "manual_kill_switch"
    return next((reason for reason in precedence if reason in breached), None)


def select_simulation_expiry(
    strategy: StrategyContractV1,
    market: SimulationMarketConfig,
    entry_session_date,
) -> SimulationExpiry:
    candidates = {
        expiry_for_remaining_sessions(entry_session_date, sessions, market.clock).expiry_session_date: sessions
        for sessions in market.options.eligible_expiry_sessions
    }
    selected_date = select_expiry(candidates, strategy.expiry)
    selected_sessions = candidates[selected_date]
    return expiry_for_remaining_sessions(entry_session_date, selected_sessions, market.clock)


def _states_with_expiry(path: GeneratedPath, expiry: SimulationExpiry):
    elapsed = 0.0
    states = []
    for state in path.states:
        elapsed += state.step_year_fraction
        states.append(replace(state, time_to_expiry_years=max(expiry.time_to_expiry_years - elapsed, 0.0)))
    return tuple(states)


def _validate_contract_alignment(strategy: StrategyContractV1, market: SimulationMarketConfig) -> None:
    if market.clock.timezone != strategy.entry.exchange_timezone:
        raise ValueError("simulation clock timezone must match the strategy contract")
    if strategy.entry.entry_time_local not in market.clock.decision_times_local:
        raise ValueError("strategy entry time must be available in the simulation clock")


def simulation_run_id(config_hash, market_hash, path_hash, policy_id, option_costs, futures_costs):
    from app.simulation.config import CostModelConfig, RuntimeRiskInputs, SimulationRunConfig, simulation_run_config_hash, stable_hash

    run_config = SimulationRunConfig(
        schema_version=1,
        simulator_version=SIMULATOR_VERSION,
        strategy_config_hash=config_hash,
        market_config_hash=market_hash,
        path_config_hash=stable_hash({"legacy_path_hash": path_hash}),
        path_hash=path_hash,
        policy_id=policy_id,
        policy_parameters={},
        option_cost_model=CostModelConfig.from_parameters(option_costs),
        futures_cost_model=CostModelConfig.from_parameters(futures_costs),
        runtime_risk_inputs=RuntimeRiskInputs(manual_kill_switch_engaged=False),
        accounting_tolerance=Decimal("0.01"),
        quantity_rounding="nearest_integer_half_even",
    )
    return f"sim-{simulation_run_config_hash(run_config).removeprefix('sha256:')[:20]}"
