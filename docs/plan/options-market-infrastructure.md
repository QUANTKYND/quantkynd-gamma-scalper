# Options-Market Infrastructure Plan

## Objective

Create point-in-time, replayable, quality-aware options-market state. The system must reconstruct which contracts, quotes, and analytics were available at any historical or live decision timestamp.

## O0 — Domain contract

Status: ACTIVE. STRAT-1 and SIM-1 provide offline contract, pricing, selection, and simulation semantics. DATA-1.0 freezes provider-neutral economic identity, validity-bounded metadata, provider mapping, point-in-time clocks, append-only corrections, event identity, quality assessments, and deterministic chain selection. DATA-1.1 adds the Postgres/Alembic foundation for catalogue versions, instrument identities and versions, provider mappings, and trading sessions. Provider ingestion and market-event persistence remain later DATA-1 work.

Define:

- Underlying instruments.
- Futures contracts.
- Option contracts.
- Trading sessions.
- Underlying quotes.
- Option quotes and trades.
- Chain snapshots.
- Provider lifecycle events.
- Data-quality events.

Economic option identity includes exchange, underlying identity, expiry exchange date, canonical Decimal strike, side, exercise style, settlement type, economically defining multiplier, and currency. Lot size, tick size, display symbol, trading status, catalogue version, and validity interval belong to a contract version. Provider and provider key belong to an effective and system-time-bounded provider mapping.

Market events separate exchange time, receipt time, availability time, and record time. Historical replay uses `known_as_of` when availability is defensible. Imports without original dissemination time are marked explicitly and cannot silently satisfy that replay mode.

Provider sequence identity requires an explicit non-empty scope. Semantic identity indexes tolerate only completely equal duplicate records and reject conflicts. Correction graphs fail closed on missing or mismatched targets, self-reference, cycles, and ambiguous branches. Normalized quotes preserve finite zero prices for policy evaluation; zero does not imply quality eligibility.

## O1 — Postgres persistence

DATA-1.1 status: ACCEPTED. Revision `20260804_02` separates semantic IDs from append-only temporal record IDs for catalogue, instrument-version, provider-mapping, and session-version state. Locked single-successor writes, graph-validated single-snapshot reads, final one-transaction units of work, and sentinel/advisory-lock destructive safety passed the zero-skip PostgreSQL migration, concurrency, and restore gates recorded in `docs/implementation/DATA-1.1-postgres-migration-foundation.md`. DATA-1.4 now adds review-pending raw-frame, normalized quote/status, failure, and provider-lifecycle persistence under revision `20260804_04`. Trade and quality-assessment persistence, retention, partition operations, and production operations remain deferred.

Add:

- SQLAlchemy repositories.
- Alembic migrations.
- Postgres connection management.
- Transaction boundaries.
- Retention and partition strategy after data volume is measured.

Initial tables:

```text
underlying_instruments
futures_contracts
option_contracts
trading_sessions
underlying_quotes
option_quotes
option_trades
chain_snapshots
data_quality_events
provider_lifecycle_events
```

Historical market events are append-only. Corrections create explicit superseding records or quality annotations.

## O2 — Catalogue ingestion

DATA-1.2 status: ACCEPTED. The initial provider-catalogue slice ingests only the approved Upstox BOD NSE `NSE.json.gz` artifact through the `upstox-nse-nifty-index-derivatives-v1` profile. It supports `NSE_INDEX|Nifty 50`, its `NSE_FO` index futures, and its `NSE_FO` call/put options. Commit mode binds all durable records to one accepted write timestamp under the provider/profile lock. Forward, same-effective-time, open historical, and bounded backfill catalogues carry explicit catalogue, version, and mapping edges to the current knowledge leaves while preserving economic provider-key binding. At read time, an eligible descendant suppresses every eligible ancestor in its visible lineage even through ineligible intermediates; separate eligible roots fail closed. PostgreSQL 17.10 migration, lifecycle, concurrency, overlapping historical resolution, and restore evidence passed with zero skips and received independent review. The slice remains local-file, offline, CLI-only, and independent of live subscriptions and execution.

DATA-1.3 status: ACCEPTED. The independently reviewed slice owns bounded deterministic Upstox V3 frame decoding, provider-neutral quote/status normalization, point-in-time catalogue subject resolution, offline connection/subscription lifecycle contracts, synthetic binary fixtures, and canonical offline CLIs. It adds no durable event state and does not alter LIVE-RV. DATA-1 remains ACTIVE pending market-event persistence and the remaining point-in-time data slices.

