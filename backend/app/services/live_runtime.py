from dataclasses import dataclass

from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.metrics import MarketDataMetrics
from app.market_data.upstox.client import UpstoxReadOnlyClient
from app.market_data.upstox.instruments import UpstoxInstrumentProvider
from app.services.rv_live_overlay import RVLiveOverlayBuilder
from app.services.rv_registry import InstrumentRVServiceRegistry


@dataclass(frozen=True)
class LiveRuntime:
    client: UpstoxReadOnlyClient
    instruments: UpstoxInstrumentProvider
    registry: InstrumentRVServiceRegistry
    coordinator: MarketDataCoordinator
    overlay: RVLiveOverlayBuilder
    metrics: MarketDataMetrics
