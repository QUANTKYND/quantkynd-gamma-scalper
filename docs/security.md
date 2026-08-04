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
- Restore verification requires distinct source and target URLs, rejects names without a test-safe marker, passes passwords through the child-process environment rather than arguments, suppresses PostgreSQL tool output, and removes its temporary dump automatically.
- The restore target is the only schema the verifier clears; production-shaped database names are rejected before destructive work.
- Dump and backup extensions are ignored, and no database service is required by broker, research, simulation, or unrelated unit-test imports.
