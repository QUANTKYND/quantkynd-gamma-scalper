# DATA-1.4 Append-Only Market-Event Persistence — Checkpoint Evidence

## Status

**Checkpoint implementation complete; independent checkpoint review pending.**

This document records the DATA-1.4 checkpoint implementation and regression evidence. It does not accept, merge, or declare DATA-1.4 complete.

DATA-1 remains active. Post-checkpoint implementation, final adversarial verification, lifecycle persistence, restore evidence, operational wiring, and independent review remain required.

## Provenance

- Repository: `QUANTKYND/quantkynd-gamma-scalper`
- Branch: `feature/append-only-market-event-persistence`
- Phase-A baseline: `a6bd58fb427eb78a57ac0ee6b573ee8842e47428`
- Part 5 accepted checkpoint SHA: `2e4972f1cdd6c3bf50365babb4283ed7895a41d3`
- Part 6 focused-verification SHA: `3c95b32922947e661626d32fa32f1ceea2e5c3e5`
- Part 7 regression-boundary correction SHA: `2dbab11862ff6ad640ce80981c7d4c461268aaf1`
- Evidence commit parent SHA: `2dbab11862ff6ad640ce80981c7d4c461268aaf1`
- Alembic revision: `20260804_04`
- PostgreSQL server: `17.10`
- `psql` client: `18.4`
- Integration database: `quantkynd_test`

## Checkpoint commit chain

```text
f853f9df34a3c46cb3d47cf4ab7728d2afc74d7d  Step 1
1f4a0bb460314ec9da0b235cb9f03ef9a04f16ed  Step 2
cbb1fd7bcc1eb719557a62e9333bf5ad2d957f43  Step 3
50ff4bf9c308d59965b208c7d329beb98703b15a  Step 4A
89e4e0335075da9cbe1b39bb2278ce5a57e27a3d  Step 4B
de05b9da5b5fbf5b9aa7d0f243c53e79eebea74b  Step 4C
1171154fc9db6185ba97f1a10392eaf16ae0438e  Step 4D
2e4972f1cdd6c3bf50365babb4283ed7895a41d3  Step 5
3c95b32922947e661626d32fa32f1ceea2e5c3e5  Part 6
2dbab11862ff6ad640ce80981c7d4c461268aaf1  Part 7 regression correction
```

The Part 6 commit is one linear commit over Part 5. The Part 7 correction is one linear commit over Part 6 and changes only:

```text
backend/app/persistence/postgres/unit_of_work.py
backend/app/services/catalogue_ingestion_service.py
backend/tests/persistence/test_unit_of_work.py
```

## Implemented checkpoint scope

The checkpoint implements and verifies:

1. Persistence-independent domain commands, deterministic identities, named errors, ports, and immutable retry comparisons.
2. SQLAlchemy rows and mappings for the approved DATA-1.4 schema.
3. Alembic revision `20260804_04`.
4. Nineteen approved DATA-1.4 tables:
   - raw market frames;
   - normalization results;
   - normalized event registry;
   - quote/status subtype tables;
   - result-event memberships;
   - normalization failures;
   - result-failure memberships;
   - subscription instrument-set registry and keys;
   - lifecycle batch/event/observation registries and memberships.
5. Append-only enforcement through database triggers, restrictive foreign keys, repository behavior, and hostile SQL tests.
6. Exact temporal provenance binding to provider mapping, contract version, and catalogue version records.
7. Composite semantic/physical provenance foreign keys using `NO ACTION`.
8. Exact raw-frame persistence with a one-byte lower bound and a 16 MiB upper bound.
9. One complete atomic frame aggregate:
   - raw frame;
   - exactly one normalization result per raw frame/schema;
   - ordered normalized events;
   - aligned typed subtypes;
   - ordered failures;
   - exact readback and corruption detection.
10. Deterministic advisory-lock derivation:
    - namespace `-1377601296`;
    - 64 lock stripes;
    - sorted and deduplicated acquisition;
    - exact two-integer PostgreSQL lock call.
