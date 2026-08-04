from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from typing import Literal

import numpy as np

from app.simulation.config import stable_hash
from app.simulation.clock import SimulationSession


@dataclass(frozen=True)
class GBMPathConfig:
    initial_spot: float
    drift: float
    realized_volatility: float
    number_of_steps: int
    step_year_fraction: float
    seed: int
    risk_free_rate: float = 0.06
    dividend_yield: float = 0.01
    implied_volatility: float = 0.18


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
    risk_free_rate: float = 0.06
    dividend_yield: float = 0.01
    implied_volatility: float = 0.18


@dataclass(frozen=True)
class UnderlyingPathPoint:
    timestamp: datetime
    session_date: date
    session_index: int
    step_index: int
    spot: float
    realized_step_year_fraction: float
    risk_free_rate: float
    dividend_yield: float
    implied_volatility: float


@dataclass(frozen=True)
class GeneratedUnderlyingPath:
    generator_id: Literal["user_provided", "gbm", "piecewise_volatility"]
    generator_version: Literal[2]
    seed: int | None
    canonical_parameters: dict[str, object]
    points: tuple[UnderlyingPathPoint, ...]
    path_hash: str


GeneratedPath = GeneratedUnderlyingPath


def generate_gbm_path(
    config: GBMPathConfig,
    sessions: tuple[SimulationSession, ...],
) -> GeneratedUnderlyingPath:
    _validate_common(config, sessions)
    if not math.isfinite(config.realized_volatility) or config.realized_volatility < 0:
        raise ValueError("realized volatility must be non-negative and finite")
    returns = _normal_returns(
        config.drift,
        (config.realized_volatility,) * config.number_of_steps,
        config.step_year_fraction,
        config.seed,
    )
    return _build_path("gbm", config, returns, sessions)


def generate_piecewise_path(
    config: PiecewisePathConfig,
    sessions: tuple[SimulationSession, ...],
) -> GeneratedUnderlyingPath:
    _validate_common(config, sessions)
    volatilities = [math.nan] * config.number_of_steps
    for regime in config.volatility_regimes:
        if (
            regime.start_step < 1
            or regime.end_step < regime.start_step
            or not math.isfinite(regime.volatility)
            or regime.volatility < 0
        ):
            raise ValueError("volatility regime is invalid")
        for step in range(regime.start_step, min(regime.end_step, config.number_of_steps) + 1):
            if not math.isnan(volatilities[step - 1]):
                raise ValueError("volatility regimes overlap")
            volatilities[step - 1] = regime.volatility
    if any(math.isnan(volatility) for volatility in volatilities):
        raise ValueError("volatility regimes must cover every generated step")
    returns = _normal_returns(config.drift, tuple(volatilities), config.step_year_fraction, config.seed)
    return _build_path("piecewise_volatility", config, returns, sessions)


def load_user_path(points: list[UnderlyingPathPoint] | tuple[UnderlyingPathPoint, ...]) -> GeneratedUnderlyingPath:
    if not points:
        raise ValueError("user-provided path cannot be empty")
    immutable = tuple(points)
    _validate_points(immutable)
    parameters = {"point_count": len(immutable)}
    return GeneratedUnderlyingPath(
        "user_provided",
        2,
        None,
        parameters,
        immutable,
        underlying_path_hash("user_provided", 2, None, parameters, immutable),
    )


def replace_path_points(
    path: GeneratedUnderlyingPath,
    points: tuple[UnderlyingPathPoint, ...],
) -> GeneratedUnderlyingPath:
    return replace(
        path,
        points=points,
        path_hash=underlying_path_hash(
            path.generator_id,
            path.generator_version,
            path.seed,
            path.canonical_parameters,
            points,
        ),
    )


