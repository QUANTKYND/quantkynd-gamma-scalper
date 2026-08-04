from __future__ import annotations

import math
import time
from collections import OrderedDict
from typing import Any

from app.instruments.models import InstrumentDefinition
from app.market_data.errors import InstrumentNotFound
from app.market_data.upstox.client import UpstoxReadOnlyClient


ALLOWED_SEGMENTS = {"NSE_INDEX", "BSE_INDEX", "NSE_EQ", "BSE_EQ"}


class UpstoxInstrumentProvider:
    def __init__(self, client: UpstoxReadOnlyClient) -> None:
        self._client = client
        self._resolved: OrderedDict[str, tuple[float, InstrumentDefinition]] = OrderedDict()

    async def search(self, query: str, exchanges: tuple[str, ...], kinds: tuple[str, ...], limit: int) -> tuple[InstrumentDefinition, ...]:
        segments = tuple("INDEX" if kind == "index" else "EQ" for kind in kinds)
        payload = await self._client.search(query=query, exchanges=exchanges, segments=segments, limit=limit)
        items: list[InstrumentDefinition] = []
        seen: set[str] = set()
        for raw in _rows(payload):
            instrument = normalize_instrument(raw)
            if instrument is None or instrument.instrument_key in seen:
                continue
            if instrument.exchange not in exchanges or instrument.kind not in kinds:
                continue
            seen.add(instrument.instrument_key)
            self._remember(instrument)
            items.append(instrument)
        return tuple(items[:limit])

    async def resolve(self, instrument_key: str) -> InstrumentDefinition:
        cached = self._resolved.get(instrument_key)
        if cached is not None and cached[0] > time.monotonic():
            self._resolved.move_to_end(instrument_key)
            return cached[1]
        self._resolved.pop(instrument_key, None)
        if "|" not in instrument_key:
            raise InstrumentNotFound(instrument_key)
        segment, identity = instrument_key.split("|", 1)
        if segment not in ALLOWED_SEGMENTS or not identity:
            raise InstrumentNotFound(instrument_key)
        kind = "index" if segment.endswith("INDEX") else "equity"
        exchange = segment.split("_", 1)[0]
        candidates = await self.search(identity, (exchange,), (kind,), 30)
        for candidate in candidates:
            if candidate.instrument_key == instrument_key:
                return candidate
        raise InstrumentNotFound(instrument_key)

    def _remember(self, instrument: InstrumentDefinition) -> None:
        self._resolved[instrument.instrument_key] = (time.monotonic() + 900, instrument)
        self._resolved.move_to_end(instrument.instrument_key)
        while len(self._resolved) > 500:
            self._resolved.popitem(last=False)


def normalize_instrument(raw: Any) -> InstrumentDefinition | None:
    if not isinstance(raw, dict):
        return None
    key = _text(raw, "instrument_key", "instrumentKey")
    segment = _text(raw, "segment") or (key.split("|", 1)[0] if key and "|" in key else None)
    if not key or segment not in ALLOWED_SEGMENTS:
        return None
    exchange = segment.split("_", 1)[0]
    kind = "index" if segment.endswith("INDEX") else "equity"
    name = _text(raw, "name", "company_name", "companyName", "trading_symbol", "tradingSymbol")
    trading_symbol = _text(raw, "trading_symbol", "tradingSymbol", "short_name", "shortName", "name")
    if not name or not trading_symbol:
        return None
    tick_size = _positive_float(raw.get("tick_size", raw.get("tickSize")))
    lot_size_value = _positive_int(raw.get("lot_size", raw.get("lotSize"))) or 1
    return InstrumentDefinition(
        instrument_key=key,
        exchange=exchange,
        segment=segment,
        kind=kind,
        name=name,
        short_name=_text(raw, "short_name", "shortName"),
        trading_symbol=trading_symbol,
        isin=_text(raw, "isin"),
        tick_size=tick_size,
        lot_size=lot_size_value,
    )


def _rows(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("instruments", "results", "items"):
            rows = data.get(key)
            if isinstance(rows, list):
                return rows
    return []


def _text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
