# Deterministic Simulator Architecture

SIM-1 is an offline research pipeline. The frozen strategy contract defines trading intent, selection bounds, sizing, policies, exits, and risk. A separate strict simulation-market contract defines the session clock, synthetic option-chain construction, strike grid, eligible expiries, liquidity, option and futures multipliers, futures identity, and futures delta per contract. Both contracts are persisted and hashed.

The clock interprets decisions in `Asia/Kolkata`, stores timezone-aware local and UTC timestamps, and derives expiry date and time-to-expiry from the same ordered sessions. Its current calendar is weekday-only and does not model NSE holidays or special sessions. Eligible expiries are generated in trading sessions and filtered by STRAT-1 bounds before the earliest eligible expiry is selected.

At a timestamp the engine marks instruments, recalculates option values and Greeks, aggregates portfolio delta, evaluates kill-switch, loss, hedge-count, delta, expiry-buffer, holding-period, and terminal exits, and only then invokes a hedge policy. If no exit is required, it records pre-decision state, applies an eligible simulated futures fill, and records post-fill state. No future state is supplied to a policy and no exit timestamp opens a routine hedge.

The exact `Decimal` ledger and position lots are accounting truth. Black–Scholes values and beginning-of-interval Greek attribution are analytical views. Reconciliation compares terminal NAV with gross option P&L, gross futures P&L, financing, and separately accumulated costs.

There are no HTTP, WebSocket, broker, database, Redis, scheduler, or frontend boundaries. The CLI is the only run entry point.
