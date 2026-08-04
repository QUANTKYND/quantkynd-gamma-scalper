# Core Data Models

This document defines conceptual models and invariants. Transport schemas, database rows, domain objects, and Redis values may differ in shape, but must preserve the same meaning.

## Identity conventions

All IDs are opaque strings in APIs. The MVP may use UUIDv4 internally.

Primary identifiers:

```text
instrument_id
contract_id
session_id
dataset_id
research_run_id
strategy_id
strategy_run_id
surface_id
candidate_id
intent_id
risk_decision_id
order_id
broker_order_id
fill_id
position_id
reconciliation_id
```

## Existing RV research models

LIVE-RV-1 extends `RVDatasetMetadata.source` with `upstox_historical`. Dataset identity includes the instrument key, ordered finalized session timestamps and closes, frequency, and provider. Live quotes are excluded.

### `RVLiveOverlayMetadata`

```text
provider
instrument_key
price_source
is_provisional
freshness
market_status
previous_close
last_trade_at
received_at
```

`price_source=live_ltp` is provisional and never denotes a completed daily close.

### `RVEstimatorMetadata`

Identifies estimator formula, input frequency, return convention, annualization, observation timing, and whether the estimator is intraday realized variance.

### `RVDatasetMetadata`

Identifies dataset source, symbol, observation range, stable dataset ID, computation time, and synthetic parameters where applicable.

### `RVHorizonEstimate`

```text
horizon_sessions
horizon_variance
annualized_variance
annualized_volatility
```

### `RVForecastHistoryPoint`

```text
origin_date
target_start
target_end
price
forecast_annualized_variance
forecast_annualized_volatility
actual_annualized_variance
actual_annualized_volatility
```

### `RVRunManifest`

Captures run identity, status, dataset, estimator, model, parameters, horizon, evaluation method, hashes, source commit, artifacts, and failure reason.

## Instrument and session models

### `UnderlyingInstrument`

```text
instrument_id
exchange
segment
symbol
name
currency
tick_size
lot_size
price_scale
valid_from
valid_until
provider_keys
```

### `FuturesContract`

```text
contract_id
underlying_instrument_id
exchange
expiry
multiplier
lot_size
tick_size
settlement_type
provider_keys
valid_from
valid_until
```

### `OptionContract`

```text
contract_id
underlying_instrument_id
exchange
expiry
strike
option_type
exercise_style
settlement_type
multiplier
lot_size
tick_size
provider_keys
valid_from
valid_until
```

Invariants:

- Strike is positive.
- Expiry is explicit and timezone-independent as an exchange date.
- Option type is `call` or `put`.
- Contract identity never depends on a mutable display symbol alone.
- Provider identifiers are versioned and time-bounded.
- Expired or not-yet-listed contracts cannot enter a point-in-time chain.

### `TradingSession`

```text
session_id
exchange
session_date
open_at
close_at
pre_open_at
post_close_at
timezone
status
```

All timestamps are timezone-aware. Storage uses UTC; exchange session interpretation uses `Asia/Kolkata` for NSE instruments.

## Market-event models

### `UnderlyingQuote`

```text
instrument_id
exchange_timestamp
received_at
bid_price
bid_size
ask_price
ask_size
last_price
last_size
sequence
source
quality_flags
```

LIVE-RV-1 keeps a bounded non-durable `LiveQuoteState` with LTP, previous close, last-trade quantity, provider message time, last-trade time, receipt time, processing time, market status, and process-local sequence. Provider time and receipt time remain distinct.

The process-local sequence is allocated after validation and increases independently for each instrument only when its quote is accepted. Invalid provider observations consume no accepted-quote sequence. Provider market status is retained as `segment_statuses`; an instrument derives its displayed state from its own `NSE_INDEX`, `BSE_INDEX`, `NSE_EQ`, or `BSE_EQ` segment.

### `OptionQuote`

```text
contract_id
exchange_timestamp
received_at
bid_price
bid_size
ask_price
ask_size
last_price
last_size
open_interest
volume
sequence
source
quality_flags
```

### `OptionTrade`

```text
contract_id
exchange_timestamp
received_at
price
quantity
trade_id
source
quality_flags
```

### `OptionChainSnapshot`

```text
snapshot_id
underlying_instrument_id
as_of
spot_or_future_price
contract_ids
source_event_range
data_quality_summary
```

A snapshot references constituent quotes; it does not duplicate uncontrolled quote values without provenance.

### `DataQualityEvent`

```text
event_id
observed_at
scope_type
scope_id
severity
code
details
source_event_id
resolved_at
```

Quality codes include stale, crossed, duplicate, out-of-order, missing sequence, invalid price, missing contract, market closed, and provider degradation.

## Option analytics models

### `OptionValuationInput`

```text
contract_id
as_of
underlying_price
strike
time_to_expiry_years
risk_free_rate
dividend_yield
volatility
model_id
```

