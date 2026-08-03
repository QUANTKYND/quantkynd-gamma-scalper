# Gamma Scalper Research Extraction

This document separates **what the sources explicitly establish** from **engineering decisions proposed for the Gamma Scalper application**. The sources mostly solve the problem of hedging an existing option position. They do not, by themselves, prove that buying gamma is profitable. Entry requires a separate expected-realized-versus-implied variance signal after execution costs and risk buffers.

## 1. Andersen, Bollerslev, Diebold and Labys - Modeling and Forecasting Realized Volatility

### Role in the application

This is the foundation for the **physical-measure volatility forecast** used to estimate how much variance the underlying is likely to realize over the intended option holding horizon.

### Assumptions

- The logarithmic price is an arbitrage-free semimartingale.
- Intraday return cross-products can approximate quadratic variation as sampling becomes finer.
- For the clean continuous-path interpretation, quadratic variation equals integrated volatility; jumps make realized quadratic variation include jump variation as well.
- Conditional on realized volatility and auxiliary regularity assumptions, standardized returns are approximately Gaussian.
- Realized logarithmic volatilities exhibit long memory and are modeled with a fractionally integrated Gaussian VAR.
- The empirical implementation deliberately samples at 30-minute intervals to balance information against market-microstructure noise.

### State variables

- Intraday log-return vector `r_(t,j)`.
- Daily/horizon realized covariance matrix `V_(t,h) = sum_j r_j r_j' = R'R`.
- Log realized standard deviations `y_t = 0.5 log(diag(V_t))`.
- Fractionally differenced log-volatility states `(1-L)^d (y_t - mu)`.
- VAR lag state, with the paper fixing `d = 0.401` and using five daily lags.

### Objective function

This is a statistical forecasting paper rather than a trading control problem. The objective is accurate conditional forecasts of realized volatility, covariance, return density and quantiles. The proposed model is

```text
A(L) (1-L)^d (y_t - mu) = epsilon_t.
```

### Practical implementation

1. Clean and synchronize bid/ask observations.
2. Construct regularly spaced log mid-prices.
3. Compute intraday log returns.
4. Aggregate squared returns and cross-products into daily realized variance/covariance.
5. Log-transform realized standard deviations.
6. Fractionally difference with `d` estimated or fixed.
7. Fit a Gaussian VAR to the filtered series.
8. Produce one- and multi-step forecasts; transform back to variance units.
9. Validate standardized residuals, out-of-sample loss and forecast calibration.
10. Add explicit jump/continuous decomposition in a modern implementation because the paper identifies this as an important extension.

### Gamma Scalper interpretation

Use the forecast as `E_P[future realized variance]`. Do not compare a one-day RV forecast directly with a 30-day option IV; align horizons first.

---

## 2. Ling Chen - Option Pricing and Hedging with Transaction Costs

### Role in the application

This source connects theoretical no-transaction regions to a **data-tuned, implementable buy/sell boundary**.

### Assumptions

- European option, primarily a short call hedged with the underlying.
- Underlying is often modeled as GBM for the theoretical derivations.
- Transaction costs are proportional and may be asymmetric: buy rate `lambda_b`, sell rate `lambda_s`.
- Rebalancing is discrete in the practical strategy.
- Negative exponential utility is used in the utility-control formulation.
- For the simple empirical rule, the Black-Scholes delta is treated as a reasonable benchmark center, while the boundary offset is learned from data.

### State variables

The theoretical utility formulation uses:

- Time `t`.
- Spot `S_t`.
- Underlying holding `y_t`.
- Cash/risk-free holding `x_t`; CARA utility removes this dimension from the optimal strategy.
- Option liability state.

The rule-based implementation uses:

- Current time and spot.
- Current hedge holding.
- Black-Scholes delta.
- Buy and sell boundary offsets `d_b(t,S)` and `d_s(t,S)`.

### Objective functions

**Utility maximization**

```text
J^i(t,x,y,S) = sup_(L,M) E[U(V_T^i) | state],
U(v) = 1 - exp(-gamma v).
```

