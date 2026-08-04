# Milestone RV-1 — Correct and Formalize Close-to-Close Volatility Research

Found underlying issues:

* `realized_variance()` uses sample variance for windows above one instead of accumulated squared returns. 
* The feature frame calculates one-day annualized absolute-return proxies and averages them to form the 5D, 21D and 63D values. 
* The forward target averages future one-day proxies, while the service applies a separate 70/30 split and calls the result a backtest. 
* “Run history” is synthesized from model names rather than loaded from actual persisted research runs. 
* The API contracts expose ambiguous fields such as `rv_5d`, without declaring whether they represent variance, volatility, annualized volatility or an absolute-return proxy. 

The implementation brief below is ready to give directly to Codex.

---

# Codex implementation brief

## Objective

Implement **Milestone RV-1: Correct and Formalize Close-to-Close Volatility Estimators**.

The milestone must replace the existing ambiguous volatility calculations with mathematically explicit close-to-close estimators, redesign the forecast target so that it represents subsequent realized variance, add complete estimator and dataset metadata, correct the frontend terminology, and ensure that research runs shown in the dashboard are genuine persisted runs rather than generated presentation records.

This milestone does **not** implement Andersen-style intraday realized volatility. It establishes the correct daily close-based fallback that later intraday estimators can replace or complement.

---

## 1. Scope and non-goals

### In scope

1. Correct daily close-to-close variance and volatility estimators.
2. Correct 1, 5, 21 and 63-session horizon calculations.
3. Correct the five-session forward forecast target.
4. Make forecast timing and information boundaries explicit.
5. Replace ambiguous API fields with well-defined contracts.
6. Add estimator, dataset and run provenance.
7. Implement genuine sequential forecast evaluation.
8. Persist actual research-run manifests and artifacts.
9. Update the existing dashboard to use the corrected fields.
10. Add comprehensive tests and documentation.
11. Remove committed Python cache files and strengthen `.gitignore`.

### Explicitly out of scope

Do not implement:

* Intraday realized variance.
* Upstox live market-data ingestion.
* Option-chain ingestion.
* Implied-volatility calculations.
* Variance-risk-premium signals.
* Gamma opportunity scoring.
* Hedge bands.
* Order execution.
* Deep hedging.
* Changes to broker authentication unless required to keep compilation working.
* Parkinson or Yang–Zhang estimators beyond retaining clear placeholders.

Do not rename the Upstox status as part of this milestone. Treat it as a separate operational milestone.

---

# 2. Mathematical definitions

These definitions are non-negotiable.

Let (P_t) be the positive closing price for trading session (t).

## 2.1 Log return

[
r_t=\log\left(\frac{P_t}{P_{t-1}}\right)
]

## 2.2 One-session close-to-close variance contribution

[
v_t=r_t^2
]

Do not subtract a sample mean.

Do not use `Series.var()`.

Do not use `ddof`.

## 2.3 Horizon realized variance

For a horizon of (h) completed sessions ending at (t):

[
RV_{t,h}
========

\sum_{j=0}^{h-1}r_{t-j}^{2}
]

This is cumulative horizon variance and has units of squared decimal return.

## 2.4 Annualized variance

[
AV_{t,h}
========

\frac{252}{h}RV_{t,h}
]

## 2.5 Annualized volatility

[
VOL_{t,h}
=========

# \sqrt{AV_{t,h}}

\sqrt{
\frac{252}{h}
\sum_{j=0}^{h-1}r_{t-j}^{2}
}
]

The backend returns decimal values. For example, `0.18` represents 18% annualized volatility.

The frontend is responsible for percentage formatting.

## 2.6 Forward target

At forecast origin (t), the subsequent (h)-session realized variance is:

[
RV^{forward}_{t,h}
==================

\sum_{j=1}^{h}r_{t+j}^{2}
]

Its annualized form is:

[
AV^{forward}_{t,h}
==================

\frac{252}{h}
\sum_{j=1}^{h}r_{t+j}^{2}
]

The display volatility is:

[
VOL^{forward}_{t,h}
===================

\sqrt{AV^{forward}_{t,h}}
]

A forecast created at the end of session (t) may use information through session (t). Its target must begin at session (t+1).

## 2.7 Important prohibition

The following is not a valid multi-session volatility estimator and must no longer be used as the dashboard RV:

[
\frac{1}{h}\sum_{j=0}^{h-1}|r_{t-j}|\sqrt{252}
]

