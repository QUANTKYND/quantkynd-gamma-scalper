# Testing Strategy

## Testing layers

### Pure quantitative tests

Cover formulas with hand-calculated values and independent implementations:

- Log returns and squared returns.
- Horizon variance and annualization.
- Forward targets and information cutoffs.
- Black–Scholes prices.
- Put-call parity.
- IV price round trips.
- Analytical Greeks against finite differences.
- Gamma-theta approximations.
- No-trade band scaling.
- Transaction-cost calculations.
- P&L attribution identities.

### Property tests

Use generated cases for invariants:

- Call price increases with spot and volatility.
- Put price decreases with spot under fixed inputs.
- Gamma and vega are non-negative for standard European vanilla options.
- IV round trips remain within tolerance on valid domains.
- Higher proportional cost does not narrow the baseline no-trade band under fixed state.
- Ledger debits and credits reconcile.
- Duplicate idempotency keys do not create duplicate orders.

### Contract tests

- Pydantic schemas reject undeclared fields.
- API examples validate against OpenAPI.
- Frontend runtime types or generated clients match backend contracts.
- WebSocket event envelopes remain versioned and sequence-aware.
- Broker adapters map provider states into internal states without losing terminal conditions.

### Repository and persistence tests

- Canonical catalogue fixtures reproduce economic, version, and provider-mapping identities independent of mapping or set order and Decimal text form.
- Provider sequences without an explicit scope fail; identical scoped sequences reproduce IDs and different scopes cannot collide.
- Naive timestamps, non-finite numerics, invalid effective intervals, and float values at Decimal domain boundaries fail explicitly.
- Exact duplicate semantic records are idempotent, while conflicting contract-version, provider-mapping, and normalized-event records raise the same error under every input permutation.
- Correction graphs reject missing targets, cross-contract and cross-type edges, self-edges, cycles, and ambiguous branches without changing results under input permutation.
- Zero quote prices and absent quote prices remain distinct observations; eligibility follows the visible quality assessment, while negative prices fail representation validation.
- Point-in-time contract queries exclude future and expired contracts.
- Quote writes are deduplicated by provider identity and sequence.
- Transactions preserve intent, order, fill, position, and cash invariants.
- Migration upgrade and downgrade behavior is tested where safe.
- Redis loss does not lose durable state.

### Replay tests

- Same dataset, seed, configuration, and source commit produce the same decision stream and terminal result.
- Changing future data does not change earlier decisions.
- Every terminal P&L is reconstructable from events and ledger entries.
- Historical chain selection uses only contracts known at the replay timestamp.
- Backfilled quotes, later catalogue corrections, explicit quote corrections, and later quality assessments do not alter an earlier `known_as_of` result.
- Deterministic chain tie-breaking uses exchange time, provider sequence or event order, receipt/availability time, and stable event ID before expiry-strike-side sorting.

### Failure tests

- Feed disconnect and reconnect.
- Sequence gaps.
- Stale quotes.
- Crossed or invalid markets.
- Missing contracts.
- Broker rejection.
- Timeout after request before acknowledgement.
- Duplicate acknowledgement.
- Partial fill.
- Cancel-replace race.
- Redis restart.
- Postgres unavailability.
- Worker restart.
- Max hedge count breach.
- Daily loss breach.
- Kill-switch engagement.
- End-of-day flatten or carry failure.

LIVE-RV-1.1 deterministically tests multi-instrument accepted-quote sequencing, invalid quote rejection, shared concurrent subscription readiness, failure cleanup and retry, in-flight capacity, WebSocket denial and close behavior, initial event ordering, disconnect cleanup, quote coalescing, unchanged-status silence, segment-specific status, India exchange dates, and finalized-history rollover.

STRAT-1 tests strict parsing, missing/unknown and non-finite fields, cross-field constraints, timezone/time parsing, semantic hashing, behavioral hash changes, and CLI status. SIM-1 tests separate underlying and executable-state identities; hash reproduction from persisted market states; clock rejection for weekend, shifted, non-UTC, and incompatible paths; contract-derived option and futures maturity; single-owner futures costs; spread, liquidity, theta, and expected-edge dispositions; hard post-fill delta control; entry-cost-inclusive position P&L; overnight-inclusive session P&L; the exact Whalley–Wilmott formula; complete run identity; multiplier-aware premium risk; explicit valuation units; numerical and IV boundaries; ledger identities; failed-manifest lifecycle; immutable artifacts; and identical non-policy provenance across all five CLI policies. SIM-1.2.1 additionally tests simulator-version collision prevention, explicit legacy market-schema rejection, market/run schema hash participation, independent manifest schema validation, path generator version, and CLI-to-artifact version/hash consistency.