### `GreekSnapshot`

```text
contract_id
as_of
model_id
input_snapshot_id
price
delta
gamma
theta
vega
rho
```

### `IVPoint`

```text
contract_id
as_of
mid_price
implied_volatility
solver_status
iterations
quality_flags
```

### `IVSurfaceSnapshot`

```text
surface_id
underlying_instrument_id
as_of
forward_price
discount_factor
expiries
points
fit_method
arbitrage_checks
quality_summary
```

### `ImpliedVarianceEstimate`

```text
underlying_instrument_id
as_of
target_start
target_end
horizon_years
method
annualized_implied_variance
coverage
interpolation_flags
quality_flags
```

## Strategy models

STRAT-1 materializes a strict immutable `StrategyContractV1` with identity, creation timestamp, simulation-only mode, underlying, signal, entry, expiry, strike, position, hedging, exit, and risk blocks. Its behavioral content excludes `created_at` from a canonical SHA-256 configuration hash.

### `StrategyDefinition`

```text
strategy_id
name
version
underlying_rule
position_template
entry_rules
exit_rules
hedge_policy_id
risk_policy_id
execution_policy_id
configuration_hash
source_commit
```

### `StrategyRun`

```text
strategy_run_id
strategy_id
environment
started_at
completed_at
status
dataset_id
configuration_hash
source_commit
failure_reason
```

### `EntryCandidate`

```text
candidate_id
strategy_run_id
as_of
contract_ids
forecast_variance
implied_variance
raw_variance_edge
expected_gamma_pnl
expected_theta
expected_option_cost
expected_hedge_cost
model_risk_buffer
net_expected_edge
eligibility
rejection_reasons
```

### `HedgeDecision`

```text
decision_id
strategy_run_id
as_of
position_id
current_delta
target_delta
lower_boundary
upper_boundary
policy_id
action
requested_quantity
reason_codes
state_snapshot_id
```

Actions are `hold`, `buy_hedge`, `sell_hedge`, `reduce_risk`, or `flatten`.

### `TradeIntent`

```text
intent_id
strategy_run_id
created_at
intent_type
instrument_id
side
quantity
limit_policy
valid_until
strategy_reason
risk_decision_id
idempotency_key
status
```

Intents are immutable. Status changes are separate events.

## Risk models

### `RiskPolicy`

```text
risk_policy_id
version
max_open_positions
max_premium_at_risk
max_daily_loss
max_theta_budget
max_absolute_delta
max_hedges_per_session
max_quote_age_ms
max_spread_bps
carry_policy
end_of_day_policy
configuration_hash
```

### `RiskDecision`

```text
risk_decision_id
intent_id
evaluated_at
policy_id
approved
reason_codes
limits_before
limits_after
state_snapshot_id
```

### `KillSwitchState`

```text
scope
engaged
reason
engaged_at
engaged_by
released_at
released_by
```

The kill switch defaults to engaged when required state is unavailable or uncertain.

## Execution and ledger models

### `Order`

```text
order_id
intent_id
account_scope
instrument_id
side
quantity
order_type
limit_price
time_in_force
idempotency_key
status
created_at
updated_at
```

### `OrderTransition`

```text
order_id
transition_id
occurred_at
from_status
to_status
source
provider_payload_hash
reason
```

Order status transitions are append-only.

### `Fill`

```text
fill_id
order_id
instrument_id
filled_at
quantity
price
fees
slippage_reference_price
slippage_amount
provider_fill_id
```

### `PositionLot`

```text
position_id
instrument_id
opened_at
quantity
average_cost
realized_pnl
strategy_run_id
```

### `CashLedgerEntry`

```text
entry_id
occurred_at
currency
amount
entry_type
reference_type
reference_id
balance_after
```

### `MarkSnapshot`

```text
position_id
as_of
mark_price
mark_source
unrealized_pnl
delta
gamma
theta
vega
quality_flags
```

### `ReconciliationResult`

```text
reconciliation_id
as_of
scope
internal_state_hash
external_state_hash
matched
differences
resolution_status
```

## Precision conventions

- Analytics returns, variance, volatility, IV, and Greeks use floating-point values with explicit units.
- Durable prices, fees, cash, and ledger balances use decimal values or integer minor units.
- Quantities use integers where instruments trade in indivisible lots; fractional support must be explicit.
- Never infer units from field names without a documented contract.

## Offline simulation models

SIM-1 uses immutable option contracts, explicit market states, option valuations, order intents, simulated fills, hedge and risk decisions, ledger entries, Greek-attribution intervals, reconciliation, summary, and run manifest values. Market states carry explicit step year fractions. Fills retain reference price, executable price, notional, spread, slippage, fixed, and proportional costs. The run manifest records every configuration and provenance hash needed to reproduce a run.
