from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.attribution.greeks import calculate_greek_attribution
from app.attribution.reconciliation import reconcile
from app.execution.costs import money
from app.execution.fills import simulate_fill
from app.execution.models import ExecutionCostParameters, OrderIntent, SimulatedFill
from app.hedging.models import HedgeDecision, HedgePolicyState
from app.hedging.policies import build_hedge_policy, force_delta_reduction
from app.options.black_scholes import value
from app.options.selection import continuous_forward, select_expiry, select_straddle, synthetic_chain
from app.portfolio.ledger import PortfolioLedger
from app.simulation.clock import SimulationExpiry, expiry_for_remaining_sessions
from app.simulation.config import (
    CostModelConfig,
    RuntimeRiskInputs,
    SimulationEntryAssumptions,
    SimulationMarketConfig,
    SimulationRunConfig,
    simulation_market_config_hash,
    simulation_run_config_hash,
    stable_hash,
)
from app.simulation.events import SimulationEvent
from app.simulation.paths import GeneratedPath
from app.simulation.results import OptionValuationRecord, SimulationResult
from app.simulation.risk import (
    absolute_daily_theta,
    entry_risk_decisions,
    initialize_risk_state,
    mark_risk_state,
    option_entry_premium_at_risk,
    post_hedge_delta_risk_decision,
    record_risk_hedge,
    state_risk_decisions,
)
from app.strategy.hashing import strategy_config_hash
from app.strategy.models import StrategyContractV1
from app.simulation.state_builder import build_executable_market_states, executable_market_state_hash


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
    if not path.points:
        raise ValueError("simulation path cannot be empty")
    _validate_contract_alignment(strategy, market)
    policy = build_hedge_policy(policy_id, strategy.hedging)
    config_hash = strategy_config_hash(strategy)
    market_hash = simulation_market_config_hash(market)
    run_config = build_simulation_run_config(
        strategy,
        market,
        path,
        policy_id,
        option_costs,
        futures_costs,
        manual_kill_switch_engaged,
        accounting_tolerance,
    )
    run_id = simulation_run_id(run_config)
    expiry, selected = select_simulation_contracts(strategy, market, path)
    executable_states = build_executable_market_states(strategy, market, path, expiry)
    market_state_hash = executable_market_state_hash(executable_states)
    initial = executable_states[0]
    futures_id = market.futures.instrument_id
    position_id = f"position-{run_id}"
    ledger = PortfolioLedger(Decimal(str(strategy.risk.starting_nav_inr)), initial.timestamp, position_id)
    valuations: list[OptionValuationRecord] = []
    decisions: list[HedgeDecision] = []
    risk_records = []
    intents: list[OrderIntent] = []
    fills: list[SimulatedFill] = []
    events: list[SimulationEvent] = []
    entry_values = _value_pair(selected.call, selected.put, initial, strategy.position.units)
    entry_intents = tuple(
        OrderIntent(
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
        for contract in (selected.call, selected.put)
    )
    entry_fills = tuple(
        simulate_fill(intent, valuation.unit_price, option_costs)
        for intent, valuation in zip(entry_intents, entry_values, strict=True)
    )
    entry_risks = entry_risk_decisions(
        initial.timestamp,
        initial.session_date or initial.timestamp.date(),
        option_entry_premium_at_risk(entry_fills),
        absolute_daily_theta(entry_values, market.clock.trading_periods_per_year),
        selected,
        strategy.risk,
        strategy.expiry.require_quote_quality,
        strategy.expiry.require_liquidity,
    )
    risk_records.extend(entry_risks)
    if any(item.decision == "reject" for item in entry_risks):
        rejection = next(item.reason_code for item in entry_risks if item.decision == "reject")
        raise ValueError(rejection)
    for intent, fill in zip(entry_intents, entry_fills, strict=True):
        ledger.record_fill(fill, "option_entry", position_id)
        intents.append(intent)
        fills.append(fill)
    risk_state = initialize_risk_state(
        ledger.starting_nav,
        ledger.portfolio_value(),
        initial.session_date or initial.timestamp.date(),
    )
    exit_reason = "simulation_end"
    processed_states = []
    for state_index, state in enumerate(executable_states):
        processed_states.append(state)
        pair_values = _value_pair(selected.call, selected.put, state, strategy.position.units)
        valuations.extend(pair_values)
        for record in pair_values:
            ledger.mark(record.contract_id, record.unit_price)
        if futures_id in ledger.positions:
            ledger.mark(futures_id, state.futures_price)
        option_delta = sum(record.portfolio_delta for record in pair_values)
        option_gamma = sum(record.portfolio_gamma for record in pair_values)
        hedge_position = ledger.positions.get(futures_id)
        hedge_delta = float(hedge_position.quantity * market.futures.delta_per_contract) if hedge_position else 0.0
        net_delta = option_delta + hedge_delta
        risk_state = mark_risk_state(
            risk_state,
            ledger.portfolio_value(),
            state.session_date or state.timestamp.date(),
        )
        state_risks = state_risk_decisions(
            state.timestamp,
            risk_state,
            net_delta,
            strategy.risk,
            manual_kill_switch_engaged,
        )
        risk_records.extend(state_risks)
        risk_exit = _exit_reason_at_state(
            state_risks,
            strategy,
            market,
            state,
            state_index == len(executable_states) - 1,
        )
        if risk_exit:
            exit_reason = risk_exit
            events.append(
                SimulationEvent(
                    len(events) + 1,
                    state.timestamp,
                    "exit_required",
                    position_id,
                    {
                        "exit_reason": exit_reason,
                        "net_delta": net_delta,
                        "portfolio_value": str(ledger.portfolio_value()),
                    },
                )
            )
            break
        policy_state = HedgePolicyState(
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
        decision = policy.decide(policy_state)
        forced_delta_control = False
        if abs(decision.net_delta_after_fill) > strategy.risk.maximum_absolute_delta_units:
            forced = force_delta_reduction(policy_state, policy_id)
            forced_reduces_delta = (
                forced.rounded_requested_futures_quantity != 0
                and abs(forced.net_delta_after_fill) < abs(net_delta)
            )
            if (
                not forced_reduces_delta
                or abs(forced.net_delta_after_fill) > strategy.risk.maximum_absolute_delta_units
            ):
                exit_reason = "absolute_delta_unhedgeable"
                risk_records.append(
                    post_hedge_delta_risk_decision(
                        state.timestamp,
                        risk_state,
                        forced.net_delta_after_fill,
                        strategy.risk.maximum_absolute_delta_units,
                        "unhedgeable",
                    )
                )
                failed_decision = replace(
                    forced,
                    action="hold",
                    rounded_requested_futures_quantity=0,
                    executed_futures_quantity=0,
                    option_delta_after_fill=option_delta,
                    hedge_delta_after_fill=hedge_delta,
                    net_delta_after_fill=net_delta,
                    quantity_rounding_residual_delta=net_delta,
                    portfolio_value_before_fill=ledger.portfolio_value(),
                    portfolio_value_after_fill=ledger.portfolio_value(),
                    session_hedge_count=risk_state.hedges_in_current_session,
                    total_hedge_count=risk_state.total_hedges,
                    reason_code="absolute_delta_unhedgeable",
                )
                decisions.append(failed_decision)
                events.append(
                    SimulationEvent(
                        len(events) + 1,
                        state.timestamp,
                        "decision_completed",
                        position_id,
                        {
                            "option_delta_before_decision": option_delta,
                            "hedge_delta_before_decision": hedge_delta,
                            "net_delta_before_decision": net_delta,
                            "continuous_target_futures_quantity": forced.continuous_target_futures_quantity,
                            "rounded_requested_futures_quantity": 0,
                            "executed_futures_quantity": 0,
                            "option_delta_after_fill": option_delta,
                            "hedge_delta_after_fill": hedge_delta,
                            "net_delta_after_fill": net_delta,
                            "portfolio_value_before_fill": str(ledger.portfolio_value()),
                            "portfolio_value_after_fill": str(ledger.portfolio_value()),
                            "action": "hold",
                        },
                    )
                )
                events.append(
                    SimulationEvent(
                        len(events) + 1,
                        state.timestamp,
                        "risk_control_failed",
                        position_id,
                        {
                            "reason_code": "absolute_delta_unhedgeable",
                            "net_delta_before_decision": net_delta,
                            "predicted_residual_delta": forced.net_delta_after_fill,
                        },
                    )
                )
                events.append(
                    SimulationEvent(
                        len(events) + 1,
                        state.timestamp,
                        "exit_required",
                        position_id,
                        {"exit_reason": exit_reason, "net_delta": net_delta},
                    )
                )
                break
            decision = forced
            forced_delta_control = True
        portfolio_value_before_fill = ledger.portfolio_value()
        executed_quantity = 0
        if decision.rounded_requested_futures_quantity:
            side = "buy" if decision.rounded_requested_futures_quantity > 0 else "sell"
            intent = OrderIntent(
                f"{run_id}-hedge-{state.step_index}-{risk_state.total_hedges}",
                state.timestamp,
                futures_id,
                side,
                abs(decision.rounded_requested_futures_quantity),
                market.futures.multiplier,
                decision.reason_code,
                position_id,
                policy_id,
            )
            fill = simulate_fill(intent, state.futures_price, futures_costs)
            ledger.record_fill(fill, "futures_hedge_buy" if side == "buy" else "futures_hedge_sell", position_id)
            intents.append(intent)
            fills.append(fill)
            risk_state = record_risk_hedge(risk_state)
            executed_quantity = decision.rounded_requested_futures_quantity
        hedge_delta_after_fill = hedge_delta + executed_quantity * market.futures.delta_per_contract
        net_delta_after_fill = option_delta + hedge_delta_after_fill
        portfolio_value_after_fill = ledger.portfolio_value()
        decision = replace(
            decision,
            executed_futures_quantity=executed_quantity,
            option_delta_after_fill=option_delta,
            hedge_delta_after_fill=hedge_delta_after_fill,
            net_delta_after_fill=net_delta_after_fill,
            quantity_rounding_residual_delta=net_delta_after_fill - decision.target_net_delta,
            portfolio_value_before_fill=portfolio_value_before_fill,
            portfolio_value_after_fill=portfolio_value_after_fill,
            session_hedge_count=risk_state.hedges_in_current_session,
            total_hedge_count=risk_state.total_hedges,
        )
        risk_records.append(
            post_hedge_delta_risk_decision(
                state.timestamp,
                risk_state,
                net_delta_after_fill,
                strategy.risk.maximum_absolute_delta_units,
                "forced_hedge" if forced_delta_control else "within_limit",
            )
        )
        risk_state = mark_risk_state(
            risk_state,
            portfolio_value_after_fill,
            state.session_date or state.timestamp.date(),
        )
        decisions.append(decision)
        events.append(
            SimulationEvent(
                len(events) + 1,
                state.timestamp,
                "decision_completed",
                position_id,
                {
                    "option_delta_before_decision": option_delta,
                    "hedge_delta_before_decision": hedge_delta,
                    "net_delta_before_decision": net_delta,
                    "continuous_target_futures_quantity": decision.continuous_target_futures_quantity,
                    "rounded_requested_futures_quantity": decision.rounded_requested_futures_quantity,
                    "executed_futures_quantity": decision.executed_futures_quantity,
                    "option_delta_after_fill": decision.option_delta_after_fill,
                    "hedge_delta_after_fill": decision.hedge_delta_after_fill,
                    "net_delta_after_fill": decision.net_delta_after_fill,
                    "portfolio_value_before_fill": str(portfolio_value_before_fill),
                    "portfolio_value_after_fill": str(portfolio_value_after_fill),
                    "action": decision.action,
                },
            )
        )
    final_state = processed_states[-1]
    final_values = _value_pair(selected.call, selected.put, final_state, strategy.position.units)
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
            fill = simulate_fill(intent, valuation.unit_price, option_costs)
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
        run_config,
        status,
        config_hash,
        market_hash,
        path.path_hash,
        market_state_hash,
        policy_id,
        selected.call,
        selected.put,
        futures_id,
        market.futures.multiplier,
        market.futures.delta_per_contract,
        tuple(executable_states),
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
        risk_state.total_hedges,
        reconciliation,
    )


def _value_pair(call, put, state, quantity):
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
                quantity,
                contract.multiplier,
                valuation.price,
                valuation.intrinsic_value,
                valuation.time_value,
                valuation.greeks.delta,
                valuation.greeks.gamma,
                valuation.greeks.theta_per_year,
                valuation.greeks.vega_per_unit_volatility,
                money(Decimal(str(valuation.price)) * quantity * contract.multiplier),
                valuation.greeks.delta * quantity * contract.multiplier,
                valuation.greeks.gamma * quantity * contract.multiplier,
                valuation.greeks.theta_per_year * quantity * contract.multiplier,
                valuation.greeks.vega_per_unit_volatility * quantity * contract.multiplier,
            )
        )
    return tuple(records)


