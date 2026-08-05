# DATA-1.4 Pre-Implementation Requirements and Design Gate

## Milestone

```text
ID: DATA-1.4
Name: Append-Only Market-Event Persistence
Parent: DATA-1 — Point-in-Time Options Data
Required starting branch: master
Required starting SHA: c1be87dd6914d946fb7086d9a7c2f67641e4f924
Target branch: feature/append-only-market-event-persistence
Expected migration: 20260804_04
```

## Current status

DATA-1.3 is accepted. DATA-1 remains active.

This task is **design-only**.

Do not:

- modify application code;
- create the migration;
- add tests;
- add dependencies;
- update implementation evidence;
- commit or push implementation;
- create tables manually;
- run destructive database operations.

The only permitted repository change before design approval is an explicitly authorized design/requirements document.

Implementation begins only after the complete design proposal has been independently reviewed and approved.

---

# 1. Baseline verification

Run:

```bash
git switch master
git pull --ff-only origin master
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline --decorate -8
git merge-base --is-ancestor \
  c1be87dd6914d946fb7086d9a7c2f67641e4f924 \
  HEAD
```

Required:

```text
branch = master
HEAD = c1be87dd6914d946fb7086d9a7c2f67641e4f924
worktree = clean
ancestor check = exit 0
```

Then create, without implementation:

```bash
git switch -c feature/append-only-market-event-persistence
```

If the branch already exists, stop and report its local and remote SHAs. Do not reset, delete, rebase, or reuse it silently.

The design proposal must record the verified branch, exact SHA, worktree state, PostgreSQL server/client availability, and current Alembic head.

---

# 2. Mandatory reading

Read in repository order:

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/conventions.md`
4. `docs/design.md`
5. `docs/data-models.md`
6. `docs/api.md`
7. `docs/environment.md`
8. `docs/dependencies.md`
9. `docs/testing.md`
10. `docs/performance.md`
11. `docs/observability.md`
12. `docs/security.md`
13. `docs/standards/milestone-requirement-standard.md`
14. `docs/plan/options-market-infrastructure.md`
15. `docs/plan/roadmap.md`
16. `docs/plan/acceptance-gates.md`
17. DATA-1.0, DATA-1.1, DATA-1.2, and DATA-1.3 implementation evidence.
18. Existing instrument/domain ports.
19. Existing PostgreSQL models, mappings, repositories, unit of work, migration verification, destructive safety, fixtures, and restore tooling.
20. Alembic revisions `20260804_01`, `20260804_02`, and `20260804_03`.
21. All DATA-1.3 raw-frame, normalization-result, quote/status, lifecycle, failure, identity, serialization, and hashing contracts.

The proposal must cite exact repository files and symbols. Do not describe an imagined architecture.

---

# 3. Problem statement

DATA-1.3 can deterministically transform an exact Upstox V3 frame or lifecycle fixture into immutable provider-neutral observations and failures.

Those results are not durable.

A process restart currently loses:

- exact raw frame bytes;
- capture identity and provenance;
- normalization result status and reconciliation;
- accepted quote and status observations;
- normalization failures;
- provider connection lifecycle;
- provider subscription lifecycle;
- full-provenance and adopted-semantics hashes.

DATA-1.4 must create one append-only PostgreSQL truth from which QuantKYND can reproduce what was captured, what normalization produced, and what failed.

Later milestones depend on this durable boundary:

```text
DATA-1.4 persistence
        ↓
DATA-1.5 versioned quality policy
        ↓
DATA-1.6 point-in-time option-chain reconstruction
```

DATA-1.4 does not decide quote eligibility and does not build chains.

---

# 4. Required outcome

At acceptance, the system must be able to prove:

> This exact capture identity and exact raw content were durably recorded; this normalization schema and implementation produced these exact ordered observations and failures; exact retries are idempotent; conflicting reuse of any deterministic identity is rejected; and the same durable records can be replayed after PostgreSQL dump and restore.

It must support deterministic read paths required by DATA-1.5 and DATA-1.6 without implementing those milestones.

---

# 5. Architectural boundary

Required dependency direction:

```text
offline CLI / future capture worker
        ↓
