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
