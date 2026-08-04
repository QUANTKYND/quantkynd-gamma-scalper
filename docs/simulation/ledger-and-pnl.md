# Ledger and P&L

Every fill creates a position quantity change, a reference-notional cash flow, and one separately linked transaction-cost entry. Buy cash flow is negative and sell cash flow is positive. The executable fill price exposes the side-aware spread/slippage adjustment, while the reference notional and each cost component prevent double counting.

The accounting identity is:

```text
terminal P&L = terminal portfolio value - starting NAV
terminal P&L = gross option P&L + gross futures P&L
             + cash financing P&L - option costs - futures costs
```

The default reconciliation tolerance is INR 0.01. A larger residual fails the run. Greek attribution never changes ledger cash, positions, or exact P&L.
