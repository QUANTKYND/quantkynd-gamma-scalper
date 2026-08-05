# Observability

The system must make degraded state obvious. Silent fallback is a defect.

## Correlation fields

Every operational record carries the identifiers that exist for its lifecycle:

```text
correlation_id
strategy_id
strategy_run_id
candidate_id
intent_id
risk_decision_id
order_id
broker_order_id
fill_id
position_id
reconciliation_id
instrument_id
contract_id
```

## Structured logs

Logs are JSON in paper environments. Required fields:

```text
timestamp
level
service
process
version
environment
event
correlation_id
source_commit
```

Logs never include credentials or complete sensitive broker payloads.

## Metrics

### Market data

- Connection state.
- Subscription state.
- Events received and accepted.
- Events rejected by quality policy.
- Sequence gaps.
- Exchange-to-receive lag.
- Receive-to-process lag.
- Latest eligible quote age.
- Chain coverage by expiry and strike.

LIVE-RV-1 exposes authentication, transport, subscription, freshness, market status, active keys, connection time, last message time, last safe error code, and reconnect attempt through `/api/v1/market-data/status`. Provider logs may carry instrument key, timestamps, processing lag, active counts, and safe error codes, but never access tokens, authorized feed URLs, OAuth codes, secrets, or raw token files.

LIVE-RV-1.1 exposes all provider segment statuses and derives both market and subscription status for the selected instrument separately. Accepted quote sequences are per instrument. Generic provider errors are recorded while transport remains `reconnecting`; `reconnect_exhausted` is terminal. Browser caches expose `connecting`, `open`, `failed`, and `closed`, plus the safe close code and UTC close time, and preserve `failed` when the error is followed by close. A rollover emits `resync_required`; a sequence gap or resync invalidates the selected instrument REST cache.

### Analytics

- IV solve success and failure counts.
- Surface build duration.
- Surface arbitrage violations.
- Forecast age and horizon coverage.
- Opportunity candidates accepted and rejected by reason.

### Strategy and risk

- Open positions.
- Net delta, gamma, theta, and vega.
- Premium at risk.
- Daily P&L and drawdown.
- Theta budget consumed.
- Hedge count.
- Risk approvals and rejections.
- Kill-switch state.

### Execution

- Intents created.
- Orders submitted, acknowledged, rejected, cancelled, and filled.
- Partial fills.
- Idempotency conflicts.
- Order-state age.
- Reconciliation differences.
- Fill slippage and fees.

### System

- API latency and errors.
- Worker heartbeat age.
- Queue or stream lag.
- Postgres pool usage.
- Redis latency and errors.
- Process memory and CPU.

## Decision journal

Every strategy decision records:

- Point-in-time market snapshot references.
- Data-quality state.
- Forecast and implied-variance inputs.
- Strategy and policy versions.
- Edge decomposition.
- Current portfolio and Greeks.
- Hedge boundaries.
- Risk evaluation.
- Resulting intent or hold reason.

The journal is immutable and queryable.

SIM-1 persists this journal as deterministic underlying-path, executable market-state, unit/position valuation, timed hedge-decision, session-aware risk-decision, intent, fill, ledger, attribution, and summary artifacts. Pre-hedge trigger delta and post-hedge residual delta are separate metrics; forced delta overrides and unhedgeable exits have stable reason codes. CLI success JSON exposes simulator, strategy, market, path-config, path, executable-state, run-config, policy, option-cost, futures-cost, and runtime-risk hashes plus seed, exit, costs, delta timings, reconciliation, and artifact location. Failed post-identity runs expose a failed manifest and reason without appearing complete. No metrics backend is introduced for offline runs.

## Alerts

Critical:

- Kill switch engaged.
- Position or cash reconciliation mismatch.
- Stale or missing feed while positions are open.
- Unknown broker order state.
- Daily loss breach.
- Max absolute delta breach.
- Paper worker heartbeat missing.

Warning:

- Surface degradation.
- Quote coverage below threshold.
- Elevated spread or slippage.
- Forecast expired.
- Redis unavailable with fallback active.
- Research worker resource saturation.

## Dashboard workspaces

- System health.
- Market-data freshness and quality.
- RV forecasts.
- Option chain and IV surface.
- Gamma opportunities.
- Position and Greek book.
- Hedge controller and timeline.
- Orders, fills, and reconciliation.
- P&L attribution.
- Risk limits and kill switch.
- Research runs and artifacts.

## DATA-1.1 database signals

The foundation provides a credential-masking `SELECT 1` health probe and sets bounded connection timeout, statement timeout, pool sizing, pool pre-ping, recycle interval, repeatable-read transaction isolation, and a low-cardinality application name. Migration and restore commands return explicit success or failure. Restore success includes revision equality, thirteen deterministic row counts, canonical digest equality, semantic/record identity equality, historical/current representative-query equality, dump removal, and target-safety recheck without a DSN.

Destructive refusals distinguish missing opt-in, exact-name mismatch, non-local-host denial, sentinel failure, advisory-lock contention, and source/target identity collision without exposing credentials. Temporal write conflicts and invalid or ambiguous read graphs are explicit domain/repository failures.

Persistent database metrics, structured SQL tracing, slow-query dashboards, automated alerts, retry loops, and production backup scheduling remain later operational work. DATA-1.1 does not add logging or metrics dependencies and does not enable SQL echo by default.

## DATA-1.2 catalogue ingestion signals

Catalogue ingestion emits structured CLI/service events for `catalogue_ingestion_started`, `catalogue_artifact_validated`, `catalogue_rows_parsed`, `catalogue_rows_normalized`, `catalogue_conflicts_checked`, `catalogue_ingestion_committed`, `catalogue_ingestion_rejected`, `catalogue_ingestion_failed`, and `catalogue_ingestion_rollback`.

Events include provider, profile version, source artifact ID, catalogue version ID when available, ingestion run ID when committed, normalized catalogue hash, physical row count, accepted unique count, exact duplicate count, excluded count, field-name fingerprint, elapsed parse and persistence time, database revision, and redacted error code. Events do not include raw provider payloads, provider credentials, database URLs, or local absolute artifact paths.

Dry-run and successful new commits expose deterministic semantic diff counts for `added`, `unchanged`, `metadata_changed`, `provider_mapping_changed`, `disappeared`, `excluded`, and `exact_duplicates`, plus sorted disappeared provider keys. Output explicitly states that disappearance is informational. An idempotent replay identifies the persisted accepted run; unrelated database and temporal failures retain their own error category instead of being reported as idempotency conflicts.

## DATA-1.3 offline normalization evidence

The fixture CLI emits canonical JSON containing raw identity/hash, response type, accepted events, frame and entry failures, union-scoped unadopted declarations, present deferred-message paths, secondary payload paths, reconciliation counts, full-result hash, and adopted-semantics hash. It never emits raw bytes. Exit codes distinguish expected-result mismatch, manifest/configuration error, schema/hash drift, and raw-identity conflict.

Lifecycle fixture output contains only normalized immutable observations and a deterministic sequence hash. Failure reasons are controlled redacted codes. DATA-1.3 deliberately adds no production logging, metrics, alerting, live lifecycle emission, or cardinality-bearing provider-key metrics.
