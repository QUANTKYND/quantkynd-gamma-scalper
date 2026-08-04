# Research Plan

## Objective

Establish whether a narrow long-gamma strategy has a repeatable net edge after option costs, hedge costs, theta, model error, and operational constraints.

The research plane must separate two decisions:

1. Gamma entry: whether expected future variance is sufficiently above market-implied variance.
2. Delta control: how to manage directional exposure after entry without spending away the convexity edge.

## Completed foundation

RV-1 and RV-1.1 provide:

- Close-to-close squared-log-return variance.
- 1, 5, 21, and 63-session horizons.
- Naive and EWMA variance forecasts.
- Correct forward targets.
- Sequential metrics.
- Regime features.
- Deterministic synthetic data.
- Persisted research runs.

This is a daily-close fallback, not the final intraday realized-volatility estimator.

## R0 — Strategy contract

Status: COMPLETE for the frozen STRAT-1 offline research contract.

Freeze:

- Underlying.
- Long-gamma structure.
- Entry and holding horizon.
- DTE and strike selection.
- Hedge instrument.
- Entry and exit rules.
- Position sizing.
- Cost assumptions.
- Hard risk limits.

No historical test begins until the strategy is fully executable from configuration.

## R1 — Deterministic option engine

Status: COMPLETE for SIM-1 European Black–Scholes analytics and bounded IV inversion.

Build explicit European option formulas before consuming live option prices.

Modules:

```text
options/contracts.py
options/black_scholes.py
options/implied_volatility.py
options/greeks.py
```

Acceptance:

- Hand-calculated and reference values.
- Put-call parity.
- Price and IV round trips.
- Analytical Greeks against finite differences.
- Boundary behavior near expiry, low volatility, and extreme moneyness.

## R2 — Cost and fill model

Status: COMPLETE for deterministic option/futures reference-mid fills with explicit fixed, proportional, half-spread, and slippage components. Delayed quote fills remain part of historical replay.

Model option and hedge execution separately.

Cost decomposition:

```text
fixed fees
exchange and statutory fees
brokerage
bid-ask crossing
slippage
market-impact proxy
financing and carry
```

Initial fill policies:

- Bid or ask crossing.
- Midpoint plus configurable penalty.
- Delayed fill at next eligible quote.
- Rejection when quote quality fails.

No research result may use an unstated midpoint fill.

## R3 — Hedge simulator

Status: COMPLETE for deterministic synthetic paths, the five baseline policies, exact ledger reconciliation, Greek attribution, and immutable local artifacts.

Policies:

- No hedge.
- Fixed interval.
- Delta threshold.
- Constant symmetric band.
- Whalley–Wilmott structural band.
- Chen-style empirically calibrated boundary later.

Every policy runs on identical paths and costs.

Required outputs:

- Terminal hedge error.
- Turnover.
- Hedge count.
- Cost per hedge.
- Delta drift.
- Maximum unhedged delta.
- Gamma and theta contributions.
- Residual attribution.
- VaR and CVaR.

## R4 — Intraday realized variance

Begins only after validated intraday data exists.

Deliver:

- Session-aware intraday returns.
- Sampling-grid comparison.
- Microstructure-noise diagnostics.
- Missing-interval policy.
- Overnight treatment.
- Daily realized variance and volatility.
- Comparison against close-to-close fallback.

Candidate forecasts:

- EWMA variance.
- HAR-RV.
- Long-memory or fractional baseline after simple models.
- Jump-robust extensions later.

## R5 — Implied variance and variance premium

Start with a hierarchy:

1. ATM IV squared as a coarse horizon proxy.
2. Interpolated ATM term structure.
3. Option-strip variance-swap approximation.
4. Contract-specific expected and implied volatility later.

Core comparison:

```text
physical expected variance
minus risk-neutral implied variance
minus option entry and exit costs
minus expected hedge costs
minus model-risk buffer
```

A positive raw IV-RV difference is not an entry signal by itself.

## R6 — Event-driven historical replay

The backtest processes market events, state updates, decisions, intents, fills, and ledger changes.

Point-in-time requirements:

- Contract existed and was listed.
- Quote was known at decision time.
- Quality filters use only contemporaneous information.
- Selection does not inspect exit-date liquidity or survival.
- Fills use later eligible events, never same-event hindsight.

## R7 — Robustness

Required comparisons:

- Hedge policies.
- Forecast models.
- DTE buckets.
- Entry thresholds.
- Holding periods.
- Spread and slippage assumptions.
- Trend, range, high-volatility, jump, and event regimes.
- Delayed hedge decisions.
- Stale or missing Greek inputs.

Success requires stability across neighboring parameters and out-of-sample periods, not one optimized point.

## R8 — Advanced policies

Deferred until deterministic baselines and realistic replay exist:

- Exact stochastic-control benchmark on restricted state spaces.
- Learned residual corrections to structural bands.
- IV-surface-informed policies.
- Additional option hedging instruments.
- Deep hedging.
- Market-impact-aware control.

## Research artifacts

Each run emits:

```text
manifest.json
configuration.json
summary.json
events.parquet or csv
decisions.parquet or csv
orders.parquet or csv
fills.parquet or csv
ledger.parquet or csv
attribution.parquet or csv
metrics.json
```

The exact format evolves, but provenance and immutability do not.
