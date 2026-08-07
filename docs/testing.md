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

Provider-identity boundary tests generate hostile Protobuf frames programmatically and cover empty, whitespace-only, edge-whitespace, newline, NUL, ASCII-control, mixed-valid/malformed, and UTF-8 byte-limit cases. Quote-key validation proves 512 bytes accepted, 513 rejected, retained live/initial response types, whole-frame failure, and zero resolver calls. Segment validation proves 128 bytes accepted, 129 rejected, retained market-info response type, and whole-frame failure. Selected-primary-only tests show malformed ignored secondary identities remain unadopted. Direct construction tests enforce failure-identifier bounds, the four resolver reasons, canonical capture schema hashes, every capture-basis clock rule, source identity pairing, and stale result-hash rejection. CLI tests prove canonical exit `1` under hash seeds 1 and 999 for structural identity failures and exit `0` for a fully reconciled entry-only failed result.

The durability-boundary amendment adds acceptance-critical zero-skip tests for strict integer-versus-boolean handling and the inclusive `2**63 - 1` source-order boundary across raw frames, quote/status observations, lifecycle events, capture manifests, and lifecycle fixtures. Multibyte cases prove 512 UTF-8 bytes are accepted and 514 are rejected without mutation for opaque IDs and provider keys. Lifecycle tests cover the 128-byte reason-code boundary, the 5,000-key global cap, exact `ltpc`/`option_greeks`/`full_d5`/`full_d30` mode limits, absent-mode unsubscribe behavior, the 10,000-event batch cap, and pre-parse rejection above the 16 MiB fixture cap. Deterministic fixture verification must prove all existing binary bytes, frame hashes, raw/event identities, and approved result hashes remain unchanged.

<!-- DATA-1.4-EVIDENCE:TESTING:START -->
## DATA-1.4 persistence verification

DATA-1.4 metadata tests prove that all frame, normalization, quote/status, failure, subscription-set, lifecycle-root, typed-subtype, and ordered-membership tables are explicit and match the migration. No placeholder table machinery remains.

Pure persistence tests cover deterministic record planning, named collision errors, exact-retry idempotency, lock-striping stability, bounded SQL parameter planning, unit-of-work exposure, input permutation, and append-only repository contracts.

Guarded PostgreSQL tests recreate the approved disposable database and exercise revision `20260804_04` with zero skips in the focused acceptance suite. They cover:

- migration creation and metadata drift;
- exact raw-frame and normalized-event persistence;
- quote/status subtype boundaries and temporal provenance;
- result-event and result-failure ordering;
- immutable subscription-set count and ordered-key reconciliation;
- lifecycle root counts, state transitions, request-mode limits, and instrument-set binding;
- exact duplicate ownership and first-capture input order;
- exactly one correct lifecycle subtype per normalized root;
- normalized batch count, contiguous ordinal, kind, raw-membership, and first-capture normalized-order reconciliation;
- append-only update, delete, and truncate rejection;
- refusal to downgrade non-empty durable history before any destructive DDL;
- exact `public`-schema ownership of all nine lifecycle validation functions, their removal on downgrade to `20260804_03`, and recreation on re-upgrade;
- Alembic drift after the downgrade/re-upgrade lifecycle;
- database dump/restore equivalence.

Acceptance evidence at implementation SHA `725e708d1ea2a89514d90bbf3008bd9e234ccd5f`:

