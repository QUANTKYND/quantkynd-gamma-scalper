# Codex Task — DATA-1.0 Point-in-Time Semantics and Identity Freeze

## Repository

- Repository: `https://github.com/QUANTKYND/quantkynd-gamma-scalper`
- Merged baseline branch: `master`
- Required starting commit: `f8b7d89587752189d81d402bec45cba977349588`
- Create branch: `feature/data-1-point-in-time-semantics`

The branch has already been created from the verified master baseline. Before making implementation changes, verify:

git branch --show-current
git rev-parse HEAD
git status --short
git merge-base --is-ancestor f8b7d89587752189d81d402bec45cba977349588 HEAD

At task start, the branch and SHA must resolve to:

feature/data-1-point-in-time-semantics
f8b7d89587752189d81d402bec45cba977349588

The only expected pre-existing untracked path is:

docs/implementation/DATA-1.0-point-in-time-semantics-and-identity-freeze.md

Treat that document as an acceptance-evidence placeholder. Do not record successful checks, an ending SHA, or completion claims until the implementation and verification commands have actually completed.

Do not continue from a different baseline without documenting and obtaining approval for the change.

---

## Milestone

`DATA-1.0 — Point-in-time semantics and identity freeze`

This is the first, deliberately narrow slice of `DATA-1 — Point-in-time option market data infrastructure`.

The purpose is to freeze the domain semantics that Postgres, catalogue ingestion, quote persistence, and chain reconstruction will later implement.

Do **not** add SQLAlchemy, Alembic, asyncpg, Postgres tables, live option subscriptions, IV calculation, Greeks, surfaces, strategy logic, or frontend work in this task.

---

## Why this task comes first

The existing plan correctly requires stable contract identity, validity intervals, append-only market events, explicit corrections, and deterministic historical chain reconstruction. Before persistence is implemented, the repository must explicitly distinguish:

1. the market or exchange time of an observation;
2. the time the observation became available to this system;
3. the time the record was persisted or superseded;
4. economic contract identity;
5. validity-bounded contract metadata;
6. provider-specific identifiers.

Without these distinctions, a historical query can accidentally use a future catalogue version, a later correction, or a provider mapping that did not exist at the decision timestamp.

---

## Mandatory reading

Read in this order before editing:

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
13. `docs/plan/roadmap.md`
14. `docs/plan/options-market-infrastructure.md`
15. `docs/plan/acceptance-gates.md`
16. relevant existing instrument, provider, strategy, simulation, hashing, and time/session code

Also inspect the accepted SIM-1.2.1 implementation and reuse existing canonical serialization, hashing, finite-value validation, timezone, and immutable-manifest conventions where applicable.

---

## Required architectural decisions

### 1. Separate the point-in-time clocks

Define and document the exact semantics of at least these fields:

- `exchange_timestamp`
  - Provider-reported market-event time.
  - UTC-aware in storage and domain objects.
- `available_at`
  - Earliest time the observation was eligible to influence this system.
  - For live events, normally derived from receipt time.
  - For historical imports without defensible original dissemination time, the limitation must be explicit.
- `recorded_at`
  - Time the normalized immutable record was persisted by QuantKYND.
- `superseded_at`
  - Optional system-time boundary for a record replaced by an explicit correction.
- `received_at`
  - Physical receipt time when available.
  - Must remain distinct from provider/exchange time.

Define the two point-in-time query modes:

- `market_as_of`
  - What market events had occurred by the exchange timestamp.
- `known_as_of`
  - What QuantKYND could actually have known by the decision timestamp.

Research replay must default to `known_as_of` whenever defensible availability timestamps exist. It must never silently claim knowledge-time validity for a backfilled dataset that lacks it.

### 2. Separate economic identity, contract versions, and provider mappings

Do not make a provider key, mutable display symbol, catalogue row, tick size, or lot size the sole identity of an economic option contract.

Freeze three concepts:

#### `OptionContractIdentity`

Stable economic identity, including only fields required to identify the derivative economically, such as:

- exchange or venue;
- underlying instrument identity;
- expiry exchange date;
- strike in canonical decimal units;
- option side;
- exercise style;
- settlement type;
- contract multiplier where economically identity-defining.

#### `OptionContractVersion`

Validity-bounded trading metadata, such as:

- contract identity reference;
- valid-from and valid-until;
- lot size;
- tick size;
- display symbol;
- trading status;
- catalogue version reference;
- recorded-at and supersession metadata.

#### `ProviderContractMapping`

Provider-specific mapping, such as:

- provider;
- provider contract key;
- contract-version reference;
- provider payload hash or source-row identity;
- effective interval;
- recorded-at and supersession metadata.

Apply the same separation where needed for futures and underlying instruments.

### 3. Deterministic identity and canonical serialization

Define canonical, deterministic identity material and hashing rules.

Requirements:

- No UUIDv4 may be used as the only reproducible identity for catalogue entities.
- Re-ingesting the same canonical catalogue fixture must produce the same identities.
- Provider mappings from different providers must be able to point to the same economic contract.
- Decimal values must be canonically serialized.
- Timestamps must be UTC-aware and canonically serialized.
- Unordered mappings and sets must not affect hashes.
- `created_at` or ingestion runtime metadata must not affect behavioral/economic identity hashes.

UUIDv5 or SHA-256-derived opaque IDs are acceptable if consistent with repository conventions.

### 4. Numeric and unit conventions

Freeze these conventions:

- Prices, strikes, tick sizes, multipliers, and monetary values use `Decimal`, never binary float, at durable/domain boundaries.
- Sizes and volume use explicitly documented units.
- Expiry is an exchange date, not an arbitrary timestamp.
- All timestamps are timezone-aware.
- Storage convention is UTC.
- NSE session interpretation is `Asia/Kolkata`.
- Optional fields are absent when unavailable; the normalizer must not invent values.

### 5. Append-only correction semantics

Define immutable record behavior:

- Raw and normalized observations are append-only.
- A correction creates a new record.
- The corrected record references the prior record through `supersedes_event_id` or an equivalent explicit relation.
- Rejection or quarantine never mutates the raw observation.
- Quality outcomes are versioned by `quality_policy_id` and `quality_policy_version`.
- A later quality-policy re-evaluation creates a new assessment rather than rewriting history.

### 6. Deterministic event identity

Define event identity and deduplication boundaries:

- Prefer provider event ID, trade ID, or provider sequence when semantically guaranteed.
- Do not collapse repeated identical quotes merely because all market fields match.
- Batch import idempotency must use a source-file identity plus source-row identity or another explicit ingestion key.
- A fallback content hash may support provenance, but must not be treated as proof that two separately transmitted events are the same event.

### 7. Chain reconstruction selection order

Document a deterministic quote tie-break order for a later `as_of` chain query. It should include, in order of semantic authority where present:

1. eligibility under contract and provider-mapping validity;
2. `exchange_timestamp <= market_as_of`;
3. `available_at <= known_as_of`;
4. accepted quality state under the requested policy version;
5. newest exchange timestamp;
6. provider sequence or event order where available;
7. received/available time;
8. stable event ID as the final deterministic tie-breaker.

The chain result must be deterministically sorted by expiry, strike, and option side.

---

## Domain implementation

Add a pure, persistence-independent domain slice using the repository's existing architectural conventions.

Expected concepts include:

- `UnderlyingInstrumentIdentity`
- `FuturesContractIdentity`
- `OptionContractIdentity`
- corresponding validity-bounded version types
- `ProviderContractMapping`
- `MarketEventTime`
- `PointInTimeQuery`
- `QuoteQualityDisposition`
- `DataQualityAssessment`
- `RawMarketObservationIdentity`
- `NormalizedMarketEventIdentity`

Exact names may differ if a clearer repository-consistent design is found.

Rules:

- Domain modules must not import FastAPI, SQLAlchemy, Alembic, asyncpg, Upstox SDK classes, Redis, or frontend schemas.
- Use immutable models where practical.
- Validate invariants at construction.
- Invalid values fail explicitly.
- No explanatory code comments; put prose in documentation.
- Reuse the repository's canonical hash implementation rather than creating a competing serializer.

---

## Documentation updates

Update all documents affected by the semantic freeze, including at minimum:

- `docs/data-models.md`
- `docs/design.md`
- `docs/conventions.md`
- `docs/testing.md`
- `docs/plan/options-market-infrastructure.md`
- `docs/plan/roadmap.md`
- `docs/plan/acceptance-gates.md`

