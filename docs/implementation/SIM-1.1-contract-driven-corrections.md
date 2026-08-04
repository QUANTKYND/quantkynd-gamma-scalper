# Codex Task — SIM-1.1 Contract-Driven Simulator Corrections

## Milestone

**SIM-1.1 — Contract-driven simulator correctness, timing, risk semantics, and reproducibility hardening**

## Branch under review

```text
feature/deterministic-option-and-hedge-simulator
```

## Objective

Correct the STRAT-1 and SIM-1 integration so that the deterministic simulator:

1. Executes the strategy contract rather than hidden engine defaults.
2. Uses consistent expiry, session-clock, and year-fraction semantics.
3. Evaluates exits before opening a hedge at the same timestamp.
4. Implements genuine position-level, daily, and per-session risk state.
5. Uses a Whalley-Wilmott formula that exactly matches its documented source.
6. Includes every behavior-changing input in deterministic run identity.
7. Applies contract multipliers to premium-at-risk and all relevant economics.
8. Records both pre-hedge and post-hedge delta.
9. Rejects invalid numerical inputs consistently.
10. Preserves immutable, reproducible research artifacts.

Do not extend scope into live execution, historical option-chain ingestion, broker integration, paper orders, Redis, Postgres, deep hedging, or intraday realized variance.

---

# Required reading

Read before implementation:

```text
AGENTS.md
docs/README.md
docs/conventions.md
docs/design.md
docs/dependencies.md
docs/data-models.md
docs/testing.md
docs/performance.md
docs/observability.md
docs/security.md
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
config/strategies/nifty-long-gamma-v1.yaml
```

Inspect especially:

```text
backend/app/simulation/engine.py
backend/app/simulation/paths.py
backend/app/simulation/run_store.py
backend/app/simulation/metrics.py
backend/app/options/black_scholes.py
backend/app/options/implied_volatility.py
backend/app/options/selection.py
backend/app/hedging/whalley_wilmott.py
backend/app/portfolio/ledger.py
backend/app/attribution/reconciliation.py
backend/app/cli/run_gamma_simulation.py
backend/tests/simulation/test_engine.py
```

Repository conventions remain in force:

- No direct `useEffect` in frontend application or feature code.
- No explanatory comments in new code.
- Existing comments remain unless surrounding code is removed.
- Names, types, functions, tests, and docs carry the explanation.
- Unknown configuration fields are rejected.
- No broker or order-placement path may be added.
- Simulation remains offline and deterministic.

---

# 1. Make SIM-1 fully contract-driven

## Problem

The simulator currently hardcodes behavior that materially affects:

```text
contract selection
maturity
option multiplier
futures multiplier
strike grid
futures delta
fills
risk
P&L
```

Examples include:

```text
expiry = initial date + 15 calendar days
strike interval = 50
four strikes below
four strikes above
option multiplier = 1
futures multiplier = 1
futures delta per contract = 1
```

These values are not consistently represented in STRAT-1 or a separate simulation-market contract.

The simulator therefore records a STRAT-1 configuration hash while executing undeclared behavior.

## Required design

Introduce a strict, typed, hashable simulation-market configuration.

Suggested model:

```python
class SimulationMarketConfig:
    schema_version: int
    market_id: str
    underlying: str
    option_multiplier: int
    futures_multiplier: int
    futures_delta_per_contract: float
    futures_expiry_rule: str
    strike_interval: float
    strikes_below: int
    strikes_above: int
    eligible_expiry_sessions: tuple[int, ...]
    option_relative_spread: float
    futures_half_spread_per_unit: Decimal
    synthetic_volume_base: int
    synthetic_open_interest_base: int
```

Equivalent smaller nested models are preferred.

Required separation:

```text
STRAT-1
  defines strategy behavior

SimulationMarketConfig
  defines the controlled synthetic market in which the strategy executes

SimulationRunConfig
  binds strategy, market, path, policy, costs, and runtime risk inputs
```

## Required behavior

The engine must:

1. Load the validated STRAT-1 contract.
2. Load the validated simulation-market config.
3. Generate eligible expiries.
4. Apply:
   - `minimum_remaining_sessions`
   - `maximum_remaining_sessions`
   - `safety_buffer_sessions`
   - `choose: earliest_eligible`
