# Paper-Trading Operations Plan

## Objective

Operate the approved strategy against live read-only market state with broker-shaped paper execution, hard risk enforcement, durable journals, and continuous reconciliation.

The paper system is accepted for operational quality, not profitability.

## P0 — Live state engine

Responsibilities:

- Consume accepted market events.
- Maintain the latest underlying, futures, option-chain, Greek, and IV-surface state.
- Track feed freshness and sequence health.
- Maintain shadow positions during early dry runs.
- Emit state snapshots with IDs.
- Publish bounded updates through Redis and WebSocket.

Unknown, stale, or inconsistent state blocks new entries and routine hedges.

## P1 — Strategy loop

The loop is deterministic for a given state and configuration:

```text
read current state
validate freshness and quality
mark portfolio
compute Greeks and limits
assess entry, exit, or hedge policy
create hold decision or immutable intent
submit intent to risk
journal result
```

A heartbeat records last successful iteration and last state timestamp.

## P2 — Risk engine

Pre-trade checks:

- Kill switch.
- Market session.
- Feed freshness.
- Quote width and quality.
- Contract validity.
- Maximum open positions.
- Premium at risk.
- Daily loss.
- Theta budget.
- Absolute and projected delta.
- Hedge count.
- Duplicate intent.
- End-of-day rules.

Risk decisions are immutable and reference the state snapshot and policy version.

## P3 — Paper order router

The router mimics broker behavior:

- Accepted, rejected, pending, acknowledged, partial, filled, cancel pending, cancelled, replace pending, and unknown states.
- Configurable latency.
- Quote-dependent fill eligibility.
- Partial fills.
- Fees and slippage.
- Idempotency.
- Retry-safe acknowledgement handling.

The router consumes approved intents only.

## P4 — Ledger and positions

Deliver:

- Append-only order transitions.
- Fill records.
- Position lots.
- Cash ledger.
- Marks and Greeks.
- Realized and unrealized P&L.
- P&L attribution.

Portfolio state is derived from durable events, not mutable dashboard state.

## P5 — Reconciliation

Reconcile:

- Intent versus order.
- Order versus fill.
- Fill versus position.
- Position versus cash ledger.
- Internal paper state versus independent recomputation.
- Broker state later when a sandbox or broker paper interface exists.

Differences engage an appropriate lockout until resolved.

## P6 — Kill switch and degraded modes

Kill-switch scopes:

- Global.
- Strategy.
- Underlying.
- Execution worker.

Triggers:

- Operator action.
- Daily loss breach.
- Reconciliation mismatch.
- Unknown order state.
- Feed stale with open positions.
- Worker heartbeat timeout.
- Repeated broker rejection.
- Runaway hedge count.

Degraded modes:

- No new entries.
- Hedge-only.
- Reduce-only.
- Flatten.
- Fully stopped.

## P7 — Monitoring

Operator console shows:

- Service and worker health.
- Current market-data age.
- Positions and contract identity.
- Net Greeks.
- Theta consumed.
- Hedge boundaries and last decision.
- Intent, risk, order, and fill timeline.
- P&L attribution.
- Current limits and headroom.
- Reconciliation status.
- Active alerts and kill-switch state.

## P8 — Failure drills

Required drills:

- Feed disconnect during no position.
- Feed disconnect with open position.
- Sequence gap.
- Missing ATM contracts.
- Wide or no-bid option market.
- Paper rejection.
- Request timeout before acknowledgement.
- Duplicate intent.
- Partial fill.
- Cancel-replace race.
- Redis restart.
- Database restart.
- Strategy-worker restart.
- Max hedge count breach.
- Daily loss breach.
- End-of-day failure.

## P9 — Acceptance campaign

Run long enough to observe normal and degraded conditions. The system passes when:

- Every decision is reconstructable.
- Every order and fill is idempotent and journaled.
- Positions, Greeks, and cash reconcile.
- Risk controls fire in drills and real degraded states.
- The system stops safely when state is unknown.
- P&L attribution is stable and independently recomputable.
- Restart recovery does not duplicate actions.
- Operators can explain current ownership, risk, hedge history, theta burn, and stop reasons.

## Explicit exclusions

- Live-capital orders.
- Automatic kill-switch release.
- Unreviewed strategy configuration changes during a session.
- Deep-learning policy changes in the paper acceptance campaign.
- Multiple simultaneous strategy templates in v1.