**Cost-constrained risk minimization**

The pathwise hedging risk is

```text
R = integral_t^T sigma^2 S_u^2 [y_u - Delta(u,S_u)]^2 du,
```

and the dual control problem is

```text
J(t,y,S) = inf_(L,M) E[theta R + C | state],
```

where `C` is total hedging cost.

**Data-driven tuning criterion**

The terminal tracking error is `V_T`. Across a basket of `M` options, Chen minimizes the realized prediction error

```text
eta_tilde = sqrt((1/M) sum_m [discount_m * V_T^(m)]^2).
```

### No-transaction policy

At each eligible rebalancing time:

```text
new_position = lower_boundary,  if current < lower_boundary
new_position = current,         if lower <= current <= upper
new_position = upper_boundary,  if current > upper_boundary
```

The data-driven band is

```text
Y_b(t,S) = max(Delta_BS(t,S) - d_b(t,S), 0)
Y_s(t,S) = min(Delta_BS(t,S) + d_s(t,S), 1).
```

The simplest empirical form sets `d_b = d_s = d`, a constant tuned on the previous period.

### Practical implementation

1. Choose an option universe and rebalancing observation grid.
2. Compute the current benchmark delta.
3. Build a symmetric or asymmetric band around delta.
4. Trade only on band exit and only to the nearest boundary.
5. Compute terminal tracking errors over a rolling basket of options.
6. Tune boundary parameters on period `k-1`; deploy them out-of-sample in period `k`.
7. Refit on period `k` for the next deployment period.
8. Add a jump-regime rule; Chen finds that suspending the next hedge after very large futures jumps improved the historical S&P 500 futures-option exercise, but this is dataset-specific and must be revalidated.

### Gamma Scalper interpretation

This is an excellent production baseline because its band can be calibrated directly against the application's own cost-adjusted hedge-error objective without solving a full HJB.

---

## 3. Hodges and Clewlow - Optimal Delta-Hedging under Transaction Costs

### Role in the application

This is the exact dynamic-programming benchmark for a utility-optimal hedge under transaction costs. It clarifies that both **band width and band center** matter and that a fixed-cost component changes the optimal jump behavior.

### Assumptions

- One underlying asset with diffusion dynamics `dS = mu(S,t)dt + sigma(S,t)dz`.
- One cash account earning a constant rate.
- European contingent claim with terminal payoff.
- Transaction cost `k(v,S)` depends on signed volume and spot; proportional costs are the main numerical case.
- The investor is risk-averse and maximizes expected utility or, equivalently, minimizes a loss function of replication error.
- The numerical solution uses a binomial approximation and dynamic programming.

### State variables

- Time `t`.
- Spot `S`.
- Number of shares `x`.
- Cash `y`.
- Claim liability and terminal liquidation costs.

### Objective function

```text
J(t,S,x,y) = max E[U(w_T)],
```

where terminal wealth includes cash, stock liquidation proceeds net of costs, and the option payoff/liability. Reservation buy and sell prices are defined by utility indifference.

### No-transaction policy

- Proportional costs produce lower and upper control boundaries.
- If the current holding exits the band, transact back to the boundary.
- With a fixed cost component, it may be optimal to jump into the interior rather than merely to the edge.

### Practical implementation in the paper

1. Solve the optimal-control problem backward on a binomial stock lattice.
2. Store lower and upper no-transaction boundaries for each time/price node.
3. Simulate daily underlying paths.
4. Interpolate the precomputed boundaries at the current spot.
5. If the hedge is outside the band, trade to the nearest edge.
6. Compare cost mean and variance with Black-Scholes, Leland and a heuristic band strategy.

The paper's simulation uses a one-year horizon, daily minimum revision, `S0=100`, annualized volatility `30%`, risk-free rate `0`, proportional underlying cost `1%`, and 1,000 paths. It studies a call and a bull spread.

### Key implementation lessons

