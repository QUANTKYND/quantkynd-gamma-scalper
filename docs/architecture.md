# Gamma Scalper Application Architecture

## Critical separation of concerns

The application should contain two distinct decision systems:

1. **Position/entry engine** - decides whether to own gamma, which strikes/maturity to use and how much.
2. **Hedge controller** - manages delta and execution costs after the option position exists.

Most hedging papers solve item 2. Carr-Wu plus the RV forecast provide the basis for item 1.

## Close-to-close volatility estimator

The current estimator uses daily closing prices. It is a close-to-close volatility estimator and not the high-frequency intraday realized-volatility estimator described by Andersen et al. Intraday realized variance will be implemented in a later milestone after validated intraday market-data ingestion exists.

For a positive closing price `P_t`, the close-to-close log return is:

```text
r_t = log(P_t / P_{t-1})
```

The horizon realized variance for `h` completed sessions ending at session `t`
is the cumulative sum of squared log returns:

```text
RV_{t,h} = sum_{j=0}^{h-1} r_{t-j}^2
```

Annualized variance uses the horizon divisor:

```text
AV_{t,h} = (252 / h) * RV_{t,h}
```

Annualized volatility is the square root of annualized variance:

```text
VOL_{t,h} = sqrt(AV_{t,h})
```

At forecast origin `t`, the subsequent `h`-session target begins after the
origin close:

```text
RV_forward_{t,h} = sum_{j=1}^{h} r_{t+j}^2
AV_forward_{t,h} = (252 / h) * RV_forward_{t,h}
VOL_forward_{t,h} = sqrt(AV_forward_{t,h})
```

| Quantity | Unit |
| --- | --- |
| Log return | decimal |
| Horizon variance | decimal squared over horizon |
| Annualized variance | decimal squared per year |
| Annualized volatility | decimal per square-root year |
| UI volatility | percentage |

Forecast-origin convention:

```text
Origin t: after session t close
Known information: through session t
Target: sessions t+1 through t+h
```

## Proposed data flow

```text
Market data and option chain
        |
        +--> Intraday return cleaner --> Realized variance/covariance --> RV forecast under P
        |
        +--> Arbitrage-clean IV surface --> OTM option strip --> Implied variance under Q
        |
        +--> Quotes, spread, depth, fees --> Cost model / liquidity regime
        |
        +--> Portfolio marks and Greeks --> Delta, gamma, vega, theta, inventory

RV forecast - Implied variance
        |
        +--> Expected gamma P&L - expected costs - model/tail buffer
        |
        +--> Entry/exit and sizing gate

Current delta hedge + target delta + gamma + cost/risk state
        |
        +--> No-transaction band
        |
        +--> Risk gates and execution constraints
        |
        +--> Order to nearest feasible boundary

All decisions and outcomes
        |
        +--> Deterministic journal --> replay --> hedge-error simulator --> calibration/evaluation
```

## Module mapping

### `rv_forecast.py`

- Current fallback computes close-to-close squared daily log-return sums.
- Production extension computes `sum r_i^2` or `R'R` from intraday log returns.
- Fits a fractional-VAR model to log realized volatility.
- Produces horizon forecasts in variance and volatility units.
- Production extension: realized kernel/pre-averaging, bipower variation and jump component.

### `volatility_signal.py`

- Integrates OTM option prices with `1/K^2` weights to estimate risk-neutral variance.
- Calculates `E_P[RV]-E_Q[RV]`.
- Converts the variance spread into approximate gamma-theta P&L.
- Applies estimated costs and risk buffer before allowing a trade.

### `hedge_band.py`

- Whalley-Wilmott cubic-root band.
- Chen-style calibrated delta band.
- Hard projection for execution and soft projection for differentiable training.
- Later extension: asymmetric widths and bounded learned center shift.

### `cost_model.py`

- Source-derived proportional buy/sell costs.
- Practical spread, fixed fee, minimum fee and nonlinear impact extensions.
- Separate underlying and option schedules.
- Production extension: exchange/broker taxes, fill probability, queue position and gap/slippage scenarios.

### `hedge_error_simulator.py`

- GBM and Merton jump paths.
- Fixed-frequency delta, Chen band and WW band policies.
- Tracks P&L, hedge error, cost, turnover and trade count.
- Reports MSE/RMSE, VaR, CVaR and probability of loss.
- Production extension: historical replay, stochastic IV surface, delayed fills, discrete contracts and portfolio-level Greeks.

## Live decision algorithm

At every observation event:

1. Update spot, option surface, portfolio Greeks and cost estimates.
2. Update same-horizon physical RV forecast and risk-neutral implied variance.
3. Revalue expected gross gamma P&L.
4. Reject entry or reduce exposure if expected net edge is not positive after cost and tail buffers.
5. For an active position, compute a risk-neutral target delta.
6. Compute the no-trade band from gamma, cost and risk aversion.
7. Apply hard inventory, margin, liquidity and loss limits.
8. If current hedge is inside the band, do nothing.
9. If outside, submit only enough quantity to reach the nearest feasible boundary.
10. Journal inputs, forecasts, band, order decision, fill and subsequent hedge error.

## Recommended milestone order

1. **Deterministic research simulator** - fixed delta versus constant band versus WW band.
2. **Empirical cost calibration** - fees, spread and slippage from paper/replay fills.
3. **RV forecast** - out-of-sample forecast tests and horizon mapping.
4. **Implied variance/VRP** - arbitrage-clean option strip and entry edge.
5. **Historical replay** - option chain plus underlying, no live orders.
6. **Paper trading** - discrete contracts, order state and risk gates.
7. **Exact-control benchmark** - small state grids to validate band geometry.
8. **Learned residual band** - NTBN/WW-NTBN with strict out-of-sample and ablation tests.
9. **Multi-instrument hedge** - underlying plus selected option only after option cost/fill models are credible.

## Acceptance gates

A policy cannot advance unless it beats the simpler baseline out-of-sample on:

- Cost-adjusted terminal P&L distribution.
- RMSE and downside-only hedge error.
- CVaR and worst-path shortfall.
- Turnover and number of trades.
- Stability across spread, volatility and jump regimes.
- Sensitivity to forecast errors and stale/incorrect Greeks.
- No look-ahead leakage and deterministic replay reproducibility.
