# DATA-1.4 Append-Only Market-Event Persistence Design Proposal

## Status

Revised Phase B design proposed; DATA-1.4 implementation is not authorized.

The DATA-1.3 durability prerequisite is merged. This proposal resolves every blocker-level identity, time, catalogue-provenance, transaction, concurrency, migration, replay, and acceptance decision. Independent design approval is still required before application code, tests, or migration `20260804_04` may be created.

## 1. Baseline and repository findings

### Verified amended baseline

| Item | Verified finding |
|---|---|
| Accepted Phase-A `master` | `a6bd58fb427eb78a57ac0ee6b573ee8842e47428` |
| `origin/master` | `a6bd58fb427eb78a57ac0ee6b573ee8842e47428` after a fresh fetch |
| Phase-A ancestor | `c1be87dd6914d946fb7086d9a7c2f67641e4f924`, ancestor check passed |
| Baseline worktree | Clean before branch creation |
| Target branch | `feature/append-only-market-event-persistence`, created locally from the exact amended SHA |
| Target remote branch | Absent at design time; no cached-ref claim is used as proof |
| Repository changes in Phase B | Design documents only; no application, migration, dependency, test, API, or environment change |
| Alembic code head | `20260804_03` |
| PostgreSQL server | Repository container `postgres:17-alpine`, healthy, server `17.10` |
| Final acceptance clients | Container `psql`, `pg_dump`, and `pg_restore` `17.10` |
| Host clients | `18.4`; explicitly excluded from final version-17 evidence |

### Existing architecture and exact source anchors

- `backend/app/instruments/ports.py` defines `CatalogueVersionState`, `InstrumentVersionState`, `ProviderMappingState`, repository protocols, `UnitOfWork`, and the existing collision/integrity/UoW exceptions.
- `backend/app/persistence/postgres/unit_of_work.py:PostgresUnitOfWork` owns one `AsyncSession`, one transaction, rollback-on-exit, finality, and read-only repeatable-read mode.
- `backend/app/persistence/postgres/repositories.py` owns immutable insert/compare, temporal-state resolution, predecessor locking, and current mapping/version/catalogue state reads.
- `backend/app/persistence/postgres/models.py` contains semantic catalogue rows plus `CatalogueVersionRecordRow`, `InstrumentVersionRecordRow`, and `ProviderMappingRecordRow` append-only temporal states.
- `backend/app/persistence/postgres/mappings.py` performs explicit row/domain reconstruction and identity validation.
- `backend/app/persistence/postgres/verification.py:DURABLE_MODELS` and `durable_snapshot` produce ordered counts and canonical durable digests.
- `backend/app/cli/verify_database_restore.py` and `backend/app/persistence/postgres/database_safety.py` provide guarded PostgreSQL dump/restore, exact database names, sentinels, loopback checks, source/target separation, and advisory locks.
- DATA-1.3 contracts are `RawMarketFrameIdentityV1`, `RawMarketFrameV1`, `FrameCaptureProvenanceV1`, `FrameNormalizationResultV1`, `NormalizationFailureV1`, quote/status observations, lifecycle raw/normalized observations, `SubscriptionInstrumentSetV1`, `NormalizedMarketEventIdentity`, and canonical serialization/hash functions under `backend/app/market_data/normalization/` and `backend/app/market_data/point_in_time.py`.
- The merged `backend/app/market_data/normalization/limits.py` freezes signed-`BIGINT` source order, 512-byte opaque identifiers, 128-byte lifecycle reasons, 16 MiB lifecycle fixtures, and 10,000-event lifecycle batches. `lifecycle.py` freezes global and request-mode subscription limits.

### Explicit changes from the first proposal

1. The baseline is the accepted Phase-A merge, the worktree was clean at branch creation, and the feature branch now exists.
2. Result identity is `(raw_event_id, normalization_schema_version)`; implementation version is immutable evidence constrained to one canonical label per schema.
3. Multiple implementation-version results under one schema are forbidden.
4. Quotes persist mapping, instrument-version, and catalogue-version temporal record IDs with real FKs.
5. `persistence_accepted_at` is renamed `persistence_recorded_at` and is not called commit time or default epistemic knowledge time.
6. Common observation availability basis is a capture-derived persistence projection, including status observations.
7. Source order is PostgreSQL `BIGINT`; indexed opaque strings use bounded byte checks.
8. Subscription keys are stored once per immutable digest rather than repeated per lifecycle observation.
9. `supersedes_event_id` has only `CHECK IS NULL`; correction FKs, successor indexes, and graph claims are removed.
10. Locks cover every deterministic aggregate root, event, failure, lifecycle identity, and instrument-set digest in one sorted order.
11. Persistence is bounded bulk I/O with parameter-budget chunks, not one awaited SQL cycle per row.
12. Read integrity now verifies raw bytes, canonical implementation labels, exact order, hashes, and semantic plus temporal catalogue provenance.
13. Advisory serialization is bounded to 64 deterministic stripes rather than one lock per identity.
14. Every normalized replay query requires an explicit schema version; cross-schema reads are separately named audits.
15. Composite FK targets, `TRUNCATE` rejection, finite `NUMERIC` checks, and the upstream raw-byte lower bound are explicit.

No source/document mismatch remains that blocks design. DATA-1.3 `recorded_at` remains capture provenance, status lacks an upstream basis but receives the explicit persistence projection in section 9, and all Phase-A bounds now fit the proposed schema.

## 2. Proposed package layout

```text
backend/app/
├── market_data/persistence/
│   ├── __init__.py
│   ├── errors.py
│   ├── identities.py
│   ├── models.py
│   └── ports.py
├── services/
│   ├── market_event_persistence_service.py
│   └── market_lifecycle_persistence_service.py
├── persistence/postgres/
│   ├── market_event_models.py
│   ├── market_event_mappings.py
│   ├── market_event_repositories.py
│   ├── market_event_append_only.py
│   ├── unit_of_work.py
│   ├── verification.py
│   └── fixtures.py
└── cli/persist_market_event_fixture.py

backend/alembic/versions/
└── 20260804_04_append_only_market_events.py

backend/tests/
├── market_data/persistence/
│   ├── test_identities.py
│   ├── test_models.py
│   ├── test_mappings.py
│   └── test_persistence_service.py
├── persistence/
│   ├── test_market_event_repositories.py
│   ├── test_market_event_concurrency.py
│   ├── test_market_event_append_only.py
│   ├── test_market_event_migration.py
│   └── test_restore_verification.py
└── test_persist_market_event_fixture_cli.py
```

`market_data.persistence` may import DATA-1.3 domain contracts and core canonical hashing only. Services depend on domain ports and a UoW factory. Only `persistence.postgres` imports SQLAlchemy. Generated Protobuf objects and provider SDK types never cross the persistence port. Existing UoW, durable registry, fixture, and restore modules are extended narrowly. No dependency is added.

## 3. Persistence aggregate boundary

The frame aggregate is atomic:

```text
exact raw frame
+ one result for (raw_event_id, normalization_schema_version)
+ ordered accepted observations
+ ordered frame/entry failures
+ exact declarations and reconciliation evidence
+ exact temporal catalogue provenance for every quote
```

The result root is the committed visibility root. All rows are prevalidated, locked, written, reconstructed, and committed once. No observation or failure is query-visible outside a committed result membership.

Lifecycle uses a separate atomic batch aggregate because lifecycle input has no frame bytes or `FrameNormalizationResultV1`. One validated batch includes original input order, exact-duplicate positions, unique raw events, normalized events, immutable instrument sets, canonical schema label, and batch/sequence hashes. Partial frame or lifecycle aggregate persistence is prohibited.

## 4. Durable identity taxonomy

| Durable object | Deterministic identity / PK | Included identity material | Excluded evidence |
|---|---|---|---|
| Raw frame | existing `raw_event_id` | existing DATA-1.3 capture tuple | bytes/hash, clocks, persistence time |
| Normalization result | `result_id` | entity, `raw_event_id`, `normalization_schema_version` | implementation label, status, hashes, persistence time |
| Observation | existing `event_id` | existing raw/type/subject/schema identity | payload, implementation label, result membership |
| Failure | `failure_id` | entity, `result_id`, complete canonical failure payload | membership ordinal, persistence time |
| Result event membership | `(result_id, event_ordinal)` | result and exact ordinal | physical insert order |
| Result failure membership | `(result_id, failure_role, failure_ordinal)` | result, role, exact ordinal | physical insert order |
| Instrument set | existing `instrument_keys_digest` | sorted unique canonical provider keys | lifecycle event/batch |
| Raw lifecycle event | existing lifecycle `raw_event_id` | existing provider/session/scope/source-order tuple | normalized payload, batch |
| Normalized lifecycle event | existing lifecycle `event_id` | raw/type/subject/schema | implementation label, batch |
| Lifecycle batch | `lifecycle_batch_id` | kind, schema version, ordered raw IDs/payload hashes, duplicate positions | implementation label, persistence time |
| Batch input membership | `(lifecycle_batch_id, input_ordinal)` | exact capture position | physical insert order |
| Batch normalized membership | `(lifecycle_batch_id, event_ordinal)` | exact unique normalized order | physical insert order |

Freeze:

```text
result_id = hash(entity, raw_event_id, normalization_schema_version)
```