The old absolute-return statistic may be retained only under an explicit diagnostic name such as:

```python
mean_absolute_return_volatility_proxy()
```

It must not be called realized variance or realized volatility and must not appear in the primary RV API.

---

# 3. Backend estimator implementation

## File

```text
backend/app/quant/rv_engine.py
```

## Required functions

Implement or revise the following:

```python
TRADING_DAYS_PER_YEAR = 252


def log_returns(prices: pd.Series) -> pd.Series:
    """Close-to-close log returns."""


def squared_log_returns(prices: pd.Series) -> pd.Series:
    """Per-session close-to-close variance contributions r_t ** 2."""


def close_to_close_realized_variance(
    prices: pd.Series,
    window: int = 21,
) -> pd.Series:
    """Rolling sum of squared log returns over completed sessions."""


def annualized_variance(
    horizon_variance: Any,
    horizon_sessions: int,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
):
    """Convert cumulative horizon variance into annualized variance."""


def close_to_close_realized_volatility(
    prices: pd.Series,
    window: int = 21,
    annualize: bool = True,
) -> pd.Series:
    """Square root of horizon variance, optionally annualized."""


def mean_absolute_return_volatility_proxy(
    prices: pd.Series,
    window: int = 21,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """Explicitly named legacy diagnostic; not a realized-variance estimator."""
```

## Required calculation

```python
returns = log_returns(prices)
horizon_variance = returns.pow(2).rolling(
    window=window,
    min_periods=window,
).sum()

annualized_variance = horizon_variance * periods_per_year / window
annualized_volatility = np.sqrt(annualized_variance.clip(lower=0))
```

## Compatibility decision

The existing functions `realized_variance()` and `realized_volatility()` may either:

1. Be removed after all internal callers are migrated, or
2. Remain as clearly documented aliases to the corrected close-to-close functions.

They must not retain the current sample-variance behaviour.

## Validation requirements

* Reject non-positive window sizes.
* Reject non-integer window sizes.
* Reject non-Series inputs.
* Convert non-numeric values to `NaN`.
* Treat zero and negative prices as invalid.
* Never emit positive or negative infinity.
* Preserve the input index.
* Require `window` valid returns before producing a value.
* `window=1` must produce (r_t^2) as variance.
* Constant prices must produce zero variance and zero volatility after the required warm-up.

---

# 4. Feature engineering redesign

## File

```text
backend/app/quant/rv_features.py
```

## Required output

Build features from daily squared log returns, not from averages of annualized one-day absolute returns.

For each origin date (t), calculate:

```text
horizon_variance_1d
horizon_variance_5d
horizon_variance_21d
horizon_variance_63d

annualized_variance_1d
annualized_variance_5d
annualized_variance_21d
annualized_variance_63d

annualized_volatility_1d
annualized_volatility_5d
annualized_volatility_21d
annualized_volatility_63d

variance_ratio_5_21
volatility_zscore_21
regime
```

## Ratio definition

[
Ratio_{5,21}
============

\frac{AV_{t,5}}{AV_{t,21}}
]

Handle a zero denominator as `NaN`.

Call this a **variance ratio**, not merely an RV ratio.

## Z-score definition

Compare current 21-session annualized volatility against its prior 63-observation distribution:

```python
current = annualized_volatility_21d

prior_mean = current.shift(1).rolling(
    window=63,
    min_periods=63,
).mean()

prior_std = current.shift(1).rolling(
    window=63,
    min_periods=63,
).std(ddof=0)

zscore = (current - prior_mean) / prior_std.replace(0, np.nan)
```

This allows the current known volatility to be compared with a distribution formed only from prior observations.

## Regime definition

```text
low     when z-score <= -1.0
normal  when -1.0 < z-score < 1.0
high    when z-score >= 1.0
unknown when insufficient history exists
```

Use a typed string or enum-compatible values.

## Information timing

Adopt an explicit **end-of-day forecast-origin convention**:

* A row indexed by date (t) may use the close and return observed at (t).
* A forecast at (t) targets returns from (t+1) onward.
* No feature may use data after (t).
* Do not insert a mechanical `.shift(1)` on every feature unless the feature definition specifically requires prior-only benchmark values.
* The z-score benchmark must use prior observations through the explicit shift shown above.

Add tests proving that changing prices after origin (t) does not change any feature at or before (t).

---

# 5. Forecast target and baseline redesign

## File

