from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from app.auth.token_store import TokenStore, token_store
from app.core.config import settings
from app.market_data.errors import AuthenticationRequired, ProviderUnavailable
from app.market_data.metrics import MarketDataMetrics


class UpstoxReadOnlyClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        tokens: TokenStore = token_store,
        base_url: str = settings.upstox_api_base_url,
        metrics: MarketDataMetrics | None = None,
    ) -> None:
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(base_url=base_url, timeout=20.0)
        self._tokens = tokens
        self._metrics = metrics or MarketDataMetrics()

    def access_token(self) -> str:
        token = self._tokens.get_token()
        access_token = token.get("access_token") if token else None
        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationRequired()
        return access_token

    async def search(self, *, query: str, exchanges: tuple[str, ...], segments: tuple[str, ...], limit: int) -> Any:
        self._metrics.increment("instrument_search_requests_total")
        return await self._get(
            "/v2/instruments/search",
            params={
                "query": query,
                "exchanges": ",".join(exchanges),
                "segments": ",".join(segments),
                "page_number": 1,
                "records": limit,
            },
        )

    async def historical_candles(self, instrument_key: str, from_date: date, to_date: date) -> Any:
        self._metrics.increment("historical_candle_requests_total")
        encoded_key = quote(instrument_key, safe="")
        try:
            return await self._get(f"/v3/historical-candle/{encoded_key}/days/1/{to_date.isoformat()}/{from_date.isoformat()}")
        except Exception:
            self._metrics.increment("historical_candle_failures_total")
            raise

    async def _get(self, path: str, params: dict[str, object] | None = None) -> Any:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token()}",
        }
        try:
            response = await self._http_client.get(path, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise ProviderUnavailable() from exc
        if response.status_code in {401, 403}:
            raise AuthenticationRequired()
        if response.status_code == 429:
            raise ProviderUnavailable("Upstox rate limit was reached")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"Upstox request failed with HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderUnavailable("Upstox returned invalid JSON") from exc

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()
