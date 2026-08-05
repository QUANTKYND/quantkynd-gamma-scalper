# Codex Task — DATA-1.4 Checkpoint Implementation Authorization

## Decision

The revised DATA-1.4 design is approved for implementation through the mandatory mid-milestone checkpoint.

Approved design:

```text
DATA-1.4 Append-Only Market-Event Persistence Design Proposal
baseline: a6bd58fb427eb78a57ac0ee6b573ee8842e47428
branch: feature/append-only-market-event-persistence
migration: 20260804_04
```

Implementation is authorized only through the checkpoint defined below.

Do not continue into lifecycle completion, the full replay CLI, dump/restore completion, final documentation, or final acceptance evidence until the checkpoint has been independently reviewed.

---

# 1. Baseline verification

Run:

```bash
git switch feature/append-only-market-event-persistence
git fetch origin
git branch --show-current
git status --short
git rev-parse HEAD
git rev-parse origin/master
git merge-base --is-ancestor \
  a6bd58fb427eb78a57ac0ee6b573ee8842e47428 \
  HEAD
git log --oneline --decorate -10
```

Required:

- branch is exactly `feature/append-only-market-event-persistence`;
- accepted Phase-A merge is an ancestor;
- no application/migration implementation exists before this task;
- worktree state is understood and reported;
- approved design documents are preserved;
- no reset, rebase, squash, or merge.

If the branch contains unexpected implementation changes, stop and report them.

Record the exact implementation starting SHA.

---

# 2. Approved design clarifications

These clarifications are frozen for implementation.

## 2.1 Lifecycle registry foreign key

Use the composite foreign key:

```text
provider_lifecycle_observations
    (raw_event_id, lifecycle_kind)
        ->
raw_provider_lifecycle_events
    (raw_event_id, lifecycle_kind)
```

Do not implement the weaker wording that references only the raw PK plus an application kind check.

## 2.2 Lifecycle subtype integrity

Use the approved common registry:

```text
provider_lifecycle_observations
        ↓
provider_connection_lifecycle_observations
provider_subscription_lifecycle_observations
```

Deferred database integrity must prove:

- exactly one subtype exists for every normalized registry event;
- the subtype matches `lifecycle_kind`;
- connection events have no subscription set;
- subscription events reference one immutable instrument set.

No polymorphic foreign key is permitted.

## 2.3 Query visibility

Every normalized-event exact lookup and scan must join through committed result or lifecycle-batch membership.

A physically present event row without valid committed membership is not a valid domain read and must fail closed or remain invisible according to the approved port contract.

## 2.4 Advisory locking

Freeze:

```text
DATA14_ADVISORY_LOCK_NAMESPACE = -1377601296
DATA14_LOCK_STRIPE_COUNT = 64
```

The namespace is the signed big-endian int32 represented by the first four bytes of:

```text
sha256("quantkynd:data14:advisory-lock-namespace:v1")
```

Acquire only:

```sql
SELECT pg_advisory_xact_lock(
    CAST(:data14_namespace AS integer),
    CAST(:stripe AS integer)
)
```

Never use Python `hash()` or the one-bigint advisory-lock form for DATA-1.4.

---

# 3. Checkpoint implementation scope

Implement only:

1. durable persistence domain contracts;
2. deterministic persistence identities;
3. persistence error taxonomy;
4. query/write ports;
5. SQLAlchemy rows and explicit mappings;
6. migration `20260804_04`;
7. append-only database enforcement;
8. `PostgresUnitOfWork` repository exposure;
9. deterministic lock-stripe derivation;
10. parameter-budget bulk chunk planner;
11. one complete frame aggregate write/read path;
12. exact retry and core collision handling for that frame path;
13. focused pure, mapping, migration, PostgreSQL, concurrency, and DATA-1.3 regression tests;
14. checkpoint evidence.

The checkpoint frame path must support:

- exact raw bytes;
- complete, partial, frame-failed, and entry-only-failed results where practical in the focused fixture set;
- ordered accepted events;
- ordered failures;
- exact full/adopted hashes;
- mapping/version/catalogue temporal record provenance;
- result membership and reconciliation;
- schema-isolated readback;
- inserted versus idempotent reporting.

It is acceptable to leave complete lifecycle application services for the post-checkpoint phase, but the approved lifecycle schema, mappings, constraints, and registry/subtype structure must exist and pass focused schema/mapping tests.

---

# 4. Explicitly forbidden before checkpoint review