```text
backend/app/quant/rv_backtest.py
```

## Replace the current target

The existing `make_forward_target(rv, horizon)` averages future proxy values. Replace it with a function that constructs subsequent realized variance directly from squared log returns.

Suggested interface:

```python
def make_forward_variance_target(
    prices: pd.Series,
    horizon_sessions: int = 5,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """
    Return:
      forward_horizon_variance
      forward_annualized_variance
      forward_annualized_volatility
      target_start
      target_end
    """
```

At row (t), it must use returns indexed (t+1) through (t+h).

## Baseline forecasts

Implement two deterministic baselines.

### Naive trailing-variance forecast

```python
daily_variance = squared_log_returns(prices)

forecast_daily_variance = daily_variance.rolling(
    window=lookback_sessions,
    min_periods=lookback_sessions,
).mean()

forecast_annualized_variance = (
    forecast_daily_variance * TRADING_DAYS_PER_YEAR
)

forecast_annualized_volatility = np.sqrt(
    forecast_annualized_variance.clip(lower=0)
)
```

Default:

```text
lookback_sessions = horizon_sessions
```

Record the value in run metadata.

### EWMA variance forecast

```python
forecast_daily_variance = daily_variance.ewm(
    span=ewma_span,
    adjust=False,
    min_periods=ewma_span,
).mean()

forecast_annualized_variance = (
    forecast_daily_variance * TRADING_DAYS_PER_YEAR
)
```

Default:

```text
ewma_span = max(horizon_sessions, 2)
```

Record the span in run metadata.

## Why the horizon is not multiplied again

The model forecasts average daily variance. Multiplication by 252 annualizes it. The forward target similarly divides cumulative future variance by the number of sessions before annualizing.

Do not calculate:

```python
forecast * horizon_sessions
```

when comparing annualized variance forecasts.

---

# 6. Evaluation semantics

Remove the current arbitrary service-level 70/30 split for these parameter-free baselines.

Implement a sequential evaluation:

1. Generate a forecast at every eligible origin.
2. Generate the subsequent realized target.
3. Align forecast and target by origin date.
4. Retain all eligible rows for the chart.
5. Use a configurable stride for reported metrics.

Default:

```text
metric_stride = horizon_sessions
```

This produces non-overlapping target windows for headline metrics.

Also record:

```text
chart_stride = 1
metric_stride = horizon_sessions
overlapping_chart_targets = true
overlapping_metric_targets = false
```

Do not call this a train/test evaluation because the naive and EWMA baselines are not fitted on a separate training sample.

Use:

```text
evaluation_method = "sequential_non_overlapping_metrics"
```

Remove or stop using:

```python
RVService._evaluation_window()
```

The generic `walk_forward_split()` helper may remain only if:

* It has tests.
* Documentation says it is a future utility.
* No UI claims it was used for the current baseline.

Otherwise remove it.

---

# 7. Forecast metrics

Calculate metrics separately for annualized variance and annualized volatility.

Suggested model:

```python
class ForecastMetrics:
    mae: float
    rmse: float
    correlation: float | None
    change_direction_accuracy: float | None
    n_obs: int
```

Return:

```text
variance_metrics
volatility_metrics
```

Do not silently replace undefined correlation with `0.0`.

Use `None` in the API when a statistic is undefined because of:

* Insufficient observations.
* Constant forecast values.
* Constant target values.

`n_obs` must be included in the public API.

## Direction metric

Rename `directional_accuracy` to:

```text
change_direction_accuracy
```

It measures whether the change in forecast and change in actual value have the same sign. It does not measure market direction.

Document this clearly.

---

# 8. API contract redesign

## File

```text
backend/app/schemas/rv.py
```

Retain:

```python
model_config = ConfigDict(extra="forbid")
```

Replace ambiguous field names such as `rv_5d` with explicit nested structures.

## Estimator metadata

```python
class RVEstimatorMetadata(RVModel):
    estimator_id: Literal["close_to_close_squared_log_returns_v1"]
    input_frequency: Literal["1d_close"]
    return_type: Literal["log"]
    annualization_periods: int
    observation_timing: Literal["end_of_day"]
    is_intraday_realized_variance: Literal[False]
```

## Dataset metadata

```python
class RVDatasetMetadata(RVModel):
    dataset_id: str
    source: Literal["csv", "synthetic"]
    symbol: str
    observations: int
    start_date: date
    end_date: date
    computed_at: datetime
```

