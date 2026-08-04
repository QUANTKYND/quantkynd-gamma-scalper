from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.market_data.errors import AuthenticationRequired, InstrumentNotFound, SubscriptionRejected
from app.schemas.market_data import MarketStreamEnvelope


router = APIRouter(prefix="/streams", tags=["market streams"])


@router.websocket("/market-state")
async def market_state_stream(websocket: WebSocket, instrument_key: str) -> None:
    runtime = websocket.app.state.live_runtime
    queue = None
    sequence = 0
    last_rv_update = 0.0
    last_freshness = "unknown"
    try:
        service = await runtime.registry.get(instrument_key)
        queue = await runtime.coordinator.subscribe(instrument_key)
        await websocket.accept()
        sequence += 1
        await _send(websocket, sequence, "market_state_snapshot", instrument_key, _snapshot_payload(runtime, service))
        last_rv_update = asyncio.get_running_loop().time()
        last_freshness = runtime.coordinator.quote_store.freshness(instrument_key)
        while True:
            freshness_changed = False
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
            except TimeoutError:
                freshness = runtime.coordinator.quote_store.freshness(instrument_key)
                freshness_changed = freshness != last_freshness
                last_freshness = freshness
                event = {"event_type": "feed_status_changed"}
            event_type = event.get("event_type", "quote_updated")
            if event_type == "quote_updated":
                await asyncio.sleep(settings.market_data_ui_publish_interval_ms / 1000)
            while not queue.empty():
                event = queue.get_nowait()
            current_freshness = runtime.coordinator.quote_store.freshness(instrument_key)
            freshness_changed = freshness_changed or current_freshness != last_freshness
            last_freshness = current_freshness
            sequence += 1
            event_type = event.get("event_type", "quote_updated")
            now = asyncio.get_running_loop().time()
            include_rv = freshness_changed or (
                event_type == "quote_updated"
                and now - last_rv_update >= settings.rv_live_recompute_interval_ms / 1000
            )
            payload = _snapshot_payload(runtime, service, include_rv=include_rv)
            if include_rv:
                last_rv_update = now
            await _send(websocket, sequence, event_type, instrument_key, payload)
    except AuthenticationRequired:
        await _close(websocket, 4401, "authentication required")
    except InstrumentNotFound:
        await _close(websocket, 4404, "instrument not found")
    except SubscriptionRejected:
        await _close(websocket, 4408, "subscription rejected")
    except WebSocketDisconnect:
        pass
    except Exception:
        await _close(websocket, 1011, "provider failure")
    finally:
        if queue is not None:
            await runtime.coordinator.unsubscribe(instrument_key, queue)


def _snapshot_payload(runtime, service, *, include_rv: bool = True) -> dict:
    quote = runtime.coordinator.quote_store.get(service.instrument.instrument_key)
    freshness = runtime.coordinator.quote_store.freshness(service.instrument.instrument_key)
    payload = {
        "status": runtime.coordinator.status().__dict__,
        "quote": _json_quote(quote, freshness),
    }
    if include_rv:
        runtime.metrics.increment("rv_live_recomputations_total")
        latest = runtime.overlay.latest(service.snapshot, service.instrument, quote, freshness)
        features = runtime.overlay.feature_series(service.snapshot, service.instrument, quote, freshness, 260)
        payload["rv_latest"] = latest.model_dump(mode="json")
        payload["rv_features"] = features.model_dump(mode="json")
    return payload


def _json_quote(quote, freshness: str) -> dict | None:
    if quote is None:
        return {"freshness": freshness, "status": "awaiting_first_tick"}
    return {
        "instrument_key": quote.instrument_key,
        "ltp": quote.ltp,
        "previous_close": quote.previous_close,
        "last_trade_quantity": quote.last_trade_quantity,
        "last_trade_at": quote.last_trade_at.isoformat(),
        "provider_message_at": quote.provider_message_at.isoformat(),
        "received_at": quote.received_at.isoformat(),
        "processed_at": quote.processed_at.isoformat(),
        "market_status": quote.market_status,
        "sequence": quote.sequence,
        "freshness": freshness,
        "status": "available",
    }


async def _send(websocket: WebSocket, sequence: int, event_type: str, instrument_key: str, payload: dict) -> None:
    envelope = MarketStreamEnvelope(
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        event_type=event_type,
        entity_id=instrument_key,
        payload=payload,
    )
    await websocket.send_json(envelope.model_dump(mode="json"))


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        pass
