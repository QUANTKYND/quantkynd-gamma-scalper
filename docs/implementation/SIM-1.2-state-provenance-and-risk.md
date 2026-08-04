# Codex Task — SIM-1.2 State Provenance, Market-Contract, and Risk Enforcement

## Milestone

**SIM-1.2 — Deterministic state provenance, complete market-contract consumption, and executable risk gates**

## Branch

```text
feature/deterministic-option-and-hedge-simulator
```

## Objective

Correct the remaining gaps in the STRAT-1/SIM-1 implementation before merging the branch.

The current implementation has substantially completed the earlier SIM-1.1 corrections, including:

- A separate simulation-market contract.
- Contract-driven option expiry and strike selection.
- Explicit option and futures multipliers.
- Session-aware timestamps.
- Exit-before-hedge event ordering.
- Position and session risk state.
- Corrected Whalley-Wilmott source formula.
- Expanded run identity.
- Multiplier-aware premium risk.
- Separate pre-hedge and post-hedge delta metrics.
- Hardened Black-Scholes and implied-volatility validation.

This task addresses the remaining correctness issues:

1. The hashed path can differ from the market states actually executed.
2. The simulation clock and futures-expiry convention are not enforced by `run_simulation`.
3. Several fields in the simulation-market contract are ignored or duplicated elsewhere.
4. Several documented STRAT-1 risk limits are not executable gates.
5. Daily and position P&L omit economically important losses.
6. Early simulation failures can occur before a failed manifest exists.
7. CLI evidence is insufficient to prove policy runs used the same path.
8. Strict configuration models still need finite-number enforcement.

Do not add live trading, paper routing, broker orders, historical option chains, Redis, Postgres, deep hedging, or intraday realized variance.

---

# Required reading

Read:

```text
AGENTS.md
docs/README.md
docs/conventions.md
docs/design.md
docs/data-models.md
docs/testing.md
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
config/simulation/nifty-synthetic-market-v2.yaml
```

Inspect especially:

```text
backend/app/simulation/engine.py
backend/app/simulation/paths.py
backend/app/simulation/clock.py
backend/app/simulation/config.py
backend/app/simulation/risk.py
backend/app/simulation/artifacts.py
backend/app/simulation/run_store.py
backend/app/cli/run_gamma_simulation.py
backend/app/options/selection.py
backend/app/portfolio/ledger.py
backend/app/portfolio/positions.py
backend/tests/simulation/
```

Repository rules remain unchanged:

- No explanatory comments in new code.
- Strict names, types, functions, tests, and docs explain the implementation.
- No direct `useEffect` outside the approved `useMountEffect`.
- Unknown configuration fields fail.
- No secrets appear in logs or artifacts.
- The simulator remains offline and deterministic.

---

# 1. Make the path hash describe the state that is actually executed

## Problem

`GeneratedPath.path_hash` hashes every original `MarketState`.

`run_simulation` subsequently replaces `time_to_expiry_years` through `_states_with_expiry`, but continues to record the original path hash.

A normal caller can therefore submit a path whose hashed states contain one option maturity while the engine executes a different maturity selected from the simulation-market contract.

The same issue exists for session identity and futures maturity when a path was generated without the configured market clock.

This breaks the central artifact claim:

```text
path hash -> exact states used by the simulator
```

## Required design

Separate exogenous path data from derived executable market state.

Preferred structure:

```python
class UnderlyingPathPoint:
    timestamp: datetime
    session_date: date
    session_index: int
    step_index: int
    spot: float
    realized_step_year_fraction: float
    risk_free_rate: float
    dividend_yield: float
    implied_volatility: float
```

```python
class GeneratedUnderlyingPath:
    generator_id: str
    generator_version: int
    seed: int | None
    canonical_parameters: dict[str, object]
    points: tuple[UnderlyingPathPoint, ...]
    path_hash: str
```

The engine derives:

```text
option time to expiry
futures remaining maturity
futures price
local timestamp
contract marks
```

from:

```text
underlying path
simulation clock
selected option expiry
futures-expiry convention
simulation-market config
```

