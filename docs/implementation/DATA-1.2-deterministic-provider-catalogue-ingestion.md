# DATA-1.2 Deterministic Provider Catalogue Ingestion Evidence

Status: implementation complete; acceptance evidence recorded; review pending. DATA-1.2 is not marked accepted.

## Provenance

- Branch: `feature/data-1-deterministic-provider-catalogue-ingestion`
- Required baseline SHA: `4030955c9be2c370d2ef40082fbb00aea7f7061a`
- Uncommitted starting SHA recorded before hardening: `4030955c9be2c370d2ef40082fbb00aea7f7061a`
- Required baseline ancestry check: `git merge-base --is-ancestor 4030955c9be2c370d2ef40082fbb00aea7f7061a HEAD` exited `0`
- Starting untracked files: none
- Starting staged changed-file list was recorded from `git diff --cached --name-only` because the implementation was already staged and `git diff --name-only` was empty.

## Fixture Evidence

- Fixture directory: `backend/tests/fixtures/upstox/`
- Canonical source: `NSE.canonical.json`
- Deterministic gzip: `NSE.json.gz`
- Accepted fixture regeneration: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python tests/fixtures/upstox/regenerate_fixture.py`
- Hostile fixture generation: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python tests/fixtures/upstox/generate_hostile_fixtures.py --output-dir /tmp/quantkynd-data12-hostile-fixtures`
- Canonical SHA-256: `73021afd2e45483d099b1ce7afb85595f48b27d3e749b41fe264ff2b8eff27d7`
- Compressed SHA-256: `4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7`

The fixture is a schema-faithful sanitized artifact generated from the approved Upstox NSE BOD field contract. No real provider BOD file, account identifier, token, private provider URL, or proprietary full instrument catalogue is committed. It preserves the top-level JSON array and official field names and units required by DATA-1.2, including `expiry` epoch milliseconds and `tick_size` in paise.

## Parser And Profile Summary

- Gzip validation enforces one complete gzip member, CRC validation, compressed/decompressed byte limits, and no symlink source paths.
- JSON parsing uses `ijson.parse(..., use_float=False)` and rejects BOMs, duplicate object keys, nested values, non-array roots, malformed JSON, trailing content, excessive rows, and oversized canonical rows.
- The Upstox Nifty profile streams the artifact twice: first to locate and validate the official underlying row, then to normalize accepted rows and persist outcomes.
- Accepted instrument types are `FUT`, `CE`, and `PE`; unrelated valid NSE rows are persisted as `excluded_by_profile`.
- `expiry` epoch milliseconds are converted through `Asia/Kolkata` to the exchange date.
- Raw `tick_size` `5` normalizes to `Decimal("0.05")`.
- Provider relation resolution is through `underlying_key`, not through display text or exchange token.
- No provider numeric value passes through binary float.

## Determinism Proof

Command:

```text
DATABASE_URL=<local test URL> DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false UV_CACHE_DIR=/tmp/uv-cache uv run pytest -ra tests/instruments tests/persistence/test_catalogue_ingestion_service.py
```

Result:

```text
16 passed in 4.68s
```

Covered: row permutation changes physical occurrence identities only; semantic row identities, normalized catalogue hash, catalogue version ID, instrument version IDs, and mapping IDs remain stable; exact duplicate count does not change catalogue identity; exact bytes under another file name retain the same artifact ID; different gzip bytes with identical decompressed content produce different artifact IDs and the same catalogue ID; JSON object-key order does not change normalized identity; Decimal parsing avoids binary floats.

## PostgreSQL Persistence Proof

Command:

```text
DATABASE_URL=<local test URL> DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false UV_CACHE_DIR=/tmp/uv-cache uv run pytest -ra tests/persistence
```

Result:

```text
64 passed in 12.17s
```

Acceptance-critical DATA-1.2 PostgreSQL tests had zero skips.

## CLI Smoke Tests

Validate-only command:

```text
DATABASE_URL=postgresql+asyncpg://localhost:1/unused UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.ingest_provider_catalogue --profile upstox-nse-nifty-index-derivatives-v1 --file tests/fixtures/upstox/NSE.json.gz --effective-from 2026-08-04T03:45:00Z --validate-only --output json
```

Result: accepted; `ingestion_run_id`, `catalogue_record_id`, and `artifact_object_key` were `null`; no database connection was required.

