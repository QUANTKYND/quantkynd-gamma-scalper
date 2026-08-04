from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class UnderlyingConfig(StrictModel):
    name: Literal["NIFTY 50"]
    instrument_key: Literal["NSE_INDEX|Nifty 50"]
    currency: Literal["INR"]


class SignalConfig(StrictModel):
    origin: Literal["end_of_finalized_session"]
    forecast_horizon_sessions: int = Field(gt=0)


class EntryConfig(StrictModel):
    eligibility: Literal["next_session"]
    entry_time_local: time
    exchange_timezone: str

    @model_validator(mode="after")
    def validate_timezone(self) -> EntryConfig:
        try:
            ZoneInfo(self.exchange_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("entry exchange_timezone must be an IANA timezone") from exc
        return self


class ExpirySelectionConfig(StrictModel):
    holding_horizon_sessions: int = Field(gt=0)
    safety_buffer_sessions: int = Field(ge=0)
    minimum_remaining_sessions: int = Field(gt=0)
    maximum_remaining_sessions: int = Field(gt=0)
    choose: Literal["earliest_eligible"]
    require_quote_quality: bool
    require_liquidity: bool

    @model_validator(mode="after")
    def validate_session_bounds(self) -> ExpirySelectionConfig:
        required = self.holding_horizon_sessions + self.safety_buffer_sessions
        if self.minimum_remaining_sessions < required:
            raise ValueError("minimum_remaining_sessions must cover holding horizon and buffer")
        if self.maximum_remaining_sessions < self.minimum_remaining_sessions:
            raise ValueError("maximum_remaining_sessions must not be below minimum")
        return self


StrikeTieBreaker = Literal[
    "lowest_combined_relative_spread",
    "highest_combined_volume",
    "highest_combined_open_interest",
    "lower_strike",
]


class StrikeSelectionConfig(StrictModel):
    method: Literal["nearest_forward_atm"]
    tie_breakers: tuple[StrikeTieBreaker, ...]

    @model_validator(mode="after")
    def validate_tie_breakers(self) -> StrikeSelectionConfig:
        expected = (
            "lowest_combined_relative_spread",
            "highest_combined_volume",
            "highest_combined_open_interest",
            "lower_strike",
        )
        if self.tie_breakers != expected:
            raise ValueError("strike tie_breakers must use the v1 deterministic order")
        return self


class PositionConfig(StrictModel):
    structure: Literal["long_straddle"]
    direction: Literal["long"]
    call_quantity: Literal[1]
    put_quantity: Literal[1]
    units: int = Field(gt=0)
    maximum_concurrent_positions: Literal[1]
    exercise_style: Literal["european"]
    settlement_type: Literal["cash"]
    require_same_strike: Literal[True]
    require_same_expiry: Literal[True]
    require_same_multiplier: Literal[True]


class FixedIntervalParameters(StrictModel):
    interval_steps: int = Field(gt=0)
    target_net_delta_units: float


class DeltaThresholdParameters(StrictModel):
    maximum_absolute_net_delta_units: float = Field(ge=0)
    target_net_delta_units: float


class ConstantBandParameters(StrictModel):
    lower_net_delta_units: float
    upper_net_delta_units: float
    rebalance_target: Literal["nearest_boundary"]

    @model_validator(mode="after")
    def validate_boundaries(self) -> ConstantBandParameters:
        if self.lower_net_delta_units >= self.upper_net_delta_units:
            raise ValueError("constant-band lower boundary must be below upper boundary")
        return self


class WhalleyWilmottParameters(StrictModel):
    transaction_cost_rate: float = Field(ge=0)
    risk_aversion_per_inr: float = Field(gt=0)
    rebalance_target: Literal["nearest_boundary"]
    maximum_half_width_delta_units: float = Field(gt=0)


HedgePolicyId = Literal[
    "no_hedge",
    "fixed_interval",
    "delta_threshold",
    "constant_band",
    "whalley_wilmott",
]


class HedgingConfig(StrictModel):
    instrument: Literal["nifty_future"]
    delta_unit: Literal["portfolio_underlying_equivalent_units"]
    default_policy: HedgePolicyId
    benchmark_policies: tuple[HedgePolicyId, ...]
    fixed_interval: FixedIntervalParameters
    delta_threshold: DeltaThresholdParameters
    constant_band: ConstantBandParameters
    whalley_wilmott: WhalleyWilmottParameters

    @model_validator(mode="after")
    def validate_benchmarks(self) -> HedgingConfig:
        expected = (
            "no_hedge",
            "fixed_interval",
            "delta_threshold",
            "constant_band",
            "whalley_wilmott",
        )
        if self.benchmark_policies != expected:
            raise ValueError("benchmark_policies must contain the complete v1 policy order")
        if self.default_policy not in self.benchmark_policies:
            raise ValueError("default_policy must be included in benchmark_policies")
        return self


ExitReason = Literal[
    "invalid_market_state",
    "invalid_quote_state",
    "daily_loss_limit",
    "position_loss_limit",
    "maximum_hedge_count",
    "insufficient_time_to_expiry",
    "maximum_holding_period",
    "simulation_end",
]


class ExitConfig(StrictModel):
    precedence: tuple[ExitReason, ...]

    @model_validator(mode="after")
    def validate_precedence(self) -> ExitConfig:
        expected = (
            "invalid_market_state",
            "invalid_quote_state",
            "daily_loss_limit",
            "position_loss_limit",
            "maximum_hedge_count",
            "insufficient_time_to_expiry",
            "maximum_holding_period",
            "simulation_end",
        )
        if self.precedence != expected:
            raise ValueError("exit precedence must use the complete v1 order")
        return self


class RiskPolicyConfig(StrictModel):
    starting_nav_inr: float = Field(gt=0)
    maximum_concurrent_positions: Literal[1]
    maximum_premium_at_risk_fraction: float = Field(gt=0, le=1)
    maximum_daily_theta_fraction: float = Field(gt=0, le=1)
    minimum_expected_net_edge_fraction: float = Field(ge=0, le=1)
    maximum_position_loss_fraction: float = Field(gt=0, le=1)
    maximum_daily_loss_fraction: float = Field(gt=0, le=1)
    maximum_absolute_delta_units: float = Field(ge=0)
    maximum_hedges_per_session: int = Field(gt=0)
    maximum_option_relative_spread: float = Field(gt=0, le=1)
    maximum_quote_age_seconds: float = Field(gt=0)
    stale_data_lockout: Literal[True]
    missing_contract_lockout: Literal[True]
    reconciliation_lockout: Literal[True]
    manual_kill_switch: Literal[True]


class StrategyContractV1(StrictModel):
    schema_version: Literal[1]
    strategy_id: Literal["nifty-long-gamma-straddle"]
    strategy_version: Literal[1]
    created_at: datetime
    mode: Literal["simulation"]
    underlying: UnderlyingConfig
    signal: SignalConfig
    entry: EntryConfig
    expiry: ExpirySelectionConfig
    strike: StrikeSelectionConfig
    position: PositionConfig
    hedging: HedgingConfig
    exit: ExitConfig
    risk: RiskPolicyConfig

    @model_validator(mode="after")
    def validate_contract_alignment(self) -> StrategyContractV1:
        if self.signal.forecast_horizon_sessions != self.expiry.holding_horizon_sessions:
            raise ValueError("forecast and holding horizons must match in v1")
        if self.risk.maximum_concurrent_positions != self.position.maximum_concurrent_positions:
            raise ValueError("position and risk concurrency limits must match")
        return self