Alternative design is acceptable only if the final executable market states receive a new stable hash and the manifest clearly distinguishes:

```text
underlying_path_hash
executable_market_state_hash
```

## Non-negotiable invariant

The hash recorded as representing executable market states must be computed from the exact states in:

```text
result.market_states
market-states.csv
```

The engine must not mutate a hashed state sequence without creating a new hash identity.

## Remove duplicated path ownership

Remove these from GBM and piecewise path configuration when a simulation-market contract is supplied:

```text
option_expiry_years
futures_maturity_years
calendar-day timestamp generation
```

They are owned by:

```text
selected option expiry
SimulationClockConfig
SyntheticFuturesMarketConfig
```

If backward compatibility is temporarily retained, reject any mismatch explicitly.

## Required tests

- A path created with an incompatible option maturity is rejected or normalized under a new executable-state hash.
- The hash for `result.market_states` reproduces from `market-states.csv`.
- Changing selected option expiry changes executable-state hash.
- Changing futures expiry convention changes executable-state hash.
- Changing only an unused legacy field cannot change run identity.
- Original path hash and executable-state hash are clearly distinct where both exist.
- No normal test fixture executes market states different from those represented by its hashes.

---

# 2. Enforce the simulation clock inside `run_simulation`

## Problem

The CLI generates a weekday-only clock, but `run_simulation` accepts arbitrary generated paths.

Existing direct callers can provide:

```text
consecutive calendar dates
weekend sessions
UTC-derived session dates
one state per calendar day
step fractions inconsistent with configured decision times
```

The engine currently validates only that the market clock timezone matches the strategy and that the entry time appears in the configured decision times.

## Required validation

Before opening the position, validate every executable point against the market clock:

```text
timestamps strictly increase
timestamps are timezone-aware UTC
local timestamps use configured timezone
session dates are weekdays under current calendar mode
session index is non-decreasing
step index is strictly increasing
decision times belong to configured decision_times_local
first decision uses strategy.entry.entry_time_local
step year fractions follow configured clock convention
states do not skip backward between sessions
```

Prefer generating sessions centrally and joining spot-path observations to those sessions rather than validating independently generated calendar timestamps.

## Date conversion

Never use:

```python
datetime.astimezone()
```

without an explicit timezone when deriving exchange-session identity.

Use:

```python
ZoneInfo(market.clock.timezone)
```

The CLI must not derive a session date from the host timezone.

## Required tests

- A weekend state is rejected.
- A path with host-local dates cannot silently pass.
- A UTC timestamp is converted through `Asia/Kolkata` before deriving session date.
- A decision time absent from market config is rejected.
- An inconsistent step year fraction is rejected.
- A correctly generated Friday-to-Monday path passes.
- `run_simulation` and the CLI use the same session-building path.

---

# 3. Make the futures contract fully owned by the simulation-market contract

## Problem

The simulation-market config defines:

```text
futures.expiry_rule
futures.expiry_buffer_sessions
futures.half_spread_per_unit
```

but these are not consistently consumed by `run_simulation`.

Futures prices are already present in the supplied path and may have been generated with a different maturity.

The CLI also uses a separate hardcoded `FUTURES_COSTS.half_spread_per_unit`.

This creates two sources of truth.

## Required design

The simulation-market contract must own futures identity and carry convention:

```text
instrument ID
multiplier
delta per contract
expiry rule
expiry buffer
```

The run cost model must own execution friction:

```text
fixed cost
proportional cost
half spread
slippage
```

Choose one owner for `half_spread_per_unit`.

Preferred correction:

- Remove `half_spread_per_unit` from `SyntheticFuturesMarketConfig`.
- Keep all execution friction in `futures_cost_model`.
- Persist and hash that cost model through `SimulationRunConfig`.

If the field remains in market config, the run cost model must derive from it and reject conflicting inputs.

## Futures pricing

Derive futures remaining maturity for every state from:

```text
entry session
holding horizon
futures expiry rule
expiry buffer
configured session clock
```

Then derive futures price from spot and carry inside the executable-state builder.