11. Bounded bulk chunk planning using:
    `max(1, min(1000, floor(60000 / parameters_per_row)))`.
12. Concurrent exact-retry convergence.
13. Named collision classification for:
    - changed raw content;
    - conflicting capture identity;
    - conflicting normalized event identity.
14. Non-empty downgrade refusal before destructive DDL.
15. Explicit transaction-boundary ownership:
    - shared engine default: `READ COMMITTED`;
    - ordinary `PostgresUnitOfWork`: `REPEATABLE READ`;
    - read-only snapshot unit of work: `REPEATABLE READ READ ONLY`.
16. Catalogue-ingestion migration compatibility advanced to exact revision `20260804_04`.
17. DATA-1.3 deterministic-normalization and LIVE-RV regression protection.

## Transaction and lock evidence

Database metadata:

```text
server_version: 17.10
database: quantkynd_test
default_transaction_isolation: read committed
max_locks_per_transaction: 64
```

DATA-1.4 direct aggregate writes use the shared `READ COMMITTED` engine behavior so a transaction waiting on an advisory lock can observe the winner's committed row on the next statement.

Repository-managed units of work explicitly select `REPEATABLE READ` before their first repository statement. Read-only point-in-time resolver units explicitly select `REPEATABLE READ READ ONLY`.

The 10,000-root boundary test:

- reads `max_locks_per_transaction`;
- acquires every derived DATA-1.4 advisory stripe;
- queries `pg_locks`;
- proves the measured count equals the number of derived stripes;
- proves the measured count is no greater than 64.

The exact measured integer was not printed in the supplied pytest stdout. The test nevertheless performed a real PostgreSQL measurement and passed its equality and upper-bound assertions.

## Downgrade safety evidence

Revision `20260804_04` checks all approved DATA-1.4 tables before any destructive downgrade operation.

Verified behavior:

- downgrade succeeds when all DATA-1.4 tables are empty;
- downgrade refuses when any DATA-1.4 table contains durable history;
- refusal occurs before removing triggers, functions, constraints, or tables;
- the revision remains at `20260804_04`;
- the durable row remains present;
- append-only triggers remain installed;
- temporal provenance constraints remain intact.

The migration does not use permissive `IF EXISTS` behavior to hide revision-shape drift in the provenance constraint teardown.

## Exact retry and collision evidence

Focused PostgreSQL concurrency tests verified:

- two concurrent exact aggregate writes serialize through transaction-scoped advisory locks;
- one transaction inserts and the retry converges idempotently;
- only one durable aggregate exists;
- the losing transaction does not leave partial registry, subtype, failure, or membership rows;
- same raw identity with changed content raises `RawFrameContentMismatchError`;
- same capture identity bound to another raw identity raises `RawCaptureIdentityConflictError`;
- shared normalized-event identity with changed immutable content raises `NormalizedEventIdentityConflictError`;
- shared exact immutable event content may converge safely;
- bounded timeouts prove no deadlock in the focused scenarios.

## Test evidence

### Focused regression correction suite

Command scope:

```text
tests/persistence/test_unit_of_work.py
tests/persistence/test_catalogue_ingestion_service.py
tests/persistence/test_postgres_repositories.py
tests/persistence/test_market_event_checkpoint_concurrency.py
```

Result:

```text
42 passed in 30.93s
zero failed
zero skipped
```

### Part 6 focused checkpoint suite

Command scope:

```text
tests/market_data/test_persistence_checkpoint.py
tests/persistence/test_postgres_migrations.py
tests/persistence/test_market_event_checkpoint_concurrency.py
```

Result:

```text
59 passed in 13.71s
zero failed
zero skipped
```

### Complete backend

Command:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q -rs
```

Result:

```text
780 passed in 51.88s
zero failed
zero skipped
```

### Complete market-data plus LIVE-RV regression

Command:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q -rs   tests/market_data   tests/test_live_rv.py
```

Result:

```text
387 passed in 6.46s
zero failed
zero skipped
```

### Explicit Upstox V3 proto ownership suite