## Frontend tests

- RTK Query loading, error, stale, and empty states.
- No direct `useEffect` import in app and feature code.
- ESLint rejects direct `useEffect` imports outside `shared/hooks/useMountEffect.ts`.
- User behavior through event handlers.
- Key-based reset behavior.
- `useMountEffect` only for approved external synchronization.
- Large tables render virtualized rows.
- Sequence-gap state triggers snapshot recovery UI.
- Risk lockouts prevent action controls.

## Test data

- Small hand-built fixtures for formulas.
- Deterministic synthetic paths for simulation.
- Wire fixtures for provider payloads.
- Sanitized and legally redistributable market samples.
- Golden decision journals for replay regression.

## Quality gates

Immediate:

```text
pytest
frontend lint
TypeScript build
git diff --check
cache and secret scan
```

Target:

```text
ruff format --check
ruff check
pyright
pytest --cov
pnpm biome check
pnpm test
pnpm build
migration check
OpenAPI contract check
```

Coverage is not a substitute for invariants. Critical money, order, risk, and reconciliation code requires branch and failure-path tests regardless of aggregate coverage.

## DATA-1.1 database verification

Pure mapping, temporal-graph, configuration, unit-of-work, and restore-safety tests run without Postgres. PostgreSQL tests require the explicit destructive opt-in, exact expected integration database name, matching sentinel, and advisory lock. If the contract is absent they skip with the missing requirements named; a final DATA-1.1 acceptance run requires zero skipped PostgreSQL tests.

Real tests cover deterministic root migration, refusal of legacy non-null `superseded_at`, upgrade to `20260804_02`, downgrade to `20260804_01`, downgrade to base, re-upgrade, metadata drift, exact reinsertion and collision, predecessor locking, competing-successor serialization, strict successor scope/time, single-snapshot current reads, unit-of-work finality, rollback, sentinel mismatch/missing behavior, sentinel survival outside `public`, and advisory-lock contention.

