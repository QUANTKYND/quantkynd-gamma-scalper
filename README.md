# QuantKynd Gamma Scalper

## Close-to-close volatility research

The current RV module implements a daily close-to-close volatility fallback for
research and dashboard monitoring. It uses positive daily closing prices,
log returns, and squared-return accumulation. It does not implement intraday
realized variance yet.

For closing price `P_t`, the log return is:

```text
r_t = log(P_t / P_{t-1})
```

The horizon realized variance ending at session `t` over `h` completed sessions
is:

```text
RV_{t,h} = sum_{j=0}^{h-1} r_{t-j}^2
```

Annualized variance and volatility are:

```text
AV_{t,h} = (252 / h) * RV_{t,h}
VOL_{t,h} = sqrt(AV_{t,h})
```

Forecasts use an end-of-day origin convention. A forecast made after the close
of session `t` may use information through `t` and targets sessions `t+1`
through `t+h`:

```text
RV_forward_{t,h} = sum_{j=1}^{h} r_{t+j}^2
AV_forward_{t,h} = (252 / h) * RV_forward_{t,h}
```

The dashboard displays volatility as percentages. Variance values remain decimal
squared-return quantities in the API.

## Synthetic data

When `backend/data/NIFTY.csv` is unavailable or invalid, the backend serves a
deterministic synthetic daily-close dataset. The synthetic-data badge means the
charts are generated from that fallback, not live market data. Synthetic
generation is controlled by:

```text
RV_SYNTHETIC_SEED=17
RV_SYNTHETIC_PERIODS=720
RV_SYNTHETIC_END_DATE=2025-12-31
RV_SYNTHETIC_INITIAL_PRICE=24000
```

The dataset ID is a stable SHA-256 hash over the symbol, ordered timestamps,
ordered prices, source, frequency, and synthetic parameters.

## Backend tests

From the repository root:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

## Persist an RV research run

From `backend`:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.run_rv_research \
  --symbol NIFTY \
  --model ewma \
  --horizon-sessions 5
```

Completed runs are written under `backend/artifacts/rv/runs/<run-id>/` with:

```text
manifest.json
summary.json
forecast-history.csv
features.csv
```

`GET /api/v1/rv/backtest/runs` reads these manifests. If no persisted manifests
exist, it returns an empty list.

## Dashboard

From `frontend`:

```bash
npm run lint
npm run build
npm run dev
```

The realized-volatility workspace can select NSE/BSE indices and equities from Upstox. Historical RV and all forecast evaluation use finalized daily candles only. During a later exchange session, an LTPC quote may create one visibly provisional feature point and update the latest cards; it never changes the finalized dataset hash or persisted research runs.

Live quote sequences are process-local and monotonic per instrument. Concurrent browser subscriptions share one upstream readiness result. The browser displays explicit connecting, open, failed, and closed socket state, retains the last live state as stale after failure, and resynchronizes finalized RV state when the India exchange date rolls over.

Copy `backend/.env.example`, configure Upstox OAuth, authenticate through the existing login control, and run the read-only provider check from `backend`:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.verify_upstox_market_data \
  --instrument-key "NSE_INDEX|Nifty 50" \
  --listen-seconds 30
```

## Deterministic option and hedge simulation

The frozen simulation-only strategy validates from `backend` with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
```

Run any benchmark policy on the same seeded path with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.run_gamma_simulation \
  --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml \
  --market-config ../config/simulation/nifty-synthetic-market-v1.yaml \
  --path-generator gbm --seed 17 --policy constant_band
```

The strategy contract defines trading behavior while the simulation-market contract defines the deterministic session clock, synthetic chain, expiries, strike grid, liquidity, multipliers, and futures convention. The CLI reports the underlying-path and derived executable-market-state hashes alongside every other run identity hash. Runs write immutable full-spec artifacts below `backend/artifacts/simulation/runs`; failures after run identity exists retain a failed manifest. Entry quality, liquidity, theta, and hard delta limits execute deterministically, while expected edge remains deferred to EDGE-1. Position P&L includes entry costs and session P&L includes overnight gaps. The current clock is weekday-only and does not model NSE holidays or special sessions. This offline simulator has no broker order path, live option data, paper routing, or intraday realized variance.
