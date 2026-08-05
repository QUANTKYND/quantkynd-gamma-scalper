# Core Data Models

This document defines conceptual models and invariants. Transport schemas, database rows, domain objects, and Redis values may differ in shape, but must preserve the same meaning.

## Identity conventions

All IDs are opaque strings in APIs. Catalogue economic identities, contract-version identities, provider-mapping identities, and normalized event identities use deterministic SHA-256 identities over canonical material. UUIDv4 may identify operational records only where reproducible identity is not required.

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

## Point-in-time instrument and contract models

DATA-1.0 separates economic identity, validity-bounded trading metadata, and provider mapping. Re-ingesting the same canonical catalogue content produces the same IDs. A provider key, display symbol, catalogue row, tick size, or lot size is never the sole economic identity.

### `UnderlyingInstrumentIdentity`

```text
instrument_id
exchange
canonical_symbol
instrument_type
currency
```

`canonical_symbol` is a QuantKYND-controlled stable symbol, not provider display text. Its changes require an explicit identity decision rather than an incidental catalogue update.

### `FuturesContractIdentity`

```text
contract_id
underlying_instrument_id
exchange
expiry
multiplier
settlement_type
currency
```

### `OptionContractIdentity`

```text
contract_id
underlying_instrument_id
exchange
expiry
strike
option_side
exercise_style
settlement_type
multiplier
currency
```

The option economic identity hash contains exactly exchange, underlying instrument ID, expiry exchange date, canonical Decimal strike, option side, exercise style, settlement type, economically defining Decimal multiplier, and currency. Futures use the corresponding fields without strike, option side, or exercise style. Provider, provider key, display symbol, catalogue version, validity timestamps, lot size, and tick size are excluded.

### Contract versions

`UnderlyingInstrumentVersion`, `FuturesContractVersion`, and `OptionContractVersion` contain validity-bounded trading metadata:

```text
instrument_id or contract_id
version_id
valid_from
valid_until
lot_size
tick_size
display_symbol
trading_status
catalogue_version_id
recorded_at
superseded_at
```

`valid_from` is inclusive and `valid_until` is exclusive in market effective time. The domain compatibility fields expose the knowledge record's `recorded_at`; `superseded_at` is derived compatibility state and is never mutated or persisted on the semantic row. Runtime timestamps do not participate in the deterministic version ID; validity and trading metadata do.

### `ProviderContractMapping`

```text
mapping_id
provider
provider_contract_key
contract_version_id
provider_payload_hash
source_row_identity
effective_from
effective_until
recorded_at
superseded_at
```

Invariants:

- Strikes, tick sizes, and multipliers are positive finite `Decimal` values at domain and durable boundaries.
- Expiry is explicit and timezone-independent as an exchange date.
- Option side is `call` or `put`.
- Contract identity never depends on a mutable display symbol alone.
- Multiple provider mappings can resolve to the same economic contract version.
- Provider identifiers and mappings are effective-time and knowledge-time bounded.
- Expired or not-yet-listed contracts cannot enter a point-in-time chain.
- Replacing validity-bounded trading metadata creates a new version without changing economic identity where the economic terms are unchanged.

## DATA-1.2 provider catalogue ingestion models

DATA-1.2 ingests one approved profile, `upstox-nse-nifty-index-derivatives-v1`, from a local official Upstox BOD NSE `NSE.json.gz` artifact. The profile supports the `NSE_INDEX|Nifty 50` underlying, its `NSE_FO` index futures, and its `NSE_FO` call and put options. `underlying_key` is authoritative for derivative relationship resolution. `underlying_symbol` is only a consistency check. Approved constants for this profile are `exchange=NSE`, `currency=INR`, `exercise_style=european`, `settlement_type=cash`, and `multiplier=1`; lot size remains trading metadata.

### `CatalogueSourceArtifact`

```text
source_artifact_id
provider
profile_version
media_type
compression
compressed_sha256
decompressed_sha256
compressed_byte_count
decompressed_byte_count
source_schema_version
artifact_object_key
```

The artifact identity includes exact compressed content and the parsing contract. File name, local path, operator, receipt time, recorded time, and temporary path are excluded. Different gzip bytes produce different artifact IDs even when decompressed content is equal.

