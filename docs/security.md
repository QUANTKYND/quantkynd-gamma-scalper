# Security and Safety

## MVP safety posture

- Paper-only execution.
- Broker connectivity begins read-only.
- No live-capital order procedure exists in the MVP API.
- The kill switch defaults to engaged when required state is missing.
- Risk evaluation precedes every paper order path.
- STRAT-1 accepts simulation mode only; SIM-1 is offline and has no broker or order-placement adapter.

## Secrets

- Broker credentials and tokens are never committed.
- OAuth state is signed, expiring, and one-time.
- Shared OAuth nonce state moves from process memory to Redis before multiple API workers are used.
- Saved tokens are encrypted at rest before non-local deployment.
- Secret values are redacted from configuration APIs and logs.

## Network boundaries

- Postgres and Redis are not exposed publicly.
- Operator APIs are bound to private network or protected by authentication.
- CORS uses explicit origins outside local development.
- WebSocket connections authenticate and authorize scopes.
- Admin procedures such as catalogue import, surface rebuild, run start, kill-switch release, and reconciliation require operator authorization.
- Browser clients connect only to the FastAPI market-state gateway. Upstox tokens, SDK configuration, and provider WebSocket authorization remain server-side.

LIVE-RV-1 is read-only. Its provider protocols expose instrument search, instrument resolution, historical closes, and live subscription lifecycle only. No order client, order procedure, portfolio write, or execution route exists.

WebSocket denials and closes use stable internal codes and generic safe text. They never include access tokens, authorized provider URLs, OAuth codes, raw SDK errors, or provider response bodies. Browser socket lifecycle state contains only the application close code and UTC close time.

## Data safety

- Research papers and datasets are included only when redistribution is permitted.
- Live broker and market data are retained according to provider licensing.
- Personally identifiable or account-specific broker data is minimized.
- Backups are encrypted and restore-tested.
- Simulation artifact roots validate deterministic run IDs and publish only beneath the configured run-store root; configuration uses safe YAML loading and rejects extra fields.

## Execution safety

- Idempotency keys are mandatory for state-changing execution procedures.
- Unknown acknowledgement state blocks automatic resubmission until reconciled.
- Retry policies distinguish safe reads from unsafe writes.
- Order replacement is cancel-replace with explicit state, never in-place assumption.
- Manual actions pass through the same risk and journal boundaries as strategy actions.
- A stale quote cannot produce a new entry or routine hedge.

## Change safety

- Strategy and risk configurations are versioned and hashed.
- Production-paper deployment identifies the exact source commit.
- Database migrations are reviewed and backed up.
- Dependency changes receive security and license review.
- Generated artifacts and secret scans run before release.

## DATA-1.1 database safety

- Database URLs are typed secrets and are never emitted in health, migration, or restore errors.
- Postgres binds to localhost in the development Compose service and uses committed credentials only for isolated local test databases.
- Destructive tests default to denied. They require an explicit opt-in, an exact configured database name equal to `current_database()`, a loopback host or separate non-local override, and a matching purpose-specific sentinel in `quantkynd_control`.
- The sentinel is created only by an explicit bootstrap command, never by destructive verification. Missing, malformed, wrong-name, wrong-purpose, wrong-version, or wrong-owner sentinel data fails closed.
- A stable PostgreSQL advisory lock is held before sentinel revalidation and destructive SQL. Concurrent destructive runs against one database are refused.
- Restore verification compares configured endpoints plus connected database/server identity, refuses a source/target alias to the same physical database, passes passwords only through the child environment, suppresses tool output, and removes its temporary dump automatically.
- Only the verified restore target's `public` schema is replaced. The protected control schema survives and is revalidated after restore.
- Dump and backup extensions are ignored, and no database service is required by broker, research, simulation, or unrelated unit-test imports.

## DATA-1.2 catalogue artifact safety

- Catalogue ingestion is local-file only for the approved Upstox BOD NSE `NSE.json.gz` profile. Provider downloads, URLs, authenticated acquisition, ZIP, CSV, and live endpoints are not part of DATA-1.2.
- The ingester refuses unsafe symlink inputs, invalid gzip members, concatenated gzip members, invalid UTF-8, UTF-8 BOM, duplicate JSON object keys, non-standard JSON constants, and configured byte-limit breaches.
- Commit mode stores exact compressed artifacts in a content-addressed object layout under `CATALOGUE_ARTIFACT_ROOT` with owner-only permissions and atomically verifies existing objects before treating retention as idempotent.
- Postgres stores artifact hashes and relative object keys, not raw provider payload blobs. A transaction rollback may leave an unreferenced content-addressed artifact, but accepted database rows must not point to a missing or hash-invalid object.
- Upstox `instrument_key` is the provider mapping key. `exchange_token` is provenance only and never provider identity.

## DATA-1.3 normalization safety

- The official Upstox V3 Proto, generated Python, generated stub, descriptor, generator version, and runtime ownership are hash-verified locally before fixture normalization. There is no runtime download.
- Frames are immutable and hash-checked, capped at 16 MiB, 5,000 feeds, 256 status segments, and 30 depth levels. Failure reasons and lifecycle reasons are controlled; lifecycle reasons reject token, URL, traceback, socket, account, user, and exception detail.
- Fixtures are synthetic and contain no token, authorized WebSocket URL, account/user identifier, or complete proprietary capture. Raw frame bytes are never emitted by the CLIs.
- Offline normalization uses no network, database, Redis, pickle, `eval`, or shell execution. The repository resolver is read-only and never commits. DATA-1.3 adds no migration, raw/event persistence, live subscription wiring, or order route.