5. Generate the strike grid from the market config.
6. Apply the STRAT-1 strike-selection method and tie-breakers.
7. Use explicit option and futures multipliers.
8. Use explicit futures delta per contract.
9. Record and hash the market config.
10. Persist the complete market config in artifacts.

## Required tests

- Engine uses the configured option multiplier.
- Engine uses the configured futures multiplier.
- Engine uses the configured strike interval.
- Engine uses the configured number of strikes above and below.
- Earliest eligible expiry is selected.
- Expiries outside STRAT-1 bounds are excluded.
- No eligible expiry fails explicitly.
- A changed multiplier changes run identity.
- A changed strike grid changes market-config hash.
- No hidden engine constant changes behavior without appearing in a hash.

---

# 2. Unify expiry date and time-to-expiry semantics

## Problem

The current implementation can represent:

```text
contract expiry date = initial date + 15 calendar days
time to expiry = 15 / 252 years
```

Those are different maturities.

## Required design

Create one source of truth for option maturity.

Suggested model:

```python
class SimulationExpiry:
    expiry_session_date: date
    remaining_trading_sessions: int
    time_to_expiry_years: float
```

Required invariant:

```text
time_to_expiry_years
=
remaining_trading_sessions / trading_periods_per_year
```

The contract expiry date must be derived from the simulation session calendar.

Do not independently compute expiry date and maturity fraction.

## Required behavior

- Expiry selection operates in trading sessions.
- Contract metadata stores the selected session date.
- Each market state recalculates remaining sessions deterministically.
- `time_to_expiry_years` reaches zero exactly on expiry.
- No negative maturity is passed into pricing.
- Exit or settlement occurs before invalid negative maturity.

## Required tests

- Fifteen remaining sessions correspond to `15 / 252`.
- Weekend dates do not count as trading sessions.
- Expiry date is the selected session date.
- Time-to-expiry decreases exactly by each step’s year fraction.
- Final expiry state is zero.
- No state produces negative time to expiry.

---

# 3. Add an explicit simulation session clock

## Problem

Path timestamps are currently created by adding consecutive calendar days while economic time advances by `1 / 252`.

This creates weekend “trading sessions” and ignores configured exchange timezone and entry time.

## Required design

Add:

```text
backend/app/simulation/clock.py
```

Suggested model:

```python
class SimulationClockConfig:
    timezone: str
    entry_time_local: time
    trading_periods_per_year: int
    calendar_mode: Literal["weekdays"]
```

Suggested clock output:

```python
class SimulationSession:
    session_index: int
    session_date: date
    decision_at: datetime
    year_fraction_from_previous: float
```

For SIM-1.1, a deterministic weekday-only calendar is sufficient.

Exchange holidays are deferred.

## Required behavior

- Use `Asia/Kolkata`.
- Use STRAT-1 `entry_time_local`.
- Skip Saturday and Sunday.
- Produce timezone-aware local datetimes.
- Persist UTC timestamps.
- Preserve local session date separately.
- Use explicit step year fractions.
- Do not infer sessions from DataFrame row count.

## Required tests

- Friday advances to Monday.
- No weekend session exists.
- Local 09:30 Asia/Kolkata converts to correct UTC.
- Same clock config produces identical sessions.
- Entry time comes from STRAT-1.
- Trading periods per year come from the clock config.
- User-provided paths must still validate session ordering.

---

# 4. Evaluate exits before opening a hedge

## Problem

The engine can:

1. Evaluate hedge policy.
2. Open a futures hedge.
3. Immediately hit maximum holding period.
4. Close that futures hedge at the same timestamp.
5. Pay two sets of costs.

## Required event order

At each timestamp:

```text
mark option and futures positions
calculate exact current portfolio state
calculate current Greeks
calculate current risk state
evaluate all exit conditions
    ├── exit required
    │     close option position
    │     close futures hedge
    │     apply costs
    │     record exit reason
    │     stop
    └── continue
          evaluate hedge policy
          create hedge intent if required
          apply risk pre-check
          execute hedge
          record post-hedge state
```

