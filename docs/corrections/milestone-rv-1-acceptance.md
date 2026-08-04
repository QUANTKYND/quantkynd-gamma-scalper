# Milestone RV-1 Acceptance Criteria

Updated: 2026-08-03

## Mathematical acceptance

- [x] Multi-session variance is a sum of squared log returns.
- [x] No estimator uses sample variance.
- [x] No estimator subtracts the sample return mean.
- [x] No primary estimator averages absolute returns.
- [x] Annualized variance uses `252 / horizon`.
- [x] Forward targets use future squared returns.
- [x] Forecast and target units match.
- [x] No future information enters forecast features.

## API acceptance

- [x] Every RV response identifies the estimator.
- [x] Every RV response identifies the dataset.
- [x] Variance and volatility are separate fields.
- [x] Horizons use `horizon_sessions`.
- [x] No ambiguous `rv_5d` field remains in backend or frontend API contracts.
- [x] Undefined metrics are `null`, not zero.
- [x] `n_obs` is exposed.
- [x] No arbitrary train/test dates remain for baseline forecast responses.

## Reproducibility acceptance

- [x] Synthetic generation accepts an explicit end date.
- [x] Same configuration produces the same prices.
- [x] Same configuration produces the same dataset ID.
- [x] Research runs write immutable manifests and artifacts.
- [x] API run history contains only persisted runs.
- [x] No fabricated run records remain.

## Frontend acceptance

- [x] Dashboard compiles.
- [x] All volatility values are formatted as percentages.
- [x] The page clearly says daily close-to-close.
- [x] The page clearly says it is not intraday RV.
- [x] Chart labels distinguish forecasts from subsequent realizations.
- [x] Backtest section states the evaluation method.
- [x] Empty run history is handled.
- [x] Synthetic-data disclosure remains visible.

## Repository acceptance

- [x] Backend tests pass: `55 passed`.
- [x] Frontend lint passes.
- [x] Frontend production build passes.
- [x] No tracked cache files remain.
- [x] README and architecture docs are updated.
- [x] `git diff --check` passes.

## Verification Commands

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.run_rv_research --symbol NIFTY --model ewma --horizon-sessions 5
```

```bash
cd frontend
npm run lint
npm run build
```

```bash
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
```

## Notes

- The verified persisted run was `rv-20260803T150018Z-ewma-07ec4383`.
- Vite reported a large bundle-size warning during production build; the build succeeded.
- Intraday realized variance remains unimplemented by design for this milestone.