Do not trust a caller-provided futures-price series in generated GBM paths unless the path mode explicitly declares:

```text
futures_price_mode: explicit
```

and the mode is hashed.

## Required tests

- Changing futures expiry buffer changes derived futures prices.
- Changing futures expiry buffer changes executable-state hash and run ID.
- A direct `run_simulation` caller cannot bypass the futures-expiry convention.
- Only one half-spread source exists.
- A conflicting futures spread configuration fails.
- Futures multiplier and delta-per-contract remain separately explicit.

---

# 4. Enforce synthetic quote quality and liquidity rules

## Problem

STRAT-1 says:

```text
require_quote_quality: true
require_liquidity: true
maximum_option_relative_spread: 0.10
```

The synthetic market allows:

```text
relative_spread up to 1
volume = 0
open interest = 0
```

and the engine still selects the straddle.

## Required entry checks

Before option-entry intents are accepted:

```text
selected combined relative spread <= configured maximum
selected volume satisfies the v1 synthetic liquidity requirement
selected open interest satisfies the v1 synthetic liquidity requirement
call and put exist
call and put share strike
call and put share expiry
call and put share multiplier
```

Define the SIM-1 synthetic liquidity rule explicitly.

A narrow v1 rule is sufficient:

```text
combined volume > 0
combined open interest > 0
```

If stronger thresholds are desired, place them in the simulation-market config and hash them.

## Required risk records

Create reconstructable entry decisions:

```text
option_spread_quality
option_volume_quality
option_open_interest_quality
matched_straddle_integrity
```

Each records:

```text
observed value
configured threshold
approve or reject
reason code
```

## Required tests

- Spread above maximum rejects entry.
- Zero volume rejects when liquidity is required.
- Zero open interest rejects when liquidity is required.
- Mismatched multiplier rejects.
- Passing synthetic liquidity produces approval records.
- No rejected entry is journaled as an open position.

---

# 5. Make the daily-theta limit executable

## Problem

The STRAT-1 risk policy documents:

```text
maximum_daily_theta_fraction
```

The simulator already computes multiplier-adjusted portfolio theta, but no entry risk gate uses it.

## Required calculation

At entry:

```text
absolute daily theta
=
abs(portfolio_theta_per_year) / trading_periods_per_year
```

```text
daily theta limit
=
starting NAV × maximum_daily_theta_fraction
```

Create an entry risk decision:

```text
rule_id: maximum_daily_theta
observed_value: absolute daily theta in INR
configured_limit: daily theta limit in INR
decision: approve or reject
```

Perform this check before entry fills are persisted.

## Required tests

- A low theta burden passes.
- A deliberately tight theta limit rejects entry.
- Contract multiplier scales theta burden.
- Trading-period convention comes from the market clock.
- Rejected theta entry produces no open option position.

---

# 6. Resolve expected-edge semantics explicitly

## Problem

The strategy contract documents:

```text
minimum_expected_net_edge_fraction
```

SIM-1 does not model physical-versus-implied variance edge and therefore cannot calculate this gate honestly.

The gate must not remain silently ignored.

## Required choice

Choose one explicit design.

### Preferred design for SIM-1

Add a hashed simulation assumption:

```python
class SimulationEntryAssumptions:
    edge_gate_mode: Literal["not_evaluated_hedge_policy_benchmark"]
```

Persist it in `SimulationRunConfig`, the manifest, and docs.

The simulator must emit an entry decision:

```text
rule_id: minimum_expected_net_edge
decision: not_evaluated
reason_code: deferred_to_edge_1
```

It must not claim that the edge gate passed.

### Alternative

Add a controlled, typed expected-edge scenario input and evaluate it.

Do not derive a fake edge from the GBM path or future states.

## Required tests

- Every run has an explicit expected-edge gate disposition.
- The assumption is hashed.
- No future path information is used.
- Summary and manifest do not claim the entry edge was validated.

---

# 7. Make the absolute-delta limit a hard deterministic control

## Problem

`maximum_absolute_delta_units` is documented as a cap.