No hedge may be opened when an exit is already required at the same timestamp.

## Exit precedence

Use the documented STRAT-1 precedence exactly:

```text
invalid_market_state
invalid_quote_state
daily_loss_limit
position_loss_limit
maximum_hedge_count
insufficient_time_to_expiry
maximum_holding_period
simulation_end
```

If the simulator supports additional internal fatal conditions, document their position in the precedence list.

## Required tests

- Maximum-holding exit produces no new hedge at the exit timestamp.
- Position-loss exit produces no new hedge first.
- Daily-loss exit produces no new hedge first.
- Kill-switch exit produces no new hedge first.
- Insufficient-time-to-expiry exit produces no new hedge first.
- No same-timestamp hedge-open/hedge-close round trip occurs.
- Exit precedence is deterministic when multiple rules breach together.

---

# 5. Implement genuine daily, position, and per-session risk state

## Problem

The engine currently uses cumulative run P&L for both:

```text
position loss
daily loss
```

and one run-level hedge count for:

```text
maximum hedges per session
```

## Required state

Track separately:

```python
class SimulationRiskState:
    position_open_value: Decimal
    position_pnl_from_entry: Decimal
    session_open_portfolio_value: Decimal
    session_pnl: Decimal
    hedges_in_current_session: int
    total_hedges: int
    current_session_date: date
```

## Session reset

At a new session:

```text
session_open_portfolio_value = current marked portfolio value
session_pnl = 0
hedges_in_current_session = 0
current_session_date = new session date
```

Do not reset position-level P&L.

## Required semantics

### Position loss

```text
position_pnl_from_entry
=
current portfolio value
minus portfolio value immediately after entry
```

### Daily loss

```text
session_pnl
=
current portfolio value
minus session_open_portfolio_value
```

### Hedge count

```text
maximum_hedges_per_session
```

must use only the current session count.

If SIM-1.1 supports one decision per session, either:

1. Add multiple decision steps per session, or
2. Rename the contract field and documentation to `maximum_hedges_per_run`.

Preferred correction: preserve the STRAT-1 per-session field and support multiple decision timestamps per session through the simulation clock.

## Required risk records

Every risk evaluation must include:

```text
rule_id
timestamp
session_date
observed_value
configured_limit
decision
reason_code
```

## Required tests

- Position loss uses entry-relative P&L.
- Daily loss resets at a new session.
- Daily loss can trigger even when lifetime position P&L remains within its limit.
- Position loss can trigger even when current-session P&L remains within its limit.
- Hedge count resets at session boundary.
- Total hedge count does not reset.
- Two sessions can each use the permitted hedge count.
- Session-boundary state is deterministic.
- Multiple risk breaches respect exit precedence.

---

# 6. Correct Whalley-Wilmott source fidelity

## Problem

The documented formula and the implemented formula do not match exactly.

The current implementation includes a discount factor while the cited expression does not.

## Required correction

Use one of two accepted paths.

### Preferred path

Implement exactly the documented source equation:

```text
h = ((3 × transaction_cost_rate × spot × gamma²) / (2 × risk_aversion))^(1/3)
```

Use the project’s explicit portfolio-delta unit convention.

### Alternative path

Retain a discount factor only if:

- The exact source is cited.
- The derivation is documented.
- The numeraire is documented.
- Units are reconciled.
- The file no longer attributes the exact expression to a source that omits it.

## Required documentation

Update:

```text
docs/research/whalley-wilmott-band.md
```

It must state:

```text
exact formula
source
variable definitions
units
input gamma convention
output band convention
transaction-cost convention
risk-aversion convention
small-cost asymptotic assumption
zero-cost limit
zero-gamma behavior
near-expiry behavior
rounding behavior
```

## Required implementation

Use a pure function:

```python
def whalley_wilmott_half_band(
    transaction_cost_rate: float,
    spot: float,
    portfolio_gamma: float,
    risk_aversion: float,
) -> float:
    ...
```

Only include time or rates if the chosen documented formula requires them.

## Required tests