There is at most one result for `(raw_event_id, normalization_schema_version)`. `normalizer_implementation_version` must equal the one code/schema/migration-approved canonical label for that schema; schema version 1 currently permits only `upstox-v3-normalizer-1`. Different output semantics require a new normalization schema version, which produces new result and event identities. The same rule applies to lifecycle observations and lifecycle batch normalization.

| Normalization schema | Canonical implementation label | Result uniqueness | Event uniqueness |
|---:|---|---|---|
| 1 | `upstox-v3-normalizer-1` | one `(raw_event_id, 1)` | existing `(raw_event_id, event_type, subject_id, 1)` hash |
| Future N | introduced only by reviewed migration/code change | one `(raw_event_id, N)` | existing identity with schema N |

`full_result_hash` and `adopted_semantics_hash` are immutable evidence, never identity. A quote event ID is both semantic and durable ID. An event cannot legitimately belong to two frame results because its raw ID and schema version also determine the sole result ID; cross-result membership is corruption. Different raw captures converging on one event ID are a collision. Every replay ID is generated outside PostgreSQL. No deterministic entity uses UUIDs, sequences, identity columns, or other database-generated IDs.

## 5. Raw bytes durability decision

Use PostgreSQL `BYTEA` for exact frame bytes. `raw_market_frames.frame_bytes` is non-empty and satisfies `octet_length(frame_bytes) <= 16777216`. The service checks before opening a UoW; PostgreSQL repeats the bound. Hashes are recomputed before write and after read.

PostgreSQL may use TOAST compression internally; the contract depends only on exact returned bytes. Metadata scans never select `frame_bytes`; `get_raw_frame` explicitly fetches them. Logs contain ID, byte count, and hash only. Raw and normalized truth share retention because removing bytes breaks decoder replay. Dump/restore must reproduce the exact bytes and SHA-256. A hash or object key without a reviewed immutable object store is insufficient.

## 6. Table-by-table schema sketch

All deterministic SHA-256 IDs and prefixed content hashes are canonical `VARCHAR(71)`. The upstream raw provider-schema digest remains its exact 64-character lowercase hexadecimal value in `VARCHAR(64)`; the persistence capture projection stores the canonical prefixed form separately where DATA-1.3 already defines it. All FKs use `ON DELETE NO ACTION`. Every new table has append-only triggers and participates in restore digests.

### `raw_market_frames`

- Purpose: exact capture truth.
- Columns: `raw_event_id VARCHAR(71) PK`; provider/schema/session/source-scope bounded strings; `source_order BIGINT`; exact `frame_bytes BYTEA`; frame/schema hashes; receipt/availability/DATA-1.3 recording clocks; capture basis; paired bounded source file/record IDs; first `persistence_recorded_at TIMESTAMPTZ`.
- Constraints: canonical hashes, `1 <= octet_length(frame_bytes) <= 16777216`, `0 <= source_order`, capture-basis clock rules, source-ID pairing, UTF-8 byte limits, and unique capture tuple. The lower bound mirrors `RawMarketFrameV1.__post_init__` in `backend/app/market_data/normalization/identities.py`, which rejects empty `frame_bytes` before persistence.
- Indexes: `(provider, connection_session_id, source_order_scope_id, source_order, raw_event_id)`, `frame_content_hash`, and durable-audit order.
- Queries: exact/lazy raw lookup and scoped capture replay.

### `market_normalization_results`

- Purpose: committed aggregate root and result evidence.
- Columns: `result_id PK`; raw FK; schema version; canonical implementation label; response type; status; decoded/accepted/failed counts; frame-failure flag; declaration arrays; full/adopted hashes; canonical metadata JSONB; `persistence_recorded_at`.
- Constraints: `UNIQUE(raw_event_id, normalization_schema_version)` and `UNIQUE(result_id, raw_event_id)`; schema-to-label check; supported enums; non-negative bounded counts; canonical hashes; basic status/frame-failure shape.
- Indexes: `(normalization_schema_version, raw_event_id)`, `(normalization_schema_version, persistence_recorded_at, result_id)`, and status.
- Visibility: only after the transaction containing all children commits.

### `market_observations`

- Purpose: common immutable event registry.
- Columns: `event_id PK`; raw FK; event type; normalized subject; provider; nullable quote provenance fields; provider timestamp; null exchange timestamp; receipt/availability/DATA-1.3 recording clocks; `availability_basis received|historical_import`; source scope/order; schema/canonical implementation label; null provider sequence; `supersedes_event_id`; canonical payload JSONB.
- Quote provenance columns: economic subject, provider key, mapping/version/catalogue semantic IDs, `provider_mapping_record_id`, `contract_version_record_id`, `catalogue_version_record_id`, and exact resolution market/knowledge cutoffs.
- Constraints: `UNIQUE(event_id, raw_event_id)`; schema-label equality, event-type shape, `source_order BIGINT`, bounded identifiers, `supersedes_event_id IS NULL`, quote provenance all present/status provenance absent, and availability projection rules.
- FKs: raw frame; economic identity; mapping/version/catalogue semantic rows; composite temporal record/semantic keys described in section 19.
- Indexes: `(normalization_schema_version, economic_subject_id, event_type, provider_timestamp, available_at, event_id)`, `(normalization_schema_version, economic_subject_id, availability_basis, available_at, event_id)`, raw ID, and mapping/version provenance. No correction index or correction FK.

### Quote subtype tables

`underlying_quote_observations`, `futures_quote_observations`, and `option_quote_observations` use `event_id` as PK/FK. Typed columns store request/feed/snapshot semantics, exact prices, sizes, last trade, volume/OI, depth counts, path arrays, and a canonical subtype payload. Checks preserve finite prices, quantity/OI/depth, and enum bounds. Deferred aggregate validation binds subtype to registry event type and economic kind. Expected reads join the common registry through event ID; no JSONB scan is required.

### `market_segment_status_observations`

`event_id` PK/FK; bounded segment; status name/numeric/known flag; canonical payload. Status availability basis is already on `market_observations`, derived from the raw frame. Index `(normalization_schema_version, provider, segment, provider_timestamp, event_id)` supports schema-isolated deterministic status scans. No catalogue FK applies.

### `market_normalization_result_events`

`result_id`, raw ID, `event_ordinal INTEGER`, and event ID. PK `(result_id, event_ordinal)`; `UNIQUE(result_id, event_id)`; FKs `(result_id, raw_event_id) -> market_normalization_results(result_id, raw_event_id)` and `(event_id, raw_event_id) -> market_observations(event_id, raw_event_id)`. Commit-time aggregate integrity validates contiguous zero-based ordinals, exact count, and no cross-frame membership.

### `market_normalization_failures`

`failure_id PK`; result/raw IDs; scope/reason; bounded subject/segment/safe-detail fields; selected union; depth; exact path arrays; canonical payload. FKs `(result_id, raw_event_id) -> market_normalization_results(result_id, raw_event_id)`; `UNIQUE(failure_id, result_id, raw_event_id)` is the referenced scoped key. Checks enforce controlled scope/reason shape and byte/count limits. Indexes support result and reason diagnostics.

### `market_normalization_result_failures`

`result_id`, raw ID, role `frame|entry`, zero-based ordinal, and `failure_id`. PK `(result_id, failure_role, failure_ordinal)`; `UNIQUE(result_id, raw_event_id, failure_role, failure_ordinal)`; FKs `(result_id, raw_event_id) -> market_normalization_results(result_id, raw_event_id)` and `(failure_id, result_id, raw_event_id) -> market_normalization_failures(failure_id, result_id, raw_event_id)`. One frame role per result; aggregate integrity validates contiguous ordinals, frame/event exclusion, and failed-entry reconciliation.

### `provider_subscription_instrument_sets`

`instrument_keys_digest VARCHAR(71) PK`; `instrument_key_count INTEGER`; canonical key-array payload JSONB; canonical payload hash. Checks enforce canonical hashes and `1..5000`. A digest retry compares the complete immutable set; different keys/count under one digest raise a digest collision.

### `provider_subscription_instrument_set_keys`

`instrument_keys_digest`, `key_ordinal INTEGER`, bounded `provider_contract_key`. PK `(digest, ordinal)`; unique `(digest, provider_contract_key)`; FK to the set. Commit-time and read validation enforce sorted canonical order, contiguous ordinals, exact count, provider-key validity, and recomputed digest. Keys are stored once per set, not once per lifecycle transition.

### `provider_lifecycle_batches`

`lifecycle_batch_id PK`; kind/provider; schema/canonical label; input/unique/normalized/duplicate counts; batch and normalized-sequence hashes; canonical metadata; `persistence_recorded_at`. `UNIQUE(lifecycle_batch_id, lifecycle_kind)` is the batch membership target. Unique batch identity excludes implementation label. Checks reconcile bounded counts and supported kind/version.

### `raw_provider_lifecycle_events`

`raw_event_id PK`; kind/provider/session/subscription scope; previous/current state; source scope/order `BIGINT`; occurrence/availability/DATA-1.3 recording clocks; nullable mode; nullable instrument-set digest/count; bounded redacted reason; null provider sequence; canonical payload. `UNIQUE(raw_event_id, lifecycle_kind)` is the exact raw membership target. Subscription rows FK the immutable set digest. Checks enforce kind/state/mode/reason/clock/bound rules. Scope-order indexes preserve named replay.

