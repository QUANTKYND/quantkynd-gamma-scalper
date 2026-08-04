# Deterministic Simulator Architecture

SIM-1 is an offline research pipeline. It loads the frozen strategy contract, generates a deterministic market path, constructs one matched European call/put pair, opens both legs through the explicit fill model, and processes each timestamp in order.

At a timestamp the engine marks instruments, recalculates option values and Greeks, aggregates portfolio delta, records risk decisions, invokes one hedge policy, applies an eligible simulated futures fill, and journals the resulting state. Risk exits precede routine hedging. Holding-period and simulation-end exits follow the timestamp decision. No future state is supplied to a policy.

The exact `Decimal` ledger and position lots are accounting truth. Black–Scholes values and beginning-of-interval Greek attribution are analytical views. Reconciliation compares terminal NAV with gross option P&L, gross futures P&L, financing, and separately accumulated costs.

There are no HTTP, WebSocket, broker, database, Redis, scheduler, or frontend boundaries. The CLI is the only run entry point.