def _exit_reason_at_state(records, strategy, market, state, is_final_state):
    breached = {record.rule_id for record in records if record.decision == "exit"}
    if "manual_kill_switch" in breached:
        return "manual_kill_switch"
    minimum_time = strategy.expiry.safety_buffer_sessions / market.clock.trading_periods_per_year
    if state.time_to_expiry_years < minimum_time:
        breached.add("insufficient_time_to_expiry")
    if state.session_index >= strategy.expiry.holding_horizon_sessions:
        breached.add("maximum_holding_period")
    if is_final_state:
        breached.add("simulation_end")
    return next((reason for reason in strategy.exit.precedence if reason in breached), None)


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


def select_simulation_contracts(
    strategy: StrategyContractV1,
    market: SimulationMarketConfig,
    path: GeneratedPath,
):
    initial = path.points[0]
    expiry = select_simulation_expiry(strategy, market, initial.session_date)
    forward = continuous_forward(
        initial.spot,
        initial.risk_free_rate,
        initial.dividend_yield,
        expiry.time_to_expiry_years,
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
    return expiry, selected


def _validate_contract_alignment(strategy: StrategyContractV1, market: SimulationMarketConfig) -> None:
    if market.clock.timezone != strategy.entry.exchange_timezone:
        raise ValueError("simulation clock timezone must match the strategy contract")
    if strategy.entry.entry_time_local not in market.clock.decision_times_local:
        raise ValueError("strategy entry time must be available in the simulation clock")


def build_simulation_run_config(
    strategy: StrategyContractV1,
    market: SimulationMarketConfig,
    path: GeneratedPath,
    policy_id: str,
    option_costs: ExecutionCostParameters,
    futures_costs: ExecutionCostParameters,
    manual_kill_switch_engaged: bool = False,
    accounting_tolerance: Decimal = Decimal("0.01"),
) -> SimulationRunConfig:
    policy_parameters = strategy.hedging.model_dump(mode="json").get(policy_id, {})
    if not isinstance(policy_parameters, dict):
        policy_parameters = {}
    return SimulationRunConfig(
        schema_version=1,
        simulator_version=SIMULATOR_VERSION,
        strategy_config_hash=strategy_config_hash(strategy),
        market_config_hash=simulation_market_config_hash(market),
        path_config_hash=stable_hash(path.canonical_parameters),
        path_hash=path.path_hash,
        policy_id=policy_id,
        policy_parameters=policy_parameters,
        option_cost_model=CostModelConfig.from_parameters(option_costs),
        futures_cost_model=CostModelConfig.from_parameters(futures_costs),
        runtime_risk_inputs=RuntimeRiskInputs(manual_kill_switch_engaged=manual_kill_switch_engaged),
        entry_assumptions=SimulationEntryAssumptions(
            edge_gate_mode="not_evaluated_hedge_policy_benchmark"
        ),
        accounting_tolerance=accounting_tolerance,
        quantity_rounding="nearest_integer_half_even",
    )


def simulation_run_id(run_config: SimulationRunConfig) -> str:
    return f"sim-{simulation_run_config_hash(run_config).removeprefix('sha256:')[:20]}"