### `provider_lifecycle_batch_events`

`lifecycle_batch_id`, lifecycle kind, input ordinal, raw ID, exact-duplicate flag, first-occurrence ordinal. PK `(lifecycle_batch_id, input_ordinal)`; FK `(lifecycle_batch_id, lifecycle_kind) -> provider_lifecycle_batches(lifecycle_batch_id, lifecycle_kind)`; FK `(raw_event_id, lifecycle_kind) -> raw_provider_lifecycle_events(raw_event_id, lifecycle_kind)`. `UNIQUE(lifecycle_batch_id, raw_event_id, input_ordinal)` documents membership identity. Validation preserves original order and exact duplicate classification.

### Normalized lifecycle tables

`provider_lifecycle_observations` is the common normalized registry: `event_id PK`; `raw_event_id`; `lifecycle_kind`; schema/canonical label; provider/session/scope; source order `BIGINT`; occurrence/availability/recorded clocks; provider sequence; canonical payload. It has `UNIQUE(event_id, lifecycle_kind)` and `UNIQUE(event_id, raw_event_id, lifecycle_kind)`, plus a real composite FK to the raw lifecycle event. `provider_connection_lifecycle_observations` and `provider_subscription_lifecycle_observations` are one-to-one typed subtype tables with `event_id PK/FK` to the registry and kind-constrained fields. Deferred aggregate integrity requires exactly one matching subtype; connection rows cannot carry subscription fields, while subscription rows reference the immutable set digest. Indexes begin with `(normalization_schema_version, ...)` for schema-isolated replay.

### `provider_lifecycle_batch_observations`

`lifecycle_batch_id`, normalized event ordinal, event ID, and kind. PK `(lifecycle_batch_id, event_ordinal)`; `UNIQUE(lifecycle_batch_id, event_id, lifecycle_kind)`; FKs `(lifecycle_batch_id, lifecycle_kind)` to the batch unique key and `(event_id, lifecycle_kind)` to `provider_lifecycle_observations(event_id, lifecycle_kind)`. It preserves unique first-capture normalized order; no kind-dependent or polymorphic FK is permitted.

## 7. Typed-column versus canonical-payload strategy

IDs, FKs, cutoffs, source order, provider time, availability basis, states, modes, prices, quantities, provenance, counts, ordinals, and hashes are typed query-critical columns. Raw bytes are exact `BYTEA`. Arrays store already ordered path/declaration tuples. Canonical JSONB stores the complete immutable DATA-1.3 projection for collision comparison and forward-compatible reconstruction; Decimal and UTC values use canonical strings.

Mappings reconstruct domain objects from typed columns, regenerate the canonical payload, and compare JSONB. Redundant typed/payload values must be equal before write and after read. Derived IDs, hashes, counts, and digests are stored only where needed for FK, query, or integrity enforcement and are recomputed. Future point-in-time reads never require arbitrary JSONB predicates.

## 8. Numeric storage

- Prices: unconstrained PostgreSQL `NUMERIC`, preserving every finite Python `Decimal` exactly. Each `bid_price`, `ask_price`, `last_price`, and `previous_close_price` column in every quote subtype has `CHECK (column IS NULL OR column NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))`; row mapping repeats `Decimal.is_finite()`.
- Sizes and reported volume: `BIGINT`, check `0..2**63-1`.
- Open interest: `BIGINT`, check `0..2**53`.
- Source order: `BIGINT`, check `0..2**63-1`; never `NUMERIC` and never boolean at the domain boundary.
- Event/key/count/ordinal values: `INTEGER`, bounded by 5,000 or 10,000 as applicable and non-negative.
- Raw byte length: `1..16,777,216`.
- Opaque indexed identifiers: `VARCHAR(512)` plus `octet_length <= 512`; redacted reason `VARCHAR(128)` plus byte check.
- Provider contract keys: 512 UTF-8 bytes, non-empty, no edge whitespace or ASCII controls; segments use the existing 128-byte equivalent.
- IDs/hashes: canonical `VARCHAR(71)` SHA-256 form.
- Enums: bounded strings plus explicit checks.

Every DATA-1.4 semantic `TIMESTAMPTZ` column (including `received_at`, `available_at`, `recorded_at`, `provider_timestamp`, `last_trade_timestamp`, `resolution_market_as_of`, `resolution_known_as_of`, `persistence_recorded_at`, and `occurred_at`) has `CHECK (column IS NULL OR (column <> 'infinity'::timestamptz AND column <> '-infinity'::timestamptz))`. Any future DATA-1.4 `DATE` column receives the equivalent finite-date check. Row mapping requires finite, timezone-aware UTC-compatible values; NULL remains valid only where the domain marks the clock optional.

PostgreSQL character length is not used as a substitute for UTF-8 byte length. Application construction uses the exact DATA-1.3 validators; database checks mirror byte/control/edge constraints, and row mapping revalidates them after any out-of-band write.

## 9. Time model

| Clock | Meaning | Default epistemic role |
|---|---|---|
| Provider timestamp | Selected provider payload time | Current DATA-1.4 market-time basis; exchange time remains null |
| Last-trade timestamp | Optional provider trade attribute | Attribute only |
| Received time | Physical receipt when available | Capture provenance |
| Available time | Earliest DATA-1.3 system availability | `available_at <= known_as_of` |
| DATA-1.3 `recorded_at` | Capture/normalization provenance | Preserved; not DB commit or acceptance time |
| Resolution market/knowledge cutoffs | Exact cutoffs used to select embedded subject state | Both must be at or before corresponding query cutoffs |
| Catalogue record IDs | Immutable normalization provenance | Exact leaves selected at the event's own resolution cutoffs; never silently reclassified as a later visible leaf |
| `persistence_recorded_at` | Service accepted a new immutable aggregate for a successful transaction | Optional `durable_as_of` audit predicate only |
| PostgreSQL commit time | Not captured exactly | No semantic claim or server default |

Common observation `availability_basis` is an event-level persistence projection with values `received` and `historical_import`. Quote rows must equal `event_time.availability_basis`. Status rows derive it from the raw capture: live-received and recorded-with-original-receipt map to `received`; historical import maps to `historical_import`. Receipt/basis consistency is revalidated.

The stored mapping/version/catalogue record IDs are immutable normalization provenance: they prove the exact leaves selected at the event's own `resolution_market_as_of` and `resolution_known_as_of`. Readback re-resolves those exact IDs at those original cutoffs and fails closed if a row was changed or cannot be reconstructed. A later catalogue successor does not reassign an existing event. A corrected interpretation requires a new normalization schema/result or a separately approved correction/re-normalization milestone.

Default future DATA-1.5/1.6 visibility for quotes is:

```sql
o.provider_timestamp <= :market_as_of
AND o.available_at <= :known_as_of
AND o.resolution_market_as_of <= :market_as_of
AND o.resolution_known_as_of <= :known_as_of
AND (:allow_historical_import OR o.availability_basis <> 'historical_import')
```

Status omits catalogue predicates. An optional, explicitly named durable-audit cutoff adds:

```sql
r.persistence_recorded_at <= :durable_as_of
```

It is never silently substituted for `known_as_of`. Physical database flush/commit latency is not market knowledge time. Instants are aware `TIMESTAMPTZ`, normalized to UTC, with inclusive cutoffs.

## 10. Persistence-time binding

After acquiring the complete deduplicated stripe set and immediately before writing any missing row, the service reads one injected UTC clock value named `persistence_recorded_at`. It means the service accepted the immutable aggregate for the transaction that subsequently succeeds; it is not exact PostgreSQL commit time.

For a new frame/result transaction, the raw frame and result receive that value. Shared pre-existing raw/event/set rows retain their original value; a later new schema result receives its own result value. Children do not duplicate the audit clock. Exact retry returns the stored value and does not call the clock for a new claim.

The caller cannot supply production time. A guarded deterministic fixture clock is injectable in tests/CLI only. DATA-1.3 clock relationships remain exact; persistence adds no requirement that capture `recorded_at` precede this service clock because offline restoration or clock-domain skew must not be reinterpreted as market knowledge. Future timestamps are accepted only if valid under upstream contracts and remain naturally invisible until their actual cutoffs. No persistence clock enters DATA-1.3 IDs or hashes.

## 11. Append-only contract

1. Ports expose insert/compare and reads only.
2. Repositories expose no update/delete/merge API and never commit.
3. One migration-owned row trigger rejects `UPDATE` and `DELETE`, and a statement-level `BEFORE TRUNCATE` trigger rejects `TRUNCATE` on every DATA-1.4 table.
4. Runtime roles receive `SELECT`/`INSERT` but no `TRUNCATE`, while migration ownership is separate outside disposable acceptance; there is no normal-path bypass flag.
5. All FKs use `NO ACTION`; no cascade exists.
6. Direct SQL tests attempt `UPDATE`, `DELETE`, and `TRUNCATE` and require rejection.

The migration owner may create/drop the trigger objects while applying an approved migration, but has no normal-path data mutation bypass and is not the runtime role. The owner and runtime role both encounter the rejection when directly attempting the three destructive statements after migration. Empty migration downgrade/re-upgrade setup uses guarded database recreation/bootstrap, never a data-table reset statement. No correction or retention path bypasses this contract. Later correction/archival behavior requires a separately reviewed migration.