Do not complete:

- lifecycle persistence application service;
- full lifecycle adversarial matrix;
- production/offline persistence CLI;
- collision-fixture CLI mode;
- final dump/restore verification;
- complete performance campaign;
- full DATA-1.4 documentation set;
- final implementation evidence;
- quality policy;
- option-chain reconstruction;
- Redis;
- live feed wiring;
- LIVE-RV persistence wiring;
- frontend/API work;
- strategy, simulation, paper execution, or live execution.

Do not merge or mark DATA-1.4 implementation complete.

---

# 5. Durable domain contracts

Create the approved persistence-independent package under:

```text
backend/app/market_data/persistence/
```

Implement:

- frame aggregate persistence command;
- durable result identity;
- failure identity;
- lifecycle batch identity contract needed by mappings/schema;
- persistence summaries;
- query cursors with explicit schema version;
- constants for canonical schema/implementation labels;
- lock namespace/stripe constants;
- chunk planner;
- named collision, referential-integrity, concurrency, time-binding, and durable-corruption errors;
- repository/UoW protocols.

Requirements:

- no SQLAlchemy imports;
- no provider SDK/Protobuf objects;
- no random/database-generated replay IDs;
- no quality or chain semantics;
- direct construction rejects malformed values;
- schema 1 accepts only `upstox-v3-normalizer-1`.

Add pure tests for every identity, label, cursor, stripe, and chunk boundary.

---

# 6. Migration and schema

Create:

```text
backend/alembic/versions/20260804_04_append_only_market_events.py
```

with:

```text
revision = 20260804_04
down_revision = 20260804_03
```

Implement the approved table inventory and exact PK/unique/FK matrix.

At minimum include:

```text
raw_market_frames
market_normalization_results
market_observations
underlying_quote_observations
futures_quote_observations
option_quote_observations
market_segment_status_observations
market_normalization_result_events
market_normalization_failures
market_normalization_result_failures

provider_subscription_instrument_sets
provider_subscription_instrument_set_keys
provider_lifecycle_batches
raw_provider_lifecycle_events
provider_lifecycle_batch_events
provider_lifecycle_observations
provider_connection_lifecycle_observations
provider_subscription_lifecycle_observations
provider_lifecycle_batch_observations
```

Also add the approved temporal composite unique keys needed for quote provenance.

## Mandatory constraints

- source order uses signed `BIGINT` bounds;
- raw bytes are `1..16 MiB`;
- exact UTF-8 byte bounds mirror DATA-1.3;
- quote prices use exact `NUMERIC`;
- all price `NUMERIC` values reject `NaN`, `Infinity`, and `-Infinity`;
- every semantic `TIMESTAMPTZ` rejects both timestamp infinities;
- semantic timestamps have no server-time default;
- `supersedes_event_id IS NULL`;
- no cascade deletion;
- schema-to-canonical-implementation checks;
- exact result/event/failure membership constraints;
- normalized lifecycle common registry and concrete subtype FKs;
- no polymorphic FK;
- set-key order/count/digest integrity;
- result/lifecycle aggregate deferred integrity;
- no correction-graph machinery.

## Append-only enforcement

Every DATA-1.4 table must reject:

```text
UPDATE
DELETE
TRUNCATE
```

Use row-level update/delete rejection plus statement-level truncate rejection and privilege restrictions as designed.

The migration downgrade must refuse when any DATA-1.4 table contains history.

An empty downgrade/re-upgrade test must use guarded database recreation/bootstrap, not in-place clearing.

---

# 7. SQLAlchemy models and mappings

Create explicit row models and mappings.

Mapping requirements:

- reconstruct domain objects only from validated typed values;
- regenerate and compare canonical JSON payloads;
- verify raw frame bytes/hash/identity;
- verify result/event/failure identities;
- verify schema/canonical implementation labels;
- verify exact event/failure order;
- verify full/adopted hashes;
- verify finite Decimal values;
- verify finite timezone-aware timestamps;
- verify temporal catalogue semantic and record IDs;
- verify lifecycle registry/subtype consistency;
- verify set sorted order/count/digest.

Any read mismatch raises:

```text
MarketEventDurableCorruptionError
```

and returns no partial aggregate.

Do not reuse write-time collision errors for durable corruption.

---

# 8. Temporal catalogue provenance

For every accepted quote persist:

```text
provider_mapping_record_id
contract_version_record_id
catalogue_version_record_id
```