The current risk engine records a breach but allows the simulation to continue.

This is especially unsafe for:

```text
no_hedge policy
coarse futures quantity rounding
a hedge request that rounds to zero
a post-fill residual still above the hard limit
```

## Required semantics

Choose and document one deterministic behavior.

### Preferred behavior

1. Evaluate routine hedge policy.
2. Predict the post-fill residual delta.
3. If the residual exceeds the hard delta limit:
   - replace the routine action with a risk-reduction hedge that minimizes absolute residual delta;
   - apply quantity and multiplier constraints;
   - execute only if it reduces risk.
4. Recalculate post-fill delta.
5. If the hard limit still cannot be satisfied because of contract granularity:
   - exit the strategy with a stable risk reason.

Suggested reason codes:

```text
absolute_delta_within_limit
absolute_delta_forced_hedge
absolute_delta_unhedgeable
absolute_delta_exit
```

### Simpler accepted behavior

Exit immediately on a pre-decision absolute-delta breach.

If this path is chosen, add the exit reason to the strategy precedence and update the strategy hash/version before merge.

## Required tests

- A no-hedge run cannot remain above the hard limit indefinitely.
- A rounded-zero routine hedge cannot bypass the limit.
- A forced hedge must reduce absolute delta.
- An unhedgeable coarse-contract residual exits deterministically.
- Post-fill delta is checked.
- Risk override is visible in intents, fills, decisions, and events.

---

# 8. Correct position and daily P&L reference semantics

## Position loss

### Problem

`position_open_value` is initialized after entry fills and entry costs.

The position-loss metric therefore excludes:

```text
entry spread
entry slippage
fixed entry costs
proportional entry costs
```

### Required behavior

Position P&L must be measured from the portfolio value immediately before entry.

For the single-position SIM-1 contract:

```text
position reference NAV = starting NAV before option entry
position P&L = current portfolio value - position reference NAV
```

Entry costs must appear immediately as a negative position P&L contribution.

## Daily loss

### Problem

On a new session, the current first mark becomes the new session baseline.

Any overnight movement between the prior session’s last mark and the current session’s first mark disappears from daily P&L.

### Required behavior

Daily/session P&L must include the overnight gap.

Use the prior session’s final marked portfolio value as the next session reference.

Suggested state:

```python
class SimulationRiskState:
    position_reference_portfolio_value: Decimal
    position_pnl_from_entry: Decimal
    session_reference_portfolio_value: Decimal
    session_pnl: Decimal
    previous_marked_portfolio_value: Decimal
    current_session_date: date
    hedges_in_current_session: int
    total_hedges: int
```

At a session transition:

```text
session reference = previous session final marked value
session P&L = current first mark - session reference
hedges in current session = 0
```

## Required tests

- Entry costs immediately reduce position P&L.
- Entry costs contribute to first-session P&L.
- Overnight loss contributes to new-session daily P&L.
- Overnight gain contributes to new-session daily P&L.
- Position P&L remains cumulative.
- Per-session hedge count still resets.
- A daily-loss breach caused by an overnight gap exits at the first new-session decision.

---

# 9. Persist failed manifests for post-identity failures

## Problem

The CLI currently performs:

```text
configuration loading
path generation
run-config construction
contract selection
```

before creating the running manifest.

A failure after a deterministic run ID exists but before `create_run` leaves no failed manifest.

## Required boundary

Once `SimulationRunConfig` and `run_id` exist, all subsequent work must occur inside the run-store failure boundary.

The base manifest may use nullable fields while status is `running`:

```text
selected_expiry
selected_strike
```

Populate them in the completed manifest after contract selection.

Failures before deterministic identity exists may remain CLI validation failures without an artifact.

Failures after run identity exists must produce a failed manifest.

## Required tests

- No eligible expiry after run identity produces a failed manifest.
- Contract-selection failure produces a failed manifest.
- Engine failure produces a failed manifest.
- Reconciliation failure produces a failed manifest.
- Failed runs are not listed as complete.
- Temporary directories are never exposed.

---