Command:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q -rs   tests/market_data/upstox/test_v3_schema.py
```

Result:

```text
11 passed in 0.03s
zero failed
zero skipped
```

The schema suite verifies:

- vendored proto bytes and SHA-256;
- protobuf descriptor package and root message;
- generated Python and stub hashes;
- descriptor hash;
- ownership manifest;
- pinned `grpcio-tools==1.82.1`;
- compatible protobuf runtime ownership.

## Deterministic fixture evidence

Accepted regeneration command:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python tests/fixtures/upstox/regenerate_fixture.py
```

The accepted DATA-1.3 corpus contains 36 deterministic fixture artifacts.

The regeneration command was executed during the checkpoint gate. No fixture or Upstox schema diff was reported by:

```bash
git diff --exit-code --   backend/app/market_data/upstox   backend/tests/fixtures/upstox
```

Therefore no binary, manifest, identity, or approved-hash drift was detected.

## Compilation, dependency, and Alembic evidence

Python compilation:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests alembic
```

Result: clean; no output.

Lockfile verification:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv lock --check
```

Result:

```text
Resolved 64 packages in 0.98ms
```

Alembic heads:

```text
20260804_04 (head)
```

Alembic current:

```text
20260804_04 (head)
```

Alembic check:

```text
No new upgrade operations detected.
```

Exactly one Alembic head is present.

## Frontend regression evidence

Commands:

```bash
pnpm lint
pnpm build
```

Results:

- ESLint passed.
- TypeScript build passed.
- Vite production build passed.
- `12,316` modules transformed.
- Production build completed in `1.37s`.
- Generated JavaScript bundle:
  `1,083.95 kB`, gzip `327.85 kB`.

The existing Vite warning for chunks larger than 500 kB remains. No DATA-1.4 frontend file changed, and the warning is not treated as newly introduced by this checkpoint.

## Repository and security hygiene

Observed evidence:

- checkpoint implementation SHA before evidence:
  `2dbab11862ff6ad640ce80981c7d4c461268aaf1`;
- fixture/schema diff check produced no output;
- Python compilation produced no output;
- Alembic autogeneration check found no operations;
- production and test changes are confined to the approved checkpoint files;
- the upcoming evidence commit must contain exactly this documentation file.

A separate tracked-source credential-scan transcript was not included in the supplied checkpoint output. The accepted DATA-1.3 corpus remains synthetic and its ownership tests passed, but independent checkpoint review must confirm tracked-source secret hygiene before DATA-1.4 acceptance.

## Explicit limitations and deferred scope

This checkpoint does not implement or accept:

- complete lifecycle persistence service behavior;
- the full lifecycle adversarial matrix;
- production/offline persistence CLI;
- collision-fixture CLI;
- final dump/restore equivalence;
- the full performance campaign;
- the complete final concurrency/adversarial matrix;
- final DATA-1.4 implementation evidence;
- quality/freshness policy;
- latest-state reconstruction;
- option-chain reconstruction;
- analytics persistence;
- Redis;
- live provider persistence wiring;
- frontend or HTTP persistence APIs;
- strategy decisions;
- paper orders;
- broker order placement;
- execution routing;
- live-capital operation.

Corrections remain structurally deferred through
`CHECK supersedes_event_id IS NULL`.

DATA-1.4 remains paper-only, offline and checkpoint-review pending.

## Review gate

Independent checkpoint review is required before any post-checkpoint implementation begins.

The reviewer must verify:

1. the linear commit chain;
2. the approved table and constraint inventory;
3. append-only and downgrade behavior;
4. transaction-isolation ownership;
5. concurrency and named collision behavior;
6. exact provenance binding;
7. deterministic fixture/proto ownership;
8. the unprinted exact advisory-lock measurement if an exact integer is required;
9. tracked-source credential hygiene;
10. that no forbidden post-checkpoint scope entered the branch.

This evidence does not authorize DATA-1.4 acceptance, merge, lifecycle completion, live wiring, or downstream DATA-1 work.