## 12. Idempotency and collision rules

For every deterministic row and complete aggregate:

```text
same deterministic ID + completely equal immutable content -> exact idempotency
same deterministic ID + any different immutable content -> named collision and rollback
```

Exact equality includes temporal mapping/version/catalogue record IDs, canonical implementation label, typed columns, canonical payload, order, counts, and hashes. Retry with different selected temporal provenance is a collision even if semantic mapping/version IDs match.

Named write-time exceptions are `RawCaptureIdentityConflictError`, `RawFrameContentMismatchError`, `NormalizationResultConflictError`, `NormalizedEventIdentityConflictError`, `NormalizationFailureIdentityConflictError`, `LifecycleIdentityConflictError`, `InstrumentSetDigestCollisionError`, and `CatalogueProvenanceConflictError`. Unexpected FK/check/unique failures are `MarketEventReferentialIntegrityError`. Read-time malformed or inconsistent state is `MarketEventDurableCorruptionError`; collision exceptions are never reused for corruption.

Concurrent exact writers serialize on all roots. The loser batch-fetches and compares the committed rows, then returns idempotently. Concurrent conflicting writers serialize, compare, raise the precise collision, and roll back. Nothing overwrites an existing row.

## 13. Failure-row identity

`failure_id` is the canonical hash of entity, revised `result_id`, and the complete canonical `NormalizationFailureV1` payload. It is independent of Python tuple position and provider map order. Scope, reason, subject/segment identity, safe detail, selected union, depth, and path declarations are identity material.

Membership owns role and tuple order. Equal repeated diagnostics reuse one immutable failure row and may occupy separate ordinals only if upstream permits the tuple. Different diagnostics for one entry produce different IDs. A stale result hash or changed canonical failure under an existing ID is rejected.

## 14. Result membership and order

Accepted events use contiguous zero-based `event_ordinal`. Failures use role plus contiguous zero-based ordinal. Declaration/path tuples retain exact upstream sorted order in arrays. Lifecycle input and normalized output use separate contiguous ordinals.

Aggregate validation runs in memory before SQL, then a deferred commit-time integrity trigger validates root counts, ordinal continuity, role shape, and cross-frame membership. Read mapping repeats all checks and reconstructs the exact upstream tuple before verifying hashes. Physical insertion order is irrelevant.

## 15. Atomic write service

`MarketEventPersistenceService.persist_frame_result(command)` executes:

```text
validate the complete raw/result/event/failure aggregate in memory
validate result identity and canonical schema implementation label
open one PostgresUnitOfWork
bulk-resolve mapping/version/catalogue temporal states at each exact event cutoff
compare every semantic and embedded subject value
derive every deterministic root, derive/deduplicate its DATA-1.4 namespace/stripe pairs, and acquire them in numeric order with the frozen two-int advisory-lock SQL
batch-fetch all existing IDs and uniqueness roots
classify exact rows versus collisions before mutation
capture persistence_recorded_at only if something is new
bulk insert missing raw/result/event/subtype/failure rows in bounded chunks
bulk insert ordered memberships
batch-read the complete aggregate without raw bytes, then with bytes for final proof
reconstruct and verify identities, temporal provenance, order, and hashes
commit once
```

The UoW exposes a bulk provenance resolver so 5,000 quotes do not call mapping/version/catalogue SQL one event at a time. Requests are deduplicated by provider key, economic subject, catalogue version, and exact cutoff tuple, then resolved in parameter-bounded batches within the same snapshot/UoW.

The result row is inserted after the raw row and before children because child FKs target it. It becomes a visibility root only at transaction commit; MVCC prevents readers from seeing the incomplete uncommitted aggregate, and all query ports join memberships to a committed result. Deferred integrity validates completeness at commit. An uncertain-commit retry locks and loads the whole root before deciding idempotency.

Repositories may flush and execute but never commit. Any failed statement invalidates the UoW; the service rolls back the whole transaction and never attempts in-transaction recovery.

## 16. Lifecycle persistence transaction

One complete validated lifecycle batch is atomic. The service runs DATA-1.3 identity-batch and sequence validation, preserves original duplicate positions, constructs/validates normalized events under the canonical schema label, and computes the batch and sequence hashes before SQL.

It derives and acquires the sorted deduplicated DATA-1.4 namespace/stripe set for the batch ID, raw lifecycle IDs, normalized event IDs, and set digests; batch-fetches existing rows; bulk inserts missing sets/keys, roots, observations, and memberships; reconstructs both input and normalized order; then commits once. Exact duplicates reference one raw/normalized row but retain all input positions. Interleaved scopes and reconnect resets retain DATA-1.3 semantics. Partial batch persistence is forbidden.

## 17. Unit of work design

Extend `UnitOfWork`/`PostgresUnitOfWork` with `market_events`, including bulk provenance resolution. Do not create a second UoW: temporal catalogue reads and durable writes must share one session, repeatable snapshot, lock set, and final transaction.

One instance represents exactly one transaction. It cannot be reused after commit, rollback, or failure. Exit without commit rolls back. Read-only repeatable-read mode remains available for replay/verification. Repositories never commit and never expose `AsyncSession` through domain ports.

## 18. Concurrency model

Use `REPEATABLE READ` plus bounded deterministic transaction advisory lock striping. Freeze the signed-int32 namespace derived from the SHA-256 of the documented label `quantkynd:data14:advisory-lock-namespace:v1`: `DATA14_ADVISORY_LOCK_NAMESPACE = -1377601296`; this is stable, tested, and distinct from the repository's existing one-bigint DATA-1.3 catalogue/destructive locks. Also freeze:

```text
DATA14_LOCK_STRIPE_COUNT = 64
```

For every deterministic root, derive:

```text
sha256("data14-lock-stripe-v1" + NUL + entity_namespace + NUL + canonical_id)
    interpreted as an unsigned integer
    modulo DATA14_LOCK_STRIPE_COUNT
```

The aggregate derives all required stripes, deduplicates them, sorts the integers, and executes `SELECT pg_advisory_xact_lock(CAST(:data14_namespace AS integer), CAST(:stripe AS integer))` once per stripe in ascending numeric order. PostgreSQL's one-bigint and two-int advisory key spaces are distinct; the two-int form is used consistently, and frame/lifecycle writers share this namespace and stripe pool. It acquires no more than 64 DATA-1.4 advisory locks per transaction, even for a 5,000-event frame or 10,000-event lifecycle batch. A collision between entities or IDs is safe serialization, not an identity collision. Stripe contention may reduce parallelism, while disjoint stripe sets proceed independently; correctness never relies on a stripe being collision-free.

The lock roots covered by stripe derivation are:

```text
raw frame ID
result ID
event IDs
failure IDs
lifecycle batch/raw/event IDs
instrument-set digests
```

Acceptance proves that unrelated one-bigint locks and two-int locks in other namespaces cannot alias this namespace; the same DATA-1.4 identity always derives the same `0..63` stripe; frame and lifecycle roots sharing a stripe serialize; no transaction acquires more than 64 DATA-1.4 locks; `pg_locks` evidence exposes the frozen namespace/stripe pair; acquisition is numeric stripe order; and duplicate stripes are acquired once.

The maximum lock count is therefore 64, fitting the acceptance PostgreSQL configuration without making lock-table use proportional to input rows. Checkpoint evidence records `show max_locks_per_transaction`, the actual maximum stripe locks used by boundary fixtures, `pg_locks` or equivalent repository-owned measurements, and contention/throughput results. Every writer acquires the complete sorted stripe set before insert/compare, preventing deadlock between overlapping aggregates.

Bulk operations use a 60,000-parameter budget, below PostgreSQL's 65,535 protocol limit:

```text
insert_chunk = max(1, min(1000, floor(60000 / parameters_per_row)))
fetch_chunk  = 1000 IDs or the lower query-specific parameter bound
```

For row family `f`, round trips are bounded by prevalidation/catalogue resolution plus:

```text
ceil(n_f / fetch_chunk)
+ ceil(missing_f / insert_chunk)
+ ceil(n_f / fetch_chunk)
```

for prefetch, insert, and compare/readback. Memberships use the same formula. A 5,000-event single-subtype frame therefore uses five chunks per registry/subtype/membership phase, not 5,000 awaited cycles. Row families are processed in a frozen order.

After locks and prefetch, targeted `ON CONFLICT (primary_key) DO NOTHING RETURNING` is permitted; non-returned IDs are batch-fetched and completely compared. All deterministic uniqueness roots are striped and locked. A non-target unique/check/FK error indicates a bypass, corruption, or design defect; it is not handled inside the aborted transaction, and the entire UoW rolls back as a named integrity failure. SQLSTATE `40001`/`40P01` maps to `MarketEventConcurrencyError`; the application may recreate the whole UoW and retry an immutable command at most twice. Tests use barriers and advisory locks, never sleeps.

Different raw frames that converge on one event ID both lock that event. The second writer compares raw provenance and raises `NormalizedEventIdentityConflictError`; it cannot abort midway or create shared ambiguous membership.

## 19. Referential integrity