Within the same UoW and repeatable snapshot:

1. resolve the mapping state at the event's exact cutoffs;
2. resolve the instrument-version state;
3. resolve the catalogue-version state;
4. compare all semantic values with `ResolvedMarketSubjectV1`;
5. preserve the exact selected temporal record IDs;
6. reject missing or mismatched temporal records;
7. treat different record IDs on exact retry as a provenance collision.

Later catalogue successors must not silently reclassify the event.

Add a focused later-successor readback test.

---

# 9. Bounded locking and bulk planning

Implement pure lock derivation first.

For every deterministic root:

```text
stripe =
    unsigned_int(
        sha256(
            "data14-lock-stripe-v1"
            + NUL
            + entity_namespace
            + NUL
            + canonical_id
        )
    ) mod 64
```

Acquire unique stripes in ascending numeric order with the exact two-int SQL.

Required tests:

- namespace constant derivation;
- stable stripe vectors;
- duplicate stripe removal;
- ascending order;
- maximum 64 stripes for 5,000 event roots;
- maximum 64 stripes for 10,000 lifecycle roots;
- one-bigint lock key `0` does not alias;
- another two-int namespace with the same stripe does not alias;
- same namespace/stripe serializes;
- disjoint stripes may proceed independently.

Implement the approved 60,000-parameter chunk planner.

No frame path may perform one awaited SQL cycle per event.

Record actual SQL/chunk counts in checkpoint evidence.

---

# 10. Frame aggregate service

Implement:

```text
MarketEventPersistenceService.persist_frame_result(...)
```

through the checkpoint path:

```text
prevalidate complete aggregate
open one UoW
bulk resolve temporal catalogue provenance
derive and acquire sorted DATA-1.4 stripes
batch-fetch all existing deterministic IDs/unique roots
classify exact rows and collisions
capture persistence_recorded_at only when new content exists
bulk insert missing roots/events/subtypes/failures
bulk insert ordered memberships
re-read and verify complete aggregate
commit once
```

Repositories may flush but never commit.

On any failed statement:

- roll back the entire UoW;
- do not continue using the aborted transaction;
- translate only after rollback;
- retry only a recreated immutable command/UoW for approved concurrency SQLSTATEs;
- no partial visibility.

Implement exact retry and at least these collision paths:

- same raw ID, different bytes;
- same result ID, different result evidence;
- same event ID, changed immutable content;
- same failure ID, changed content;
- different temporal catalogue record provenance;
- forged shared event ID across raw captures.

---

# 11. Focused query paths

Implement enough approved read ports to prove:

```text
get_raw_frame_metadata
get_raw_frame
get_result(raw_event_id, normalization_schema_version)
get_event(event_id, normalization_schema_version)
load_result_aggregate
scan_normalization_results(normalization_schema_version, ...)
list_subject_observations(normalization_schema_version, ...)
list_provider_status(normalization_schema_version, ...)
```

Every normalized strategy/research query requires one explicit schema version.

Cross-schema audit methods may be deferred beyond the checkpoint unless needed for a schema-isolation test.

Queries must join committed membership roots and must not expose orphan event rows as valid domain observations.

Do not implement quality eligibility or latest-state selection.

---

# 12. Checkpoint tests

## Pure

- IDs and canonical labels;
- failure identity;
- cursor/schema requirements;
- namespace and stripe vectors;
- chunk planning;
- Decimal and timestamp validation;
- canonical payload equality;
- set canonicalization;
- upstream boundary mirroring.

## PostgreSQL schema/mapping

- full PK/unique/FK catalog inventory;
- common lifecycle registry and subtype FKs;
- no polymorphic FK;
- result/event/failure membership constraints;
- temporal composite provenance FKs;
- raw bytes and hashes;
- finite numeric checks;
- finite timestamp checks;
- UTF-8 byte constraints;
- update/delete/truncate rejection;
- non-empty downgrade refusal.

## Frame aggregate

- insertion;
- exact retry;
- complete result;
- partial result;
- frame failure;
- entry-only failure;
- ordered events/failures;
- all core collision classes;
- transaction rollback;
- schema-isolated readback;
- temporal provenance;
- later catalogue successor;
- raw-byte lazy versus full retrieval;
- typed/JSON mismatch fails closed.

## Concurrency

- concurrent exact inserts;
- concurrent conflicting inserts;
- shared stripe serialization;
- disjoint stripe progress;
- forged shared event ID;
- uncertain-commit retry behavior;
- failed bulk statement leaves no rows.

