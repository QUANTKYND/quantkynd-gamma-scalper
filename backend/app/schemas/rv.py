"""Stable API contracts for realized-volatility research data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RVModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RVPoint(RVModel):
    date: date
    price: float
    rv_5d: float
    forecast_5d: float
    actual_forward_5d: float


class RVFeaturePoint(RVModel):
    date: date
    price: float
    rv_1d: float
    rv_5d: float
    rv_21d: float
    rv_63d: float
    rv_ratio_5_21: float
    rv_zscore_21: float
    regime: str


class RVLatestResponse(RVModel):
    symbol: str
    as_of: date
    price: float
    rv_1d: float
    rv_5d: float
    rv_21d: float
    rv_63d: float
    rv_ratio_5_21: float
    rv_zscore_21: float
    regime: str
    source: Literal["csv", "synthetic"]


class RVFeatureResponse(RVModel):
    symbol: str
    points: list[RVFeaturePoint]


class RVBacktestMetrics(RVModel):
    mae: float
    rmse: float
    correlation: float
    directional_accuracy: float


class RVRegimeMetric(RVModel):
    regime: str
    mae: float
    rmse: float
    count: int


class RVBacktestSummary(RVModel):
    symbol: str
    horizon_days: int
    model: str
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    metrics: RVBacktestMetrics
    regime_metrics: list[RVRegimeMetric]


class RVRunSummary(RVModel):
    run_id: str
    created_at: datetime
    symbol: str
    model: str
    horizon_days: int
    status: Literal["complete", "failed", "running"]


class RVRunsResponse(RVModel):
    runs: list[RVRunSummary]


class RVHistoryResponse(RVModel):
    symbol: str
    points: list[RVPoint]


class RVHealthResponse(RVModel):
    status: Literal["ok"]
    service: str
    source: Literal["csv", "synthetic"]
    observations: int
