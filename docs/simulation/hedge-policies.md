# Hedge Policies

Every policy receives only current timestamp, step/session indexes, option delta and gamma, hedge delta, net delta, spot, time to expiry, risk-free rate, and futures delta per contract.

- `no_hedge` always records a hold.
- `fixed_interval` trades only on configured step multiples and targets configured net delta.
- `delta_threshold` holds at or within the absolute threshold and otherwise targets configured net delta.
- `constant_band` holds inside inclusive fixed boundaries and trades to the nearest breached boundary.
- `whalley_wilmott` computes the documented state-dependent half-width and trades to its nearest boundary.

Continuous futures quantity is `(target net delta - pre-hedge net delta) / futures delta per contract`. It rounds to the nearest integer contract with half-even ties. Zero-rounded requests hold.

Every decision separately records option, hedge, and net delta before the decision; continuous target, rounded request, and executed futures quantity; option, hedge, and net delta after the fill; the rounding residual; before/after portfolio value; per-session hedge count; and total hedge count. Summary statistics never mix policy-trigger delta with post-fill residual delta.