- Exact numeric regression from a hand-computed example.
- Higher transaction cost does not narrow the band.
- Higher absolute gamma follows the documented formula.
- Zero transaction cost returns the documented limit.
- Zero gamma returns the documented limit.
- Negative or non-finite inputs fail.
- Invalid risk aversion fails.
- Output units match portfolio-delta units.
- Policy trades no more often with a wider analytical band on the same path.

---

# 7. Expand deterministic run identity

## Problem

The run ID omits behavior-changing inputs such as:

```text
manual kill-switch state
accounting tolerance
strike-grid settings
contract multipliers
futures delta
expiry-generation convention
```

This can produce collisions between materially different simulations.

## Required design

Create a canonical top-level run specification.

Suggested model:

```python
class SimulationRunConfig:
    schema_version: int
    simulator_version: str
    strategy_config_hash: str
    market_config_hash: str
    path_config_hash: str
    path_hash: str
    policy_id: str
    policy_parameters: dict[str, object]
    option_cost_model: ExecutionCostParameters
    futures_cost_model: ExecutionCostParameters
    runtime_risk_inputs: RuntimeRiskInputs
    accounting_tolerance: Decimal
    quantity_rounding: str
```

Suggested runtime risk model:

```python
class RuntimeRiskInputs:
    manual_kill_switch_engaged: bool
```

## Canonicalization

- Stable key ordering.
- UTF-8.
- Explicit numeric normalization.
- No wall-clock fields.
- No artifact path.
- Include every input capable of changing:
  - decisions
  - fills
  - costs
  - P&L
  - exit reason
  - reconciliation
  - artifact content

## Required hashes

Persist:

```text
strategy_config_hash
market_config_hash
path_config_hash
path_hash
policy_config_hash
option_cost_model_hash
futures_cost_model_hash
runtime_risk_hash
run_config_hash
```

The run ID may derive from `run_config_hash`.

## Required tests

- Manual kill switch changes run ID.
- Accounting tolerance changes run ID.
- Option multiplier changes run ID.
- Futures multiplier changes run ID.
- Strike interval changes run ID.
- Expiry convention changes run ID.
- Policy parameters change run ID.
- Runtime timestamps do not change run ID.
- Identical semantic config produces the same run ID.
- Two different runs never collide in the immutable run store.

---

# 8. Apply multipliers to premium-at-risk economics

## Problem

Premium-at-risk currently omits the option contract multiplier.

The error is masked by a synthetic multiplier of one.

## Required formula

```text
premium at risk
=
sum(option unit price × signed quantity × contract multiplier)
for long premium paid
+
documented entry costs if configured
```

For the long straddle:

```text
gross premium at risk
=
(call unit price × call contracts × call multiplier)
+
(put unit price × put contracts × put multiplier)
```

Use absolute premium paid for risk comparison.

## Documentation decision

Explicitly choose whether entry transaction costs count toward:

```text
maximum premium at risk
```

Preferred:

```text
premium budget includes gross option premium and entry transaction costs
```

Record that choice in:

```text
docs/strategy/risk-policy-v1.md
docs/simulation/ledger-and-pnl.md
```

## Required tests

- Multiplier one preserves current baseline behavior.
- Multiplier greater than one scales premium risk correctly.
- Entry costs are included or excluded exactly as documented.
- Premium-at-risk breach blocks entry before fills are persisted as a completed open position.
- Call and put multipliers must match for the v1 straddle.
- A multiplier change affects run identity.

---

# 9. Record pre-hedge and post-hedge delta separately

## Problem

The current event record can combine:

```text
pre-hedge net delta
post-fill portfolio value
```

This mixes state timings and contaminates summary metrics.

## Required event fields

Record:

```text
option_delta_before_decision
hedge_delta_before_decision
net_delta_before_decision
continuous_target_futures_quantity
rounded_requested_futures_quantity
executed_futures_quantity
option_delta_after_fill
hedge_delta_after_fill
net_delta_after_fill
portfolio_value_before_fill
portfolio_value_after_fill
```

For a hold decision:

```text
before and after delta are equal
requested and executed quantity are zero
```

## Required metrics

Replace ambiguous metrics with:

```text
maximum absolute pre-hedge net delta
mean absolute pre-hedge net delta
pre-hedge net-delta RMSE
maximum absolute post-hedge residual delta
mean absolute post-hedge residual delta
post-hedge residual-delta RMSE
```

Do not use one field for both policy trigger state and post-execution residual risk.

## Required tests

- Fixed-interval hedge reduces post-hedge residual delta when a tradable integer hedge exists.
- Hold decisions preserve equal before and after delta.
- Quantity rounding residual is recorded.
- Summary metrics use the correct fields.
- Portfolio value timestamps align with before/after state.
- Wider bands may increase pre-hedge delta while reducing turnover.
- Post-hedge residual metrics remain meaningful under coarse futures multipliers.

---

# 10. Harden numerical validation

## Black-Scholes

Validate all inputs are finite:

```text
spot
strike
time to expiry
volatility
risk-free rate
dividend yield
```

Required behavior:

- Non-finite input fails explicitly.
- Negative time fails.
- Negative volatility fails.
- Zero volatility follows the documented deterministic boundary.
- Zero time follows exact payoff.

## Implied volatility

Validate:

```text
observed price
spot
strike
time to expiry
risk-free rate
dividend yield
lower volatility
upper volatility
price tolerance
maximum iterations
```

Required behavior:

- Bounds are finite.
- Lower bound is non-negative.
- Upper bound exceeds lower bound.
- Tolerance is positive and finite.
- Maximum iterations is positive.
- Impossible price fails.
- Intrinsic-boundary price follows documented behavior.
- Do not return `0.0` when the caller provided a strictly positive lower bound unless the result contract explicitly reports that boundary exception.

Preferred result:

```python
class ImpliedVolatilityResult:
    implied_volatility: float | None
    converged: bool
    iterations: int
    final_price_error: float
    reason_code: str
```

## Required tests

- NaN rate rejected.
- Infinite dividend yield rejected.
- NaN volatility bound rejected.
- Reversed bounds rejected.
- Zero tolerance rejected.
- Intrinsic-boundary behavior documented and tested.
- Non-convergence returns explicit reason.
- No silent zero substitution.

---

# 11. Clarify valuation-record units

## Problem

Some fields are per-unit while Greeks are multiplier-adjusted.

## Required model

Rename fields or split models so units are explicit.

Suggested:

```python
class OptionUnitValuation:
    unit_price: float
    unit_intrinsic_value: float
    unit_time_value: float
    unit_delta: float
    unit_gamma: float
    unit_theta_per_year: float
    unit_vega_per_volatility_unit: float
```

```python
class OptionPositionValuation:
    quantity: int
    multiplier: int
    market_value: Decimal
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta_per_year: float
    portfolio_vega_per_volatility_unit: float
```

Equivalent naming is acceptable.

Do not leave a field named `price` beside multiplier-adjusted Greeks without explicit documentation.

## Required tests

- Position market value equals unit price × quantity × multiplier.
- Portfolio delta equals unit delta × quantity × multiplier.
- Portfolio gamma equals unit gamma × quantity × multiplier.
- Theta and vega scale consistently.
- Artifact columns include units in names or schema documentation.

---

# 12. Artifact and manifest updates

Update the simulation manifest to include:

```text
strategy_config_hash
market_config_hash
path_config_hash
path_hash
policy_config_hash
option_cost_model_hash
futures_cost_model_hash
runtime_risk_hash
run_config_hash
simulation_clock_config
selected_expiry
selected_strike
option_multiplier
futures_multiplier
futures_delta_per_contract
accounting_tolerance
quantity_rounding
```

Update artifact schemas to include:

```text
session_date
local timestamp
UTC timestamp
pre-hedge delta
post-hedge delta
continuous target quantity
rounded quantity
session hedge count
total hedge count
position P&L
session P&L
```

Failed manifests must still persist the full run specification when available.

Do not commit generated artifacts.

---

# 13. Documentation updates

Add or update:

