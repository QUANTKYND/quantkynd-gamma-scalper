# Testing Strategy

## Testing layers

### Pure quantitative tests

Cover formulas with hand-calculated values and independent implementations:

- Log returns and squared returns.
- Horizon variance and annualization.
- Forward targets and information cutoffs.
- Black–Scholes prices.
- Put-call parity.
- IV price round trips.
- Analytical Greeks against finite differences.
- Gamma-theta approximations.
- No-trade band scaling.
- Transaction-cost calculations.
- P&L attribution identities.

### Property tests

Use generated cases for invariants:

- Call price increases with spot and volatility.
- Put price decreases with spot under fixed inputs.
- Gamma and vega are non-negative for standard European vanilla options.
- IV round trips remain within tolerance on valid domains.
- Higher proportional cost does not narrow the baseline no-trade band under fixed state.
- Ledger debits and credits reconcile.
- Duplicate idempotency keys do not create duplicate orders.

### Contract tests

- Pydantic schemas reject undeclared fields.
- API examples validate against OpenAPI.
- Frontend runtime types or generated clients match backend contracts.
- WebSocket event envelopes remain versioned and sequence-aware.
- Broker adapters map provider states into internal states without losing terminal conditions.

### Repository and persistence tests

- Point-in-time contract queries exclude future and expired contracts.
- Quote writes are deduplicated by provider identity and sequence.
- Transactions preserve intent, order, fill, position, and cash invariants.
- Migration upgrade and downgrade behavior is tested where safe.
- Redis loss does not lose durable state.

### Replay tests

- Same dataset, seed, configuration, and source commit produce the same decision stream and terminal result.
- Changing future data does not change earlier decisions.
- Every terminal P&L is reconstructable from events and ledger entries.
- Historical chain selection uses only contracts known at the replay timestamp.

### Failure tests

- Feed disconnect and reconnect.
- Sequence gaps.
- Stale quotes.
- Crossed or invalid markets.
- Missing contracts.
- Broker rejection.
- Timeout after request before acknowledgement.
- Duplicate acknowledgement.
- Partial fill.
- Cancel-replace race.
- Redis restart.
- Postgres unavailability.
- Worker restart.
- Max hedge count breach.
- Daily loss breach.
- Kill-switch engagement.
- End-of-day flatten or carry failure.

## Frontend tests

- RTK Query loading, error, stale, and empty states.
- No direct `useEffect` import in app and feature code.
- User behavior through event handlers.
- Key-based reset behavior.
- `useMountEffect` only for approved external synchronization.
- Large tables render virtualized rows.
- Sequence-gap state triggers snapshot recovery UI.
- Risk lockouts prevent action controls.

## Test data

- Small hand-built fixtures for formulas.
- Deterministic synthetic paths for simulation.
- Wire fixtures for provider payloads.
- Sanitized and legally redistributable market samples.
- Golden decision journals for replay regression.

## Quality gates

Immediate:

```text
pytest
frontend lint
TypeScript build
git diff --check
cache and secret scan
```

Target:

```text
ruff format --check
ruff check
pyright
pytest --cov
pnpm biome check
pnpm test
pnpm build
migration check
OpenAPI contract check
```

Coverage is not a substitute for invariants. Critical money, order, risk, and reconciliation code requires branch and failure-path tests regardless of aggregate coverage.
