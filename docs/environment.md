# Environment

## Supported environments

| Environment | Purpose | Market data | Execution |
|---|---|---|---|
| `local` | Developer workflow and synthetic fixtures | Synthetic, fixture, optional broker read-only | Disabled |
| `test` | Unit, property, integration, replay, and failure tests | Deterministic fixtures | Simulated |
| `paper` | Live read-only data and broker-shaped paper trading | Live or delayed provider feed | Paper router only |
| `production-paper` | Stable paper campaign on controlled infrastructure | Live provider feed | Paper router only |

A live-capital environment is outside the MVP.

## Current toolchain

- Python 3.12 or later.
- `uv` for Python dependency and command execution.
- FastAPI and Uvicorn for the backend.
- React, TypeScript, Vite, Redux Toolkit, RTK Query, MUI, and Recharts for the frontend.
- `pnpm` for frontend dependency management because the repository carries a `pnpm-lock.yaml`.
- Docker for reproducible services and deployment.

## Target local services

```text
frontend        5173
backend         8000
postgres        5432
redis           6379
```

Postgres and Redis are added when their owning milestones begin. The RV research baseline may continue to run without them.

DATA-1.1 adds the optional local Postgres service. Redis remains deferred. Database-free research, simulation, API startup, and unit tests remain supported.

## Environment variables

### Application

```text
APP_NAME
API_V1_PREFIX
CORS_ORIGINS
FRONT_URL
LOG_LEVEL
ENVIRONMENT
```

### Upstox authentication and read-only connectivity

```text
BROKER
UPSTOX_CLIENT_ID
UPSTOX_CLIENT_SECRET
UPSTOX_REDIRECT_URI
UPSTOX_LOGIN_URL
UPSTOX_TOKEN_URL
UPSTOX_API_VERSION
UPSTOX_ACCESS_TOKEN_FILE
UPSTOX_STATE_SIGNING_SECRET
UPSTOX_API_BASE_URL
UPSTOX_DEFAULT_INSTRUMENT_KEY
UPSTOX_HISTORY_LOOKBACK_YEARS
UPSTOX_MARKET_DATA_MODE
UPSTOX_STREAM_RECONNECT_INTERVAL_SECONDS
UPSTOX_STREAM_MAX_RECONNECT_ATTEMPTS
UPSTOX_MAX_ACTIVE_INSTRUMENTS
MARKET_DATA_STALE_AFTER_SECONDS
MARKET_DATA_UI_PUBLISH_INTERVAL_MS
RV_LIVE_RECOMPUTE_INTERVAL_MS
RV_FINALIZED_SNAPSHOT_CACHE_SECONDS
```

`UPSTOX_MARKET_DATA_MODE` is restricted to `ltpc`. Counts and durations must be positive, the UI publish interval cannot exceed the RV recompute interval, and the active-instrument limit is capped below the provider limit. The token is loaded lazily when a provider request or first live subscription occurs.

### RV synthetic fallback

```text
RV_SYNTHETIC_SEED
RV_SYNTHETIC_PERIODS
RV_SYNTHETIC_END_DATE
RV_SYNTHETIC_INITIAL_PRICE
```

### Persistence

```text
DATABASE_URL
DATABASE_POOL_SIZE
DATABASE_MAX_OVERFLOW
DATABASE_POOL_TIMEOUT_SECONDS
DATABASE_POOL_RECYCLE_SECONDS
DATABASE_CONNECT_TIMEOUT_SECONDS
DATABASE_STATEMENT_TIMEOUT_MS
DATABASE_APPLICATION_NAME
DATABASE_ECHO
DATABASE_RESTORE_TEST_URL
REDIS_URL
REDIS_KEY_PREFIX
ARTIFACT_ROOT
```

### Paper execution

```text
EXECUTION_MODE=paper
PAPER_FILL_MODEL
PAPER_LATENCY_MS
PAPER_SLIPPAGE_BPS
RISK_POLICY_ID
KILL_SWITCH_DEFAULT=engaged
```

## Secrets

- `.env` files are local only and ignored.
- `.env.example` contains names and safe placeholders, never real credentials.
- Broker tokens and signing secrets are never committed.
- Logs must not contain access tokens, authorization codes, client secrets, account identifiers, or complete broker payloads containing private data.
- Paper and live credentials must never share a storage location.

## Local workflow

Backend:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/tmp/uv-cache uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm build
pnpm dev
```

Research run:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.run_rv_research \
  --symbol NIFTY \
  --model ewma \
  --horizon-sessions 5
```

Strategy validation and offline simulation:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --path-generator gbm --seed 17 --policy constant_band
```

SIM-1 uses no environment secrets, provider token, database, Redis, or execution-mode variable. Its default artifact root is `backend/artifacts/simulation`.

## DATA-1.1 local Postgres

Start the test service from the repository root:

```bash
docker compose up -d postgres
docker compose ps
```

Use local-only values matching `docker-compose.yaml` in `backend/.env`:

```text
DATABASE_URL=postgresql+asyncpg://quantkynd:quantkynd_local@localhost:5432/quantkynd_test
DATABASE_RESTORE_TEST_URL=postgresql+asyncpg://quantkynd:quantkynd_local@localhost:5432/quantkynd_restore
```

Both variables are optional until a database-backed command is invoked. Application URLs must use `postgresql+asyncpg`. The restore verifier refuses equal source and target databases and requires both database names to contain an explicit `test`, `restore`, `dev`, or `local` marker.

From `backend`, migrate or inspect the schema with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
UV_CACHE_DIR=/tmp/uv-cache uv run alembic downgrade base
```

Run the destructive dump/restore acceptance check only against dedicated test-safe databases:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_database_restore
```

## Deployment target

The first stable deployment is one VPS or one controlled host using Docker Compose:

- One frontend container or static asset server.
- One FastAPI container.
- One Postgres container with durable volume and backup.
- One Redis container with persistence configured only for coordination recovery, not as durable trading truth.
- Separate worker processes for collection, live state, and paper execution as they are introduced.

## Reproducibility

Every research and paper run records:

- Git commit.
- Dataset ID.
- Strategy ID and configuration hash.
- Estimator and model versions.
- Environment name.
- Dependency lockfile state.
- Start and completion timestamps.
- Artifact locations.
- Failure reason when incomplete.
