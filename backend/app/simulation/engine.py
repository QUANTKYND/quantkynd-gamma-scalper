from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal

from app.attribution.reconciliation import reconcile
from app.attribution.greeks import calculate_greek_attribution
from app.execution.fills import simulate_fill
from app.execution.models import ExecutionCostParameters, OrderIntent, SimulatedFill
from app.hedging.models import HedgeDecision, HedgePolicyState
from app.hedging.policies import build_hedge_policy
from app.options.black_scholes import value
from app.options.selection import continuous_forward, select_straddle, synthetic_chain
from app.portfolio.ledger import PortfolioLedger
from app.simulation.events import SimulationEvent
from app.simulation.paths import GeneratedPath
from app.simulation.results import OptionValuationRecord, SimulationResult
from app.simulation.risk import entry_risk_decisions, state_risk_decisions
from app.strategy.hashing import strategy_config_hash
from app.strategy.models import StrategyContractV1


SIMULATOR_VERSION = "sim-1.0"
FUTURES_INSTRUMENT_ID = "NIFTY-FUTURE-SIM"


def run_simulation(
    strategy: StrategyContractV1,
    path: GeneratedPath,
    policy_id: str,
    option_costs: ExecutionCostParameters,
    futures_costs: ExecutionCostParameters,
    manual_kill_switch_engaged: bool = False,
    accounting_tolerance: Decimal = Decimal("0.01"),
) -> SimulationResult:
    if not path.states:
        raise ValueError("simulation path cannot be empty")
    policy = build_hedge_policy(policy_id, strategy.hedging)
    config_hash = strategy_config_hash(strategy)
    run_id = _run_id(config_hash, path.path_hash, policy_id, option_costs, futures_costs)
    initial = path.states[0]
    expiry = initial.timestamp.date() + timedelta(days=15)
    forward = continuous_forward(
        initial.spot,
        initial.risk_free_rate,
        initial.dividend_yield,
        initial.time_to_expiry_years,
    )
    selected = select_straddle(synthetic_chain("NIFTY", forward, 50, 4, 4, expiry, 1), forward)
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
    for state in path.states:
        processed_states.append(state)
        pair_values = _value_pair(selected.call, selected.put, state)
        valuations.extend(pair_values)
        for record in pair_values:
            ledger.mark(record.contract_id, record.price)
        if FUTURES_INSTRUMENT_ID in ledger.positions:
            ledger.mark(FUTURES_INSTRUMENT_ID, state.futures_price)
        option_delta = sum(record.delta for record in pair_values) * strategy.position.units
        option_gamma = sum(record.gamma for record in pair_values) * strategy.position.units
        hedge_position = ledger.positions.get(FUTURES_INSTRUMENT_ID)
        hedge_delta = float(hedge_position.quantity * hedge_position.multiplier) if hedge_position else 0.0
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
                1.0,
                state.risk_free_rate,
            )
        )
        decisions.append(decision)
        if decision.requested_quantity:
            side = "buy" if decision.requested_quantity > 0 else "sell"
            intent = OrderIntent(
                f"{run_id}-hedge-{state.step_index}-{hedge_count}",
                state.timestamp,
                FUTURES_INSTRUMENT_ID,
                side,
                abs(decision.requested_quantity),
                1,
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
    hedge_position = ledger.positions.get(FUTURES_INSTRUMENT_ID)
    if hedge_position and hedge_position.quantity:
        side = "sell" if hedge_position.quantity > 0 else "buy"
        intent = OrderIntent(
            f"{run_id}-futures-close",
            final_state.timestamp,
            FUTURES_INSTRUMENT_ID,
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
        FUTURES_INSTRUMENT_ID,
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
        path.path_hash,
        policy_id,
        selected.call,
        selected.put,
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


def _run_id(config_hash, path_hash, policy_id, option_costs, futures_costs):
    payload = json.dumps(
        {
            "simulator": SIMULATOR_VERSION,
            "strategy": config_hash,
            "path": path_hash,
            "policy": policy_id,
            "option_costs": asdict(option_costs),
            "futures_costs": asdict(futures_costs),
        },
        sort_keys=True,
        default=str,
    )
    return f"sim-{hashlib.sha256(payload.encode()).hexdigest()[:20]}"