- Result to raw frame: real FK.
- Observation to raw frame: real FK.
- Result membership to matching result/raw and event/raw: composite real FKs.
- Quote economic subject to `market_instruments`: real FK.
- Quote semantic version/mapping/catalogue IDs: real FKs.
- Quote temporal IDs: real composite FKs after migration adds unique `(record_id, semantic_id)` constraints to `provider_mapping_records`, `instrument_version_records`, and `catalogue_version_records`.
- Mapping/provider/key/version and version/instrument/catalogue relationships: existing semantic FKs plus composite equality constraints/triggers.
- Failure to result/raw: real FKs.
- Common normalized lifecycle registry to raw lifecycle, each typed subtype to the registry, subscription subtype to instrument set, and memberships to batch/registry: real FKs. No single membership FK targets different tables by `lifecycle_kind`.
- Provider schema, capture session/scope, source file/record, and lifecycle scopes remain bounded opaque historical evidence.
- Subscription keys are evidence and are not provider-mapping FKs because attempted subscriptions may contain unknown keys.

The complete referenced-key inventory is frozen as follows:

| Referencing columns | Referenced columns | Required referenced key |
|---|---|---|
| `market_normalization_results.raw_event_id` | `raw_market_frames.raw_event_id` | raw PK |
| `(market_normalization_results.result_id, raw_event_id)` | result table | `UNIQUE(result_id, raw_event_id)` |
| `market_observations.raw_event_id` | `raw_market_frames.raw_event_id` | raw PK |
| `(market_observations.event_id, raw_event_id)` | observation table | `UNIQUE(event_id, raw_event_id)` |
| `(result_events.result_id, raw_event_id)` | result table | `UNIQUE(result_id, raw_event_id)` |
| `(result_events.event_id, raw_event_id)` | observation table | `UNIQUE(event_id, raw_event_id)` |
| `(result_failures.result_id, raw_event_id)` | result table | `UNIQUE(result_id, raw_event_id)` |
| `(result_failures.failure_id, result_id, raw_event_id)` | failure table | `UNIQUE(failure_id, result_id, raw_event_id)` |
| `(batch_events.batch_id, lifecycle_kind)` | lifecycle batch | `UNIQUE(batch_id, lifecycle_kind)` |
| `(batch_events.raw_event_id, lifecycle_kind)` | raw lifecycle | `UNIQUE(raw_event_id, lifecycle_kind)` |
| `(batch_observations.batch_id, lifecycle_kind)` | lifecycle batch | `UNIQUE(batch_id, lifecycle_kind)` |
| `(batch_observations.event_id, lifecycle_kind)` | `provider_lifecycle_observations` | `UNIQUE(event_id, lifecycle_kind)` |
| `provider_lifecycle_observations.raw_event_id` | `raw_provider_lifecycle_events.raw_event_id` | raw PK (plus kind equality check) |
| `provider_connection_lifecycle_observations.event_id` | `provider_lifecycle_observations.event_id` | subtype PK/FK; kind constant `connection` |
| `provider_subscription_lifecycle_observations.event_id` | `provider_lifecycle_observations.event_id` | subtype PK/FK; kind constant `subscription` |
| `provider_subscription_lifecycle_observations.instrument_keys_digest` | `provider_subscription_instrument_sets.instrument_keys_digest` | set PK |
| `(provider_mapping_record_id, provider_mapping_id)` | provider mapping records | `UNIQUE(record_id, mapping_id)` with semantic equality check |
| `(contract_version_record_id, contract_version_id)` | instrument version records | `UNIQUE(record_id, version_id)` with semantic equality check |
| `(catalogue_version_record_id, catalogue_version_id)` | catalogue version records | `UNIQUE(record_id, catalogue_version_id)` with semantic equality check |

Migration acceptance inspects this complete matrix from PostgreSQL catalogs; a missing referenced unique key is a schema failure, not an implementation detail.

The lifecycle-specific PK/unique/FK matrix is also frozen:

| Table | Primary key | Additional unique keys | Foreign keys |
|---|---|---|---|
| `provider_lifecycle_batches` | `lifecycle_batch_id` | `(lifecycle_batch_id, lifecycle_kind)` | none |
| `raw_provider_lifecycle_events` | `raw_event_id` | `(raw_event_id, lifecycle_kind)` | immutable instrument set when subscription digest is present |
| `provider_lifecycle_observations` | `event_id` | `(event_id, lifecycle_kind)`; `(event_id, raw_event_id, lifecycle_kind)` | `(raw_event_id, lifecycle_kind)` to raw lifecycle unique key |
| `provider_connection_lifecycle_observations` | `event_id` | none beyond PK | `event_id` to common registry |
| `provider_subscription_lifecycle_observations` | `event_id` | none beyond PK | `event_id` to common registry; instrument-set digest to set PK |
| `provider_lifecycle_batch_events` | `(lifecycle_batch_id, input_ordinal)` | `(lifecycle_batch_id, raw_event_id, input_ordinal)` | batch-kind; raw-event-kind |
| `provider_lifecycle_batch_observations` | `(lifecycle_batch_id, event_ordinal)` | `(lifecycle_batch_id, event_id, lifecycle_kind)` | batch-kind; `(event_id, lifecycle_kind)` to common registry |
| `provider_subscription_instrument_sets` | `instrument_keys_digest` | none beyond PK | none |
| `provider_subscription_instrument_set_keys` | `(instrument_keys_digest, key_ordinal)` | `(instrument_keys_digest, provider_contract_key)` | instrument-set digest |

The subtype kind is a checked constant and deferred validation proves registry kind matches exactly one subtype; two subtype rows or a kind mismatch are rejected.

Every quote persists `provider_mapping_record_id`, `contract_version_record_id`, and `catalogue_version_record_id`. Catalogue temporal identity is required because `contract_version.catalogue_version_id` alone identifies semantic content, not the knowledge-state leaf visible at the resolution cutoff. Within the same UoW and exact event cutoffs, the service resolves all three states, requires their semantic values equal the embedded `ResolvedMarketSubjectV1`, requires the catalogue ID referenced by the version equal the resolved catalogue value, and stores all three record IDs.

Static fixture persistence must seed the corresponding catalogue semantic and temporal records first. Exact retry with any different record ID is a provenance collision. Restore verification includes these rows and point-in-time states.

## 20. Event correction model

DATA-1.4 persists `supersedes_event_id` only as exact payload evidence and requires:

```sql
CHECK (supersedes_event_id IS NULL)
```

There is no correction target FK, partial-successor index, cycle trigger, graph lock, or correction-write/read claim. DATA-1.3 emits only null. DATA-1.6 treats non-null as unsupported/corrupt. A later reviewed migration may relax the null check and add the complete graph/service/knowledge-time contract; DATA-1.4 does not reserve premature graph machinery.

## 21. Query ports

```text
get_raw_frame_metadata(raw_event_id)
get_raw_frame(raw_event_id)
get_result(raw_event_id, normalization_schema_version)
get_event(event_id, normalization_schema_version)
load_result_aggregate(result_id, normalization_schema_version, include_raw_bytes=True)
scan_raw_frames(provider, connection_session_id, source_order_scope_id,
                after_source_order, limit)
scan_normalization_results(normalization_schema_version, after_cursor, limit,
                           durable_as_of=None)
list_subject_observations(normalization_schema_version, subject_id, event_types,
                          market_as_of, known_as_of,
                          allow_historical_import, provider=None,
                          mapping_id=None, version_id=None,
                          durable_as_of=None, after_cursor=None, limit=...)
list_provider_status(normalization_schema_version, provider, segment,
                     market_as_of, known_as_of,
                     allow_historical_import, durable_as_of=None,
                     after_cursor=None, limit=...)
list_connection_lifecycle(normalization_schema_version, provider,
                          connection_session_id,
                          occurred_through, known_as_of,
                          durable_as_of=None, after_cursor=None, limit=...)
list_subscription_lifecycle(normalization_schema_version, provider,
                            connection_session_id,
                            subscription_scope_id, occurred_through,
                            known_as_of, durable_as_of=None,
                            after_cursor=None, limit=...)
```

Every strategy/research replay method requires exactly one `normalization_schema_version`, and the SQL filters both result and observation rows by it. A separately named `audit_results_across_schemas(...)` and `audit_observations_across_schemas(...)` may return multiple schemas only when the caller explicitly requests cross-schema audit; those methods order by schema first and are not DATA-1.5/1.6 strategy inputs. Result lookup no longer accepts implementation version. Every exact read validates the canonical label for the selected schema. Pagination cursors contain schema version, the complete stable order tuple, and query mode. No port applies quality eligibility, returns latest eligible quotes, or constructs an option chain.

## 22. Replay ordering

- Capture scope order: caller names provider, connection session, and source-order scope; order `(source_order, raw_event_id)`.
- Event knowledge order: `(normalization_schema_version, available_at, source_order_scope_id, source_order, event_id)` after the required schema and epistemic predicates.
- Optional durable audit order: `(normalization_schema_version, persistence_recorded_at, result_id, event_ordinal, event_id)` only when the caller explicitly requests durable audit.
- Provider-time order: `(normalization_schema_version, provider_timestamp, available_at, source_order_scope_id, source_order, event_id)`.
- Lifecycle scope order: `(source_order, raw_event_id)` within the named source scope; original batch replay uses input ordinal.

