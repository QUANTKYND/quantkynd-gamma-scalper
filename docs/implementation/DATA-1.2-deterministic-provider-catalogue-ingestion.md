# DATA-1.2 Deterministic Provider Catalogue Ingestion Evidence

DATA-1.2 status: ACCEPTED

## Independent Acceptance — 2026-08-05

Independent review accepted corrected implementation SHA `0f6543e65b359eda731ca8a49aea95691a40e975` and reviewed evidence SHA `1f3e94bf55d2aa4b1e098e1228d6ff5cc14d6efc`. The review inspected the published commits, commit-specific source, temporal resolver, PostgreSQL lifecycle tests, restore verifier, documentation, and acceptance evidence. It found no remaining correctness, architecture, research-validity, security, or operational blocker within DATA-1.2's approved scope. The reviewer did not independently execute the test suite; acceptance relies on the committed PostgreSQL 17.10 evidence reporting `443 passed`, zero skips, migration head `20260804_03`, and restore digest `sha256:941b2c94406bd8b0d3555d8fd1090a2c73a6622ce0656d3ff200a1b7a48af6e6`.

## Transitive Market-Time Supersession Correction — 2026-08-05

- Branch: `feature/data-1-deterministic-provider-catalogue-ingestion`
- Correction starting SHA: `b4421125f19f7cc4467f66ca7ecc2b5d2a8dd840`
- Required ancestor: `4030955c9be2c370d2ef40082fbb00aea7f7061a`
- Corrected implementation SHA: `0f6543e65b359eda731ca8a49aea95691a40e975`

Implementation commits through the corrected implementation SHA:

```text
d8758fb fix(data): apply transitive market-time supersession
8e5b703 test(data): prove overlapping historical catalogue correction
0f6543e test(data): restore overlapping historical lineage
```

The visible knowledge graph is filtered and fully validated before market selection. Every eligible record then walks its immutable predecessor chain and suppresses every eligible ancestor it encounters. An eligible descendant therefore suppresses all eligible ancestors in its visible lineage even when one or more intermediate records are market-ineligible. Supersession edges, not timestamp comparison, define lineage order. No eligible records returns no result. Eligible records in separate roots or otherwise unordered by the validated lineage remain an explicit ambiguity. Missing targets, cross-scope edges, branches, cycles, non-increasing knowledge time, deterministic ordering, and current knowledge-leaf resolution are unchanged.

The PostgreSQL lifecycle and restore fixture use A open from `2026-08-04T03:45:00Z`, B open from `2026-08-05T03:45:00Z`, and H bounded to `[2026-08-04T12:00:00Z, 2026-08-04T18:00:00Z)`, recorded in A→B→H knowledge order. At `2026-08-04T13:00:00Z`, catalogue, instrument-version, and mapping reads return A before H is known and H after H is known despite ineligible B between them. At B's start they return B; between A's start and H, and between H's end and B, they return A. The graph retains one catalogue root with two successors and four version/mapping roots with eight successors, without ambiguity. A same-effective-time successor after B remains selected as the latest eligible descendant.

Baseline verification switched to the required branch, completed `git pull --ff-only` as already up to date, confirmed exact starting SHA `b4421125f19f7cc4467f66ca7ecc2b5d2a8dd840`, found a clean worktree, and passed the required-ancestor check. Pure temporal resolver tests returned `16 passed`; the PostgreSQL catalogue lifecycle suite returned `23 passed`; both had zero skips. The complete declared-PostgreSQL-17 backend suite returned `443 passed in 30.14s` with zero skips. Compileall passed, Alembic reported `20260804_03 (head)` and no pending upgrade operations, and frontend lint/build passed with only the existing Vite large-chunk warning.

The final PostgreSQL 17 restore digest is `sha256:941b2c94406bd8b0d3555d8fd1090a2c73a6622ce0656d3ff200a1b7a48af6e6`. Source and restored reads were equal. Representative semantic IDs were:

```text
                         before H known                                                    after H known                                                     current at B
catalogue                sha256:658275c2a976e0403ea1b9087d2fdba069973be83b750435ab697ec71f2cd418  sha256:4f08958a1b246a26d27ccaa299ba0c1c17bec9221f4e30a9048fee42915799c4  sha256:4c799f3f16b2784871e03187e7bb5bd95b42991b1e05eb8e19b0adcae7606252
instrument version       sha256:63bdb4de19b1bcdb2034a6574837d7b5b135f34bffa53029b1b78142750492e3  sha256:2a074dbded152abf0d74079d2b952b0ee8710fe056e1e8be73325c6765f9499d  sha256:b24ecf720a0ae3ad604966e88ef2b1287f2b355ffb82c69e1b7151fbbf10e3dd
provider mapping         sha256:5bc5c3a144a1e718f87a47c6e5a468eae92e8c85bc5d449e2cc20c77ae10c98a  sha256:42b94f265ddc26f4ed7cf7dfc0bfd16329558c2c37843ccec70118b9838e948b  sha256:af806598ebae4bb8ea1e0e369d5a88915a7cd182635f530da22041aca60ebc29
```

The restore contained three non-zero DATA-1.2 ingestion runs, twelve memberships, fifteen row outcomes, and three source artifacts. Digest, semantic/record IDs, representative queries, provider binding, successor edges, and artifact hashes matched; the temporary dump was removed. Server, `psql`, `pg_dump`, and `pg_restore` were PostgreSQL `17.10`; the server was the declared Alpine image build on `x86_64-pc-linux-musl`.

## Final Point-in-Time Corrections — 2026-08-05

- Branch: `feature/data-1-deterministic-provider-catalogue-ingestion`
- Correction starting SHA: `854cdd62f1c136a32b81b32f8c832cc300d46a00`
- Required ancestor: `4030955c9be2c370d2ef40082fbb00aea7f7061a`
- Corrected implementation SHA: `0804218d387613381fc4efbeba3a7e3d74b5a009`

Correction commits through the implementation base:

```text
cb1fad2 fix(data): assign catalogue knowledge time at acceptance
dd6564f fix(data): resolve current temporal knowledge leaves
8ed0afc test(data): prove historical catalogue corrections
0804218 test(data): verify DATA-1.2 on PostgreSQL 17
```

### Timestamp Boundary

The command captures `started_at` on invocation, then validates, parses, normalizes, and retains the artifact before opening the durable transition. Commit mode acquires the provider/profile advisory lock and completes the idempotency check before capturing one accepted write timestamp immediately before transition planning. A pure time-binding operation applies that timestamp to the catalogue, every instrument version, and every provider mapping without changing their semantic IDs. Their temporal record IDs are then derived from those accepted knowledge records. The accepted run uses the same `recorded_at` and enforces `started_at <= recorded_at <= completed_at`.

Validate-only and dry-run capture invocation time for the ephemeral semantic plan but never request or persist a durable knowledge timestamp. A `known_as_of` cutoff between invocation and acceptance cannot see the new catalogue; a cutoff at or after acceptance can see it when its market interval is eligible.

### Current Knowledge-Leaf Transitions

Transition planning no longer applies the incoming `effective_from` while choosing predecessors. Persistence-independent repository operations load and validate the entire visible temporal graph and resolve the single current unsuperseded knowledge leaf for the provider/profile catalogue scope, each economic instrument-version scope, and each provider/key mapping scope. Missing targets, multiple roots or leaves, branches, cycles, cross-scope edges, and non-increasing knowledge time fail closed.

The first catalogue is allowed only when its provider/profile scope has no record. Every later catalogue explicitly names the current catalogue knowledge leaf; a missing, stale, root-but-not-leaf, or unrelated predecessor is rejected. New versions and mappings for existing scopes supersede their current knowledge leaves. Stable provider-key binding to one durable economic instrument remains mandatory across all history.

Market selection remains a separate read concern. After applying `known_as_of` and validating the graph, the repositories apply interval eligibility. Every eligible descendant hides all eligible ancestors in its visible predecessor chain, including through ineligible intermediate records. Forward and same-effective-time corrections select the later-known successor when admitted. Open and bounded historical corrections replace eligible ancestors inside their intervals after they are known, while the applicable ancestor remains selected outside those intervals. Earlier knowledge cutoffs reproduce the earlier lineage state.

