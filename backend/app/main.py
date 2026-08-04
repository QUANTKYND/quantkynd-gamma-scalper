from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.routes import router
from app.core.config import settings
from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.errors import MarketDataError
from app.market_data.metrics import MarketDataMetrics
from app.market_data.quote_store import LiveQuoteStore
from app.market_data.upstox.client import UpstoxReadOnlyClient
from app.market_data.upstox.history import UpstoxHistoricalCloseProvider
from app.market_data.upstox.instruments import UpstoxInstrumentProvider
from app.market_data.upstox.streamer import UpstoxLiveMarketProvider
from app.services.live_runtime import LiveRuntime
from app.services.rv_live_overlay import RVLiveOverlayBuilder
from app.services.rv_registry import InstrumentRVServiceRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    metrics = MarketDataMetrics()
    client = UpstoxReadOnlyClient(metrics=metrics)
    instruments = UpstoxInstrumentProvider(client)
    history = UpstoxHistoricalCloseProvider(client)
    quote_store = LiveQuoteStore(settings.market_data_stale_after_seconds)
    live_provider = UpstoxLiveMarketProvider()
    coordinator = MarketDataCoordinator(
        live_provider,
        quote_store,
        max_active=settings.upstox_max_active_instruments,
        metrics=metrics,
    )
    registry = InstrumentRVServiceRegistry(
        instruments,
        history,
        lookback_years=settings.upstox_history_lookback_years,
        cache_seconds=settings.rv_finalized_snapshot_cache_seconds,
    )
    app.state.live_runtime = LiveRuntime(
        client=client,
        instruments=instruments,
        registry=registry,
        coordinator=coordinator,
        overlay=RVLiveOverlayBuilder(),
        metrics=metrics,
    )
    yield
    await coordinator.stop()
    await client.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MarketDataError)
async def market_data_error_handler(request: Request, exc: MarketDataError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://quantkynd.dev/problems/{exc.code.replace('_', '-')}",
            "title": str(exc),
            "status": exc.status_code,
            "code": exc.code,
            "detail": str(exc),
            "correlation_id": request.headers.get("x-correlation-id"),
            "field_errors": [],
        },
        media_type="application/problem+json",
    )


app.include_router(router, prefix=settings.api_v1_prefix)
app.include_router(auth_router)


@app.get("/")
def root():
    return {"message": "Trading Platform API"}
