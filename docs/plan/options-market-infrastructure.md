# Options-Market Infrastructure Plan

## Objective

Create point-in-time, replayable, quality-aware options-market state. The system must reconstruct which contracts, quotes, and analytics were available at any historical or live decision timestamp.

## O0 — Domain contract

Status: READY. STRAT-1 and SIM-1 provide offline contract, pricing, selection, and simulation semantics; point-in-time provider identity and persistence remain DATA-1 work.

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

Contract identity includes exchange, underlying, expiry, strike, side, multiplier, lot size, tick size, provider key, and validity interval.

## O1 — Postgres persistence

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

- Non-positive or nonsensical prices.
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