# 10. Improve CLI reproducibility evidence

## Required success output

Add:

```text
simulator_version
strategy_config_hash
market_config_hash
path_config_hash
path_hash
executable_market_state_hash
run_config_hash
policy_config_hash
option_cost_model_hash
futures_cost_model_hash
runtime_risk_hash
```

The five-policy verification command must allow the operator to prove that all policies used the same:

```text
underlying path
executable market states
strategy contract
market contract
cost assumptions
seed
```

Only policy identity and policy parameters should differ.

## Required tests

- CLI output contains every provenance hash.
- Same seed and non-policy inputs produce the same path and market-state hashes across all five policies.
- Policy hash differs where expected.
- Output remains valid structured JSON.

---

# 11. Reject NaN and infinity in strict configuration models

## Problem

The strict Pydantic models forbid extra fields but do not globally disable NaN and infinity.

Fields with `gt`, `ge`, or `le` constraints can still have inconsistent behavior for non-finite values.

## Required configuration

Use:

```python
ConfigDict(
    extra="forbid",
    frozen=True,
    allow_inf_nan=False,
)
```

Apply to:

```text
strategy models
simulation-market models
simulation-run models
cost models
```

Retain explicit domain validations where useful.

## Required tests

Reject non-finite values for:

```text
starting NAV
risk fractions
delta thresholds
risk aversion
transaction-cost rate
strike interval
relative spread
futures delta
clock periods
cost-model values
accounting tolerance
```

---

# 12. Documentation updates

Update:

```text
docs/strategy/risk-policy-v1.md
docs/strategy/decision-log.md
docs/strategy/configuration-reference.md
docs/simulation/architecture.md
docs/simulation/numerical-conventions.md
docs/simulation/ledger-and-pnl.md
docs/simulation/artifacts.md
docs/testing.md
docs/observability.md
docs/plan/roadmap.md
README.md
```

Document:

- Underlying path versus executable market states.
- Both hashes and what each proves.
- Simulation-clock enforcement.
- Futures expiry and cost ownership.
- Synthetic spread/liquidity gates.
- Daily theta gate.
- Expected-edge deferral or controlled scenario input.
- Hard absolute-delta behavior.
- Entry-cost-inclusive position P&L.
- Overnight-inclusive daily P&L.
- Failed-manifest boundary.
- Full CLI provenance output.
- Weekday-only calendar remains a limitation.

Do not mark SIM-1.2 complete until the code, tests, and docs agree.

---

# 13. Acceptance criteria

## State provenance

- [x] Executed market states have a stable hash.
- [x] That hash reproduces from `market-states.csv`.
- [x] No hashed path is mutated without a new identity.
- [x] Option and futures maturities come from the market contract.
- [x] Legacy duplicated maturity fields are removed or rejected.

## Clock enforcement

- [x] `run_simulation` cannot silently execute weekend/calendar-day paths.
- [x] Exchange dates use explicit `Asia/Kolkata`.
- [x] Decision times and step fractions match the market clock.
- [x] CLI and direct engine calls use the same clock semantics.

## Futures contract

- [x] Futures expiry buffer affects executable prices.
- [x] One source owns half-spread.
- [x] Conflicting cost configuration fails.
- [x] Futures convention is hashed and persisted.

## Entry quality

- [x] Spread limit is enforced.
- [x] Required volume and open interest are enforced.
- [x] Matched-straddle integrity is enforced.
- [x] Daily theta limit is enforced.
- [x] Expected-edge gate has an explicit disposition.

## Risk

- [x] Absolute-delta cap is not telemetry-only.
- [x] Post-fill residual delta is checked.
- [x] Entry costs count in position P&L.
- [x] Overnight gaps count in daily P&L.
- [x] Daily and position loss remain separately testable.

## Artifacts

- [x] Post-identity failures persist failed manifests.
- [x] CLI emits complete provenance hashes.
- [x] Five-policy comparison can prove identical non-policy inputs.

## Validation

