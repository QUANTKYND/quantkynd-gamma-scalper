# Codex Task — DATA-1.1 Postgres and Migration Foundation

## Repository baseline

- Repository: `https://github.com/QUANTKYND/quantkynd-gamma-scalper`
- Required starting branch: `master`
- Required starting SHA: `cfaf5372a7fa5042ed61f16cc0135b0b176641c3`
- Create branch: `feature/data-1-postgres-migration-foundation`

Run from the repository root:

```bash
git switch master
git pull --ff-only origin master
git rev-parse HEAD
git status --short
git merge-base --is-ancestor cfaf5372a7fa5042ed61f16cc0135b0b176641c3 HEAD
```

The resolved SHA must be exactly:

```text
cfaf5372a7fa5042ed61f16cc0135b0b176641c3
```

The worktree must be clean. Then create the branch:

```bash
git switch -c feature/data-1-postgres-migration-foundation
git branch --show-current
git rev-parse HEAD
git status --short
```

Do not continue from a different baseline without documenting and obtaining approval for the change.

---

## Milestone

`DATA-1.1 — Postgres and migration foundation`

Introduce:

- SQLAlchemy 2 async persistence;
- Alembic migrations;
- asyncpg;
- typed database configuration;
- explicit transaction boundaries;
- repository ports and Postgres infrastructure adapters;
- migration upgrade/downgrade verification;
- database backup-and-restore verification.

Initial durable scope:

- provider-neutral instrument and contract identities;
- validity-bounded instrument/contract versions;
- provider mappings;
- trading sessions;
- catalogue versions.

This slice does **not** ingest provider catalogues or persist quotes. It creates the durable foundation that later DATA-1 slices use.

---

## Mandatory reading

Read before editing:

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
16. `docs/implementation/DATA-1.0-point-in-time-semantics.md`
17. `backend/app/instruments/identity.py`
18. `backend/app/market_data/point_in_time.py`
19. `backend/app/core/hashing.py`
20. existing application settings, API startup, test fixtures, and dependency-locking conventions

Preserve DATA-1.0 identity, Decimal, UTC, half-open interval, append-only, conflict-detection, and knowledge-time semantics exactly.

---

## Architectural requirements

### 1. Keep the domain independent of SQLAlchemy

Domain modules must not import:

- SQLAlchemy;
- Alembic;
- asyncpg;
- FastAPI;
- provider SDKs;
- Redis;
- infrastructure sessions or row classes.

Repository interfaces belong to the port layer. SQLAlchemy models, sessions, and repositories belong to infrastructure.

The intended dependency direction remains:

```text
API / CLI
    ↓
Application services
    ↓
Domain models and policies
    ↓
Repository and unit-of-work ports
    ↓
Postgres infrastructure adapters
```

Do not pass `AsyncSession` through domain or application APIs.

### 2. Explicit transaction ownership

Repository methods must never commit independently.

A transaction is owned by an application-level unit of work:

```python
async with unit_of_work:
    await unit_of_work.instruments.add_...
    await unit_of_work.catalogues.add_...
    await unit_of_work.commit()
```

Requirements:

- one SQLAlchemy `AsyncSession` per unit of work;
- commit is explicit;
- rollback occurs on exceptions;
- closing is deterministic;
- nested or accidental independent commits are avoided;
- read-only operations do not unexpectedly mutate or commit;
- domain exceptions are not replaced by driver-specific exceptions at the port boundary;
- retry policy is not added unless a concrete idempotent operation owns it.

### 3. Deterministic writes and collision detection

Economic IDs, version IDs, mapping IDs, catalogue IDs, and session IDs remain application-generated deterministic strings.

For immutable deterministic rows:

- insert on first observation;
- exact re-insert is idempotent;
- the same ID with different content raises an explicit semantic collision error;
- never silently update, merge, or overwrite an immutable record;
- never use database-generated random identity as the sole identity of a reproducible catalogue entity.

