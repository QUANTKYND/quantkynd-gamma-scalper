"""Realized-volatility research API."""

from fastapi import APIRouter, Query

from app.schemas.rv import (
    RVBacktestSummary,
    RVFeatureResponse,
    RVHealthResponse,
    RVHistoryResponse,
    RVLatestResponse,
    RVRunsResponse,
)
from app.services.rv_service import rv_service


router = APIRouter(prefix="/rv", tags=["realized volatility"])


@router.get("/latest", response_model=RVLatestResponse)
def latest_rv() -> RVLatestResponse:
    return rv_service.latest()


@router.get("/features", response_model=RVFeatureResponse)
def rv_features(limit: int = Query(default=260, ge=20, le=1000)) -> RVFeatureResponse:
    return rv_service.feature_series(limit=limit)


@router.get("/backtest/latest", response_model=RVBacktestSummary)
def latest_backtest() -> RVBacktestSummary:
    return rv_service.backtest_summary()


@router.get("/backtest/runs", response_model=RVRunsResponse)
def backtest_runs() -> RVRunsResponse:
    return rv_service.runs()


@router.get("/history", response_model=RVHistoryResponse)
def rv_history(limit: int = Query(default=260, ge=20, le=1000)) -> RVHistoryResponse:
    return rv_service.history(limit=limit)


@router.get("/health", response_model=RVHealthResponse)
def rv_health() -> RVHealthResponse:
    return rv_service.health()
