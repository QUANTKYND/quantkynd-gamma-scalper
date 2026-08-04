# Acceptance Gates

## Strategy Contract gate

- One underlying and one structure.
- Exact selection, entry, hedge, exit, sizing, and risk rules.
- Versioned configuration and hash.
- No discretionary gaps.

## Deterministic option engine gate

- Reference pricing tests pass.
- Put-call parity passes.
- IV round trips pass over the approved domain.
- Greeks match finite differences within tolerance.
- Units and conventions are documented.
- Invalid inputs fail explicitly.

## Hedge simulator gate

- Deterministic replay by seed.
- Ledger reconciles to machine or accounting tolerance.
- Frictionless higher-frequency hedging reduces hedge error in controlled cases.
- More trading increases modeled costs.
- Cost increases affect band width in the expected direction for the baseline formula.
- Policies receive identical paths and information.
- P&L attribution sums to terminal P&L.

## Point-in-time data gate

- Contract identity is stable and validity-bounded.
- Historical chain reconstruction is deterministic.
- No future contract or quote leakage.
- Quote quality and exclusions are persisted.
- Exchange-session and timezone behavior is tested.
- Database migrations and restore path are tested.

## IV surface gate

- Valid prices solve IV or expose explicit failure.
- Price-IV round trips pass.
- Surface inputs and exclusions are reconstructable.
- Static-arbitrage diagnostics are visible.
- Implied variance declares strike coverage and interpolation risk.

## Opportunity engine gate

- Physical and implied variance horizons match.
- Net edge includes theta, option costs, expected hedge costs, and model-risk buffer.
- Eligibility rules use only point-in-time state.
- Rejected candidates expose reason codes.
- Opportunity results are reproducible from snapshot and configuration IDs.

## Historical replay gate

- Every decision, intent, order, fill, mark, and ledger entry is reconstructable.
- Same inputs produce the same event stream.
- Fill rules are conservative and explicit.
- Expiry and settlement reconcile.
- No same-event or future-event fill leakage.

## Robustness gate

- Out-of-sample evaluation exists.
- Neighboring parameters do not collapse performance.
- Costs and latency are stressed.
- Regime results are reported.
- Simple baselines remain included.
- Any selected policy has a documented reason beyond maximum backtest P&L.

## Live read-only gate

- Feed and subscription state are separate from authentication state.
- Sequence gaps and freshness are visible.
- Redis loss does not lose durable truth.
- Current state survives worker restart or rebuilds deterministically.
- Shadow decisions run without order submission across multiple sessions.

## Paper execution gate

- Risk precedes every order path.
- Idempotency prevents duplicates.
- Partial fills and cancel-replace work.
- Unknown acknowledgement state blocks unsafe retries.
- Positions and cash derive from fills and ledger entries.
- Reconciliation differences create lockouts.
- Kill switch works in tests.

## Paper acceptance gate

- Multi-session paper campaign completed.
- Failure drills completed.
- Every order and hedge is reconstructable.
- Greeks and positions match independent checks.
- Risk rules fired correctly.
- P&L attribution is stable and believable.
- Data freshness and missing-data behavior are visible.
- Restart recovery does not duplicate actions.
- No live-capital route exists.
