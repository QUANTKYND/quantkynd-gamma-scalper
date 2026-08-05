# Codex Task — DATA-1.4 Design Review Amendments and DATA-1.3 Durability Prerequisite

## Decision

The DATA-1.4 proposal is **not approved for implementation yet**.

Its overall architecture is strong, and its identified DATA-1.3 lifecycle-bound blocker is valid, but that blocker is incomplete. Several persistence decisions also conflict with the frozen DATA-1.3 identity model or need stronger point-in-time guarantees.

This task freezes the required corrections. Do not begin DATA-1.4 implementation.

Work in two phases:

1. complete and independently verify a narrowly scoped DATA-1.3 durability-boundary amendment;
2. update the DATA-1.4 design proposal against the amended accepted `master`.

Stop after the revised design proposal. DATA-1.4 implementation remains unauthorized.

---

# Phase A — DATA-1.3 durability-boundary amendment

## A1. Baseline and branch

Start from accepted `master`:

```text
c1be87dd6914d946fb7086d9a7c2f67641e4f924
```

The repository must be clean before branch creation.

The untracked DATA-1.4 requirements document must not remain in the repository working tree during baseline verification. Move it outside the repository or explicitly handle it under the repository's approved documentation workflow. Do not commit it to `master` merely to clear the worktree.

Create:

```text
fix/data-1.3-durable-boundaries
```

Do not reset, rebase, or reuse a pre-existing branch silently.

## A2. Bound source-order values

Freeze:

```text
MAX_SOURCE_ORDER = 2**63 - 1
```

Apply to every DATA-1.3 source-order contract:

- `RawMarketFrameIdentityV1`;
- `RawMarketFrameV1`;
- quote observations;
- market-status observations;
- raw connection lifecycle events;
- normalized connection lifecycle observations;
- raw subscription lifecycle events;
- normalized subscription lifecycle observations;
- capture/lifecycle manifests and CLIs.

Require:

```text
integer
not bool
0 <= source_order <= 2**63 - 1
```

This allows DATA-1.4 to use PostgreSQL `BIGINT` without claiming support for arbitrary Python integers that PostgreSQL cannot preserve without an operational bound.

Existing valid fixtures and event identities must remain unchanged.

## A3. Bound indexed opaque identifiers

Inventory every caller-controlled string that DATA-1.4 must index or place in a uniqueness constraint.

At minimum cover:

```text
provider_schema_id
connection_session_id
source_order_scope_id
subscription_scope_id
source_file_id
source_record_id
redacted_reason_code
```

Freeze a shared UTF-8 byte bound unless a field needs a narrower documented bound.

Recommended:

```text
MAX_OPAQUE_IDENTIFIER_BYTES = 512
MAX_REDACTED_REASON_CODE_BYTES = 128
```

Continue to require non-empty controlled values where existing contracts already do so.

Do not truncate, trim, case-normalize, or rewrite valid identifiers.

Add multibyte boundary tests.

## A4. Bound subscription instrument sets

`SubscriptionInstrumentSetV1` must use the existing provider-contract-key validator:

```text
non-empty
no edge whitespace
no ASCII controls
<= 512 UTF-8 bytes
```

Freeze:

```text
MAX_SUBSCRIPTION_INSTRUMENT_KEYS = 5000
```

The set constructor must reject more than 5,000 unique keys.

Apply request-mode-specific absolute limits in raw and normalized subscription lifecycle events:

```text
ltpc            <= 5000
option_greeks   <= 3000
full_d5         <= 2000
full_d30        <= 50
```

For unsubscribe events with no request mode, the global 5,000-key bound remains applicable.

Do not attempt to enforce Upstox's cross-category combined account limit in this immutable per-scope value. That requires connection-wide live subscription policy and remains outside DATA-1.3/DATA-1.4.

## A5. Bound lifecycle fixture/batch input

Freeze:

```text
MAX_LIFECYCLE_FIXTURE_BYTES = 16 MiB
MAX_LIFECYCLE_EVENTS_PER_BATCH = 10_000
```

The lifecycle fixture CLI must reject oversized input before full parsing and reject batches above the event limit.

No live-stream wiring is authorized.

## A6. Focused amendment verification

Required:

- direct hostile construction tests;
- JSON boolean/integer boundary tests;
- multibyte identifier/key byte boundaries;
- mode-specific subscription limits;
- lifecycle fixture byte and event limits;
- unchanged valid fixture IDs and hashes;
- complete DATA-1.3 tests;
- LIVE-RV tests unchanged;
- complete backend regression;
- frontend lint/build;
- no migration;
- Alembic remains `20260804_03`.

Update DATA-1.3 evidence as an accepted-contract amendment, but do not reopen unrelated DATA-1.3 behavior.

Commit, push, independently review, and merge this amendment before rebasing the DATA-1.4 design baseline.