- [x] NaN and infinity are rejected in all strict configs.
- [x] Backend tests pass.
- [x] Frontend lint passes.
- [x] Frontend build passes.
- [x] `git diff --check` passes.
- [x] No direct `useEffect` exists outside `useMountEffect`.
- [x] No order-placement path is added.
- [x] Intraday realized variance remains unimplemented.

## Acceptance evidence

- Starting commit: `e0d417cca8d64c4f8cc8e6ad2089be192203b180`.
- Backend: `281 passed` with `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`.
- Strategy validation: valid with configuration hash `sha256:0030bd06406afbbcbe7334a034c778b417c3a2d69114459e8b12a35247fbbb4d`.
- Five-policy verification: all policies completed with identical strategy, market, path-config, path, executable-market-state, option-cost, futures-cost, runtime-risk, simulator-version, and seed identities. Policy and run-config hashes were distinct.
- Frontend: `npm run lint` passed and `npm run build` passed. Vite reported only its existing large-chunk advisory.
- Hygiene: `git diff --check` passed; tracked cache/generated-artifact scan was empty; direct `useEffect` appears only in `frontend/src/shared/hooks/useMountEffect.ts`.
- Scope: no broker or order-placement path was added; the simulator remains offline and deterministic; intraday realized variance remains unimplemented.

```text
STRAT-1: COMPLETE
SIM-1: COMPLETE
SIM-1.1: COMPLETE
SIM-1.2: COMPLETE
Merge recommendation: APPROVED
Ready for DATA-1: YES
```

---

# 14. Verification commands

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Validate strategy:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
```

Run all policies:

```bash
for policy in no_hedge fixed_interval delta_threshold constant_band whalley_wilmott
do
  UV_CACHE_DIR=/tmp/uv-cache \
  uv run python -m app.cli.run_gamma_simulation \
    --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
    --market-config ../config/simulation/nifty-synthetic-market-v2.yaml \
    --path-generator gbm \
    --seed 17 \
    --policy "$policy"
done
```

Verify identical non-policy hashes.

Frontend regression:

```bash
cd ../frontend
npm run lint
npm run build
```

Repository hygiene:

```bash
cd ..
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
grep -R "useEffect" frontend/src \
  --exclude="useMountEffect.ts"
```

---

# 15. Suggested commit sequence

```text
1. Separate underlying-path and executable-market-state identities
2. Enforce simulation clock and remove duplicated maturity ownership
3. Make futures expiry and cost ownership single-source
4. Add spread, liquidity, theta, and explicit edge-gate decisions
5. Enforce absolute-delta hard control
6. Correct entry-cost and overnight P&L references
7. Move post-identity work inside failed-manifest boundary
8. Expand CLI provenance output
9. Reject non-finite config values
10. Add integration regressions and update documentation
```

---

# 16. Codex completion report

Codex must report:

1. Starting commit SHA.
2. Ending commit SHA.
3. Commits created.
4. Files added.
5. Files modified.
6. Files removed.
7. Underlying-path model.
8. Executable-market-state model.
9. Path hash semantics.
10. Executable-state hash semantics.
11. Clock-enforcement rules.
12. Futures maturity convention.
13. Futures cost ownership.
14. Spread and liquidity gates.
15. Daily theta calculation.
16. Expected-edge gate disposition.
17. Absolute-delta hard-control behavior.
18. Position P&L reference.
19. Daily P&L and overnight-gap reference.
20. Failed-manifest boundary.
21. CLI provenance fields.
22. Non-finite configuration validation.
23. Backend test count and result.
24. Five-policy hash comparison.
25. Frontend lint result.
26. Frontend build result.
27. `git diff --check` result.
28. Direct `useEffect` scan result.
29. Known limitations.
30. Confirmation that no broker or order-placement path was added.
31. Confirmation that the simulator remains offline and deterministic.
32. Confirmation that intraday realized variance remains unimplemented.

Use this status only after all criteria pass:

```text
STRAT-1: COMPLETE
SIM-1: COMPLETE
SIM-1.1: COMPLETE
SIM-1.2: COMPLETE
Merge recommendation: APPROVED
Ready for DATA-1: YES
```