There is no global source order across scopes/connections. Provider sequence remains null. Equal times use listed deterministic tie-breakers. Equal event IDs with different rows are corruption, not an ordering tie.

## 23. Point-in-time read predicates

Quote observation reads join committed result membership and the three exact temporal records. The joins prove referential integrity; the application/mapping layer verifies that each stored record was the selected leaf at the observation's original resolution cutoffs. Later successors are not used as a new visibility predicate:

```sql
WHERE o.economic_subject_id = :subject_id
  AND o.event_type = ANY(:event_types)
  AND o.normalization_schema_version = :schema_version
  AND r.normalization_schema_version = :schema_version
  AND o.provider_timestamp <= :market_as_of
  AND o.available_at <= :known_as_of
  AND o.resolution_market_as_of <= :market_as_of
  AND o.resolution_known_as_of <= :known_as_of
  AND (:allow_historical_import OR o.availability_basis <> 'historical_import')
  AND (:provider IS NULL OR o.provider = :provider)
  AND (:mapping_id IS NULL OR o.provider_mapping_id = :mapping_id)
  AND (:version_id IS NULL OR o.contract_version_id = :version_id)
  AND (:durable_as_of IS NULL OR r.persistence_recorded_at <= :durable_as_of)
ORDER BY o.normalization_schema_version, o.provider_timestamp, o.available_at,
         o.source_order_scope_id, o.source_order, o.event_id
```

Status uses provider timestamp, availability, basis, and optional durable cutoff but no catalogue predicates. Lifecycle uses occurrence as market/event cutoff, availability as knowledge cutoff, and optional batch durable cutoff. `known_as_of` is mandatory for point-in-time methods. Historical imports require explicit opt-in and are marked in returned query metadata. Physical row presence is naturally limited by the transaction snapshot; database insertion latency is not silently folded into market knowledge.

Status and lifecycle SQL add `normalization_schema_version = :schema_version` to their common-row predicates. Result scans add the same schema predicate. A cross-schema audit explicitly projects `normalization_schema_version` and orders by `(normalization_schema_version, ...)`; it is never used as the DATA-1.5/1.6 strategy/research read path. Query construction rejects an omitted schema version rather than defaulting to the newest or mixing schemas.

## 24. Failed and partial result persistence

Malformed frames with no decoded response type persist raw bytes, a failed result, and one frame failure. A frame failure permits no accepted event or entry failure. A decoded entry-only failure may have zero events and retains every entry diagnostic. Partial results persist accepted observations and failures atomically. Complete results persist zero failures.

Zero counts are accepted only when `FrameNormalizationResultV1` reconstruction permits them. Exact retry compares the entire outcome. Changed status, declarations, counts, failure, canonical label, or hash under one result ID is a result/failure collision. No failure is discarded because no observation exists.

## 25. Hash verification after persistence

Every aggregate read must:

1. load exact raw bytes, recompute frame hash, reconstruct `RawMarketFrameV1`, and verify raw identity;
2. recompute revised result identity and verify the one canonical implementation label for its schema;
3. reconstruct each typed observation and verify event identity and raw provenance;
4. verify exact event and failure ordinals plus all declaration arrays;
5. reconstruct failures and `FrameNormalizationResultV1`, verifying full/adopted hashes;
6. load mapping/version/catalogue semantic and temporal rows and require embedded subject values plus exact cutoffs resolve to the stored record IDs;
7. verify lifecycle raw/event IDs, set sorted keys/count/digest, batch order, duplicate positions, and sequence hashes.

Every mapped semantic clock is additionally checked as finite, timezone-aware UTC-compatible data; a database `infinity` or `-infinity` value is durable corruption even if an out-of-band write bypassed the database check.

Write-time immutable reuse differences raise named collision exceptions. Durable readback inconsistency, missing FKs, impossible temporal resolution, typed/JSON mismatch, or hash drift raises `MarketEventDurableCorruptionError` and returns no partial object.

## 26. Migration `20260804_04`

- Filename: `backend/alembic/versions/20260804_04_append_only_market_events.py`.
- Revision/down revision: `20260804_04` / `20260804_03`.
- Upgrade order: add temporal `(record_id, semantic_id)` unique constraints; create append-only `UPDATE`/`DELETE` row-trigger and `TRUNCATE` statement-trigger functions; raw frame; immutable set/set-key tables; result root; common observations and quote/status subtypes; failures/memberships; lifecycle batch/raw/normalized/membership tables; indexes; deferred aggregate integrity triggers; append-only triggers.
- Use existing naming conventions and `op.f`; no semantic timestamp has a server-time default.
- Source order is `BIGINT`; byte constraints reflect Phase A; raw frame bytes use the accepted one-byte lower bound; all quote price NUMERIC columns reject NaN and infinities; every semantic TIMESTAMPTZ rejects both PostgreSQL infinities; the common lifecycle registry and concrete subtype FKs are created; no correction FK/index exists.
- Upgrade is additive with no imagined backfill.

Downgrade first checks every DATA-1.4 table is empty. Any durable history raises a precise refusal even in ordinary owner sessions. With empty tables, it drops children, integrity/append-only triggers, tables, function, and added temporal composite unique constraints in reverse order. There is no destructive override in the migration. Empty upgrade/downgrade/re-upgrade tests obtain an empty database only through the existing guarded database recreation/bootstrap boundary; they never `DELETE` or `TRUNCATE` accepted history in place. Direct SQL tests prove the runtime role and owner path both reject `TRUNCATE` on durable tables during normal operation.

## 27. Restore verification

Extend `DURABLE_MODELS`, canonical durable snapshots, and guarded restore fixtures for every new table and added temporal constraint. The fixture contains complete, partial, frame-failed, and entry-only-failed aggregates; a 5,000-event/key stress shape where practical; exact retries; Decimal exponent cases; binary raw bytes; temporal catalogue histories with later-known leaves; connection/reconnect lifecycle; interleaved subscription scopes; exact duplicates; and immutable set reuse.

Using server/client `17.10`, compare source/restored Alembic revision, table counts, canonical row digests, raw-byte hashes, result/event/failure hashes, exact temporal record IDs, representative aggregate reconstruction, point-in-time reads before/after temporal knowledge edges, lifecycle ordering, set digests, constraints, finite timestamp behavior, and append-only triggers. Preserve source/target non-aliasing, sentinels, the DATA-1.4 two-int advisory-lock namespace, credential redaction, public-schema-only restore, and dump cleanup.

## 28. Volume and performance assumptions

Planning hypotheses, not acceptance promises:

| Input | Planning | Stress boundary |
|---|---:|---:|
| Frames/second | 2 | 10 |
| Events/frame | 100 | 5,000 |
| Average/max frame | 64 KiB | 16 MiB |
| Session | 6.25 hours | 6.25 hours |

The planning case is roughly 45,000 frames, 4.5 million observations, and 2.75 GiB raw bytes/session before TOAST/backup compression. Initial acceptance records transaction duration distributions, chunk counts, query plans, row/index sizes, dump size/time, and restore time on the declared environment. It proves the parameter-budget formula and absence of per-row SQL cycles.

No portable p95 threshold is frozen before measurement. After the first accepted baseline, documentation will freeze regression budgets tied to that hardware/container profile. Partitioning review triggers at 100 million rows in a primary event table, 30-day indexes above 50 GiB, or demonstrated query/maintenance pressure after query/index correction. External raw storage review triggers at raw growth above 250 GiB/month, backup above two hours, or restore above four hours. Neither is implemented now.

## 29. Retention boundary

DATA-1.4 deletes nothing automatically. Raw bytes, results, observations, failures, temporal provenance, and lifecycle history share the append-only replay boundary. Deleting bytes prevents decoder replay; deleting failures or memberships falsifies history.

Future retention requires an independently approved archive contract with immutable content addressing, exact retrieval, availability guarantees, references, and restore proof before any deletion migration. Until then storage growth is unbounded, so operational use is limited to bounded offline/paper datasets with monitored capacity.

## 30. Security

- Raw provider payloads and backups are sensitive; neither raw bytes nor canonical payloads are logged.
- Existing DATA-1.3 token, URL, account/user, provider-key, segment, opaque-ID, and redacted-reason controls remain authoritative.
- Exceptions expose deterministic IDs and controlled categories, not bytes, payload JSON, DSNs, or full provider keys.
- Runtime roles use least privilege; migration/destructive roles remain separate.
- Frame, lifecycle batch, source-order, identifier, key-count, mode, and SQL parameter limits are enforced before SQL and where possible in constraints.
- No decompression, pickle, dynamic SQL identifier, provider network call, or shell interpolation enters persistence.
- SQL uses bound parameters and owned static table/column names.
- Acceptance scans secrets, dumps/backups, caches/build output, and unexpected binaries; only inventoried synthetic fixtures are permitted.

## 31. Observability

Structured summaries contain only:

```text
raw_event_id / lifecycle_batch_id
frame_content_hash
result_id and schema version
result status
event/failure/input/duplicate counts
inserted/idempotent counts by row family
bulk chunk and round-trip counts
persistence_recorded_at
transaction duration
database revision
collision/integrity category
DATA-1.4 advisory-lock namespace and stripe-count summary
```