With the repository Postgres service healthy and the two local URLs configured:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
```

The restore verifier holds verified source and target advisory locks, seeds append-only histories through repositories, creates a custom-format public-schema-only no-owner/no-privilege dump, drops only the verified target's `public` schema, restores it, and rechecks the protected target sentinel. It compares the Alembic revision, all thirteen table counts, canonical durable-row digest, semantic and record IDs, and historical/current provider-mapping, trading-session, and catalogue A/B reads. A successful `pg_restore` alone is not acceptance.

## DATA-1.2 catalogue ingestion verification

DATA-1.2 tests cover the approved Upstox BOD NSE profile only. Fixture tests use sanitized official-format `NSE.json.gz` samples and hostile variants. Acceptance does not require a live Upstox endpoint or access token.

Required parser and profile tests:

- one top-level JSON array;
- gzip CRC validation and multi-member rejection;
- UTF-8 without BOM;
- duplicate object-key rejection;
- non-standard numeric rejection;
- epoch-millisecond expiry converted through `Asia/Kolkata` to an exchange date;
- lexical JSON numeric parsing into `Decimal`;
- raw `tick_size=5` persisted as `Decimal("0.05")`;
- Nifty 50 underlying resolution by `underlying_key`;
- unrelated NSE rows excluded rather than rejected;
- in-profile malformed or conflicting rows rejecting the catalogue.

Required identity tests:

- row permutation changes occurrence IDs but not semantic row IDs;
- row permutation preserves normalized catalogue hash, catalogue ID, version IDs, and mapping IDs;
- exact duplicates do not alter catalogue identity;
- different file names with exact bytes preserve artifact ID;
- different gzip bytes with equal decompressed content produce different artifact IDs and equal catalogue IDs.

Required persistence tests:

- accepted commit stores the compressed artifact in the content-addressed artifact root;
- dry-run and validate-only retain no artifact;
- rejected commit persists no accepted audit rows;
- all outcomes and memberships commit atomically;
- two concurrent first catalogues cannot both become roots;
- same idempotency key with different command digest conflicts;
- migration `20260804_03` upgrades, downgrades, passes Alembic drift checks, and is included in restore digests.

Review-correction acceptance additionally proves the invocation/knowledge-time boundary with an injected clock: parsing begins at `started_at`, one accepted timestamp binds every durable catalogue/version/mapping record, semantic IDs survive rebinding, temporal IDs represent the accepted records, the pre-acceptance knowledge interval cannot see the catalogue, and accepted run timestamps are ordered. Validate-only and dry-run request no durable timestamp.

Forward, same-effective-time, open historical, and bounded backfill tests resolve predecessors by current knowledge leaf. Pure resolver tests freeze transitive market supersession: eligible A plus ineligible B plus eligible H resolves H; eligible A/B plus ineligible H resolves B; only eligible A resolves A; separate eligible roots remain ambiguous; and a knowledge cutoff before H resolves A while a cutoff after H resolves H.

The acceptance-critical PostgreSQL lifecycle uses A open from T0, B open from T1, and later-known bounded H inside A's interval but before T1, with knowledge edges A→B→H. Catalogue, instrument-version, and mapping reads must all return A inside H's interval before H is known, H there after H is known, B at or after T1, and A on both sides of H before T1. It proves one root and two successors in every scope without ambiguity. Dry-run must produce the same transition checks and deterministic semantic diff as commit without writes or artifact retention. Persistence failure tests distinguish accepted idempotency races from semantic collisions, unrelated constraints, and temporal successor conflicts. The restore fixture contains the same overlapping lineage, all three retained artifact references, both successor edges, and equivalent source/restored catalogue, version, and mapping reads. Acceptance-critical persistence and concurrency tests run with zero skips on the declared PostgreSQL 17 service.

## DATA-1.3 normalization verification

The no-infrastructure suite runs normalization models, lifecycle transitions, bounded decoder cases, 17 synthetic binary fixtures, capture/subject manifests, both offline CLIs, existing LIVE-RV tests, schema ownership, and deterministic regeneration with database, restore URL, token, and Redis variables unset. It proves byte-identical replay under `PYTHONHASHSEED=1` and `999`, reversed protobuf map wire order, exact sidecar hashes/event IDs, adopted-versus-deferred hash boundaries, and all CLI exit classes.

The acceptance-critical resolver test runs on the declared PostgreSQL 17 service with zero skips. It covers underlying/future/option provenance, exact caller cutoffs, sorted mixed batches, unknown/stale/ambiguous mappings, effective/expiry/knowledge boundaries, version staleness, superseded knowledge replay, one read-only transaction, and no writes. Fixture regeneration uses `tools/generate_market_event_fixtures.py --write`; verification uses `tools/verify_market_event_fixtures.py` and fails on any generated binary, sidecar, subject-manifest, or inventory drift.

Final-review tests additionally cover every supported request-mode/feed-union/subject-kind tuple and hostile direct pairs; reconnect ordinal reset from `100` to `0`; lifecycle enum/UTC canonicalization; unforgeable subscription sets and mode acknowledgements; raw lifecycle identity collisions; status subject identity and deferred-failure adopted hashes; duplicate-identity structural metadata; canonical malformed/unsupported frame CLI results; a real two-envelope exit-4 path; exact schema/provider and strict-integer manifest validation; and a PostgreSQL mixed batch with one valid key plus one ambiguous contract-version graph.

Final lifecycle/CLI correction tests prove capture-ordered interleaving of independent subscription and mode-change scopes; per-scope provider/session/source-scope/instrument-set binding; terminal scope non-restart; non-adjacent session and source-scope uniqueness across three reconnect lifetimes; non-empty subscription instrument sets; strict capture, subject, decimal-string, timestamp, enum, array, object, and optional-field manifest boundaries; canonical exit `2` without tracebacks or raw bytes; structural frame exit `1` even when expected hashes match; stale/forged result-hash rejection after adopted-event or capture-provenance changes; and successful first-capture-order lifecycle duplicate removal for connection and subscription fixtures.
