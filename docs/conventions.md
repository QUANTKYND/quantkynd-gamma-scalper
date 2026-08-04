# Conventions

## Frontend: no direct `useEffect`

Direct `useEffect` usage is banned in app and feature code.

The five replacements are mandatory:

1. Deriving state from state or props: compute it inline during render.
2. Fetching: use RTK Query.
3. Reacting to user action: use the event handler.
4. Resetting state when a prop changes: use `key` on the component.
5. One-time external synchronization on mount: use the shared `useMountEffect` hook.

### Allowed boundary

The direct React `useEffect` import is permitted only inside the shared implementation of `useMountEffect` and narrowly scoped infrastructure adapters approved in design review.

Target location:

```text
frontend/src/shared/hooks/useMountEffect.ts
```

Target shape:

```ts
import { useEffect } from 'react'

export function useMountEffect(effect: () => void | (() => void)) {
  useEffect(effect, [])
}
```

`useMountEffect` is not used for fetching, derived state, prop-driven resets, or user actions.

### Enforcement

- Add an ESLint restricted-import rule for product code.
- Permit the direct import only in the shared hook implementation.
- Keep RTK Query subscriptions and polling in API slices and middleware.
- Keep WebSocket lifecycle in a shared external-store or middleware boundary, not page components.

## No new code comments

New code carries no explanatory comments.

- Names, types, schemas, and small functions do the explaining.
- Prose and rationale belong in `docs/`.
- Existing comments stay; removing or rewriting them without changing behavior creates noise.
- Generated-file headers remain untouched.
- `biome-ignore` directives are allowed.
- Auto-generated Prisma headers are exempt, although Prisma is not currently planned for the Python backend.

Avoid introducing large functions that would otherwise need comments. Split them by domain meaning.

## Naming

### Python

- Modules and functions: `snake_case`.
- Types and Pydantic models: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Private helpers: leading underscore only when the module owns the abstraction.

### TypeScript

- Components and types: `PascalCase`.
- Functions, variables, hooks, and fields: `camelCase`.
- Constants: `UPPER_SNAKE_CASE` only for immutable module constants.
- Files: `camelCase.ts` for utilities and hooks, `PascalCase.tsx` for components where the existing convention supports it.

### API and persistence

- JSON fields: `snake_case` to match backend schemas unless a future generated-client migration explicitly changes the repository convention.
- URL resources: lowercase kebab-case or plural nouns.
- Enum values: lowercase snake_case.
- IDs: opaque strings.

## Time

- Persist timestamps in UTC.
- Emit timezone-aware ISO 8601 timestamps.
- Interpret NSE session rules in `Asia/Kolkata`.
- Distinguish exchange timestamp, provider timestamp, received timestamp, processed timestamp, and persisted timestamp.
- Trading horizon names use sessions when the definition is session-based. Do not call five sessions five calendar days.
- Option expiry is an exchange date plus explicit settlement convention.

## Quantitative units

- Returns are decimals.
- Horizon variance is cumulative decimal squared return.
- Annualized variance is decimal squared return per year.
- Volatility and IV are annualized decimals; `0.18` means 18%.
- The frontend performs percent formatting.
- Time to expiry in model inputs is years under a declared day-count convention.
- Theta declares whether it is per year, per calendar day, or per trading day.
- Greeks declare whether they are per unit, per contract, or portfolio-scaled.
- Prices, fees, and cash declare currency.

## Financial precision

- Analytics use floating point where numerical libraries require it.
- Durable cash, fees, balances, premiums, and order prices use decimal values or integer minor units.
- Never derive accounting balances from rounded UI values.
- Round only at defined exchange, broker, or display boundaries.

## Research

- Every forecast has an origin, target start, target end, horizon, estimator, model version, feature cutoff, and dataset ID.
- Every research run has immutable configuration, source commit, artifacts, and status.
- No future data may enter features, selection, fills, or quality filters.
- Parameter search and final evaluation use distinct data or nested procedures.
- Failed runs remain visible and explain why they failed.

## Strategy and execution

- Strategy emits intents, not orders.
- Risk approves or rejects intents before routing.
- Execution translates approved intents into broker-shaped orders.
- Every write is idempotent.
- Order transitions are append-only.
- Positions and cash are ledger-derived.
- Unknown or stale state causes hold or stop, never optimistic execution.

## API

- All new procedures are versioned under `/api/v1`.
- Use nouns for resources and action subresources only when the domain action is not CRUD-shaped.
- Status codes carry meaning; do not return HTTP 200 for rejected or malformed writes.
- Undefined statistics are `null`, not zero.
- Collection responses include pagination and provenance where relevant.
- APIs do not silently fall back from live to synthetic market data.

## Frontend rendering

- Compute simple derived state during render.
- Use memoization only after profiling or for referential stability required by a library boundary.
- Use RTK Query selectors and normalized entities for shared state.
- Do not copy query results into component state.
- Do not render every market event; render bounded, coalesced state updates.
- Large tables are virtualized.
- Charts use downsampled or aggregated series appropriate to viewport width.

## Documentation

- Architecture decisions belong in `docs/design.md` or a decision record.
- API changes update `docs/api.md`.
- Model changes update `docs/data-models.md`.
- Dependencies update `docs/dependencies.md`.
- New environment variables update `docs/environment.md` and `.env.example`.
- Milestone status updates the relevant file under `docs/plan/`.