### Source row identities

```text
source_row_semantic_id = provider + profile_version + canonical raw-row hash
source_row_occurrence_id = source_artifact_id + physical row number + canonical raw-row hash
```

Semantic row identity is independent of row order and artifact bytes. Physical occurrence identity preserves where a row appeared in one artifact. Provider mappings use `source_row_semantic_id`; row outcomes and membership provenance retain `source_row_occurrence_id`.

### Normalized catalogue identity

`CatalogueVersion.source_content_hash` is the normalized catalogue hash over sorted unique in-profile normalized row projections. The projection excludes row number, artifact identity, file name, receipt time, record time, duplicate occurrence count, raw object key order, and runtime metadata. `CatalogueVersion.row_count` is the accepted unique membership count.

### `CatalogueIngestionRun`

```text
ingestion_run_id
idempotency_key
command_digest
source_artifact_id
catalogue_version_id
catalogue_record_id
profile_version
original_file_name
effective_from
effective_until
started_at
recorded_at
completed_at
normalized_catalogue_hash
physical_row_count
accepted_unique_count
exact_duplicate_count
excluded_count
database_revision
```

DATA-1.2 persists accepted commit-mode runs only. `started_at` is invocation time; `recorded_at` is the single accepted write-boundary timestamp captured under the provider/profile lock immediately before durable transition planning; `completed_at` follows the writes. Accepted rows require `started_at <= recorded_at <= completed_at`. The catalogue version, every instrument version, every provider mapping, all corresponding temporal record identities, and the accepted run share that `recorded_at`. Validation failures, validate-only, dry-runs, and rejected commits have no durable knowledge timestamp or mutable run row.

The normalized semantic plan is independent of its runtime knowledge timestamp. Rebinding changes the knowledge record and therefore its temporal record ID, while preserving catalogue, version, mapping, instrument, row, outcome, and membership semantic identities.

Catalogue predecessor selection is knowledge-ordered rather than market-ordered. A first catalogue is permitted only when its provider/profile scope has no records. Every later catalogue explicitly names the current unsuperseded knowledge leaf. Existing instrument-version and provider/key mapping scopes likewise supersede their current knowledge leaves, even when the new market interval begins earlier than, equals, or is bounded before the predecessor interval.

Read-time market selection remains independent. After knowledge filtering and full graph validation, each eligible record walks its complete visible predecessor chain and suppresses every eligible ancestor it encounters, including through ineligible intermediate records. Immutable edges define that order; timestamps do not. A bounded H that supersedes ineligible B can therefore suppress eligible A inside H's interval, while A remains selected outside H and before B. Separate eligible roots still fail closed. The same resolver governs catalogue versions, instrument versions, provider mappings, and trading-session versions.

### `CatalogueRowOutcome`

```text
row_outcome_id
ingestion_run_id
source_row_occurrence_id
source_row_semantic_id
physical_row_number
raw_row_hash
normalized_row_hash
provider_contract_key
disposition
reason_codes
instrument_id
version_id
mapping_id
```

Allowed dispositions are `accepted`, `exact_duplicate`, and `excluded_by_profile`. In-profile malformed or conflicting rows reject the full catalogue and are not persisted as accepted-run outcomes.

### `CatalogueMembership`

```text
membership_id
catalogue_version_id
row_outcome_id
source_row_occurrence_id
source_row_semantic_id
instrument_id
version_id
mapping_id
provider_contract_key
raw_row_hash
normalized_row_hash
```

Membership has one row per accepted unique in-profile provider row. Exact duplicates and out-of-profile rows have outcomes but no membership. Disappearance from a later catalogue is reported by diffing memberships and does not imply expiry, delisting, mapping closure, or temporal supersession.

### `CatalogueTransitionPlan`

```text
catalogue_predecessor_record_id
catalogue_predecessor_version_id
item_transitions
disappeared_provider_contract_keys
semantic_diff
```

Each `CatalogueItemTransition` contains the normalized provider row, stable economic instrument ID, new provenance-bound version and mapping, eligible prior instrument-version record ID, eligible prior provider-mapping record ID, and one diff category. The categories are `added`, `unchanged`, `metadata_changed`, and `provider_mapping_changed`. Aggregate diff output also includes `disappeared`, `excluded`, and `exact_duplicates`.

