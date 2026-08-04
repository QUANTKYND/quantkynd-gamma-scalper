# Codex Task — STRAT-1 and SIM-1

## Milestone sequence

1. **STRAT-1 — Strategy Contract v1**
2. **SIM-1 — Deterministic Option and Hedge Simulator**

SIM-1 must not begin until STRAT-1 is implemented, tested, documented, and accepted.

The purpose of this sequence is to freeze one precise research strategy and then build a deterministic simulator capable of answering:

> Given a market path, a long-gamma option position, a hedge policy, and explicit transaction costs, what exact terminal P&L results, and why?

The output must be a research-valid, reproducible foundation. It is not a live-trading implementation.

---

# Current project position

The repository currently contains:

- A FastAPI backend and React frontend.
- Correct close-to-close realized-variance calculations.
- Reproducible RV research runs.
- A selectable Upstox instrument workflow.
- Historical daily closes from Upstox.
- A read-only LTPC stream.
- Clearly separated provisional live close-to-close estimates.
- Finalized-close-only forecast evaluation.
- No option pricing, option ledger, hedge simulator, paper execution, or order-placement path.

Preserve those boundaries.

---

# Required reading

Before modifying code, read:

```text
AGENTS.md
docs/README.md
docs/conventions.md
docs/design.md
docs/dependencies.md
docs/data-models.md
docs/api.md
docs/environment.md
docs/testing.md
docs/performance.md
docs/observability.md
docs/security.md
docs/plan/roadmap.md
docs/plan/research.md
docs/plan/options-market-infrastructure.md
docs/plan/paper-trading-operations.md
docs/plan/acceptance-gates.md
```

Also inspect the current project structure and existing patterns for:

```text
configuration models
Pydantic API models
stable dataset/configuration hashes
immutable research artifacts
CLI research runs
structured errors
structured logs
test fixtures
```

Read the project’s research notes and source papers related to:

```text
realized volatility
variance risk premium
discrete delta hedging
transaction costs
no-transaction bands
hedge-error accumulation
```

Do not silently invent a paper formula. Any analytical hedge-band formula must identify its source, units, assumptions, and implementation convention in `docs/research/`.

---

# Repository conventions

## Frontend

- Direct `useEffect` remains prohibited in application and feature code.
- Derive state inline during render.
- Use RTK Query for fetching.
- React to user actions in event handlers.
- Use `key` to reset identity-specific component state.
- Use `useMountEffect` only for a genuine one-time external synchronization.
- Do not copy RTK Query results into component state.

STRAT-1 and the quantitative core of SIM-1 require no new frontend implementation unless an existing page must be updated to reflect milestone status.

## Code comments

New code carries no explanatory comments.

Names, types, small functions, tests, and documents must explain the implementation.

Existing comments remain unless their surrounding code is removed.

The following are not treated as explanatory comments:

```text
biome-ignore directives
lint directives that are technically necessary
auto-generated file headers
```

## Safety

Codex must not add:

```text
broker order placement
paper-order routing
portfolio writes outside the simulator
live trade intents
automatic strategy execution
Redis
Postgres
Celery
a live trading scheduler
option-chain ingestion
implied-volatility surfaces from live quotes
intraday realized variance
```

The simulator is offline and deterministic.

---

# Part I — STRAT-1: Strategy Contract v1

## Objective

Create a versioned, validated, hashable strategy contract that removes ambiguity from every later simulation, backtest, and paper-trading decision.

No later component may guess:

```text
which underlying is traded
which option structure is opened
how expiry is selected
how strike is selected
when the signal is formed
when entry becomes eligible
how long the position is held
which hedge instrument is used
which hedge policies are permitted
when the position exits
which risk limits apply
```

---

## 1. Frozen v1 research strategy

Implement one narrow strategy contract.

| Area | STRAT-1 v1 decision |
|---|---|
| Strategy family | Long gamma |
| Underlying | NIFTY 50 |
| Underlying instrument key | `NSE_INDEX|Nifty 50` |
| Option structure | Long near-ATM straddle |
| Option exercise style | European |
| Settlement | Cash |
| Position direction | Long one call and long one put at the same strike and expiry |
| Signal origin | End of finalized trading session |
| Physical-variance forecast horizon | 5 completed trading sessions |
| Maximum holding period | 5 completed trading sessions |
| Entry eligibility | Next trading session after the signal origin |
| Expiry rule | Earliest eligible expiry with sufficient remaining trading sessions |
| Strike rule | Strike closest to forward price |
| Hedge instrument | NIFTY futures in simulation |
| Concurrent strategy positions | 1 |
| Execution mode | Simulation only |
| Live capital | Prohibited |
| Profit-taking optimization | Not included in v1 |
| Deep hedging | Not included in v1 |

These decisions are research defaults, not claims of profitability.

---

## 2. Entry semantics

The signal is formed only after session `t` is finalized.

A historical or simulated entry may occur no earlier than session `t+1`.

The strategy contract must represent:

```yaml
signal:
  origin: end_of_finalized_session
  forecast_horizon_sessions: 5

entry:
  eligibility: next_session
  entry_time_local: "09:30:00"
  exchange_timezone: "Asia/Kolkata"
```

No simulation or later backtest may use the session-`t` closing signal and enter retroactively at the same closing price.

The quantitative edge condition is conceptually:

```text
forecast physical variance
minus implied variance
minus expected option-entry costs
minus expected hedge costs
minus a model-risk buffer
```

STRAT-1 defines the required inputs and thresholds. It does not implement the live implied-variance calculation.

For SIM-1, implied volatility is a controlled scenario input.

---

## 3. Expiry-selection contract

Represent expiry rules explicitly:

```yaml
expiry:
  holding_horizon_sessions: 5
  safety_buffer_sessions: 2
  minimum_remaining_sessions: 7
  maximum_remaining_sessions: 15
  choose: earliest_eligible
```

Validation rules:

- `holding_horizon_sessions` must be positive.
- `safety_buffer_sessions` must be non-negative.
- `minimum_remaining_sessions` must be at least holding horizon plus safety buffer.
- `maximum_remaining_sessions` must be at least the minimum.
- The selection method must be one of the explicitly supported values.
- STRAT-1 supports only `earliest_eligible`.

Later market-data code will also require liquidity and quote-quality checks, but those checks are represented as policy fields now even though SIM-1 uses controlled synthetic markets.

---

## 4. Strike-selection contract

Use forward moneyness.

Conceptually:

```text
forward = spot × exp((risk-free rate − dividend yield) × time to expiry)
selected strike = available strike with minimum absolute distance to forward
```

Tie-breaking order:

1. Lowest combined call-and-put relative spread.
2. Highest combined traded volume.
3. Highest combined open interest.
4. Lower strike as the deterministic final tie-break.

Represent:

```yaml
strike:
  method: nearest_forward_atm
  tie_breakers:
    - lowest_combined_relative_spread
    - highest_combined_volume
    - highest_combined_open_interest
    - lower_strike
```

SIM-1 may use a generated strike grid and controlled liquidity fields.

---

## 5. Position contract

The v1 strategy position is:

```text
long 1 call
long 1 put
same underlying
same strike
same expiry
same multiplier
```

The number of strategy units must be configurable but default to one:

```yaml
position:
  structure: long_straddle
  units: 1
  maximum_concurrent_positions: 1
```

Reject:

```text
zero or negative units
mixed expiries
mixed strikes
mixed multipliers
naked call-only or put-only variants
short-gamma variants
multiple concurrent strategy positions
```

---

## 6. Hedge contract

The permitted policies are:

```text
no_hedge
fixed_interval
delta_threshold
constant_band
whalley_wilmott
```

Represent one default policy plus a benchmark set:

```yaml
hedging:
  instrument: nifty_future
  default_policy: constant_band
  benchmark_policies:
    - no_hedge
    - fixed_interval
    - delta_threshold
    - constant_band
    - whalley_wilmott
```

Each policy must have a typed parameter block.

Example:

```yaml
hedging:
  fixed_interval:
    interval_steps: 1

  delta_threshold:
    maximum_absolute_net_delta: 0.10

  constant_band:
    lower_net_delta: -0.05
    upper_net_delta: 0.05
    rebalance_target: nearest_boundary

  whalley_wilmott:
    transaction_cost_rate: 0.0002
    risk_aversion: 1.0
    rebalance_target: nearest_boundary
```

Do not hide units or normalization.

Every delta threshold or boundary must state whether it is:

```text
raw contract delta
multiplier-adjusted unit delta
portfolio delta
delta as a fraction of configured NAV
```

For STRAT-1 and SIM-1 use:

```text
portfolio delta in underlying-equivalent units
```

---

## 7. Exit contract

Exit at the earliest valid trigger:

```text
maximum holding period reached
insufficient remaining time to expiry
position-loss limit breached
daily-loss limit breached
maximum hedge count breached
market state invalid
quote state invalid
manual simulation kill switch
simulation path ended
```

Represent deterministic precedence:

```yaml
exit:
  precedence:
    - invalid_market_state
    - invalid_quote_state
    - daily_loss_limit
    - position_loss_limit
    - maximum_hedge_count
    - insufficient_time_to_expiry
    - maximum_holding_period
    - simulation_end
```

Do not add profit targets or trailing stops in v1.

---

## 8. Risk policy v1

Add explicit, versioned research defaults.

Suggested starting values:

```yaml
risk:
  starting_nav: 1000000
  maximum_concurrent_positions: 1
  maximum_premium_at_risk_fraction: 0.02
  maximum_daily_theta_fraction: 0.001
  minimum_expected_net_edge_fraction: 0.0005
  maximum_position_loss_fraction: 0.01
  maximum_daily_loss_fraction: 0.015
  maximum_absolute_delta_units: 0.10
  maximum_hedges_per_session: 12
  maximum_option_relative_spread: 0.10
  maximum_quote_age_seconds: 5
  stale_data_lockout: true
  missing_contract_lockout: true
  reconciliation_lockout: true
  manual_kill_switch: true
```

These are provisional research constraints.

Validation:

- Monetary values must be positive where required.
- Fractions must lie in valid ranges.
- Loss fractions must be positive and less than or equal to one.
- Quote age must be positive.
- Maximum hedge count must be a positive integer.
- Maximum absolute delta must be non-negative.
- Risk fields may not be omitted silently.
- Unknown fields must be rejected.

---

## 9. Configuration identity

Every strategy configuration must have:

```text
strategy_id
strategy_version
schema_version
canonical configuration payload
stable SHA-256 configuration hash
created_at
```

Suggested identity:

```yaml
strategy_id: nifty-long-gamma-straddle
strategy_version: 1
schema_version: 1
```

Canonicalization rules:

- Stable key ordering.
- UTF-8.
- No insignificant whitespace dependency.
- Explicit numeric normalization.
- Exclude runtime-only timestamps from the content hash.
- Include every field that can change strategy behavior.
- Unknown fields are forbidden.

Same semantic configuration must produce the same hash.

Any behavioral change must produce a different hash.

---

## 10. STRAT-1 backend structure

Suggested structure:

```text
backend/app/strategy/
├── __init__.py
├── models.py
├── config.py
├── validation.py
├── hashing.py
└── registry.py
```

Suggested config file:

```text
config/strategies/nifty-long-gamma-v1.yaml
```

Suggested documents:

```text
docs/strategy/strategy-charter-v1.md
docs/strategy/risk-policy-v1.md
docs/strategy/decision-log.md
docs/strategy/configuration-reference.md
```

Do not duplicate behavioral defaults across Python and YAML.

The YAML file is the configured strategy instance.

Pydantic models are the schema and validator.

---

## 11. STRAT-1 core models

Use strict models with extra fields forbidden.

Suggested top-level model:

```python
class StrategyContractV1:
    schema_version: int
    strategy_id: str
    strategy_version: int
    mode: Literal["simulation"]
    underlying: UnderlyingConfig
    signal: SignalConfig
    entry: EntryConfig
    expiry: ExpirySelectionConfig
    strike: StrikeSelectionConfig
    position: PositionConfig
    hedging: HedgingConfig
    exit: ExitConfig
    risk: RiskPolicyConfig
```

Use small nested models rather than one large untyped dictionary.

The exact class names may follow repository conventions.

---

## 12. STRAT-1 CLI

Add a validation CLI:

```text
backend/app/cli/validate_strategy_config.py
```

Invocation:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
```

Output:

```text
strategy ID
strategy version
schema version
configuration hash
underlying
structure
forecast horizon
holding horizon
default hedge policy
validation status
```

Do not print secrets or environment values.

Exit non-zero on validation failure.

---

## 13. STRAT-1 tests

Add tests for:

### Parsing

- Valid YAML loads.
- Unknown fields fail.
- Missing required fields fail.
- Unsupported strategy mode fails.
- Unsupported structure fails.
- Unsupported hedge policy fails.
- Invalid enum values fail.

### Cross-field validation

- Minimum remaining sessions respects holding horizon plus buffer.
- Maximum remaining sessions is not below minimum.
- One concurrent position is enforced.
- Long-straddle legs share strike, expiry, and multiplier at construction time.
- Constant-band lower boundary is below upper boundary.
- Fixed interval is positive.
- Risk aversion is positive.
- Transaction-cost rate is non-negative.
- Maximum hedge count is positive.
- Entry timezone is valid.
- Entry time parses correctly.

### Hashing

- Same semantic configuration yields the same hash.
- Key order does not alter the hash.
- Runtime timestamps do not alter the hash.
- Behavioral changes alter the hash.
- Unknown fields cannot disappear silently before hashing.

### CLI

- Valid configuration exits zero.
- Invalid configuration exits non-zero.
- Output includes the stable configuration hash.

---

## 14. STRAT-1 acceptance criteria

- [ ] One unambiguous v1 strategy contract exists.
- [ ] The contract is fully represented in versioned YAML.
- [ ] Strict typed models validate the YAML.
- [ ] Unknown fields are rejected.
- [ ] Cross-field constraints are enforced.
- [ ] Strategy behavior has a stable SHA-256 hash.
- [ ] Every future simulation can record strategy ID, version, and hash.
- [ ] No later component must guess entry, expiry, strike, hedge, exit, or risk rules.
- [ ] Validation CLI works.
- [ ] Tests pass.
- [ ] Documentation is updated.
- [ ] No live order path is added.

SIM-1 may begin only after all STRAT-1 criteria pass.

---

# Part II — SIM-1: Deterministic Option and Hedge Simulator

## Objective

Build an offline deterministic simulator for the STRAT-1 long near-ATM straddle.

The simulator must:

1. Load a validated STRAT-1 configuration.
2. Create or load a deterministic market path.
3. Construct a European call and put at one strike and expiry.
4. Price the options and calculate Greeks.
5. Open the straddle using an explicit fill and cost model.
6. Track exact cash and positions.
7. Evaluate a hedge policy at every simulation decision point.
8. Trade the simulated futures hedge when required.
9. Close or settle positions according to the strategy contract.
10. Reconcile exact terminal P&L.
11. Produce approximate Greek attribution separately.
12. Persist immutable research artifacts.
13. Reproduce identical results from identical inputs.

---

## 15. SIM-1 scope

### In scope

```text
European call and put pricing
Black-Scholes baseline
analytical delta, gamma, theta, and vega
implied-volatility inversion
user-provided deterministic paths
seeded GBM paths
seeded piecewise-volatility paths
synthetic strike grids
near-forward-ATM straddle construction
simulated futures hedge instrument
five hedge policies
explicit fill model
explicit transaction-cost components
cash ledger
position ledger
exact P&L reconciliation
Greek attribution
drawdown and hedge-quality metrics
immutable run artifacts
CLI execution
offline tests
```

### Out of scope

```text
live Upstox option chains
live futures subscriptions
historical option-chain reconstruction
American exercise
early exercise
physical delivery
margin optimization
broker fees calibrated from a live account
partial fills
cancel/replace
order queues
market impact models
stochastic implied-volatility surfaces
local volatility
stochastic volatility
deep hedging
reinforcement learning
portfolio netting across strategies
Redis
Postgres
REST or WebSocket simulator APIs
frontend simulator dashboard
```

---

## 16. Numerical and accounting conventions

Document these conventions in `docs/simulation/numerical-conventions.md`.

### Quantitative calculations

Use `float64` for:

```text
spot
forward
volatility
rates
time in years
option prices
Greeks
path generation
analytical attribution
```

### Accounting calculations

Use `Decimal` for:

```text
cash ledger
fill notional
transaction costs
realized cash flows
terminal accounting P&L
```

Define one conversion boundary from quantitative values to accounting values.

Configure a currency precision and rounding convention.

Suggested:

```text
currency: INR
currency quantum: 0.01
rounding: ROUND_HALF_EVEN
```

Do not repeatedly convert back and forth inside pricing functions.

### Time

- Store timestamps in UTC.
- Interpret exchange sessions in `Asia/Kolkata`.
- Use an explicit day-count convention.
- Default annual trading periods: `252`.
- A simulation step must carry an explicit year fraction.
- Do not infer time from row count alone.

### Sign conventions

Document:

```text
long option quantity is positive
long futures quantity is positive
buy cash flow is negative
sell cash flow is positive
costs are positive amounts and reduce cash
option-book delta includes quantity and multiplier
net portfolio delta includes option and hedge positions
```

No module may define its own incompatible sign convention.

---

## 17. SIM-1 architecture

Suggested structure:

```text
backend/app/
├── options/
│   ├── __init__.py
│   ├── contracts.py
│   ├── black_scholes.py
│   ├── implied_volatility.py
│   ├── greeks.py
│   └── selection.py
│
├── simulation/
│   ├── __init__.py
│   ├── clock.py
│   ├── paths.py
│   ├── market.py
│   ├── events.py
│   ├── engine.py
│   ├── results.py
│   ├── artifacts.py
│   └── run_store.py
│
├── portfolio/
│   ├── __init__.py
│   ├── positions.py
│   ├── cash.py
│   ├── ledger.py
│   └── valuation.py
│
├── hedging/
│   ├── __init__.py
│   ├── models.py
│   ├── policies.py
│   ├── no_hedge.py
│   ├── fixed_interval.py
│   ├── delta_threshold.py
│   ├── constant_band.py
│   └── whalley_wilmott.py
│
├── execution/
│   ├── __init__.py
│   ├── models.py
│   ├── costs.py
│   ├── fills.py
│   └── simulator.py
│
└── attribution/
    ├── __init__.py
    ├── pnl.py
    ├── greeks.py
    └── reconciliation.py