`ON CONFLICT DO NOTHING` is insufficient by itself. After a conflict, compare the complete immutable record or use an equivalent atomic pattern that distinguishes exact idempotency from an ID/content collision.

### 4. Durable numeric and temporal types

Use:

- PostgreSQL `NUMERIC` mapped to Python `Decimal` for strikes, multipliers, and tick sizes;
- no binary floating-point durable boundary for those fields;
- `TIMESTAMP WITH TIME ZONE` for all instants;
- `DATE` for expiry and exchange session dates;
- UTC-normalized values in adapters;
- half-open validity intervals;
- explicit check constraints for positive lot size, positive tick size, positive strike and multiplier, and valid interval ordering;
- string values plus check constraints for domain enums unless a PostgreSQL enum is clearly justified.

Do not rely solely on Python validation. Important invariants must also be protected by database constraints.

### 5. No runtime `create_all`

All schema creation and alteration must happen through Alembic.

`Base.metadata.create_all()` is allowed only in isolated migration-development experiments and must not appear in runtime or accepted test setup.

---

## Dependencies

Add with the repository's `uv` workflow:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv add "sqlalchemy[asyncio]>=2.0,<3"
UV_CACHE_DIR=/tmp/uv-cache uv add "alembic>=1.13,<2"
UV_CACHE_DIR=/tmp/uv-cache uv add "asyncpg>=0.29,<1"
```

Add a dev-only async testing dependency only if the existing test stack cannot express the integration tests cleanly. Do not add `psycopg`, testcontainers, Tenacity, or a second migration framework without demonstrated need.

Update:

- `backend/pyproject.toml`;
- `backend/uv.lock`;
- `docs/dependencies.md`.

Document owner, purpose, runtime impact, security/license considerations, and removal criteria.

---

## Package layout

Use repository-consistent naming. A suitable target is:

```text
backend/app/
├── core/
│   └── database_config.py
├── instruments/
│   ├── catalogue.py
│   ├── sessions.py
│   └── ports.py
├── persistence/
│   └── postgres/
│       ├── base.py
│       ├── engine.py
│       ├── models.py
│       ├── mappings.py
│       ├── repositories.py
│       └── unit_of_work.py
└── cli/
    └── verify_database_restore.py

backend/
├── alembic.ini
└── alembic/
    ├── env.py
    ├── script.py.mako
    └── versions/
```

`app/infrastructure/postgres/` is also acceptable if it better matches the repository. Do not scatter SQLAlchemy imports through domain packages.

---

## Typed database configuration

Add a dedicated typed database configuration that does not make Postgres mandatory for pure research, strategy validation, simulation, or unrelated unit tests.

Expected fields:

```text
DATABASE_URL
DATABASE_POOL_SIZE
DATABASE_MAX_OVERFLOW
DATABASE_POOL_TIMEOUT_SECONDS
DATABASE_POOL_RECYCLE_SECONDS
DATABASE_CONNECT_TIMEOUT_SECONDS
DATABASE_STATEMENT_TIMEOUT_MS
DATABASE_APPLICATION_NAME
DATABASE_ECHO
DATABASE_RESTORE_TEST_URL
```

Requirements:

- `DATABASE_URL` is optional until a database-backed path is invoked;
- invoking a database-backed path without it fails with a precise configuration error;
- accepted application URLs use `postgresql+asyncpg://`;
- restore verification uses a distinct database URL and refuses to run when source and target resolve to the same database;
- pool counts and durations are range-validated;
- credentials are never printed;
- engine creation is lazy;
- importing settings does not open a connection;
- Alembic reads configuration without requiring broker secrets;
- pure tests and deterministic simulation remain runnable without Postgres;
- `.env.example` or the repository's equivalent receives safe placeholders only.

Do not place a real password, token, host, or account identifier in committed files.

---

## Engine and session foundation

Implement:

- one metadata registry with deterministic SQLAlchemy naming conventions;
- an async engine factory;
- an `async_sessionmaker`;
- safe disposal;
- a connection-health probe such as `SELECT 1`;
- optional statement timeout and application name through driver/server settings;
- pool pre-ping;
- no engine creation at module import.

