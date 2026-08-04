# Performance: Redis and Rendering

Performance work follows measurements. The system must remain correct without Redis and must remain understandable without UI micro-optimizations.

## Redis role

Redis is introduced at Live-1 or earlier only when a measured cross-process need exists.

LIVE-RV-1 remains one backend process and intentionally uses bounded in-memory latest quote and finalized-snapshot stores. It supports at most 50 active instrument keys, caches at most 50 finalized snapshots for 15 minutes, coalesces browser quote delivery to 250 ms, and recomputes the provisional RV view no faster than 1000 ms. Redis remains deferred until a multi-process or recovery requirement exists.

Status transitions bypass quote coalescing and emit only when transport, subscription, selected-segment market status, or freshness changes. The backend concurrently waits for browser disconnects without sending unchanged one-second status events. Frontend quote envelopes are coalesced to 250 ms; lifecycle and resync envelopes apply immediately.

Use Redis for:

- Latest accepted underlying and option quote state.
- Latest Greek and IV-surface snapshots.
- Worker heartbeats and liveness.
- Idempotency keys for intent and order routing.
- Short-lived distributed locks where unavoidable.
- Kill-switch mirror for immediate reads.
- Pub/Sub or Streams fan-out to WebSocket gateways.
- Short-lived API response caches for expensive read models.

Do not use Redis as the only copy of:

- Instruments or contracts.
- Historical quotes required for replay.
- Research runs.
- Intents.
- Orders or fills.
- Positions.
- Cash ledger entries.
- Risk decisions.
- Reconciliation results.

## Redis key convention

```text
qk:{environment}:{domain}:{entity}:{id}:{version}
```

Examples:

```text
qk:paper:market:quote:option-123:v1
qk:paper:surface:nifty:latest:v1
qk:paper:worker:live-state:heartbeat:v1
qk:paper:execution:idempotency:intent-456:v1
qk:paper:risk:kill-switch:global:v1
```

## Redis invariants

- Values carry schema version and `updated_at`.
- Latest-state values have bounded TTLs where staleness must become visible.
- A missing or expired key is unknown state, not zero state.
- Durable changes are committed to Postgres before or atomically with cache publication according to the operation design.
- Cache invalidation is explicit by entity version or write event.
- Pub/Sub is for transient notification; Streams are used when consumers require replay and acknowledgement.
- Lua or transactions are limited to small atomic state transitions.

## API caching

Eligible:

- Instrument catalogue lookups.
- Current session calendar.
- Latest read-only market state with a very short TTL.
- Latest surface and opportunity read models.

Not eligible without explicit design:

- Risk approvals.
- Intent creation.
- Order writes.
- Kill-switch writes.
- Reconciliation.

Every cached response exposes source timestamp and freshness.

## Frontend rendering model

The frontend is a Vite client-rendered operator console. Server-side rendering is not required for the MVP.

### State flow

```text
HTTP snapshots and WebSocket deltas
        ↓
RTK Query cache or Redux middleware
        ↓
Normalized latest state
        ↓
Memoized selectors where measured
        ↓
Bounded component rendering
```

### No event-by-event rendering

Market feeds may update faster than a human-readable dashboard. The browser renders coalesced state, not raw event frequency.

Recommended UI refresh classes:

| View | Target refresh |
|---|---:|
| Connection and stale-feed status | Immediate to 250 ms |
| Net Greeks and risk limits | 100–250 ms |
| Position and order tables | On state change, batched within 100 ms |
| Quote table | 100–250 ms with row virtualization |
| Charts | 250–1000 ms depending on horizon |
| Research history | Request-driven |

Batch high-frequency deltas in middleware and publish one render-state update per interval or animation frame.

## Table rendering

- Use MUI X Data Grid virtualization.
- Provide stable row IDs.
- Avoid rebuilding column definitions during render.
- Render only required columns for the active workspace.
- Paginate historical data on the server.
- Keep latest-state tables separate from historical audit tables.

## Chart rendering

- Downsample on the backend or selector layer according to viewport width.
- Preserve extrema and event markers during downsampling.
- Avoid passing thousands of unchanged object instances after each tick.
- Use separate series for state estimates and event markers.
- Load heavy chart routes lazily.
- Disable decorative animation on high-frequency operational charts.

## RTK Query

- Use RTK Query for all HTTP fetching.
- Use tags for explicit invalidation.
- Prefer polling only for low-frequency operational state when WebSocket is unnecessary.
- Keep WebSocket updates inside `onCacheEntryAdded`, middleware, or a shared external-store adapter rather than page effects.
- Do not copy RTK Query data into local state.

## Render-performance budget

Target on a normal operator workstation:

- Initial dashboard interactive within 2 seconds on local or LAN paper deployment.
- User input response below 100 ms.
- Normal live update commits below 16 ms where practical and below 50 ms at the 95th percentile.
- No unbounded DOM growth.
- No chart receives more points than it can display meaningfully.
- Memory remains stable over a full trading session.

## Backend-performance budget

Initial paper-MVP targets:

- Latest-state read API: p95 below 100 ms on LAN deployment.
- Risk evaluation: p95 below 50 ms excluding external calls.
- Intent persistence: p95 below 100 ms.
- Live-state processing lag: visible and normally below the configured freshness threshold.
- Research jobs are isolated from live-state latency through process separation and resource limits.

Performance budgets are operational targets, not trading latency claims.

## Offline simulation

SIM-1 accumulates typed records during a run and creates DataFrames only while writing artifacts. Policy decisions and pricing are linear in path length, and one path remains single-threaded to preserve straightforward determinism. Redis and parallel path execution remain unnecessary.
