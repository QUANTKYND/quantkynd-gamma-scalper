# Strategy Decision Log

## Version 1 — 2026-08-04

The first executable contract freezes NIFTY 50, a long cash-settled European near-forward-ATM straddle, a five-session forecast and holding horizon, next-session entry, one concurrent position, simulated NIFTY futures hedging, five deterministic benchmark policies, and explicit risk exits.

The configuration uses forward moneyness because spot moneyness silently ignores carry. The expiry window includes a two-session safety buffer beyond the holding horizon. Tie-breakers include only point-in-time synthetic liquidity fields. The final lower-strike tie-break removes residual ambiguity.

Simulation is the only accepted mode. No live or paper execution path is authorized by this decision.