Optional synthetic metadata may be nested:

```python
class RVSyntheticDatasetParameters(RVModel):
    seed: int
    periods: int
    end_date: date
    initial_price: float
```

## Horizon estimate

```python
class RVHorizonEstimate(RVModel):
    horizon_sessions: int
    horizon_variance: float
    annualized_variance: float
    annualized_volatility: float
```

## Latest response

```python
class RVLatestResponse(RVModel):
    symbol: str
    as_of: date
    price: float
    estimates: list[RVHorizonEstimate]
    variance_ratio_5_21: float | None
    volatility_zscore_21: float | None
    regime: Literal["low", "normal", "high", "unknown"]
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata
```

The estimates list must contain horizons:

```text
1, 5, 21, 63
```

in ascending order.

## Feature-point response

```python
class RVFeaturePoint(RVModel):
    date: date
    price: float
    estimates: list[RVHorizonEstimate]
    variance_ratio_5_21: float | None
    volatility_zscore_21: float | None
    regime: Literal["low", "normal", "high", "unknown"]
```

The feature response must also contain top-level estimator and dataset metadata.

## Forecast history point

```python
class RVForecastHistoryPoint(RVModel):
    origin_date: date
    target_start: date
    target_end: date
    price: float

    forecast_annualized_variance: float
    forecast_annualized_volatility: float

    actual_annualized_variance: float
    actual_annualized_volatility: float
```

Remove ambiguous history fields:

```text
rv_5d
forecast_5d
actual_forward_5d
```

## Backtest summary

```python
class RVBacktestSummary(RVModel):
    symbol: str
    model: str
    model_parameters: dict[str, int | float | str]
    horizon_sessions: int
    evaluation_method: Literal[
        "sequential_non_overlapping_metrics"
    ]
    chart_stride: int
    metric_stride: int
    evaluation_start: date
    evaluation_end: date
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata
    variance_metrics: RVBacktestMetrics
    volatility_metrics: RVBacktestMetrics
    regime_metrics: list[RVRegimeMetric]
```

Remove:

```text
train_start
train_end
test_start
test_end
```

for these current non-fitted baseline models.

The backend and frontend must be migrated atomically. Do not retain misleading aliases merely to keep the old frontend compiling.

---

# 9. Reproducible synthetic dataset

## File

```text
backend/app/services/rv_service.py
```

The current synthetic generator uses the current date for its index, so its output dates change across executions even with the same random seed. Correct that.

Use an explicit function signature:

```python
def synthetic_prices(
    *,
    periods: int,
    seed: int,
    end_date: date,
    initial_price: float,
) -> pd.Series:
```

Do not call `Timestamp.now()` inside this function.

Add configurable defaults, for example through settings:

```text
RV_SYNTHETIC_SEED=17
RV_SYNTHETIC_PERIODS=720
RV_SYNTHETIC_END_DATE=2025-12-31
RV_SYNTHETIC_INITIAL_PRICE=24000
```

Do not hardcode a new date without documenting it.

## Dataset ID

Calculate a stable SHA-256 identifier from the normalized dataset.

The hash input must include:

```text
symbol
ordered timestamps
ordered prices
frequency
source
```

For synthetic data, also include the generation parameters.

Suggested format:

```text
sha256:<64-hex-character-digest>
```

The same synthetic configuration must produce the same dataset ID and identical numerical results.

Changing the seed, end date, period count or prices must change the dataset ID.

---

# 10. Service snapshot semantics

Refactor `RVService` so that the data it serves has explicit provenance.

Suggested internal object:

```python
@dataclass(frozen=True)
class RVResearchSnapshot:
    symbol: str
    prices: pd.Series
    features: pd.DataFrame
    backtests: dict[str, RVBacktestResult]
    estimator_metadata: RVEstimatorMetadata
    dataset_metadata: RVDatasetMetadata
```

The service may still build one immutable snapshot at startup during RV-1.

However:

* It must expose `computed_at`.
* It must not imply that the data is live.
* It must not invent research runs.
* It must not recompute independently in every endpoint.
* All endpoints must refer to the same snapshot and dataset ID.
* Every response must be internally consistent with the same estimator version.

Add a public method:

```python
def refresh(self) -> None:
    """Reload source data and atomically replace the current snapshot."""
```

Do not expose an unauthenticated recompute endpoint during this milestone.

---

# 11. Genuine research-run persistence

The current `runs()` method creates two run records from the latest date and model names. Remove this behaviour.

