from dataclasses import asdict

from fastapi import APIRouter, Query, Request

from app.core.config import settings
from app.schemas.instruments import InstrumentDefinition
from app.schemas.rv import (
    RVBacktestSummary,
    RVFeatureResponse,
    RVHealthResponse,
    RVHistoryResponse,
    RVLatestResponse,
    RVRunsResponse,
)
from app.services.rv_service import RVService, rv_service


router = APIRouter(prefix="/rv", tags=["realized volatility"])


def _key(instrument_key: str | None) -> str:
    return instrument_key or settings.upstox_default_instrument_key


@router.get("/latest", response_model=RVLatestResponse)
async def latest_rv(request: Request, instrument_key: str | None = Query(default=None)) -> RVLatestResponse:
    runtime = request.app.state.live_runtime
    service = await runtime.registry.get(_key(instrument_key))
    quote = runtime.coordinator.quote_store.get(service.instrument.instrument_key)
    freshness = runtime.coordinator.quote_store.freshness(service.instrument.instrument_key)
    return runtime.overlay.latest(service.snapshot, service.instrument, quote, freshness)


@router.get("/features", response_model=RVFeatureResponse)
async def rv_features(
    request: Request,
    instrument_key: str | None = Query(default=None),
    limit: int = Query(default=260, ge=20, le=1000),
) -> RVFeatureResponse:
    runtime = request.app.state.live_runtime
    service = await runtime.registry.get(_key(instrument_key))
    quote = runtime.coordinator.quote_store.get(service.instrument.instrument_key)
    freshness = runtime.coordinator.quote_store.freshness(service.instrument.instrument_key)
    return runtime.overlay.feature_series(service.snapshot, service.instrument, quote, freshness, limit)


@router.get("/backtest/latest", response_model=RVBacktestSummary)
async def latest_backtest(request: Request, instrument_key: str | None = Query(default=None)) -> RVBacktestSummary:
    service = await request.app.state.live_runtime.registry.get(_key(instrument_key))
    response = RVService(symbol=service.snapshot.symbol, snapshot=service.snapshot).backtest_summary()
    return response.model_copy(update={"instrument": InstrumentDefinition.model_validate(asdict(service.instrument))})


@router.get("/backtest/runs", response_model=RVRunsResponse)
def backtest_runs() -> RVRunsResponse:
    return rv_service.runs()


@router.get("/history", response_model=RVHistoryResponse)
async def rv_history(
    request: Request,
    instrument_key: str | None = Query(default=None),
    limit: int = Query(default=260, ge=20, le=1000),
) -> RVHistoryResponse:
    service = await request.app.state.live_runtime.registry.get(_key(instrument_key))
    response = RVService(symbol=service.snapshot.symbol, snapshot=service.snapshot).history(limit=limit)
    return response.model_copy(update={"instrument": InstrumentDefinition.model_validate(asdict(service.instrument))})


@router.get("/health", response_model=RVHealthResponse)
async def rv_health(request: Request, instrument_key: str | None = Query(default=None)) -> RVHealthResponse:
    runtime = request.app.state.live_runtime
    service = await runtime.registry.get(_key(instrument_key))
    quote = runtime.coordinator.quote_store.get(service.instrument.instrument_key)
    freshness = runtime.coordinator.quote_store.freshness(service.instrument.instrument_key)
    response = RVService(symbol=service.snapshot.symbol, snapshot=service.snapshot).health()
    live = runtime.overlay.latest(service.snapshot, service.instrument, quote, freshness).live
    return response.model_copy(
        update={
            "instrument": InstrumentDefinition.model_validate(asdict(service.instrument)),
            "finalized_as_of": service.snapshot.dataset_metadata.end_date,
            "live": live,
        }
    )