```text
PostgreSQL: PostgreSQL 17.10 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
max_locks_per_transaction: 64
focused persistence: 70 passed in 18.99s; zero skipped
complete backend: 796 passed in 69.37s (0:01:09)
restore verifier: {"artifact_bytes_external_to_database": true, "artifact_reference": {"artifacts": [{"artifact_object_key": "sha256/b7/b73ef6c11ef3920df6557ff5a961fe1ae140ff231fec1b3758287f17e4b0d72d.json.gz", "compressed_sha256": "sha256:b73ef6c11ef3920df6557ff5a961fe1ae140ff231fec1b3758287f17e4b0d72d", "source_artifact_id": "sha256:12006ffaecb700c2fcc82693226c6064c337c64ae39a30be8818bbb36cf51b4e"}, {"artifact_object_key": "sha256/b2/b28171f89ac7b00fb7cb9efd79fbea9caeefbeb4fa6922cd93f2cdae10ad6023.json.gz", "compressed_sha256": "sha256:b28171f89ac7b00fb7cb9efd79fbea9caeefbeb4fa6922cd93f2cdae10ad6023", "source_artifact_id": "sha256:1ec4d76a451f951296d10e89ab6be6e5122b3720570efa41e7578ebdff7c4ffd"}, {"artifact_object_key": "sha256/4d/4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7.json.gz", "compressed_sha256": "sha256:4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7", "source_artifact_id": "sha256:4f46ddc27f32b66ddd3f926edfcaf4270eba88d90bbb08f58600c81402d8b9ef"}]}, "artifact_reference_hash_valid": true, "canonical_digest": "sha256:ab85ea7c707825994fb82d0ff0932f02411cdfe318f7e341e2377f6cda139539", "catalogue_representative_query_match": true, "catalogue_representative_reads": {"catalogue_before_second_known": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:658275c2a976e0403ea1b9087d2fdba069973be83b750435ab697ec71f2cd418"}, "catalogue_current": {"recorded_at": "2026-08-07T04:44:20.904200+00:00", "semantic_id": "sha256:4c799f3f16b2784871e03187e7bb5bd95b42991b1e05eb8e19b0adcae7606252"}, "catalogue_historical_after_known": {"recorded_at": "2026-08-07T04:44:21.190809+00:00", "semantic_id": "sha256:4f08958a1b246a26d27ccaa299ba0c1c17bec9221f4e30a9048fee42915799c4"}, "catalogue_historical_before_known": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:658275c2a976e0403ea1b9087d2fdba069973be83b750435ab697ec71f2cd418"}, "catalogue_known_before_effective": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:658275c2a976e0403ea1b9087d2fdba069973be83b750435ab697ec71f2cd418"}, "catalogue_successor_edges": [{"record_id": "sha256:3dcd8d891b66de591e66fa4e7d15806013ae5b8dcd1052483e52e7e261bb9c90", "supersedes_record_id": "sha256:188de05c2c972b2b9eff4589e6c261765ccffcb32ab76b3caf4de79174b9ecc9"}, {"record_id": "sha256:d78318f035621acfd3851776f68ac69f5cbb5c3780dd2e3106219154e5721ef2", "supersedes_record_id": "sha256:3dcd8d891b66de591e66fa4e7d15806013ae5b8dcd1052483e52e7e261bb9c90"}], "excluded_by_profile_counts": [1, 1, 1], "ingestion_runs": [{"catalogue_record_id": "sha256:188de05c2c972b2b9eff4589e6c261765ccffcb32ab76b3caf4de79174b9ecc9", "catalogue_version_id": "sha256:658275c2a976e0403ea1b9087d2fdba069973be83b750435ab697ec71f2cd418", "command_digest": "sha256:231e11b8bb955bfed6d5b2aa55811caff0312a7f233b6c032548be8452a572e3", "ingestion_run_id": "sha256:4a33896c664574adf37cd9c33be1541f916fa580f29d6d4b3834b28f7105a955", "recorded_at": "2026-08-07T04:44:20.697602+00:00", "source_artifact_id": "sha256:4f46ddc27f32b66ddd3f926edfcaf4270eba88d90bbb08f58600c81402d8b9ef"}, {"catalogue_record_id": "sha256:3dcd8d891b66de591e66fa4e7d15806013ae5b8dcd1052483e52e7e261bb9c90", "catalogue_version_id": "sha256:4c799f3f16b2784871e03187e7bb5bd95b42991b1e05eb8e19b0adcae7606252", "command_digest": "sha256:4a0432f4b6db2d18a153924e4a7fa74cbe4a5b786888c0386e417e4099792fdc", "ingestion_run_id": "sha256:e7c6683750f076614c1bee282743d2847dc1c3989c0ad4354303a5790e69bca9", "recorded_at": "2026-08-07T04:44:20.904200+00:00", "source_artifact_id": "sha256:1ec4d76a451f951296d10e89ab6be6e5122b3720570efa41e7578ebdff7c4ffd"}, {"catalogue_record_id": "sha256:d78318f035621acfd3851776f68ac69f5cbb5c3780dd2e3106219154e5721ef2", "catalogue_version_id": "sha256:4f08958a1b246a26d27ccaa299ba0c1c17bec9221f4e30a9048fee42915799c4", "command_digest": "sha256:cbd1e71074f7e83d24a7c2ba7c04682cd426701577130fc098e74fb8e7ada159", "ingestion_run_id": "sha256:3236a955eff85e154877e0eacafbdf190e8eca129951246ffcf4a66c18cfdbb9", "recorded_at": "2026-08-07T04:44:21.190809+00:00", "source_artifact_id": "sha256:12006ffaecb700c2fcc82693226c6064c337c64ae39a30be8818bbb36cf51b4e"}], "instrument_version_current": {"recorded_at": "2026-08-07T04:44:20.904200+00:00", "semantic_id": "sha256:b24ecf720a0ae3ad604966e88ef2b1287f2b355ffb82c69e1b7151fbbf10e3dd"}, "instrument_version_historical_after_known": {"recorded_at": "2026-08-07T04:44:21.190809+00:00", "semantic_id": "sha256:2a074dbded152abf0d74079d2b952b0ee8710fe056e1e8be73325c6765f9499d"}, "instrument_version_historical_before_known": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:63bdb4de19b1bcdb2034a6574837d7b5b135f34bffa53029b1b78142750492e3"}, "memberships": [[{"instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_id": "sha256:5bc5c3a144a1e718f87a47c6e5a468eae92e8c85bc5d449e2cc20c77ae10c98a", "membership_id": "sha256:ab3c3f99ef5f51716bbc91829a096f5b6bff66a65050b4d5779b89e9248438ac", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "version_id": "sha256:63bdb4de19b1bcdb2034a6574837d7b5b135f34bffa53029b1b78142750492e3"}, {"instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_id": "sha256:48b61a46b3fdebd73551b2ecef83ddd11b79a8d8bb31891b633bb85b35341405", "membership_id": "sha256:6b5ceead2b1af1052863b97b00a305a3011bcbf5041d6d8d5610f86957f9b09d", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "version_id": "sha256:c0627851a7ac46894e8daf2d371df1fcc3cacf8d217abd7623e5f0d031851083"}, {"instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_id": "sha256:81da7d65ff3b6156dcde6c86a95525e3dd42bbcf47c1df10ebbd95cf5ec74c62", "membership_id": "sha256:e37f11a4d68852ae5b9605fe54d1dababf7e2a8677a5208290b64a77f06a7fde", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "version_id": "sha256:f1f1736ca9a4aebea4bc767a9f8862cc87cda9551db1287e107691291585858d"}, {"instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_id": "sha256:8c1b9d9df9aafa0255fa07802fd7db47331b408bc3897480540559c0ce3355fe", "membership_id": "sha256:42992429013ab422cc60a20802e5a11157c515765942db758a69da62b765f709", "provider_contract_key": "NSE_INDEX|Nifty 50", "version_id": "sha256:62cce94b1c26fea5aa712054bc9d46f10866e3018c0b03d401ddf6dda123a8dd"}], [{"instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_id": "sha256:af806598ebae4bb8ea1e0e369d5a88915a7cd182635f530da22041aca60ebc29", "membership_id": "sha256:dd4911bbd3b3f2f523e82e49cfd2cac9a920c5a6d71178e5a86d7160a6d8b6e1", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "version_id": "sha256:b24ecf720a0ae3ad604966e88ef2b1287f2b355ffb82c69e1b7151fbbf10e3dd"}, {"instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_id": "sha256:33c09ffa327da4241a2e500b1a027237dcc669a3d617b5968fa58e71d39d8939", "membership_id": "sha256:8e44d1e83beecdf828b28e38dad0ecfac70df7abf92fdbd69a70c2b6afdc2764", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "version_id": "sha256:9153234525ffd1d5bf89c75573433473b95c5a3a025528b778838961df3827cb"}, {"instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_id": "sha256:fc86c0242ff430527475c5024aa800689a705557078ada44fc640b443150a4dc", "membership_id": "sha256:f4a4de31d9ce3322d4b0afaea81a9dbc183c85da6ce6124858749507c014ec22", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "version_id": "sha256:f20d5345cff6753d7951dfc5b14ea6ba3789f7bc6a0fbb7481d7b8a1ffab2b70"}, {"instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_id": "sha256:9209c11084259a618a0c875709a46cefc33c10fcd4442d180f14d14a0b8d4286", "membership_id": "sha256:03a19a1459e52b9555ed493eec957ffbf05ee03b390a7c15baf9f9b8c7a64af4", "provider_contract_key": "NSE_INDEX|Nifty 50", "version_id": "sha256:49de289777581b4c2c99a9a4cd9470044c722550545f69b6576bed1b32902890"}], [{"instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_id": "sha256:42b94f265ddc26f4ed7cf7dfc0bfd16329558c2c37843ccec70118b9838e948b", "membership_id": "sha256:39691413e4aad3dfc7bb729cdf66ccb2fd028d053e9fe00e2cef19c2e353c6d8", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "version_id": "sha256:2a074dbded152abf0d74079d2b952b0ee8710fe056e1e8be73325c6765f9499d"}, {"instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_id": "sha256:b3b7dc188df299b19d2236bffa295152ec62686943cb279ae7e10008dee1415f", "membership_id": "sha256:aca3fffa2b764179ee3ba4ce9f338ac285342104abf4977bb39f74688512671d", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "version_id": "sha256:9951f1e82af07f46e97601d49f639e39b28a8d6b1c4515e2f30652210cf1c106"}, {"instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_id": "sha256:efb5d8150aaf55427b586a6528e5a51f6a83bbf6eb898244f9844f40971b6911", "membership_id": "sha256:8fb29fb1e413f8e28a416ca18d0a4a8f74f7ad7f25a5245facf6ecdbc636603b", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "version_id": "sha256:822f0541435f06f923a5f9a7baa43b108189d8c70043191337a2a1e8c262d570"}, {"instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_id": "sha256:348e5a0078c7b1a09efc47b2caeeaa0d120569024f6abbd4556cc1decd1af15e", "membership_id": "sha256:0947f2e068f1e967b195d618db3dda7d32603c54068ed2b9b8de549f9c7f509d", "provider_contract_key": "NSE_INDEX|Nifty 50", "version_id": "sha256:f33d8db8a967c6107c495825b310f1231370102f13bc73cf8bda43677982f3e5"}]], "provider_binding_continuity": true, "provider_mapping_before_second_known": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:5bc5c3a144a1e718f87a47c6e5a468eae92e8c85bc5d449e2cc20c77ae10c98a"}, "provider_mapping_current": {"recorded_at": "2026-08-07T04:44:20.904200+00:00", "semantic_id": "sha256:af806598ebae4bb8ea1e0e369d5a88915a7cd182635f530da22041aca60ebc29"}, "provider_mapping_historical_after_known": {"recorded_at": "2026-08-07T04:44:21.190809+00:00", "semantic_id": "sha256:42b94f265ddc26f4ed7cf7dfc0bfd16329558c2c37843ccec70118b9838e948b"}, "provider_mapping_historical_before_known": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:5bc5c3a144a1e718f87a47c6e5a468eae92e8c85bc5d449e2cc20c77ae10c98a"}, "provider_mapping_known_before_effective": {"recorded_at": "2026-08-07T04:44:20.697602+00:00", "semantic_id": "sha256:5bc5c3a144a1e718f87a47c6e5a468eae92e8c85bc5d449e2cc20c77ae10c98a"}, "row_outcomes": [[{"disposition": "accepted", "instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_id": "sha256:8c1b9d9df9aafa0255fa07802fd7db47331b408bc3897480540559c0ce3355fe", "provider_contract_key": "NSE_INDEX|Nifty 50", "row_outcome_id": "sha256:37bbb7c58a8307b08adc4b240b941e144c877ad882da018f54f09d16ab61bcf4", "version_id": "sha256:62cce94b1c26fea5aa712054bc9d46f10866e3018c0b03d401ddf6dda123a8dd"}, {"disposition": "accepted", "instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_id": "sha256:81da7d65ff3b6156dcde6c86a95525e3dd42bbcf47c1df10ebbd95cf5ec74c62", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "row_outcome_id": "sha256:c4c134df1d058c555b3b61c99f74e02787ff61f0ea32fbe4a80f2661c72a4735", "version_id": "sha256:f1f1736ca9a4aebea4bc767a9f8862cc87cda9551db1287e107691291585858d"}, {"disposition": "accepted", "instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_id": "sha256:5bc5c3a144a1e718f87a47c6e5a468eae92e8c85bc5d449e2cc20c77ae10c98a", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "row_outcome_id": "sha256:f4b4b05b5cada716d98b0a818ee0ff122db4d92c481c5f9bc5d284ab480835b3", "version_id": "sha256:63bdb4de19b1bcdb2034a6574837d7b5b135f34bffa53029b1b78142750492e3"}, {"disposition": "accepted", "instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_id": "sha256:48b61a46b3fdebd73551b2ecef83ddd11b79a8d8bb31891b633bb85b35341405", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "row_outcome_id": "sha256:d3ca461d2c2835d5f5d37ebff59a0123ed1b8f5bfb1ed765911e05e2a4df989d", "version_id": "sha256:c0627851a7ac46894e8daf2d371df1fcc3cacf8d217abd7623e5f0d031851083"}, {"disposition": "excluded_by_profile", "instrument_id": null, "mapping_id": null, "provider_contract_key": "NSE_EQ|SANITIZED_EQ", "row_outcome_id": "sha256:bf6d259c3d9496d8d27e28137d854af59cc2b17a27bb237f8db63ea0edde6c9b", "version_id": null}], [{"disposition": "accepted", "instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_id": "sha256:9209c11084259a618a0c875709a46cefc33c10fcd4442d180f14d14a0b8d4286", "provider_contract_key": "NSE_INDEX|Nifty 50", "row_outcome_id": "sha256:24b2b477308208d8ee3d9dad9d01fbb34ddc21c6b48dc5149c9dbb3ac9f01fd3", "version_id": "sha256:49de289777581b4c2c99a9a4cd9470044c722550545f69b6576bed1b32902890"}, {"disposition": "accepted", "instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_id": "sha256:fc86c0242ff430527475c5024aa800689a705557078ada44fc640b443150a4dc", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "row_outcome_id": "sha256:040d2ebaff64e53af056aac5f31e7aba7f5915bc1c5e02e100bb26ef2953888f", "version_id": "sha256:f20d5345cff6753d7951dfc5b14ea6ba3789f7bc6a0fbb7481d7b8a1ffab2b70"}, {"disposition": "accepted", "instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_id": "sha256:af806598ebae4bb8ea1e0e369d5a88915a7cd182635f530da22041aca60ebc29", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "row_outcome_id": "sha256:b924c2b1af622c1ec3eb1592eb9bed56316d2f838054b3e735f6f241ed4c461a", "version_id": "sha256:b24ecf720a0ae3ad604966e88ef2b1287f2b355ffb82c69e1b7151fbbf10e3dd"}, {"disposition": "accepted", "instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_id": "sha256:33c09ffa327da4241a2e500b1a027237dcc669a3d617b5968fa58e71d39d8939", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "row_outcome_id": "sha256:2d425b20a9d310435dc4bcd231ce612bcd502a93ebe3f81a1ed1ff122cabbbeb", "version_id": "sha256:9153234525ffd1d5bf89c75573433473b95c5a3a025528b778838961df3827cb"}, {"disposition": "excluded_by_profile", "instrument_id": null, "mapping_id": null, "provider_contract_key": "NSE_EQ|SANITIZED_EQ", "row_outcome_id": "sha256:aa7c5bb1fa58c3e482fb274203b2b59c87b971f4d8d75853d15d4528a495658d", "version_id": null}], [{"disposition": "accepted", "instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_id": "sha256:348e5a0078c7b1a09efc47b2caeeaa0d120569024f6abbd4556cc1decd1af15e", "provider_contract_key": "NSE_INDEX|Nifty 50", "row_outcome_id": "sha256:f94d6a320e79669a40cb985403684d53087e9496c27e2b1c9827c8190c072dfb", "version_id": "sha256:f33d8db8a967c6107c495825b310f1231370102f13bc73cf8bda43677982f3e5"}, {"disposition": "accepted", "instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_id": "sha256:efb5d8150aaf55427b586a6528e5a51f6a83bbf6eb898244f9844f40971b6911", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "row_outcome_id": "sha256:385add0cdbdfa7d3284969ad9ab2e433e139779e9de28fd559bb9072a2166f29", "version_id": "sha256:822f0541435f06f923a5f9a7baa43b108189d8c70043191337a2a1e8c262d570"}, {"disposition": "accepted", "instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_id": "sha256:42b94f265ddc26f4ed7cf7dfc0bfd16329558c2c37843ccec70118b9838e948b", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "row_outcome_id": "sha256:77013a0d15bdf5ebb04e6d1a04811128c1d65eec2091bf954a641c78232ad0b1", "version_id": "sha256:2a074dbded152abf0d74079d2b952b0ee8710fe056e1e8be73325c6765f9499d"}, {"disposition": "accepted", "instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_id": "sha256:b3b7dc188df299b19d2236bffa295152ec62686943cb279ae7e10008dee1415f", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "row_outcome_id": "sha256:34239bdfa7728061bf9ba980588a351d467f11364fe659f43fb9c51f382eabb3", "version_id": "sha256:9951f1e82af07f46e97601d49f639e39b28a8d6b1c4515e2f30652210cf1c106"}, {"disposition": "excluded_by_profile", "instrument_id": null, "mapping_id": null, "provider_contract_key": "NSE_EQ|SANITIZED_EQ", "row_outcome_id": "sha256:c353a116fb2a801e9f1c6253f2c5ea9ccd9b05749ff938815b5b3e3dddf33585", "version_id": null}]], "source_artifacts": [{"artifact_object_key": "sha256/4d/4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7.json.gz", "compressed_sha256": "sha256:4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7", "decompressed_sha256": "sha256:73021afd2e45483d099b1ce7afb85595f48b27d3e749b41fe264ff2b8eff27d7", "source_artifact_id": "sha256:4f46ddc27f32b66ddd3f926edfcaf4270eba88d90bbb08f58600c81402d8b9ef"}, {"artifact_object_key": "sha256/b2/b28171f89ac7b00fb7cb9efd79fbea9caeefbeb4fa6922cd93f2cdae10ad6023.json.gz", "compressed_sha256": "sha256:b28171f89ac7b00fb7cb9efd79fbea9caeefbeb4fa6922cd93f2cdae10ad6023", "decompressed_sha256": "sha256:af9f9422dd4fb517545d28f7be22f49a0ba83519c7836094b9b8826000418ed2", "source_artifact_id": "sha256:1ec4d76a451f951296d10e89ab6be6e5122b3720570efa41e7578ebdff7c4ffd"}, {"artifact_object_key": "sha256/b7/b73ef6c11ef3920df6557ff5a961fe1ae140ff231fec1b3758287f17e4b0d72d.json.gz", "compressed_sha256": "sha256:b73ef6c11ef3920df6557ff5a961fe1ae140ff231fec1b3758287f17e4b0d72d", "decompressed_sha256": "sha256:79d1b3eac1f5cda7f096b942beb5622e17faae92a359b4e8936a943d54dca7f5", "source_artifact_id": "sha256:12006ffaecb700c2fcc82693226c6064c337c64ae39a30be8818bbb36cf51b4e"}], "version_and_mapping_successor_edges": [{"current_mapping_record_id": "sha256:a7a98745ad10a5a4af3487b64ae4877f51b2083102a893e9f9e162dcd290e4a0", "current_version_record_id": "sha256:614be61bca000590bc667d17756ad091f58a3f4be437dfef9e82703687ad5778", "instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_supersedes_record_id": "sha256:e8a7b9245af95f2798ccfbfae4c0a8f6564ebcd63db3b0ffae70e5c9e0f07cae", "prior_mapping_record_id": "sha256:e8a7b9245af95f2798ccfbfae4c0a8f6564ebcd63db3b0ffae70e5c9e0f07cae", "prior_version_record_id": "sha256:5019eaa6e0ae2765d9d4430b7b3820df330d1f2091eb15ae88c26581cf1d2f5b", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "transition_index": 1, "version_supersedes_record_id": "sha256:5019eaa6e0ae2765d9d4430b7b3820df330d1f2091eb15ae88c26581cf1d2f5b"}, {"current_mapping_record_id": "sha256:faee8594417efff70fc83290eae57378399a86ad5fc42fc3f92eed2c7ecd6fce", "current_version_record_id": "sha256:6299ac92fc102ef3bb9d97eb485d125eede589757091874fc045365600223a8d", "instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_supersedes_record_id": "sha256:8529c11e2474c0908753d924390f2c9379043e61462ba18a5413ea742ebf4072", "prior_mapping_record_id": "sha256:8529c11e2474c0908753d924390f2c9379043e61462ba18a5413ea742ebf4072", "prior_version_record_id": "sha256:3bac6dc4f6c2fbe504923732442aca178b6025730d375044e6b450ccee1e8fea", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "transition_index": 1, "version_supersedes_record_id": "sha256:3bac6dc4f6c2fbe504923732442aca178b6025730d375044e6b450ccee1e8fea"}, {"current_mapping_record_id": "sha256:43ed55345301cde4e2972950dc58f73b5bae931e0ef7cf1dcf54837ef26d86fc", "current_version_record_id": "sha256:ea874abad4e9445e23575fc07fd47630ea38b68ee09ac77e8b711014dcdb35bc", "instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_supersedes_record_id": "sha256:4e83101375209f71b30c4de85e53d9bccf95d0f8e56ae27b4088d3e4753d4c2e", "prior_mapping_record_id": "sha256:4e83101375209f71b30c4de85e53d9bccf95d0f8e56ae27b4088d3e4753d4c2e", "prior_version_record_id": "sha256:804a0d9383f7b77c8ddda8a4c703bedc9d8f7319c631a545578169f726db017c", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "transition_index": 1, "version_supersedes_record_id": "sha256:804a0d9383f7b77c8ddda8a4c703bedc9d8f7319c631a545578169f726db017c"}, {"current_mapping_record_id": "sha256:30db97923e3acc00bffbcdc9ecca4ace85e14d06880b57f40f8476d99c41f1ff", "current_version_record_id": "sha256:8c540bd9a233e86d7f53206a9715dfa4a58c64c21075e7d75789adc807ae51b2", "instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_supersedes_record_id": "sha256:97ed2967a51ff1d4521e2ed12ce8d03d7823b5c860fc582619ff6bd661bf7cbc", "prior_mapping_record_id": "sha256:97ed2967a51ff1d4521e2ed12ce8d03d7823b5c860fc582619ff6bd661bf7cbc", "prior_version_record_id": "sha256:fb53e2e6705ec532d7f31debaf1be5d3a7670b085e1fa8183c9dcbc4f3f677b8", "provider_contract_key": "NSE_INDEX|Nifty 50", "transition_index": 1, "version_supersedes_record_id": "sha256:fb53e2e6705ec532d7f31debaf1be5d3a7670b085e1fa8183c9dcbc4f3f677b8"}, {"current_mapping_record_id": "sha256:7297658df686714881cc4524c4b57599d44ba0cc1d66ddac9d9716ecf18054a4", "current_version_record_id": "sha256:215d463f50c26bb1e30865519efed2fbb91d6805dc22d04ccddc3d1035062bd5", "instrument_id": "sha256:c9b2124c264fe3bb429153a4766726f0244f4caf8365b1d9548a7aa040979b13", "mapping_supersedes_record_id": "sha256:a7a98745ad10a5a4af3487b64ae4877f51b2083102a893e9f9e162dcd290e4a0", "prior_mapping_record_id": "sha256:a7a98745ad10a5a4af3487b64ae4877f51b2083102a893e9f9e162dcd290e4a0", "prior_version_record_id": "sha256:614be61bca000590bc667d17756ad091f58a3f4be437dfef9e82703687ad5778", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_CE", "transition_index": 2, "version_supersedes_record_id": "sha256:614be61bca000590bc667d17756ad091f58a3f4be437dfef9e82703687ad5778"}, {"current_mapping_record_id": "sha256:9152f9d61b5d78c573e9481b78c1c8426cd4f0261854db2c96aec40cc3852ba8", "current_version_record_id": "sha256:fcd7faa032b965e4ffaafdd90de959938525c6aa3953ff78c9957e1fa0bc7fc6", "instrument_id": "sha256:9a571ddc7adf1aa39b651785bd12c14ed7361052409766463815d362b9e11210", "mapping_supersedes_record_id": "sha256:faee8594417efff70fc83290eae57378399a86ad5fc42fc3f92eed2c7ecd6fce", "prior_mapping_record_id": "sha256:faee8594417efff70fc83290eae57378399a86ad5fc42fc3f92eed2c7ecd6fce", "prior_version_record_id": "sha256:6299ac92fc102ef3bb9d97eb485d125eede589757091874fc045365600223a8d", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_24500_PE", "transition_index": 2, "version_supersedes_record_id": "sha256:6299ac92fc102ef3bb9d97eb485d125eede589757091874fc045365600223a8d"}, {"current_mapping_record_id": "sha256:28c0aeec76258bacf32c8725e4cf297bbb223aec2822d31009a0e8872a73d2b4", "current_version_record_id": "sha256:9de9dc7f4199a667913ef6e73565141371151b0008907927704a54c892c75ea7", "instrument_id": "sha256:7d974b490f26c94ad41c73f173b15167e2e1862d0276ccbf21da8100d9bf2d87", "mapping_supersedes_record_id": "sha256:43ed55345301cde4e2972950dc58f73b5bae931e0ef7cf1dcf54837ef26d86fc", "prior_mapping_record_id": "sha256:43ed55345301cde4e2972950dc58f73b5bae931e0ef7cf1dcf54837ef26d86fc", "prior_version_record_id": "sha256:ea874abad4e9445e23575fc07fd47630ea38b68ee09ac77e8b711014dcdb35bc", "provider_contract_key": "NSE_FO|SANITIZED_NIFTY_FUT", "transition_index": 2, "version_supersedes_record_id": "sha256:ea874abad4e9445e23575fc07fd47630ea38b68ee09ac77e8b711014dcdb35bc"}, {"current_mapping_record_id": "sha256:4aa39ad8466a82807f8ee36e7ee0c0ff7f90affe534e7157d844956060c381aa", "current_version_record_id": "sha256:4e4c767109b91d9126fe935d8ef441a013f4c385135940f31ab79a8f623af3d5", "instrument_id": "sha256:af6e7d2b16f9e50afef865970c12a992d83c7803f3ddedd93303d24892e70da0", "mapping_supersedes_record_id": "sha256:30db97923e3acc00bffbcdc9ecca4ace85e14d06880b57f40f8476d99c41f1ff", "prior_mapping_record_id": "sha256:30db97923e3acc00bffbcdc9ecca4ace85e14d06880b57f40f8476d99c41f1ff", "prior_version_record_id": "sha256:8c540bd9a233e86d7f53206a9715dfa4a58c64c21075e7d75789adc807ae51b2", "provider_contract_key": "NSE_INDEX|Nifty 50", "transition_index": 2, "version_supersedes_record_id": "sha256:8c540bd9a233e86d7f53206a9715dfa4a58c64c21075e7d75789adc807ae51b2"}]}, "digest_match": true, "dump_removed": true, "representative_query_match": true, "restored_revision": "20260804_04", "row_counts": {"catalogue_ingestion_runs": 3, "catalogue_memberships": 12, "catalogue_row_outcomes": 15, "catalogue_source_artifacts": 3, "catalogue_version_records": 5, "catalogue_versions": 5, "futures_contracts": 2, "instrument_version_records": 16, "instrument_versions": 16, "market_instruments": 7, "option_contracts": 3, "provider_contract_mappings": 14, "provider_mapping_records": 14, "trading_session_version_records": 2, "trading_session_versions": 2, "trading_sessions": 1, "underlying_instruments": 2}, "semantic_and_record_ids_match": true, "source_revision": "20260804_04", "status": "passed", "target_safety_rechecked": true}
Alembic current: 20260804_04 (head)
Alembic check: No new upgrade operations detected.
compileall: passed
git diff --check: passed
```

The acceptance evidence remains independent-review pending and does not mark DATA-1.4 accepted.
<!-- DATA-1.4-EVIDENCE:TESTING:END -->