They never contain bytes, canonical payloads, provider keys, source paths, DSNs, or PostgreSQL error detail that may echo values. Existing logging is sufficient; no metrics/logging dependency is added. Measurements gathered in section 28 become the evidence for a later regression budget.

## 32. CLI boundary

Add one offline CLI with frame and lifecycle subcommands. It reuses DATA-1.3 fixture loaders/normalizers, persists through the services, reads back, and verifies exact hashes/order/provenance. It supports exact retry and a deliberate collision fixture, requires a named environment variable containing a `postgresql+asyncpg` URL, never contacts Upstox, and never logs raw bytes.

An injected `--persistence-recorded-at` is accepted only with `--deterministic-test-clock` against the exact guarded disposable database. Collision mode succeeds only when the intended collision is rejected and row counts/digests are unchanged.

| Exit | Meaning |
|---:|---|
| 0 | inserted or exact-idempotent and fully verified |
| 2 | argument/manifest/configuration error |
| 3 | schema or fixture ownership/hash error |
| 4 | raw capture/lifecycle identity collision |
| 5 | result/event/failure/set/provenance collision |
| 6 | durable corruption, reconciliation, or hash failure |
| 7 | database unavailable or bounded concurrency retries exhausted |
| 8 | unsafe database/test-clock/collision-mode refusal |

Output is canonical JSON containing only safe summaries.

## 33. Adversarial scenario matrix

| Scenario | Required behavior |
|---|---|
| Exact aggregate inserted twice | Idempotent; same readback and stored audit time |
| Concurrent exact inserts | One durable aggregate; both callers resolve safely |
| Same raw ID, different bytes | Reject and roll back |
| Same frame hash, different capture identity | Persist distinct captures |
| Same event ID, changed quote field | Reject and roll back |
| Different raw captures present the same `event_id` through forged/corrupt input | Sorted event lock; collision rejection and aggregate rollback without partial rows |
| Same result identity, different implementation label | Reject; schema permits one canonical label |
| Same schema/implementation, changed output | Reject; material change requires new schema |
| Same result identity, changed failure | Reject |
| Retry resolves different mapping/version record | Provenance collision |
| Retry resolves different catalogue record | Provenance collision |
| Semantic subject differs from temporal state | Reject before write/FK validation |
| Static fixture lacks temporal rows | Reject referentially; no partial aggregate |
| Partial valid/failed subjects | Persist both atomically |
| Frame failure, zero decoded | Persist frame failure and no events |
| Entry-only failed result | Persist every failure |
| Event/failure ordinal gap or duplicate | Prevalidation/deferred integrity rejects |
| Event refers to another raw frame | Composite FK/compare rejects |
| Invalid Decimal introduced outside repository | Read fails closed as durable corruption |
| Raw bytes changed without matching hash | Append-only trigger blocks; read hash also fails |
| Status basis disagrees with raw capture | Reject |
| Quote basis disagrees with event-time basis | Reject |
| Event available after `known_as_of` | Exclude |
| Catalogue record known after `known_as_of` | Exclude |
| Subject resolution cutoff after query cutoff | Exclude |
| Aggregate persisted after `known_as_of`, no durable cutoff | Included if event/catalogue epistemic predicates pass |
| Aggregate after explicit `durable_as_of` | Exclude from durable-audit query |
| Historical import without opt-in | Exclude and report limitation |
| Non-null correction edge | `CHECK IS NULL` rejects; no graph support claimed |
| Crash before commit | No visible or durable partial rows |
| Retry after uncertain commit | Lock/load/compare resolves exact commit idempotently |
| Statement fails mid-bulk insert | Whole UoW rolls back; no use of aborted transaction |
| 5,000-event frame | Bounded chunks; no per-row awaited SQL cycle; no more than 64 advisory locks |
| 10,000 lifecycle events | Bounded chunks; no more than 64 advisory locks |
| Concurrent aggregates share one stripe | Serialize safely; exact/collision comparison still decides outcome |
| Existing non-DATA-1.4 advisory lock uses bigint key 0 | No alias with DATA-1.4 two-int namespace/stripe lock |
| Existing two-int lock uses another namespace and same stripe | No alias |
| Same DATA-1.4 namespace and stripe | Serializes |
| Single lifecycle membership FK points to two subtype tables | Forbidden design; catalog has no polymorphic FK claim |
| Connection normalized membership | Concrete FK succeeds |
| Subscription normalized membership | Concrete FK succeeds |
| Registry kind and subtype mismatch | Deferred integrity rejects |
| Two lifecycle subtype rows for one registry event | Reject |
| Concurrent aggregates have disjoint stripes | May proceed independently subject to ordinary database resources |
| Statement parameter count near limit | Chunk formula stays below 60,000 parameters |
| Two aggregates derive overlapping stripes in reverse input order | Numeric stripe order prevents deadlock |
| Instrument set reused across transitions | One set/key copy; observations reference digest |
| Instrument set digest reused with changed keys | Digest collision and batch rollback |
| `full_d30` with 51 keys | Upstream/direct durable validation rejects |
| Unsubscribe without mode and 5,000 keys | Accepted at global boundary |
| Source order `2**63 - 1` | Round-trips exactly through `BIGINT` |
| Source order `2**63` or boolean | Rejected before SQL |
| 512-byte opaque/key value | Accepted unchanged |
| Oversized multibyte opaque/key value | Rejected without truncation/normalization |
| 10,000 lifecycle events | Accepted at boundary |
| 10,001 lifecycle events | Rejected before persistence |
| 16 MiB frame | Accepted at boundary |
| Frame above bound | Rejected before UoW |
| Provider sequence absent | Null preserved; no global sequence invented |
| Same source order in different scope | Allowed |
| Same source order twice in one scope | Deterministic identity/uniqueness collision |
| Lifecycle exact duplicate | One raw/event row; all duplicate positions preserved |
| Interleaved subscription scopes | Validated and replayed independently |
| Reversed physical insert order | Identical ordered domain reconstruction |
| Schema 1 and schema 2 coexist | Strategy query requires one schema; cross-schema results are audit-only |
| Query omits schema version | Domain/API construction rejects; no newest-schema default |
| Composite FK referenced key absent | Migration/catalog inspection fails before acceptance |
| Direct UPDATE/DELETE/TRUNCATE | Corresponding append-only trigger/privilege rejects |
| Zero-byte raw frame | Rejected before persistence because accepted `RawMarketFrameV1` rejects empty bytes |
| Later catalogue successor | Original temporal leaves remain immutable provenance; no silent event reassignment |
| PostgreSQL NUMERIC NaN/Infinity | Database finite-value check and row mapping reject |
| `TIMESTAMPTZ 'infinity'` | Check rejects |
| `TIMESTAMPTZ '-infinity'` | Check rejects |
| Nullable optional clock is NULL | Accepted where domain permits |
| Database restored | Same bytes, rows, hashes, provenance, and order |
| Downgrade with durable history | Refuses without dropping data |
| Final evidence uses host v18 clients | Rejected; container v17 tools required |

## 34. Proof obligations

Acceptance provides executable proofs of:

1. exact retry idempotency, including stored audit time;
2. every named identity/content/provenance collision;
3. frame and lifecycle aggregate atomicity;
4. concurrent identical insertion;
5. concurrent conflicting insertion, including cross-frame event convergence;
6. deterministic event/failure/lifecycle order;
7. no mutation of DATA-1.3 identities or hashes;
8. exact Decimal, quantity, OI, and signed-`BIGINT` round trips;
9. UTC/timezone preservation and honest persistence-time semantics;
10. no future event or catalogue knowledge leakage;
11. no future subject-resolution cutoff leakage;
12. optional `durable_as_of` behavior remains distinct from `known_as_of`;
13. explicit historical-import opt-in;
14. full/adopted hashes survive row/domain round trip;
15. exact raw bytes survive PostgreSQL dump/restore;
16. complete/partial/frame-failed/entry-failed outcomes survive;
17. lifecycle order, duplicates, mode bounds, and set digests survive;
18. correction writes are safely unavailable with no premature graph schema;
19. upgrade, empty downgrade, re-upgrade, and non-empty downgrade refusal;
20. no DATA-1.3 or LIVE-RV regression;
21. no quality, chain, analytics, Redis, live wiring, or execution logic;
22. typed/canonical-payload equality and complete read integrity;
23. direct UPDATE, DELETE, and TRUNCATE refusal;
24. result visibility only at aggregate commit;
25. bounded bulk round trips and parameter counts for 5,000 events;
26. deterministic 64-stripe lock derivation, maximum lock count, disjoint/overlapping behavior, and deadlock avoidance;
27. exact mapping/version/catalogue temporal provenance at original event cutoffs, including later-successor replay;
28. status/quote availability-basis projection correctness;
29. exact schema-isolated strategy reads and explicitly ordered cross-schema audits;
30. complete composite-FK/unique-key inventory validated against PostgreSQL catalogs;
31. direct `UPDATE`, `DELETE`, and `TRUNCATE` rejection and guarded empty-database reset;
32. accepted one-byte raw-frame lower bound and zero-byte rejection proof;
33. database finite-NUMERIC checks for NaN and both infinities;
34. two-int namespace isolation, fixed namespace derivation, sorted unique stripe acquisition, and `pg_locks` key evidence;
35. executable lifecycle registry/subtype FKs, kind checks, and catalog inventory with no polymorphic FK;
36. database rejection of TIMESTAMPTZ `infinity` and `-infinity`, nullable clocks, and finite UTC mapping.

