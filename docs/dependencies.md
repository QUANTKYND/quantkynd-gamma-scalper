# Dependencies

Dependencies are added only when a milestone requires them. Each dependency must have a clear purpose and an owner. Avoid adding overlapping libraries that solve the same problem.

## Already present

### Backend runtime

| Dependency | Purpose |
|---|---|
| `fastapi[standard]` | HTTP API, validation integration, OpenAPI, and development server tooling. |
| `uvicorn` | ASGI serving. |
| `numpy` | Numerical arrays and quantitative calculations. |
| `pandas` | Time-series research, feature frames, and artifact generation. |
| `pydantic-settings` | Typed environment configuration. |
| `pyyaml` | STRAT-1 owner; safe loading of versioned strategy configuration. Remove if configuration moves to a format supported by the standard library. |
| `httpx` | LIVE-RV-1 owner; explicit asynchronous Upstox search and historical-candle reads with mock-transport testability. Remove only if the provider adapter is replaced by an equally testable owned HTTP boundary. |
| `upstox-python-sdk` | LIVE-RV-1 owner; official V3 protobuf market-feed decoding, subscription management, and bounded reconnect support. Remove when Upstox connectivity is retired or an approved provider-neutral feed adapter replaces it. |
| `sqlalchemy[asyncio]` | DATA-1.1 owner; SQLAlchemy 2 async engine, typed relational mappings, statements, repositories, and transaction sessions. Remove only if the Postgres adapter is replaced with an equivalent explicit persistence boundary. |
| `alembic` | DATA-1.1 owner; reviewed forward and reverse Postgres schema migrations plus metadata drift detection. Remove only with an approved replacement migration system and converted revision history. |
| `asyncpg` | DATA-1.1 owner; async PostgreSQL driver for application repositories and Alembic online migrations. Remove when Postgres or the SQLAlchemy async adapter is retired. |

### Backend development

| Dependency | Purpose |
|---|---|
| `pytest` | Unit and integration testing. |

### Frontend runtime

| Dependency | Purpose |
|---|---|
| `react`, `react-dom` | Operator console UI. |
| `react-router` | Client-side routes. |
| `@reduxjs/toolkit`, `react-redux` | Application state and RTK Query. |
| `@mui/material`, `@mui/icons-material`, Emotion | UI system and styling. |
| `@mui/x-charts`, `recharts` | Research and operations charts. |
| `@mui/x-data-grid` | Large tabular views. |
| `@mui/x-date-pickers`, `dayjs` | Date selection and formatting. |
| `@mui/x-tree-view` | Hierarchical operator views where needed. |
| `@react-spring/web` | Limited UI motion. |

### Frontend development

| Dependency | Purpose |
|---|---|
| `typescript` | Static type checking. |
| `vite`, `@vitejs/plugin-react` | Development and production builds. |
| `eslint`, TypeScript ESLint, React Hooks and Refresh plugins | Current linting baseline. |

## Planned: next research milestones

| Dependency | Phase | Purpose |
|---|---|---|
| `scipy` | Deterministic options engine | Normal distribution functions, numerical root finding, interpolation, and optimization. |
| `hypothesis` | Deterministic options engine | Property tests for parity, monotonicity, round trips, and ledger invariants. |
| `pytest-cov` | Immediate hardening | Coverage reporting and critical-path gates. |
| `ruff` | Immediate hardening | Python formatting and static linting. |
| `pyright` | Immediate hardening | Python type checking. |

## Planned: options-market infrastructure

DATA-1.1 owns SQLAlchemy, Alembic, and asyncpg. It does not add a synchronous driver, retries, calendar packages, or optimized serialization.

| Dependency | Phase | Purpose |
|---|---|---|
| `psycopg` | Data-1 optional | Synchronous CLI, migrations, and recovery utilities if needed. |
| `tenacity` | Data-1 | Bounded retries with explicit policies. |
| `orjson` | Data-1 | Fast event serialization where profiling justifies it. |
| `exchange-calendars` | Data-1 | Exchange-session and holiday logic after NIFTY calendar requirements are validated. |
| `pyarrow` | Backtest-1 | Efficient columnar artifacts and replay datasets. |

## Planned: Redis and live state

| Dependency | Phase | Purpose |
|---|---|---|
| `redis` | Live-1 | Latest-state cache, idempotency, heartbeats, distributed coordination, and event fan-out. |

Redis is not introduced as durable persistence and is not required for the close-to-close RV research module.

## Planned: observability

| Dependency | Phase | Purpose |
|---|---|---|
| `structlog` | Data-1 or Live-1 | Consistent JSON structured logs. |
| `prometheus-client` | Live-1 | Operational metrics. |
| OpenTelemetry packages | Paper-1 | Cross-process traces when multiple workers exist. |

## Planned: frontend quality and performance

| Dependency | Phase | Purpose |
|---|---|---|
| `@biomejs/biome` | Immediate hardening | Formatting, import organization, and selected lint rules. |
| `vitest` | Immediate hardening | Unit and component tests. |
| `@testing-library/react`, `@testing-library/user-event` | Immediate hardening | Behavior-focused component tests. |
| `jsdom` | Immediate hardening | Browser-like test environment. |
| `msw` | Data-1 | API contract and failure-state mocks. |
| `zod` | Data-1 optional | Runtime validation at external browser boundaries if generated OpenAPI types are not sufficient. |

When Biome is adopted, avoid running two competing formatters. ESLint remains only for rules Biome does not cover, including the direct `useEffect` import ban if required.

## Explicitly deferred

- Deep-learning frameworks.
- RL environments.
- Distributed task queues.
- Kafka or another event broker.
- Kubernetes.
- A second dataframe library alongside pandas without a measured need.
- Multiple option-pricing libraries that hide formulas behind inconsistent conventions.
- Prisma for the Python backend.

## Dependency change checklist

A dependency change must document:

- Owning milestone.
- Problem solved.
- Why current dependencies are insufficient.
- Runtime or build impact.
- Security and license considerations.
- Removal or replacement criteria.
- Lockfile update.
- Test evidence.