## Add a small local artifact store

Suggested structure:

```text
backend/artifacts/rv/
└── runs/
    └── <run-id>/
        ├── manifest.json
        ├── summary.json
        ├── forecast-history.csv
        └── features.csv
```

Add this directory to `.gitignore`.

## Run manifest

Create a schema resembling:

```python
class RVRunManifest(RVModel):
    run_id: str
    created_at: datetime
    completed_at: datetime | None
    status: Literal["running", "complete", "failed"]

    symbol: str
    dataset_id: str
    estimator_id: str

    model: str
    model_parameters: dict[str, int | float | str]

    horizon_sessions: int
    evaluation_method: str

    config_hash: str
    git_commit: str | None

    artifact_directory: str
    failure_reason: str | None
```

## Run command

Add a CLI module, for example:

```text
backend/app/cli/run_rv_research.py
```

Expected invocation:

```bash
uv run python -m app.cli.run_rv_research \
  --symbol NIFTY \
  --model ewma \
  --horizon-sessions 5
```

The command must:

1. Load the configured CSV or explicit synthetic dataset.
2. Compute the corrected estimators.
3. Run the sequential evaluation.
4. Write artifacts.
5. Write a `running` manifest first.
6. Atomically replace it with `complete` after all artifacts succeed.
7. Write `failed` and a failure reason when an exception occurs.
8. Return a non-zero process exit code on failure.

Use a temporary directory and atomic rename where practical so incomplete artifacts are not presented as completed runs.

## API behaviour

`GET /rv/backtest/runs` must read persisted manifests.

When no runs exist, return:

```json
{
  "runs": []
}
```

Do not fabricate fallback runs.

The frontend must show an informative empty state.

---

# 12. Frontend migration

## Primary files

```text
frontend/src/store/api/rvApi.ts
frontend/src/components/rv/RvSummaryCards.tsx
frontend/src/components/rv/RvLineChart.tsx
frontend/src/components/rv/RvFeatureTable.tsx
frontend/src/components/rv/RvBacktestTable.tsx
frontend/src/components/rv/RvRunHistory.tsx
```

Update all TypeScript types to match the new backend contracts.

## Page terminology

Use:

```text
Close-to-Close Volatility
```

or:

```text
Close-to-Close Volatility Research
```

Do not label the current daily-close estimator as Andersen intraday realized volatility.

Add a visible explanatory line:

> Calculated from daily close-to-close squared log returns. This is not an intraday realized-volatility estimator.

Retain the visible synthetic-data disclosure.

## Summary cards

Display:

```text
1-session annualized volatility
5-session annualized volatility
21-session annualized volatility
63-session annualized volatility
5D / 21D annualized variance ratio
Volatility regime
```

Do not display cumulative horizon variance as a percentage.

Format annualized volatility:

```typescript
`${(value * 100).toFixed(2)}%`
```

Format annualized variance either:

* As decimal variance with a clear label, or
* Do not display it in the summary cards.

## Chart labels

Use:

```text
Forecast annualized volatility
Subsequent realized annualized volatility
```

Include the horizon:

```text
5-session forecast
5-session subsequent realization
```

The tooltip should show:

```text
Forecast origin
Target start
Target end
Forecast annualized volatility
Actual annualized volatility
```

## Backtest section

Display:

```text
Evaluation: Sequential
Metric target spacing: 5 sessions
Overlapping chart points: Yes
Overlapping metric targets: No
Observations: <n_obs>
```

Do not display arbitrary train/test dates.

Display separate metric groups:

```text
Annualized variance metrics
Annualized volatility metrics
```

## Feature table

Use explicit headings:

```text
1D Ann. Vol.
5D Ann. Vol.
21D Ann. Vol.
63D Ann. Vol.
5D / 21D Variance Ratio
21D Vol. Z-score
Regime
```

## Run history

Read persisted runs only.

Empty-state text:

> No persisted RV research runs yet. Execute the RV research command to create one.

Do not create fake rows in the frontend.

---

# 13. Unit tests

## `backend/tests/quant/test_rv_engine.py`

Add the following tests.

### Hand-calculated price path

Use:

```python
prices = pd.Series(
    [100.0, 101.0, 99.0, 102.0],
    index=pd.date_range("2025-01-01", periods=4, freq="D"),
)
```

Calculate expected returns independently in the test:

