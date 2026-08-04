# System Design

## Architectural style

The MVP is a modular monolith with separately runnable processes. Domain boundaries are explicit in code, while deployment remains simple enough for one machine and one operator.

Do not create independently deployed microservices until load, reliability, ownership, or scaling requirements justify them.

## System planes

### Research plane

Owns datasets, estimators, forecasts, simulations, backtests, artifacts, experiment manifests, and model comparison.

### Market-state plane

Owns instruments, sessions, quotes, trades, chain snapshots, data-quality events, Greeks, IV surfaces, and current market state.

### Strategy and risk plane

Owns strategy configuration, entry candidates, opportunity scores, hedge decisions, risk decisions, and kill-switch state.

### Execution plane

Owns paper orders, broker-shaped order state, fills, positions, cash ledger entries, reconciliation, and end-of-day controls.

### Observability plane

Owns structured logs, metrics, traces, alerts, immutable decision journals, and operator dashboards.

## Runtime topology

```mermaid
flowchart LR
    UI[React operator console]
    API[FastAPI API]
    PG[(Postgres)]
    REDIS[(Redis)]
    COLLECTOR[Market-data collector]
    LIVE[Live-state worker]
    RESEARCH[Research runner]
    PAPER[Paper execution worker]
    BROKER[Upstox and broker adapters]
    ALERTS[Alert adapters]

    UI -->|HTTP and WebSocket| API
    API --> PG
    API --> REDIS
    COLLECTOR --> BROKER
    COLLECTOR --> PG
    COLLECTOR --> REDIS
    LIVE --> REDIS
    LIVE --> PG
    RESEARCH --> PG
    RESEARCH -->|artifacts| PG
    PAPER --> PG
    PAPER --> REDIS
    PAPER --> BROKER
    API --> ALERTS
    PAPER --> ALERTS
```

## Planned code boundaries

```text
backend/app/
├── api/
├── core/
├── auth/
├── market_data/
├── instruments/
├── volatility/
├── options/
├── surfaces/
├── opportunities/
├── simulation/
├── hedging/
├── strategies/
├── portfolio/
├── execution/
├── risk/
├── reconciliation/
├── observability/
├── schemas/
├── services/
└── cli/

frontend/src/
├── app/
├── features/
├── pages/
├── shared/
│   ├── api/
│   ├── components/
│   ├── hooks/
│   ├── formatting/
│   └── types/
└── store/
```

The existing RV implementation may remain under `quant/` during migration. New domain work should use the target boundaries rather than expanding a generic `quant` package indefinitely.

STRAT-1 and SIM-1 implement the target `strategy`, `options`, `simulation`, `portfolio`, `hedging`, `execution`, and `attribution` boundaries as an offline deterministic research slice. These modules have no FastAPI, broker, Redis, or database dependencies. The simulation CLI coordinates pure analytics and publishes immutable local artifacts.

## Dependency direction

```text
API and CLI
    ↓
Application services
    ↓
Domain policies and analytics
    ↓
Ports and repositories
    ↓
Infrastructure adapters
```

Rules:

- Domain modules do not import FastAPI, broker SDKs, database sessions, Redis clients, or UI contracts.
- API routers validate transport input and call application services.
- Application services coordinate repositories, domain calculations, and policies.
- Infrastructure implements ports for databases, broker APIs, files, Redis, and alerts.
- Pydantic transport schemas are not the durable domain model by default.
- Research calculations are pure functions wherever practical.
- Execution and risk decisions are deterministic for a given state and policy version.

## Primary data flow

```mermaid
flowchart TD
    A[Market events] --> B[Normalization]
    B --> C[Quality policy]
    C -->|accepted| D[Durable event storage]
    C -->|rejected or degraded| E[Data-quality events]
    D --> F[Point-in-time state]
    F --> G[RV and IV analytics]
    G --> H[Opportunity engine]
    H --> I[Strategy policy]
    I --> J[Risk pre-check]
    J -->|approved| K[Trade intent]
    J -->|rejected| L[Risk journal]
    K --> M[Paper order router]
    M --> N[Orders and fills]
    N --> O[Positions and cash ledger]
    O --> P[P&L attribution]
    P --> Q[Dashboard and alerts]
```

## Source-of-truth rules

- Postgres is the durable source of truth for instruments, quotes retained for replay, strategy runs, intents, orders, fills, positions, ledgers, reconciliation, and risk events.
- Immutable research artifacts remain content-addressed files initially and may later be registered in Postgres or object storage.
- Redis is an acceleration and coordination layer, never the only copy of durable trading state.
- The broker is authoritative for broker-acknowledged order and position state once broker integration exists.
- Internal state is reconciled against the broker; it is never assumed correct merely because an order request succeeded.

## State ownership

| State | Owner | Durable | Redis eligible |
|---|---|---:|---:|
| Instrument catalogue | Postgres | Yes | Latest lookup cache |
| Historical quotes | Postgres | Yes | No |
| Latest quotes | Market-state worker | Snapshot and event history | Yes |
| IV surface snapshot | Surface engine | Selected snapshots | Yes |
| Strategy configuration | Postgres and version control | Yes | Read cache |
| Trade intents | Postgres | Yes | Notification only |
| Orders and fills | Postgres and broker | Yes | Latest-state cache |
| Positions and cash ledger | Postgres | Yes | Latest-state cache |
| Kill switch | Postgres with Redis mirror | Yes | Yes |
| UI query cache | RTK Query | No | Browser only |

## Safety boundary

The MVP ends at paper execution. Broker authentication and market-data access do not imply permission to place live-capital orders. A live order adapter must remain absent or disabled by construction until a separate approval and acceptance process exists.

## LIVE-RV-1 read-only slice

LIVE-RV-1 uses one lazy `MarketDataStreamerV3` per backend process. Browser WebSockets terminate at FastAPI, and the in-memory coordinator reference-counts browser interest before changing upstream LTPC subscriptions. SDK callbacks cross into the FastAPI event loop with `call_soon_threadsafe`.

Finalized Upstox daily-close snapshots are immutable, bounded to 50 instruments, and cached for 15 minutes. The live quote store retains only the latest normalized state. It is an acceleration layer, not durable truth. An LTP may extend a finalized price series temporarily for the latest feature display, but never changes the finalized snapshot, forecast evaluation, persisted runs, or dataset identity.

LIVE-RV-1.1 assigns accepted-quote sequences in the coordinator independently per instrument. Normalization produces validated candidates without application sequence numbers. Each instrument subscription has one shared `subscribing`, `subscribed`, or `rejected` entry and readiness future, so concurrent browsers observe the same upstream result and failed entries leave no listeners behind. Selected-instrument status reads that instrument's entry; the status endpoint without an instrument retains aggregate operational status.

WebSocket authentication and exact instrument validation occur before acceptance. Upstream subscription and finalized-history loading occur after acceptance, and `market_state_snapshot` is always the first stream event. The stream concurrently observes browser disconnects and backend events, emits only changed status, coalesces quotes, and obtains refreshed finalized history through the registry with `resync_required` when the India exchange date changes. Provider errors are nonterminal while SDK auto-reconnect remains active: the retained quote becomes stale and the browser stream remains subscribed. Retry exhaustion is terminal, emits `provider_error`, and closes the browser stream with `1011`.
