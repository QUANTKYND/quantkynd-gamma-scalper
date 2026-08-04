from datetime import UTC, datetime

from app.hedging.models import HedgePolicyState
from app.hedging.policies import ConstantBandPolicy, DeltaThresholdPolicy, FixedIntervalPolicy, NoHedgePolicy


def state(net_delta: float, step: int = 1, contract_delta: float = 0.1) -> HedgePolicyState:
    return HedgePolicyState(
        datetime(2026, 1, 1, tzinfo=UTC),
        step,
        0,
        net_delta,
        0,
        net_delta,
        0.01,
        24000,
        0.05,
        contract_delta,
    )


def test_no_hedge_never_trades() -> None:
    decision = NoHedgePolicy().decide(state(100))
    assert decision.action == "hold"
    assert decision.requested_quantity == 0


def test_fixed_interval_only_trades_on_schedule() -> None:
    policy = FixedIntervalPolicy(2, 0)
    assert policy.decide(state(0.3, 1)).action == "hold"
    assert policy.decide(state(0.3, 2)).action == "sell_hedge"


def test_threshold_holds_then_trades_to_zero() -> None:
    policy = DeltaThresholdPolicy(0.1, 0)
    assert policy.decide(state(0.1)).action == "hold"
    decision = policy.decide(state(0.31))
    assert decision.requested_quantity == -3
    assert abs(decision.post_trade_residual_delta) < 0.011


def test_constant_band_trades_to_nearest_boundary() -> None:
    policy = ConstantBandPolicy(-0.1, 0.1)
    assert policy.decide(state(0.05)).action == "hold"
    lower = policy.decide(state(-0.31))
    upper = policy.decide(state(0.31))
    assert lower.action == "buy_hedge"
    assert lower.target_net_delta == -0.1
    assert upper.action == "sell_hedge"
    assert upper.target_net_delta == 0.1


def test_futures_rounding_is_half_even_and_residual_is_recorded() -> None:
    decision = DeltaThresholdPolicy(0, 0).decide(state(0.25, contract_delta=0.1))
    assert decision.continuous_target_quantity == -2.5
    assert decision.requested_quantity == -2
    assert decision.post_trade_residual_delta == 0.04999999999999999


def test_wider_band_produces_no_more_trades_on_same_states() -> None:
    path = [state(delta) for delta in (-0.3, -0.15, 0, 0.15, 0.3)]
    narrow = sum(ConstantBandPolicy(-0.05, 0.05).decide(item).action != "hold" for item in path)
    wide = sum(ConstantBandPolicy(-0.2, 0.2).decide(item).action != "hold" for item in path)
    assert wide <= narrow