---

# Phase B — revise the DATA-1.4 design proposal

After Phase A is accepted and merged:

1. update local `master`;
2. record the new exact accepted `master` SHA;
3. verify a clean worktree;
4. create `feature/append-only-market-event-persistence`;
5. revise the design only;
6. do not implement the migration or application code.

The revised proposal must preserve its current 40-section structure and incorporate every item below.

---

# B1. Correct normalization-result versioning

## Current conflict

DATA-1.3 event identity is:

```text
raw_event_id
event_type
subject_id
normalization_schema_version
```

It excludes `normalizer_implementation_version`.

The immutable event payload includes `normalizer_implementation_version`.

Therefore two results for one raw frame with:

```text
same normalization schema version
different normalizer implementation version
```

produce the same event IDs but different immutable event payloads, causing deterministic event collisions.

The current proposal simultaneously:

- allows multiple results per raw frame by implementation version; and
- stores observations globally by `event_id`.

Those choices are incompatible.

## Frozen decision

Use one canonical implementation-semantics label per normalization schema version.

Persist at most one result for:

```text
(raw_event_id, normalization_schema_version)
```

`normalizer_implementation_version` is immutable evidence and must equal the canonical implementation label allowed for that schema version.

A materially different implementation output requires a new normalization schema version.

Freeze:

```text
result_id = hash(
    entity,
    raw_event_id,
    normalization_schema_version
)
```

The same rule applies to normalized lifecycle events and lifecycle batch normalization.

Do not support multiple implementation versions under one schema through result-scoped copies. That would make the existing `event_id` and future quality-assessment identity ambiguous.

Update:

- durable identity taxonomy;
- result constraints;
- ports;
- query signatures;
- collision rules;
- adversarial cases;
- proof obligations.

---

# B2. Preserve exact temporal catalogue provenance

## Current gap

A quote stores semantic:

```text
provider_mapping_id
contract_version_id
economic_subject_id
```

The accepted catalogue model also has append-only temporal record identities for mapping and version knowledge states.

A semantic FK alone does not prove which temporal record leaf the resolver selected at:

```text
resolution_market_as_of
resolution_known_as_of
```

## Required design

For every quote observation, DATA-1.4 must durably bind:

```text
provider_mapping_record_id
contract_version_record_id
```

Evaluate whether `catalogue_version_record_id` is also required for complete source lineage. State the decision explicitly.

The persistence service must use the same UoW and exact event cutoffs to:

1. resolve mapping state;
2. resolve version state;
3. require semantic values equal the embedded `ResolvedMarketSubjectV1`;
4. store the selected temporal record IDs;
5. enforce real FKs to the corresponding record tables.

These record IDs are DATA-1.4 persistence provenance. They do not alter DATA-1.3 event IDs or hashes.

Exact retry with different temporal record provenance is a collision.

Static fixture persistence must seed matching catalogue temporal records before accepting quote observations.

Update point-in-time predicates and restore proofs accordingly.

---

# B3. Clarify persistence-time semantics

The proposal calls `persistence_accepted_at` a committed database boundary but captures it before writes. That is not the actual commit time.

Freeze an honest, executable meaning.

Recommended:

```text
persistence_recorded_at
```

Meaning:

> The DATA-1.4 service accepted the immutable aggregate for a successful persistence transaction.

Capture it from an injected UTC clock after lock acquisition and immediately before writing a new aggregate.

Do not call it exact PostgreSQL commit time.

Default DATA-1.5/DATA-1.6 epistemic visibility remains based on:

```text
event.available_at <= known_as_of
catalogue temporal record visibility <= known_as_of
historical-import policy
```

Provide an optional named durable-audit predicate:

```text
persistence_recorded_at <= durable_as_of
```

Do not silently make database flush latency part of market knowledge time.

If the design instead requires exact post-commit visibility time, specify a two-transaction immutable acceptance-marker protocol with crash recovery. Do not claim exact commit time from a pre-commit timestamp.

Update the time matrix, query ports, SQL predicates, and terminology consistently.

---

# B4. Address status availability basis

Quote observations carry an explicit normalized availability basis. Market-status observations do not.

Choose one:

### Recommended

Store an event-level persistence projection derived from the raw capture:

```text
received
historical_import
```

For quote events, require equality with `event_time.availability_basis`.

For status events, derive it from `RawMarketFrameV1.capture_basis` and receipt semantics.

### Alternative

Do not store availability basis on the common observation row and always join the raw frame for historical-import filtering.

Do not leave a common non-null availability-basis column unexplained for status events.

---

# B5. Use bounded bulk persistence

A valid frame may contain 5,000 accepted observations.

The implementation design must not perform one awaited SQL insert/select cycle per:

- registry row;
- subtype row;
- failure row;
- membership row.

Define a deterministic bulk strategy:

```text
prevalidate complete aggregate
acquire deterministic locks
batch-fetch existing IDs
bulk insert missing immutable rows
batch-fetch conflicts
compare complete immutable payloads
bulk insert memberships
reconstruct and verify
```

Use parameter-budget-based chunks so no statement exceeds PostgreSQL/asyncpg parameter limits.

State:

- chunk-size calculation;
- number of round trips as a function of N;
- deterministic lock order;
- conflict classification;
- behavior for 5,000-event frames;
- concurrency behavior across different raw frames sharing an event ID;
- how a failed statement avoids leaving the transaction unusable.

Do not rely on portable p95 thresholds before a baseline is measured. Record performance evidence first, then freeze a regression budget.

---

# B6. Normalize subscription instrument-set storage

Replace repeated key rows per lifecycle observation with immutable set-level storage:

```text
provider_subscription_instrument_sets
    instrument_keys_digest PK
    instrument_key_count
    canonical payload/hash

provider_subscription_instrument_set_keys
    instrument_keys_digest
    key_ordinal
    provider_contract_key
```

Subscription lifecycle observations reference the digest.

Validate:

- sorted canonical order;
- count;
- digest;
- mode-specific bound;
- exact retry;
- digest collision.

This avoids multiplying up to 5,000 key rows for every lifecycle state transition.

---

# B7. Correction-edge deferral

DATA-1.3 requires:

```text
supersedes_event_id is None
```

DATA-1.4 does not write corrections.

Persist the field only as exact payload evidence with:

```text
CHECK supersedes_event_id IS NULL
```

Do not add partial-successor indexes, graph FKs, or claim correction support now.

A later reviewed migration may:

- relax the null check;
- add graph constraints;
- add correction-write services;
- add knowledge-time graph reads.

DATA-1.6 treats non-null values as unsupported until that migration.

---

# B8. Refine concurrency locking

A raw-frame advisory lock alone does not serialize two different raw captures that attempt to insert the same deterministic event or lifecycle identity.

The revised design must freeze either:

### Recommended

Acquire transaction advisory locks for all deterministic roots in sorted order:

```text
raw frame ID
result ID
event IDs
failure IDs
lifecycle raw/event IDs
instrument-set digests
```

Use a stable signed-64-bit lock-key derivation with entity namespace separation.

### Alternative

Prove a bulk `ON CONFLICT DO NOTHING` plus batch compare design that cannot abort the transaction on non-target unique constraints and can classify every conflict safely.

Define deadlock avoidance and tests with different raw frames converging on one event ID.

---

# B9. Refine table constraints and sizes

After Phase A:

- use PostgreSQL `BIGINT` for source order;
- use bounded `VARCHAR` or explicit UTF-8 byte checks for indexed opaque identifiers;
- retain canonical SHA-256 checks;
- keep exact prices as unconstrained `NUMERIC`;
- keep quantity/OI bounds;
- make provider key and segment byte checks match DATA-1.3.

Do not use unbounded `NUMERIC` to claim arbitrary Python source-order support.

---

# B10. Revisit acceptance-time and result-root insert order

Define when the result root becomes the visibility marker.

If child rows may be inserted first, specify deferred FKs and commit-time integrity triggers.

If the result root is inserted first, explain how readers cannot observe an incomplete aggregate before commit and how exact retries classify an uncertain commit.

The aggregate remains one transaction. Repositories do not commit.

---

# B11. Complete raw/catalogue read integrity

On readback, verify:

- raw frame bytes/hash/identity;
- normalization result identity;
- canonical implementation label for schema;
- event identities;
- exact event order;
- failure identities/order;
- full/adopted hashes;
- mapping and version semantic IDs;
- mapping/version temporal record IDs;
- embedded subject values equal the referenced temporal states;
- lifecycle identities/digests/order.

Name separate collision versus durable-corruption exceptions.

---

# B12. Baseline and acceptance environment

Resolve before implementation authorization:

- clean baseline;
- accepted Phase-A `master` SHA;
- feature branch existence/remote state;
- PostgreSQL server 17.x;
- final `psql`, `pg_dump`, and `pg_restore` 17.x rather than host 18.x;
- current Alembic head `20260804_03`.

Do not treat cached remote refs as final baseline proof.

---

# Required revised design response

Return:

1. verified amended baseline;
2. clean target branch;
3. revised complete 40-section DATA-1.4 proposal;
4. explicit diff from the first proposal;
5. updated table-by-table schema;
6. updated identity/version matrix;
7. temporal catalogue record provenance;
8. final time/knowledge semantics;
9. bounded bulk-write/concurrency model;
10. amended migration/downgrade plan;
11. amended adversarial matrix and proof obligations;
12. no unresolved blocker-level questions.

Stop after the revised proposal.

Do not implement DATA-1.4 until independent design approval.
