# Codex Task — DATA-1.2 Review Corrections

## Repository baseline

- Repository: `https://github.com/QUANTKYND/quantkynd-gamma-scalper`
- Continue on branch: `feature/data-1-deterministic-provider-catalogue-ingestion`
- Reviewed branch head: `643a9b2ee8e5b3b8f09a8ff7ee8350bddb3c6660`
- Required ancestor: `4030955c9be2c370d2ef40082fbb00aea7f7061a`

Before editing:

```bash
git switch feature/data-1-deterministic-provider-catalogue-ingestion
git pull --ff-only
git branch --show-current
git rev-parse HEAD
git status --short
git merge-base --is-ancestor 4030955c9be2c370d2ef40082fbb00aea7f7061a HEAD
```

Record the correction starting SHA. The worktree must be clean. Do not merge into `master`.

The evidence status must remain:

```text
implementation complete; acceptance evidence recorded; independent review pending
```

until independent review approves the corrected branch.

---

## Review outcome

DATA-1.2 is not yet accepted.

The first-catalogue path is well covered, but the implementation does not yet support the core sequential-catalogue lifecycle safely. It also has profile-classification, duplicate-provider-key, dry-run, numeric, and exception-translation gaps.

Correct all requirements below.

---

# 1. Fix sequential catalogue ingestion

## Current failure

The service rejects provider reassignment by comparing:

```text
existing mapping contract_version_id
versus
new item version_id
```

This is incorrect because version identity contains `catalogue_version_id`. A later catalogue normally creates a different version ID even when the provider key still represents the same economic instrument.

The service also inserts new instrument-version and provider-mapping temporal records without predecessor record IDs. A second catalogue can therefore create multiple root leaves in one temporal scope.

## Required behavior

A later accepted catalogue must support:

```text
catalogue A
    ↓ explicit catalogue predecessor
catalogue B
```

For every included provider row:

- compare provider-key binding by stable economic `instrument_id`, not by version ID;
- the same Upstox `instrument_key` may continue to bind to the same economic instrument;
- the same Upstox `instrument_key` binding to a different economic instrument is always rejected;
- a new provenance-bound instrument version must supersede the currently eligible instrument-version record in the same instrument scope;
- a new provider mapping must supersede the currently eligible mapping record in the same provider/key scope;
- no new unrelated temporal root may be created when an eligible predecessor exists;
- exact retries remain idempotent;
- disappeared rows are reported but are not automatically superseded, expired, or deleted.

Introduce an explicit transition plan, for example:

```text
CatalogueTransitionPlan
CatalogueItemTransition
```

Each item transition should contain:

```text
economic instrument ID
new version
new mapping
prior version record ID, if any
prior mapping record ID, if any
diff category
```

The transition plan must be used by both dry-run and commit.

## Repository ports

Add persistence-independent repository capabilities that return the semantic value and temporal record identity needed for safe transitions.

Do not expose SQLAlchemy rows or sessions.

Suitable capabilities include:

```text
resolve instrument version state by instrument scope and cutoffs
resolve provider mapping state with economic instrument ID and record ID
resolve catalogue state with catalogue record ID
```

The service must validate the operator-supplied catalogue predecessor against the current eligible catalogue leaf after acquiring the provider/profile advisory lock.

## Write order

Inside one unit of work:

1. acquire provider/profile advisory lock;
2. resolve and validate catalogue predecessor;
3. build or revalidate the repository-aware transition plan;
4. insert catalogue temporal successor;
5. insert economic identities deterministically;
6. insert each version with its explicit predecessor record ID;
7. insert each mapping with its explicit predecessor record ID;
8. insert run, outcomes, and memberships;
9. commit once.

---

# 2. Correct profile candidate classification

## Current failure

The current profile predicate requires valid values for:

```text
segment
exchange
underlying_key
underlying_type
instrument_type
```

A Nifty-linked derivative with a missing or invalid `instrument_type` or `underlying_type` can therefore be classified as `excluded_by_profile` instead of rejected as malformed in-profile data.

## Required classification

Separate:

```text
candidate identification
```

from:

```text
candidate validation
```

Rules:

- the exact approved underlying key is always an in-profile candidate and must satisfy the complete underlying schema;
- an `NSE_FO` row whose `underlying_key` is `NSE_INDEX|Nifty 50` is an in-profile candidate;
- a candidate with missing or invalid exchange, segment, underlying type, instrument type, expiry, strike, lot size, tick size, display symbol, or underlying-symbol consistency must reject the catalogue;
- stock derivatives and derivatives for other index underlying keys are excluded;
- unrelated valid NSE rows remain `excluded_by_profile`.

