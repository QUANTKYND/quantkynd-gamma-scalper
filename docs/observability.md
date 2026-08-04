# Observability

The system must make degraded state obvious. Silent fallback is a defect.

## Correlation fields

Every operational record carries the identifiers that exist for its lifecycle:

```text
correlation_id
strategy_id
strategy_run_id
candidate_id
intent_id
risk_decision_id
order_id
broker_order_id
fill_id
position_id
reconciliation_id
instrument_id
contract_id
```

## Structured logs

Logs are JSON in paper environments. Required fields:

```text
timestamp
level
service
process
version
environment
event
correlation_id
source_commit
```

Logs never include credentials or complete sensitive broker payloads.

## Metrics

### Market data

- Connection state.
- Subscription state.
- Events received and accepted.
- Events rejected by quality policy.
- Sequence gaps.
- Exchange-to-receive lag.
- Receive-to-process lag.
- Latest eligible quote age.
- Chain coverage by expiry and strike.

### Analytics

- IV solve success and failure counts.
- Surface build duration.
- Surface arbitrage violations.
- Forecast age and horizon coverage.
- Opportunity candidates accepted and rejected by reason.

### Strategy and risk

- Open positions.
- Net delta, gamma, theta, and vega.
- Premium at risk.
- Daily P&L and drawdown.
- Theta budget consumed.
- Hedge count.
- Risk approvals and rejections.
- Kill-switch state.

### Execution

- Intents created.
- Orders submitted, acknowledged, rejected, cancelled, and filled.
- Partial fills.
- Idempotency conflicts.
- Order-state age.
- Reconciliation differences.
- Fill slippage and fees.

### System

- API latency and errors.
- Worker heartbeat age.
- Queue or stream lag.
- Postgres pool usage.
- Redis latency and errors.
- Process memory and CPU.

## Decision journal

Every strategy decision records:

- Point-in-time market snapshot references.
- Data-quality state.
- Forecast and implied-variance inputs.
- Strategy and policy versions.
- Edge decomposition.
- Current portfolio and Greeks.
- Hedge boundaries.
- Risk evaluation.
- Resulting intent or hold reason.

The journal is immutable and queryable.

## Alerts

Critical:

- Kill switch engaged.
- Position or cash reconciliation mismatch.
- Stale or missing feed while positions are open.
- Unknown broker order state.
- Daily loss breach.
- Max absolute delta breach.
- Paper worker heartbeat missing.

Warning:

- Surface degradation.
- Quote coverage below threshold.
- Elevated spread or slippage.
- Forecast expired.
- Redis unavailable with fallback active.
- Research worker resource saturation.

## Dashboard workspaces

- System health.
- Market-data freshness and quality.
- RV forecasts.
- Option chain and IV surface.
- Gamma opportunities.
- Position and Greek book.
- Hedge controller and timeline.
- Orders, fills, and reconciliation.
- P&L attribution.
- Risk limits and kill switch.
- Research runs and artifacts.