The provider-key binding invariant spans all durable mapping history: one provider and provider key can identify only one economic instrument ID. Version IDs may change on every catalogue because catalogue provenance participates in version identity. A successor version or mapping therefore compares economic identity and attaches the eligible temporal record ID rather than comparing new and old version IDs. Multiple provider keys may identify one economic contract, but one catalogue cannot contain two non-identical raw rows for one provider key or conflicting version metadata for one economic instrument.

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

## Point-in-time clocks

### `MarketEventTime`

```text
exchange_timestamp
received_at
available_at
recorded_at
availability_basis
```

- `exchange_timestamp` is the provider-reported market-event time.
- `received_at` is the physical receipt time when available and remains distinct from provider time.
- `available_at` is the earliest time the observation was eligible to influence QuantKYND. Live events normally use receipt time. It never precedes a present `received_at`.
- `recorded_at` is when QuantKYND persisted the normalized immutable record and never precedes `available_at`.
- Catalogue, instrument-version, mapping, and session corrections use immutable durable records with `supersedes_record_id`. Any compatibility `superseded_at` value is derived from a visible successor and is not a durable mutable field. Market-event corrections remain append-only and identify the prior event with `supersedes_event_id`.

All domain timestamps are timezone-aware and normalized to UTC. NSE sessions are interpreted in `Asia/Kolkata`.

`market_as_of` asks which market events had occurred by exchange time. `known_as_of` additionally asks what QuantKYND could have known by a decision time. Research replay defaults to `known_as_of` whenever defensible availability exists. A historical import without original dissemination or receipt timestamps uses `availability_basis=historical_import`; it is excluded from defensible knowledge-time replay unless the caller explicitly permits that limitation.

## Market-event models

### Event identities

`RawMarketObservationIdentity` prefers a provider event or trade ID, a provider sequence within its guaranteed scope, or a source-file plus source-row identity. A provider sequence requires a non-empty `provider_sequence_scope_id`; no global scope is inferred. The scope can identify a connection, feed session, channel, partition, trading date, or a provider-guaranteed global sequence. Otherwise the observation requires a unique ingestion-event identity. A content hash records provenance but never proves two transmissions are the same event. Therefore repeated quotes with identical market fields remain distinct when their provider event identities differ.

