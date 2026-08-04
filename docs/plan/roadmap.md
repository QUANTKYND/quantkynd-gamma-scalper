# Milestone Roadmap

## Status legend

- `COMPLETE`: acceptance evidence exists.
- `ACTIVE`: current implementation focus.
- `READY`: prerequisite gates are complete.
- `BLOCKED`: prerequisite or data dependency is missing.
- `LATER`: outside the paper-MVP critical path.

## Current position

| Milestone | Status | Outcome |
|---|---|---|
| Research synthesis | COMPLETE | Paper extraction, research matrix, and architecture direction. |
| RV-1 | COMPLETE | Correct daily close-to-close variance and volatility estimators. |
| RV-1.1 | COMPLETE | Evaluation, run persistence, labels, and documentation hardening. |
| Strategy Contract v1 | ACTIVE | Freeze one underlying, position template, horizon, selection rule, hedge instrument, exits, and hard risk limits. |
| SIM-1 deterministic option engine | READY | Black–Scholes, IV solver, Greeks, and explicit conventions. |
| SIM-2 hedge simulator | BLOCKED by SIM-1 | Ledger, costs, fills, P&L attribution, and policy comparison. |
| DATA-1 point-in-time options model | READY after strategy contract | Instruments, sessions, contracts, quotes, chains, storage, and quality. |
| OPTIONS-1 IV surface | BLOCKED by DATA-1 | Market-derived IV, Greeks, surface, and diagnostics. |
| EDGE-1 gamma opportunity engine | BLOCKED by OPTIONS-1 | Physical versus implied variance and net edge decomposition. |
| BACKTEST-1 event replay | BLOCKED by DATA-1, SIM-2, EDGE-1 | Point-in-time entries, hedges, fills, ledger, and journal. |
| BACKTEST-2 robustness | BLOCKED by BACKTEST-1 | Walk-forward and regime sensitivity. |
| LIVE-1 read-only state | BLOCKED by DATA-1 and OPTIONS-1 | Live feed, current chain, IV surface, Greeks, and shadow decisions. |
| PAPER-1 execution and risk | BLOCKED by LIVE-1 and BACKTEST-2 | Paper router, state machine, risk, ledger, and reconciliation. |
| PAPER-2 acceptance campaign | BLOCKED by PAPER-1 | Multi-session operational acceptance. |
| Deep hedging and learned bands | LATER | Learned residual policy after deterministic baselines. |
| Live-capital execution | LATER and separately approved | Not part of the paper MVP. |

## Milestone sequence

### M0 — Strategy Contract v1

Freeze the research question and paper operating limits.

Deliverables:

- `docs/plan/strategy-contract-v1.md` finalized.
- Versioned strategy configuration.
- Versioned risk policy.
- Explicit unresolved assumptions.

### SIM-1 — Deterministic option analytics

Deliver:

- European call and put valuation.
- IV inversion.
- Delta, gamma, theta, vega, and rho.
- Finite-difference and property tests.
- Explicit units and day-count conventions.

### SIM-2 — Deterministic hedge simulator

Deliver:

- Deterministic price paths.
- Option and hedge ledgers.
- Option and futures cost models.
- Fill policies.
- No hedge, fixed-frequency, threshold, constant-band, and Whalley–Wilmott policies.
- P&L attribution and reconciliation.

### DATA-1 — Point-in-time options data

Deliver:

- Instrument catalogue.
- Session calendar.
- Option and futures contract identity.
- Quote normalization.
- Chain snapshot reconstruction.
- Postgres persistence and migrations.
- Data-quality events.

### OPTIONS-1 — IV surface

Deliver:

- Quote eligibility.
- Mid and conservative executable marks.
- IV solving.
- Greeks from market inputs.
- Smile and term structure.
- Static-arbitrage diagnostics.
- Stored surface snapshots.

### EDGE-1 — Gamma opportunity engine

Deliver:

- Horizon-aligned physical variance.
- ATM proxy and option-strip implied variance.
- Gamma, theta, option cost, hedge cost, and model-risk decomposition.
- Eligibility and rejection reasons.
- Research dashboard workspace.

### BACKTEST-1 — Event-driven replay

Deliver:

- Historical point-in-time chain selection.
- Strategy events.
- Conservative fills.
- Orders, fills, positions, and cash ledger.
- Full journal and attribution.

### BACKTEST-2 — Robustness

Deliver:

- Walk-forward evaluation.
- Regime analysis.
- Parameter sensitivity.
- Cost and latency stress.
- Jump and stale-state scenarios.
- Out-of-sample report.

### LIVE-1 — Read-only state

Deliver:

- Live subscriptions.
- Sequence and freshness monitoring.
- Redis latest-state cache.
- Current chain, Greeks, and IV surface.
- Shadow entry and hedge intents with no order routing.

### PAPER-1 — Paper execution

Deliver:

- Broker-neutral order interface.
- Paper order router.
- Idempotency.
- Order state machine.
- Partial fills and cancellation.
- Risk pre-check.
- Positions, cash ledger, and reconciliation.
- Kill switch.

### PAPER-2 — Acceptance campaign

Run across enough sessions to encounter normal and degraded conditions. Operational success means rules, observability, reconciliation, and safe stopping work consistently.
