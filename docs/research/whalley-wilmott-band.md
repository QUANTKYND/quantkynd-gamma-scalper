# Whalley–Wilmott No-Transaction Band

SIM-1 implements the small-cost asymptotic band reported by Arzel and Lehdili, *Bridging Stochastic Control and Deep Hedging*, as their Whalley–Wilmott structural prior. The repository extraction records the formula and its relationship to the original Whalley–Wilmott approximation.

With risk-neutral drift, the frictionless center is Black–Scholes portfolio delta. For proportional transaction-cost rate `lambda`, spot `S`, portfolio gamma `Gamma`, and CARA risk aversion `a`, the half-width is:

```text
h = [3 lambda S Gamma² / (2 a)]^(1/3)
```

SIM-1 expresses `h` and both boundaries as portfolio delta in underlying-equivalent units. `lambda` is a dimensionless proportional rate. `S` is INR per underlying unit. `Gamma` is the absolute change in portfolio underlying-equivalent delta per INR move. `a` is inverse INR. Contract quantities and multipliers are aggregated into portfolio gamma before the formula is called.

The policy is centered at zero net portfolio delta: `[-h, h]`. It holds inside the inclusive band and trades to the nearest boundary after a breach. The continuous futures target is divided by futures delta per contract, then rounded to the nearest integer with half-even ties. The post-trade residual is retained.

`Gamma` is the absolute multiplier- and quantity-adjusted option-book gamma at the decision timestamp. The output is a half-width in the same portfolio underlying-equivalent delta units as the policy state. Transaction costs are a proportional, symmetric, dimensionless rate and risk aversion is inverse INR.

Zero cost or zero gamma produces a zero-width limiting band. Negative or non-finite inputs and non-positive risk aversion or spot fail. The formula has no explicit time or rate input. Near-expiry behavior enters only through portfolio gamma; the configured maximum half-width caps extreme values.

This is a small-cost, diffusion, continuous-liquidity approximation. It is not exact for jumps, wide spreads, discrete contracts, stochastic volatility, liquidity stress, or large costs. The cap is an engineering safety convention, not part of the source formula.
