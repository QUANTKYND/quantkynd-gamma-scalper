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
| LIVE-RV-1 | COMPLETE | Selectable Upstox index/equity history and a clearly provisional LTPC close-to-close overlay; read-only precursor, not the full LIVE-1 gate. |
| LIVE-RV-1.1 | COMPLETE | Accepted quote sequences, concurrent subscriptions, WebSocket lifecycle, segment status, and finalized rollover are hardened with deterministic evidence. |
| Strategy Contract v1 | COMPLETE | Frozen NIFTY long-straddle contract, typed risk limits, and stable behavioral hash. |
| SIM-1 deterministic option engine | COMPLETE | Contract-driven Black–Scholes, separate path/executable-state provenance, strict clock and finite inputs, explicit valuation units, and hardened IV outcomes. |
| SIM-2 hedge simulator | COMPLETE | Contract-owned maturities, executable entry and delta risk, correct P&L references, five policies, exact ledger, attribution, failed manifests, and full provenance. |
| DATA-1 point-in-time options model | ACTIVE | DATA-1.0 freezes deterministic semantics. DATA-1.1 and DATA-1.2 provide the accepted persistence and catalogue-ingestion foundation. DATA-1.3 deterministic Upstox V3 normalization is implementation complete with evidence recorded and independent review pending. Market-event persistence remains. |
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

DATA-1.1 implements the migration and persistence foundation with lazy typed configuration, one async transaction boundary, deterministic immutable inserts, two-clock repository reads, local test Postgres, and automated dump/restore equivalence verification. It does not yet implement provider catalogue ingestion, normalized quote/trade/quality persistence, chain snapshots, retention, Redis, or production backup operations.

DATA-1.3 implements the offline deterministic normalization boundary: immutable frame and lifecycle inputs, bounded owned-Protobuf decoding, point-in-time repository/static subject resolution, quote/status observations, partial failure reconciliation, union-scoped deferred declarations, golden synthetic fixtures, and canonical CLIs. Status is implementation complete with acceptance evidence recorded; independent review remains pending. Persistence, quality policy, replay storage, latest-state rebuilding, and live wiring remain later slices.

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