The adapter must mask connection credentials in exceptions and logs.

---

## Initial domain additions

DATA-1.0 already freezes identity and contract-version semantics. Add only the missing domain contracts needed by persistence.

### `CatalogueVersion`

Define a persistence-independent immutable model with fields such as:

```text
catalogue_version_id
provider
source_content_hash
catalogue_schema_version
effective_from
effective_until
published_at
recorded_at
row_count
```

Required semantics:

- deterministic ID excludes runtime-only `recorded_at`;
- source content hash is mandatory;
- effective interval is half-open;
- timestamps are aware and UTC-normalized;
- row count is non-negative;
- provider and schema version are explicit;
- later ingestion status and diff reports remain DATA-1.2 unless essential to this foundation.

### Trading sessions

Freeze and implement a point-in-time-safe session model before persisting it.

Prefer separation between:

```text
TradingSessionIdentity
TradingSessionVersion
```

Identity should be stable for an exchange session date and session kind. Versioned metadata should contain open, close, optional pre-open/post-close boundaries, timezone, status, `recorded_at`, and optional `superseded_at`.

Requirements:

- session instants are timezone-aware and UTC-normalized;
- exchange interpretation remains `Asia/Kolkata` for NSE;
- open precedes close;
- optional pre-open does not follow open;
- optional post-close does not precede close;
- later corrections append a new version rather than rewriting the earlier known schedule;
- deterministic session and version IDs exclude runtime record timestamps where appropriate.

Do not introduce a holiday/calendar library in this slice.

---

## Initial relational schema

Implement the first Alembic revision with explicit primary keys, foreign keys, checks, and query-supporting indexes.

### `catalogue_versions`

Suggested fields:

```text
catalogue_version_id PK
provider
source_content_hash
catalogue_schema_version
effective_from
effective_until NULL
published_at NULL
recorded_at
row_count
```

### Common market-instrument registry

Use a common parent registry so versions and provider mappings have enforceable foreign keys across underlyings, futures, and options:

```text
market_instruments
    instrument_id PK
    instrument_kind  # underlying | future | option
    exchange
    currency
```

Subtype tables:

```text
underlying_instruments
    instrument_id PK/FK market_instruments
    canonical_symbol
    instrument_type

futures_contracts
    contract_id PK/FK market_instruments.instrument_id
    underlying_instrument_id FK underlying_instruments
    expiry
    settlement_type
    multiplier

option_contracts
    contract_id PK/FK market_instruments.instrument_id
    underlying_instrument_id FK underlying_instruments
    expiry
    strike
    option_side
    exercise_style
    settlement_type
    multiplier
```

The adapter may continue to expose `instrument_id` and `contract_id` according to domain terminology even though the registry uses one FK-compatible column.

### `instrument_versions`

One shared version table is preferred because metadata is common and provider mappings require one enforceable version FK:

```text
version_id PK
instrument_id FK market_instruments
valid_from
valid_until NULL
lot_size
tick_size
display_symbol
trading_status
catalogue_version_id FK catalogue_versions
recorded_at
superseded_at NULL
```

If separate subtype version tables are chosen, provider mapping referential integrity must still be enforceable without a polymorphic, unchecked ID.

### `provider_contract_mappings`

```text
mapping_id PK
provider
provider_contract_key
contract_version_id FK instrument_versions
provider_payload_hash
source_row_identity NULL
effective_from
effective_until NULL
recorded_at
superseded_at NULL
```

Add point-in-time lookup indexes covering:

- provider plus provider contract key;
- contract version;
- effective interval starts;
- system-time record/supersession boundaries.

Do not create a uniqueness rule that prevents legitimate historical reuse of a provider key. Uniqueness must include the relevant effective/version identity.

### Trading sessions