market-event persistence application service
        ↓
market-event domain ports
        ↓
one UnitOfWork transaction
        ↓
PostgreSQL repositories and mappings
        ↓
SQLAlchemy rows / Alembic schema
```

Forbidden:

- normalization domain importing SQLAlchemy;
- DATA-1.3 decoder or normalizer writing to Postgres;
- repositories committing independently;
- application services exposing `AsyncSession`;
- provider SDK or generated Protobuf objects entering durable domain ports;
- database rows becoming domain contracts;
- persistence altering event identity or hashes;
- persistence recalculating market values from raw frames;
- live WebSocket or subscription wiring;
- Redis;
- frontend changes;
- quality-policy decisions;
- option-chain reconstruction;
- analytics or execution.

The proposal must name every new package/module and its allowed dependencies.

---

# 6. Frozen upstream contracts

Do not redesign DATA-1.3.

Persistence must preserve exactly:

- `RawMarketFrameV1`;
- `RawMarketFrameIdentityV1`;
- `FrameCaptureProvenanceV1`;
- `FrameNormalizationResultV1`;
- `NormalizationFailureV1`;
- underlying/futures/option quote observations;
- provider market-segment status observations;
- raw and normalized connection lifecycle events;
- raw and normalized subscription lifecycle events;
- deterministic event IDs;
- full-result and adopted-semantics hashes;
- unit-neutral quantity basis;
- explicit provider sequence absence;
- selected response type;
- deferred-field declarations;
- lifecycle duplicate classification;
- canonical serialization.

If a durable requirement reveals an upstream contract defect, stop and identify it as a blocker. Do not modify DATA-1.3 silently.

---

# 7. Scope to design

The design proposal must cover persistence for:

## 7.1 Raw frame truth

- deterministic raw frame identity;
- exact raw bytes or an explicitly justified durable equivalent;
- canonical frame hash;
- provider/schema identity;
- connection session;
- source-order scope and ordinal;
- receipt/availability/recording clocks;
- capture basis;
- paired optional source file/record IDs.

## 7.2 Frame normalization result

- result identity;
- raw frame reference;
- normalizer schema and implementation version;
- response type;
- complete/partial/failed status;
- decoded/accepted/failed reconciliation counts;
- frame failure;
- entry failures;
- unadopted schema declarations;
- present deferred nested-message declarations;
- secondary-payload declarations;
- full-result hash;
- adopted-semantics hash.

## 7.3 Accepted market observations

- underlying quote;
- futures quote;
- option quote;
- market-segment status.

## 7.4 Provider lifecycle observations

- connection lifecycle;
- subscription lifecycle;
- instrument-set digest/count and, if approved, canonical keys;
- raw identity provenance;
- exact duplicate classification boundary.

## 7.5 Deterministic replay reads

- retrieve exact raw capture;
- retrieve one normalization result with ordered events/failures;
- scan captures/results in stable source order;
- retrieve observations by subject and point-in-time cutoffs;
- retrieve provider lifecycle by session/scope and time;
- verify full and adopted hashes after row-to-domain mapping.

---

# 8. Explicit non-goals

DATA-1.4 must not implement:

- `DataQualityAssessment`;
- `DataQualityEvent` policy production;
- accepted/quarantined/rejected quote disposition;
- freshness or sequence-gap policy;
- latest eligible quote;
- option-chain reconstruction;
- option trades;
- chain snapshots;
- IV, Greeks, surfaces, implied variance;
- Redis or latest-state cache;
- live subscription changes;
- LIVE-RV persistence wiring unless separately approved;
- strategy decisions;
- backtest integration;
- paper/live orders;
- production retention deletion;
- partitioning without measured need and approved design;
- object-store infrastructure unless explicitly approved before implementation.

Schema must not include speculative quality or chain fields.

---

# 9. Required design response

Return one complete design proposal with the following numbered sections.

Do not return implementation code.

## 1. Baseline and repository findings

Record:

- exact branch/SHA;
- current Alembic head;
- current PostgreSQL/UoW architecture;
- existing relevant rows, mappings, ports, repositories, exceptions, and verification tools;
- DATA-1.3 contracts to be persisted;
- any mismatch between documentation and source.

## 2. Proposed package layout

Show every proposed file.

Separate:

- domain ports;
- application service;
- PostgreSQL rows;
- mappings;
- repositories;
- UoW exposure;
- migration;
- CLI;
- tests;
- verification/evidence.

## 3. Persistence aggregate boundary

Define whether the atomic aggregate is:

```text
raw frame + normalization result + events + failures
```

and whether lifecycle batches use a separate aggregate.

Explain why.

## 4. Durable identity taxonomy

For every durable object distinguish:

- semantic identity;
- deterministic durable record identity;
- provider identity;
- source/capture identity;
- database primary key;
- excluded identity material.

Answer:

- What is the normalization-result ID?
- Is `full_result_hash` an identity or evidence?
- Is a quote event ID both semantic and durable ID?
- What identifies a failure row?
- What identifies result-to-event order?
- What identifies raw lifecycle records?
- Can two results exist for one raw frame under different normalizer versions?
- Can the same accepted event belong to two deterministic results?
- Which IDs are generated outside the database?
- Are any IDs database-generated?

No UUID is permitted where replay identity must be reproducible.

## 5. Raw bytes durability decision

Choose and justify one:

### A. PostgreSQL `BYTEA`

Persist exact frame bytes in PostgreSQL.

### B. Durable object reference

Persist an immutable object key plus content verification, only if a real object-store dependency is explicitly added and accepted.

### C. Another design

Must still reproduce exact bytes after restore.

A hash alone is insufficient for decoder replay.

Address:

- 16 MiB maximum;
- TOAST behavior;
- frame-size checks;
- row and backup volume;
- compression;
- read amplification;
- security/logging;
- retention limitation;
- dump/restore;
- whether raw bytes are fetched lazily.

Do not silently omit raw bytes.

## 6. Table-by-table schema sketch

For every table provide:

- table name;
- purpose;
- columns and PostgreSQL types;
- primary key;
- foreign keys;
- check constraints;
- unique constraints;
- immutable fields;
- indexes;
- deletion policy;
- conflict behavior;
- expected queries.

At minimum evaluate the need for tables equivalent to:

```text
raw_market_frames
market_normalization_results
market_normalization_failures
market_normalization_result_events or event ordinal ownership

