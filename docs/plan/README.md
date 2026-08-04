# Plan Index

The plan is organized by capability rather than weeks.

| Plan | Outcome |
|---|---|
| [`roadmap.md`](roadmap.md) | Full milestone sequence and current position. |
| [`research.md`](research.md) | Research-valid strategy, estimators, simulator, costs, policies, and robustness. |
| [`options-market-infrastructure.md`](options-market-infrastructure.md) | Point-in-time contracts, market data, IV surfaces, implied variance, and live read-only state. |
| [`paper-trading-operations.md`](paper-trading-operations.md) | Intents, risk, paper orders, fills, positions, reconciliation, monitoring, and acceptance. |
| [`strategy-contract-v1.md`](strategy-contract-v1.md) | Proposed first narrow experiment. |
| [`acceptance-gates.md`](acceptance-gates.md) | Evidence required to move between milestone families. |

The active sequence is:

```text
Strategy Contract
        ↓
Deterministic Option and Hedge Simulator
        ↓
Point-in-Time Options Data
        ↓
Pricing, Greeks, and IV Surface
        ↓
Gamma Entry Engine
        ↓
Event-Driven Historical Replay
        ↓
Robustness
        ↓
Live Read-Only State
        ↓
Paper Execution and Risk
        ↓
Paper Acceptance Campaign
```