- The optimal method works naturally for mixed long/short portfolios and non-convex aggregate payoffs.
- Leland's volatility adjustment is less natural for a bull spread because the aggregate gamma changes sign.
- The band center is not necessarily identical to Black-Scholes delta.
- The exact solution is a benchmark and calibration oracle, not the first live implementation, because its grid cost grows rapidly with state dimension.

---

## 4. Arzel and Lehdili - Bridging Stochastic Control and Deep Hedging

### Role in the application

This source provides the clearest bridge from a stochastic-control no-trade band to a neural policy with a structural prior.

### Assumptions

- European option on a GBM underlying.
- Risk-free bond.
- Symmetric proportional transaction cost `lambda`.
- CARA utility `u(x)=1-exp(-gamma x)`.
- The core numerical comparison sets up a short call and uses Black-Scholes delta/gamma.
- The Whalley-Wilmott approximation is valid for small transaction costs and is reported as useful for small-to-moderate costs.

### State variables

**Stochastic control**

- Time `t`.
- Spot `S_t`.
- Stock holding `y_t`.
- Cash `X_t`; CARA factorization removes it from the reduced QVI.

**Deep hedging**

- Log-moneyness `log(S/K)`.
- Time to maturity.
- Volatility.
- Previous hedge for the plain MLP; the band network removes previous hedge from the boundary network input and applies a clamp afterward.

### Objective functions

**CARA control**

```text
sup_(l,m>=0) E[u(X_T + y_T S_T - lambda S_T |y_T| - payoff(S_T))].
```

**HJB-QVI**

The buy, sell and no-trade operators satisfy

```text
max(A, B, C) = 0,
```

and no trade is optimal when

```text
(1-lambda)S <= U_y/U_X <= (1+lambda)S.
```

**Deep hedging**

Terminal P&L is

```text
X = -payoff(S_T) + sum_t y_t (S_(t+dt)-S_t)
    - sum_t lambda S_t |y_t-y_(t-1)|,
```

and the loss is entropic risk

```text
rho_gamma(X) = (1/gamma) log E[exp(-gamma X)].
```

### Band formula

The frictionless optimal position under CARA is

```text
y* = Delta_BS + (mu-r)/(sigma^2 gamma S exp(r(T-t))).
```

Under `mu=r`, the center reduces to Black-Scholes delta. The Whalley-Wilmott half-width is

```text
h_WW = [3 lambda exp(-r tau) S Gamma_BS^2 / (2 gamma)]^(1/3).
```

Trade only when outside `[y*-h_WW, y*+h_WW]`, then move to the nearest edge.

### Network implementations

- `NTBN-Delta`: network outputs non-negative lower and upper half-widths around Black-Scholes delta.
- `WW-NTBN`: initialize the half-width with `h_WW`, learn residual corrections, and use a differentiable soft clamp.
- The structural prior improves convergence and cross-cost generalization in the reported experiments.
- The trade-off is model dependence: using Black-Scholes delta/gamma introduces lognormal assumptions.

### Gamma Scalper interpretation

Use `h_WW` as the first live baseline and as a feature/prior for any learned band. Do not treat it as exact in high-cost, jump-heavy or liquidity-stressed regimes.

---

## 5. Mastinsek and free replacements

### What can be established from the accessible abstract

Mastinsek studies discrete-time delta hedging and derives a discrete-time adjusted Black-Scholes-Merton equation. The method anticipates the time sensitivity of delta so that the delta depends on the rebalancing interval, then applies the framework to transaction costs and obtains a closed-form call delta. The full derivation is subscription-only, so its assumptions and formulas cannot be responsibly reconstructed beyond the abstract.

### Recommended open replacement 1 - Artur Sepp

**An Approximate Distribution of Delta-Hedging Errors in a Jump-Diffusion Model with Discrete Trading and Transaction Costs** is the best practical replacement for this application because it directly combines:

- Discrete rebalancing.
- Jump-diffusion paths.
- Transaction costs.
- An approximate hedging-error distribution.
- An explicit trade-off between hedging frequency, error and cost.

Use it to validate the simulator's frequency sweep and to build an analytic approximation for expected cost and P&L variance.

