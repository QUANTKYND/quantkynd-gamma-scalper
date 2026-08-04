from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.auth.token_store import TokenStore, token_store
from app.market_data.errors import SubscriptionRejected
from app.market_data.metrics import MarketDataMetrics
from app.market_data.models import LiveQuoteState, MarketDataStatus
from app.market_data.provider import LiveMarketProvider
from app.market_data.quote_store import LiveQuoteStore
from app.market_data.upstox.normalization import market_status_for_segment, normalize_feed_quotes, normalize_segment_statuses


@dataclass
class SubscriptionEntry:
    instrument_key: str
    phase: Literal["subscribing", "subscribed", "rejected"]
    listeners: set[asyncio.Queue[dict[str, Any]]]
    readiness: asyncio.Future[None]


class MarketDataCoordinator:
    def __init__(self, provider: LiveMarketProvider, quote_store: LiveQuoteStore, *, max_active: int, tokens: TokenStore = token_store, metrics: MarketDataMetrics | None = None) -> None:
        self._provider = provider
        self.quote_store = quote_store
        self._max_active = max_active
        self._tokens = tokens
        self.metrics = metrics or MarketDataMetrics()
        self._subscriptions: dict[str, SubscriptionEntry] = {}
        self._quote_sequences: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._transport_state = "idle"
        self._segment_statuses: dict[str, str] = {}
        self._connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._last_error_code: str | None = None
        self._last_error_at: datetime | None = None
        self._reconnect_attempt = 0
        bind = getattr(provider, "bind", None)
        if callable(bind):
            bind(self.receive_provider_message, self.receive_provider_state)

    async def subscribe(self, instrument_key: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        async with self._lock:
            entry = self._subscriptions.get(instrument_key)
            if entry is None or entry.phase == "rejected":
                active_count = sum(item.phase != "rejected" for item in self._subscriptions.values())
                if active_count >= self._max_active:
                    raise SubscriptionRejected("Active instrument capacity reached")
                readiness = asyncio.get_running_loop().create_future()
                entry = SubscriptionEntry(instrument_key, "subscribing", set(), readiness)
                self._subscriptions[instrument_key] = entry
                first = True
            else:
                first = False
            entry.listeners.add(queue)
            readiness = entry.readiness
            self.metrics.increment("market_feed_subscription_changes_total")
        if first:
            self._transport_state = "connecting" if self._transport_state in {"idle", "disconnected", "auth_missing"} else self._transport_state
            try:
                await self._provider.subscribe((instrument_key,))
            except BaseException as exc:
                failure = SubscriptionRejected()
                async with self._lock:
                    current = self._subscriptions.get(instrument_key)
                    if current is entry:
                        entry.phase = "rejected"
                        entry.listeners.clear()
                        self._subscriptions.pop(instrument_key, None)
                        if not readiness.done():
                            readiness.set_exception(failure)
                if isinstance(exc, asyncio.CancelledError):
                    readiness.exception()
                    raise
            else:
                async with self._lock:
                    current = self._subscriptions.get(instrument_key)
                    if current is entry:
                        entry.phase = "subscribed"
                        if not readiness.done():
                            readiness.set_result(None)
        try:
            await asyncio.shield(readiness)
        except asyncio.CancelledError:
            await self.unsubscribe(instrument_key, queue)
            raise
        return queue

    async def unsubscribe(self, instrument_key: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        should_unsubscribe = False
        async with self._lock:
            entry = self._subscriptions.get(instrument_key)
            if entry is None or queue not in entry.listeners:
                return
            entry.listeners.remove(queue)
            self.metrics.increment("market_feed_subscription_changes_total")
            if not entry.listeners:
                self._subscriptions.pop(instrument_key, None)
                should_unsubscribe = entry.phase == "subscribed"
        if should_unsubscribe:
            await self._provider.unsubscribe((instrument_key,))

    def receive_provider_message(self, payload: Any) -> None:
        received_at = datetime.now(UTC)
        self.metrics.increment("market_feed_messages_total")
        requested_keys = set(self._subscriptions)
        candidates = normalize_feed_quotes(payload, requested_keys=requested_keys, received_at=received_at)
        self._last_message_at = received_at
        if isinstance(payload, dict) and payload.get("feeds") and not candidates:
            self.metrics.increment("market_feed_invalid_messages_total")
        segment_statuses = normalize_segment_statuses(payload)
        changed_segments = {key for key, value in segment_statuses.items() if self._segment_statuses.get(key) != value}
        self._segment_statuses.update(segment_statuses)
        for instrument_key in tuple(self._subscriptions):
            if _segment_for(instrument_key) in changed_segments:
                self._publish(instrument_key, {"event_type": "market_status_changed"})
        for candidate in candidates:
            next_sequence = self._quote_sequences.get(candidate.instrument_key, 0) + 1
            quote = LiveQuoteState(
                instrument_key=candidate.instrument_key,
                ltp=candidate.ltp,
                previous_close=candidate.previous_close,
                last_trade_quantity=candidate.last_trade_quantity,
                last_trade_at=candidate.last_trade_at,
                provider_message_at=candidate.provider_message_at,
                received_at=candidate.received_at,
                processed_at=candidate.processed_at,
                market_status=self.market_status(candidate.instrument_key),
                sequence=next_sequence,
            )
            if self.quote_store.put(quote):
                self._quote_sequences[candidate.instrument_key] = next_sequence
                self._publish(candidate.instrument_key, {"event_type": "quote_updated"})

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
            self.quote_store.mark_stale(tuple(self._subscriptions))
        elif state in {"disconnected", "failed"}:
            self.quote_store.mark_stale(tuple(self._subscriptions))
        if error_code:
            self._last_error_code = error_code
            self._last_error_at = now
        event_type = "provider_error" if state == "failed" else "feed_status_changed"
        for instrument_key in tuple(self._subscriptions):
            self._publish(instrument_key, {"event_type": event_type})

    def _publish(self, instrument_key: str, event: dict[str, Any]) -> None:
        entry = self._subscriptions.get(instrument_key)
        if entry is None:
            return
        for queue in tuple(entry.listeners):
            if queue.full():
                self.metrics.increment("market_feed_dropped_or_coalesced_updates_total")
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    def market_status(self, instrument_key: str) -> str:
        return market_status_for_segment(self._segment_statuses, _segment_for(instrument_key))

    def authentication_available(self) -> bool:
        return self._tokens.is_connected()

    def status(self, instrument_key: str | None = None) -> MarketDataStatus:
        authenticated = self._tokens.is_connected()
        transport = self._transport_state if authenticated else "auth_missing"
        if instrument_key is not None:
            entry = self._subscriptions.get(instrument_key)
            subscription_state = entry.phase if entry is not None else "unsubscribed"
        else:
            subscription_state = self._aggregate_subscription_state()
        return MarketDataStatus(
            authentication_state="authenticated" if authenticated else "missing",
            transport_state=transport,
            subscription_state=subscription_state,
            market_status=self.market_status(instrument_key) if instrument_key else None,
            segment_statuses=dict(self._segment_statuses),
            active_instrument_keys=tuple(sorted(self._subscriptions)),
            connected_at=self._connected_at,
            last_message_at=self._last_message_at,
            last_error_code=self._last_error_code,
            last_error_at=self._last_error_at,
            reconnect_attempt=self._reconnect_attempt,
        )

    def _aggregate_subscription_state(self) -> str:
        phases = {entry.phase for entry in self._subscriptions.values()}
        if "subscribing" in phases:
            return "subscribing"
        elif "subscribed" in phases:
            return "subscribed"
        elif "rejected" in phases:
            return "rejected"
        return "unsubscribed"

    def subscriber_counts(self) -> dict[str, int]:
        return {key: len(entry.listeners) for key, entry in self._subscriptions.items()}

    async def stop(self) -> None:
        self._transport_state = "stopping"
        await self._provider.stop()
        self._transport_state = "disconnected"


def _segment_for(instrument_key: str) -> str:
    return instrument_key.split("|", 1)[0]
