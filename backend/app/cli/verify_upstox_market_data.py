from __future__ import annotations

import argparse
import asyncio

from app.auth.token_store import token_store
from app.core.config import settings
from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.quote_store import LiveQuoteStore
from app.market_data.upstox.client import UpstoxReadOnlyClient
from app.market_data.upstox.history import UpstoxHistoricalCloseProvider
from app.market_data.upstox.instruments import UpstoxInstrumentProvider
from app.market_data.upstox.streamer import UpstoxLiveMarketProvider
from app.services.rv_registry import InstrumentRVServiceRegistry


async def verify(instrument_key: str, listen_seconds: int) -> int:
    if not token_store.is_connected():
        print("Upstox authentication missing")
        return 1
    client = UpstoxReadOnlyClient()
    instruments = UpstoxInstrumentProvider(client)
    history = UpstoxHistoricalCloseProvider(client)
    registry = InstrumentRVServiceRegistry(
        instruments,
        history,
        lookback_years=settings.upstox_history_lookback_years,
        cache_seconds=settings.rv_finalized_snapshot_cache_seconds,
    )
    provider = UpstoxLiveMarketProvider()
    coordinator = MarketDataCoordinator(
        provider,
        LiveQuoteStore(settings.market_data_stale_after_seconds),
        max_active=settings.upstox_max_active_instruments,
    )
    queue = None
    try:
        service = await registry.get(instrument_key)
        dataset = service.snapshot.dataset_metadata
        print(f"Resolved {service.instrument.trading_symbol} ({service.instrument.instrument_key})")
        print(f"Finalized closes {dataset.observations}: {dataset.start_date} to {dataset.end_date}")
        queue = await coordinator.subscribe(instrument_key)
        print(f"Transport {coordinator.status().transport_state}")
        deadline = asyncio.get_running_loop().time() + listen_seconds
        while asyncio.get_running_loop().time() < deadline:
            timeout = deadline - asyncio.get_running_loop().time()
            try:
                await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                break
            quote = coordinator.quote_store.get(instrument_key)
            if quote is not None:
                print(f"Quote LTP={quote.ltp} last_trade_at={quote.last_trade_at.isoformat()}")
                print(f"Market status {quote.market_status or 'unknown'}")
                return 0
        print(f"No quote received; market status {coordinator.status().market_status or 'unknown'}")
        return 1
    except Exception as exc:
        print(f"Verification failed: {type(exc).__name__}")
        return 1
    finally:
        if queue is not None:
            await coordinator.unsubscribe(instrument_key, queue)
        await coordinator.stop()
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument-key", default=settings.upstox_default_instrument_key)
    parser.add_argument("--listen-seconds", type=int, default=30)
    args = parser.parse_args()
    if args.listen_seconds <= 0:
        parser.error("--listen-seconds must be positive")
    return asyncio.run(verify(args.instrument_key, args.listen_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
