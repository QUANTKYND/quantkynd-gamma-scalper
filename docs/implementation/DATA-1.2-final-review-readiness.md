# Codex Task — DATA-1.2 Final Review Readiness

## Current state

- Branch: `feature/data-1-deterministic-provider-catalogue-ingestion`
- Required baseline: `4030955c9be2c370d2ef40082fbb00aea7f7061a`
- Implementation is local and not yet pushed.
- Evidence status must remain:
  `implementation complete; acceptance evidence recorded; review pending`

Do not mark DATA-1.2 accepted until the branch is committed, pushed, independently reviewed, and the non-trivial restore gate below passes.

---

## 1. Fix the DATA-1.2 restore acceptance gap

The current restore verifier reports zero rows in all DATA-1.2 tables:

```text
catalogue_source_artifacts = 0
catalogue_ingestion_runs = 0
catalogue_row_outcomes = 0
catalogue_memberships = 0
```

That proves schema restoration but does not prove DATA-1.2 durable data, foreign keys, identities, memberships, outcomes, or representative catalogue queries survive dump and restore.

Update the restore verifier so its deterministic source fixture creates a real accepted DATA-1.2 catalogue through the production ingestion service and repositories before `pg_dump`.

The seeded restore fixture must produce non-zero rows in:

```text
catalogue_source_artifacts
catalogue_ingestion_runs
catalogue_row_outcomes
catalogue_memberships
catalogue_versions
catalogue_version_records
market_instruments
instrument_versions
instrument_version_records
provider_contract_mappings
provider_mapping_records
```

At minimum, seed:

- one sanitized Upstox Nifty underlying row;
- one future;
- one call;
- one put;
- one valid out-of-profile row;
- one accepted catalogue;
- one accepted ingestion run;
- accepted and excluded row outcomes;
- memberships for the accepted unique in-profile rows;
- retained artifact reference metadata.

The verifier must compare source versus restored database for:

1. Alembic revision;
2. non-zero row counts for every DATA-1.2 table;
3. canonical digest including all DATA-1.2 durable rows;
4. semantic IDs and temporal record IDs;
5. ingestion run ID and command digest;
6. source artifact ID and object key;
7. row outcome IDs and dispositions;
8. membership IDs and linked instrument/version/mapping IDs;
9. current catalogue resolution;
10. historical `known_as_of` catalogue resolution;
11. current provider-key resolution;
12. historical provider-key resolution;
13. profile-exclusion outcome reconstruction.

The external artifact bytes need not be embedded in the database dump, but the verifier must:

- ensure the source database artifact reference points to an existing hash-valid object before dumping;
- ensure the restored database contains the identical artifact reference;
- verify the same external object remains hash-valid after restore;
- state explicitly that database restore and external artifact backup are separate operational concerns.

A zero-row DATA-1.2 restore fixture is not acceptable.

---

## 2. Strengthen validate-only proof

Rerun validate-only with database configuration genuinely absent:

```bash
env -u DATABASE_URL \
    -u DATABASE_RESTORE_TEST_URL \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run python -m app.cli.ingest_provider_catalogue \
      --profile upstox-nse-nifty-index-derivatives-v1 \
      --file tests/fixtures/upstox/NSE.json.gz \
      --effective-from 2026-08-04T03:45:00Z \
      --validate-only \
      --output json
```

Record:

- exit code;
- JSON result;
- proof that no engine or connection was created;
- proof that no artifact was retained.

Do not use an intentionally invalid `DATABASE_URL` as the final proof that the mode is database-independent.

---

## 3. Record PostgreSQL server/client compatibility

Record:

```bash
psql --version
pg_dump --version
pg_restore --version
```

And from the server:

```sql
SHOW server_version;
```

Document that the acceptance dump/restore used PostgreSQL 18.4 client tools against the actual server version, and record the result. Do not describe the clients as container-provided if host `/usr/bin` clients were used.

---

## 4. Create reviewable commits

Before committing:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --stat
git diff --cached --name-only
```

Create small reviewable commits. Preserve architectural boundaries where practical:

1. parser dependency;
2. domain and identity contracts;
3. Upstox profile and fixture parser;
4. persistence models/repositories;
5. migration `20260804_03`;
6. ingestion service and CLI;
7. fixture and deterministic tests;
8. migration/restore/CLI hardening tests;
9. documentation and review-pending evidence.

Do not create an “accepted” evidence commit yet.

After committing:

```bash
git status --short
git log --oneline --decorate -12
git diff 4030955c9be2c370d2ef40082fbb00aea7f7061a..HEAD --stat
```

The worktree must be clean.

---

## 5. Push the review branch

Push only the feature branch:

```bash
git push -u origin feature/data-1-deterministic-provider-catalogue-ingestion
```

Do not merge into `master`.

Record:

```bash
git rev-parse HEAD
git status --short
git branch -vv
```

The pushed branch head must equal the local implementation/evidence SHA.

---

## 6. Final verification after the restore change

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

Run frontend lint/build and repository checks again after all commits.

Acceptance-critical DATA-1.2 tests must have zero skips.

---

## 7. Evidence update

Update:

```text
docs/implementation/DATA-1.2-deterministic-provider-catalogue-ingestion.md
```

Record:

- branch;
- baseline SHA;
- implementation ending SHA;
- review-pending evidence SHA;
- commit list;
- exact changed-file list;
- non-zero DATA-1.2 restore row counts;
- restored digest and ID/query equivalence;
- external artifact-reference verification;
- validate-only with database variables absent;
- PostgreSQL server and client versions;
- exact full test result and skip summary;
- pushed branch head;
- worktree clean;
- remaining limitations.

Keep status:

```text
implementation complete; acceptance evidence recorded; independent review pending
```

---

## Required final response

Return:

- branch;
- baseline SHA;
- implementation SHA;
- evidence SHA;
- pushed branch SHA;
- commits;
- worktree status;
- non-zero restore counts for all DATA-1.2 tables;
- canonical digest;
- representative query results;
- external artifact-reference verification;
- validate-only no-database result;
- PostgreSQL server/client versions;
- full backend result;
- frontend result;
- evidence path.

Do not merge or mark accepted.
