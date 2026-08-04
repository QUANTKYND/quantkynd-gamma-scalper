from fastapi import APIRouter, Request

from app.schemas.market_data import LiveQuoteResponse, MarketDataStatusResponse


router = APIRouter(prefix="/market-data", tags=["market data"])


@router.get("/status", response_model=MarketDataStatusResponse)
def market_data_status(request: Request) -> MarketDataStatusResponse:
    coordinator = request.app.state.live_runtime.coordinator
    status = coordinator.status()
    freshness_values = [coordinator.quote_store.freshness(key) for key in status.active_instrument_keys]
    if not freshness_values:
        feed_quality = "unknown"
    elif "stale" in freshness_values:
        feed_quality = "stale"
    elif "fresh" in freshness_values:
        feed_quality = "fresh"
    else:
        feed_quality = "awaiting_first_tick"
    return MarketDataStatusResponse(
        authentication_state=status.authentication_state,
        transport_state=status.transport_state,
        subscription_state=status.subscription_state,
        feed_quality=feed_quality,
        market_status=status.market_status,
        active_instrument_keys=list(status.active_instrument_keys),
        connected_at=status.connected_at,
        last_message_at=status.last_message_at,
        last_error_code=status.last_error_code,
        last_error_at=status.last_error_at,
        reconnect_attempt=status.reconnect_attempt,
        counters=coordinator.metrics.snapshot(),
        browser_clients=sum(coordinator.subscriber_counts().values()),
        active_instruments=len(status.active_instrument_keys),
    )


@router.get("/quotes/{instrument_key:path}", response_model=LiveQuoteResponse)
async def latest_quote(request: Request, instrument_key: str) -> LiveQuoteResponse:
    runtime = request.app.state.live_runtime
    await runtime.instruments.resolve(instrument_key)
    return quote_response(runtime.coordinator, instrument_key)


def quote_response(coordinator, instrument_key: str) -> LiveQuoteResponse:
    quote = coordinator.quote_store.get(instrument_key)
    freshness = coordinator.quote_store.freshness(instrument_key)
    if quote is None:
        return LiveQuoteResponse(
            instrument_key=instrument_key,
            status="awaiting_first_tick",
            freshness=freshness,
            ltp=None,
            previous_close=None,
            absolute_change=None,
            percentage_change=None,
            last_trade_quantity=None,
            last_trade_at=None,
            provider_message_at=None,
            received_at=None,
            processed_at=None,
            market_status=coordinator.status().market_status,
            sequence=None,
        )
    change = quote.ltp - quote.previous_close if quote.previous_close else None
    percentage = change / quote.previous_close if change is not None and quote.previous_close else None
    return LiveQuoteResponse(
        instrument_key=instrument_key,
        status="available",
        freshness=freshness,
        ltp=quote.ltp,
        previous_close=quote.previous_close,
        absolute_change=change,
        percentage_change=percentage,
        last_trade_quantity=quote.last_trade_quantity,
        last_trade_at=quote.last_trade_at,
        provider_message_at=quote.provider_message_at,
        received_at=quote.received_at,
        processed_at=quote.processed_at,
        market_status=quote.market_status,
        sequence=quote.sequence,
    )