```text
docs/simulation/architecture.md
docs/simulation/numerical-conventions.md
docs/simulation/ledger-and-pnl.md
docs/simulation/hedge-policies.md
docs/simulation/artifacts.md
docs/strategy/risk-policy-v1.md
docs/strategy/configuration-reference.md
docs/research/whalley-wilmott-band.md
docs/data-models.md
docs/testing.md
docs/observability.md
docs/plan/roadmap.md
README.md
```

Document:

- Strategy contract versus simulation-market contract.
- Simulation run contract and hashes.
- Trading-session clock.
- Weekday-only calendar limitation.
- Expiry/session consistency.
- Exit-before-hedge ordering.
- Daily versus position P&L.
- Per-session hedge counts.
- Multiplier-aware premium risk.
- Pre-hedge versus post-hedge delta.
- Exact Whalley-Wilmott formula and source.
- Numerical-validation behavior.
- Remaining limitations.

`docs/api.md` should continue to state that SIM-1 exposes no HTTP or WebSocket procedures.

---

# 14. Required regression tests

Create focused integration tests in addition to unit tests.

Suggested files:

```text
backend/tests/simulation/test_contract_integration.py
backend/tests/simulation/test_event_ordering.py
backend/tests/simulation/test_risk_sessions.py
backend/tests/simulation/test_run_identity.py
backend/tests/simulation/test_clock.py
backend/tests/hedging/test_whalley_wilmott.py
backend/tests/options/test_numerical_validation.py
```

At minimum, cover:

## Contract integration

- Engine consumes every behavior-changing STRAT-1 field.
- Engine consumes every simulation-market field.
- Hidden constants are absent.
- Selected expiry and strike match the configured rules.
- Multipliers propagate into fills, ledger, Greeks, and risk.

## Event ordering

- Exit before hedge.
- No same-timestamp round trip.
- Exit precedence is deterministic.
- Risk exit does not create a hedge first.

## Session risk

- Daily P&L resets.
- Position P&L does not reset.
- Per-session hedge count resets.
- Total hedge count persists.
- Friday-to-Monday boundary works.

## Run identity

- Every behavior-changing input changes the run identity.
- Runtime timestamps do not.
- Immutable run-store collisions do not occur for distinct runs.

## Whalley-Wilmott

- Exact formula regression.
- Units and monotonicity.
- Zero and invalid boundaries.

## Metrics

- Pre-hedge and post-hedge values are separate.
- Summary uses the correct columns.

## Numerical validation

- Non-finite rates and bounds fail.
- IV failure reason is explicit.

---

# 15. Acceptance criteria

Acceptance verified on `feature/deterministic-option-and-hedge-simulator` through commit `dcccdc9`: 221 backend tests passed, STRAT-1 validation passed, all five policy runs reconciled to `0.00`, frontend lint and build passed, and repository hygiene checks passed.

## Contract-driven engine

- [x] No hidden option or futures contract constants remain in the engine.
- [x] Simulation-market configuration is strict, typed, persisted, and hashed.
- [x] STRAT-1 expiry rules are executed.
- [x] STRAT-1 strike rules are executed.
- [x] Option and futures multipliers are explicit.
- [x] Futures delta per contract is explicit.

## Time and expiry

- [x] Weekends are skipped.
- [x] Asia/Kolkata and configured entry time are used.
- [x] Contract expiry and year fraction share one source of truth.
- [x] No negative maturity reaches pricing.

## Event ordering

- [x] Exit rules run before hedge policy.
- [x] No hedge is opened at an exit timestamp.
- [x] No same-timestamp hedge-open/close round trip occurs.
- [x] Exit precedence is tested.

## Risk

- [x] Position P&L and daily P&L are separate.
- [x] Daily P&L resets by session.
- [x] Per-session hedge count resets.
- [x] Total hedge count remains available.
- [x] Risk decisions record observed value and limit.
- [x] Premium-at-risk includes multipliers.

## Whalley-Wilmott

- [x] Formula exactly matches the documented source.
- [x] Exact numeric regression test exists.
- [x] Units are explicit.
- [x] Boundary behavior is documented.

## Reproducibility

- [x] Every behavior-changing input appears in run identity.
- [x] Distinct runtime risk inputs produce distinct run IDs.
- [x] Identical semantic inputs produce identical run IDs.
- [x] Immutable run-store collisions are eliminated.

