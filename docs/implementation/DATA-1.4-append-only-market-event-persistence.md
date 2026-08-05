# DATA-1.4 checkpoint implementation evidence

Status: implementation checkpoint; independent checkpoint review pending.

Branch: `feature/append-only-market-event-persistence`

Original checkpoint starting SHA: `a6bd58fb427eb78a57ac0ee6b573ee8842e47428`.

Continuation starting SHA: `cfaa1c08f638e0e4f29640a76369936715db308f`.

The checkpoint foundation includes persistence contracts, deterministic identities, named collision errors, lock-striping and bounded chunk planning, migration `20260804_04`, append-only triggers, and `PostgresUnitOfWork.market_events` exposure. The frame repository now inserts or compares raw frames, result evidence, observations, failures, and ordered memberships inside the caller-owned unit of work. Lifecycle services, CLI, dump/restore, and final acceptance remain deferred.

Frozen constants:

- `DATA14_ADVISORY_LOCK_NAMESPACE = -1377601296`
- `DATA14_LOCK_STRIPE_COUNT = 64`
- advisory lock form: two-int `pg_advisory_xact_lock(namespace, stripe)`
- parameter budget: 60,000 parameters per chunk

Verification run on the continuation:

- PostgreSQL server: `PostgreSQL 17.10` on Alpine;
- `max_locks_per_transaction`: `64`;
- Alembic upgrade reached `20260804_04`; metadata check reports no new upgrade operations;
- focused pure checkpoint suite: 5 passed, zero skipped;
- backend pytest: existing suite passed with the repository's pre-existing PostgreSQL skips;
- Python compilation: passed with `uv run python -m compileall`;
- `uv lock --check`: passed;
- frontend ESLint and production build: passed;
- `git diff --check`: passed.

Known checkpoint deviations remain: temporal catalogue record provenance is not persisted; the approved PK/unique/FK matrix and hostile numeric/time constraints are incomplete; PostgreSQL concurrency and rollback suites are absent. Repository event/failure writes now use parameter-bounded batch execution with the approved chunk planner. This document intentionally does not claim checkpoint completion, final DATA-1.4 acceptance, dump/restore completion, or lifecycle completion.
