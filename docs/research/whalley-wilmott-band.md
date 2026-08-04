# Whalley–Wilmott No-Transaction Band

SIM-1 implements the small-cost asymptotic band reported by Arzel and Lehdili, *Bridging Stochastic Control and Deep Hedging*, as their Whalley–Wilmott structural prior. The repository extraction records the formula and its relationship to the original Whalley–Wilmott approximation.

With risk-neutral drift, the frictionless center is Black–Scholes portfolio delta. For proportional transaction-cost rate `lambda`, spot `S`, remaining time `tau`, continuously compounded risk-free rate `r`, portfolio gamma `Gamma`, and CARA risk aversion `a`, the half-width is:

```text
h = [3 lambda exp(-r tau) S Gamma² / (2 a)]^(1/3)
```

SIM-1 expresses `h` and both boundaries as portfolio delta in underlying-equivalent units. `lambda` is a dimensionless proportional rate. `S` is INR per underlying unit. `Gamma` is the absolute change in portfolio underlying-equivalent delta per INR move. `a` is inverse INR. Contract quantities and multipliers are aggregated into portfolio gamma before the formula is called.

The policy is centered at zero net portfolio delta: `[-h, h]`. It holds inside the inclusive band and trades to the nearest boundary after a breach. The continuous futures target is divided by futures delta per contract, then rounded to the nearest integer with half-even ties. The post-trade residual is retained.

Zero cost or zero gamma produces a zero-width limiting band. Negative inputs, non-positive risk aversion or spot, and negative time fail. The configured maximum half-width caps the result, ensuring finite near-expiry behavior when Black–Scholes gamma becomes extreme.

This is a small-cost, diffusion, continuous-liquidity approximation. It is not exact for jumps, wide spreads, discrete contracts, stochastic volatility, liquidity stress, or large costs. The cap is an engineering safety convention, not part of the source formula.