underlying_quote_observations
futures_quote_observations
option_quote_observations
market_segment_status_observations

provider_connection_lifecycle_observations
provider_subscription_lifecycle_observations
subscription_instrument_keys, if canonical keys are durable
```

Do not accept this list blindly. Consolidation or separation must be justified.

## 7. Typed-column versus canonical-payload strategy

For each entity decide which values are:

- query-critical typed columns;
- canonical JSONB payload;
- exact binary payload;
- derived and therefore not stored;
- stored redundantly with equality validation.

Address forward-compatible reconstruction and collision comparison.

Do not make future point-in-time queries depend on scanning arbitrary JSONB.

## 8. Numeric storage

Specify:

- price type and precision;
- quantity type;
- OI type;
- source order type;
- counts;
- byte lengths;
- hash lengths;
- enum/check strategy.

Preserve exact `Decimal` values.

Show why all approved values fit.

## 9. Time model

Distinguish:

- provider timestamp;
- last-trade timestamp;
- received time;
- availability time;
- DATA-1.3 `recorded_at`;
- database transaction acceptance time;
- physical row insertion time, if different;
- market query cutoff;
- knowledge query cutoff.

Resolve the critical question:

> Is DATA-1.3 `recorded_at` the durable knowledge time, or must DATA-1.4 add a separate accepted persistence boundary?

Explain historical import visibility.

State exact predicates for future DATA-1.5/1.6 reads.

No timestamp may be silently replaced with `now()`.

## 10. Persistence-time binding

Define:

- whether the caller supplies the accepted write timestamp;
- whether one transaction captures one write-boundary timestamp;
- relationship between frame/result/event `recorded_at` values;
- allowed clock skew;
- future timestamps;
- offline backfills;
- retry behavior;
- what participates in hashes/IDs.

## 11. Append-only contract

Specify how the database prevents:

- updates;
- deletes;
- mutable corrections;
- accidental cascades;
- silent overwrite.

Decide whether append-only is enforced through:

- application-only discipline;
- restricted repository API;
- SQLAlchemy event hooks;
- database permissions;
- triggers;
- tests;
- a combination.

Avoid adding operational complexity without proof, but do not leave append-only as an undocumented convention.

## 12. Idempotency and collision rules

For each table define:

```text
same deterministic ID + completely equal immutable content
    -> idempotent

