from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.auth.token_store import TokenStore, token_store
from app.market_data.errors import SubscriptionRejected
from app.market_data.models import MarketDataStatus
from app.market_data.metrics import MarketDataMetrics
from app.market_data.provider import LiveMarketProvider
from app.market_data.quote_store import LiveQuoteStore
from app.market_data.upstox.normalization import normalize_feed_quotes, normalize_market_status


class MarketDataCoordinator:
    def __init__(self, provider: LiveMarketProvider, quote_store: LiveQuoteStore, *, max_active: int, tokens: TokenStore = token_store, metrics: MarketDataMetrics | None = None) -> None:
        self._provider = provider
        self.quote_store = quote_store
        self._max_active = max_active
        self._tokens = tokens
        self.metrics = metrics or MarketDataMetrics()
        self._counts: dict[str, int] = {}
        self._listeners: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()
        self._transport_state = "idle"
        self._subscription_state = "unsubscribed"
        self._market_status: str | None = None
        self._connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._last_error_code: str | None = None
        self._last_error_at: datetime | None = None
        self._reconnect_attempt = 0
        self._provider_sequence = 0
        bind = getattr(provider, "bind", None)
        if callable(bind):
            bind(self.receive_provider_message, self.receive_provider_state)

    async def subscribe(self, instrument_key: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        async with self._lock:
            count = self._counts.get(instrument_key, 0)
            if count == 0 and len(self._counts) >= self._max_active:
                raise SubscriptionRejected("Active instrument capacity reached")
            self._counts[instrument_key] = count + 1
            self._listeners.setdefault(instrument_key, set()).add(queue)
            first = count == 0
            self._subscription_state = "subscribing" if first else "subscribed"
            self.metrics.increment("market_feed_subscription_changes_total")
        if first:
            try:
                self._transport_state = "connecting" if self._transport_state in {"idle", "disconnected", "auth_missing"} else self._transport_state
                await self._provider.subscribe((instrument_key,))
                self._subscription_state = "subscribed"
            except Exception:
                await self._rollback_subscription(instrument_key, queue)
                raise
        return queue

    async def unsubscribe(self, instrument_key: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            listeners = self._listeners.get(instrument_key)
            if listeners is not None:
                listeners.discard(queue)
                if not listeners:
                    self._listeners.pop(instrument_key, None)
            count = self._counts.get(instrument_key, 0)
            if count <= 1:
                self._counts.pop(instrument_key, None)
                last = count == 1
            else:
                self._counts[instrument_key] = count - 1
                last = False
            self._subscription_state = "subscribed" if self._counts else "unsubscribed"
            self.metrics.increment("market_feed_subscription_changes_total")
        if last:
            await self._provider.unsubscribe((instrument_key,))

    async def _rollback_subscription(self, instrument_key: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._listeners.get(instrument_key, set()).discard(queue)
            self._listeners.pop(instrument_key, None)
            self._counts.pop(instrument_key, None)
            self._subscription_state = "rejected"

    def receive_provider_message(self, payload: Any) -> None:
        received_at = datetime.now(UTC)
        self.metrics.increment("market_feed_messages_total")
        self._provider_sequence += 1
        quotes = normalize_feed_quotes(
            payload,
            requested_keys=set(self._counts),
            received_at=received_at,
            first_sequence=self._provider_sequence,
        )
        self._last_message_at = received_at
        if isinstance(payload, dict) and payload.get("feeds") and not quotes:
            self.metrics.increment("market_feed_invalid_messages_total")
        market_status = normalize_market_status(payload)
        if market_status is not None and market_status != self._market_status:
            self._market_status = market_status
            for instrument_key in tuple(self._listeners):
                self._publish(instrument_key, {"event_type": "market_status_changed"})
        for quote in quotes:
            self._market_status = quote.market_status or self._market_status
            self.quote_store.put(quote)
            self._publish(quote.instrument_key, {"event_type": "quote_updated"})

    def receive_provider_state(self, state: str, error_code: str | None) -> None:
        self._transport_state = state
        now = datetime.now(UTC)
        if state == "connected":
            self._connected_at = now
            self._reconnect_attempt = 0
            self.metrics.increment("market_feed_connections_total")
        elif state == "reconnecting":
            self._reconnect_attempt += 1
            self.metrics.increment("market_feed_reconnects_total")
            self.quote_store.mark_stale(tuple(self._counts))
        elif state in {"disconnected", "failed"}:
            self.quote_store.mark_stale(tuple(self._counts))
        if error_code:
            self._last_error_code = error_code
            self._last_error_at = now
        for instrument_key in tuple(self._listeners):
            self._publish(instrument_key, {"event_type": "feed_status_changed"})

    def _publish(self, instrument_key: str, event: dict[str, Any]) -> None:
        for queue in tuple(self._listeners.get(instrument_key, ())):
            if queue.full():
                self.metrics.increment("market_feed_dropped_or_coalesced_updates_total")
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    def status(self) -> MarketDataStatus:
        authenticated = self._tokens.is_connected()
        transport = self._transport_state if authenticated else "auth_missing"
        return MarketDataStatus(
            authentication_state="authenticated" if authenticated else "missing",
            transport_state=transport,
            subscription_state=self._subscription_state,
            market_status=self._market_status,
            active_instrument_keys=tuple(sorted(self._counts)),
            connected_at=self._connected_at,
            last_message_at=self._last_message_at,
            last_error_code=self._last_error_code,
            last_error_at=self._last_error_at,
            reconnect_attempt=self._reconnect_attempt,
        )

    def subscriber_counts(self) -> dict[str, int]:
        return dict(self._counts)

    async def stop(self) -> None:
        self._transport_state = "stopping"
        await self._provider.stop()
        self._transport_state = "disconnected"