```python
r1 = math.log(101.0 / 100.0)
r2 = math.log(99.0 / 101.0)
r3 = math.log(102.0 / 99.0)
```

Expected final three-session horizon variance:

```python
expected_rv = r1**2 + r2**2 + r3**2
```

Expected annualized variance:

```python
expected_ann_var = expected_rv * 252 / 3
```

Expected annualized volatility:

```python
expected_ann_vol = math.sqrt(expected_ann_var)
```

Do not use a production function to calculate the expected value.

### Required engine tests

* Log-return correctness.
* Squared-return correctness.
* One-session variance equals (r_t^2).
* Three-session variance equals the sum of three squared returns.
* Annualized variance uses `252 / window`.
* Annualized volatility is the square root of annualized variance.
* Constant-price path produces zero.
* Insufficient history produces `NaN`.
* Invalid non-positive prices do not produce infinity.
* Non-Series input raises.
* Invalid window raises.
* A path with non-zero mean proves the implementation is not sample variance.
* Legacy absolute-return proxy has an explicit name and different values from the corrected estimator.

## `backend/tests/quant/test_rv_features.py`

Required tests:

* Correct horizons appear.
* Each horizon uses sum of squared returns.
* Annualized values use the correct horizon divisor.
* Ratio uses annualized variance.
* Zero denominator yields `NaN`.
* Z-score benchmark excludes the current observation from its historical mean and standard deviation.
* Regime boundaries at `-1` and `+1`.
* Future-data mutation test:

  * Build features.
  * Change prices strictly after origin (t).
  * Rebuild features.
  * Assert all rows through (t) are unchanged.
* Exact output column set.
* No infinite values.

## `backend/tests/quant/test_rv_backtest.py`

Required tests:

* Forward target at origin (t) uses only returns (t+1) through (t+h).
* Forward target does not include the origin return.
* Last `h` rows have no complete target.
* Forecast at (t) is unchanged when prices after (t) are modified.
* Naive forecast calculation.
* EWMA forecast calculation.
* Variance and volatility targets are mathematically consistent.
* `metric_stride=horizon` selects non-overlapping targets.
* Metrics include `n_obs`.
* Undefined correlation returns `None`.
* Direction metric is named `change_direction_accuracy`.
* Regime metrics are based on the regime known at the forecast origin.

## `backend/tests/test_rv_api.py`

Update tests to verify:

* No old ambiguous fields exist.
* Metadata appears in all relevant responses.
* Estimator ID is correct.
* `is_intraday_realized_variance` is false.
* Horizon estimates are ordered `1, 5, 21, 63`.
* Dataset IDs are stable.
* Same dataset ID appears across latest, features, history and backtest responses.
* Backtest response no longer contains train/test fields.
* Run endpoint returns only persisted runs.
* Empty run store returns an empty list.
* Pydantic rejects undeclared response fields.

## Run-store tests

Add tests for:

* Successful manifest creation.
* Failed manifest creation.
* Stable configuration hash.
* Artifact files exist for complete runs.
* Incomplete temporary directories are not listed.
* Invalid manifests are ignored or reported safely.
* Same synthetic configuration gives identical dataset ID.
* Changed synthetic seed gives a different dataset ID.

---

# 14. Frontend verification

The current frontend has lint and production-build scripts but no test framework. 

For RV-1, frontend tests are optional, but the following are mandatory:

```bash
npm run lint
npm run build
```

Use the package manager corresponding to the committed lockfile.

The build must have:

* No TypeScript errors.
* No stale references to `rv_5d`, `forecast_5d` or `actual_forward_5d`.
* No stale train/test labels.
* No fabricated run-history fallback.
* No generic “realized volatility” statement that implies intraday data.

Do not add a full frontend test framework solely for this milestone unless it is straightforward and does not distract from quantitative correctness.

---

# 15. Repository hygiene

Remove tracked:

```text
__pycache__/
*.pyc
```

Add or confirm in the root `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

backend/artifacts/
artifacts/

.env
.env.*
!.env.example

frontend/node_modules/
frontend/dist/
```

Do not delete valid source fixtures or synthetic configuration files.

Add a README section describing:

* What the current RV module does.
* Exact formulas.
* Daily-close limitation.
* How to run the backend tests.
* How to generate a persisted RV research run.
* How to start the dashboard.
* Meaning of the synthetic-data badge.

---

# 16. Documentation requirements

Update:

```text
docs/architecture.md
```

Add a section:

## Close-to-close volatility estimator