```

Prefer cohesive modules and pure functions.

Do not create network dependencies.

---

## 18. Dependencies

Do not add a dependency merely for convenience.

The first implementation should use:

```text
Python standard library
NumPy
pandas
Pydantic
existing project utilities
```

Use `statistics.NormalDist` or a tested internal normal CDF/PDF implementation if suitable.

Add SciPy only if the implementation genuinely requires it and document:

```text
purpose
owner
milestone
removal criteria
```

Do not add a general optimization library only for one-dimensional implied-volatility inversion.

A bounded bisection or Brent-style internal solver is acceptable if thoroughly tested.

Update `docs/dependencies.md` for any added direct dependency.

---

## 19. Core domain models

All immutable domain values should use frozen dataclasses or strict immutable Pydantic models according to repository conventions.

### Option contract

Required fields:

```text
contract_id
underlying
option_type: call or put
strike
expiry
multiplier
exercise_style: european
settlement_type: cash
currency: INR
```

### Market state

Required fields:

```text
timestamp
session_index
spot
futures_price
risk_free_rate
dividend_yield
implied_volatility
time_to_expiry_years
step_year_fraction
```

### Option valuation

Required fields:

```text
contract_id
timestamp
price
delta
gamma
theta_per_year
vega_per_volatility_point convention
intrinsic_value
time_value
```

The vega unit must be explicit.

### Strategy position

Required fields:

```text
strategy_position_id
strategy_id
call_contract_id
put_contract_id
units
opened_at
closed_at
status
```

### Hedge position

Required fields:

```text
instrument_id
quantity
multiplier
average_price
mark_price
unrealized_pnl
realized_pnl
```

### Order intent

Required fields:

```text
intent_id
timestamp
instrument_id
side
quantity
reason_code
strategy_position_id
policy_id
```

### Simulated fill

Required fields:

```text
fill_id
intent_id
timestamp
instrument_id
side
quantity
reference_price
fill_price
gross_notional
half_spread_cost
slippage_cost
fixed_cost
proportional_cost
total_cost
```

### Ledger entry

Required fields:

```text
entry_id
timestamp
entry_type
instrument_id
quantity_change
cash_change
cost
reference_id
strategy_position_id
```

### Hedge decision

Required fields:

```text
timestamp
policy_id
current_option_delta
current_hedge_delta
current_net_delta
target_net_delta
lower_boundary
upper_boundary
action
requested_quantity
reason_code
```

### Simulation manifest

Required fields:

```text
run_id
created_at
completed_at
status
strategy_id
strategy_version
strategy_config_hash
simulator_version
path_generator
path_config_hash
seed
market_scenario_hash
policy_id
policy_parameters
cost_model_hash
git_commit
artifact_directory
failure_reason
```

---

## 20. Black-Scholes baseline

Implement European call and put pricing with continuous compounding and continuous dividend yield.

Required functions:

```text
call_price
put_price
price
call_delta
put_delta
gamma
call_theta
put_theta
vega
intrinsic_value
time_value
```

Required behavior:

- Reject non-positive spot.
- Reject non-positive strike.
- Reject negative time to expiry.
- Reject negative volatility.
- Handle zero time to expiry exactly.
- Handle zero volatility deterministically.
- Remain numerically stable for very small positive time.
- Return finite values for deep ITM and deep OTM cases.
- Preserve put-call parity within tolerance.
- State whether theta is per year or per day.
- State whether vega is per unit volatility or per one-volatility-point move.

Do not leave Greek units implicit.

---

## 21. Implied-volatility inversion

Implement a robust one-dimensional inversion helper.

Inputs:

```text
option type
observed price
spot
strike
time to expiry
risk-free rate
dividend yield
lower volatility bound
upper volatility bound
price tolerance
maximum iterations
```

Required behavior:

- Validate static no-arbitrage price bounds.
- Reject impossible prices.
- Handle intrinsic-value boundaries.
- Return a typed result with:
  - implied volatility,
  - converged flag,
  - iteration count,
  - final price error.
- Do not return zero silently on failure.
- Do not use future path data.

Required tests:

- Round-trip known call and put prices.
- Low volatility.
- High volatility.
- Near expiry.
- Deep ITM.
- Deep OTM.
- Impossible price.
- Non-convergence path.

---

## 22. Contract and strike selection

Create a deterministic synthetic option chain from:

```text
spot
forward
strike interval
number of strikes above and below
expiry
multiplier
synthetic relative spreads
synthetic volume
synthetic open interest
```

Use the STRAT-1 selection contract.

Required tests:

- Nearest-forward strike selected.
- Spread tie-break works.
- Volume tie-break works.
- Open-interest tie-break works.
- Lower-strike final tie-break works.
- Call and put share strike, expiry, and multiplier.
- No eligible expiry fails explicitly.

---

## 23. Path generators

Implement three path sources.

### User-provided path

Load an explicit sequence of market states or prices.

Validate:

```text
strictly increasing timestamps
positive finite prices
non-negative volatility
non-negative time to expiry
consistent step fractions
no duplicate timestamps
```

### Seeded GBM

Required configuration:

```text
initial_spot
drift
realized_volatility
number_of_steps
step_year_fraction
seed
```

### Seeded piecewise-volatility path

Required configuration:

```text
initial_spot
drift
volatility regimes
regime start/end steps
number_of_steps
step_year_fraction
seed
```

Every generated path must record:

```text
generator ID
generator version
seed
canonical parameters
path hash
```

Identical inputs must produce identical paths and hashes.

Different seeds must produce different paths.

Do not use wall-clock time inside path generation.

---

## 24. Futures hedge instrument

SIM-1 must model a linear futures hedge.

Support:

```text
explicit futures-price path
or
cost-of-carry-derived futures price
```

For the derived mode, document the convention:

```text
futures price is derived from spot, rates, dividend yield, and remaining futures maturity
```

The hedge instrument must have:

```text
instrument_id
expiry
multiplier
tick_size
price
delta_per_contract
```

Default delta per futures unit is one underlying-equivalent unit before multiplier adjustment.

Do not assume option and futures multipliers are identical without validation.

---

## 25. Execution and fill model

Implement deterministic fills.

### Option entry and exit

Default configurable behavior:

```text
buy at reference mid plus half-spread plus slippage
sell at reference mid minus half-spread minus slippage
```

### Futures hedge

Use the same explicit side-aware rule with futures-specific parameters.

### Cost components

Represent separately:

```text
fixed cost per order
proportional notional cost
half-spread cost
slippage cost
```

Required model:

```python
class ExecutionCostParameters:
    fixed_cost_per_order
    proportional_notional_rate
    half_spread_per_unit
    slippage_per_unit
