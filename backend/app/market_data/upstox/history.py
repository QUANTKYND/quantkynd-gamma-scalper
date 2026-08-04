from __future__ import annotations

from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.market_data.errors import InsufficientHistory
from app.market_data.models import HistoricalCloseDataset
from app.market_data.upstox.client import UpstoxReadOnlyClient


INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


class UpstoxHistoricalCloseProvider:
    def __init__(self, client: UpstoxReadOnlyClient) -> None:
        self._client = client

    async def daily_closes(self, instrument_key: str, from_date: date, to_date: date) -> HistoricalCloseDataset:
        payload = await self._client.historical_candles(instrument_key, from_date, to_date)
        prices = normalize_daily_closes(payload)
        if len(prices) < 100:
            raise InsufficientHistory()
        return HistoricalCloseDataset(instrument_key=instrument_key, prices=prices)


def normalize_daily_closes(payload: Any) -> pd.Series:
    rows = _candle_rows(payload)
    observations: list[tuple[pd.Timestamp, date, float]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        try:
            timestamp = pd.Timestamp(row[0])
            if timestamp.tzinfo is None:
                continue
            timestamp = timestamp.tz_convert(INDIA_TIMEZONE)
            close = float(row[4])
        except (TypeError, ValueError):
            continue
        if not np.isfinite(close) or close <= 0:
            continue
        observations.append((timestamp, timestamp.date(), close))
    observations.sort(key=lambda item: item[0])
    by_date: dict[date, float] = {}
    for _, session_date, close in observations:
        by_date[session_date] = close
    index = pd.DatetimeIndex([pd.Timestamp(session_date) for session_date in sorted(by_date)])
    return pd.Series([by_date[item.date()] for item in index], index=index, name="price", dtype=float)


def _candle_rows(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("candles"), list):
        return data["candles"]
    return []