same deterministic ID + different content
    -> named collision failure
```

Address concurrent identical inserts and concurrent conflicting inserts.

Named failures must distinguish:

- raw capture identity conflict;
- raw content/hash mismatch;
- normalized event identity conflict;
- normalization-result conflict;
- failure identity conflict;
- lifecycle identity conflict;
- mapping/referential integrity error.

## 13. Failure-row identity

Define a deterministic failure-row identity that remains stable across:

- repeated normalization;
- input map-order differences;
- failure tuple order;
- multiple diagnostics for one entry;
- frame versus subject versus segment scope.

Do not rely on an auto-increment row ID for replay identity.

## 14. Result membership and order

Define how the database preserves exact deterministic order of:

- accepted events;
- entry failures;
- unadopted paths;
- present deferred paths;
- secondary payload paths.

If arrays or JSONB are used, justify query and integrity behavior.

If join rows are used, define ordinal constraints and reconciliation.

## 15. Atomic write service

Design the application service for persisting one frame result.

Required semantics:

```text
validate complete aggregate before write
        ↓
one UnitOfWork
        ↓
insert/compare raw frame
        ↓
insert/compare result
        ↓
insert/compare events and failures
        ↓
validate reconciliation
        ↓
commit once
```

Any failure rolls back the entire aggregate.

Repositories never commit.

## 16. Lifecycle persistence transaction

Define whether one lifecycle event or one validated lifecycle batch is the atomic unit.

Address:

- exact duplicate removal;
- conflict under reused raw identity;
- interleaved subscription scopes;
- reconnect session/scope history;
- batch hash, if any;
- partial persistence prohibition;
- source-order readback.

## 17. Unit of work design

Specify how market-event repositories are exposed from `PostgresUnitOfWork`.

Preserve:

- one instance, one transaction;
- no reuse after commit/rollback;
- rollback on context exit;
- read-only repeatable-read mode;
- no repository commit.

State whether a specialized market-event UoW is preferable and why.

## 18. Concurrency model

Cover:

- two writers persisting the exact same aggregate;
- same raw identity with different bytes;
- same event ID with different payload;
- result inserted while another transaction inserts event rows;
- deadlock avoidance;
- transaction isolation;
- lock ordering;
- retry policy;
- SQLSTATE translation;
- no partial visibility.

Do not depend on timing-sensitive tests alone.

## 19. Referential integrity

Define database FKs for:

- raw frame to provider mapping/version/economic subject, where appropriate;
- result to raw frame;
- events to result/raw frame;
- quote to economic subject/version/mapping;
- lifecycle to raw identity;
- failure to result;
- correction target.

Explain which provenance IDs must be real FKs and which remain opaque historical evidence because the referenced catalogue row might not exist in the same database restore.

## 20. Event correction model

DATA-1.0 permits append-only event corrections through `supersedes_event_id`.

Decide whether DATA-1.4:

- fully supports and validates correction edges now;
- stores nullable edges but defers correction writes;
- excludes them and requires a later migration.

If supported, specify:

- same event type;
- same economic subject;
- target existence;
- no self-edge;
- no cycle;
- one visible successor;
- knowledge-time visibility;
- concurrency behavior;
- graph read validation.

DATA-1.6 must not inherit an ambiguous correction schema.

## 21. Query ports

Define exact domain-facing repository methods needed by DATA-1.4.

At minimum consider:

```text
get_raw_frame(raw_event_id)
get_result(raw_event_id, normalizer version)
get_event(event_id)
load_result_aggregate(...)
scan_raw_frames(...)
scan_normalization_results(...)
list_subject_observations(...)
list_provider_status(...)
list_connection_lifecycle(...)
list_subscription_lifecycle(...)
```

Every query must define ordering and cutoffs.

Do not implement latest eligible quote or chain selection.

## 22. Replay ordering

Define deterministic replay order when:

- provider sequence is absent;
- multiple connections exist;
- source-order scopes differ;
- provider timestamps tie;
- availability times tie;
- event IDs tie only through corruption.

Specify whether replay is:

- capture order;
- knowledge order;
- provider-time order;
- a named mode.

No implicit global source order.

## 23. Point-in-time read predicates

Design reads that DATA-1.5 and DATA-1.6 can build on.

For observations define behavior for:

```text
market_as_of
known_as_of
availability basis
historical-import opt-in
subject ID
event type
provider/mapping/version provenance
```

State exact SQL predicates and deterministic order.

Do not yet apply quality eligibility.

## 24. Failed and partial result persistence

Persist complete, partial, and failed outcomes.

Define:

- whether malformed frames with no decoded response type are durable;
- how zero decoded entries reconcile;
- how entry-only failed results persist;
- whether accepted events can coexist with entry failures;
- how frame failures forbid event rows;
- retry/collision behavior.

No failure may disappear because no accepted event exists.

## 25. Hash verification after persistence

Define row-to-domain verification for:

- frame content hash;
- raw event ID;
- normalized event IDs;
- full-result hash;
- adopted-semantics hash;
- lifecycle IDs/digests.

Reads must fail closed if durable rows reconstruct a different hash.

Name the integrity exception.

## 26. Migration `20260804_04`

Specify:

- exact filename;
- down revision;
- operation order;
- constraints and indexes;
- use of naming conventions;
- no server-time defaults for semantic clocks;
- upgrade from `20260804_03`;
- downgrade policy.

Address whether downgrade:

- is allowed only when new tables are empty;
- is destructive only in disposable acceptance databases;
- requires an explicit guard.

Do not silently drop durable market history.

## 27. Restore verification

Extend the established PostgreSQL 17 dump/restore gate.

Required comparison:

- Alembic revision;
- table and row counts;
- canonical row digests;
- raw-byte hashes;
- result hashes;
- representative aggregate reconstruction;
- representative point-in-time scans;
- lifecycle ordering;
- constraints after restore;
- no source/target aliasing.

## 28. Volume and performance assumptions

Provide initial estimates for:

- frames per second;
- events per frame;
- average and maximum raw frame bytes;
- daily row growth;
- index growth;
- dump/restore size;
- query patterns.

Define measurable thresholds that would trigger later partitioning or external raw-object storage.

Do not introduce partitioning merely because the table may become large.

## 29. Retention boundary

DATA-1.4 is append-only.

Define:

- no automatic deletion in milestone scope;
- whether raw bytes and normalized events share retention;
- why deleting raw bytes would break replay;
- how future retention would require an explicit archived-content contract;
- what the initial operational limitation is.

## 30. Security

Address:

- raw provider payload sensitivity;
- no token/authorized URL/account ID;
- no raw-byte logging;
- safe exception text;
- database least privilege;
- backup sensitivity;
- binary-size bounds;
- decompression not required;
- denial-of-service boundaries;
- SQL injection avoidance;
- secret and artifact scans.

## 31. Observability

Define structured summaries for successful and failed persistence:

```text
raw_event_id
frame hash
result status
event/failure counts
idempotent versus inserted counts
transaction duration
database revision
collision reason
```

Never log raw bytes or full provider payloads.

Do not add a new metrics/logging dependency unless explicitly justified.

## 32. CLI boundary

Propose an offline persistence/replay CLI for deterministic fixtures.

It must:

- accept DATA-1.3 fixture inputs;
- normalize through the existing application flow;
- persist through the new service;
- read back and verify;
- support exact retry;
- support a deliberate collision fixture;
- require explicit PostgreSQL URL;
- refuse unsafe database names where destructive setup is involved;
- never contact Upstox;
- never log raw bytes.

Define exit codes.

## 33. Adversarial scenario matrix

Include at least:

| Scenario | Required behavior |
|---|---|
| Exact aggregate inserted twice | Idempotent, same readback |
| Concurrent exact inserts | One durable aggregate, both callers resolve safely |
| Same raw ID, different bytes | Reject and roll back |
| Same frame hash, different capture identity | Persist as distinct captures |
| Same event ID, changed quote field | Reject and roll back |
| Same result identity, changed failure | Reject |
| Partial result with one valid and one failed subject | Persist both atomically |
| Frame failure with zero decoded entries | Persist failure, no events |
| Entry-only failed result | Persist all failures |
| Result event ordinal gap | Reject |
| Duplicate ordinal | Reject |
| Event refers to another raw frame | Reject |
| Quote mapping/version/subject mismatch | Reject |
| Invalid Decimal row introduced outside repository | Read fails closed |
| Raw bytes changed without hash change | Constraint/read verification fails |
| `recorded_at` later than accepted persistence boundary | Reject or named approved rule |
| Historical import queried without opt-in | Excluded |
| Two correction successors for one target | Reject/fail closed |
| Correction crosses subject/type | Reject |
| Process crashes before commit | No partial rows |
| Process retries after uncertain commit | Exact retry resolves idempotently |
| Database restored | Same hashes and ordered aggregates |
| Downgrade with persisted history | Refuse unless explicit approved destructive mode |
| 16 MiB frame | Accepted at boundary |
| Frame above bound | Rejected before persistence |
| Provider sequence absent | No invented global sequence |
| Reversed insert order | Same durable read result |

Add milestone-specific hostile cases discovered during source inspection.

## 34. Proof obligations

State executable proofs for:

1. exact retry idempotency;
2. collision rejection;
3. aggregate atomicity;
4. concurrent identical insertion;
5. concurrent conflicting insertion;
6. deterministic result ordering;
7. no identity mutation;
8. no numeric precision loss;
9. no time-zone loss;
10. no future knowledge leakage in repository reads;
11. historical-import limitation is explicit;
12. full/adopted hashes survive round trip;
13. raw bytes survive dump/restore exactly;
14. failed results survive persistence;
15. lifecycle order survives round trip;
16. correction graph is unambiguous or explicitly deferred safely;
17. migration upgrade/downgrade/re-upgrade behavior;
18. no DATA-1.3 behavior regression;
19. no LIVE-RV behavior change;
20. no quality/chain logic introduced.

## 35. Test plan

Separate:

### Pure tests

- durable identity;
- mappings;
- typed row projections;
- canonical payloads;
- collision comparison;
- time and Decimal round trips.

### PostgreSQL integration

- all repositories;
- aggregate write/read;
- idempotency;
- concurrency;
- partial/failed results;
- point-in-time scans;
- lifecycle;
- correction rules;
- malformed durable rows;
- UoW state.

### Migration

- `20260804_03 -> 20260804_04`;
- fresh upgrade;
- downgrade policy;
- re-upgrade;
- Alembic drift.

### Restore

- dump;
- guarded restore;
- canonical digest;
- raw bytes;
- representative queries.

### Regression

- DATA-1.3;
- DATA-1.2;
- complete backend;
- frontend lint/build.

Acceptance-critical PostgreSQL tests must have zero skips.

## 36. Acceptance environment

Require:

```text
PostgreSQL server 17.x
psql 17.x
pg_dump 17.x
pg_restore 17.x
database quantkynd_test
disposable-database sentinel
explicit destructive-test opt-in
local-host restriction
advisory lock
```

List exact required environment variables and refusal conditions.

## 37. Acceptance commands

Provide exact commands for:

- compile;
- focused no-database tests;
- PostgreSQL integration;
- concurrency;
- migration;
- restore;
- fixture persistence/replay CLI;
- complete backend;
- Alembic heads/current/check;
- frontend lint/build;
- secret/binary scan;
- `git diff --check`;
- worktree and remote-SHA verification.

## 38. Mandatory mid-milestone checkpoint

The implementation authorization must stop after:

1. durable domain/port contracts;
2. SQLAlchemy row and mapping design;
3. migration `20260804_04`;
4. repository interfaces;
5. one aggregate write/read path;
6. focused mapping/migration/PostgreSQL tests;
7. DATA-1.3 regression.

It must stop before:

- complete lifecycle adapters;
- full replay CLI;
- complete concurrency matrix;
- dump/restore completion;
- documentation/evidence completion.

Define the checkpoint evidence required.

## 39. Documentation plan

List exact updates to:

```text
docs/design.md
docs/data-models.md
docs/dependencies.md
docs/environment.md
docs/testing.md
docs/performance.md
docs/security.md
docs/observability.md
docs/plan/options-market-infrastructure.md
docs/plan/roadmap.md
docs/plan/acceptance-gates.md
docs/implementation/DATA-1.4-append-only-market-event-persistence.md
```

## 40. Unresolved questions and recommendation

List every unresolved decision.

For each:

- alternatives;
- correctness implications;
- operational implications;
- recommendation.

No blocker-level question may remain before implementation authorization.

---

# 10. Decisions that must not be deferred to implementation

The design must explicitly freeze:

1. Whether exact raw bytes are persisted and where.
2. Normalization-result identity.
3. Failure-row identity.
4. Result membership and order representation.
5. Event-table inheritance versus separate tables.
6. Typed columns versus canonical JSONB.
7. DATA-1.3 `recorded_at` versus actual database acceptance time.
8. Knowledge-time read predicates.
9. Aggregate transaction boundary.
10. Concurrent exact-retry semantics.
11. Concurrent collision semantics.
12. Correction-edge scope.
13. Downgrade refusal policy.
14. Raw-data retention limitation.
15. Replay ordering without provider sequence.
16. PostgreSQL indexes needed by DATA-1.5/1.6.
17. Restore digest and raw-byte proof.
18. CLI exit codes.
19. Mandatory checkpoint contents.
20. Explicit non-goals.

---

# 11. Design review standard

The proposal will be rejected if it:

- begins implementation;
- relies on hashes without durable raw bytes or a real immutable raw-object source;
- stores market prices as float;
- uses database-generated IDs for deterministic replay entities;
- treats `full_result_hash` as a substitute for identity without proof;
- overwrites existing rows on conflict;
- persists accepted events but drops failures;
- permits partial aggregate commits;
- invents provider sequence;
- hides historical imports in defensible knowledge-time replay;
- queries point-in-time state only by provider timestamp;
- uses JSONB as the only representation of query-critical values;
- lets repositories commit;
- introduces quality-policy decisions;
- introduces chain reconstruction;
- wires live subscriptions;
- adds Redis;
- omits PostgreSQL 17 migration/restore/concurrency tests;
- allows acceptance-critical skips;
- allows downgrade to silently destroy market history;
- leaves raw retention undefined;
- lacks a mandatory implementation checkpoint.

---

# 12. Required response

Return:

- verified baseline;
- proposed branch;
- complete 40-section design;
- table-by-table schema;
- identity and clock matrix;
- transaction and concurrency model;
- migration/downgrade plan;
- replay query contract;
- adversarial matrix;
- proof obligations;
- test and acceptance commands;
- unresolved questions and recommendations.

Stop after the design proposal.

Do not implement DATA-1.4 until the proposal is independently reviewed and approved.