Include the exact formulas for:

* Log return.
* Horizon realized variance.
* Annualized variance.
* Annualized volatility.
* Forward target.

State explicitly:

> The current estimator uses daily closing prices. It is a close-to-close volatility estimator and not the high-frequency intraday realized-volatility estimator described by Andersen et al. Intraday realized variance will be implemented in a later milestone after validated intraday market-data ingestion exists.

Document units:

| Quantity              | Unit                  |
| --------------------- | --------------------- |
| Log return            | decimal               |
| Horizon variance      | decimal² over horizon |
| Annualized variance   | decimal² per year     |
| Annualized volatility | decimal per √year     |
| UI volatility         | percentage            |

Document the forecast-origin convention:

```text
Origin t: after session t close
Known information: through session t
Target: sessions t+1 through t+h
```

---

# 17. Acceptance criteria

RV-1 is complete only when all of the following pass.

## Mathematical acceptance

* [ ] Multi-session variance is a sum of squared log returns.
* [ ] No estimator uses sample variance.
* [ ] No estimator subtracts the sample return mean.
* [ ] No primary estimator averages absolute returns.
* [ ] Annualized variance uses `252 / horizon`.
* [ ] Forward targets use future squared returns.
* [ ] Forecast and target units match.
* [ ] No future information enters forecast features.

## API acceptance

* [ ] Every response identifies the estimator.
* [ ] Every response identifies the dataset.
* [ ] Variance and volatility are separate fields.
* [ ] Horizons use `horizon_sessions`.
* [ ] No ambiguous `rv_5d` field remains.
* [ ] Undefined metrics are `null`, not zero.
* [ ] `n_obs` is exposed.
* [ ] No arbitrary train/test dates remain for baseline forecasts.

## Reproducibility acceptance

* [ ] Synthetic generation accepts an explicit end date.
* [ ] Same configuration produces the same prices.
* [ ] Same configuration produces the same dataset ID.
* [ ] Research runs write immutable manifests and artifacts.
* [ ] API run history contains only persisted runs.
* [ ] No fabricated run records remain.

## Frontend acceptance

* [ ] Dashboard compiles.
* [ ] All volatility values are formatted as percentages.
* [ ] The page clearly says daily close-to-close.
* [ ] The page clearly says it is not intraday RV.
* [ ] Chart labels distinguish forecasts from subsequent realizations.
* [ ] Backtest section states the evaluation method.
* [ ] Empty run history is handled.
* [ ] Synthetic-data disclosure remains visible.

## Repository acceptance

* [ ] Backend tests pass.
* [ ] Frontend lint passes.
* [ ] Frontend production build passes.
* [ ] No tracked cache files remain.
* [ ] README and architecture docs are updated.
* [ ] `git diff --check` passes.

---

# 18. Commands Codex must run

From the repository root, adapt only where required by the existing environment:

```bash
cd backend
uv sync --group dev
uv run pytest
```

Then:

```bash
cd ../frontend
npm run lint
npm run build
```

Also run:

```bash
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
```

Run the research CLI at least once:

```bash
cd backend
uv run python -m app.cli.run_rv_research \
  --symbol NIFTY \
  --model ewma \
  --horizon-sessions 5
```

Then verify that:

```text
manifest.json
summary.json
forecast-history.csv
features.csv
```

were created and that the runs API lists the completed run.

---

# 19. Codex completion report

At the end, Codex must report:

1. Files added.
2. Files modified.
3. Files removed.
4. Exact estimator formulas implemented.
5. Old semantics removed.
6. API contract changes.
7. Run-artifact design.
8. Commands executed.
9. Test counts and results.
10. Frontend lint/build results.
11. Known limitations.
12. Confirmation that intraday realized variance remains unimplemented.

Codex must not claim RV-1 is complete merely because the UI renders. Quantitative tests and artifact reproducibility are acceptance requirements.

---

## Recommended commit sequence

Keep the work reviewable:

```text
1. Correct close-to-close variance estimators and tests
2. Redesign features and forward targets
3. Replace RV API contracts and service responses
4. Add reproducible datasets and persisted research runs
5. Migrate the frontend to explicit variance/volatility contracts
6. Update documentation and repository hygiene
```

The important principle for RV-1 is:

> **Variance is the primary modeled quantity. Volatility is its square root for interpretation and display.**

That foundation will later allow the application to compare physical expected variance with option-implied variance without mixing incompatible statistics.