```

Use separate parameter sets for:

```text
options
futures
```

The fill record must expose every component.

Do not collapse costs into one adjustment.

---

## 26. Exact ledger

The accounting ledger is the source of truth.

Required event types include:

```text
initial_capital
option_entry
option_exit
option_expiry_settlement
futures_hedge_buy
futures_hedge_sell
futures_close
transaction_cost
cash_financing
simulation_close
```

Every fill must produce balanced:

```text
position change
cash change
cost deduction
reference linkage
```

Required identities:

```text
terminal P&L = terminal portfolio value − starting NAV
```

and:

```text
terminal P&L
=
option P&L
+
futures hedge P&L
+
cash financing P&L
− option costs
− futures costs
```

The reconciliation residual must be below a configurable accounting tolerance.

No Greek approximation may be used as the accounting source of truth.

---

## 27. Hedge policies

All policies implement one protocol.

Suggested interface:

```python
class HedgePolicy(Protocol):
    def decide(
        self,
        state: HedgePolicyState,
    ) -> HedgeDecision: ...
```

The state must include only information available at the current simulation timestamp.

It must not include future path values.

### Policy A — No hedge

- Never emits an order.
- Records a hold decision with a stable reason code.

### Policy B — Fixed interval

- Evaluates only at configured step intervals.
- Rebalances toward zero net delta or a documented target.
- Does not trade outside scheduled steps.

### Policy C — Delta threshold

Trade only when:

```text
absolute current net portfolio delta
exceeds configured maximum
```

Rebalance to:

```text
zero
or
a configured target
```

The v1 default must be explicit.

### Policy D — Constant band

Hold while net delta remains between lower and upper boundaries.

After a breach, trade to the nearest boundary.

Required behavior:

- No trade inside the band.
- Buy after lower-bound breach when required.
- Sell after upper-bound breach when required.
- Deterministic quantity rounding.
- No oscillation caused solely by inconsistent rounding.

### Policy E — Whalley-Wilmott

Before implementation, add:

```text
docs/research/whalley-wilmott-band.md
```

The document must state:

```text
paper/source used
exact formula
variable definitions
units
whether the band is expressed in shares, futures units, or portfolio delta
transaction-cost convention
risk-aversion convention
assumptions
small-cost limitation
near-expiry behavior
zero-gamma behavior
rounding behavior
```

Do not copy a formula without reconciling dimensions.

The code must use a pure formula function with explicit inputs and a typed result.

Required qualitative tests:

- Higher proportional transaction cost does not narrow the band.
- Higher absolute gamma changes the band according to the documented formula.
- Zero transaction cost approaches the documented limiting behavior.
- Invalid risk aversion fails.
- Invalid gamma or price inputs fail or follow documented boundary behavior.
- Near-expiry behavior is finite or explicitly capped according to the document.
- Wider bands produce no more hedge trades than narrower bands on the same path, subject to deterministic rounding.

---

## 28. Simulation event loop

Implement an event-driven loop.

Required order:

```text
Load and validate strategy contract
        ↓