Do not let malformed Nifty-linked derivatives disappear into the exclusion count.

Validate the underlying row's required `instrument_type=INDEX` and any other approved profile fields.

---

# 3. Reject non-identical duplicate provider keys

## Current failure

Two different raw rows with the same provider key and the same normalized projection are both accepted because only differing normalized projections are rejected.

That can create multiple overlapping provider mappings for one provider key and an ambiguous temporal state.

## Required behavior

- exact raw duplicate rows remain `exact_duplicate`;
- a second non-identical raw row using an already-seen provider key must reject the catalogue, even when its normalized projection is equal;
- do not create two memberships or mappings for the same provider key in one catalogue;
- preserve the rule that two different provider keys may map to the same economic contract.

Add a database-level or repository-level defensive check where practical, while preserving legitimate historical mapping records.

---

# 4. Make dry-run use the real transition plan

## Current failure

Dry-run currently:

- acquires the advisory lock;
- checks only whether a catalogue predecessor is required;
- returns no semantic diff;
- does not perform the provider binding, version predecessor, mapping predecessor, or persistence-collision planning used by commit.

A dry-run may therefore report accepted when commit would fail.

## Required behavior

Dry-run must:

- run in one read-only repeatable-read transaction;
- acquire the same provider/profile advisory lock;
- resolve the same explicit catalogue predecessor;
- build the same repository-aware transition plan as commit;
- perform provider-key reassignment checks;
- detect temporal predecessor conflicts and ambiguous state;
- compute a deterministic semantic diff;
- perform no writes and retain no artifact.

Return a deterministic diff in CLI JSON, at minimum:

```text
added
unchanged
metadata_changed
provider_mapping_changed
disappeared
excluded
exact_duplicates
```

The result must make clear that disappearance is informational and does not imply deletion.

Commit must consume the same plan or revalidate it under the same lock so dry-run and commit cannot drift by implementation logic.

---

# 5. Remove binary floating-point from expiry conversion

## Current failure

The expiry conversion performs:

```python
milliseconds / 1000
```

before `datetime.fromtimestamp`, which converts provider numeric data through binary floating point.

This contradicts the implementation evidence.

## Required behavior

Convert epoch milliseconds using integer arithmetic only.

For example:

```text
seconds, remainder_ms = divmod(milliseconds, 1000)
UTC epoch + timedelta(seconds=seconds, milliseconds=remainder_ms)
```

Then convert to `Asia/Kolkata` and extract the exchange date.

Reject:

- booleans;
- non-integral values;
- invalid range;
- unsupported negative values if the profile does not permit them.

Add boundary tests around an exchange-local date transition.

Update the evidence claim only after this is true.

---

# 6. Preserve non-idempotency persistence errors

## Current failure

Commit catches broad:

```text
IntegrityError
PersistenceIntegrityError
SemanticCollisionError
```

and always attempts to reinterpret the failure through idempotency lookup.

An unrelated constraint failure or semantic collision can be masked as an idempotency conflict.

## Required behavior

After the failed transaction is rolled back and finalized:

- open a fresh read transaction;
- if the idempotency key now identifies an accepted run:
  - return idempotent success only when the command digest and immutable command inputs match;
  - otherwise raise `CatalogueIdempotencyConflictError`;
- if no accepted run exists, re-raise or translate the original error according to its real category;
- do not turn temporal, semantic, foreign-key, check-constraint, or data-corruption failures into idempotency failures.

Add tests for:

- genuine concurrent same-command idempotency race;
- same key with different command;
- semantic collision with no accepted run;
- unrelated integrity constraint failure with no accepted run;
- temporal successor conflict.

---

# 7. Add sequential lifecycle tests

Acceptance-critical real-PostgreSQL tests must prove:

## Same economic catalogue later

1. ingest catalogue A;
2. ingest catalogue B at a later effective time with explicit catalogue predecessor;
3. use the same provider keys and economic contracts;
4. B succeeds despite new catalogue/version/mapping IDs;
5. B's version records supersede A's eligible version records;
6. B's mapping records supersede A's eligible mapping records;
7. no temporal scope has multiple roots or ambiguous eligible leaves.

## Historical reproducibility