Dry-run command:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.ingest_provider_catalogue --profile upstox-nse-nifty-index-derivatives-v1 --file tests/fixtures/upstox/NSE.json.gz --effective-from 2026-08-04T03:45:00Z --dry-run --output json
```

Result: accepted; `artifact_object_key` was `null`. Post-run row counts for catalogue ingestion, catalogue, instrument, version, and provider mapping tables were all `0`.

Commit command:

```text
CATALOGUE_ARTIFACT_ROOT=/tmp/quantkynd-data12-cli-artifacts-20260804 UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.ingest_provider_catalogue --profile upstox-nse-nifty-index-derivatives-v1 --file tests/fixtures/upstox/NSE.json.gz --effective-from 2026-08-04T03:45:00Z --idempotency-key DATA-1.2-cli-commit --output json
```

Result: accepted; `ingestion_run_id=sha256:c5fe5f71db378cfb8d6c284535f3975ad857a457dd236847edca5976feb20b5e`; `catalogue_record_id=sha256:6b8821472cbf86838f46974c464502098e224ea1ad9e18791a8069911adc5f72`; `artifact_object_key=sha256/4d/4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7.json.gz`.

Post-commit row counts:

```text
catalogue_ingestion_runs|1
catalogue_memberships|4
catalogue_row_outcomes|5
catalogue_source_artifacts|1
catalogue_versions|1
instrument_versions|4
market_instruments|4
provider_contract_mappings|4
```

Idempotent replay used the same command and idempotency key. Result: accepted with the same run and catalogue record IDs; counts did not increase.

Conflict command changed `--effective-from` to `2026-08-04T04:00:00Z` with the same idempotency key. Result:

```text
{"error": "catalogue_idempotency_conflict", "status": "failed"}
```

Rejected catalogue command used `/tmp/quantkynd-data12-malformed.json.gz`. Result:

```text
{"error": "catalogue_normalization_error", "status": "failed"}
```

Counts stayed unchanged after rejection. Successful profile-exclusion dispositions:

```text
accepted|4
excluded_by_profile|1
```

## Artifact Store Proof

- Commit mode retained the exact compressed fixture content at the content-addressed key derived from compressed SHA-256.
- Retained object SHA-256: `4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7`
- Directory modes: artifact root `700`, `sha256` directory `700`, digest prefix directory `700`.
- Object mode: `600`.
- Temporary-file glob after commit: no `.tmp-*` files.
- Tests verify validate-only and dry-run retain nothing, existing objects are rehashed before idempotent reuse, mismatched existing objects fail closed, symlink source and store-parent traversal fail closed, and database writes are not added on malformed in-profile input.
- Restore verification validates database references. Artifact bytes remain in the external content-addressed store and are not included in database dumps.

## Migration Lifecycle Proof

Commands and results:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run alembic downgrade 20260804_02
Running downgrade 20260804_03 -> 20260804_02

UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
20260804_02
```

After downgrade to `20260804_02`, DATA-1.2 relation checks returned `0` regclass matches while DATA-1.1 rows remained:

```text
catalogue_version_records|1
catalogue_versions|1
instrument_versions|4
market_instruments|4
provider_contract_mappings|4
```

```text
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade 20260804_03
Running upgrade 20260804_02 -> 20260804_03

UV_CACHE_DIR=/tmp/uv-cache uv run alembic downgrade 20260804_02
Running downgrade 20260804_03 -> 20260804_02

UV_CACHE_DIR=/tmp/uv-cache uv run alembic downgrade base
Running downgrade 20260804_02 -> 20260804_01
Running downgrade 20260804_01 ->

UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade 20260804_03
Running upgrade -> 20260804_01
Running upgrade 20260804_01 -> 20260804_02
Running upgrade 20260804_02 -> 20260804_03

UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
20260804_03 (head)

UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
No new upgrade operations detected.
```

Migration revision: `20260804_03`.

## Restore Verification

PostgreSQL clients:

```text
/usr/bin/pg_dump
pg_dump (PostgreSQL) 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1)
/usr/bin/pg_restore
pg_restore (PostgreSQL) 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1)
```

Command:

```text
DATABASE_URL=<local source test URL> DATABASE_RESTORE_TEST_URL=<local restore test URL> DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
```

Result:

```text
status=passed
source_revision=20260804_03
restored_revision=20260804_03
canonical_digest=sha256:fe7f1a4a5e19a61b96674697c17397d16f86c7e3179b004571211787bcbd306f
digest_match=true
semantic_and_record_ids_match=true
representative_query_match=true
dump_removed=true
target_safety_rechecked=true
```

Representative restored DATA-1.2 row counts were all `0` in the verifier fixture state: `catalogue_source_artifacts`, `catalogue_ingestion_runs`, `catalogue_row_outcomes`, and `catalogue_memberships`.

## Full Verification

Backend compile:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
passed
```

Backend tests:

```text
DATABASE_URL=<local test URL> DATABASE_RESTORE_TEST_URL=<local restore test URL> DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false UV_CACHE_DIR=/tmp/uv-cache uv run pytest -ra
400 passed in 19.31s
```

Frontend:

```text
pnpm lint
passed

pnpm build
passed with existing Vite large-chunk warning
```

Dependency lock:

```text
UV_CACHE_DIR=/tmp/uv-cache uv lock --check
Resolved 64 packages in 1ms
```

Repository:

```text
git diff --check
passed
```

Repository artifact tracking check before final staging returned no tracked `__pycache__`, `.pyc`, `node_modules`, `dist`, dump, backup, or provider artifact files. After staging, the only tracked `NSE.json.gz` is expected to be `backend/tests/fixtures/upstox/NSE.json.gz`.

Reasonable pattern scan was run with `rg` across tracked files. It is not a full secret scanner. It reported existing code/test references to token field names, test placeholder tokens, and historical/example database URLs; no Upstox access token, private provider URL, unsanitized provider file, or new DATA-1.2 runtime artifact was identified in this evidence.

## Dependency Ownership

`ijson` is owned by DATA-1.2. Accepted range: `>=3.3,<4`; resolved version: `3.5.1`; resolved lock package count: `64`. Purpose, footprint, license/security consideration, and removal criteria are recorded in `docs/dependencies.md`.

## Remaining Limitations

- Real Upstox BOD files are not committed. Repository acceptance uses the schema-faithful sanitized fixture, and local acceptance may use a user-supplied official `NSE.json.gz`.
- DATA-1.2 does not download provider catalogues, ingest other formats, or introduce live-capital paths.
- DATA-1.2 remains review pending and must not be marked accepted until independent review is complete.
