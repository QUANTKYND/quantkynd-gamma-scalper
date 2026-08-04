# QuantKynd Gamma Scalper Documentation

This directory is the source of truth for the system plan, architecture, contracts, conventions, and delivery gates.

## Product objective

Build a research-valid and operationally safe paper-trading system for a narrow long-gamma strategy. The system must answer, for every decision:

- What volatility is expected under the statistical measure?
- What variance is implied by option prices?
- Is the expected spread large enough to survive theta, option execution costs, hedge costs, model error, and risk buffers?
- Which option contract or structure satisfies the frozen strategy contract?
- When should delta be left alone, and when should it be rebalanced?
- What does the system own, why does it own it, what risk does it carry, and why should it stop?

Profitability is a research result. Operational acceptance requires determinism, observability, reconciliation, safe failure, and rule compliance.

## Current position

Completed:

- Research synthesis and architecture direction.
- Daily close-to-close volatility foundation.
- Correct squared-log-return variance estimators.
- Naive and EWMA variance forecasts.
- Sequential forecast evaluation.
- Deterministic synthetic datasets and stable dataset identity.
- Persisted RV research runs and artifacts.
- FastAPI research API and React monitoring dashboard.
- RV-1 and RV-1.1 acceptance and hardening.
- LIVE-RV-1 selectable Upstox historical closes and provisional live close-to-close overlay.

Not yet implemented:

- Frozen strategy contract and risk policy.
- Deterministic option-pricing and Greek engine.
- Transaction-cost and fill models.
- Hedge-policy simulator and no-transaction bands.
- Point-in-time option contracts and quote history.
- IV smile, surface, and implied variance.
- Gamma opportunity engine.
- Event-driven historical replay.
- Full live read-only option state, surfaces, Greeks, and shadow decisions.
- Paper execution, risk enforcement, and reconciliation.

## Documents

| Document | Purpose |
|---|---|
| [`design.md`](design.md) | System architecture, process boundaries, dependency direction, and data flow. |
| [`environment.md`](environment.md) | Local, test, paper, and deployment environments. |
| [`dependencies.md`](dependencies.md) | Existing and planned software dependencies with adoption phases. |
| [`data-models.md`](data-models.md) | Core domain, persistence, event, research, strategy, and execution models. |
| [`api.md`](api.md) | Current and planned routers and procedures. |
| [`conventions.md`](conventions.md) | Code, frontend, API, time, units, naming, and documentation conventions. |
| [`performance.md`](performance.md) | Redis, caching, rendering, event batching, and performance budgets. |
| [`testing.md`](testing.md) | Quantitative, contract, integration, replay, and failure-testing strategy. |
| [`observability.md`](observability.md) | Logs, metrics, traces, journals, alerts, and operator views. |
| [`security.md`](security.md) | Secrets, broker boundaries, authorization, and paper-only safety. |
| [`plan/roadmap.md`](plan/roadmap.md) | Milestone-gated roadmap and current status. |
| [`plan/research.md`](plan/research.md) | Research-validity plan. |
| [`plan/options-market-infrastructure.md`](plan/options-market-infrastructure.md) | Point-in-time options data and analytics infrastructure. |
| [`plan/paper-trading-operations.md`](plan/paper-trading-operations.md) | Live state, paper execution, reconciliation, risk, and acceptance. |
| [`plan/strategy-contract-v1.md`](plan/strategy-contract-v1.md) | Proposed narrow v1 experiment contract. |
| [`plan/acceptance-gates.md`](plan/acceptance-gates.md) | Exit criteria for each milestone family. |

## Delivery model

The roadmap is milestone-gated, not calendar-driven. A later milestone does not begin because a week elapsed. It begins because the prior gate is satisfied with evidence.

```text
Research validity
        ↓
Options-market infrastructure
        ↓
Historical replay and robustness
        ↓
Live read-only state
        ↓
Paper execution and risk
        ↓
Paper-trading acceptance
```

Deep hedging, multiple hedging instruments, market impact, and live-capital execution are later stages and are not part of the production-grade paper MVP.
