# Risk Policy v1

The strategy configuration is the source of truth for provisional research limits. Starting NAV is INR 1,000,000. Premium at risk is capped at 2% of NAV and includes gross premium for both long option legs after quantity and contract multiplier plus configured entry transaction costs. Daily theta is capped at 0.1%, position loss at 1%, daily loss at 1.5%, and absolute portfolio delta at 0.10 underlying-equivalent units. Expected net edge must be at least 0.05% of NAV.

At most 12 hedges may occur in a session. The count and daily P&L reset on a new trading session; cumulative hedge count and position P&L do not. Option relative spread may not exceed 10%, and quotes older than five seconds are invalid in market-facing successors. Stale data, missing contracts, and reconciliation failures are lockouts. The simulation kill switch is enabled by construction.

These limits are research defaults, not suitability or profitability claims. A behavioral change requires a new configuration hash and review.