```text
trading_sessions
    session_id PK
    exchange
    session_date
    session_kind

trading_session_versions
    session_version_id PK
    session_id FK trading_sessions
    pre_open_at NULL
    open_at
    close_at
    post_close_at NULL
    timezone
    status
    recorded_at
    superseded_at NULL
```

Add indexes for exchange/date lookups and knowledge-time visibility.

### Constraint rules

At minimum:

- all deterministic SHA-256 IDs have bounded non-empty storage;
- interval end is null or strictly after start;
- superseded time is null or strictly after recorded time;
- positive lot size;
- positive numeric strike, multiplier, and tick size;
- non-negative catalogue row count;
- option side, exercise style, settlement type, trading status, instrument kind, and session status are constrained to supported values;
- subtype row type agrees with the parent registry kind;
- no cascade deletes that could erase historical records.

Do not add quote, trade, quality, chain snapshot, IV, surface, Redis, strategy, order, or ledger tables.

---

## Repository ports

Define persistence-independent async protocols. Keep them narrow.

Expected capabilities:

### Catalogue repository

- add an immutable catalogue version;
- retrieve by deterministic ID;
- list versions for a provider;
- resolve the catalogue visible at market and knowledge cutoffs where meaningful.

### Instrument repository

- add underlying, future, and option economic identities;
- add immutable instrument versions;
- add provider mappings;
- fetch identities and versions by deterministic ID;
- resolve a provider key at `market_as_of` and optional `known_as_of`;
- list contract versions for an underlying and expiry;
- reject semantic ID/content collisions.

### Trading-session repository

- add session identity and version;
- retrieve the session visible at a market/session date and knowledge cutoff;
- reject conflicting deterministic identities.

Do not expose SQLAlchemy row types, `AsyncSession`, engine objects, or SQL expressions through ports.

---

## Postgres adapters

Implement explicit domain-to-row and row-to-domain mapping.

Requirements:

- round-trip `Decimal` exactly;
- round-trip aware datetimes as UTC;
- reconstruct domain enums;
- preserve `None` versus a value;
- detect malformed durable rows explicitly;
- immutable insert is idempotent only for complete equality;
- repository reads use deterministic ordering;
- provider-key resolution applies effective and system-time intervals;
- ambiguous visible mappings fail closed rather than selecting arbitrarily;
- no lazy ORM relationship access outside the owning session;
- avoid N+1 reads in the point-in-time resolution methods.

Use SQLAlchemy 2 statement style.

---

## Alembic foundation

Configure Alembic to:

- load only the persistence metadata;
- support the asyncpg URL through an async Alembic environment;
- run online migrations with `await connection.run_sync(...)`;
- support offline SQL generation if practical;
- use deterministic constraint names;
- include the Alembic version table;
- avoid importing global application settings that require broker credentials;
- refuse to operate without an explicit database URL;
- never log the database password.

Create one clear initial revision for the DATA-1.1 schema.

The migration must have a valid downgrade to empty/base for the new tables. Downgrade must remove children before parents and must not use broad schema drops.

---

## Local Postgres test service

Add or update the repository's Docker Compose configuration with a development/test Postgres service.

Recommended baseline:

```text
postgres:17-alpine
```

Requirements:

- named durable volume for local development;
- health check using `pg_isready`;
- safe local-only credentials;
- no exposed non-Postgres services added by this slice;
- a distinct integration-test database;
- documented startup and teardown commands;
- no dependence on Redis.

Example workflow:

```bash
docker compose up -d postgres
docker compose ps
```

Do not make ordinary pure unit tests require the container.

---

## Tests

### Configuration tests

- no connection is opened at import;
- missing URL fails only when DB functionality is requested;
- malformed or non-async Postgres URLs fail clearly;
- invalid pool settings fail;
- credentials are redacted;
- source and restore-test databases must differ.

### Mapping tests

- every DATA-1.0 identity and version round-trips through the adapter;
- Decimal precision is exact;
- UTC timestamps are preserved;
- enums and nullable fields round-trip;
- malformed row data cannot silently become a domain object.

### Repository integration tests

