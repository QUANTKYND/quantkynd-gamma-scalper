"""Stable API contracts for close-to-close volatility research data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


RVRegime = Literal["low", "normal", "high", "unknown"]
RVModelName = Literal["naive", "ewma"]
RVEvaluationMethod = Literal["sequential_non_overlapping_metrics"]


class RVModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RVEstimatorMetadata(RVModel):
    estimator_id: Literal["close_to_close_squared_log_returns_v1"]
    input_frequency: Literal["1d_close"]
    return_type: Literal["log"]
    annualization_periods: int
    observation_timing: Literal["end_of_day"]
    is_intraday_realized_variance: Literal[False]


class RVSyntheticDatasetParameters(RVModel):
    seed: int
    periods: int
    end_date: date
    initial_price: float


class RVDatasetMetadata(RVModel):
    dataset_id: str
    source: Literal["csv", "synthetic"]
    symbol: str
    observations: int
    start_date: date
    end_date: date
    computed_at: datetime
    synthetic_parameters: RVSyntheticDatasetParameters | None = None


class RVHorizonEstimate(RVModel):
    horizon_sessions: int
    horizon_variance: float
    annualized_variance: float
    annualized_volatility: float


class RVLatestResponse(RVModel):
    symbol: str
    as_of: date
    price: float
    estimates: list[RVHorizonEstimate]
    variance_ratio_5_21: float | None
    volatility_zscore_21: float | None
    regime: RVRegime
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata


class RVFeaturePoint(RVModel):
    date: date
    price: float
    estimates: list[RVHorizonEstimate]
    variance_ratio_5_21: float | None
    volatility_zscore_21: float | None
    regime: RVRegime


class RVFeatureResponse(RVModel):
    symbol: str
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata
    points: list[RVFeaturePoint]


class RVForecastHistoryPoint(RVModel):
    origin_date: date
    target_start: date
    target_end: date
    price: float
    forecast_annualized_variance: float
    forecast_annualized_volatility: float
    actual_annualized_variance: float
    actual_annualized_volatility: float


class RVHistoryResponse(RVModel):
    symbol: str
    model: RVModelName
    horizon_sessions: int
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata
    points: list[RVForecastHistoryPoint]


class RVBacktestMetrics(RVModel):
    mae: float | None
    rmse: float | None
    correlation: float | None
    change_direction_accuracy: float | None
    n_obs: int


class RVRegimeMetric(RVModel):
    regime: RVRegime
    variance_metrics: RVBacktestMetrics
    volatility_metrics: RVBacktestMetrics


class RVBacktestSummary(RVModel):
    symbol: str
    model: RVModelName
    model_parameters: dict[str, int | float | str]
    horizon_sessions: int
    evaluation_method: RVEvaluationMethod
    chart_stride: int
    metric_stride: int
    overlapping_chart_targets: bool
    overlapping_metric_targets: bool
    evaluation_start: date
    evaluation_end: date
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata
    variance_metrics: RVBacktestMetrics
    volatility_metrics: RVBacktestMetrics
    regime_metrics: list[RVRegimeMetric]


class RVRunManifest(RVModel):
    run_id: str
    created_at: datetime
    completed_at: datetime | None
    status: Literal["running", "complete", "failed"]
    symbol: str
    dataset_id: str
    estimator_id: str
    model: RVModelName
    model_parameters: dict[str, int | float | str]
    horizon_sessions: int
    evaluation_method: str
    config_hash: str
    git_commit: str | None
    artifact_directory: str
    failure_reason: str | None


class RVRunSummary(RVModel):
    run_id: str
    created_at: datetime
    completed_at: datetime | None
    status: Literal["running", "complete", "failed"]
    symbol: str
    dataset_id: str
    estimator_id: str
    model: RVModelName
    model_parameters: dict[str, int | float | str]
    horizon_sessions: int
    evaluation_method: str
    failure_reason: str | None


class RVRunsResponse(RVModel):
    runs: list[RVRunSummary]


class RVHealthResponse(RVModel):
    status: Literal["ok"]
    service: str
    source: Literal["csv", "synthetic"]
    observations: int
    estimator: RVEstimatorMetadata
    dataset: RVDatasetMetadata