Load or generate path
        ↓
Select expiry and strike
        ↓
Construct call and put
        ↓
Price entry market
        ↓
Generate option-entry intents
        ↓
Simulate fills and costs
        ↓
Update ledger and positions
        ↓
For each simulation timestamp:
    update market state
    update time to expiry
    mark futures
    revalue call and put
    calculate option Greeks
    aggregate option-book Greeks
    calculate hedge delta
    calculate net portfolio delta
    evaluate risk exits
    invoke hedge policy
    create hedge intent when required
    simulate hedge fill
    update ledger and positions
    record market, valuation, decision, and risk state
        ↓
Apply earliest valid exit trigger
        ↓
Close or settle call and put
        ↓
Close futures hedge
        ↓
Apply exit costs
        ↓
Reconcile exact P&L
        ↓
Calculate approximate Greek attribution
        ↓
Write immutable artifacts
```

The order of operations at one timestamp must be documented and tested.

No same-timestamp look-ahead may occur.

---

## 29. Position sizing and quantity rounding

SIM-1 uses one straddle unit by default.

Contract quantities must respect:

```text
integer option contracts
integer futures contracts
configured multipliers
```

Define a deterministic futures rounding rule.

Suggested benchmark rule:

```text
round hedge quantity toward the nearest integer contract
ties use half-even or another explicitly documented rule
```

Record:

```text
continuous target quantity
rounded requested quantity
post-trade residual delta
```

Do not pretend exact neutrality is possible when one futures contract is coarse relative to the option-book delta.

---

## 30. Risk controls inside the simulator

Implement the STRAT-1 controls as deterministic simulation gates.

At minimum:

```text
maximum position loss
maximum daily loss
maximum absolute net delta
maximum hedges per session
maximum premium at risk
manual simulation kill switch
reconciliation failure
```

Every risk decision must produce:

```text
timestamp
rule ID
observed value
configured limit
decision
reason code
```

No simulated order may bypass the risk pre-check.

A risk-triggered exit must be reconstructable from artifacts.

---

## 31. Greek attribution

Calculate an approximate interval attribution:

```text
delta contribution
gamma contribution
theta contribution
vega contribution
residual
```

Use a documented convention such as beginning-of-interval Greeks.

The implementation must clearly distinguish:

```text
exact accounting P&L
approximate Greek attribution
```

Required relationship:

```text
exact option mark change
=
delta approximation
+
gamma approximation
+
theta approximation
+
vega approximation
+
attribution residual
```

The attribution residual is expected to be non-zero.

Do not force it to zero.

---

## 32. Simulation metrics

Produce at least:

```text
starting NAV
terminal portfolio value
terminal net P&L
gross option P&L
gross futures hedge P&L
cash financing P&L
option transaction costs
futures transaction costs
total transaction costs
hedge count
turnover
maximum absolute net delta
mean absolute net delta
net-delta RMSE
maximum drawdown
position holding duration
gamma contribution
theta contribution
vega contribution
delta contribution
attribution residual
ledger reconciliation residual
exit reason
```

Metrics must state units.

Undefined metrics must be `null`, not zero.

---

## 33. Immutable research artifacts

Write each run under:

```text
backend/artifacts/simulation/runs/<run-id>/
```

Required files:

```text
manifest.json
strategy-config.json
path-config.json
path.csv
market-states.csv
option-valuations.csv
hedge-decisions.csv
risk-decisions.csv
order-intents.csv
fills.csv
ledger.csv
positions.csv
pnl-attribution.csv
summary.json
```

Run-store behavior:

- Write to a temporary directory.
- Write a running manifest first.
- Atomically publish the completed run.
- Persist a failed manifest on failure.
- Never list incomplete temporary directories as completed runs.
- Never overwrite an existing immutable run.
- Include hashes for strategy, path configuration, market scenario, and cost model.
- Record the Git commit when available.

Do not commit generated run artifacts.

---

## 34. SIM-1 CLI

Add:

```text
backend/app/cli/run_gamma_simulation.py
```

Example:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm \
  --seed 17 \
  --policy constant_band
```