Against real Postgres:

- exact reinsert is idempotent;
- same deterministic ID with different content raises the repository collision error;
- identities, versions, mappings, catalogues, and sessions persist in one transaction;
- rollback removes all writes from the failed unit of work;
- repository methods do not commit independently;
- provider key resolves correctly by `market_as_of`;
- future effective records do not leak backward;
- records stored later do not appear before `known_as_of`;
- superseded versions remain reproducible before their supersession cutoff;
- ambiguous visible mappings fail closed;
- deleting a referenced identity/version is rejected;
- deterministic ordering is independent of insertion order.

### Migration tests

Against a newly created database:

1. upgrade from base to head;
2. assert the expected tables, columns, foreign keys, checks, indexes, and Alembic revision;
3. insert deterministic fixture rows;
4. downgrade from head to base;
5. assert DATA-1.1 tables are gone;
6. upgrade to head again;
7. rerun fixture persistence;
8. run `alembic check` or an equivalent metadata-to-head drift check.

Migration tests must not depend on a developer's pre-existing schema.

### Transaction failure tests

- exception before commit causes rollback;
- exception during commit leaves no partial catalogue;
- two repositories share the same unit-of-work transaction;
- closed unit of work cannot be reused accidentally;
- explicit rollback is safe and deterministic.

---

## Database backup and restore verification

Implement a real verification path using PostgreSQL tools:

```text
pg_dump
pg_restore
```

A suitable CLI is:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
```

The verifier must:

1. require explicit source and restore-test database configuration;
2. refuse to run when both point to the same database;
3. verify both databases are non-production/test-safe according to documented rules;
4. migrate the source to Alembic head;
5. seed a deterministic DATA-1.1 fixture through repositories and one unit of work;
6. create a custom-format dump with ownership and privileges excluded;
7. restore into a clean restore-test database;
8. verify the restored Alembic revision;
9. compare deterministic row counts and a canonical digest of all DATA-1.1 durable rows;
10. run representative provider-key and session point-in-time reads against both databases and compare results;
11. remove temporary dump artifacts;
12. return non-zero on any mismatch;
13. never print passwords or a full unredacted DSN.

Do not call this a successful restore test if it merely verifies that `pg_restore` exited zero. Data and representative query equivalence are mandatory.

The verification can be an acceptance command rather than part of every ordinary `pytest` invocation, but it must be automated, documented, and run for acceptance.

---

## Documentation updates

Update at minimum:

- `docs/design.md`
- `docs/data-models.md`
- `docs/dependencies.md`
- `docs/environment.md`
- `docs/testing.md`
- `docs/security.md`
- `docs/observability.md`
- `docs/plan/options-market-infrastructure.md`
- `docs/plan/roadmap.md`
- `docs/plan/acceptance-gates.md`

Document:

- new persistence package boundaries;
- source-of-truth and transaction ownership;
- table model and foreign-key strategy;
- exact point-in-time repository semantics;
- deterministic insert/collision behavior;
- database configuration;
- migration commands;
- local Postgres workflow;
- backup/restore verification;
- what remains deferred.

Add:

```text
docs/implementation/DATA-1.1-postgres-migration-foundation.md
```

---

## Explicit non-goals

Do not implement:

- provider catalogue download or parsing;
- Upstox instrument-file ingestion;
- catalogue diff reports;
- underlying, option, or futures quote persistence;
- option trade persistence;
- data-quality assessment persistence;
- chain snapshots;
- IV inversion;
- Greeks;
- smiles or surfaces;
- implied variance;
- Redis;
- live option subscriptions;
- API endpoints or frontend screens for catalogue data;
- backtesting;
- EDGE-1;
- paper execution;
- broker order placement;
- retention partitions before volume is measured;
- automatic retry loops without an owned idempotency policy;
- a live-capital environment.

The deterministic simulator must remain database-independent and offline.

---

## Acceptance criteria

DATA-1.1 is accepted only when:

1. the branch begins at the verified master SHA;
2. SQLAlchemy 2, Alembic, and asyncpg are owned and locked dependencies;
3. domain modules remain persistence-independent;
4. typed DB configuration is lazy and does not break offline workflows;
5. migrations are the only schema-creation path;
6. identities, versions, provider mappings, sessions, and catalogue versions have enforceable relational integrity;
7. deterministic inserts distinguish exact idempotency from semantic collision;
8. repository ports expose no SQLAlchemy types;
9. one unit of work owns commit and rollback;
10. point-in-time provider and session resolution respects market and knowledge cutoffs;
11. migration upgrade, downgrade, re-upgrade, and drift checks pass on clean Postgres;
12. a real dump/restore verification proves schema revision, row digest, and representative query equivalence;
13. full backend tests pass;
14. frontend lint and build pass;
15. `git diff --check` passes;
16. generated artifacts, secrets, DSNs, and Postgres dump files are not tracked;
17. the worktree is clean;
18. no deferred market-data, analytics, Redis, strategy, or execution path is introduced;
19. acceptance evidence contains exact commands and results.

---

## Required verification

### Pure and full backend

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Run any configured backend formatter, linter, type checker, or coverage gate if present.

### Postgres and migrations

Use the repository-documented commands, covering at minimum:

```bash
docker compose up -d postgres
docker compose ps

cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
```

Run the clean-database migration test suite, including downgrade and re-upgrade.

### Restore

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
```

Record the source revision, restored revision, row counts, canonical digest comparison, and representative query comparison without recording credentials.

### Frontend

```bash
cd frontend
pnpm lint
pnpm build
```

Use `npm` only if the checked-in repository scripts and lockfile have intentionally changed to npm.

### Repository checks

```bash
git diff --check
git status --short
git ls-files | grep -E '(^|/)(__pycache__|.*\.pyc|node_modules|dist|.*\.dump|.*\.backup)(/|$)' || true
```

Run the repository's secret scan.

Do not claim a check passed unless it was actually run successfully.

---

## Acceptance evidence

Create:

```text
docs/implementation/DATA-1.1-postgres-migration-foundation.md
```

Record:

- branch;
- starting SHA;
- verified implementation ending SHA;
- final evidence-only SHA if applicable;
- commits;
- files changed;
- dependency additions and lockfile change;
- domain additions;
- relational schema;
- transaction-boundary design;
- repository ports and adapters;
- migration revision;
- exact upgrade/downgrade/re-upgrade results;
- exact backend test result;
- exact frontend lint/build result;
- dump/restore command and equivalence result;
- security and artifact scans;
- known limitations;
- explicit statement that no quote persistence, provider ingestion, Redis, IV/surface work, strategy expansion, paper routing, live-capital route, or broker order path was introduced.

---

## Suggested commit sequence

Prefer small reviewable commits:

1. `build(data): add postgres persistence dependencies`
2. `feat(data): add typed database configuration`
3. `feat(data): define catalogue and session domain contracts`
4. `feat(data): add persistence ports and unit of work`
5. `feat(data): add postgres models and repositories`
6. `feat(data): add initial DATA-1.1 migration`
7. `test(data): verify postgres repositories and transactions`
8. `test(data): verify migrations and database restore`
9. `docs(data): document DATA-1.1 postgres foundation`
10. `docs(data): record DATA-1.1 acceptance`

Do not squash away useful review boundaries before review.

---

## Final response format

Return:

- branch;
- starting SHA;
- implementation ending SHA;
- final ending SHA;
- commits created;
- files changed;
- schema summary;
- transaction and repository design;
- migration revision;
- exact unit/integration/migration/restore test results;
- frontend results;
- remaining limitations;
- acceptance-evidence path.

---

## Implementation evidence — 2026-08-04

### Provenance

