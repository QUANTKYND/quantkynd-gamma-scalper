from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.market_data.models import LiveQuoteCandidate


def normalize_feed_quotes(
    payload: Any,
    *,
    requested_keys: set[str],
    received_at: datetime,
) -> tuple[LiveQuoteCandidate, ...]:
    if not isinstance(payload, dict):
        return ()
    provider_at = _epoch_time(payload.get("currentTs") or payload.get("current_ts")) or received_at
    feeds = payload.get("feeds")
    if not isinstance(feeds, dict):
        return ()
    quotes: list[LiveQuoteCandidate] = []
    for instrument_key, feed in feeds.items():
        if instrument_key not in requested_keys or not isinstance(feed, dict):
            continue
        ltpc = _ltpc(feed)
        if ltpc is None:
            continue
        ltp = _positive_float(ltpc.get("ltp"))
        last_trade_at = _epoch_time(ltpc.get("ltt"))
        if ltp is None or last_trade_at is None or last_trade_at > received_at + timedelta(minutes=5):
            continue
        quotes.append(
            LiveQuoteCandidate(
                instrument_key=instrument_key,
                ltp=ltp,
                previous_close=_positive_float(ltpc.get("cp")),
                last_trade_quantity=_optional_int(ltpc.get("ltq")),
                last_trade_at=last_trade_at,
                provider_message_at=provider_at,
                received_at=received_at,
                processed_at=datetime.now(UTC),
            )
        )
    return tuple(quotes)


def _ltpc(feed: dict[str, Any]) -> dict[str, Any] | None:
    direct = feed.get("ltpc")
    if isinstance(direct, dict):
        return direct
    full_feed = feed.get("fullFeed") or feed.get("full_feed")
    if isinstance(full_feed, dict):
        market_ff = full_feed.get("marketFF") or full_feed.get("market_ff") or full_feed.get("indexFF") or full_feed.get("index_ff")
        if isinstance(market_ff, dict) and isinstance(market_ff.get("ltpc"), dict):
            return market_ff["ltpc"]
    return None


def normalize_segment_statuses(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    info = payload.get("marketInfo") or payload.get("market_info")
    if not isinstance(info, dict):
        return {}
    statuses = info.get("segmentStatus") or info.get("segment_status")
    if not isinstance(statuses, dict) or not statuses:
        return {}
    return {str(segment): _normalize_market_status(value) for segment, value in statuses.items()}


def market_status_for_segment(segment_statuses: dict[str, str], segment: str) -> str:
    return segment_statuses.get(segment, "unknown")


def _normalize_market_status(value: Any) -> str:
    normalized = str(value).lower()
    if "open" in normalized and "pre" not in normalized:
        return "open"
    if "pre" in normalized:
        return "pre_open"
    if "close" in normalized:
        return "closed"
    return "unknown"


def _epoch_time(value: Any) -> datetime | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    seconds = number / 1000 if number > 10_000_000_000 else number
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _optional_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
