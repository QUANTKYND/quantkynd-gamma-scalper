from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.market_data.errors import MarketDataError, SubscriptionRejected
from app.schemas.market_data import MarketStreamEnvelope


router = APIRouter(prefix="/streams", tags=["market streams"])


@router.websocket("/market-state")
async def market_state_stream(websocket: WebSocket, instrument_key: str) -> None:
    runtime = websocket.app.state.live_runtime
    queue = None
    accepted = False
    try:
        if not runtime.coordinator.authentication_available():
            await _deny(websocket, 401, "authentication_required")
            return
        try:
            await runtime.instruments.resolve(instrument_key)
        except MarketDataError as exc:
            status = exc.status_code if exc.status_code in {401, 404} else 503
            await _deny(websocket, status, exc.code)
            return
        await websocket.accept()
        accepted = True
        try:
            queue = await runtime.coordinator.subscribe(instrument_key)
        except SubscriptionRejected:
            await _close(websocket, 4408, "subscription rejected")
            return
        service = await runtime.registry.get(instrument_key)
        await _stream(websocket, runtime, service, queue)
    except WebSocketDisconnect:
        pass
    except Exception:
        if accepted:
            await _close(websocket, 1011, "provider failure")
    finally:
        if queue is not None:
            await runtime.coordinator.unsubscribe(instrument_key, queue)


async def _stream(websocket: WebSocket, runtime, service, queue) -> None:
    instrument_key = service.instrument.instrument_key
    sequence = 1
    await _send(websocket, sequence, "market_state_snapshot", instrument_key, _snapshot_payload(runtime, service))
    loop = asyncio.get_running_loop()
    last_rv_update = loop.time()
    last_freshness = runtime.coordinator.quote_store.freshness(instrument_key)
    last_status = _status_signature(runtime, instrument_key)
    exchange_date = runtime.registry.exchange_date()
    pending_quote = False
    quote_due: float | None = None
    receive_task = asyncio.create_task(websocket.receive())
    try:
        while True:
            timeout = max(0.0, quote_due - loop.time()) if quote_due is not None else 1.0
            queue_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({queue_task, receive_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if receive_task in done:
                if queue_task not in done:
                    queue_task.cancel()
                    await asyncio.gather(queue_task, return_exceptions=True)
                message = receive_task.result()
                if message.get("type") == "websocket.disconnect":
                    return
                receive_task = asyncio.create_task(websocket.receive())
            if queue_task in done:
                event = queue_task.result()
                event_type = event.get("event_type", "quote_updated")
                if event_type == "quote_updated":
                    pending_quote = True
                    quote_due = quote_due or loop.time() + settings.market_data_ui_publish_interval_ms / 1000
                elif event_type == "provider_error":
                    sequence += 1
                    await _send(websocket, sequence, event_type, instrument_key, _snapshot_payload(runtime, service, include_rv=False))
                    await _close(websocket, 1011, "provider failure")
                    return
                elif _status_signature(runtime, instrument_key) != last_status:
                    sequence += 1
                    last_status = _status_signature(runtime, instrument_key)
                    await _send(websocket, sequence, event_type, instrument_key, _snapshot_payload(runtime, service, include_rv=False))
            else:
                queue_task.cancel()
                await asyncio.gather(queue_task, return_exceptions=True)
            freshness = runtime.coordinator.quote_store.freshness(instrument_key)
            if freshness != last_freshness:
                last_freshness = freshness
                sequence += 1
                await _send(websocket, sequence, "feed_status_changed", instrument_key, _snapshot_payload(runtime, service))
                last_rv_update = loop.time()
            current_exchange_date = runtime.registry.exchange_date()
            if current_exchange_date != exchange_date:
                exchange_date = current_exchange_date
                service = await runtime.registry.refresh(instrument_key)
                sequence += 1
                await _send(websocket, sequence, "resync_required", instrument_key, _snapshot_payload(runtime, service))
                last_rv_update = loop.time()
            if pending_quote and quote_due is not None and loop.time() >= quote_due:
                include_rv = loop.time() - last_rv_update >= settings.rv_live_recompute_interval_ms / 1000
                sequence += 1
                await _send(websocket, sequence, "quote_updated", instrument_key, _snapshot_payload(runtime, service, include_rv=include_rv))
                if include_rv:
                    last_rv_update = loop.time()
                pending_quote = False
                quote_due = None
    finally:
        receive_task.cancel()
        await asyncio.gather(receive_task, return_exceptions=True)


def _status_signature(runtime, instrument_key: str) -> tuple[str, str, str | None]:
    status = runtime.coordinator.status(instrument_key)
    return status.transport_state, status.subscription_state, status.market_status


def _snapshot_payload(runtime, service, *, include_rv: bool = True) -> dict:
    instrument_key = service.instrument.instrument_key
    quote = runtime.coordinator.quote_store.get(instrument_key)
    freshness = runtime.coordinator.quote_store.freshness(instrument_key)
    payload = {
        "status": runtime.coordinator.status(instrument_key).__dict__,
        "quote": _json_quote(quote, freshness, runtime.coordinator.market_status(instrument_key)),
    }
    if include_rv:
        runtime.metrics.increment("rv_live_recomputations_total")
        latest = runtime.overlay.latest(service.snapshot, service.instrument, quote, freshness)
        features = runtime.overlay.feature_series(service.snapshot, service.instrument, quote, freshness, 260)
        payload["rv_latest"] = latest.model_dump(mode="json")
        payload["rv_features"] = features.model_dump(mode="json")
    return payload


def _json_quote(quote, freshness: str, market_status: str) -> dict:
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
        "market_status": market_status,
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


async def _deny(websocket: WebSocket, status_code: int, code: str) -> None:
    response = JSONResponse(
        status_code=status_code,
        content={"status": status_code, "code": code, "detail": "Market stream unavailable"},
    )
    await websocket.send_denial_response(response)


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        pass