`NormalizedMarketEventIdentity` deterministically combines raw event identity, event type, subject identity, and normalization schema version. Raw and normalized observations are append-only.

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
available_at
recorded_at
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
supersedes_event_id
```

Prices use finite non-negative `Decimal` values. Zero bid, ask, or last values are preserved as observations; negative and non-finite values are invalid representations. `None` means unavailable and remains distinct from zero. Crossed markets, zero prices, and other liquidity or market-quality conditions are classified by versioned quality assessments rather than removed during normalization. Bid, ask, last sizes, volume, and open interest are non-negative integer contracts in DATA-1.0; a provider adapter must explicitly convert and document any provider-specific lot or unit representation.

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

### `DataQualityAssessment`

```text
assessment_id
assessment_run_id
event_id
quality_policy_id
quality_policy_version
disposition
reason_codes
assessed_at
recorded_at
```

Dispositions are `accepted`, `accepted_with_flags`, `quarantined`, and `rejected`. Quality codes include stale, crossed, duplicate, out-of-order, missing sequence, invalid price, missing contract, market closed, and provider degradation. A later policy evaluation appends an assessment; it never rewrites the raw or normalized observation or an earlier assessment.

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

`DataQualityEvent` remains the operational event model for feed and catalogue degradation. It does not replace the versioned per-observation `DataQualityAssessment` used by point-in-time quote eligibility.

### Point-in-time option-chain reconstruction

For each economic contract, a query applies this order:

1. require a contract version and provider mapping effective at `market_as_of` and visible at `known_as_of` when present;
2. require `exchange_timestamp <= market_as_of`;
3. require `available_at <= known_as_of` and defensible availability unless explicitly waived;
4. select the latest visible assessment for the requested quality policy ID and version and require an eligible disposition;
5. validate and apply visible `supersedes_event_id` correction relations;
6. prefer newest exchange timestamp, then provider sequence, event order, receipt time, availability time, and stable event ID.

Correction sources cannot supersede themselves. A target must exist as a visible or historically eligible normalized quote with the same economic contract and normalized event type. Correction graphs must be acyclic and have at most one visible correction per target. Missing targets, cross-contract or cross-type edges, self-edges, cycles, and competing correction branches raise `InvalidCorrectionGraphError`; they never silently remove a quote.

Contract-version, provider-mapping, and normalized-event indexes accept repeated IDs only when the complete immutable records are equal. A shared ID with different record content raises `ConflictingSemanticIdentityError`. The final chain is sorted by expiry, strike, and option side. Successful results and structural errors are therefore invariant to input order.

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
option_delta_before_decision
hedge_delta_before_decision
net_delta_before_decision
target_delta
lower_boundary
upper_boundary
policy_id
action
continuous_target_futures_quantity
rounded_requested_futures_quantity
executed_futures_quantity
option_delta_after_fill
hedge_delta_after_fill
net_delta_after_fill
quantity_rounding_residual_delta
portfolio_value_before_fill
portfolio_value_after_fill
session_hedge_count
total_hedge_count
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

SIM-1 uses immutable option contracts, exogenous `UnderlyingPathPoint` sequences, derived executable `MarketState` sequences, unit-and-position option valuations, order intents, simulated fills, timed hedge and risk decisions, ledger entries, Greek-attribution intervals, reconciliation, summary, and run manifest values. Underlying points carry UTC timestamp, session identity, spot, realized step fraction, rates, dividend yield, and implied volatility. Executable market states add local timestamp, selected-option time to expiry, futures time to expiry, and carry-derived futures price. Distinct path and executable-state hashes identify the exact persisted sequences.

Fills retain reference price, executable price, notional, multiplier, spread, slippage, fixed, and proportional costs. Risk state retains pre-entry position reference NAV, cumulative position P&L, prior-session marked reference, session P&L, previous marked value, and separate session and total hedge counts. Risk decisions expose entry gate dispositions, pre-decision limits, forced delta overrides, and terminal risk reasons. The manifest permits null selected expiry, strike, and executable-state hash while a post-identity run is running or fails before selection; a completed manifest requires those values to have been populated by execution. Persisted strategy, market, path, and run configurations record every behavioral input and provenance hash needed to reproduce a run.

SIM-1.2.1 uses simulator behavior version `sim-1.2`, simulation-market schema version 2, simulation-run schema version 2, and manifest schema version 2. The active market instance is `nifty-synthetic-market-v2`. Path generator version remains 2. Simulator behavior, payload schemas, generated scenario identity, and exact content hashes are independent identity dimensions and all persist in their owning artifacts.

## DATA-1.1 durable foundation

Revision `20260804_01` introduces the nine semantic application tables. Revision `20260804_02` adds `catalogue_version_records`, `instrument_version_records`, `provider_mapping_records`, and `trading_session_version_records`, for thirteen application tables total. The follow-up preserves every semantic ID while moving knowledge time into append-only records.

Each temporal record contains `record_id`, its semantic ID, non-empty `scope_id`, `recorded_at`, optional immutable `supersedes_record_id`, and optional source provenance. `record_id` is deterministic over those fields. The predecessor is a non-cascading self-reference, and a partial unique index on non-null predecessor IDs enforces one direct successor. Multiple records may share one semantic ID. Exact record reinsertion is idempotent; conflicting durable content under one record ID raises `SemanticCollisionError`.

The application writes successors only after locking the predecessor and checking same-table existence, equal entity scope, strict knowledge-time increase, and successor absence. Concurrent competitors yield one commit and one `TemporalSupersessionConflictError`. Read-time graph validation remains mandatory for corruption introduced outside accepted writers. Missing targets, self-reference, cross-scope edges, non-increasing time, cycles, and branches fail closed through `InvalidTemporalGraphError`; multiple eligible leaves raise `AmbiguousPointInTimeResultError`.

Revision `20260804_02` creates one deterministic root record for every legacy semantic row. It aborts before schema changes if any legacy instrument, mapping, or session row has non-null `superseded_at`; the timestamp alone cannot identify a successor and is never discarded or converted into an invented edge. Downgrade to `20260804_01` is permitted only while every semantic row has exactly one root record and no successor history.

`market_instruments` remains the common registry for instrument subtypes. Futures and options reference an underlying, and no foreign key cascades deletion. Strike, multiplier, and tick size use `NUMERIC(38,18)` and remain exact `Decimal` values.

## DATA-1.3 normalized market-event contracts

`RawMarketFrameV1` owns a deterministic capture identity and exact frame hash. Live and recorded-original-receipt captures require `available_at == received_at`; historical imports require no receipt time. Optional historical source file/record identifiers are all-or-none. Normalization schema version 1 produces underlying, future, option, and provider-segment-status observations with exact catalogue mapping, contract version, and economic identity provenance.

Quote sizes and volume are integers from zero through `2**63 - 1`; open interest is an integer from zero through `2**53`. At most one depth level is normalized, while the selected feed union declares fixed deferred schema paths and reconciles provider, normalized, and unadopted depth counts. Frame results are complete, partial, or failed; a frame failure emits no events. `full_result_hash` covers capture and all declared output, while `adopted_semantics_hash` excludes capture identity and deferred provider fields.

Connection and subscription lifecycle raw/normalized events use explicit prior/current states, source-order scope, UTC occurrence/availability/recording times, controlled redacted failure reasons, and absent provider sequence. Every connection-session ID and source-order-scope ID is bound to one connection lifetime across the complete validated reconnect stream. Subscription identity is stable over provider, connection session, and subscription scope; per-scope transition state permits deterministic interleaving while preventing scope rebinding or restart after completion/failure.

`SubscriptionInstrumentSetV1` requires at least one provider key, stores sorted unique non-empty keys, and derives its count and stable digest internally; callers cannot supply either derived value. Subscription request modes are `ProviderRequestMode | None`, with required request/acknowledgement equality. A changed instrument set begins a new subscription scope. Normalized lifecycle construction canonicalizes enum instances and UTC timestamps even when direct inputs use enum strings or another aware offset. Exact raw lifecycle duplicates are reported and removed in first-capture order before sequence validation; changed content under one raw identity remains a conflict.

`FrameNormalizationResultV1.response_type` is optional because malformed or structurally invalid bytes can fail before a response type is available. `FrameCaptureProvenanceV1` carries the schema hash, capture clocks/basis, and optional paired source identities needed to reconstruct the full-result projection without raw bytes. Construction recomputes both declared hashes and rejects stale or forged full-result and adopted-semantics hashes. The adopted status projection includes provider-derived subject identity. The adopted failure projection excludes deferred declaration/presence metadata while retaining controlled adopted failure meaning. Full-result hashing covers raw identity, frame content identity, capture provenance, outcomes, structural metadata, response type, and reconciliation counts.

Selected Upstox feed-map identities are exact provider values and are never trimmed, rewritten, case-normalized, hashed into substitutes, or invented. Provider contract keys must be non-empty without leading/trailing whitespace or ASCII control characters and occupy at most 512 UTF-8 bytes. Market segments follow the same contract with a 128-byte bound. Invalid selected identities produce `invalid_provider_contract_key` or `invalid_market_segment` frame failures with zero decoded entries; ignored secondary-payload identities are not adopted or validated. Subject-resolution failure reasons are exactly `unknown_provider_key`, `stale_provider_mapping`, `ambiguous_provider_mapping`, and `ambiguous_contract_version`.

`FrameCaptureProvenanceV1.provider_schema_sha256` uses `sha256:` plus 64 lowercase hexadecimal characters. Live-received and recorded-original-receipt provenance requires receipt and equal receipt/availability; historical-import provenance forbids receipt. Availability never precedes receipt, recording never precedes availability, and source file/record IDs are all-or-none. A fully decoded frame with only entry failures has `status=failed` and no frame failure; the offline CLI treats it as a valid reconciled result and returns exit `0`, including when expected hashes match. A frame failure always returns exit `1`.
