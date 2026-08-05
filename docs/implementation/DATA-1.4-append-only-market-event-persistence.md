# DATA-1.4 checkpoint implementation evidence

Status: implementation checkpoint corrected; independent checkpoint review pending.

Branch: `feature/append-only-market-event-persistence`

Original checkpoint starting SHA: `a6bd58fb427eb78a57ac0ee6b573ee8842e47428`.

Continuation starting SHA: `cfaa1c08f638e0e4f29640a76369936715db308f`.

The checkpoint foundation includes persistence contracts, deterministic identities, named collision errors, lock-striping and bounded chunk planning, migration `20260804_04`, append-only triggers, and `PostgresUnitOfWork.market_events` exposure. The frame repository now performs bounded prefetch/compare lookups for existing observations and memberships so exact-retry replays remain idempotent while staying within the approved parameter budget. Lifecycle services, CLI, dump/restore, and final acceptance remain deferred.

Frozen constants:

- `DATA14_ADVISORY_LOCK_NAMESPACE = -1377601296`
- `DATA14_LOCK_STRIPE_COUNT = 64`
- advisory lock form: two-int `pg_advisory_xact_lock(namespace, stripe)`
- parameter budget: 60,000 parameters per chunk

Verification run on the corrected checkpoint:

- PostgreSQL server: `PostgreSQL 17.10` on Alpine;
- `max_locks_per_transaction`: `64`;
- Alembic upgrade reached `20260804_04`; metadata check reports no new upgrade operations;
- focused persistence suite: `27 passed in 10.44s`, zero skipped;
- Python compilation: passed with `uv run python -m compileall`;
- `git diff --check`: passed.

Known deferred scope remains: lifecycle services, CLI completion, dump/restore completion, and final DATA-1.4 acceptance remain out of scope for this checkpoint handoff. This document intentionally does not claim lifecycle completion, final DATA-1.4 acceptance, dump/restore completion, or post-checkpoint application-service completion.
