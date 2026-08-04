from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import numpy as np

from app.simulation.market import MarketState, carry_futures_price


@dataclass(frozen=True)
class GBMPathConfig:
    initial_spot: float
    drift: float
    realized_volatility: float
    number_of_steps: int
    step_year_fraction: float
    seed: int
    start_at: datetime
    risk_free_rate: float = 0.06
    dividend_yield: float = 0.01
    implied_volatility: float = 0.18
    option_expiry_years: float = 15 / 252
    futures_maturity_years: float = 30 / 252


@dataclass(frozen=True)
class VolatilityRegime:
    start_step: int
    end_step: int
    volatility: float


@dataclass(frozen=True)
class PiecewisePathConfig:
    initial_spot: float
    drift: float
    volatility_regimes: tuple[VolatilityRegime, ...]
    number_of_steps: int
    step_year_fraction: float
    seed: int
    start_at: datetime
    risk_free_rate: float = 0.06
    dividend_yield: float = 0.01
    implied_volatility: float = 0.18
    option_expiry_years: float = 15 / 252
    futures_maturity_years: float = 30 / 252


@dataclass(frozen=True)
class GeneratedPath:
    generator_id: Literal["user_provided", "gbm", "piecewise_volatility"]
    generator_version: Literal[1]
    seed: int | None
    canonical_parameters: dict[str, object]
    states: tuple[MarketState, ...]
    path_hash: str


def generate_gbm_path(config: GBMPathConfig) -> GeneratedPath:
    _validate_common(config)
    if config.realized_volatility < 0:
        raise ValueError("realized volatility must be non-negative")
    returns = _normal_returns(
        config.drift,
        (config.realized_volatility,) * config.number_of_steps,
        config.step_year_fraction,
        config.seed,
    )
    return _build_path("gbm", config, returns)


def generate_piecewise_path(config: PiecewisePathConfig) -> GeneratedPath:
    _validate_common(config)
    volatilities = [math.nan] * config.number_of_steps
    for regime in config.volatility_regimes:
        if regime.start_step < 1 or regime.end_step < regime.start_step or regime.volatility < 0:
            raise ValueError("volatility regime is invalid")
        for step in range(regime.start_step, min(regime.end_step, config.number_of_steps) + 1):
            if not math.isnan(volatilities[step - 1]):
                raise ValueError("volatility regimes overlap")
            volatilities[step - 1] = regime.volatility
    if any(math.isnan(volatility) for volatility in volatilities):
        raise ValueError("volatility regimes must cover every generated step")
    returns = _normal_returns(config.drift, tuple(volatilities), config.step_year_fraction, config.seed)
    return _build_path("piecewise_volatility", config, returns)


def load_user_path(states: list[MarketState] | tuple[MarketState, ...]) -> GeneratedPath:
    if not states:
        raise ValueError("user-provided path cannot be empty")
    immutable = tuple(states)
    for previous, current in zip(immutable, immutable[1:], strict=False):
        if current.timestamp <= previous.timestamp:
            raise ValueError("path timestamps must be strictly increasing")
        if current.step_year_fraction <= 0:
            raise ValueError("non-initial user path steps need a positive year fraction")
    parameters = {"state_count": len(immutable)}
    return GeneratedPath("user_provided", 1, None, parameters, immutable, _path_hash("user_provided", parameters, immutable))


def _normal_returns(drift: float, volatilities: tuple[float, ...], dt: float, seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    shocks = generator.standard_normal(len(volatilities))
    volatility_array = np.asarray(volatilities, dtype=np.float64)
    return (drift - 0.5 * volatility_array**2) * dt + volatility_array * math.sqrt(dt) * shocks


def _build_path(generator_id: Literal["gbm", "piecewise_volatility"], config, returns: np.ndarray) -> GeneratedPath:
    parameters = _json_parameters(asdict(config), exclude={"seed"})
    spots = [config.initial_spot]
    for path_return in returns:
        spots.append(spots[-1] * math.exp(float(path_return)))
    states = tuple(_state(config, step, spot) for step, spot in enumerate(spots))
    return GeneratedPath(generator_id, 1, config.seed, parameters, states, _path_hash(generator_id, parameters, states, config.seed))


def _state(config, step: int, spot: float) -> MarketState:
    elapsed = step * config.step_year_fraction
    futures_maturity = max(config.futures_maturity_years - elapsed, 0.0)
    return MarketState(
        timestamp=config.start_at.astimezone(UTC) + timedelta(days=step),
        session_index=step,
        step_index=step,
        spot=spot,
        futures_price=carry_futures_price(spot, config.risk_free_rate, config.dividend_yield, futures_maturity),
        risk_free_rate=config.risk_free_rate,
        dividend_yield=config.dividend_yield,
        implied_volatility=config.implied_volatility,
        time_to_expiry_years=max(config.option_expiry_years - elapsed, 0.0),
        step_year_fraction=0.0 if step == 0 else config.step_year_fraction,
    )


def _validate_common(config) -> None:
    if config.initial_spot <= 0 or config.number_of_steps <= 0 or config.step_year_fraction <= 0:
        raise ValueError("path price, step count, and year fraction must be positive")
    if config.start_at.tzinfo is None:
        raise ValueError("path start timestamp must be timezone-aware")
    if config.option_expiry_years < config.number_of_steps * config.step_year_fraction:
        raise ValueError("option expiry must cover the generated path")


def _json_parameters(payload: dict[str, object], exclude: set[str]) -> dict[str, object]:
    return {key: _json_value(value) for key, value in payload.items() if key not in exclude}


def _json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _path_hash(generator_id: str, parameters: dict[str, object], states: tuple[MarketState, ...], seed: int | None = None) -> str:
    payload = {
        "generator_id": generator_id,
        "generator_version": 1,
        "seed": seed,
        "parameters": parameters,
        "states": [asdict(state) for state in states],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_value).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
