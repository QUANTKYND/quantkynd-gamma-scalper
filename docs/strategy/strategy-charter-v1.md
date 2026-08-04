# Strategy Charter v1

`nifty-long-gamma-straddle` version 1 is an offline research strategy for one long NIFTY 50 near-forward-ATM straddle. It is simulation-only and cannot create broker, paper-order, or live-capital actions.

The signal is formed after a finalized session and entry is first eligible at 09:30 Asia/Kolkata on the next session. The physical-variance forecast and maximum holding horizon are five completed sessions. The earliest expiry with 7–15 remaining sessions is eligible. The selected call and put share strike, expiry, multiplier, European exercise, and cash settlement.

The strike nearest the continuous-carry forward is selected. Ties use combined relative spread, volume, open interest, then the lower strike. One call and one put make one unit; only one concurrent strategy position is permitted.

The hedge instrument is a simulated NIFTY future. Research benchmarks are no hedge, fixed interval, delta threshold, constant band, and Whalley–Wilmott. Delta is always portfolio delta in underlying-equivalent units.

Exit triggers are evaluated in the fixed order encoded by the strategy configuration. Profit targets, trailing stops, short gamma, multiple positions, deep hedging, and live execution are excluded.