Support:

```text
strategy config path
path generator
seed
policy override from the contract’s benchmark set
artifact root
```

Do not permit arbitrary unsupported policies.

CLI output:

```text
run ID
strategy ID and hash
path generator and seed
policy
exit reason
terminal P&L
total costs
hedge count
maximum absolute delta
reconciliation residual
artifact directory
```

Exit non-zero on failed simulation or failed reconciliation.

---

## 35. SIM-1 tests

### Pricing

- Known call price.
- Known put price.
- Put-call parity.
- Zero time to expiry.
- Zero volatility.
- Very small time to expiry.
- Deep ITM.
- Deep OTM.
- Analytical delta against finite difference.
- Analytical gamma against finite difference.
- Analytical theta against finite difference.
- Analytical vega against finite difference.
- Invalid inputs rejected.

### Implied volatility

- Call round-trip.
- Put round-trip.
- Low-volatility round-trip.
- High-volatility round-trip.
- Near-expiry round-trip.
- Impossible price rejected.
- Non-convergence reported explicitly.

### Selection

- Earliest eligible expiry.
- No eligible expiry.
- Nearest forward strike.
- Every tie-break level.
- Matched call and put contract fields.

### Paths

- Same seed and config yield identical path.
- Same seed and config yield identical path hash.
- Different seed changes the path.
- User path validation.
- Piecewise regimes activate at correct steps.
- No wall-clock dependency.

### Costs and fills

- Buy-side fill worsens upward.
- Sell-side fill worsens downward.
- Fixed cost applied once.
- Proportional cost uses correct notional.
- Spread and slippage are separate.
- Option and futures parameters remain separate.
- Total fill cost equals component sum.

### Ledger

- Initial capital recorded.
- Entry premium deducted.
- Entry costs deducted once.
- Hedge cash flows correct.
- Exit proceeds recorded.
- Futures close correct.
- Expiry settlement correct.
- Position quantities reconcile.
- Cash ledger reconciles.
- Terminal accounting identity holds.
- Reconciliation failure causes run failure.

### Hedge policies

- No-hedge never trades.
- Fixed interval trades only on schedule.
- Threshold holds below threshold.
- Threshold trades after breach.
- Constant band holds inside.
- Constant band trades to nearest boundary.
- Wider constant band produces no more trades on the same path.
- Futures quantity rounding is deterministic.
- Residual delta is recorded.
- Whalley-Wilmott qualitative monotonicity matches its documented formula.
- No policy sees future state.

### Risk controls

- Premium-at-risk breach blocks entry.
- Position-loss breach exits.
- Daily-loss breach exits.
- Maximum hedge count prevents further hedges and triggers configured behavior.
- Maximum delta breach is recorded.
- Manual kill switch exits.
- Every risk action has a reason code.

### Attribution

- Exact ledger P&L remains independent of attribution.
- Constant-volatility paths produce zero or near-zero vega contribution according to the chosen convention.
- Theta sign is correct for long options.
- Attribution residual is preserved.
- Component sum plus residual matches exact option mark change within tolerance.

### Determinism and artifacts

- Same inputs produce identical summary and artifacts except allowed runtime metadata.
- Same inputs produce stable configuration hashes.
- Different policy changes policy hash or manifest parameters.
- Completed run has every required artifact.
- Failed run has a failed manifest.
- Temporary directories are not listed.
- Existing run is not overwritten.
- No future market data changes an earlier decision.

---

## 36. Documentation updates

Add:

```text
docs/strategy/strategy-charter-v1.md
docs/strategy/risk-policy-v1.md
docs/strategy/decision-log.md
docs/strategy/configuration-reference.md
docs/simulation/architecture.md
docs/simulation/numerical-conventions.md
docs/simulation/ledger-and-pnl.md
docs/simulation/hedge-policies.md
docs/simulation/artifacts.md
docs/research/whalley-wilmott-band.md
```

Update:

```text
docs/README.md
docs/design.md
docs/dependencies.md
docs/data-models.md
docs/api.md
docs/environment.md
docs/testing.md
docs/observability.md
docs/security.md
docs/plan/roadmap.md
docs/plan/research.md
docs/plan/options-market-infrastructure.md
README.md
AGENTS.md if the reading order changes
```

`docs/api.md` should state that SIM-1 exposes no HTTP or WebSocket procedures.

Do not create placeholder API routes merely to fill a table.

---

## 37. Observability

Use structured logs for CLI and simulation events.

Suggested fields:

```text
event
run_id
strategy_id
strategy_config_hash
policy_id
path_generator
path_hash
seed
timestamp
instrument_id
intent_id
fill_id
risk_rule_id
exit_reason
reconciliation_residual
error_code
```

Never log an entire configuration when a stable hash and selected safe fields are sufficient.

No metrics backend is required.