### Final PostgreSQL 17 Acceptance Evidence

The initial branch, head, worktree, and ancestry checks found branch `feature/data-1-deterministic-provider-catalogue-ingestion`, exact correction starting SHA `854cdd62f1c136a32b81b32f8c832cc300d46a00`, a clean worktree, and required ancestor `4030955c9be2c370d2ef40082fbb00aea7f7061a`. The cached remote feature-branch ref also equalled the correction starting SHA. Two `git pull --ff-only` attempts could not pass the environment's automatic escalation review before timeout; no local or cached-remote state changed.

The declared `postgres:17-alpine` service supplied:

```text
server: PostgreSQL 17.10 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
psql: PostgreSQL 17.10
pg_dump: PostgreSQL 17.10
pg_restore: PostgreSQL 17.10
```

Migration acceptance upgraded to `20260804_03`, downgraded to `20260804_02`, re-upgraded to `20260804_03`, reported `20260804_03 (head)`, and returned `No new upgrade operations detected.` The complete backend result was:

```text
python -m compileall -q app tests: passed
pytest -ra: 443 passed in 30.14s; 0 skipped
```

Exact acceptance commands, with the two local disposable PostgreSQL URLs redacted, were:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
DATABASE_URL=<local-quantkynd_test-url> UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
DATABASE_URL=<local-quantkynd_test-url> UV_CACHE_DIR=/tmp/uv-cache uv run alembic downgrade 20260804_02
DATABASE_URL=<local-quantkynd_test-url> UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
DATABASE_URL=<local-quantkynd_test-url> DATABASE_RESTORE_TEST_URL=<local-quantkynd_restore-url> DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false CATALOGUE_ARTIFACT_ROOT=/tmp/quantkynd-data12-pg17-full-artifacts UV_CACHE_DIR=/tmp/uv-cache uv run pytest -ra
DATABASE_URL=<local-quantkynd_test-url> UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
DATABASE_URL=<local-quantkynd_test-url> UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
DATABASE_URL=<local-quantkynd_test-url> DATABASE_RESTORE_TEST_URL=<local-quantkynd_restore-url> DATABASE_ALLOW_DESTRUCTIVE_TEST_OPERATIONS=true DATABASE_EXPECTED_INTEGRATION_TEST_NAME=quantkynd_test DATABASE_EXPECTED_RESTORE_TEST_NAME=quantkynd_restore DATABASE_ALLOW_NONLOCAL_DESTRUCTIVE_OPERATIONS=false CATALOGUE_ARTIFACT_ROOT=/tmp/quantkynd-data12-pg17-final-artifacts UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
cd ../frontend
pnpm lint
pnpm build
cd ..
git diff --check
git status --short
```

The acceptance-critical catalogue service subset separately returned `23 passed` with zero skips. Its deterministic clock proof used invocation `2026-08-05T10:00:00Z`, acceptance `2026-08-05T10:05:00Z`, and completion `2026-08-05T10:05:02Z`. Every new catalogue, instrument-version, mapping, and run knowledge record used the acceptance timestamp; a cutoff inside the five-minute pre-acceptance interval returned no catalogue, while the acceptance cutoff returned the market-eligible catalogue.

Forward A→B returned A before B was known, A when B was known but not market-eligible, and B after both cutoffs admitted it. Open historical H explicitly superseded A's knowledge leaf and became the unambiguous eligible value after it was known. Bounded historical H returned no value at the earlier knowledge cutoff, returned H inside its bounded interval after acceptance, and continued returning A for the current interval. Missing predecessors, stale A after B, and provider-key economic reassignment failed closed. A later-known correction at B's same `effective_from` succeeded only with B's current record ID.

The final restore fixture contains A, forward B, and bounded historical H. Exact temporal counts are:

```text
scope                 roots  successors
catalogue                 1           2
instrument versions       4           8
provider mappings         4           8
```

The PostgreSQL 17 `pg_dump`/`pg_restore` verification returned:

```text
source_revision=20260804_03
restored_revision=20260804_03
canonical_digest=sha256:941b2c94406bd8b0d3555d8fd1090a2c73a6622ce0656d3ff200a1b7a48af6e6
catalogue_ingestion_runs=3
catalogue_memberships=12
catalogue_row_outcomes=15
catalogue_source_artifacts=3
catalogue_version_records=5
catalogue_versions=5
instrument_version_records=16
instrument_versions=16
provider_contract_mappings=14
provider_mapping_records=14
digest_match=true
semantic_and_record_ids_match=true
representative_query_match=true
catalogue_representative_query_match=true
provider_binding_continuity=true
artifact_reference_hash_valid=true
dump_removed=true
target_safety_rechecked=true
```

Before H was known, the overlapping historical catalogue, instrument-version, and mapping queries returned A. After H was known, the same queries returned H through ineligible intermediate B. At B's market start, the three queries returned B. Source and restored results were identical; exact semantic IDs are recorded in the transitive-correction evidence above.

Frontend `pnpm lint` passed. `pnpm build` passed under Vite `8.2.0`; the existing warning for a minified chunk larger than 500 kB remained. `git diff --check` passed. The evidence commit, final pushed branch SHA, and clean post-push worktree are reported in the implementation handoff because a commit cannot contain its own SHA. PostgreSQL 18.4 results below remain supplementary and do not replace this PostgreSQL 17 acceptance run. DATA-1.2 status: ACCEPTED.

## Review Correction Evidence — 2026-08-05

- Correction branch: `feature/data-1-deterministic-provider-catalogue-ingestion`
- Reviewed branch head and correction starting SHA: `643a9b2ee8e5b3b8f09a8ff7ee8350bddb3c6660`
- Required ancestor: `4030955c9be2c370d2ef40082fbb00aea7f7061a`
- Corrected implementation SHA: `c5dc29b9730bc0e9f80832d9bf6eb7863d957e35`
- Review-pending evidence base SHA: `68a12126b3aaf7a70b7b9eeff13107d4a195f8a5`
- The correction started with related uncommitted edits in seven backend files supplied in the workspace. They were preserved, reviewed, completed, tested, and divided into the commits below.

Correction commits:

```text
e362ea9 fix(data): classify malformed profile candidates strictly
a2984c6 fix(data): plan sequential catalogue temporal transitions
1b0d3c2 fix(data): preserve catalogue persistence error categories
fadce82 feat(data): add repository-aware catalogue diff
38ec814 test(data): prove sequential catalogue lifecycle
c5dc29b test(data): extend catalogue restore verification
68a1212 docs(data): document DATA-1.2 review corrections
docs(data): record corrected DATA-1.2 evidence
```

### Corrected Sequential Lifecycle

The real-PostgreSQL lifecycle suite ingested catalogue A and then catalogue B with an explicit catalogue predecessor. The four provider keys remained bound to the same four economic instrument IDs while B produced new provenance-bound catalogue, version, and mapping IDs. B's catalogue record superseded A's catalogue record; all four B instrument-version records superseded their eligible A records; and all four B mapping records superseded their eligible A records. The resulting graph had four version roots and four version successors, plus four mapping roots and four mapping successors, with no ambiguous eligible leaves.

Historical checks returned A before B was known, A after B was known but before B was market-effective, and B only when both knowledge and market cutoffs admitted it. A changed futures display symbol was classified as one `metadata_changed` row without changing economic identity. A missing predecessor member was reported as disappeared and remained open, eligible, and unsuperseded. Reusing a provider key with a changed strike was rejected by comparing its durable historical economic `instrument_id`, not its catalogue-bound version ID.

The B dry-run used the same locked repository transition plan as commit and returned:

```json
{
  "added": 0,
  "unchanged": 3,
  "metadata_changed": 1,
  "provider_mapping_changed": 0,
  "disappeared": 0,
  "excluded": 1,
  "exact_duplicates": 0
}
```

Dry-run retained no artifact and wrote no catalogue, instrument, version, mapping, run, outcome, or membership rows. Separate tests proved informational disappearance, competing-root and competing-successor serialization, and exact concurrent replay as one commit plus one verified idempotent success.

### Corrected Classification, Duplicate, Numeric, And Failure Behavior

- The exact approved underlying key and every row with the approved `underlying_key` are candidates before schema validation.
- Missing or unsupported candidate instrument type, underlying type, exchange, segment, and required underlying fields reject the catalogue.
- Other-index and stock derivatives remain exclusions.
- Exact raw duplicates remain `exact_duplicate`; a non-identical row reusing one provider key rejects even when its normalized projection is equal.
- Two provider keys can identify one economic contract only when their version metadata is consistent.
- Expiry conversion uses integer `divmod` plus UTC epoch `timedelta`; booleans, fractional values, negative values, and out-of-range values reject. Exchange-local midnight boundary tests pass.
- A fresh transaction interprets a failed write as idempotent only when an accepted run has the same key, command digest, and immutable command inputs. Semantic collisions, unrelated integrity failures, and temporal successor conflicts retain their original category when no accepted run exists.

Focused parser/profile result:

```text
28 passed
```

Acceptance-critical catalogue service result:

```text
17 passed; 0 skipped
```

### Corrected Restore Evidence

The restore verifier seeded two accepted catalogue runs through the production ingestion service, using two retained compressed source artifacts. It verified the A→B catalogue edge, all four version edges, all four mapping edges, historical A reads, current B reads, economic binding continuity, both audit histories, and both hash-valid external artifact references before and after restore.

```text
source_revision=20260804_03
restored_revision=20260804_03
canonical_digest=sha256:d91e846443058ba1a5e6e3307f72057e5b0928ae22615ef234b0b96b9fa0dd5a
catalogue_ingestion_runs=2
catalogue_memberships=8
catalogue_row_outcomes=10
catalogue_source_artifacts=2
catalogue_version_records=4
catalogue_versions=4
instrument_version_records=12
instrument_versions=12
market_instruments=7
provider_contract_mappings=10
provider_mapping_records=10
digest_match=true
semantic_and_record_ids_match=true
representative_query_match=true
catalogue_representative_query_match=true
provider_binding_continuity=true
artifact_reference_hash_valid=true
dump_removed=true
target_safety_rechecked=true
```

The totals include the pre-existing DATA-1.1 deterministic temporal fixture plus the two DATA-1.2 catalogues. Database restoration preserves artifact references; external artifact backup remains a separate operational responsibility.

### Corrected Full Verification

```text
backend compile: passed
backend tests: 430 passed in 14.26s; 0 skipped
alembic current: 20260804_03 (head)
alembic check: No new upgrade operations detected.
frontend lint: passed
frontend build: passed with the existing Vite large-chunk warning
```

Validate-only ran from `/tmp` with `DATABASE_URL`, `DATABASE_RESTORE_TEST_URL`, and `CATALOGUE_ARTIFACT_ROOT` absent. It exited `0`, returned `status=accepted`, four accepted unique rows, one exclusion, and null run, catalogue-record, and artifact keys. The unit boundary test also proves that validate-only never constructs a database engine.

Earlier supplementary evidence used PostgreSQL `18.4` server with host `/usr/bin` `psql`, `pg_dump`, and `pg_restore` version `18.4`. The final acceptance evidence above supersedes it with the declared PostgreSQL 17 service and PostgreSQL 17.10 client tools.

The final evidence commit, pushed branch SHA, and clean worktree are reported in the implementation handoff because a Git commit cannot contain its own SHA. DATA-1.2 status: ACCEPTED.

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

The restore verifier now drops and recreates the source public schema, migrates it to head, seeds the DATA-1.1 temporal fixture, and then creates a real accepted DATA-1.2 catalogue through the production ingestion service before `pg_dump`. The restore comparison includes non-zero DATA-1.2 row counts, canonical digest equality, ingestion run and command digest equality, source artifact and object-key equality, row outcome and disposition equality, membership and linked instrument/version/mapping equality, current and historical catalogue resolution, current and historical provider-key resolution, and profile-exclusion reconstruction. The verifier also checks that the database artifact reference points to an existing hash-valid external object before dump and after restore.

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

Database restore and external artifact backup remain separate operational concerns. The database dump stores the content-addressed artifact reference; artifact bytes remain in the external content-addressed store and must be backed up by the artifact-store operational path.

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
- DATA-1.2 status: ACCEPTED.
