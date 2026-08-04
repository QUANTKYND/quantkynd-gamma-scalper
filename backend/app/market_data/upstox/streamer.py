from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.auth.token_store import TokenStore, token_store
from app.core.config import settings
from app.market_data.errors import AuthenticationRequired, ProviderUnavailable


class UpstoxLiveMarketProvider:
    def __init__(self, tokens: TokenStore = token_store) -> None:
        self._tokens = tokens
        self._streamer: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_message: Callable[[Any], None] | None = None
        self._on_state: Callable[[str, str | None], None] | None = None
        self._connected_event: asyncio.Event | None = None
        self._active_keys: set[str] = set()
        self._has_connected = False
        self._start_lock = asyncio.Lock()

    def bind(self, on_message: Callable[[Any], None], on_state: Callable[[str, str | None], None]) -> None:
        self._on_message = on_message
        self._on_state = on_state

    async def start(self) -> None:
        async with self._start_lock:
            if self._streamer is not None:
                if self._connected_event is not None:
                    await asyncio.wait_for(self._connected_event.wait(), timeout=20)
                return
            access_token = self._access_token()
            self._loop = asyncio.get_running_loop()
            self._connected_event = asyncio.Event()
            import upstox_client

            configuration = upstox_client.Configuration()
            configuration.access_token = access_token
            api_client = upstox_client.ApiClient(configuration)
            streamer = upstox_client.MarketDataStreamerV3(api_client)
            streamer.auto_reconnect(
                True,
                settings.upstox_stream_reconnect_interval_seconds,
                settings.upstox_stream_max_reconnect_attempts,
            )
            streamer.on("open", self._handle_open)
            streamer.on("message", self._bridge_message)
            streamer.on("reconnecting", self._handle_reconnecting)
            streamer.on("autoReconnectStopped", self._handle_reconnect_stopped)
            streamer.on("error", self._handle_error)
            streamer.on("close", lambda *args: self._bridge_state("disconnected", None))
            self._streamer = streamer
            await asyncio.to_thread(streamer.connect)
            try:
                await asyncio.wait_for(self._connected_event.wait(), timeout=20)
            except TimeoutError as exc:
                await asyncio.to_thread(streamer.disconnect)
                self._streamer = None
                raise ProviderUnavailable("Upstox market feed did not connect") from exc

    async def stop(self) -> None:
        streamer, self._streamer = self._streamer, None
        if streamer is not None:
            await asyncio.to_thread(streamer.disconnect)

    async def subscribe(self, instrument_keys: tuple[str, ...]) -> None:
        await self.start()
        await asyncio.to_thread(self._streamer.subscribe, list(instrument_keys), settings.upstox_market_data_mode)
        self._active_keys.update(instrument_keys)

    async def unsubscribe(self, instrument_keys: tuple[str, ...]) -> None:
        if self._streamer is not None:
            await asyncio.to_thread(self._streamer.unsubscribe, list(instrument_keys))
        self._active_keys.difference_update(instrument_keys)

    def _handle_open(self) -> None:
        if self._has_connected and self._active_keys and self._streamer is not None:
            self._streamer.subscribe(list(self._active_keys), settings.upstox_market_data_mode)
        self._has_connected = True
        if self._loop is not None and self._connected_event is not None:
            self._loop.call_soon_threadsafe(self._connected_event.set)
        self._bridge_state("connected", None)

    def _handle_reconnecting(self, *args: Any) -> None:
        self._bridge_state("reconnecting", None)

    def _handle_reconnect_stopped(self, *args: Any) -> None:
        self._bridge_state("failed", "reconnect_exhausted")

    def _handle_error(self, *args: Any) -> None:
        self._bridge_state("reconnecting", "provider_error")

    def _access_token(self) -> str:
        token = self._tokens.get_token()
        access_token = token.get("access_token") if token else None
        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationRequired()
        return access_token

    def _bridge_message(self, payload: Any) -> None:
        if self._loop is not None and self._on_message is not None:
            self._loop.call_soon_threadsafe(self._on_message, payload)

    def _bridge_state(self, state: str, error_code: str | None) -> None:
        if self._loop is not None and self._on_state is not None:
            self._loop.call_soon_threadsafe(self._on_state, state, error_code)
