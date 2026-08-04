# Strategy Contract v1

Status: proposed; must be explicitly frozen before historical strategy research.

## Research question

Can a narrowly selected long-gamma NIFTY position produce a positive and robust net result when entry is based on horizon-aligned expected variance versus implied variance and delta is managed by a cost-aware hedge policy?

## Proposed scope

| Field | v1 proposal |
|---|---|
| Underlying | NIFTY index family. |
| Option structure | Long near-ATM straddle. |
| Concurrent structures | One. |
| Forecast horizon | Five trading sessions. |
| Maximum holding horizon | Five trading sessions, subject to expiry and risk exits. |
| Expiry rule | One liquid expiry bucket with enough remaining life to cover the holding horizon. Exact DTE band must be frozen after data inspection. |
| Strike rule | Nearest eligible ATM strike using point-in-time forward or spot convention. Exact convention must be frozen. |
| Hedge instrument | NIFTY futures in simulation and paper state. |
| Entry | Net expected edge above threshold after option costs, expected hedge costs, theta, and model-risk buffer. |
| Hedge policies compared | Fixed interval, delta threshold, constant band, and Whalley–Wilmott band. |
| Exit | Horizon end, edge invalidation, risk exit, liquidity failure, expiry rule, or end-of-day policy. |
| Execution | Paper only. |

## Required strategy configuration

```yaml
strategy_id: nifty-long-gamma-v1
version: 1
underlying: NIFTY
position_template: long_atm_straddle
forecast_horizon_sessions: 5
maximum_holding_sessions: 5
expiry_rule:
  minimum_dte_sessions: pending
  maximum_dte_sessions: pending
strike_rule:
  reference: pending
  selection: nearest_eligible_atm
entry:
  minimum_net_expected_edge: pending
  minimum_quote_coverage: pending
  maximum_option_spread_bps: pending
  maximum_quote_age_ms: pending
hedging:
  instrument: nifty_future
  policy: pending
  maximum_hedges_per_session: pending
exit:
  close_at_horizon: true
  edge_invalidation: true
  liquidity_lockout: true
risk_policy_id: pending
execution_policy_id: paper-v1
```

## Hard risk policy to freeze

- Maximum premium at risk.
- Maximum daily loss.
- Maximum theta budget.
- Maximum absolute delta.
- Maximum hedge count.
- Maximum option spread.
- Maximum quote age.
- Maximum one-way slippage.
- No-new-entry cutoff.
- End-of-day carry or flatten rule.
- Behavior when futures or option quotes disagree or become stale.

## Success metrics

Research metrics:

- Net P&L distribution.
- Sharpe with explicit sampling convention.
- Maximum drawdown.
- CVaR.
- Gamma capture relative to theta.
- Forecast calibration.
- Hedge-error RMSE.
- Turnover and hedge count.
- Option and hedge costs.
- Cost per hedge.
- Parameter and regime stability.

Operational metrics:

- Rule adherence.
- Decision reconstruction rate.
- Reconciliation success.
- Feed freshness compliance.
- Duplicate-action count.
- Unknown-state duration.
- Kill-switch response.

## Freeze gate

The contract is frozen when every `pending` value is resolved or explicitly parameterized for a controlled experiment, and a reviewer can implement the strategy without discretionary interpretation.