### Recommended open replacement 2 - Artur Sepp

**When You Hedge Discretely: Optimization of Sharpe Ratio for Delta-Hedging Strategy under Discrete Hedging and Transaction Costs** is useful when the application needs an explicit optimal scheduled hedge frequency rather than an event-driven band.

### Recommended open replacement 3 - Broden and Tankov

**Tracking Errors from Discrete Hedging in Exponential Levy Models** provides jump-model robustness and compares delta hedging with quadratic hedging. It is especially valuable for testing irregular payoffs and for showing that equidistant delta hedging can have poor convergence under jumps.

### Already uploaded free supplement

**A Portfolio Approach to Risk Reduction in Discretely Rebalanced Option Hedges** studies accumulated, correlated hedge errors and demonstrates why portfolio-level hedging and error covariance matter. Use it when the app moves from one option to a book.

---

## 6. Carr and Wu - Variance Risk Premia

### Role in the application

This source provides the **risk-neutral implied-variance side** of the gamma-scalping signal and explains why implied variance is not simply a forecast of physical realized variance.

### Assumptions

- A variance swap has zero initial value.
- Under no arbitrage, its fixed rate is the risk-neutral expectation of future realized variance.
- A static continuum of OTM European options plus dynamic futures approximately replicates return quadratic variation.
- Replication is exact under continuous underlying paths.
- With jumps, the instantaneous approximation error is third order in jump size.
- Practical finite-strike implementation requires interpolation and extrapolation.
- Deterministic rates are used in the derivation; futures/forward structure handles dividends.

### State variables

- Spot/futures/forward price.
- Maturity and discount factor.
- OTM call and put prices over strike.
- Realized return variance over the same horizon.
- Synthetic variance swap rate.
- Variance risk premium.

### Objective/quantity

Variance swap payoff:

```text
(RV_(t,T) - SW_(t,T)) * notional.
```

No-arbitrage rate:

```text
SW_(t,T) = E_Q[RV_(t,T)].
```

Option-strip approximation:

```text
E_Q[RV] ~= (2/(T-t)) integral_0^infinity OTM(K,T)/(B(t,T) K^2) dK.
```

The paper's realized premium convention is

```text
RP = realized variance - variance swap rate.
```

For live decisions, replace ex-post realized variance with the RV module's physical forecast:

```text
forward_VRP = E_P[future RV] - E_Q[future RV].
```

### Practical implementation

1. Build an arbitrage-clean option surface.
2. Determine forward and discount factor.
3. Select OTM puts below the forward and OTM calls above it.
4. Integrate option price divided by strike squared.
5. Interpolate between maturities to the desired horizon.
6. Compare with a same-horizon physical RV forecast.
7. Convert the variance spread into expected gamma P&L.
8. Subtract expected hedge costs and a model-risk/tail-risk buffer.

### Gamma Scalper interpretation

A positive `E_P[RV]-E_Q[RV]` supports long gamma; a negative value supports short variance economically, but short-gamma execution belongs to a different risk mandate. The paper documents historically negative index variance risk premia, so a long-gamma scalper requires selective timing, not permanent exposure.

---

## 7. Francois, Gauthier, Godin and Perez-Mendoza - Deep Hedging with Options Using the Implied Volatility Surface

### Role in the application

This is the advanced policy layer: use the full implied-volatility surface, a realistic joint simulator, multiple hedging instruments and a global terminal-risk objective.

### Assumptions

- Short portfolio of European options; the numerical case is an ATM straddle.
- Self-financing hedge with cash, underlying and a longer-dated option.
- Daily rebalancing in the paper's experiments.
- Proportional cost `kappa_1` for the underlying and `kappa_2` for the hedging option, with option costs materially larger.
- Joint dynamics of returns and five IV-surface factors are generated by the JIVR model.
- Policy is learned with a recurrent/feed-forward neural network.

### State variables