## 35. Test plan

### Pure tests

Revised result/batch IDs; canonical schema labels; failure identity; lock-key derivation/order; chunk calculation; mappings; typed projections; canonical payloads; collision comparison; Decimal/`BIGINT`/UTC round trips; availability projection; temporal provenance comparison; set canonicalization/digest; and every upstream bound. Zero skips.

### PostgreSQL integration and concurrency

All repositories and query ports; frame/lifecycle write/read; complete/partial/failed results; idempotency; all collision classes; all-root locks; two-int namespace isolation; cross-frame shared event conflict; 5,000-event chunking; uncertain commit; point-in-time event/catalogue/durable cutoffs; static fixture temporal seeding; set reuse/collision; executable lifecycle registry/subtype FKs; append-only triggers; malformed direct rows including TIMESTAMPTZ infinities; UoW finality. Acceptance-critical runs have zero skips.

### Migration

Fresh upgrade, `20260804_03 -> 20260804_04`, schema/constraint/index inspection, empty downgrade/re-upgrade, non-empty downgrade refusal, and Alembic drift. Zero skips on PostgreSQL 17.

### Restore

Guarded version-17 dump/restore; counts/digests; raw bytes; result hashes; temporal record IDs/reads; representative epistemic and durable-audit scans; lifecycle/set order; constraints/triggers. Zero skips.

### Regression

Complete DATA-1.3 and DATA-1.2 suites, fixture identity/hash verification, LIVE-RV, full backend, frontend lint/build, compilation, lock check, diff hygiene, cache/binary/secret scan.

## 36. Acceptance environment

Required:

```text
PostgreSQL server 17.x
psql 17.x
pg_dump 17.x
pg_restore 17.x
database quantkynd_test
restore database quantkynd_restore
purpose-specific disposable-database sentinels
explicit destructive-test opt-in
loopback restriction
database advisory locks
```

Environment:

```text
DATABASE_URL
DATABASE_RESTORE_TEST_URL
DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true
DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test
DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore
DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false
CATALOGUE_ARTIFACT_ROOT
```

The repository container currently supplies server and all client tools `17.10`; final commands use `docker compose exec -T postgres` or another explicitly recorded version-17 client path, never the host 18.4 binaries. Refuse missing/non-asyncpg URLs, exact-name/sentinel/purpose mismatch, non-local targets without explicit approval, source/target aliasing, advisory contention, wrong tool versions, or any acceptance-critical skip.

## 37. Acceptance commands

From `backend`, after exporting the declared guarded environment:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/market_data/persistence tests/test_persist_market_event_fixture_cli.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/persistence/test_market_event_repositories.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/persistence/test_market_event_concurrency.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/persistence/test_market_event_migration.py
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic heads
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.persist_market_event_fixture frame --frame tests/fixtures/upstox/market_feed_v3/nifty-option-live-market-ff-d5.bin --capture-manifest tests/fixtures/upstox/market_feed_v3/nifty-option-live-market-ff-d5.capture.json --subject-manifest tests/fixtures/upstox/market_feed_v3/subjects.json --database-url-env DATABASE_URL --verify-readback --repeat-exact
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.persist_market_event_fixture lifecycle --fixture tests/fixtures/upstox/market_feed_v3/subscription-lifecycle.json --database-url-env DATABASE_URL --verify-readback --repeat-exact
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.persist_market_event_fixture frame --collision-frame tests/fixtures/upstox/market_feed_v3/data-1.4-raw-collision.bin --collision-capture-manifest tests/fixtures/upstox/market_feed_v3/data-1.4-raw-collision.capture.json --database-url-env DATABASE_URL --verify-collision-fixture
UV_CACHE_DIR=/tmp/uv-cache uv run python tools/verify_market_event_fixtures.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -ra
UV_CACHE_DIR=/tmp/uv-cache uv lock --check
```

Version-17 tool proof and guarded database checks:

```bash
docker compose exec -T postgres psql --version
docker compose exec -T postgres pg_dump --version
docker compose exec -T postgres pg_restore --version
docker compose exec -T postgres psql -U quantkynd -d quantkynd_test -Atc 'show server_version'
docker compose exec -T postgres psql -U quantkynd -d quantkynd_test -Atc 'show max_locks_per_transaction'
```

From `frontend`:

```bash
pnpm lint
pnpm build
```

From repository root:

```bash
git diff --check
git status --short
git merge-base --is-ancestor a6bd58fb427eb78a57ac0ee6b573ee8842e47428 HEAD
git rev-parse HEAD
git rev-parse origin/master
git rev-parse origin/feature/append-only-market-event-persistence
git ls-files | rg '(^|/)(__pycache__|.*\.pyc|node_modules|dist|.*\.dump|.*\.backup)(/|$)' || true
git ls-files -z | xargs -0 rg -n --hidden '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}|authorizedRedirectUri|wss://.*token=)' || true
```

Record exact counts, zero skips, versions, revision, chunk/round-trip evidence, restore/raw digests, CLI summaries, and final clean status. The pattern check is not described as a complete secret scanner unless a repository-owned scanner exists.

## 38. Mandatory mid-milestone checkpoint

Implementation authorization, if later granted, must stop after:

1. durable domain commands/IDs/errors/ports, including result identity and canonical labels;
2. all SQLAlchemy rows/mappings and exact temporal-provenance projections;
3. migration `20260804_04` with `BIGINT`, normalized sets, correction null-check, constraints, and triggers;
4. UoW exposure, all-root lock derivation, and bulk chunk planner;
5. one complete frame aggregate write/read path;
6. focused pure/mapping/migration/PostgreSQL/concurrency tests;
7. complete DATA-1.3 regression.

Checkpoint evidence must record SHA/files, generated schema inventory, Alembic current/check, `show max_locks_per_transaction`, the frozen DATA-1.4 namespace and exact two-int SQL form, actual maximum advisory locks used by 5,000-event and 10,000-event boundary fixtures, `pg_locks` or an equivalent repository-owned lock measurement, zero-skip results, schema-version query isolation, the complete PK/unique/FK inventory including registry/subtype lifecycle targets, inserted/exact-retry aggregate, deliberate raw/result/event/provenance collisions, readback bytes/hashes/temporal IDs, direct update/delete/truncate refusal, finite-NUMERIC and TIMESTAMPTZ-infinity hostile rows, the accepted one-byte raw-frame lower-bound proof, later-catalogue-successor provenance proof, bounded bulk round trips for a large frame, and all deviations.

Stop before complete lifecycle adapters, full replay CLI, complete concurrency/adversarial matrix, dump/restore completion, broad documentation, and final evidence. Independent checkpoint approval is required to continue.

## 39. Documentation plan

- `docs/design.md`: durable aggregate boundary, temporal provenance, clocks, bulk transactions, lock order.
- `docs/data-models.md`: every table, identity/version matrix, availability projection, membership, set normalization, correction deferral.
- `docs/dependencies.md`: record that no dependency was added, or document any separately approved change with ownership/removal criteria.
- `docs/environment.md`: guarded CLI/database variables and version-17 client path.
- `docs/testing.md`: mapping, bulk, concurrency, migration, epistemic/durable reads, replay, restore gates.
- `docs/performance.md`: measured baseline, chunk/round-trip evidence, later regression budget and review thresholds.
- `docs/security.md`: raw bytes/backups, bounds, logging, roles, denial-of-service controls.
- `docs/observability.md`: safe summaries, chunk counts, collision/integrity categories.
- `docs/plan/options-market-infrastructure.md`: DATA-1.4 status and narrow scope.
- `docs/plan/roadmap.md`: DATA-1 remains active after this persistence slice.
- `docs/plan/acceptance-gates.md`: zero-skip persistence/concurrency/restore sub-gate and checkpoint.
- `docs/implementation/DATA-1.4-append-only-market-event-persistence.md`: implementation evidence only after authorized work and all gates.

No HTTP API is proposed, so `docs/api.md` records no contract change. If implementation changes that fact, it must stop and return to design review.

## 40. Unresolved questions and recommendation

### Blocker-level questions

None. The Phase-A bounds are merged, all identity/time/provenance/storage/transaction/concurrency/migration/replay decisions are frozen, and the required version-17 environment is available.

### Non-blocking operational measurement

The only deliberately open item is the numerical performance regression budget. Alternatives are to invent a portable p95 now or measure the accepted environment first. An invented threshold could reject correct bulk persistence or conceal hardware-specific regressions; measurement has no correctness impact because parameter, frame, event, and transaction bounds are already frozen. Recommendation: capture the section 28 baseline during acceptance, document hardware/container characteristics, and freeze subsequent regression thresholds against that evidence before live wiring.

### Frozen recommendation

Approve this proposal for implementation only after independent review confirms every Phase B amendment is represented consistently. If approved, begin from this branch, implement migration `20260804_04` and the checkpoint scope only, then stop at section 38. DATA-1.4 remains paper/offline, append-only, and independent of quality policy, chain construction, Redis, live subscriptions, frontend/API changes, strategy, execution, and live capital.