---

## 38. Performance

Correctness and determinism take priority.

Still avoid obvious inefficiencies:

- Price call and put together where shared terms can be reused.
- Do not rebuild the full ledger DataFrame on every event.
- Accumulate typed records and materialize tables at artifact-writing time.
- Avoid O(n²) scans through prior events.
- Keep policy decisions pure.
- Do not add Redis.
- Do not parallelize one deterministic path prematurely.

A benchmark is optional, not an acceptance requirement.

---

## 39. Security and safety

- No broker client is instantiated.
- No order API is added.
- No Upstox token is needed.
- No environment secret is written to artifacts.
- Artifact paths are validated against path traversal.
- YAML loading uses safe parsing.
- Config extra fields are rejected.
- CLI errors do not dump secret environment state.
- Simulation mode is the only accepted strategy mode.

---

## 40. Verification commands

### STRAT-1 validation

```bash
cd backend

UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
```

### Backend tests

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

### Example simulations

Run at least:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm \
  --seed 17 \
  --policy no_hedge
```

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm \
  --seed 17 \
  --policy fixed_interval
```

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm \
  --seed 17 \
  --policy delta_threshold
```

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm \
  --seed 17 \
  --policy constant_band
```

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm \
  --seed 17 \
  --policy whalley_wilmott
```

All policies must use the same path when the seed and path configuration are identical.

### Frontend regression verification

Even though no feature UI is required:

```bash
cd ../frontend
npm run lint
npm run build
```

### Repository checks

```bash
cd ..
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
grep -R "useEffect" frontend/src \
  --exclude="useMountEffect.ts"
```

---

# 41. Combined acceptance criteria

## STRAT-1

- [x] Strategy contract is explicit and narrow.
- [x] Versioned YAML exists.
- [x] Strict typed validation exists.
- [x] Cross-field validation exists.
- [x] Stable configuration hash exists.
- [x] Validation CLI passes.
- [x] Unknown fields fail.
- [x] Documentation is complete.
- [x] Tests pass.

## SIM-1

- [x] Black-Scholes pricing and Greeks pass tests.
- [x] Implied-volatility inversion passes tests.
- [x] Deterministic path generators exist.
- [x] Straddle selection is deterministic.
- [x] Futures hedge instrument is explicit.
- [x] Five hedge policies exist.
- [x] Whalley-Wilmott formula and units are documented.
- [x] Fill and cost components are explicit.
- [x] Exact ledger is the accounting source of truth.
- [x] Greek attribution is separate and approximate.
- [x] Risk controls are enforced.
- [x] Terminal P&L reconciles.
- [x] Identical inputs reproduce identical results.
- [x] Immutable artifacts are written.
- [x] Failed runs persist failure manifests.
- [x] CLI runs all five policies on the same seeded path.
- [x] Backend tests pass.
- [x] Frontend lint and build still pass.
- [x] Repository checks pass.
- [x] No order-placement path exists.
- [x] No live provider dependency exists.
- [x] Intraday realized variance remains unimplemented.

---

# 42. Codex implementation order

Use small reviewable commits.

Suggested sequence:

```text
1. STRAT-1 models, YAML, validation, hashing, tests
2. STRAT-1 docs and validation CLI
3. SIM-1 option contracts, pricing, Greeks, IV inversion, tests
4. SIM-1 paths, market states, selection, tests
5. SIM-1 execution costs, fills, positions, ledger, tests
6. SIM-1 hedge-policy protocol and deterministic policies
7. Whalley-Wilmott research note, formula implementation, tests
8. SIM-1 event engine, risk controls, exact reconciliation
9. Greek attribution and summary metrics
10. Artifact run store and simulation CLI
11. Documentation, repository hygiene, final verification
```

Do not combine all work into one unreviewable commit.

---

# 43. Codex completion report

Codex must report:

1. Starting commit SHA.
2. Ending commit SHA.
3. Commits created.
4. Files added.
5. Files modified.
6. Files removed.
7. STRAT-1 strategy decisions implemented.
8. Strategy schema and cross-field validations.
9. Configuration canonicalization and hash design.
10. Pricing and Greek conventions.
11. Implied-volatility solver behavior.
12. Path generators and determinism guarantees.
13. Futures-price convention.
14. Fill-price convention.
15. Cost components.
16. Position and cash sign conventions.
17. Ledger accounting identity.
18. Hedge-policy behavior.
19. Whalley-Wilmott source, formula, units, and limitations.
20. Quantity-rounding convention.
21. Risk controls.
22. Greek-attribution convention.
23. Artifact layout.
24. Run-ID and immutability design.
25. Backend test count and result.
26. Strategy validation CLI result.
27. Results of the five policy simulation runs.
28. Frontend lint result.
29. Frontend build result.
30. `git diff --check` result.
31. Direct `useEffect` scan result.
32. Known limitations.
33. Confirmation that no broker or order-placement path was added.
34. Confirmation that SIM-1 is offline and deterministic.
35. Confirmation that intraday realized variance remains unimplemented.

Use these milestone statuses only when all criteria pass:

```text
STRAT-1: COMPLETE
SIM-1: COMPLETE
Live broker execution: NOT IMPLEMENTED
Paper execution: NOT IMPLEMENTED
Historical option-chain replay: NOT IMPLEMENTED
Ready for DATA-1 / OPTIONS-1: YES
```