- before B is known, historical catalogue and provider-key reads return A;
- after B is known but before B is effective, reads return A;
- after B is known and effective, reads return B;
- earlier knowledge cutoffs remain reproducible.

## Metadata change

- same economic contract and provider key with a changed lot size, tick size, or display symbol is accepted as a new version;
- historical reads return the old metadata;
- current reads return the new metadata.

## Economic reassignment

- the same provider key changing strike, expiry, side, or economic underlying is rejected.

## Disappearance

- a predecessor member absent from B is reported as disappeared;
- it is not automatically deleted, expired, or superseded.

## Concurrency

- two concurrent first catalogues cannot both become roots;
- two concurrent successors of A cannot both commit;
- exact concurrent replay produces one commit and one verified idempotent success.

---

# 8. Add classification and duplicate tests

Add tests proving:

- Nifty-linked row missing `instrument_type` rejects;
- Nifty-linked row with unsupported `instrument_type` rejects;
- Nifty-linked row missing or invalid `underlying_type` rejects;
- Nifty-linked row with wrong exchange/segment rejects;
- approved underlying row with wrong or missing `instrument_type` rejects;
- derivative for another underlying is excluded;
- stock derivative is excluded;
- exact duplicate raw row is `exact_duplicate`;
- same provider key with different raw content but equal normalized projection rejects;
- same provider key with different normalized content rejects;
- two different provider keys for the same economic contract remain allowed.

---

# 9. Extend restore verification

The restore fixture should include two sequential catalogues, not only the first-catalogue path.

Verify after restore:

- catalogue A and B temporal record IDs;
- version and mapping successor edges;
- historical A reads;
- current B reads;
- provider binding continuity by economic instrument ID;
- non-zero DATA-1.2 audit rows for both accepted runs;
- artifact references for both source artifacts if two artifacts are used;
- canonical digest and row counts.

---

# 10. Documentation and evidence

Update:

- `docs/design.md`
- `docs/data-models.md`
- `docs/testing.md`
- `docs/observability.md`
- `docs/plan/options-market-infrastructure.md`
- `docs/plan/acceptance-gates.md`
- `docs/implementation/DATA-1.2-deterministic-provider-catalogue-ingestion.md`

Remove or relocate:

```text
docs/implementation/DATA-1.2-final-review-readiness.md
```

A task instruction is not implementation evidence and should not remain under `docs/implementation/`.

Record:

- correction starting SHA;
- corrected implementation SHA;
- review-pending evidence SHA;
- exact commits;
- second-catalogue lifecycle results;
- dry-run diff example;
- zero skipped DATA-1.2 integration tests;
- migration/restore results;
- updated full test count;
- worktree status.

Do not mark accepted.

---

# 11. Verification

Run:

```bash
cd backend

UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests

DATABASE_URL=<redacted-test-url> \
DATABASE_RESTORE_TEST_URL=<redacted-restore-url> \
DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true \
DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test \
DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore \
DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false \
CATALOGUE_ARTIFACT_ROOT=<temporary-acceptance-root> \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -ra

UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check

DATABASE_URL=<redacted-test-url> \
DATABASE_RESTORE_TEST_URL=<redacted-restore-url> \
DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true \
DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test \
DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore \
DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false \
CATALOGUE_ARTIFACT_ROOT=<temporary-acceptance-root> \
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.verify_database_restore
```

Also run:

```bash
cd frontend
pnpm lint
pnpm build
```

From repository root:

```bash
git diff --check
git status --short
```

Acceptance-critical DATA-1.2 tests must have zero skips.

---

# 12. Suggested commits

1. `fix(data): classify malformed profile candidates strictly`
2. `fix(data): plan sequential catalogue temporal transitions`
3. `fix(data): preserve catalogue persistence error categories`
4. `feat(data): add repository-aware catalogue diff`
5. `test(data): prove sequential catalogue lifecycle`
6. `test(data): extend catalogue restore verification`
7. `docs(data): document DATA-1.2 review corrections`
8. `docs(data): record corrected DATA-1.2 evidence`

---

# Required final response

Return:

- branch;
- correction starting SHA;
- corrected implementation SHA;
- evidence SHA;
- commits;
- sequential A/B catalogue results;
- temporal predecessor/successor results;
- provider binding comparison method;
- dry-run diff result;
- classification and duplicate test results;
- exact backend result and skips;
- migration and restore results;
- frontend results;
- worktree status;
- updated evidence path.

Push the corrected feature branch. Do not merge or mark accepted.