## Metrics

- [x] Pre-hedge and post-hedge delta are separate.
- [x] Summary metrics use correctly timed fields.
- [x] Quantity-rounding residual is visible.

## Numerical hardening

- [x] Rates and yields must be finite.
- [x] IV bounds and tolerance must be valid.
- [x] No silent zero result on solver failure.
- [x] Valuation units are explicit.

## Verification

- [x] All backend tests pass.
- [x] Frontend lint passes.
- [x] Frontend build passes.
- [x] `git diff --check` passes.
- [x] No direct `useEffect` exists outside `useMountEffect`.
- [x] No tracked Python cache files exist.
- [x] No broker or order-placement code is added.
- [x] No live market dependency is added.
- [x] Intraday realized variance remains unimplemented.

---

# 16. Verification commands

From the repository root:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Run STRAT-1 validation:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
```

Run all five policies on the same deterministic path:

```bash
for policy in no_hedge fixed_interval delta_threshold constant_band whalley_wilmott
do
  UV_CACHE_DIR=/tmp/uv-cache \
  uv run python -m app.cli.run_gamma_simulation \
    --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
    --market-config ../config/simulation/nifty-synthetic-market-v1.yaml \
    --path-generator gbm \
    --seed 17 \
    --policy "$policy"
done
```

Verify that all five runs report the same:

```text
strategy_config_hash
market_config_hash
path_config_hash
path_hash
seed
```

and differ only where policy-dependent inputs or outputs should differ.

Run frontend regression checks:

```bash
cd ../frontend
npm run lint
npm run build
```

Run repository checks:

```bash
cd ..
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
grep -R "useEffect" frontend/src \
  --exclude="useMountEffect.ts"
```

---

# 17. Suggested commit sequence

Use small reviewable commits:

```text
1. Add simulation-market and run-config models with hashing
2. Add deterministic session clock and expiry unification
3. Make contract and strike selection config-driven
4. Correct event ordering and exit precedence
5. Implement session-aware risk state
6. Correct Whalley-Wilmott formula and documentation
7. Apply multipliers to premium risk and valuation units
8. Split pre-hedge and post-hedge state and metrics
9. Harden Black-Scholes and IV numerical validation
10. Update artifacts, CLI, docs, and integration tests
11. Run full verification and repository hygiene checks
```

Do not combine all corrections into one unreviewable commit.

---

# 18. Codex completion report

Codex must report:

1. Starting commit SHA.
2. Ending commit SHA.
3. Commits created.
4. Files added.
5. Files modified.
6. Files removed.
7. Simulation-market contract design.
8. Simulation-run contract design.
9. Run-hash canonicalization.
10. Expiry and session-clock semantics.
11. Strike and expiry selection behavior.
12. Option multiplier.
13. Futures multiplier.
14. Futures delta-per-contract convention.
15. Exit-before-hedge ordering.
16. Exit precedence.
17. Position P&L semantics.
18. Daily P&L semantics.
19. Per-session hedge-count semantics.
20. Premium-at-risk formula.
21. Whalley-Wilmott source and exact implemented formula.
22. Numerical-validation changes.
23. Pre-hedge and post-hedge metric changes.
24. Artifact schema changes.
25. Backend test count and result.
26. STRAT-1 validation CLI result.
27. Five-policy simulation results.
28. Evidence that the five policies used the same path hash.
29. Frontend lint result.
30. Frontend build result.
31. `git diff --check` result.
32. Direct `useEffect` scan result.
33. Known limitations.
34. Confirmation that no broker or order-placement path was added.
35. Confirmation that SIM-1 remains offline and deterministic.
36. Confirmation that intraday realized variance remains unimplemented.

Use this status only when all acceptance criteria pass:

```text
STRAT-1: COMPLETE
SIM-1: COMPLETE
SIM-1.1 CORRECTIONS: COMPLETE
Live broker execution: NOT IMPLEMENTED
Paper execution: NOT IMPLEMENTED
Historical option-chain replay: NOT IMPLEMENTED
Ready for DATA-1 / OPTIONS-1: YES
```