Update `docs/dependencies.md` only to clarify that database dependencies remain deferred to the next DATA-1 slice. Do not add them in this task.

The documentation must explicitly state:

- which fields form economic identity;
- which fields are validity-bounded metadata;
- how provider mappings work;
- effective-time versus system/knowledge-time semantics;
- historical import limitations;
- correction and supersession semantics;
- deterministic chain quote selection;
- Decimal and timezone conventions.

---

## Required tests

Add focused tests for the pure domain semantics.

### Identity tests

- Same canonical option identity produces the same deterministic ID.
- Mapping order does not change the ID.
- Decimal textual variants representing the same value do not change the ID.
- A call and put never collide.
- Different expiries never collide.
- Different strikes never collide.
- Different providers can map to the same economic contract.
- Changing a provider key does not change economic contract identity.
- Changing a validity-bounded trading attribute creates a new contract version but not a new economic contract where appropriate.

### Time tests

- Naive timestamps are rejected.
- UTC normalization is deterministic.
- `available_at` cannot precede defensible source constraints where such constraints are present.
- Invalid validity intervals fail.
- A not-yet-effective contract version is not eligible.
- An expired/superseded contract version is not eligible.

### No-future-leakage tests

Construct fixtures in which:

- a contract is listed after the query timestamp;
- a provider mapping is corrected later;
- a quote is backfilled later;
- a quote is superseded later;
- a later quality-policy assessment changes disposition.

Prove that a `known_as_of` query cannot see any later information.

### Event identity tests

- Re-importing the same source row is idempotent.
- Two distinct transmissions with identical quote fields remain distinct when the provider supplies distinct sequence/event identity.
- A content hash alone does not force event deduplication.

### Serialization tests

- Canonical serialized output is stable.
- Hashes are stable across repeated runs.
- Unsupported/non-finite numeric input fails explicitly.

---

## Explicit non-goals

Do not implement:

- Postgres or any database schema;
- SQLAlchemy repositories;
- Alembic migrations;
- Upstox live option subscriptions;
- option-chain API endpoints;
- IV inversion changes;
- market-derived Greeks;
- smile or surface fitting;
- implied variance;
- EDGE-1;
- backtesting;
- paper orders;
- broker order placement;
- Redis;
- frontend screens.

The existing simulator must remain offline and deterministic.

---

## Acceptance criteria

The task is accepted only when:

1. the point-in-time clocks are explicit and non-ambiguous;
2. economic contract identity is separate from provider identity and validity-bounded trading metadata;
3. corrections and quality re-evaluations are append-only;
4. deterministic identities and canonical hashes are tested;
5. no-future-leakage fixtures pass;
6. Decimal and timezone conventions are enforced;
7. no database or live-market dependency has been introduced;
8. existing strategy and simulator behavior remains unchanged;
9. all backend tests pass;
10. frontend lint and build still pass if repository policy requires full-project verification;
11. `git diff --check` passes;
12. documentation is internally consistent;
13. an acceptance-evidence document is added under `docs/implementation/`.

---

## Required verification

Run the repository-standard checks. At minimum:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Also run any configured Python lint/type checks and:

```bash
cd ../frontend
npm run lint
npm run build
```

From the repository root:

```bash
git diff --check
git status --short
```

Do not claim a check passed unless it was actually run successfully.

---

## Acceptance evidence document

Create:

```text
docs/implementation/DATA-1.0-point-in-time-semantics.md
```

Record:

- starting SHA;
- ending SHA;
- branch;
- commits created;
- files changed;
- frozen identity model;
- frozen time model;
- correction and supersession model;
- deterministic hashing rules;
- test commands and exact results;
- known limitations;
- explicit statement that no Postgres, live option feed, IV surface, strategy expansion, paper routing, or broker order path was introduced.

---

## Commit discipline

Prefer small reviewable commits, for example:

1. `docs(data): freeze point-in-time time semantics`
2. `docs(data): separate contract and provider identity`
3. `feat(data): add deterministic market identity domain`
4. `test(data): prove identity and no-future-leakage invariants`
5. `docs(data): record DATA-1.0 acceptance`

Do not squash away useful review boundaries before review.

---

## Final response format

Return:

- starting SHA;
- ending SHA;
- branch;
- commit list;
- concise implementation summary;
- tests and checks run with exact results;
- remaining limitations;
- path to the acceptance-evidence document.
