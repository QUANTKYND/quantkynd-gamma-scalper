# Strategy Decision Log

## Version 1 — 2026-08-04

The first executable contract freezes NIFTY 50, a long cash-settled European near-forward-ATM straddle, a five-session forecast and holding horizon, next-session entry, one concurrent position, simulated NIFTY futures hedging, five deterministic benchmark policies, and explicit risk exits.

The configuration uses forward moneyness because spot moneyness silently ignores carry. The expiry window includes a two-session safety buffer beyond the holding horizon. Tie-breakers include only point-in-time synthetic liquidity fields. The final lower-strike tie-break removes residual ambiguity.

Simulation is the only accepted mode. No live or paper execution path is authorized by this decision.

## SIM-1.2 correction — 2026-08-04

Underlying paths now contain only exogenous spot, rate, dividend, volatility, timestamp, and session data. The market contract and selected expiry derive executable option and futures maturities. Futures spread belongs only to the run cost model. Risk gates consume synthetic quote quality and liquidity; expected edge is deferred to EDGE-1. Absolute delta is enforced after routine policy decisions, position P&L includes entry costs, and session P&L includes overnight gaps.