- Branch: `feature/data-1-postgres-migration-foundation`
- Required starting SHA: `cfaf5372a7fa5042ed61f16cc0135b0b176641c3`
- Resolved starting SHA: `cfaf5372a7fa5042ed61f16cc0135b0b176641c3`
- Implementation ending SHA: `4548b66a83fa84b8d50558e2834914fec2263015`
- Final evidence-only SHA: reported in the final handoff because a Git commit cannot contain its own resulting SHA
- Migration revision: `20260804_01`
- Acceptance status: implementation complete; real-Postgres migration and dump/restore acceptance blocked by unavailable local Docker integration and PostgreSQL client tools

### Commits

```text
5cd1ac0 build(data): add postgres persistence dependencies
5211811 feat(data): add typed database configuration
1e06ba4 feat(data): define persistence domain contracts and ports
ba249ee feat(data): add postgres models repositories and unit of work
11a9489 feat(data): add initial postgres migration and local service
57fb592 feat(data): add deterministic database restore verification
47285ec test(data): verify postgres foundation invariants
4548b66 docs(data): document DATA-1.1 postgres foundation
```

### Implemented foundation

- Added and locked SQLAlchemy 2 async support, Alembic, and asyncpg. No synchronous Postgres driver, retry library, calendar package, Redis client, or serialization dependency was added.
- Added lazy typed database configuration, bounded pool and timeout settings, credential redaction, local-host alias comparison, and distinct restore-target enforcement. Pure research, simulation, API imports, and unit tests do not require a database URL.
- Added immutable persistence-independent catalogue and trading-session domain contracts, narrow async repository protocols, explicit collision/integrity/ambiguity errors, and a unit-of-work protocol.
- Added nine application tables: `catalogue_versions`, `market_instruments`, `underlying_instruments`, `futures_contracts`, `option_contracts`, `instrument_versions`, `provider_contract_mappings`, `trading_sessions`, and `trading_session_versions`.
- Added bounded IDs, `NUMERIC(38,18)` values, enum and interval checks, subtype-kind integrity, non-cascading foreign keys, and deterministic query indexes. Alembic is the only schema-creation path.
- Added explicit row/domain adapters that preserve UTC, `Decimal`, enums, and nullability, and reject malformed data or deterministic ID/content mismatches.
- Added immutable repository insertion where exact complete-record reinsertion is idempotent and different durable content under the same deterministic ID raises `SemanticCollisionError`.
- Added deterministic provider-key and session resolution. Provider lookup intersects mapping and instrument-version market intervals and both knowledge intervals; ambiguous results fail closed.
- Added one-session async unit of work. Repository methods never commit; explicit commit succeeds the transaction, while exceptions, commit failure, explicit rollback, and exit without commit roll back and close.
- Added a deterministic fixture and a restore CLI that migrates and seeds the source, creates a custom no-owner/no-privilege dump, clears only a test-safe target schema, restores it, and compares revision, table counts, canonical digest, provider mapping, and session reads.
- Added a localhost-only Postgres 17 Compose service with separate `quantkynd_test` and `quantkynd_restore` databases.

### Files changed

```text
.gitignore
backend/.env.example
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/20260804_01_data_1_1_foundation.py
backend/app/cli/verify_database_restore.py
backend/app/core/database_config.py
backend/app/instruments/catalogue.py
backend/app/instruments/ports.py
backend/app/instruments/sessions.py
backend/app/persistence/__init__.py
backend/app/persistence/postgres/__init__.py
backend/app/persistence/postgres/base.py
backend/app/persistence/postgres/engine.py
backend/app/persistence/postgres/fixtures.py
backend/app/persistence/postgres/mappings.py
backend/app/persistence/postgres/migrations.py
backend/app/persistence/postgres/models.py
backend/app/persistence/postgres/repositories.py
backend/app/persistence/postgres/unit_of_work.py
backend/app/persistence/postgres/verification.py
backend/pyproject.toml
backend/tests/persistence/conftest.py
backend/tests/persistence/test_database_config.py
backend/tests/persistence/test_domain_models.py
backend/tests/persistence/test_mappings.py
backend/tests/persistence/test_postgres_migrations.py
backend/tests/persistence/test_postgres_repositories.py
backend/tests/persistence/test_restore_verification.py
backend/tests/persistence/test_unit_of_work.py
backend/uv.lock
docker-compose.yaml
docker/postgres/init/01-create-databases.sql
docs/conventions.md
docs/data-models.md
docs/dependencies.md
docs/design.md
docs/environment.md
docs/implementation/DATA-1.1-postgres-migration-foundation.md
docs/observability.md
docs/plan/acceptance-gates.md
docs/plan/options-market-infrastructure.md
docs/plan/roadmap.md
docs/security.md
docs/testing.md
```