def underlying_path_hash(
    generator_id: str,
    generator_version: int,
    seed: int | None,
    parameters: dict[str, object],
    points: tuple[UnderlyingPathPoint, ...],
) -> str:
    return stable_hash(
        {
            "generator_id": generator_id,
            "generator_version": generator_version,
            "seed": seed,
            "parameters": parameters,
            "points": [asdict(point) for point in points],
        }
    )


def _normal_returns(drift: float, volatilities: tuple[float, ...], dt: float, seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    shocks = generator.standard_normal(len(volatilities))
    volatility_array = np.asarray(volatilities, dtype=np.float64)
    return (drift - 0.5 * volatility_array**2) * dt + volatility_array * math.sqrt(dt) * shocks


def _build_path(
    generator_id: Literal["gbm", "piecewise_volatility"],
    config: GBMPathConfig | PiecewisePathConfig,
    returns: np.ndarray,
    sessions: tuple[SimulationSession, ...],
) -> GeneratedUnderlyingPath:
    parameters = _canonical_parameters(config)
    spots = [config.initial_spot]
    for path_return in returns:
        spots.append(spots[-1] * math.exp(float(path_return)))
    points = tuple(
        UnderlyingPathPoint(
            timestamp=session.decision_at,
            session_date=session.session_date,
            session_index=session.session_index,
            step_index=step,
            spot=spot,
            realized_step_year_fraction=session.year_fraction_from_previous,
            risk_free_rate=config.risk_free_rate,
            dividend_yield=config.dividend_yield,
            implied_volatility=config.implied_volatility,
        )
        for step, (spot, session) in enumerate(zip(spots, sessions, strict=True))
    )
    _validate_points(points)
    path_hash = underlying_path_hash(generator_id, 2, config.seed, parameters, points)
    return GeneratedUnderlyingPath(generator_id, 2, config.seed, parameters, points, path_hash)


def _validate_common(
    config: GBMPathConfig | PiecewisePathConfig,
    sessions: tuple[SimulationSession, ...],
) -> None:
    numeric = (
        config.initial_spot,
        config.drift,
        config.step_year_fraction,
        config.risk_free_rate,
        config.dividend_yield,
        config.implied_volatility,
    )
    if not all(math.isfinite(value) for value in numeric):
        raise ValueError("path inputs must be finite")
    if config.initial_spot <= 0 or config.number_of_steps <= 0 or config.step_year_fraction <= 0:
        raise ValueError("path price, step count, and year fraction must be positive")
    if config.implied_volatility < 0:
        raise ValueError("implied volatility must be non-negative")
    if len(sessions) != config.number_of_steps + 1:
        raise ValueError("simulation clock point count must match generated path")
    if any(
        session.year_fraction_from_previous != config.step_year_fraction
        for session in sessions[1:]
    ):
        raise ValueError("path year fraction must match simulation clock")


def _validate_points(points: tuple[UnderlyingPathPoint, ...]) -> None:
    for index, point in enumerate(points):
        numeric = (
            point.spot,
            point.realized_step_year_fraction,
            point.risk_free_rate,
            point.dividend_yield,
            point.implied_volatility,
        )
        if point.timestamp.tzinfo is None or not all(math.isfinite(value) for value in numeric):
            raise ValueError("underlying path points must be timezone-aware and finite")
        if point.spot <= 0 or point.realized_step_year_fraction < 0 or point.implied_volatility < 0:
            raise ValueError("underlying path point values are invalid")
        if point.step_index != index:
            raise ValueError("underlying path step indexes must be contiguous")
        if index == 0 and point.realized_step_year_fraction != 0:
            raise ValueError("initial underlying path point must have zero elapsed time")
        if index and point.timestamp <= points[index - 1].timestamp:
            raise ValueError("underlying path timestamps must be strictly increasing")


def _canonical_parameters(config: GBMPathConfig | PiecewisePathConfig) -> dict[str, object]:
    return {
        key: _json_value(value)
        for key, value in asdict(config).items()
        if key != "seed"
    }


def _json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value
