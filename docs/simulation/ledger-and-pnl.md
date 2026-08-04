# Ledger and P&L

Every fill creates a position quantity change, a reference-notional cash flow, and one separately linked transaction-cost entry. Buy cash flow is negative and sell cash flow is positive. The executable fill price exposes the side-aware spread/slippage adjustment, while the reference notional and each cost component prevent double counting.

The accounting identity is:

```text
terminal P&L = terminal portfolio value - starting NAV
terminal P&L = gross option P&L + gross futures P&L
             + cash financing P&L - option costs - futures costs
```

The default reconciliation tolerance is INR 0.01. A larger residual fails the run. Greek attribution never changes ledger cash, positions, or exact P&L.

Entry premium at risk is the absolute reference notional of both long option fills plus their configured entry transaction costs. Each reference notional is `unit price × quantity × option multiplier`. Risk approval occurs before either entry fill is journaled as an open position.

Position P&L is current portfolio value minus starting NAV immediately before entry. Entry spread, slippage, fixed cost, and proportional cost therefore appear immediately in position and first-session P&L. Position P&L remains cumulative across sessions.

Session P&L is current portfolio value minus the prior session's final marked value. The first mark of a new session therefore includes the full overnight gain or loss. The per-session hedge count resets at that transition; total hedge count remains cumulative.
