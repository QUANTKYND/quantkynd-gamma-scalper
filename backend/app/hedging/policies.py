from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from app.hedging.models import HedgeDecision, HedgePolicy, HedgePolicyState
from app.strategy.models import HedgingConfig


class NoHedgePolicy:
    policy_id = "no_hedge"

    def decide(self, state: HedgePolicyState) -> HedgeDecision:
        return _hold(state, self.policy_id, state.current_net_delta, None, None, "policy_never_hedges")


class FixedIntervalPolicy:
    policy_id = "fixed_interval"

    def __init__(self, interval_steps: int, target_net_delta: float):
        if interval_steps <= 0:
            raise ValueError("fixed hedge interval must be positive")
        self.interval_steps = interval_steps
        self.target_net_delta = target_net_delta

    def decide(self, state: HedgePolicyState) -> HedgeDecision:
        if state.step_index % self.interval_steps:
            return _hold(state, self.policy_id, self.target_net_delta, None, None, "outside_scheduled_step")
        return _trade_to_target(state, self.policy_id, self.target_net_delta, None, None, "scheduled_rebalance")


class DeltaThresholdPolicy:
    policy_id = "delta_threshold"

    def __init__(self, maximum_absolute_delta: float, target_net_delta: float):
        if maximum_absolute_delta < 0:
            raise ValueError("delta threshold must be non-negative")
        self.maximum_absolute_delta = maximum_absolute_delta
        self.target_net_delta = target_net_delta

    def decide(self, state: HedgePolicyState) -> HedgeDecision:
        if abs(state.current_net_delta) <= self.maximum_absolute_delta:
            return _hold(
                state,
                self.policy_id,
                self.target_net_delta,
                -self.maximum_absolute_delta,
                self.maximum_absolute_delta,
                "inside_delta_threshold",
            )
        return _trade_to_target(
            state,
            self.policy_id,
            self.target_net_delta,
            -self.maximum_absolute_delta,
            self.maximum_absolute_delta,
            "delta_threshold_breached",
        )


class ConstantBandPolicy:
    policy_id = "constant_band"

    def __init__(self, lower_boundary: float, upper_boundary: float):
        if lower_boundary >= upper_boundary:
            raise ValueError("constant hedge band is invalid")
        self.lower_boundary = lower_boundary
        self.upper_boundary = upper_boundary

    def decide(self, state: HedgePolicyState) -> HedgeDecision:
        if self.lower_boundary <= state.current_net_delta <= self.upper_boundary:
            return _hold(
                state,
                self.policy_id,
                state.current_net_delta,
                self.lower_boundary,
                self.upper_boundary,
                "inside_constant_band",
            )
        target = self.lower_boundary if state.current_net_delta < self.lower_boundary else self.upper_boundary
        return _trade_to_target(
            state,
            self.policy_id,
            target,
            self.lower_boundary,
            self.upper_boundary,
            "constant_band_breached",
        )


def build_hedge_policy(policy_id: str, config: HedgingConfig) -> HedgePolicy:
    if policy_id not in config.benchmark_policies:
        raise ValueError(f"unsupported hedge policy: {policy_id}")
    if policy_id == "no_hedge":
        return NoHedgePolicy()
    if policy_id == "fixed_interval":
        params = config.fixed_interval
        return FixedIntervalPolicy(params.interval_steps, params.target_net_delta_units)
    if policy_id == "delta_threshold":
        params = config.delta_threshold
        return DeltaThresholdPolicy(params.maximum_absolute_net_delta_units, params.target_net_delta_units)
    if policy_id == "constant_band":
        params = config.constant_band
        return ConstantBandPolicy(params.lower_net_delta_units, params.upper_net_delta_units)
    if policy_id == "whalley_wilmott":
        from app.hedging.whalley_wilmott import WhalleyWilmottPolicy

        return WhalleyWilmottPolicy(config.whalley_wilmott)
    raise ValueError(f"unsupported hedge policy: {policy_id}")


def _trade_to_target(
    state: HedgePolicyState,
    policy_id: str,
    target: float,
    lower: float | None,
    upper: float | None,
    reason: str,
) -> HedgeDecision:
    continuous = (target - state.current_net_delta) / state.futures_delta_per_contract
    requested = int(Decimal(str(continuous)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))
    residual = state.current_net_delta + requested * state.futures_delta_per_contract
    if requested == 0:
        return HedgeDecision(
            state.timestamp,
            policy_id,
            state.current_option_delta,
            state.current_hedge_delta,
            state.current_net_delta,
            target,
            lower,
            upper,
            "hold",
            continuous,
            0,
            residual,
            "rounded_quantity_zero",
        )
    return HedgeDecision(
        state.timestamp,
        policy_id,
        state.current_option_delta,
        state.current_hedge_delta,
        state.current_net_delta,
        target,
        lower,
        upper,
        "buy_hedge" if requested > 0 else "sell_hedge",
        continuous,
        requested,
        residual,
        reason,
    )


def _hold(
    state: HedgePolicyState,
    policy_id: str,
    target: float,
    lower: float | None,
    upper: float | None,
    reason: str,
) -> HedgeDecision:
    return HedgeDecision(
        state.timestamp,
        policy_id,
        state.current_option_delta,
        state.current_hedge_delta,
        state.current_net_delta,
        target,
        lower,
        upper,
        "hold",
        0.0,
        0,
        state.current_net_delta,
        reason,
    )
