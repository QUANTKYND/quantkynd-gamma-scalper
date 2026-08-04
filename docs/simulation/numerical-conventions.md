# Simulation Numerical Conventions

Pricing, Greeks, forward carry, generated paths, policy inputs, and attribution use Python `float`/NumPy `float64`. Black–Scholes uses continuously compounded rates and continuous dividend yield. Time is an explicit year fraction on every state, with 252 default trading periods per year.

Theta is price change per calendar year as calendar time advances. Vega is price change per unit volatility, so a move from 0.18 to 0.19 is multiplied by `0.01`. Delta is underlying-equivalent units and gamma is delta units per INR move. Contract multipliers are applied before portfolio aggregation.

Option valuation records name unit fields explicitly. `unit_price` and unit Greeks describe one underlying unit; `market_value` and portfolio Greeks equal the unit value multiplied by integer quantity and the configured contract multiplier.

Cash, notional, costs, realized P&L, and terminal accounting use `Decimal`. The single quantitative-to-accounting boundary is fill creation through `Decimal(str(value))`. INR values round to `0.01` with `ROUND_HALF_EVEN`.

Long option and futures quantities are positive. Buys reduce cash, sells increase cash, and positive costs reduce cash. Net portfolio delta is option-book delta plus futures delta. Timestamps are UTC and timezone-aware; exchange configuration remains Asia/Kolkata.

Futures prices are derived as `spot × exp((r-q) × remaining maturity)`. Remaining futures maturity starts at holding-horizon sessions plus the simulation-market expiry buffer, divided by configured trading periods per year, and declines by realized path fractions. Futures multiplier controls notional while futures delta per contract separately controls hedge exposure. Quantity targets round to the nearest integer with half-even ties.

Black–Scholes rejects non-finite spot, strike, time, volatility, rate, and dividend yield. Strict strategy, simulation-market, run, and cost configurations reject NaN and infinity. Negative time and volatility fail; zero time returns exact payoff and zero volatility follows the discounted deterministic payoff. The IV solver rejects non-finite or reversed bounds, non-positive tolerance, and non-positive iteration limits. It reports `converged`, `intrinsic_boundary`, `root_not_bracketed`, or `maximum_iterations_reached`; an intrinsic-boundary result may explicitly return zero volatility even when the supplied search lower bound is positive.
