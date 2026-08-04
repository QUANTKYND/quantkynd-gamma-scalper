# Security and Safety

## MVP safety posture

- Paper-only execution.
- Broker connectivity begins read-only.
- No live-capital order procedure exists in the MVP API.
- The kill switch defaults to engaged when required state is missing.
- Risk evaluation precedes every paper order path.

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

## Data safety

- Research papers and datasets are included only when redistribution is permitted.
- Live broker and market data are retained according to provider licensing.
- Personally identifiable or account-specific broker data is minimized.
- Backups are encrypted and restore-tested.

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