DATA-1.4 status: implementation complete; acceptance evidence recorded; independent review pending. Revision `20260804_04` provides append-only durable raw frame, normalization result, quote/status observation, failure, subscription-set, and provider lifecycle storage. Deterministic identities, exact-retry idempotency, semantic collision rejection, ordered memberships, typed lifecycle subtypes, deferred aggregate reconciliation, guarded downgrade behavior, and dump/restore verification are covered. The slice is not accepted yet and adds no quality policy, point-in-time chain reconstruction, Redis/live wiring, trade persistence, analytics, paper execution, or live-capital route. DATA-1 remains ACTIVE.

Requirements:

- Provider payload stored or hashed for provenance.
- Stable internal IDs independent of mutable display symbols.
- Validity intervals.
- Duplicate and collision detection.
- Expiry, lot, strike, and option-side validation.
- Diff report between catalogue versions.

Acceptance:

Given a timestamp, resolve the correct provider contract key without using a future catalogue.

## O3 — Market-data normalization

Provider adapters emit internal events with:

- Exchange timestamp.
- Received timestamp.
- Sequence where available.
- Bid, ask, sizes, last, volume, and open interest where available.
- Raw payload hash.
- Source and connection identity.

The normalizer never invents missing fields.

## O4 — Quality policy

Checks:

- Zero, negative, non-finite, or otherwise nonsensical prices with representation validity distinguished from policy eligibility.
- Bid above ask.
- Zero-width or negative-width market.
- Quote age.
- Duplicate sequence or event identity.
- Out-of-order events.
- Sequence gaps.
- Expired or unknown contracts.
- Quotes outside the exchange session.
- Missing strikes or expiries.
- Provider disconnect and reconnect.

Each observation is accepted, accepted with flags, quarantined, or rejected. Reasons are persisted.

## O5 — Point-in-time chain reconstruction

A chain query accepts:

```text
underlying
as_of
expiry filter
quote freshness threshold
quality policy version
```

It applies conflict-free contract and mapping indexes, market and knowledge cutoffs, the latest visible assessment under the requested policy version, validated fail-closed event supersession, and a stable quote tie-break. Final rows sort by expiry, strike, and option side.

It returns:

- Contracts known at `as_of`.
- Most recent eligible quote at or before `as_of`.
- Missing and rejected contracts.
- Spot or futures reference.
- Coverage and freshness summary.

## O6 — Option analytics

Build:

- Forward and discount inputs.
- Executable and midpoint marks.
- IV inversion with status.
- Greeks with input snapshot reference.
- Moneyness, log-moneyness, and DTE.

Invalid or low-quality prices produce explicit failure states, not fabricated IV.

## O7 — Surface construction

For each expiry:

- Select eligible quotes.
- Solve IV.
- Normalize moneyness.
- Fit or interpolate under a named method.
- Check calendar and butterfly consistency.
- Record exclusions and fit diagnostics.

Surface snapshots are immutable and reference source quotes.

## O8 — Implied variance

Deliver:

- ATM variance proxy.
- Horizon interpolation between expiries.
- Option-strip implied variance.
- Strike coverage diagnostics.
- Tail interpolation and extrapolation flags.
- Comparison with physical forecast on exactly aligned horizons.

## O9 — Live read-only state

Introduce Redis for latest state and fan-out:

- Current quotes.
- Current chain.
- Latest Greeks.
- Latest IV surface.
- Feed and subscription health.
- Worker heartbeat.

Postgres remains the durable truth for replay and audit.

### LIVE-RV-1 precursor

The selectable close-to-close RV workspace establishes the provider-neutral read protocols, one-process Upstox LTPC multiplexer, freshness state, browser gateway, and provisional daily-close overlay without options, Postgres, or Redis. This precursor does not satisfy O9 or the full live read-only acceptance gate because it has no durable quote truth, chain, Greeks, IV surface, or restart rebuild.

LIVE-RV-1.1 hardens this precursor with per-instrument accepted sequences, a concurrent subscription state machine, explicit backend and browser WebSocket lifecycle, segment-specific status, India-local historical ranges, and finalized-history rollover resync. These remain process-local read-only facilities and do not satisfy durable O9 recovery.

## O10 — Operator workspaces

Dashboard panels:

- Instrument catalogue status.
- Feed connection, subscription, and freshness.
- Option chain.
- Smile and term structure.
- Surface quality.
- Implied variance.
- Data-quality event stream.

## Acceptance

The infrastructure is ready for strategy replay when:

- A historical timestamp reconstructs the same chain deterministically.
- Future-listed contracts never leak backward.
- Quote provenance and quality are visible.
- IV failures are explicit.
- Surface inputs and exclusions are reconstructable.
- Feed degradation becomes visible within the freshness threshold.