### Verification results

Backend compilation:

```text
Command: cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
Result: PASS, exit 0, no output
```

Backend tests:

```text
Command: cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest
Result: PARTIAL PASS — 348 passed, 8 skipped in 5.87s
Skipped: 1 clean migration lifecycle test and 7 real-Postgres repository/transaction tests because DATABASE_URL was not configured and no PostgreSQL service was available
```

Dependency lock:

```text
Command: cd backend && UV_CACHE_DIR=/tmp/uv-cache uv lock --check
Result: PASS — Resolved 63 packages in 0.89ms
```

Offline migration compilation and identifier verification:

```text
Command: cd backend && DATABASE_URL=postgresql+asyncpg://quantkynd:local@localhost:5432/quantkynd_test UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head --sql
Result: PASS — revision 20260804_01 generated 202 lines of PostgreSQL DDL
Result: PASS — every migration constraint/index name matched persistence metadata and the longest identifier was below PostgreSQL's 63-character limit
```

Frontend:

```text
Command: cd frontend && pnpm lint
Result: PASS — eslint .
Command: cd frontend && pnpm build
Result: PASS — TypeScript and Vite production build completed; 12,316 modules transformed in 1.30s
Note: Vite emitted the existing non-failing warning for a minified chunk larger than 500 kB
```

Repository hygiene:

```text
Command: git diff --check
Result: PASS
Command: git ls-files | grep -E '(^|/)(__pycache__|.*\.pyc|node_modules|dist|.*\.dump|.*\.backup)(/|$)' || true
Result: PASS — no tracked generated artifacts matched
Secret scanner discovery: no gitleaks, detect-secrets, git-secrets, or repository-owned secret-scan command is configured in this environment
```

### Blocked acceptance commands

Local Postgres service:

```text
Command: docker compose version
Result: BLOCKED — Docker reports that the command is unavailable in this WSL 2 distribution and requests Docker Desktop WSL integration
Direct docker.exe probe: BLOCKED — WSL vsock connection failed
```

Online migration lifecycle and drift:

```text
Commands not claimed as passed: alembic upgrade head; alembic current; alembic check; clean downgrade/re-upgrade integration test
Reason: no reachable PostgreSQL service is available
```

Restore equivalence:

```text
Command: cd backend && DATABASE_URL=<test-safe asyncpg URL> DATABASE_RESTORE_TEST_URL=<distinct test-safe asyncpg URL> UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
Result: BLOCKED, non-zero — {"error": "required PostgreSQL tools are unavailable: pg_dump, pg_restore", "status": "failed"}
```

DATA-1.1 cannot be called fully accepted until Docker/Postgres and the client tools are made available, the 8 database tests run rather than skip, the online Alembic lifecycle and drift checks pass, and the dump/restore equivalence command passes. The implementation keeps those checks automated and ready to rerun without code changes.

### Remaining limitations and scope statement

Provider catalogue download/parsing and diff reports remain DATA-1.2. Normalized quote, trade, quality-assessment, chain-snapshot, IV, Greeks, smile/surface, implied-variance, retention, retry, production backup scheduling, and operational database metrics remain deferred to their owning milestones.

No quote persistence, provider ingestion, Redis, IV or surface implementation, frontend or API catalogue path, strategy expansion, paper routing, live-capital route, broker order placement, or change to deterministic simulator behavior or hashes was introduced.
