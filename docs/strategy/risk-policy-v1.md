# Risk Policy v1

The strategy configuration is the source of truth for provisional research limits. Starting NAV is INR 1,000,000. Premium at risk is capped at 2% of NAV and includes gross premium for both long option legs after quantity and contract multiplier plus configured entry transaction costs. Daily theta is capped at 0.1%, position loss at 1%, daily loss at 1.5%, and absolute portfolio delta at 0.10 underlying-equivalent units. Expected net edge must be at least 0.05% of NAV.

At most 12 hedges may occur in a session. The count resets on a new trading session; cumulative hedge count and position P&L do not. Position P&L references NAV immediately before entry, so entry costs are losses at entry. Session P&L references the prior session's final mark, so the first mark includes the overnight gap. Option relative spread may not exceed 10%, and synthetic volume and open interest must be positive. Quotes older than five seconds are invalid in market-facing successors. Stale data, missing contracts, and reconciliation failures are lockouts. The simulation kill switch is enabled by construction.

Premium, spread, liquidity, matched-straddle integrity, and absolute daily theta are executable pre-entry gates. Expected edge remains explicitly `not_evaluated` until EDGE-1 supplies a point-in-time edge input. The absolute-delta cap is a hard post-policy control: the simulator substitutes a risk-reducing hedge when possible and exits with `absolute_delta_unhedgeable` when contract granularity cannot satisfy the cap.

These limits are research defaults, not suitability or profitability claims. A behavioral change requires a new configuration hash and review.
