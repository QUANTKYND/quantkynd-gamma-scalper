from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.execution.models import ExecutionCostParameters


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SimulationClockConfig(StrictFrozenModel):
    timezone: str
    trading_periods_per_year: int = Field(gt=0)
    calendar_mode: Literal["weekdays"]
    decision_times_local: tuple[time, ...]

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("clock timezone must be an IANA timezone") from exc
        return value

    @field_validator("decision_times_local")
    @classmethod
    def validate_decision_times(cls, value: tuple[time, ...]) -> tuple[time, ...]:
        if not value or tuple(sorted(value)) != value or len(set(value)) != len(value):
            raise ValueError("decision times must be non-empty, unique, and ordered")
        return value


class SyntheticOptionMarketConfig(StrictFrozenModel):
    multiplier: int = Field(gt=0)
    strike_interval: float = Field(gt=0)
    strikes_below: int = Field(ge=0)
    strikes_above: int = Field(ge=0)
    eligible_expiry_sessions: tuple[int, ...]
    relative_spread: float = Field(ge=0, le=1)
    synthetic_volume_base: int = Field(ge=0)
    synthetic_open_interest_base: int = Field(ge=0)

    @field_validator("eligible_expiry_sessions")
    @classmethod
    def validate_expiry_sessions(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or any(item <= 0 for item in value) or tuple(sorted(set(value))) != value:
            raise ValueError("eligible expiry sessions must be positive, unique, and ordered")
        return value


class SyntheticFuturesMarketConfig(StrictFrozenModel):
    instrument_id: str = Field(min_length=1)
    multiplier: int = Field(gt=0)
    delta_per_contract: float = Field(gt=0)
    expiry_rule: Literal["holding_horizon_plus_buffer"]
    expiry_buffer_sessions: int = Field(ge=0)


class SimulationMarketConfig(StrictFrozenModel):
    schema_version: Literal[1]
    market_id: str = Field(min_length=1)
    underlying: str = Field(min_length=1)
    clock: SimulationClockConfig
    options: SyntheticOptionMarketConfig
    futures: SyntheticFuturesMarketConfig


class CostModelConfig(StrictFrozenModel):
    fixed_cost_per_order: Decimal = Field(ge=0)
    proportional_notional_rate: Decimal = Field(ge=0)
    half_spread_per_unit: Decimal = Field(ge=0)
    slippage_per_unit: Decimal = Field(ge=0)

    @classmethod
    def from_parameters(cls, parameters: ExecutionCostParameters) -> CostModelConfig:
        return cls.model_validate(parameters.__dict__)

    def to_parameters(self) -> ExecutionCostParameters:
        return ExecutionCostParameters(**self.model_dump())


class RuntimeRiskInputs(StrictFrozenModel):
    manual_kill_switch_engaged: bool


class SimulationEntryAssumptions(StrictFrozenModel):
    edge_gate_mode: Literal["not_evaluated_hedge_policy_benchmark"]


class SimulationRunConfig(StrictFrozenModel):
    schema_version: Literal[1]
    simulator_version: str
    strategy_config_hash: str
    market_config_hash: str
    path_config_hash: str
    path_hash: str
    policy_id: str
    policy_parameters: dict[str, object]
    option_cost_model: CostModelConfig
    futures_cost_model: CostModelConfig
    runtime_risk_inputs: RuntimeRiskInputs
    entry_assumptions: SimulationEntryAssumptions
    accounting_tolerance: Decimal = Field(gt=0)
    quantity_rounding: Literal["nearest_integer_half_even"]

    @model_validator(mode="after")
    def validate_hashes(self) -> SimulationRunConfig:
        hashes = (
            self.strategy_config_hash,
            self.market_config_hash,
            self.path_config_hash,
            self.path_hash,
        )
        if any(not value.startswith("sha256:") or len(value) != 71 for value in hashes):
            raise ValueError("run configuration hashes must be SHA-256 identities")
        return self


def load_simulation_market_config(path: Path | str) -> SimulationMarketConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("simulation-market configuration must be a YAML mapping")
    return SimulationMarketConfig.model_validate(payload)


def simulation_market_config_hash(config: SimulationMarketConfig) -> str:
    return stable_hash(config.model_dump(mode="json"))


def simulation_run_config_hash(config: SimulationRunConfig) -> str:
    return stable_hash(config.model_dump(mode="json"))


def policy_config_hash(policy_id: str, parameters: dict[str, object]) -> str:
    return stable_hash({"policy_id": policy_id, "parameters": parameters})


def stable_hash(payload: object) -> str:
    encoded = canonical_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def canonical_json(payload: object) -> str:
    return json.dumps(_normalize(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    return value