## Regression

- complete DATA-1.3 normalization suite;
- LIVE-RV;
- DATA-1.2 catalogue tests;
- fixture identity/hash verification.

Acceptance-critical checkpoint tests must have zero skips.

---

# 13. Required checkpoint evidence

Create:

```text
docs/implementation/DATA-1.4-append-only-market-event-persistence.md
```

with status:

```text
implementation checkpoint; independent checkpoint review pending
```

Record:

- starting SHA;
- checkpoint implementation SHA;
- commits and changed files;
- exact schema/table inventory;
- PK/unique/FK catalog dump;
- Alembic head/current/check;
- PostgreSQL server/client versions;
- `show max_locks_per_transaction`;
- frozen namespace and exact lock SQL;
- maximum locks used by 5,000-event and 10,000-event derived-root fixtures;
- `pg_locks` or repository-owned lock evidence;
- chunk formula and actual round trips;
- inserted and exact-retry aggregate summaries;
- collision summaries;
- raw bytes/hash/readback;
- full/adopted hashes;
- temporal record IDs;
- later-successor proof;
- schema-isolation proof;
- update/delete/truncate rejection;
- finite numeric/timestamp hostile results;
- one-byte raw-frame boundary proof;
- focused test counts/skips;
- DATA-1.3/LIVE-RV regression;
- Alembic migration behavior;
- worktree and local/remote SHA;
- every deviation from the approved design.

Do not claim dump/restore completion at this checkpoint.

---

# 14. Verification commands

Use the repository's exact guarded PostgreSQL environment.

At minimum run:

```bash
cd backend

UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m compileall -q app tests

UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -ra \
  tests/market_data/persistence \
  tests/persistence/test_market_event_repositories.py \
  tests/persistence/test_market_event_concurrency.py \
  tests/persistence/test_market_event_append_only.py \
  tests/persistence/test_market_event_migration.py \
  <all DATA-1.3 normalization tests> \
  <all LIVE-RV tests>
```

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic heads
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
UV_CACHE_DIR=/tmp/uv-cache uv run python tools/verify_market_event_fixtures.py
UV_CACHE_DIR=/tmp/uv-cache uv lock --check
```

Version proof:

```bash
docker compose exec -T postgres psql --version
docker compose exec -T postgres pg_dump --version
docker compose exec -T postgres pg_restore --version
docker compose exec -T postgres \
  psql -U quantkynd -d quantkynd_test -Atc 'show server_version'

docker compose exec -T postgres \
  psql -U quantkynd -d quantkynd_test -Atc \
  'show max_locks_per_transaction'
```

Frontend regression:

```bash
cd ../frontend
pnpm lint
pnpm build
```

Repository:

```bash
cd ..
git diff --check
git status --short
git rev-parse HEAD
git ls-remote --heads origin feature/append-only-market-event-persistence
```

Use exact existing test paths if repository inspection shows different names. Document every adjustment.

---

# 15. Commit structure

Suggested commits:

1. `feat(data): define market-event persistence contracts`
2. `feat(data): add append-only market-event schema`
3. `feat(data): map durable market-event aggregates`
4. `feat(data): add bounded persistence locking and batching`
5. `feat(data): persist deterministic frame aggregates`
6. `test(data): verify DATA-1.4 checkpoint invariants`
7. `docs(data): record DATA-1.4 checkpoint evidence`

Do not squash prior approved history.

Push the feature branch and stop for independent checkpoint review.

---

# 16. Required response

Return:

- branch;
- starting SHA;
- checkpoint implementation SHA;
- evidence SHA/final pushed SHA;
- commits;
- exact changed files;
- schema/table inventory;
- PK/unique/FK inventory result;
- migration head/current/check;
- PostgreSQL server/client versions;
- lock namespace, SQL form, and maximum acquired stripes;
- bulk chunk and round-trip evidence;
- frame insertion/exact-retry results;
- collision and rollback results;
- temporal provenance/later-successor result;
- schema-isolation result;
- append-only hostile results;
- finite numeric/timestamp hostile results;
- raw-byte and result-hash readback;
- focused tests/skips;
- DATA-1.3/LIVE-RV regression;
- frontend result;
- worktree and local/remote SHA.

Stop at the checkpoint.

Do not continue into the remaining DATA-1.4 implementation until independent review approves it.