- Underlying `S_t`.
- Five IV factors: long-term ATM level, term slope, moneyness slope, smile attenuation and smirk.
- Variance states for the IV factors.
- Conditional return variance.
- Time to maturity.
- Target portfolio value, delta and gamma.
- Hedging-option price.
- Hedge portfolio value.
- Current underlying and hedge-option positions.

### Objective function

Terminal shortfall:

```text
xi_T = target_portfolio_payoff_or_value - hedge_portfolio_value.
```

The policy minimizes one of:

```text
MSE   = E[xi_T^2]
SMSE  = E[xi_T^2 1{x_i >= 0}]
CVaR  = E[xi_T | xi_T exceeds VaR threshold].
```

A soft tracking-error constraint penalizes pathological speculative/doubling behavior.

### Practical implementation

1. Fit or source a joint return/IV-surface simulator.
2. Generate state paths and option marks/Greeks.
3. Simulate underlying and optional option-hedge trades with separate cost schedules.
4. Train policies for MSE, downside-only loss and CVaR.
5. Add anti-speculation constraints.
6. Evaluate on independent simulated paths and chronological historical backtests.
7. Perform ablations with and without IV-surface states.
8. Track turnover, trade size, cost, tail loss and exposure to the variance risk premium.

### Gamma Scalper interpretation

The main engineering insight is not merely "use AI." It is that the policy needs forward-looking IV-surface states and a realistic cost model. The paper reports smaller, more gradual trades and better resilience to transaction costs. This should be a later milestone after the deterministic band and simulator are validated.

---

# Cross-paper disagreements and reconciliation

## Continuous hedging versus discrete execution

- Black-Scholes-style theory makes continuous adjustment the ideal.
- Andersen supplies a continuously motivated but discretely measured volatility state.
- Chen, Hodges-Clewlow and Arzel-Lehdili show that continuous adjustment is not optimal with costs.
- The reconciliation is: observe frequently, decide frequently, but transact only on a band breach.

## Fixed hedge frequency versus event-driven bands

- Mastinsek/Sepp-style work treats the rebalancing interval as a decision variable.
- No-trade-band work makes trade time endogenous to state movement.
- A practical engine can combine both: evaluate the band on a fine grid, impose a minimum decision interval and maximum stale-hedge interval, and trade only if the band is breached or a hard risk limit forces action.

## Band center

- Chen's practical rule centers on Black-Scholes delta.
- Arzel-Lehdili show that the exact CARA frictionless center also contains a Merton speculative demand unless `mu=r`.
- Hodges-Clewlow show that the optimal center can differ from Black-Scholes delta.
- The safe first production choice is a risk-neutral delta center with no speculative drift term. Later, learn a bounded residual center shift from IV-surface and realized-volatility states.

## Band width

- Whalley-Wilmott gives a transparent cubic-root approximation.
- Chen tunes a simpler constant or categorized offset from realized hedge errors.
- Hodges-Clewlow obtain the exact numerical band for the assumed model.
- Deep hedging learns residual asymmetric widths.
- Recommended hierarchy: WW prior -> rolling empirical calibration -> exact-control benchmark -> learned residual.

## Volatility signal

- Andersen estimates future variance under the physical measure.
- Carr-Wu extracts variance under the risk-neutral measure.
- Deep IV-surface hedging uses richer state dynamics and recognizes time-varying variance risk premium.
- Therefore the entry signal is not `RV > IV` in mismatched units. It is a horizon-aligned, cost-adjusted estimate of `E_P[RV] - E_Q[RV]`, translated into expected gamma P&L.

## Objective function

- Expected utility/entropic risk is economically coherent but requires a risk-aversion parameter.
- Tracking-error MSE is simple and auditable but penalizes gains and losses symmetrically.
- SMSE and CVaR focus on shortfall/tail risk.
- For production, report all of them. Optimize one primary metric but enforce hard drawdown, liquidity and inventory limits independently.

## Model risk

- GBM/Black-Scholes provides tractable delta, gamma and bands.
- Jumps, surface dynamics and liquidity violate those assumptions.
- Production acceptance should require performance under GBM, stochastic volatility, jump diffusion, historical replay, spread shocks and delayed fills.
